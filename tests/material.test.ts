import { describe, expect, it } from "vitest";
import { materialProvenance } from "../src/core/material.js";
import type { ResearchResult } from "../src/core/contracts.js";

const result = (notes: string) => ({ notes }) as ResearchResult;

describe("material provenance", () => {
  const notes = "## Q\n### Cited Findings\n- Fact A — [P](https://a.org)\n- Fact B — [P](https://b.org)";
  it("accepts selected, reordered and excerpted lines plus added headings", () => {
    const p = materialProvenance({ material: [{ label: "x", notes: "# Group 1\n- Fact B — [P](https://b.org) (unverified link)\n\n- Fact A — [P](https://a.org)" }] }, [result(notes)]);
    expect(p).toMatchObject({ lines: 2, unmatched: 0 });
  });
  it("flags rewritten or added evidence", () => {
    const p = materialProvenance({ material: [{ label: "x", notes: "- Fact A, rephrased — [P](https://a.org)\nConflict: A contradicts B." }] }, [result(notes)]);
    expect(p.unmatched).toBe(2);
  });
});
