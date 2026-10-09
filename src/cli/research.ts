/**
 * Run one question:
 *   npm run research -- --strategy baseline --model haiku --task ebd
 *   npm run research -- --strategy baseline --model luna --question "..." [--options '{"maxPerRound":4}'] [--researchers 10]
 */
import "dotenv/config";
import { parseArgs } from "node:util";
import { TASKS } from "../config/tasks.js";
import { shutdownTracing } from "../observability/langfuse.js";
import { runOne } from "../platform/run.js";

const { values } = parseArgs({
  options: {
    strategy: { type: "string", default: "baseline" },
    options: { type: "string" },
    model: { type: "string", default: "haiku" },
    task: { type: "string" },
    question: { type: "string" },
    researchers: { type: "string", default: "10" },
    out: { type: "string", default: "local/runs" },
  },
});
const question = values.question ?? (values.task ? TASKS[values.task] : undefined);
if (!question) {
  console.error(`Give --question "..." or --task <${Object.keys(TASKS).join("|")}>`);
  process.exit(2);
}
const summary = await runOne(
  {
    question,
    strategy: { name: values.strategy!, ...(values.options ? { options: JSON.parse(values.options) } : {}) },
    profile: values.model!,
    researchersTotal: Number(values.researchers),
    maxRounds: 8,
    concurrency: 4,
    researcherTimeoutMs: 8 * 60_000,
    outDir: values.out!,
  },
  (l) => console.error(l),
);
console.log(JSON.stringify(summary, null, 2));
await shutdownTracing();
process.exit(summary.status === "ok" ? 0 : 1);
