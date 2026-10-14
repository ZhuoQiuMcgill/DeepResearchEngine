import { describe, expect, it } from "vitest";
import { applyDecision, budgetView } from "../src/core/budget.js";

const brief = (objective: string, priority?: number) => ({ objective, keyQuestions: ["q"], ...(priority === undefined ? {} : { priority }) });

describe("applyDecision", () => {
  it("assigns ids and round to accepted briefs", () => {
    const out = applyDecision({ briefs: [brief("a"), brief("b")], stop: false, rationale: "" }, 1, budgetView({ researchersTotal: 5, toolCallsPerResearcher: 8 }, 0));
    expect(out.accepted.map((b) => [b.id, b.round, b.objective])).toEqual([["r1-b1", 1, "a"], ["r1-b2", 1, "b"]]);
    expect(out.stop).toBe(false);
  });

  it("drops lowest priority beyond the remaining budget and keeps strategy order", () => {
    const out = applyDecision(
      { briefs: [brief("low", 0), brief("high", 5), brief("mid", 2)], stop: false, rationale: "" },
      2,
      budgetView({ researchersTotal: 4, toolCallsPerResearcher: 8 }, 2),
    );
    expect(out.accepted.map((b) => b.objective)).toEqual(["high", "mid"]);
    expect(out.dropped.map((b) => b.objective)).toEqual(["low"]);
  });

  it("ignores briefs when stop is true", () => {
    const out = applyDecision({ briefs: [brief("a")], stop: true, rationale: "" }, 2, budgetView({ researchersTotal: 4, toolCallsPerResearcher: 8 }, 0));
    expect(out.accepted).toEqual([]);
    expect(out.ignored).toHaveLength(1);
    expect(out.stop).toBe(true);
  });

  it("reports invalid briefs instead of throwing", () => {
    const out = applyDecision({ briefs: [{ objective: "", keyQuestions: [] } as never, brief("ok")], stop: false, rationale: "" }, 1, budgetView({ researchersTotal: 4, toolCallsPerResearcher: 8 }, 0));
    expect(out.invalid).toHaveLength(1);
    expect(out.accepted.map((b) => b.objective)).toEqual(["ok"]);
  });
});
