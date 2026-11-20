/**
 * The whole EBD loop through the real skeleton, without network (design section 15): a fake model
 * answers each role by the submit tool it is bound to, and fake researchers write notes with [Qn]
 * sections. The script plants a disagreement that decides the claim of the question, a finding about
 * another thing of the same name and a new term, so the rules of sections 8 to 12 run once; and the
 * two ablation switches of the platform's experiments are tried.
 */
import { describe, expect, it } from "vitest";
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { buildResearchGraph, initialState, type DecisionRecord } from "../../graph/skeleton.js";
import { PLAN_TOOL, type PlanReply } from "./environment.js";
import ebd from "./index.js";
import type { EbdState } from "./state.js";

const QUESTION = "Why did the town of Ashby close its public library in 2019?";
const TODAY = "2026-11-19";
const q = (text: string) => ({ text, kind: "social" as const });
/** Goals: Q1 the check of the claim, Q2 the client's question (written, not searched), Q3 and Q4 the two main parts. */
const PLAN: PlanReply = {
  status: "ok",
  status_reason: null,
  restated_request: "Explain why the town of Ashby closed its public library in 2019.",
  subject: "the closure of Ashby's public library",
  purpose: { value: "To understand the closure.", basis: "default" },
  time_frame: { value: "Latest available evidence as of 2026-11-19.", basis: "default" },
  place: { value: "Ashby.", basis: "explicit" },
  directives: [],
  not_stated: [],
  terms: [],
  claims: [{ claim: "The town of Ashby closed its public library in 2019.", verdict: "check", reason: "A particular event with a date." }],
  parts: [
    { name: "The closure", need: "necessary", objective: "Establish whether, when and by whose decision the town of Ashby closed its public library.", questions: [q("Did the town of Ashby close its public library, and on what date?"), q("Which body decided to close the public library of Ashby?"), q("What happened to the building of Ashby's public library after the closure?"), q("What did the closure of Ashby's public library save the town each year?")], source_hints: ["council minutes"] },
    { name: "Reasons", need: "necessary", objective: "Establish the reasons given for closing the public library of Ashby and how far the evidence supports each.", questions: [q("What did the budget of the town of Ashby show for its public library before the closure?"), q("How did use of Ashby's public library change before the closure?"), q("Where do residents and the council of Ashby disagree about the reasons for the closure?"), q("Which alternatives to closing the public library did the council of Ashby consider?")], source_hints: [] },
  ],
};

/** Two findings from two hosts for one key question. Markers steer the fake checker and analyst. */
function findingsFor(key: string, i: number, brief: ResearchBrief): [string, string][] {
  const first = brief.round === 1;
  // The check of the claim: the sources disagree on the year in round 1.
  if (key.startsWith("[Q1]") && first) return [["The council closed the public library of Ashby in June 2019 (Y2019).", "council.example"], ["The public library of Ashby closed its doors in 2018 (Y2018).", "blog.example"]];
  // The goal that settles the disagreement, and a second try of the check when the conflict checker is off.
  if (brief.round > 1 && (key.includes("Which account is correct") || key.startsWith("[Q1]"))) return [["The council minutes record the closure on 30 June 2019.", "council.example"], ["The county archive lists 2019 as the year of the closure.", "archive.example"]];
  if (key.includes("What did the budget of the town of Ashby show") && first) return [["Since the closure the county bookmobile now serves Ashby twice a month (NEWTERM).", "county.example"], ["The public library of Ashby in Massachusetts was renovated in 2019 (OFFTARGET).", "mass.example"]];
  return [[`A finding for key question ${i + 1} of ${brief.tag}.`, `a${i}.example`], [`A second finding for key question ${i + 1} of ${brief.tag}.`, `b${i}.example`]];
}

const research = async (_q: string, brief: ResearchBrief): Promise<ResearchResult> => ({
  brief,
  status: "ok",
  notes: brief.keyQuestions
    .map((key, i) => [`## ${key}`, "### Takeaway", `Takeaway ${i + 1}.`, "### Cited Findings", ...findingsFor(key, i, brief).map(([text, host]) => `- ${text} — [Source](https://${host}/${brief.id})`), "### Gaps", "- Nothing more was found."].join("\n"))
    .join("\n\n"),
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

/** The conflict checker: the two years, which decide the claim A1, and one finding about another Ashby. */
function conflicts(message: string) {
  const fresh = lines(block(message, "new_evidence"));
  const out = [];
  const y2019 = fresh.find((l) => l.text.includes("(Y2019)"));
  const y2018 = fresh.find((l) => l.text.includes("(Y2018)"));
  if (y2019 && y2018) out.push({ type: "source_vs_source", about: "Q1", statement: "One source dates the closure to 2019 and another to 2018.", side_a: [y2019.id], side_b: [y2018.id], settle_by: "The council minutes.", condition: "", claim: "A1", critical: true });
  const off = fresh.find((l) => l.text.includes("(OFFTARGET)"));
  // No claim field: a missing claim counts as empty.
  if (off) out.push({ type: "off_target", about: "O1", statement: "A finding is about the public library of Ashby in Massachusetts.", side_a: [off.id], side_b: ["O1"], settle_by: "", condition: "", critical: false });
  return { conflicts: out };
}

/** The round analyst: judges each served goal from the evidence listed under it, and raises a goal for the new term. */
function round(message: string) {
  const judgments = block(message, "served_goals")
    .split(/\n(?=### )/)
    .map((g) => {
      const id = /^### (Q\d+)/.exec(g)![1]!;
      const claims = [...g.matchAll(/^- (A\d+): /gm)].map((m) => m[1]!);
      const all = lines(g).filter((l) => l.id.includes("-f")).map((l) => l.id);
      const listed = /^Judge only: (.*)$/m.exec(g)?.[1];
      // A main part: every key question answered from the part's first finding.
      if (listed !== undefined) return { goal_id: id, parts: listed.split(", ").filter((p) => /^M\d+$/.test(p)).map((p) => ({ part: `${p} answered`, met: true, evidence: [all[0]!] })), outcome: "answered", verdicts: [], missing: [] };
      // The check of the claim, first try: the sources disagree, so the claim is left open.
      if (g.includes("(Y2018)") && g.includes("attempt 1")) return { goal_id: id, parts: [{ part: "the year of the closure", met: false, evidence: [] }], outcome: "conflicting", verdicts: claims.map((c) => ({ claim_id: c, verdict: "unsettled" })), missing: ["which year is right"] };
      const latest = all.filter((e) => e.startsWith(`r${Math.max(...all.map((x) => Number(/^r(\d+)/.exec(x)![1])))}-`));
      return { goal_id: id, parts: [{ part: "the answer", met: true, evidence: latest }], outcome: "answered", verdicts: claims.map((c) => ({ claim_id: c, verdict: "supported" })), missing: [] };
    });
  const newterm = lines(block(message, "served_goals")).find((l) => l.text.includes("(NEWTERM)"));
  const proposals = newterm
    ? [{
        text: "What does the county bookmobile offer the residents of Ashby since the public library closed?",
        template: "T1", need: "necessary", object_id: "O1", new_object: "county bookmobile", new_object_quote: "county bookmobile now serves Ashby",
        prompted_by: [newterm.id], leads_to: ["Q2"], done_when: "What the bookmobile offers and how often, with its source.", source_hints: ["county library service"],
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
        const args = name === PLAN_TOOL ? PLAN : name === "submit_conflicts" ? conflicts(message) : round(message);
        return new AIMessage({ content: "", tool_calls: [{ id: `c${calls.length}`, name, args: args as Record<string, unknown>, type: "tool_call" }] });
      },
    }),
  } as unknown as BaseChatModel;
  return { model, calls };
}

async function run(options: Record<string, unknown> = {}, researchersTotal = 10, researcher = research) {
  const { model, calls } = fakeModel();
  const decisions: DecisionRecord[] = [];
  let synthesis: { material: { label: string; notes: string }[]; outline?: string[]; guidance?: string } | undefined;
  const graph = buildResearchGraph({
    strategy: ebd.create(options as never),
    strategyModel: model,
    research: researcher,
    write: async (_q, s) => ((synthesis = s), { report: "report", diagnostics: [] }),
    limits: { researchersTotal, toolCallsPerResearcher: 12 },
    maxRounds: 8,
    concurrency: 4,
    runId: "t",
    today: TODAY,
    hooks: { onDecision: (d) => void decisions.push(d) },
  });
  const final = await graph.invoke(initialState(QUESTION), { recursionLimit: 100 });
  return { final, decisions, synthesis: synthesis!, calls, state: final.strategyState as EbdState };
}

describe("ebd strategy through the skeleton", () => {
  it("settles the disagreement that decides the claim, grows a goal from a new term and stops complete", async () => {
    const { final, decisions, synthesis, calls, state } = await run();
    expect(final.stopReason).toBe("strategy-stop");
    expect(state.stop).toMatchObject({ kind: "complete" });
    expect(final.synthesisDiagnostics).toEqual([]);
    expect(calls[0]).toBe(PLAN_TOOL);
    expect(state.problems).toEqual([]);

    // Round 1: a researcher for each main part; the check of the claim leads the first brief.
    expect(decisions[0]!.accepted.map((b) => b.tag)).toEqual(["Q1,Q3", "Q4"]);
    const goal = (id: string) => state.goals.find((g) => g.id === id)!;

    // The two years decide the claim A1, so the disagreement got a necessary settle goal; settling it answered the check.
    const c1 = state.conflicts.find((c) => c.type === "source_vs_source")!;
    expect(c1).toMatchObject({ status: "settled", about: "Q1", claim: "A1", critical: true });
    expect(goal(c1.settleGoal!)).toMatchObject({ kind: "settle", level: 1, status: "answered", verifies: ["A1"] });
    expect(goal("Q1")).toMatchObject({ status: "answered", verdicts: { A1: "supported" } });

    // The new term grew one goal, one step from the request, served in round 2 beside the settle goal.
    const grown = state.goals.find((g) => g.origin.type === "finding")!;
    expect(grown).toMatchObject({ depth: 1, status: "answered", need: "necessary", leadsTo: ["Q2"] });
    expect(state.objectsFound[0]).toMatchObject({ text: "county bookmobile", parent: "O1" });
    expect(decisions[1]!.accepted.map((b) => b.tag).sort()).toEqual([c1.settleGoal!, grown.id].sort());
    expect(state.tree.byOrigin).toMatchObject({ conflict: 1, finding: 1 });

    // Writer input: whole notes lines, the line about the other Ashby removed, and only what the notes do not show.
    const all = synthesis.material.map((m) => m.notes).join("\n");
    expect(all).not.toContain("OFFTARGET");
    expect(all).toContain("(Y2019)");
    expect(synthesis.material[0]!.notes.startsWith("# [")).toBe(true);
    expect(synthesis.outline).toBeUndefined();
    expect(synthesis.guidance).toContain("different referent");
    // The claim holds after the settle goal, so the writer gets no line about it.
    expect(synthesis.guidance).not.toContain("The question presupposes");

    // Every step recorded its own model calls for the viewer.
    expect(decisions.map((d) => (d.strategyState as EbdState).step.calls.map((c) => c.role))).toEqual([
      ["environment_analyst"],
      ["conflict_checker", "round_analyst"],
      ["conflict_checker", "round_analyst"],
    ]);
  });

  it("makes no conflict records with conflicts: false (H1 ablation)", async () => {
    const { state, calls } = await run({ conflicts: false });
    expect(calls).not.toContain("submit_conflicts");
    expect(state.conflicts).toEqual([]);
    expect(state.goals.some((g) => g.settles)).toBe(false);
    // Without a conflict record the analyst's "conflicting" judgment is judged on its parts, and the check is searched again.
    expect(state.goals.find((g) => g.id === "Q1")!.servedRounds).toEqual([1, 2]);
    expect(state.stop).toMatchObject({ kind: "complete" });
  });

  it("serves only the plan's goals with newGoals: false (tree-growth ablation)", async () => {
    const { state } = await run({ newGoals: false });
    expect(state.goals.every((g) => g.origin.type !== "finding" && g.origin.type !== "uncovered")).toBe(true);
    expect(state.objectsFound).toEqual([]);
    // The disagreement that decides the claim is still settled.
    expect(state.goals.filter((g) => g.settles).map((g) => g.status)).toEqual(["answered"]);
    expect(state.stop).toMatchObject({ kind: "complete" });
  });

  it("reports a run whose researchers all failed as researcher failures, with its claim unchecked (live failure test, 2026-11-05)", async () => {
    const failing = async (question: string, brief: ResearchBrief): Promise<ResearchResult> => ({ ...(await research(question, brief)), status: "failed", notes: "", failure: { kind: "timeout", message: "timed out" } });
    const { state, synthesis } = await run({}, 30, failing);
    expect(state.stop?.kind).toBe("researcher_failures");
    const tried = state.goals.filter((g) => g.attempts > 0);
    expect(tried.length).toBeGreaterThan(0);
    expect(tried.every((g) => g.status === "exhausted" && g.failedAttempts === g.attempts)).toBe(true);
    // Nothing was checked, so the claim has no verdict, and the writer gets only the short note, with no outline.
    expect(state.goals.every((g) => Object.keys(g.verdicts).length === 0)).toBe(true);
    expect(synthesis.guidance).toMatch(/^Nothing could be researched: every researcher failed for technical reasons/);
    expect(synthesis.outline).toBeUndefined();
  });

  it("records the unmet demand when the budget runs out", async () => {
    const { final, state } = await run({}, 2);
    expect(final.stopReason).toBe("budget-exhausted");
    expect(state.stop?.kind).toBe("budget");
    expect(final.decisions.at(-1)!.dropped.length).toBeGreaterThan(0);
  });
});
