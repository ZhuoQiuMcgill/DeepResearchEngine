import "dotenv/config";
import { parseArgs } from "node:util";
import { runFixtureReplay, runLiveEvaluation } from "../evaluation/index.js";
import { shutdownTracing } from "../observability/langfuse.js";

const { values } = parseArgs({
  options: {
    case: { type: "string" },
    profile: { type: "string" },
    researchers: { type: "string", default: "4" },
  },
});
try {
  if (Boolean(values.case) !== Boolean(values.profile)) {
    throw new Error("Pass both --case and --profile for a live evaluation.");
  }
  const result =
    values.case && values.profile
      ? await runLiveEvaluation({
          caseId: values.case,
          profile: values.profile,
          researchersTotal: Number(values.researchers),
          outDir: "local/evaluation-runs",
        })
      : runFixtureReplay();
  console.log(JSON.stringify(result, null, 2));
} finally {
  await shutdownTracing();
}
