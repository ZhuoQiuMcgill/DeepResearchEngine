import { describe, expect, it } from "vitest";
import type { ResearchResult } from "../src/core/contracts.js";
import { citationBinding, markUnverifiedLinks, repairTruncatedUrls, unknownCitations } from "../src/core/citations.js";
import { pageKey } from "../src/core/urls.js";

const result = (notes: string, sources: string[] = []): ResearchResult => ({
  brief: { id: "r1-b1", round: 1, objective: "o", keyQuestions: ["q"], constraints: [], sourceHints: [] },
  status: "ok",
  notes,
  sources: sources.map((url) => ({ url, cited: true })),
  queries: [],
  usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 },
  model: "m",
  durationMs: 0,
  unlistedCitations: [],
  diagnostics: [],
});

const NOTES = `### Cited Findings
- Vision Pro costs $3,499 at launch — [Source](https://apple.com/vp)
- Quest 3 weighs 515 g — [Source](https://meta.com/q3)`;

describe("citation diagnostics", () => {
  it("accepts numbers cited with the URL the notes give them", () => {
    const b = citationBinding("Vision Pro launched at **$3,499** ([Source](https://apple.com/vp)).", [result(NOTES)]);
    expect(b).toMatchObject({ checked: 1, unbound: 0 });
  });

  it("flags numbers cited with a different URL", () => {
    const b = citationBinding("Quest 3 weighs 515 g ([Source](https://apple.com/vp)).", [result(NOTES)]);
    expect(b.unbound).toBe(1);
    expect(b.examples[0]!.missing).toEqual(["515"]);
  });

  it("matches report URLs to sources across query parameters", () => {
    expect(unknownCitations("See https://pubmed.ncbi.nlm.nih.gov/22038497/ and https://x.org/y", [result("", ["https://pubmed.ncbi.nlm.nih.gov/22038497/?dopt=Abstract"])])).toEqual(["https://x.org/y"]);
  });

  it("marks links to pages the tools never reported", () => {
    const out = markUnverifiedLinks("A — [Meta](https://meta.com/q3?x=1). B — [Apple](https://apple.com/vp)", new Set([pageKey("https://meta.com/q3")]));
    expect(out.marked).toBe(1);
    expect(out.text).toBe("A — [Meta](https://meta.com/q3?x=1) (unverified link). B — [Apple](https://apple.com/vp)");
  });

  it("repairs a URL the writer cut short when the completion is unique", () => {
    const notes = "- x — [J](https://www.jstage.jst.go.jp/article/jcbn/75/3/_article)\n- y — [C](https://spectrum.library.concordia.ca/id/eprint/975833/1/NR37760.pdf)";
    const report = "A ([JCBN](https://www.jstage.jst.go.jp'). B ([C](https://spectrum.library.concordia.ca/id/eprint/975833/)). C ([X](https://nowhere.org/a)).";
    const out = repairTruncatedUrls(report, [result(notes)]);
    expect(out.repairs).toHaveLength(2);
    expect(out.report).toContain("(https://www.jstage.jst.go.jp/article/jcbn/75/3/_article)");
    expect(out.report).toContain("(https://spectrum.library.concordia.ca/id/eprint/975833/1/NR37760.pdf)");
    expect(out.report).toContain("https://nowhere.org/a");
  });

  it("does not touch full URLs that share the truncated prefix", () => {
    const full = "https://www.jstage.jst.go.jp/article/jcbn/75/3/_article";
    const out = repairTruncatedUrls(`A ([J](${full})). B ([J](https://www.jstage.jst.go.jp')).`, [result(`- x — [J](${full})`)]);
    expect(out.report).toBe(`A ([J](${full})). B ([J](${full})).`);
  });
});
