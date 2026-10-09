/**
 * Run one question:
 *   npm run research -- --model haiku --task ebd
 *   npm run research -- --model luna --question "..." [--strategy baseline] [--researchers 10]
 */
import "dotenv/config";
import { TASKS } from "../config/tasks.js";
import { shutdownTracing } from "../observability/langfuse.js";
import { runResearch } from "../run.js";
import { RUN_OPTIONS, parseArgs, runConfigFrom } from "./args.js";

const { values } = parseArgs({
  options: { ...RUN_OPTIONS, model: { type: "string", default: "haiku" }, task: { type: "string" }, question: { type: "string" } },
});
const question = values.question ?? (values.task ? TASKS[values.task] : undefined);
if (!question) {
  console.error(`Give --question "..." or --task <${Object.keys(TASKS).join("|")}>`);
  process.exit(2);
}
const summary = await runResearch(question, runConfigFrom(values, values.model!), (l) => console.error(l));
console.log(JSON.stringify(summary, null, 2));
await shutdownTracing();
process.exit(summary.status === "ok" ? 0 : 1);
