import { describe, expect, it } from "vitest";
import { checkAnalysis, cutAt, minimalAnalysis, pageKey, salvage } from "./checks.js";
import { EXAMPLES } from "./examples.js";
import { scanRequest } from "./scan.js";
import { AnalysisFullSchema, LIMITS, type Analysis, type ScanResult } from "./schema.js";

const E1 = EXAMPLES[0]!;
const scanE1 = scanRequest(E1.request, E1.runDate);
const clone = (): Analysis => structuredClone(E1.analysis);
const codes = (a: unknown, ctx: Partial<Parameters<typeof checkAnalysis>[1]> = {}) =>
  checkAnalysis(a, { request: E1.request, scan: scanE1, ...ctx }).errors.map((e) => e.code);

describe("request analysis checks", () => {
  it("accept every converted worked example", () => {
    for (const e of EXAMPLES) {
      const r = checkAnalysis(e.analysis, { request: e.request, scan: scanRequest(e.request, e.runDate) });
      expect(r.errors, e.id).toEqual([]);
    }
  });

  it("reject questions that point back to another question instead of restating it (Lab 3)", () => {
    const back = clone();
    back.questions[4]!.text = "What do the forecasters identified in Q3 expect for new-car prices in Canada in 2026?";
    expect(codes(back)).toContain("question_not_self_contained");
    const earlier = clone();
    earlier.questions[4]!.done_when = "The 2026 range from each source found by the previous question.";
    expect(codes(earlier)).toContain("question_not_self_contained");
  });

  it("accept country names and possessive acronym expansions as known names (Lab 3)", () => {
    const named = clone();
    named.questions[2]!.text += " Include forecasts that compare Canada with Russia, the Philippines and the European Union's members.";
    const request = `${E1.request} Compare with the EU.`;
    const out = checkAnalysis(named, { request, scan: scanRequest(request, E1.runDate) });
    expect(out.errors.filter((e) => e.code === "names_not_in_request")).toEqual([]);
  });

  it("reject quotes, references and routes that break the contract", () => {
    const quote = clone();
    quote.rom.objects[3]!.text = "tarifs";
    expect(codes(quote)).toContain("quote_not_in_request");

    const ref = clone();
    ref.questions[0]!.object_ids = ["O99"];
    expect(codes(ref)).toContain("unknown_reference");

    const product = clone();
    product.questions[0]!.object_ids.push("O1");
    expect(codes(product)).toContain("product_searched");

    const hints = clone();
    hints.questions[6]!.source_hints = ["economic studies"];
    expect(codes(hints)).toContain("source_hints");

    const scope = clone();
    scope.status = "out_of_scope";
    scope.status_reason = "x";
    expect(codes(scope)).toContain("status");
  });

  it("reject an object covered only by a verification question (review of 2026-10-20)", () => {
    // E1's "raise" is checked by Q4 (T7) and defined by Q6 (T4); without Q6 nothing defines it.
    const onlyChecked = clone();
    onlyChecked.questions[5]!.object_ids = ["O6"];
    expect(codes(onlyChecked)).toContain("object_only_verified");
    // A defining question that also verifies the claim is enough, as E1's Q1 does for "tariffs".
    expect(codes(clone())).not.toContain("object_only_verified");
  });

  it("reject lengths and broken structure", () => {
    const long = clone();
    long.questions[0]!.text = "x".repeat(401);
    expect(codes(long)).toContain("limit");
    const broken = { ...clone(), questions: undefined };
    const r = checkAnalysis(broken, { request: E1.request, scan: scanE1 });
    expect(r.analysis).toBeNull();
    expect(r.errors[0]!.code).toBe("schema");
  });

  it("reject names the request does not contain unless a reported search result grounds them", () => {
    const named = clone();
    named.questions[2]!.text += " Include Scotiabank.";
    expect(codes(named)).toContain("names_not_in_request");

    // A plural possessive of a request word is not a new name (live run, 2026-10-19).
    const gpus = "Compare Nvidia and AMD flagship GPUs.";
    const possessive = checkAnalysis({ ...clone(), restated_request: "Compare the flagship GPUs' cost." }, { request: gpus, scan: { ...scanE1, spans: [] } });
    expect(possessive.errors.find((e) => e.code === "names_not_in_request")).toBeUndefined();

    const grounded = structuredClone(named);
    grounded.grounding = [
      { object_id: "O9", query: "economists expect new-car prices Canada 2026", url: "https://www.example.org/outlook?utm_source=openai", finding: "A bank outlook forecasts prices.", names: ["Scotiabank"] },
    ];
    expect(codes(grounded)).toContain("grounding_without_search");
    expect(codes(grounded, { reported: [{ url: "https://example.org/other" }] })).toContain("grounding_url_not_reported");
    const ok = checkAnalysis(grounded, { request: E1.request, scan: scanE1, reported: [{ url: "https://example.org/outlook", title: "Scotiabank auto outlook" }] });
    expect(ok.errors).toEqual([]);
    expect(ok.warnings).toEqual([]);
  });

  it("reject an ok analysis that drops a span of the scan", () => {
    const scan: ScanResult = { ...scanE1, spans: [...scanE1.spans, { id: "S99", kind: "restrictor", text: "only", start: 0, end: 4, window: null }] };
    const r = checkAnalysis(clone(), { request: E1.request, scan });
    expect(r.errors.map((e) => [e.code, e.path])).toEqual([["span_not_covered", "scan.S99"]]);
  });

  it("salvage drops faulty questions and their dependents", () => {
    const a = clone();
    const kept = salvage(a, [{ code: "x", path: "questions[0].text", message: "" }]);
    expect(kept?.questions.map((q) => q.id)).toEqual(["Q2", "Q3", "Q5", "Q8"]);
    expect(salvage(a, [0, 1, 2, 4].map((i) => ({ code: "x", path: `questions[${i}]`, message: "" })))).toBeNull();
  });

  it("salvage keeps a question whose only fault is its length, cut at the limit (section 24.4)", () => {
    const a = clone();
    const filler = " It also states the range of values that each source reports and the period that each value covers.";
    a.questions[0]!.done_when = `${a.questions[0]!.done_when}${filler.repeat(5)}`;
    const { errors } = checkAnalysis(a, { request: E1.request, scan: scanE1 });
    expect(errors.map((e) => [e.code, e.path])).toEqual([["limit", "questions[0].done_when"]]);
    const kept = salvage(a, errors)!;
    expect(kept.questions.map((q) => q.id)).toEqual(a.questions.map((q) => q.id));
    const cut = kept.questions[0]!.done_when;
    expect(cut.length).toBeLessThanOrEqual(LIMITS.long);
    expect(a.questions[0]!.done_when.startsWith(cut)).toBe(true);
    expect(cut.endsWith(".")).toBe(true);
    // The cut analysis passes the checks it failed.
    expect(checkAnalysis(kept, { request: E1.request, scan: scanE1 }).errors).toEqual([]);
    // A question with another fault besides its length is dropped as before, with its dependents.
    const both = salvage(a, [...errors, { code: "x", path: "questions[0].text", message: "" }]);
    expect(both?.questions.map((q) => q.id)).toEqual(["Q2", "Q3", "Q5", "Q8"]);
  });

  it("cut a text after its last full sentence, or after its last whole word", () => {
    expect(cutAt("short", 10)).toBe("short");
    expect(cutAt("One sentence here. Another sentence follows it.", 28)).toBe("One sentence here.");
    // A full stop early in the text would lose most of it, so the cut falls after the last whole word.
    expect(cutAt("One. Another sentence follows it here", 30)).toBe("One. Another sentence follows");
    expect(cutAt("a long run of words without any full stop in it", 20)).toBe("a long run of words");
  });

  it("the minimal plan is a valid analysis with the request as its one search question (section 24.4)", () => {
    const a = minimalAnalysis("How can I study medicine in Germany?", "2026-11-18");
    expect(AnalysisFullSchema.safeParse(a).success).toBe(true);
    expect(a.questions.map((q) => [q.id, q.route, q.text])).toEqual([["Q1", "search", "How can I study medicine in Germany?"], ["Q2", "synthesis", "How can I study medicine in Germany?"]]);
    expect(a.assumptions).toEqual([]);
    expect(salvage(a, [])).toEqual(a);
  });

  it("compare URLs by page", () => {
    expect(pageKey("https://www.Example.org/a/?utm_source=openai#x")).toBe("example.org/a");
  });
});
