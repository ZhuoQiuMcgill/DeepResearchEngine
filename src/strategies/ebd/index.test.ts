import { describe, expect, it } from "vitest";
import { directiveLines, firstRoundBriefs, writerGuidance } from "./index.js";
import { EXAMPLES } from "./request/examples.js";
import type { Analysis } from "./request/schema.js";

const withDirectives = (): Analysis => ({
  ...structuredClone(EXAMPLES[0]!.analysis),
  client_directives: [
    { kind: "source_preference", text: "Use only official statistics.", evidence: ["official statistics only"] },
    { kind: "report_format", text: "A one-page briefing.", evidence: ["one-page"] },
    { kind: "scope_limit", text: "Leave out used cars.", evidence: [] },
  ],
});

describe("ebd v0: what each reader receives", () => {
  it("gives every brief the frame and the client's evidence directives, in the client's words", () => {
    const briefs = firstRoundBriefs(withDirectives(), { init: "fixed", maxPerRound: 4, questionsPerBrief: 3 }, 10);
    expect(briefs.map((b) => b.tag)).toEqual(["Q1", "Q2", "Q3"]);
    for (const b of briefs) {
      expect(b.constraints).toContain('Client source preference: Use only official statistics. (client\'s words: "official statistics only")');
      expect(b.constraints).toContain("Client scope limit: Leave out used cars.");
      expect(b.constraints!.some((c) => c.startsWith("Client report format"))).toBe(false);
      expect(b.constraints!.some((c) => c.startsWith("Time frame (explicit)"))).toBe(true);
    }
  });

  it("gives the writer the report format, scope limits and the assumptions to address", () => {
    const guidance = writerGuidance(withDirectives());
    expect(guidance).toContain('Client report format: A one-page briefing. (client\'s words: "one-page")');
    expect(guidance).toContain("Client scope limit: Leave out used cars.");
    expect(guidance).not.toContain("source preference");
    expect(guidance).toContain("The question presupposes");
    expect(directiveLines(EXAMPLES[1]!.analysis, "writer")).toEqual([]);
  });

  it("tells the writer when nothing was researched", () => {
    expect(writerGuidance(EXAMPLES[2]!.analysis)).toMatch(/^Nothing was researched: /);
  });
});
