import { describe, expect, it } from "vitest";
import template from "../src/strategies/_template/index.js";
import type { ResearchBrief, ResearchResult } from "../src/core/index.js";
import { buildResearchGraph, initialState } from "../src/graph/skeleton.js";
import { listStrategies } from "../src/platform/strategies.js";

describe("strategy template", () => {
  it("is not offered as a strategy", () => {
    expect(listStrategies()).not.toContain("_template");
  });

  it("runs through the skeleton and passes researcher notes to the writer", async () => {
    const research = async (_q: string, brief: ResearchBrief): Promise<ResearchResult> => ({
      brief, status: "ok", notes: "- A fact — [P](https://p.org)", sources: [{ url: "https://p.org", cited: true }], queries: [],
      usage: { inputTokens: 0, outputTokens: 0, searches: 1, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [],
    });
    let material = "";
    const graph = buildResearchGraph({
      strategy: template.create(), strategyModel: {} as never, research,
      write: async (_q, s) => { material = s.material.map((m) => m.notes).join("\n"); return { report: "r", diagnostics: [] }; },
      limits: { researchersTotal: 3, toolCallsPerResearcher: 8 }, maxRounds: 8, concurrency: 1, runId: "t", today: "2026-10-09",
    });
    const final = await graph.invoke(initialState("Q?"), { recursionLimit: 50 });
    expect(final.researchersUsed).toBe(1);
    expect(final.stopReason).toBe("strategy-stop");
    expect(final.synthesisDiagnostics).toEqual([]);
    expect(material).toBe("- A fact — [P](https://p.org)");
  });
});
