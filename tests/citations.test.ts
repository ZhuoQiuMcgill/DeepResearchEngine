import { describe, expect, it } from "vitest";
import type { ResearchResult } from "../src/core/contracts.js";
import { citationBinding, unknownCitations } from "../src/core/citations.js";

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
});
