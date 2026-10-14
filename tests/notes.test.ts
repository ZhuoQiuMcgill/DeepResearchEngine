import { describe, expect, it } from "vitest";
import { parseNotes, summarizeNotes } from "../src/core/notes.js";

const NOTES = `## What is EBD?

### Takeaway
EBD is a design methodology.
It models the environment.

### Cited Findings
- EBD was proposed by Yong Zeng — [Source](https://example.org/a)
- It has three activities — [Source](https://example.org/b)
  continued line

### Inferences
- It suits conceptual design.

### Gaps
- No adoption statistics found.

## Who uses it?
### **Takeaway:**
Mostly academia.
### Gaps
- Industry use unclear.`;

describe("parseNotes", () => {
  it("parses sections, findings and gaps", () => {
    const p = parseNotes(NOTES);
    expect(p.parsed).toBe(true);
    expect(p.sections).toHaveLength(2);
    expect(p.sections[0]!.takeaway).toBe("EBD is a design methodology. It models the environment.");
    expect(p.sections[0]!.findings).toHaveLength(2);
    expect(p.sections[0]!.findings[1]).toContain("continued line");
    expect(p.sections[1]!.takeaway).toBe("Mostly academia.");
    expect(p.sections[1]!.gaps).toEqual(["Industry use unclear."]);
  });

  it("falls back to raw text when the format is not followed", () => {
    expect(parseNotes("Just a paragraph.").parsed).toBe(false);
    expect(summarizeNotes("Just a paragraph.")).toBe("Just a paragraph.");
  });
});
