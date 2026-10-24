/**
 * Run viewer: turns run records into static HTML pages that show, step by step,
 * what the agents did: the strategy's model calls (input, reply, check errors),
 * its code actions, the goal table and its changes, the briefs, each
 * researcher's notes with evidence IDs, the writer's input and the report.
 *
 *   npx tsx src/strategies/ebd/viewer/build.ts [run dir or folder of runs ...]
 *
 * Without arguments it reads local/runs, local/checks and local/experiments.
 * It writes local/viewer/index.html and one page per run. The pages are
 * self-contained (no network); open them in a browser.
 *
 * A development tool: the strategy never imports it, and it only reads the
 * run records the platform writes (docs/strategy-modules.md, "Running and testing").
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = resolve("local/viewer");
const DEFAULT_ROOTS = ["local/runs", "local/checks", "local/experiments"];

function readJson(path: string): unknown {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

function readText(path: string): string | null {
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}

/** Every directory under the roots that holds an events.jsonl. */
export function findRuns(roots: string[]): string[] {
  const out: string[] = [];
  const walk = (dir: string, depth: number) => {
    if (!existsSync(dir) || !statSync(dir).isDirectory()) return;
    if (existsSync(join(dir, "events.jsonl"))) {
      out.push(dir);
      return;
    }
    if (depth > 3) return;
    for (const name of readdirSync(dir)) walk(join(dir, name), depth + 1);
  };
  for (const r of roots) walk(resolve(r), 0);
  return out.sort();
}

type Event = { type: string; at: string; data: Record<string, unknown> };

/**
 * One run's data for the page. Researcher notes are kept once (results), not in
 * every state snapshot, so a page stays small enough to open quickly.
 */
export function loadRun(dir: string) {
  const events = (readText(join(dir, "events.jsonl")) ?? "")
    .split("\n")
    .filter(Boolean)
    .flatMap((l) => {
      try {
        return [JSON.parse(l) as Event];
      } catch {
        return [];
      }
    });
  for (const e of events) {
    const state = e.type === "decision" ? (e.data.strategyState as { results?: { notes: string }[] } | null) : null;
    if (state && Array.isArray(state.results)) state.results = state.results.map((r) => ({ ...r, notes: "" }));
  }
  const resultsDir = join(dir, "results");
  const results: Record<string, unknown> = {};
  if (existsSync(resultsDir)) {
    for (const f of readdirSync(resultsDir).filter((n) => n.endsWith(".json"))) results[f.replace(/\.json$/, "")] = readJson(join(resultsDir, f));
  }
  return {
    runId: basename(dir),
    dir: relative(process.cwd(), dir),
    question: readText(join(dir, "question.txt")) ?? "",
    config: readJson(join(dir, "config.json")),
    summary: readJson(join(dir, "summary.json")),
    events,
    results,
    synthesis: readJson(join(dir, "synthesis.json")),
    report: readText(join(dir, "report.md")),
    error: readText(join(dir, "error.txt")),
  };
}

/** Inline JSON safely inside a <script> element. */
function embed(data: unknown): string {
  // "<", U+2028 and U+2029 would end the <script> or a line inside it; write them as JSON escapes.
  const escape = (code: number) => `${String.fromCharCode(92)}u${code.toString(16).padStart(4, "0")}`;
  return JSON.stringify(data).replace(/[<\u2028\u2029]/g, (c) => escape(c.charCodeAt(0)));
}

function page(template: string, title: string, data: unknown): string {
  return template.replace("__TITLE__", title.replace(/[<>&"]/g, "")).replace("__DATA__", embed(data));
}

type IndexRow = {
  file: string;
  runId: string;
  dir: string;
  question: string;
  label: string;
  model: string;
  status: string;
  stopReason: string;
  stopKind: string;
  rounds: number;
  researchers: string;
  cost: number | null;
  at: string;
};

export function build(roots: string[]): { pages: number; index: string } {
  const template = readFileSync(join(here, "page.html"), "utf8");
  const indexTemplate = readFileSync(join(here, "index.html"), "utf8");
  mkdirSync(OUT, { recursive: true });
  const rows: IndexRow[] = [];
  for (const dir of findRuns(roots)) {
    const run = loadRun(dir);
    const file = `${run.runId}.html`;
    writeFileSync(join(OUT, file), page(template, `Run ${run.runId}`, run), "utf8");
    const s = (run.summary ?? {}) as Record<string, any>;
    const lastState = [...run.events].reverse().find((e) => e.type === "decision")?.data.strategyState as Record<string, any> | undefined;
    rows.push({
      file,
      runId: run.runId,
      dir: run.dir,
      question: run.question,
      label: s.strategy?.label ?? (run.config as any)?.strategy?.name ?? "",
      model: s.profile ?? "",
      status: s.status ?? (run.error ? "error" : "incomplete"),
      stopReason: s.stopReason ?? "",
      stopKind: lastState?.stop?.kind ?? "",
      rounds: s.rounds ?? 0,
      researchers: s.researchersUsed !== undefined ? `${s.researchersUsed}/${s.researchersBudget}` : "",
      cost: typeof s.costUsdEstimate === "number" ? s.costUsdEstimate : null,
      at: run.events[0]?.at ?? "",
    });
  }
  rows.sort((a, b) => b.at.localeCompare(a.at));
  const index = join(OUT, "index.html");
  writeFileSync(index, page(indexTemplate, "Runs", rows), "utf8");
  return { pages: rows.length, index };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const { pages, index } = build(args.length ? args : DEFAULT_ROOTS);
  console.log(`${pages} run page(s) written. Open ${index}`);
}
