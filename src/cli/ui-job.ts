import "dotenv/config";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { shutdownTracing } from "../observability/langfuse.js";
import { runOne } from "../platform/run.js";

// The local UI server sends one validated job over stdin. No shell or positional
// argument ever interprets the research question.
type ResearchJob = {
  kind: "research";
  question: string;
  strategy: "ebd" | "baseline";
  profile: string;
  researchers: number;
};
const chunks: Buffer[] = [];
let bytes = 0;
for await (const chunk of process.stdin) {
  const buffer = Buffer.from(chunk);
  bytes += buffer.length;
  if (bytes > 40_000) throw new Error("Job input is too large.");
  chunks.push(buffer);
}
const job = JSON.parse(Buffer.concat(chunks).toString("utf8")) as ResearchJob;
if (job.kind !== "research") throw new Error("Expected a research job.");
const outDir = resolve("local", "ui-runs");
await mkdir(outDir, { recursive: true });

let result: unknown;
try {
  const summary = await runOne({
    question: job.question,
    strategy: { name: job.strategy },
    profile: job.profile,
    researchersTotal: job.researchers,
    maxRounds: 8,
    concurrency: 4,
    researcherTimeoutMs: 8 * 60_000,
    outDir,
  });
  result = { runId: summary.runId, status: summary.status };
} finally {
  await shutdownTracing();
}
console.log("ENGINE_JOB_RESULT " + JSON.stringify(result));
