/**
 * Run several tasks on several model profiles:
 *   npm run batch -- --models haiku,luna --tasks ebd,headset,flight,sleep [--parallel 2]
 */
import "dotenv/config";
import { TASKS } from "../config/tasks.js";
import { shutdownTracing } from "../observability/langfuse.js";
import { runResearch, type RunSummary } from "../run.js";
import { RUN_OPTIONS, parseArgs, runConfigFrom } from "./args.js";

const { values } = parseArgs({
  options: {
    ...RUN_OPTIONS,
    models: { type: "string", default: "haiku,luna" },
    tasks: { type: "string", default: Object.keys(TASKS).join(",") },
    parallel: { type: "string", default: "2" },
  },
});
const jobs = values.models!.split(",").flatMap((m) => values.tasks!.split(",").map((t) => ({ model: m.trim(), task: t.trim() })));
for (const j of jobs) if (!TASKS[j.task]) throw new Error(`Unknown task ${j.task}`);

const summaries: (RunSummary & { task: string })[] = [];
let next = 0;
async function worker() {
  while (next < jobs.length) {
    const job = jobs[next++]!;
    const s = await runResearch(TASKS[job.task]!, runConfigFrom(values, job.model), (l) => console.error(l));
    summaries.push({ ...s, task: job.task });
    console.error(`DONE ${job.model}/${job.task}: ${s.status} ${s.dir}`);
  }
}
await Promise.all(Array.from({ length: Math.max(1, Number(values.parallel)) }, worker));
await shutdownTracing();

const rows = summaries
  .sort((a, b) => a.profile.localeCompare(b.profile) || a.task.localeCompare(b.task))
  .map((s) =>
    [s.profile, s.task, s.status, s.stopReason ?? "-", `${s.researchersUsed}/${s.researchersBudget}`, `${s.results.ok}/${s.results.failed}`, s.searches, s.pageReads, `$${s.costUsdEstimate.toFixed(3)}`, `${Math.round(s.durationMs / 1000)}s`, s.citationCheck.unknownUrls.length, `${s.citationCheck.binding.unbound}/${s.citationCheck.binding.checked}`, s.diagnostics.length, s.runId].join(" | "),
  );
console.log(["model | task | status | stop | researchers | ok/failed | searches | reads | cost | time | unknownUrls | unbound | diags | runId", ...rows].join("\n"));
