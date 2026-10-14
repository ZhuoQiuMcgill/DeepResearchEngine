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
  it("recognizes a publication year in the matching bibliography label", () => {
    const notes = '- Three activities — [ACM (Sun et al., 2011)](https://example.org/paper)';
    expect(citationBinding('The 2011 paper describes three activities [ACM](https://example.org/paper).', [result(notes)]).unbound).toBe(0);
    expect(citationBinding('The 2012 paper describes three activities [ACM](https://example.org/paper).', [result(notes)]).unbound).toBe(1);
  });
  it("does not use bibliographic years, identifier digits or arbitrary label numbers as factual quantities", () => {
    const notes = '- Three activities — [ACM 2011, page 515](https://example.org/paper/9999)';
    expect(citationBinding('The study enrolled 2011 participants [ACM](https://example.org/paper/9999).', [result(notes)]).unbound).toBe(1);
    expect(citationBinding('The cost is 515 [ACM](https://example.org/paper/9999).', [result(notes)]).unbound).toBe(1);
    expect(citationBinding('The cost is 9999 [ACM](https://example.org/paper/9999).', [result(notes)]).unbound).toBe(1);
  });
  it("keeps unsupported temporal inferences flagged and detects dropped citations", () => {
    const notes = '- A precursor dates to 2004 — [Paper](https://example.org/paper)\n- Development began in the mid-2000s.';
    expect(citationBinding('Development began in the mid-2000s [Paper](https://example.org/paper).', [result(notes)]).unbound).toBe(1);
    expect(citationBinding('The precursor dates to 2004.', [result(notes)]).unbound).toBe(1);
  });
  it("keeps a multi-sentence quotation with its trailing citation without borrowing across unrelated sentences", () => {
    const notes = '- A 2011 paper reports 500. A result — [Paper](https://example.org/paper)';
    expect(citationBinding('The 2011 paper states "The count is 500. This is the result." [Paper](https://example.org/paper).', [result(notes)]).unbound).toBe(0);
    expect(citationBinding('The count is 900. This other result cites [Paper](https://example.org/paper).', [result(notes)]).unbound).toBe(1);
  });
  it("preserves an abbreviated journal reference with its trailing citation", () => {
    const notes = '- The 2004 paper appears in J. Design 8(4), pages 45–63 [Paper](https://example.org/paper).';
    expect(citationBinding('The structure comes from the 2004 paper (J. Design 8(4), 45–63) [Paper](https://example.org/paper).', [result(notes)])).toMatchObject({ checked: 1, unbound: 0 });
    expect(citationBinding('The 2004 paper appears in J. Design [Paper](https://example.org/paper).', [result(notes)])).toMatchObject({ checked: 1, unbound: 0 });
  });

  it("matches report URLs to sources across query parameters", () => {
    expect(unknownCitations("See https://pubmed.ncbi.nlm.nih.gov/22038497/ and https://x.org/y", [result("", ["https://pubmed.ncbi.nlm.nih.gov/22038497/?dopt=Abstract"])])).toEqual(["https://x.org/y"]);
  });
  it("does not grant provenance to a URL merely because it occurs in notes", () => {
    const url = "https://example.org/invented";
    expect(unknownCitations(`Claim [X](${url})`, [result(`Claim [X](${url})`)])).toEqual([url]);
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
