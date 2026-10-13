import { describe, expect, it } from "vitest";
import type { ResearchBrief, ResearchResult } from "../src/core/contracts.js";
import type { Source } from "../src/core/contracts.js";
import type { ResearchStrategy } from "../src/core/strategy.js";
import { buildResearchGraph, initialState, type DecisionRecord } from "../src/graph/skeleton.js";

const brief = (objective: string) => ({ objective, keyQuestions: ["q"] });

it("relays only completed source records and does not taint a known URL across nodes", async () => {
  const carried: Source[][] = [];
  const real = "https://example.org/real", invented = "https://example.org/invented";
  let written: any;
  const strategy = scripted([["identity"], ["details"]]);
  strategy.finalize = async () => ({ material: [{ label: "Identity", notes: `Finding [Real](${real})` }] });
  const graph = buildResearchGraph({ strategy, strategyModel: {} as never,
    research: async (_q, b, inherited = []) => {
      carried.push(inherited);
      const result = await fakeResearch().fn(_q, b);
      return { ...result, notes: `Finding [Real](${real})`,
        sources: b.round === 1 ? [{ url: real, cited: true, readState: "snippet" as const }] : [],
        unlistedCitations: b.round === 1 ? [invented] : [real] };
    },
    write: async (_q, synthesis) => { written = synthesis; return { report: "done", diagnostics: [] }; },
    limits: { researchersTotal: 3, toolCallsPerResearcher: 8 }, maxRounds: 3, concurrency: 1, runId: "test", today: "2026-10-13" });
  await graph.invoke(initialState("Question"));
  expect(carried[0]).toEqual([]);
  expect(carried[1]).toEqual([{ url: real, cited: true, readState: "snippet", originBriefId: "r1-b1" }]);
  expect(carried.flat().some(s => s.url === invented)).toBe(false);
  expect(written.sourceRegistry[0].originBriefId).toBe("r1-b1");
  expect(written.material[0].notes).toContain(real);
  expect(written.material.some((m: any) => m.notes.includes("(unverified link)"))).toBe(false);
});

function fakeResearch(fail: Set<string> = new Set()) {
  const seen: ResearchBrief[] = [];
  const fn = async (_q: string, b: ResearchBrief): Promise<ResearchResult> => {
    seen.push(b);
    const failed = fail.has(b.objective);
    return {
      brief: b,
      status: failed ? "failed" : "ok",
      ...(failed ? { failure: { kind: "provider" as const, message: "boom" } } : {}),
      notes: failed ? "" : `notes for ${b.objective}`,
      sources: [],
      queries: [],
      usage: { inputTokens: 1, outputTokens: 1, searches: 1, pageReads: 0 },
      model: "fake",
      durationMs: 1,
      unlistedCitations: [],
      diagnostics: [],
    };
  };
  return { fn, seen };
}

/** Strategy scripted by a list of brief batches, one per round. */
function scripted(batches: string[][], onObserve?: (results: ResearchResult[]) => void): ResearchStrategy<{ round: number; seen: string[] }> {
  return {
    name: "scripted",
    async init() {
      return { state: { round: 0, seen: [] }, decision: { briefs: (batches[0] ?? []).map(brief), stop: false, rationale: "start" } };
    },
    async observe(state, results) {
      onObserve?.(results);
      const round = state.round + 1;
      const next = batches[round] ?? [];
      return {
        state: { round, seen: [...state.seen, ...results.map((r) => `${r.brief.id}:${r.status}`)] },
        decision: { briefs: next.map(brief), stop: next.length === 0, rationale: `after round ${round}` },
      };
    },
    async finalize(state) {
      return { material: state.seen.map((s) => ({ label: s, notes: s })) };
    },
  };
}

async function run(strategy: ResearchStrategy<any>, opts: { total?: number; maxRounds?: number; fail?: Set<string> } = {}) {
  const research = fakeResearch(opts.fail);
  const decisions: DecisionRecord[] = [];
  const graph = buildResearchGraph({
    strategy,
    strategyModel: {} as never,
    research: research.fn,
    write: async (q, s) => ({ report: `report: ${q} (${s.material.length})`, diagnostics: [] }),
    limits: { researchersTotal: opts.total ?? 10, toolCallsPerResearcher: 8 },
    maxRounds: opts.maxRounds ?? 8,
    concurrency: 2,
    runId: "test",
    today: "2026-10-09",
    hooks: { onDecision: (d) => void decisions.push(d) },
  });
  const final = await graph.invoke(initialState("Q?"), { recursionLimit: 100 });
  return { final, decisions, seen: research.seen };
}

describe("skeleton", () => {
  it("runs rounds until the strategy stops and passes every result to observe", async () => {
    const observed: number[] = [];
    const { final, decisions } = await run(scripted([["a", "b"], ["c"]], (r) => observed.push(r.length)));
    expect(observed).toEqual([2, 1]);
    expect(final.results.map((r: ResearchResult) => r.brief.id).sort()).toEqual(["r1-b1", "r1-b2", "r2-b1"]);
    expect(final.stopReason).toBe("strategy-stop");
    expect(final.researchersUsed).toBe(3);
    expect(decisions.map((d) => d.phase)).toEqual(["init", "observe", "observe"]);
    expect(final.report).toBe("report: Q? (3)");
  });

  it("passes failures to the strategy as results", async () => {
    const statuses: string[] = [];
    await run(scripted([["a", "bad"]], (r) => statuses.push(...r.map((x) => x.status))), { fail: new Set(["bad"]) });
    expect(statuses.sort()).toEqual(["failed", "ok"]);
  });

  it("enforces the researcher budget across rounds", async () => {
    const { final, decisions } = await run(scripted([["a", "b", "c"], ["d", "e", "f"], ["g"]]), { total: 4 });
    expect(final.researchersUsed).toBe(4);
    expect(decisions[1]!.accepted).toHaveLength(1);
    expect(decisions[1]!.dropped).toHaveLength(2);
    expect(decisions[2]!.dropped).toHaveLength(1);
    expect(final.stopReason).toBe("budget-exhausted");
  });

  it("stops at the round safety cap", async () => {
    const forever: ResearchStrategy<number> = {
      name: "forever",
      init: async () => ({ state: 0, decision: { briefs: [brief("x")], stop: false, rationale: "" } }),
      observe: async (s) => ({ state: s + 1, decision: { briefs: [brief("x")], stop: false, rationale: "" } }),
      finalize: async () => ({ material: [] }),
    };
    const { final } = await run(forever, { maxRounds: 3, total: 100 });
    expect(final.researchersUsed).toBe(3);
    expect(final.stopReason).toBe("max-rounds");
  });

  it("rejects strategy state that does not round-trip through JSON", async () => {
    const bad: ResearchStrategy<any> = {
      name: "bad",
      init: async () => ({ state: { when: new Date() }, decision: { briefs: [], stop: true, rationale: "" } }),
      observe: async (s) => ({ state: s, decision: { briefs: [], stop: true, rationale: "" } }),
      finalize: async () => ({ material: [] }),
    };
    await expect(run(bad)).rejects.toThrow(/round-trip through JSON/);
  });
});
