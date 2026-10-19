import { describe, expect, it } from "vitest";
import { budgetView } from "../src/core/budget.js";
import type { ResearchResult } from "../src/core/contracts.js";
import { buildRouterTools } from "../src/strategies/baseline-router/tools.js";

const NOTES = `## What is X?
### Takeaway
X is a method.
### Cited Findings
- X was introduced in 2001 — [Source](https://example.org/x)
### Inferences
### Gaps
- Its current status is unclear.`;

function result(id: string, status: "ok" | "failed" = "ok"): ResearchResult {
  return {
    brief: { id, round: 1, objective: `Objective of ${id}`, keyQuestions: ["What is X?"], constraints: [], sourceHints: [] },
    status,
    ...(status === "failed" ? { failure: { kind: "timeout" as const, message: "took too long" } } : {}),
    notes: status === "ok" ? NOTES : "",
    sources: status === "ok" ? [{ url: "https://example.org/x", cited: true }, { url: "https://other.net/y", cited: false }] : [],
    queries: [],
    usage: { inputTokens: 1000, outputTokens: 200, searches: 3, pageReads: 1 },
    model: "test",
    durationMs: 4000,
    unlistedCitations: [],
    diagnostics: [],
  };
}

function tools(results = [result("r1-b1"), result("r1-b2"), result("r1-b3", "failed")]) {
  return buildRouterTools({ results, budget: budgetView({ researchersTotal: 10, toolCallsPerResearcher: 12 }, 3), maxBriefs: 2, round: 2 });
}

const brief = (gap: string, targets: string[], objective = "Find the current status of X") => ({
  objective,
  keyQuestions: ["What is the current status of X?"],
  constraints: [],
  sourceHints: [],
  gap,
  targets,
  priority: 5,
});

const code = (out: { ok: boolean; text: string }) => (out.ok ? "ok" : JSON.parse(out.text).error.code);

describe("baseline-router tools", () => {
  it("reports budget and usage per researcher", () => {
    const status = JSON.parse(tools().run("get_round_status", {}).text);
    expect(status.budget.researchers_remaining).toBe(7);
    expect(status.budget.max_new_researchers).toBe(2);
    expect(status.researchers.map((r: { status: string }) => r.status)).toEqual(["ok", "ok", "failed"]);
    expect(status.researchers[0].gaps_reported).toBe(1);
  });

  it("reads one parsed section or rejects a missing one", () => {
    const t = tools();
    expect(JSON.parse(t.run("read_notes", { brief_id: "r1-b1", section: 1 }).text).takeaway).toBe("X is a method.");
    expect(code(t.run("read_notes", { brief_id: "r1-b1", section: 4 }))).toBe("rule_violation");
    expect(code(t.run("read_notes", { brief_id: "r9-b9", section: null }))).toBe("invalid_arguments");
  });

  it("rejects arguments outside the schema", () => {
    const t = tools();
    expect(code(t.run("check_sources", { brief_id: "r1-b1", extra: true }))).toBe("invalid_arguments");
    expect(code(t.run("launch_followups", { briefs: [brief("unclear", ["r1-b1"])], rationale: "x".repeat(30) }))).toBe("invalid_arguments");
    expect(code(t.run("launch_followups", { briefs: [1, 2, 3].map((i) => brief("failed", ["r1-b3"], `Gap number ${i} objective`)), rationale: "x".repeat(30) }))).toBe(
      "invalid_arguments",
    );
    expect(code(t.run("no_such_tool", {}))).toBe("unknown_tool");
  });

  it("requires evidence for each kind of gap", () => {
    const t = tools();
    const launch = (b: object) => t.run("launch_followups", { briefs: [b], rationale: "The status of X is a key part of the question." });
    expect(code(launch(brief("unanswered", ["r1-b1"])))).toBe("rule_violation");
    expect(code(launch(brief("unsourced", ["r1-b1"])))).toBe("rule_violation");
    expect(code(launch(brief("contradiction", ["r1-b1"])))).toBe("rule_violation");
    expect(code(launch(brief("failed", ["r1-b1"])))).toBe("rule_violation");
    expect(code(launch(brief("failed", ["r1-b3"], "Objective of r1-b3")))).toBe("rule_violation"); // repeats round 1
    t.run("read_notes", { brief_id: "r1-b1", section: null });
    expect(code(launch(brief("unanswered", ["r1-b1"])))).toBe("ok");
    expect(t.outcome()).toMatchObject({ kind: "launch", briefs: [{ tag: "unanswered:r1-b1", priority: 5 }] });
    expect(code(t.run("finish_research", { rationale: "Nothing else is needed for this question." }))).toBe("already_decided");
  });

  it("finishes with a reason", () => {
    const t = tools();
    expect(code(t.run("finish_research", { rationale: "short" }))).toBe("rule_violation");
    expect(code(t.run("finish_research", { rationale: "Every key question is answered with cited sources." }))).toBe("ok");
    expect(t.outcome()).toEqual({ kind: "finish", rationale: "Every key question is answered with cited sources." });
  });
});
