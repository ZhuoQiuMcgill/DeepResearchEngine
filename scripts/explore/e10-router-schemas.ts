// E10: print the baseline-router tool schemas exactly as they are sent to OpenAI in
// strict mode, for a round with three researchers and room for two follow-ups.
import { convertToOpenAITool } from "@langchain/core/utils/function_calling";
import { budgetView } from "../../src/core/budget.js";
import type { ResearchResult } from "../../src/core/contracts.js";
import { buildRouterTools } from "../../src/strategies/baseline-router/tools.js";

const result = (id: string): ResearchResult => ({
  brief: { id, round: 1, objective: id, keyQuestions: ["q"], constraints: [], sourceHints: [] },
  status: "ok",
  notes: "",
  sources: [],
  queries: [],
  usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 },
  model: "gpt-6-luna",
  durationMs: 0,
  unlistedCitations: [],
  diagnostics: [],
});
const tools = buildRouterTools({
  results: ["r1-b1", "r1-b2", "r1-b3"].map(result),
  budget: budgetView({ researchersTotal: 10, toolCallsPerResearcher: 12 }, 3),
  maxBriefs: 2,
  round: 2,
});
console.log(JSON.stringify(tools.definitions.map((t) => convertToOpenAITool(t, { strict: true })), null, 2));
