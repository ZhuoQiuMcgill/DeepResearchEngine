import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import type { IncomingMessage } from "node:http";
import type { Connect, Plugin } from "vite";
import { evaluationCases } from "../../src/evaluation/cases";

const profiles = ["haiku", "luna"] as const;
const keyForProfile = {
  haiku: "ANTHROPIC_API_KEY",
  luna: "OPENAI_API_KEY",
} as const;
const maxJobMs = 20 * 60_000;
const maxFilesBytes = 12 * 1024 * 1024;
const runIdPattern = /^[\w-]{1,180}$/;
const loopbackHost = /^(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$/i;
const frame = "ENGINE_JOB_RESULT ";
const recordNames = [
  "summary.json",
  "config.json",
  "question.txt",
  "events.jsonl",
  "report.md",
  "synthesis.json",
  "guardrails.json",
];
type Profile = (typeof profiles)[number];
type JobRequest =
  | {
      kind: "research";
      question: string;
      strategy: "ebd" | "baseline";
      profile: Profile;
      researchers: number;
    }
  | { kind: "evaluation"; mode: "fixture" }
  | { kind: "evaluation"; mode: "live"; caseId: string; profile: Profile };
type Job = {
  id: string;
  kind: JobRequest["kind"];
  status: "running" | "complete" | "error";
  result?: unknown;
  error?: string;
  runId?: string;
};

function isProfile(value: unknown): value is Profile {
  return value === "haiku" || value === "luna";
}

async function readJson(req: IncomingMessage) {
  let bytes = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    const buffer = Buffer.from(chunk);
    bytes += buffer.length;
    if (bytes > 40_000) throw new Error("Job request is too large.");
    chunks.push(buffer);
  }
  const value = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Expected a job object.");
  return value as Record<string, unknown>;
}

function validate(
  value: Record<string, unknown>,
  liveProfiles: readonly Profile[],
): JobRequest {
  if (value.kind === "evaluation" && value.mode === "fixture")
    return { kind: "evaluation", mode: "fixture" };
  const profile = value.profile;
  if (!isProfile(profile) || !liveProfiles.includes(profile))
    throw new Error(
      "Configure the selected model profile on the engine server.",
    );
  if (value.kind === "evaluation") {
    if (
      value.mode !== "live" ||
      typeof value.caseId !== "string" ||
      !evaluationCases.some((entry) => entry.id === value.caseId)
    ) {
      throw new Error("Choose an evaluation case.");
    }
    return { kind: "evaluation", mode: "live", caseId: value.caseId, profile };
  }
  const { question, researchers, strategy } = value;
  if (
    value.kind !== "research" ||
    (strategy !== "ebd" && strategy !== "baseline")
  )
    throw new Error("Choose EBD or Baseline research.");
  if (
    typeof question !== "string" ||
    !question.trim() ||
    question.length > 6000
  )
    throw new Error("Enter a question of 1–6000 characters.");
  if (
    typeof researchers !== "number" ||
    !Number.isInteger(researchers) ||
    researchers < 1 ||
    researchers > 12
  ) {
    throw new Error("Choose a researcher budget between 1 and 12.");
  }
  return { kind: "research", question, researchers, strategy, profile };
}

async function recordFiles(
  root: string,
  runId: string,
  redact: (text: string) => string,
) {
  const folder = join(root, "local", "ui-runs", runId);
  const names = [...recordNames];
  try {
    for (const entry of await readdir(join(folder, "results"), {
      withFileTypes: true,
    })) {
      if (entry.isFile() && /^r\d+-b\d+\.(json|md)$/.test(entry.name))
        names.push(`results/${entry.name}`);
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  let total = 0;
  const files: { name: string; relativePath: string; text: string }[] = [];
  for (const name of names) {
    const path = join(folder, name);
    try {
      const info = await stat(path);
      if (!info.isFile() || (total += info.size) > maxFilesBytes) {
        throw new Error(
          "This record is too large to open in the browser. Open its folder from Engine Run Review.",
        );
      }
      let content = redact(await readFile(path, "utf8"));
      if (name === "summary.json") {
        const summary = JSON.parse(content);
        if (summary.error)
          summary.error =
            "The engine reported a failure. Inspect the local run folder for diagnostics.";
        content = JSON.stringify(summary);
      }
      files.push({
        name: name.split("/").at(-1)!,
        relativePath: `${runId}/${name}`,
        text: content,
      });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
  if (
    !files.some(
      (item) => item.name === "summary.json" || item.name === "config.json",
    )
  )
    throw new Error("The engine did not create a readable run record.");
  return files;
}

export function officialEnginePlugin(
  root: string,
  providerEnv: Record<string, string>,
): Plugin {
  const jobs = new Map<string, Job>();
  const liveProfiles = profiles.filter((profile) =>
    Boolean(providerEnv[keyForProfile[profile]]?.trim()),
  );
  let active = false;
  let activeChild: ChildProcess | undefined;
  const entry = join(root, "src", "cli", "ui-job.ts");
  const secrets = liveProfiles
    .map((profile) => providerEnv[keyForProfile[profile]])
    .filter((value) => value.length >= 8);
  const redact = (text: string) =>
    secrets.reduce(
      (value, secret) => value.replaceAll(secret, "[redacted]"),
      text,
    );

  function start(input: JobRequest): Job {
    if (jobs.size >= 12) {
      const oldest = jobs.keys().next().value;
      if (oldest) jobs.delete(oldest);
    }
    const job: Job = { id: randomUUID(), kind: input.kind, status: "running" };
    jobs.set(job.id, job);
    active = true;
    const child = spawn(process.execPath, ["--import", "tsx", entry], {
      cwd: root,
      env: { ...process.env, ...providerEnv },
      stdio: ["pipe", "pipe", "ignore"],
      windowsHide: true,
    });
    activeChild = child;
    const buffers: Buffer[] = [];
    let bytes = 0;
    let failure: string | undefined;
    let settled = false;
    const timer = setTimeout(() => {
      failure = "The job exceeded the 20-minute limit.";
      child.kill();
    }, maxJobMs);
    function finish(error?: string) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      active = false;
      activeChild = undefined;
      job.status = error ? "error" : "complete";
      if (error) job.error = error;
    }
    child.stdout.on("data", (chunk: Buffer) => {
      bytes += chunk.length;
      if (bytes > 2_000_000) {
        failure = "The engine returned a result that was too large.";
        child.kill();
        return;
      }
      buffers.push(chunk);
    });
    child.stdin.on("error", () => {});
    child.on("error", () =>
      finish(
        "Could not start the engine. Install the root project dependencies.",
      ),
    );
    child.on("close", (code) => {
      if (settled) return;
      if (code !== 0 || failure) {
        finish(
          failure ??
            "The engine job failed. Check the model configuration and the local run files.",
        );
        return;
      }
      try {
        const line = Buffer.concat(buffers)
          .toString("utf8")
          .split(/\r?\n/)
          .findLast((line) => line.startsWith(frame));
        const result = JSON.parse(redact(line?.slice(frame.length) ?? ""));
        if (input.kind === "research") {
          if (
            typeof result?.runId !== "string" ||
            !runIdPattern.test(result.runId)
          )
            throw new Error();
          job.runId = result.runId;
          job.result = { runId: job.runId, runStatus: result.status };
        } else {
          job.result = result;
        }
        finish();
      } catch {
        finish("The engine did not return a readable result.");
      }
    });
    child.stdin.end(JSON.stringify(input));
    return job;
  }

  const middleware: Connect.NextHandleFunction = async (req, res, next) => {
    const path = req.url?.split("?")[0];
    if (path !== "/api/engine" && !path?.startsWith("/api/engine/"))
      return next();
    const send = (status: number, data: unknown) => {
      res.statusCode = status;
      res.setHeader("Content-Type", "application/json");
      res.setHeader("Cache-Control", "no-store");
      res.end(JSON.stringify(data));
    };
    if (
      !loopbackHost.test(req.headers.host ?? "") ||
      (req.headers.origin &&
        req.headers.origin !== `http://${req.headers.host}`)
    ) {
      return send(403, { error: "Origin not allowed." });
    }
    if (req.method === "GET" && path === "/api/engine") {
      return send(200, {
        profiles,
        liveProfiles,
        cases: evaluationCases.map(({ id, objective, question }) => ({
          id,
          title:
            id === "dated-conflict"
              ? "Dated evidence conflict"
              : "Untrusted report instructions",
          objective,
          question,
        })),
      });
    }
    if (req.method === "POST" && path === "/api/engine/jobs") {
      if (
        !/^application\/json(?:;|$)/i.test(
          String(req.headers["content-type"] ?? ""),
        )
      ) {
        return send(415, { error: "Expected a JSON job request." });
      }
      if (active)
        return send(409, { error: "An engine job is already running." });
      try {
        const input = validate(await readJson(req), liveProfiles);
        if (active)
          return send(409, { error: "An engine job is already running." });
        return send(202, start(input));
      } catch (error) {
        return send(400, {
          error:
            error instanceof SyntaxError
              ? "Expected a valid JSON job request."
              : (error as Error).message,
        });
      }
    }
    const match = path?.match(/^\/api\/engine\/jobs\/([a-f\d-]+)(\/files)?$/);
    const job = match ? jobs.get(match[1]) : undefined;
    if (req.method !== "GET" || !job)
      return send(404, { error: "Engine job not found." });
    if (!match?.[2]) return send(200, job);
    if (job.status !== "complete" || !job.runId)
      return send(409, { error: "The run record is not ready." });
    try {
      return send(200, { files: await recordFiles(root, job.runId, redact) });
    } catch {
      return send(409, {
        error:
          "Could not load the run in the browser. Open its folder under local/ui-runs.",
      });
    }
  };
  return {
    name: "official-engine",
    configureServer(server) {
      server.middlewares.use(middleware);
      server.httpServer?.once("close", () => activeChild?.kill());
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
      server.httpServer.once("close", () => activeChild?.kill());
    },
  };
}
