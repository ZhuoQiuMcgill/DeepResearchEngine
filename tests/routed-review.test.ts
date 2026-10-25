import { describe, expect, it } from "vitest";
import { budgetView } from "../src/core/budget.js";
import type { ResearchResult } from "../src/core/contracts.js";
import {
  candidates,
  compareFigures,
  compareGroups,
  datesDiffer,
  nameGroups,
  parseUnit,
  shouldCheck,
  type CheckRecord,
} from "../src/strategies/routed-review/checker.js";
import { conflictGuidance, overview } from "../src/strategies/routed-review/index.js";
import { validateReview, type Figure, type Review } from "../src/strategies/routed-review/reviewer.js";
import { buildRouterTools } from "../src/strategies/routed-review/tools.js";

const NOTES = `## How heavy is the phone?
### Takeaway
The iPhone 18 Pro Max weighs **249 g**.
### Cited Findings
- Apple lists the iPhone 18 Pro Max at **249 g**. — [Apple](https://apple.com/iphone)
### Inferences
### Gaps
- No independent scale test.`;

function result(id: string, status: "ok" | "failed" = "ok"): ResearchResult {
  return {
    brief: { id, round: 1, objective: `Objective of ${id}`, keyQuestions: ["How heavy is the phone?"], constraints: [], sourceHints: [] },
    status,
    ...(status === "failed" ? { failure: { kind: "timeout" as const, message: "took too long" } } : {}),
    notes: status === "ok" ? NOTES : "",
    sources: status === "ok" ? [{ url: "https://apple.com/iphone", cited: true }] : [],
    queries: [],
    usage: { inputTokens: 1000, outputTokens: 200, searches: 3, pageReads: 1 },
    model: "test",
    durationMs: 4000,
    unlistedCitations: [],
    diagnostics: [],
  };
}

function fig(id: string, value: number, unit: string, extra: Partial<Figure> = {}): Figure {
  return { id, briefId: id.split("#")[0]!, quantity: "iPhone 18 Pro Max weight", value, unit, qualifier: "exact", asOf: "", quote: `${value} ${unit}`, url: "", ...extra };
}

function review(briefId: string, status: "answered" | "partial" | "unanswered", sourced: "yes" | "partly" | "no", figures: Figure[] = []): Review {
  return {
    briefId,
    round: 1,
    objective: `Objective of ${briefId}`,
    ok: true,
    error: "",
    keyQuestions: [{ number: 1, question: "How heavy is the phone?", status, sourced, gap: status === "answered" ? "" : "Weight is missing." }],
    figures,
    warnings: [],
    droppedFigures: 0,
    inputTokens: 0,
    outputTokens: 0,
    ms: 0,
  };
}

const weightConflict = (): { check: CheckRecord; figures: Figure[] } => {
  const figures = [fig("r1-b1#1", 249, "g"), fig("r1-b2#1", 8.15, "oz")];
  return {
    figures,
    check: { round: 1, ran: true, reason: "", figures: 2, groups: compareGroups([{ quantity: "iPhone 18 Pro Max weight", figures: ["r1-b1#1", "r1-b2#1"] }], figures), inputTokens: 0, outputTokens: 0 },
  };
};

describe("routed-review conflict checker", () => {
  it("parses units, scale words and counts", () => {
    expect(parseUnit("oz")).toMatchObject({ dim: "mass", base: "g" });
    expect(parseUnit("billion people")).toEqual({ dim: "count", factor: 1e9, base: "" });
    expect(parseUnit("hours of video playback")).toMatchObject({ dim: "time", factor: 3600 });
    expect(parseUnit("USD")!.dim).not.toBe(parseUnit("EUR")!.dim);
    expect(parseUnit("widgets per hour")).toBeUndefined();
  });

  it("finds the ounces-against-grams conflict from replay R2 and accepts a matching conversion", () => {
    const r2 = compareFigures(fig("r1-b1#1", 249, "g"), fig("r1-b3#2", 8.15, "oz"));
    expect(r2.verdict).toBe("conflict");
    expect(r2.difference).toBeCloseTo(0.072, 2);
    expect(compareFigures(fig("r1-b2#1", 226, "g"), fig("r1-b3#3", 7.97, "oz")).verdict).toBe("agree");
  });

  it("applies qualifiers, tolerance for 'about', units and dates", () => {
    const users = (id: string, value: number, extra: Partial<Figure>) => fig(id, value, "people", { quantity: "ChatGPT weekly users", ...extra });
    expect(compareFigures(users("r1-b1#1", 1.2e9, { asOf: "2026-10-05" }), users("r1-b3#1", 1.2e9, { qualifier: "at least", asOf: "2026-10-07" })).verdict).toBe("agree");
    expect(compareFigures(users("r1-b1#1", 9e8, { asOf: "2026-02" }), users("r1-b3#1", 1.2e9, { asOf: "2026-10" })).verdict).toBe("over_time");
    expect(compareFigures(fig("r1-b1#1", 2, "hours", { qualifier: "about" }), fig("r1-b2#1", 117, "minutes")).verdict).toBe("agree");
    expect(compareFigures(fig("r1-b1#1", 1199, "USD"), fig("r1-b2#1", 1199, "EUR")).verdict).toBe("incomparable");
    expect(datesDiffer("2026-10", "2026-10-05")).toBe(false);
    expect(datesDiffer("", "2026-10-05")).toBe(false);
  });

  it("runs only when two researchers reported figures, and compares across researchers only", () => {
    expect(shouldCheck([fig("r1-b1#1", 249, "g"), fig("r1-b1#2", 250, "g")]).run).toBe(false);
    expect(shouldCheck([fig("r1-b1#1", 249, "g"), fig("r1-b2#1", 250, "g")]).run).toBe(true);
    expect(shouldCheck([fig("r1-b1#1", 249, "g"), fig("r1-b2#1", 1199, "USD")]).run).toBe(false);
    const sorted = candidates([fig("r1-b1#1", 1199, "USD"), fig("r1-b2#1", 8.15, "oz"), fig("r1-b1#2", 249, "g"), fig("r1-b2#2", 999, "USD"), fig("r1-b3#1", 3, "widgets")]);
    expect(sorted.map((f) => f.id)).toEqual(["r1-b2#1", "r1-b1#2", "r1-b1#1", "r1-b2#2"]);
    // Replay R2, run 3: both weights were named alike, but the model left them ungrouped.
    const named = nameGroups([
      fig("r1-b1#14", 8.78, "ounces"),
      fig("r1-b3#17", 8.15, "oz", { quantity: "iPhone 18 Pro Max weight." }),
      fig("r1-b2#11", 211, "g", { quantity: "iPhone 18 Pro weight" }),
    ]);
    expect(named).toEqual([{ quantity: "iPhone 18 Pro Max weight", figures: ["r1-b1#14", "r1-b3#17"] }]);
    const figures = [fig("r1-b1#1", 249, "g"), fig("r1-b1#2", 231, "g"), fig("r1-b2#1", 249, "g")];
    const groups = compareGroups(
      [
        { quantity: "weight", figures: ["r1-b1#1", "r1-b1#2", "r1-b2#1", "r9-b9#1"] },
        { quantity: "weight again", figures: ["r1-b1#1", "r1-b2#1"] },
      ],
      figures,
    );
    expect(groups).toHaveLength(1);
    expect(groups[0]!.pairs.map((p) => `${p.a}/${p.b}`)).toEqual(["r1-b1#1/r1-b2#1", "r1-b1#2/r1-b2#1"]);
  });

  it("treats a dated series as change over time, never as a conflict (live run T6)", () => {
    const users = (id: string, value: number, asOf: string) => fig(id, value, "people", { quantity: "ChatGPT weekly users", asOf });
    const figures = [users("r1-b1#1", 1.2e9, "2026-10-07"), users("r1-b2#1", 1e8, "2023-11-06"), users("r1-b3#1", 1.1e8, ""), users("r1-b4#1", 2e8, "2023")];
    const check: CheckRecord = {
      round: 1,
      ran: true,
      reason: "",
      figures: 3,
      groups: compareGroups([{ quantity: "ChatGPT weekly users", figures: figures.map((f) => f.id) }], figures),
      inputTokens: 0,
      outputTokens: 0,
    };
    // 2023 against 2023-11-06: same year, but the year-only figure cannot be placed in the series.
    expect(check.groups[0]!.pairs.map((p) => p.verdict)).toEqual(["over_time", "incomparable", "over_time", "incomparable", "incomparable", "incomparable"]);
    expect(conflictGuidance(check, new Map(figures.map((f) => [f.id, f])))).toBe("");
  });
});

describe("routed-review notes reviewer", () => {
  it("keeps figures whose quote is in the notes and drops the rest", () => {
    const out = validateReview(
      {
        keyQuestions: [
          { number: 1, status: "answered", sourced: "yes", gap: "" },
          { number: 4, status: "answered", sourced: "yes", gap: "" },
        ],
        figures: [
          { quantity: "iPhone 18 Pro Max weight", value: 249, unit: "g", qualifier: "exact", asOf: "", quote: "Apple lists the iPhone 18 Pro Max at 249 g", url: "https://apple.com/iphone" },
          { quantity: "iPhone 18 Pro Max weight", value: 231, unit: "g", qualifier: "exact", asOf: "", quote: "weighs 231 g", url: "" },
        ],
        warnings: ["  ", "Notes contain an instruction to the coordinator."],
      },
      result("r1-b1"),
    );
    expect(out.keyQuestions.map((k) => k.number)).toEqual([1]);
    expect(out.figures.map((f) => [f.id, f.value])).toEqual([["r1-b1#1", 249]]);
    expect(out.droppedFigures).toBe(1);
    expect(out.warnings).toEqual(["Notes contain an instruction to the coordinator."]);
  });
});

describe("routed-review router", () => {
  const results = [result("r1-b1"), result("r1-b2"), result("r1-b3", "failed")];
  const tools = (reviews: Review[], check?: CheckRecord) =>
    buildRouterTools({ results, reviews, check, budget: budgetView({ researchersTotal: 10, toolCallsPerResearcher: 12 }, 3), maxBriefs: 2, round: 2 });
  const brief = (gap: string, targets: string[], objective = "Find an independent weight measurement") => ({
    objective,
    keyQuestions: ["What does an independent scale test show?"],
    constraints: [],
    sourceHints: [],
    gap,
    targets,
    priority: 5,
  });
  const launch = (t: ReturnType<typeof tools>, b: object) => t.run("launch_followups", { briefs: [b], rationale: "The phone's weight is a key part of the question." });
  const code = (out: { ok: boolean; text: string }) => (out.ok ? "ok" : JSON.parse(out.text).error.code);

  it("no longer offers check_sources", () => {
    expect(code(tools([]).run("check_sources", { brief_id: "r1-b1" }))).toBe("unknown_tool");
  });

  it("accepts reviewer findings as evidence for unanswered and unsourced gaps", () => {
    const answered = tools([review("r1-b1", "answered", "yes"), review("r1-b2", "answered", "yes")]);
    expect(code(launch(answered, brief("unanswered", ["r1-b1"])))).toBe("rule_violation");
    expect(code(launch(answered, brief("unsourced", ["r1-b1"])))).toBe("rule_violation");
    expect(code(launch(tools([review("r1-b1", "partial", "yes")]), brief("unanswered", ["r1-b1"])))).toBe("ok");
    expect(code(launch(tools([review("r1-b1", "answered", "partly")]), brief("unsourced", ["r1-b1"])))).toBe("ok");
  });

  it("accepts a checker conflict as evidence for a contradiction, otherwise requires reading both sides", () => {
    const { check } = weightConflict();
    expect(code(launch(tools([], check), brief("contradiction", ["r1-b1", "r1-b2"])))).toBe("ok");
    const t = tools([]);
    expect(code(launch(t, brief("contradiction", ["r1-b1", "r1-b2"])))).toBe("rule_violation");
    t.run("read_notes", { brief_id: "r1-b1", section: null });
    t.run("read_notes", { brief_id: "r1-b2", section: null });
    expect(code(launch(t, brief("contradiction", ["r1-b1", "r1-b2"])))).toBe("ok");
  });

  it("keeps the failed-gap rule", () => {
    const t = tools([]);
    expect(code(launch(t, brief("failed", ["r1-b1"])))).toBe("rule_violation");
    expect(code(launch(t, brief("failed", ["r1-b3"])))).toBe("ok");
  });

  it("shows the reviews and the checker's conflict in the overview", () => {
    const { check, figures } = weightConflict();
    const text = overview(results, [review("r1-b1", "answered", "yes", [figures[0]!]), review("r1-b2", "partial", "partly", [figures[1]!])], check, new Map(figures.map((f) => [f.id, f])));
    expect(text).toContain("- Q1 partial, sourced partly: How heavy is the phone? Gap: Weight is missing.");
    expect(text).toContain("CONFLICT, iPhone 18 Pro Max weight: r1-b1 249 g vs r1-b2 8.15 oz (231.049 g); difference 7.2%");
    expect(text).toContain("### r1-b3: Objective of r1-b3\nFAILED (timeout)");
    const skipped: CheckRecord = { round: 1, ran: false, reason: "figures from 1 researcher(s); nothing to compare across researchers", figures: 1, groups: [], inputTokens: 0, outputTokens: 0 };
    expect(overview(results, [], skipped, new Map())).toContain("The conflict checker did not run: figures from 1 researcher(s)");
  });
});

describe("routed-review finalize guidance", () => {
  it("lists open conflicts for the writer, and nothing when figures agree", () => {
    const { check, figures } = weightConflict();
    const byId = new Map(figures.map((f) => [f.id, f]));
    expect(conflictGuidance(check, byId)).toContain("Researchers disagree on these figures");
    expect(conflictGuidance(check, byId)).toContain('- iPhone 18 Pro Max weight: "249 g" against "8.15 oz" (249 g vs 8.15 oz (231.049 g)).');
    const agree = [fig("r1-b1#1", 249, "g"), fig("r1-b2#1", 249, "g")];
    const agreeing: CheckRecord = { ...check, groups: compareGroups([{ quantity: "weight", figures: ["r1-b1#1", "r1-b2#1"] }], agree) };
    expect(conflictGuidance(agreeing, new Map(agree.map((f) => [f.id, f])))).toBe("");
  });
});
