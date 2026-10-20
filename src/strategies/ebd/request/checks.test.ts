import { describe, expect, it } from "vitest";
import { checkAnalysis, pageKey, salvage } from "./checks.js";
import { EXAMPLES } from "./examples.js";
import { scanRequest } from "./scan.js";
import type { Analysis, ScanResult } from "./schema.js";

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

  it("compare URLs by page", () => {
    expect(pageKey("https://www.Example.org/a/?utm_source=openai#x")).toBe("example.org/a");
  });
});
