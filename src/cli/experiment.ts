/**
 * Run an experiment spec:
 *   npm run experiment -- experiments/baseline-all.json [--dry-run]
 */
import "dotenv/config";
import { readFileSync } from "node:fs";
import { shutdownTracing } from "../observability/langfuse.js";
import { planJobs, resultsTable, runExperiment } from "../platform/experiment.js";

const file = process.argv[2];
if (!file) {
  console.error("Usage: npm run experiment -- <spec.json> [--dry-run]");
  process.exit(2);
}
const spec = JSON.parse(readFileSync(file, "utf8"));
if (process.argv.includes("--dry-run")) {
  const { jobs } = planJobs(spec);
  for (const j of jobs) console.log(`${j.taskId} | ${j.strategy.label} | ${j.model} | #${j.repeat}`);
  console.log(`${jobs.length} run(s)`);
  process.exit(0);
}
const result = await runExperiment(spec, (l) => console.error(l));
console.log(resultsTable(result.summaries));
console.log(`Records: ${result.dir}`);
await shutdownTracing();
process.exit(result.summaries.every((s) => s.status === "ok") ? 0 : 1);
