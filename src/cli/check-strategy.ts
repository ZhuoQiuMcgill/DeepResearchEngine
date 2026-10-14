/**
 * Check a strategy module against the contract with one live run:
 *   npm run check-strategy -- --strategy ebd [--model haiku] [--task ebd] [--options '{...}']
 * Exits non-zero when any check fails.
 */
import "dotenv/config";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { parseArgs } from "node:util";
import { TASKS } from "../config/tasks.js";
import type { DecisionRecord } from "../graph/skeleton.js";
import { shutdownTracing } from "../observability/langfuse.js";
import { runOne } from "../platform/run.js";
import { loadStrategyModule } from "../platform/strategies.js";

const { values } = parseArgs({
  options: {
    strategy: { type: "string" },
    options: { type: "string" },
    model: { type: "string", default: "haiku" },
    task: { type: "string", default: "ebd" },
    researchers: { type: "string", default: "6" },
    concurrency: { type: "string", default: "4" },
  },
});
if (!values.strategy) {
  console.error("Usage: npm run check-strategy -- --strategy <name> [--model haiku] [--task ebd] [--options '{...}']");
  process.exit(2);
}

type Check = { level: "FAIL" | "WARN" | "PASS"; name: string; detail?: string };
const checks: Check[] = [];
const add = (ok: boolean, name: string, detail?: string, level: "FAIL" | "WARN" = "FAIL") =>
  checks.push({ level: ok ? "PASS" : level, name, ...(detail ? { detail } : {}) });

let loaded = false;
try {
  const m = await loadStrategyModule(values.strategy);
  add(true, `module loads (${m.name}, contract ${m.contractVersion})`);
  loaded = true;
} catch (e) {
  add(false, "module loads", String((e as Error).message));
}

if (loaded) {
  const summary = await runOne(
    {
      question: TASKS[values.task!] ?? values.task!,
      strategy: { name: values.strategy, ...(values.options ? { options: JSON.parse(values.options) } : {}) },
      profile: values.model!,
      researchersTotal: Number(values.researchers),
      maxRounds: 8,
      concurrency: Number(values.concurrency),
      researcherTimeoutMs: 8 * 60_000,
      outDir: "local/checks",
    },
    (l) => console.error(l),
  );
  const decisions: DecisionRecord[] = existsSync(join(summary.dir, "events.jsonl"))
    ? readFileSync(join(summary.dir, "events.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l)).filter((e) => e.type === "decision").map((e) => e.data)
    : [];
  add(summary.status === "ok", "run completes with a report", summary.error);
  add(decisions[0]?.phase === "init" && decisions[0].accepted.length > 0, "init returns at least one valid brief");
  const invalid = decisions.flatMap((d) => d.invalid);
  add(invalid.length === 0, "every brief is valid", invalid[0] ? `${invalid.length} invalid, e.g. ${invalid[0].reason}` : undefined);
  const ignored = decisions.reduce((n, d) => n + d.ignored.length, 0);
  add(ignored === 0, "no briefs returned together with stop: true", ignored ? `${ignored} ignored` : undefined, "WARN");
  add(decisions.every((d) => d.rationale.trim().length > 0), "every decision has a rationale", undefined, "WARN");
  add(summary.stopReason !== "max-rounds", "stops on its own before the round safety cap", summary.stopReason, "WARN");
  const synth = (prefix: string) => summary.diagnostics.find((d) => d.startsWith(`synthesis: ${prefix}`));
  add(!synth("invalid SynthesisInput"), "finalize returns a valid SynthesisInput", synth("invalid SynthesisInput"));
  add(!synth("synthesis has no material"), "finalize passes material to the writer");
  const prov = summary.diagnostics.find((d) => /material line\(s\) are not researcher notes/.test(d));
  add(!prov, "material consists of researcher notes lines", prov);
  add(summary.citationCheck.unknownUrls.length === 0, "report cites only URLs from the research", summary.citationCheck.unknownUrls.join(" "), "WARN");
  console.log(`\nRun record: ${summary.dir}  cost ≈ $${summary.costUsdEstimate.toFixed(3)}`);
}

console.log("");
for (const c of checks) console.log(`${c.level.padEnd(4)}  ${c.name}${c.detail ? ` — ${c.detail}` : ""}`);
const failed = checks.filter((c) => c.level === "FAIL").length;
console.log(`\n${failed ? `${failed} check(s) failed` : "All required checks passed"}`);
await shutdownTracing();
process.exit(failed ? 1 : 0);
