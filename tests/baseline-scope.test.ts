import { expect, it } from "vitest";
import { RunnableLambda } from "@langchain/core/runnables";
import { BaselineStrategy } from "../src/strategies/baseline/index.js";
import { needsIdentityRound } from "../src/strategies/baseline/scope.js";
import type { ResearchResult, StrategyContext } from "../src/core/index.js";

it("resolves definition questions and explicit expansions, without making all questions sequential", () => {
  expect(needsIdentityRound("What is ABC (Adaptive Boundary Control)?")).toBe(true);
  expect(needsIdentityRound("Define autopoiesis")).toBe(true);
  expect(needsIdentityRound("Compare solar and wind installation costs")).toBe(false);
});

it("does not guess a domain before sources and passes prior results to every dependent researcher", async () => {
  const question = "What is ABC (Adaptive Boundary Control)?";
  let plannerInput = "";
  const ctx = { today: "2026-10-13", round: 1, runId: "test", budget: {
    researchersRemaining: 4, researchersUsed: 0, researchersTotal: 4, toolCallsPerResearcher: 8 },
    model: { withStructuredOutput: () => RunnableLambda.from(async (input: any) => {
      plannerInput = input.toString();
      return { rationale: "From discovered sources", interpretation: "", briefs: [
        { objective: "Explain the method", keyQuestions: ["How does it work?"], constraints: [], sourceHints: [] },
        { objective: "Explain applications", keyQuestions: ["Where is it used?"], constraints: [], sourceHints: [] },
      ] };
    }) } } as unknown as StrategyContext;
  const strategy = new BaselineStrategy();
  const first = await strategy.init({ question }, ctx);
  expect(plannerInput).toBe(""); // No ungrounded planner call.
  expect(first.decision.briefs).toHaveLength(1);
  expect(first.state.question).toBe(question);
  const result = { status: "ok", brief: { ...first.decision.briefs[0], id: "r1-b1", round: 1 },
    notes: "Original author defines ABC in control engineering — https://example.org/original", diagnostics: [] } as unknown as ResearchResult;
  const second = await strategy.observe(first.state, [result], ctx);
  expect(plannerInput).toContain(result.notes);
  expect(second.decision.briefs).toHaveLength(2);
  for (const brief of second.decision.briefs) {
    expect(brief.instructions).toContain(result.notes);
    expect(brief.constraints?.join("\n")).toContain(question);
  }
  const done = await strategy.observe(second.state, [], ctx);
  expect(done.decision.stop).toBe(true);
  expect(done.state.rounds).toBe(2);
  expect((await strategy.finalize(done.state)).material[0]?.notes).toBe(result.notes);
});

it("stops cleanly without inventing assignments when no identity budget remains", async () => {
  const ctx = { budget: { researchersRemaining: 0 } } as StrategyContext;
  const out = await new BaselineStrategy().init({ question: "Define ABC" }, ctx);
  expect(out.decision.stop).toBe(true);
  expect(out.decision.briefs).toEqual([]);
});
