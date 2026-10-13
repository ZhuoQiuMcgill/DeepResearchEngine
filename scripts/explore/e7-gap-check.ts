// E7: does the baseline gap check launch a follow-up round when an essential
// subtopic is missing? Replays a saved run's round-1 results with one removed
// and one marked failed, using the live model.
import "dotenv/config";
import { readFileSync, readdirSync } from "node:fs";
import { ResearchResultSchema } from "../../src/core/contracts.js";
import { budgetView } from "../../src/core/budget.js";
import { createChatModel, getProfile } from "../../src/config/models.js";
import { BaselineStrategy } from "../../src/strategies/baseline/index.js";

const [dir, profileName] = process.argv.slice(2) as [string, string];
const results = readdirSync(`${dir}/results`).filter((f) => f.endsWith(".json")).sort()
  .map((f) => ResearchResultSchema.parse(JSON.parse(readFileSync(`${dir}/results/${f}`, "utf8"))));
const question = readFileSync(`${dir}/question.txt`, "utf8");
// Simulate: the first researcher failed (provider error), everything else kept.
const damaged = results.map((r, i) => (i === 0 ? { ...r, status: "failed" as const, notes: "", failure: { kind: "provider" as const, message: "Simulated: connection reset before any output" } } : r));
const strategy = new BaselineStrategy();
const ctx = { model: createChatModel(getProfile(profileName)), budget: budgetView({ researchersTotal: 10, toolCallsPerResearcher: 12 }, results.length), round: 2, runId: "e7", today: new Date().toISOString().slice(0, 10) };
const state = { question, interpretation: "", identityFirst: false, rounds: 0, notes: [], failures: [] };
const step = await strategy.observe(state, damaged, ctx);
console.log(JSON.stringify({ failedBrief: results[0]!.brief.objective, stop: step.decision.stop, briefs: step.decision.briefs.map((b) => b.objective), rationale: step.decision.rationale.slice(0, 500) }, null, 1));
