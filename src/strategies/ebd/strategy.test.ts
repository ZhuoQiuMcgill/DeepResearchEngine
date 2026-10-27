/**
 * The whole EBD loop through the real skeleton, without network (design section 15):
 * a fake model answers each role by the submit tool it is bound to, and fake
 * researchers write notes with [Qn] sections. The script plants a disagreement,
 * an off-target finding, a contradicted premise and a new term, so every rule
 * of sections 8–12 runs once.
 */
import { describe, expect, it } from "vitest";
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { buildResearchGraph, initialState, type DecisionRecord } from "../../graph/skeleton.js";
import ebd from "./index.js";
import { EXAMPLES } from "./request/examples.js";
import type { EbdState } from "./state.js";

const E1 = EXAMPLES[0]!;

/** Findings each goal's researcher reports, by attempt: [text, host]. Markers steer the fake checker and analyst. */
const NOTES: Record<string, [string, string][][]> = {
  Q1: [[["The US imposed tariffs on imported vehicles and parts in 2025.", "gov-a.example"], ["Tariffs of 25% applied from April 2025.", "news-b.example"]]],
  Q2: [[["The new-vehicle price index rose 4% in 2025 (RISE).", "stats-c.example"], ["The new-vehicle price index fell 1% in 2025 (FALL).", "blog-d.example"]]],
  Q4: [[["Prices rose because of the exchange rate, not tariffs (CONTRADICTS).", "bank-e.example"], ["A study found no tariff pass-through to Canadian prices (CONTRADICTS).", "uni-f.example"]]],
  Q3: [
    [["The Bank of Canada publishes a price outlook (NEWTERM).", "bank-e.example"], ["Economists in Australia expect tariffs on wine (OFFTARGET).", "au-g.example"]],
    [["Two banks publish forecasts of new-car prices for 2026.", "bank-h.example"], ["An industry group also publishes a 2026 outlook.", "ind-i.example"]],
  ],
  Q5: [[["Forecasts expect prices to rise 2–3% in 2026.", "bank-h.example"], ["One outlook expects flat prices in 2026.", "ind-i.example"]]],
};

function notesFor(brief: ResearchBrief): string {
  const ids = (brief.tag ?? "").split(",");
  return ids
    .map((id, i) => {
      const attempt = brief.round > 1 && NOTES[id]?.[1] ? 1 : 0;
      const findings = NOTES[id]?.[attempt] ?? [[`A finding for ${id}.`, `${id.toLowerCase()}-a.example`], [`Another finding for ${id}.`, `${id.toLowerCase()}-b.example`]];
      return [
        `## ${brief.keyQuestions[i]}`,
        "### Takeaway",
        `Takeaway for ${id}.`,
        "### Cited Findings",
        ...findings.map(([text, host]) => `- ${text} — [Source](https://${host}/${id})`),
        "### Gaps",
        `- Nothing more was found for ${id}.`,
      ].join("\n");
    })
    .join("\n\n");
}

const research = async (_q: string, brief: ResearchBrief): Promise<ResearchResult> => ({
  brief,
  status: "ok",
  notes: notesFor(brief),
  sources: [],
  queries: [],
  usage: { inputTokens: 0, outputTokens: 0, searches: 1, pageReads: 0 },
  model: "fake",
  durationMs: 0,
  unlistedCitations: [],
  diagnostics: [],
});

type Line = { id: string; text: string };

function block(message: string, tag: string): string {
  return new RegExp(`<${tag}>\\n([\\s\\S]*?)\\n</${tag}>`).exec(message)?.[1] ?? "";
}

function lines(text: string): Line[] {
  return text.split("\n").flatMap((l) => {
    const m = /^(r\d+-b\d+-[fg]\d+) (?:\[[^\]]*\] )?(.*)$/.exec(l);
    return m ? [{ id: m[1]!, text: m[2]! }] : [];
  });
}

/** The conflict checker: one disagreement on the price index, one off-target finding. */
function conflicts(message: string) {
  const fresh = lines(block(message, "new_evidence"));
  const out = [];
  const rise = fresh.find((l) => l.text.includes("(RISE)"));
  const fall = fresh.find((l) => l.text.includes("(FALL)"));
  if (rise && fall) {
    // A rise against a fall decides A2 ("prices rose"), so the settle goal checks it.
    out.push({ type: "source_vs_source", about: "Q2", statement: "One source reports a 4% rise and another a 1% fall in the 2025 index.", side_a: [rise.id], side_b: [fall.id], settle_by: "The official statistics release for 2025.", condition: "", claim: "A2" });
  }
  const off = fresh.find((l) => l.text.includes("(OFFTARGET)"));
  // No claim field: a missing claim counts as empty.
  if (off) out.push({ type: "off_target", about: "O9", statement: "A finding is about tariffs on Australian wine.", side_a: [off.id], side_b: ["O9"], settle_by: "", condition: "" });
  return { conflicts: out };
}

/** The round analyst: judges each served goal from the evidence the message lists under it. */
function round(message: string) {
  const goals = block(message, "served_goals").split(/\n(?=### )/);
  const judgments = goals.map((g) => {
    const id = /^### (Q\d+)/.exec(g)![1]!;
    const claims = [...g.matchAll(/^- (A\d+): /gm)].map((m) => m[1]!);
    const findings = lines(g).filter((l) => l.id.includes("-f"));
    const latest = findings.filter((l) => l.id.startsWith(`r${Math.max(...findings.map((f) => Number(/^r(\d+)/.exec(f.id)![1])))}-`));
    if (id === "Q2" && g.includes("attempt 1")) {
      return { goal_id: id, parts: [{ part: "the index change", met: false, evidence: [] }], outcome: "conflicting", verdicts: claims.map((c) => ({ claim_id: c, verdict: "unsettled" })), missing: ["which index value is right"] };
    }
    if (id === "Q3" && g.includes("attempt 1")) {
      return {
        goal_id: id,
        parts: [{ part: "who publishes forecasts", met: true, evidence: [findings[0]!.id] }, { part: "the full list", met: false, evidence: [] }],
        outcome: "partial",
        verdicts: [],
        missing: ["the full list of forecasters"],
      };
    }
    const contradicted = latest.some((l) => l.text.includes("CONTRADICTS"));
    return {
      goal_id: id,
      parts: [{ part: "the answer", met: true, evidence: latest.map((l) => l.id) }],
      outcome: "answered",
      verdicts: claims.map((c) => ({ claim_id: c, verdict: contradicted ? "contradicted" : "supported" })),
      missing: [],
    };
  });
  const newterm = lines(block(message, "served_goals")).find((l) => l.text.includes("(NEWTERM)"));
  const proposals = newterm
    ? [{
        text: "What does the Bank of Canada's price outlook say about new-car prices in Canada for 2026?",
        template: "T1", need: "necessary", object_id: "O9", new_object: "Bank of Canada price outlook", new_object_quote: "Bank of Canada publishes a price outlook",
        prompted_by: [newterm.id], leads_to: ["Q5"], done_when: "The outlook's 2026 expectation for new-car prices, with its date.", source_hints: ["central bank publications"],
      }]
    : [];
  return { judgments, proposals };
}

function fakeModel() {
  const calls: string[] = [];
  const model = {
    bindTools: (tools: { function: { name: string } }[]) => ({
      invoke: async (messages: BaseMessage[]) => {
        const name = tools[0]!.function.name;
        const message = String(messages.at(-1)!.content);
        calls.push(name);
        const args = name === "submit_analysis" ? E1.analysis : name === "submit_conflicts" ? conflicts(message) : round(message);
        return new AIMessage({ content: "", tool_calls: [{ id: `c${calls.length}`, name, args: args as Record<string, unknown>, type: "tool_call" }] });
      },
    }),
  } as unknown as BaseChatModel;
  return { model, calls };
}

async function run(options: Record<string, unknown> = {}) {
  const { model, calls } = fakeModel();
  const decisions: DecisionRecord[] = [];
  let synthesis: { material: { label: string; notes: string }[]; outline?: string[]; guidance?: string } | undefined;
  const graph = buildResearchGraph({
    strategy: ebd.create(options as never),
    strategyModel: model,
    research,
    write: async (_q, s) => ((synthesis = s), { report: "report", diagnostics: [] }),
    limits: { researchersTotal: 10, toolCallsPerResearcher: 12 },
    maxRounds: 8,
    concurrency: 4,
    runId: "t",
    today: E1.runDate,
    hooks: { onDecision: (d) => void decisions.push(d) },
  });
  const final = await graph.invoke(initialState(E1.request), { recursionLimit: 100 });
  return { final, decisions, synthesis: synthesis!, calls, state: final.strategyState as EbdState };
}

describe("ebd strategy through the skeleton", () => {
  it("grows the goal tree, settles the conflict, makes moot goals and stops complete", async () => {
    const { final, decisions, synthesis, calls, state } = await run();
    expect(final.stopReason).toBe("strategy-stop");
    expect(state.stop).toMatchObject({ kind: "complete" });
    expect(final.synthesisDiagnostics).toEqual([]);
    expect(calls[0]).toBe("submit_analysis");

    // Round 1: premise checks first (L-7), then the definition goal.
    expect(decisions[0]!.accepted.map((b) => b.tag)).toEqual(["Q2", "Q1", "Q4", "Q3"]);
    const goal = (id: string) => state.goals.find((g) => g.id === id)!;

    // The disagreement on Q2 created a level-1 settle goal; settling it answered Q2.
    const c1 = state.conflicts.find((c) => c.type === "source_vs_source")!;
    expect(c1).toMatchObject({ status: "settled", about: "Q2" });
    expect(goal(c1.settleGoal!)).toMatchObject({ kind: "settle", level: 1, status: "answered", verifies: ["A2"] });
    expect(goal("Q2")).toMatchObject({ status: "answered", verdicts: { A2: "supported" } });

    // The contradicted premise (A3, checked by Q4) made Q6, which relies on it, moot.
    expect(goal("Q4")).toMatchObject({ status: "answered", verdicts: { A3: "contradicted" } });
    expect(goal("Q6").status).toBe("moot");

    // The new term grew one goal at depth 1, served before Q5, which waited for Q2 and Q3.
    const grown = state.goals.find((g) => g.origin.type === "finding")!;
    expect(grown).toMatchObject({ depth: 1, status: "answered", leadsTo: ["Q5"] });
    expect(state.objectsFound[0]).toMatchObject({ text: "Bank of Canada price outlook", parent: "O9" });
    expect(goal("Q5")).toMatchObject({ status: "answered", servedRounds: [3] });
    expect(state.tree).toMatchObject({ byOrigin: { request: 6, conflict: 1, finding: 1 }, maxDepth: 1 });

    // Writer input: whole notes lines, off-target lines removed, analysis in the guidance.
    const all = synthesis.material.map((m) => m.notes).join("\n");
    expect(all).not.toContain("OFFTARGET");
    expect(all).toContain("(RISE)");
    expect(synthesis.material[0]!.notes.startsWith("# [")).toBe(true);
    expect(synthesis.outline).toEqual(E1.analysis.questions.filter((q) => q.route === "synthesis").map((q) => q.text));
    expect(synthesis.guidance).toContain("The evidence contradicts this; say so plainly early in the report.");
    expect(synthesis.guidance).toContain("different referent");
    expect(synthesis.guidance).toContain("not pursued because a premise they rely on was contradicted");

    // Every step recorded its own model calls for the viewer.
    expect(decisions.map((d) => (d.strategyState as EbdState).step.calls.map((c) => c.role))).toEqual([
      ["request_analyst"],
      ["conflict_checker", "round_analyst"],
      ["conflict_checker", "round_analyst"],
      ["conflict_checker", "round_analyst"],
    ]);
  });

  it("makes no conflict records with conflicts: false (H1 ablation)", async () => {
    const { state, calls } = await run({ conflicts: false });
    expect(calls).not.toContain("submit_conflicts");
    expect(state.conflicts).toEqual([]);
    // Without a conflict record the analyst's "conflicting" judgment falls back to partial and Q2 is re-served.
    expect(state.goals.find((g) => g.id === "Q2")!.servedRounds).toEqual([1, 2]);
  });

  it("serves only the analysis's goals with newGoals: false", async () => {
    const { state } = await run({ newGoals: false });
    expect(state.goals.every((g) => g.origin.type !== "finding")).toBe(true);
    expect(state.objectsFound).toEqual([]);
  });

  it("records the unmet demand when the budget runs out", async () => {
    const { model } = fakeModel();
    const graph = buildResearchGraph({
      strategy: ebd.create({}),
      strategyModel: model,
      research,
      write: async () => ({ report: "r", diagnostics: [] }),
      limits: { researchersTotal: 4, toolCallsPerResearcher: 12 },
      maxRounds: 8,
      concurrency: 4,
      runId: "t",
      today: E1.runDate,
    });
    const final = await graph.invoke(initialState(E1.request), { recursionLimit: 100 });
    expect(final.stopReason).toBe("budget-exhausted");
    expect((final.strategyState as EbdState).stop?.kind).toBe("budget");
    expect(final.decisions.at(-1)!.dropped.length).toBeGreaterThan(0);
  });
});
