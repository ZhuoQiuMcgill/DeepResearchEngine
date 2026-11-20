/**
 * Critical conflicts, the follow-up rules and the lean writer input (design section 20), without
 * network. With both options off, everything sent to a model is the earlier text.
 */
import { describe, expect, it } from "vitest";
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { buildResearchGraph, initialState, type DecisionRecord } from "../../graph/skeleton.js";
import { MAX_PART_QUESTIONS, askedByPart, isClaimCheck, shareChecks } from "./briefs.js";
import { applyExtension, isSuperseded, type ExtensionReply } from "./extension.js";
import { gatesAnswer, goalsFromAnalysis, treeMetrics } from "./goals.js";
import ebd from "./index.js";
import { parseOptions } from "./options.js";
import { apiJsonSchema } from "./request/index.js";
import { EXAMPLES } from "./request/examples.js";
import { ANALYST_FOCUS_SECTION, ANALYST_MAP_SECTION, ANALYST_SYSTEM, FOCUS_NECESSARY, MAIN_PARTS_CITED, MAIN_PARTS_UNCITED, acceptProposals, analystMessage, analystSystem, applyJudgments, checkRound, type RoundReply } from "./rounds/analyst.js";
import { CONFLICT_CRITICAL_SECTION, CONFLICT_MAP_SECTION, CONFLICT_SYSTEM, applyConflicts, asksCritical, checkConflicts, conflictSystem, conflictsToolSchema, settlePriority } from "./rounds/conflicts.js";
import { readResult } from "./rounds/evidence.js";
import { isCritical, type Conflict, type EbdState } from "./state.js";
import { CRITICAL_HEADING, DISAGREEMENT_SECTION, MAX_CRITICAL_LINES, READING_LABEL, buildGuidance, buildOutline, buildSynthesis, criticalForWriter } from "./synthesis.js";

const E1 = EXAMPLES[0]!;
const off = parseOptions({});
const focus = parseOptions({ focusFollowUp: true });

function stateOf(): EbdState {
  const analysis = structuredClone(E1.analysis);
  const goals = goalsFromAnalysis(analysis);
  return {
    question: E1.request,
    today: E1.runDate,
    init: { mode: "fixed", accepted: true, fallback: false, attempts: 1, stopReason: "accepted" },
    analysis,
    goals,
    objectsFound: [],
    map: null,
    conflicts: [],
    evidence: [],
    results: [],
    roundsObserved: 0,
    extraRoundServed: false,
    stop: null,
    tree: treeMetrics(goals),
    step: { phase: "init", round: 0, calls: [], events: [] },
    problems: [],
  };
}

/** Findings f1 and f2 (two hosts) and gap g1 under Q2, finding f3 (a third host) under Q1. */
const NOTES = [
  "## [Q2] How are prices measured?",
  "### Cited Findings",
  "- The index rose 4% — [StatCan](https://www.statcan.gc.ca/a)",
  "- Dealers report higher prices — https://news.example.org/x.",
  "### Gaps",
  "- No regional data.",
  "",
  "## [Q1] Did the US impose tariffs?",
  "### Cited Findings",
  "- Yes, in April 2025 — [Gov](https://gov.example/t)",
].join("\n");

function withEvidence() {
  const s = stateOf();
  const brief: ResearchBrief = { id: "r1-b1", round: 1, objective: "o", keyQuestions: ["[Q2] q", "[Q1] q"], constraints: [], sourceHints: [], tag: "Q2,Q1" };
  const result: ResearchResult = { brief, status: "ok", notes: NOTES, sources: [], queries: [], usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [] };
  const { record, evidence } = readResult(result);
  s.results.push(record);
  s.evidence.push(...evidence);
  return { s, evidence };
}

const goalOf = (s: EbdState, id: string) => s.goals.find((g) => g.id === id)!;
const disagreement = { type: "source_vs_source" as const, about: "Q2", statement: "They differ.", side_a: ["r1-b1-f1"], side_b: ["r1-b1-f2"], settle_by: "The official release.", condition: "", claim: "" };
const conflictOf = (fields: Partial<Conflict>): Conflict => ({ id: "C1", type: "source_vs_source", about: "Q2", statement: "They differ.", sideA: ["r1-b1-f1"], sideB: ["r1-b1-f2"], settleBy: "x", condition: "", claim: null, critical: null, status: "disputed", createdRound: 1, settledRound: 1, settleGoal: null, checkedBy: null, ...fields });
const judgment = (goal_id: string, met: number, unmet: number, extra: Partial<RoundReply["judgments"][number]> = {}): RoundReply => ({
  judgments: [{
    goal_id,
    parts: [...Array.from({ length: met }, (_, i) => ({ part: `met part ${i + 1}`, met: true, evidence: ["r1-b1-f1", "r1-b1-f2"] })), ...Array.from({ length: unmet }, (_, i) => ({ part: `unmet part ${i + 1}`, met: false, evidence: [] }))],
    outcome: unmet === 0 ? "answered" : met === 0 ? "not_found" : "partial",
    verdicts: [],
    missing: Array.from({ length: unmet }, (_, i) => `unmet part ${i + 1}`),
    ...extra,
  }],
  proposals: [],
});

describe("what is sent to the models (section 20)", () => {
  it("is the earlier text when both options are off", () => {
    expect(conflictSystem(false)).toBe(CONFLICT_SYSTEM);
    expect(analystSystem(false)).toBe(ANALYST_SYSTEM);
    expect(conflictSystem(true)).not.toContain(CONFLICT_CRITICAL_SECTION);
    expect(analystSystem(true)).not.toContain(ANALYST_FOCUS_SECTION);
    expect(JSON.stringify(apiJsonSchema(conflictsToolSchema(false)))).not.toContain('"critical"');
    expect(JSON.stringify(apiJsonSchema(conflictsToolSchema(true)))).not.toContain('"critical"');
    expect(asksCritical(off)).toBe(false);
    const { s } = withEvidence();
    s.conflicts.push(conflictOf({ critical: false, createdRound: 1 }));
    expect(analystMessage(s, 1, [goalOf(s, "Q2")], off)).not.toMatch(/not critical|of them necessary/);
  });

  it("adds each section after the map section, and the mark to the schema, only when asked", () => {
    expect(conflictSystem(true, true)).toContain(`${CONFLICT_MAP_SECTION}\n\n${CONFLICT_CRITICAL_SECTION}`);
    expect(analystSystem(true, true)).toContain(`${ANALYST_MAP_SECTION}\n\n${ANALYST_FOCUS_SECTION}`);
    expect(conflictSystem(false, true)).toContain(CONFLICT_CRITICAL_SECTION);
    expect(JSON.stringify(apiJsonSchema(conflictsToolSchema(false, true)))).toContain('"critical"');
    expect(asksCritical(focus)).toBe(true);
    expect(asksCritical(parseOptions({ leanGuidance: true }))).toBe(true);
  });

  it("shows the round analyst which conflicts are critical, and how many new goals may be necessary", () => {
    const { s } = withEvidence();
    s.conflicts.push(conflictOf({ critical: false }), conflictOf({ id: "C2", critical: true }));
    const message = analystMessage(s, 1, [goalOf(s, "Q2")], focus);
    expect(message).toContain("C1 source_vs_source (not critical) about Q2");
    expect(message).toContain("C2 source_vs_source (critical) about Q2");
    expect(message).toContain(`New goals you may propose this round: 4, at most ${FOCUS_NECESSARY} of them necessary.`);
  });
});

describe("critical conflicts (section 20)", () => {
  it("counts a mark left out as not critical, with a warning, only when the mark is asked for", () => {
    const { s, evidence } = withEvidence();
    const asked = checkConflicts({ conflicts: [disagreement] }, s, evidence, true);
    expect(asked.errors).toEqual([]);
    expect(asked.warnings[0]!.message).toContain("critical was left out");
    expect(asked.value!.conflicts[0]!.critical).toBe(false);
    const notAsked = checkConflicts({ conflicts: [disagreement] }, s, evidence);
    expect(notAsked.warnings).toEqual([]);
    expect(notAsked.value!.conflicts[0]!.critical).toBeUndefined();
  });

  it("gives a settle goal only to a critical conflict, and makes that goal necessary", () => {
    const { s } = withEvidence();
    const log: string[] = [];
    applyConflicts(s, { conflicts: [{ ...disagreement, critical: false }, { ...disagreement, side_a: ["r1-b1-f2"], side_b: ["r1-b1-f3"], about: "Q1", critical: true }] }, 1, focus, (l) => log.push(l));
    expect(s.conflicts.map((c) => [c.critical, c.status, c.settleGoal !== null])).toEqual([[false, "disputed", false], [true, "open", true]]);
    expect(log[0]).toContain("not critical, so it gets no settle goal");
    settlePriority(s, () => {}, true);
    expect(s.goals.find((g) => g.settles === "C2")).toMatchObject({ need: "necessary", level: 1 });
    // Without the option the same settle goal decides no claim and holds up no goal, so it is completing.
    settlePriority(s, () => {});
    expect(s.goals.find((g) => g.settles === "C2")).toMatchObject({ need: "completing", level: 4 });
  });

  it("settles one critical conflict per round, and never leaves out one with a client claim at stake", () => {
    const { s } = withEvidence();
    const log: string[] = [];
    const second = { ...disagreement, side_a: ["r1-b1-f2"], side_b: ["r1-b1-f3"], about: "Q1" };
    const claimed = { ...disagreement, side_a: ["r1-b1-f1"], side_b: ["r1-b1-f3"], about: "Q3", claim: "A2" };
    applyConflicts(s, { conflicts: [{ ...disagreement, critical: true }, { ...second, critical: true }, { ...claimed, critical: false }] }, 1, focus, (l) => log.push(l));
    // The conflict that decides a claim is recorded first and gets its settle goal; of the two others, only the first.
    expect(s.conflicts.map((c) => [c.about, c.claim, c.status, c.settleGoal !== null])).toEqual([["Q3", "A2", "open", true], ["Q2", null, "disputed", false], ["Q1", null, "disputed", false]]);
    expect(log.join("\n")).toContain("one critical conflict is followed up per round");
    // Without a claim among them, the first critical conflict of the round is the one settled.
    const other = withEvidence().s;
    applyConflicts(other, { conflicts: [{ ...disagreement, critical: true }, { ...second, critical: true }] }, 1, focus, () => {});
    expect(other.conflicts.map((c) => [c.about, c.status])).toEqual([["Q2", "open"], ["Q1", "disputed"]]);
    // Without the option, each gets its settle goal, as before.
    const before = withEvidence().s;
    applyConflicts(before, { conflicts: [disagreement, second] }, 1, off, () => {});
    expect(before.conflicts.map((c) => c.status)).toEqual(["open", "open"]);
  });

  it("treats a conflict with a client claim at stake as critical whatever the mark says", () => {
    const { s } = withEvidence();
    applyConflicts(s, { conflicts: [{ ...disagreement, claim: "A2", critical: false }, { ...disagreement, type: "evidence_vs_assumption", about: "Q4", side_a: ["r1-b1-f2"], side_b: ["A3"], critical: false }] }, 1, focus, () => {});
    expect(s.conflicts.map((c) => [c.critical, isCritical(c), c.settleGoal !== null])).toEqual([[true, true, true], [true, true, true]]);
  });

  it("records the mark for the writer without changing the follow-up when only leanGuidance is on, and no mark when both are off", () => {
    const lean = withEvidence().s;
    applyConflicts(lean, { conflicts: [{ ...disagreement, critical: false }] }, 1, parseOptions({ leanGuidance: true }), () => {});
    expect(lean.conflicts[0]).toMatchObject({ critical: false, status: "open" });
    expect(lean.goals.some((g) => g.settles === "C1")).toBe(true);
    const plain = withEvidence().s;
    applyConflicts(plain, { conflicts: [{ ...disagreement, critical: true }] }, 1, off, () => {});
    expect(plain.conflicts[0]!.critical).toBeNull();
  });
});

describe("what is searched again (section 20)", () => {
  it("searches a partial goal again only when most of it is unanswered", () => {
    for (const [met, unmet, withFocus, status] of [[2, 1, true, "answered"], [1, 1, true, "answered"], [1, 2, true, "open"], [2, 1, false, "open"]] as const) {
      const { s } = withEvidence();
      const q3 = goalOf(s, "Q3");
      q3.attempts = 1;
      const log: string[] = [];
      const applied = applyJudgments(s, judgment("Q3", met, unmet), [q3], 1, withFocus ? focus : off, (l) => log.push(l));
      expect([met, unmet, withFocus, q3.status]).toEqual([met, unmet, withFocus, status]);
      if (status === "answered") {
        expect(applied.settled).toEqual(["Q3"]);
        expect(log.at(-1)).toContain("answered in the main; not searched again: unmet part 1");
        expect(q3.missing).toEqual(["unmet part 1"]);
      }
    }
  });

  it("ends a premise check once its claim is decided on enough independent sources, whatever its other parts say", () => {
    const run = (verdict: "supported" | "unsettled", evidence: string[]) => {
      const { s } = withEvidence();
      const q1 = goalOf(s, "Q1");
      q1.attempts = 1;
      const reply: RoundReply = {
        judgments: [{ goal_id: "Q1", parts: [{ part: "states the verdict", met: false, evidence: [] }, { part: "dates of the sources", met: false, evidence: [] }, { part: "the tariffs", met: true, evidence }], outcome: "partial", verdicts: [{ claim_id: "A1", verdict }], missing: ["an explicit verdict"] }],
        proposals: [],
      };
      const log: string[] = [];
      applyJudgments(s, reply, [q1], 1, focus, (l) => log.push(l));
      return { status: q1.status, log };
    };
    const done = run("supported", ["r1-b1-f1", "r1-b1-f3"]);
    expect(done.status).toBe("answered");
    expect(done.log.at(-1)).toContain("claim A1 supported on 2 independent sources → answered (1/3 parts)");
    // One source is below the evidence floor, and an unsettled claim is what a second search is for.
    expect(run("supported", ["r1-b1-f3"]).status).toBe("open");
    expect(run("unsettled", ["r1-b1-f1", "r1-b1-f3"]).status).toBe("open");
  });

  it("applies the evidence floor to client claims only", () => {
    for (const [options, status] of [[off, "open"], [focus, "answered"]] as const) {
      const { s } = withEvidence();
      const q3 = goalOf(s, "Q3");
      q3.attempts = 1;
      // Q3 asks for dates and checks no claim; its one met part rests on one host.
      const reply = judgment("Q3", 1, 0);
      reply.judgments[0]!.parts[0]!.evidence = ["r1-b1-f1"];
      applyJudgments(s, reply, [q3], 1, options, () => {});
      expect(q3.status).toBe(status);
    }
  });

  it("gives a settle goal one attempt", () => {
    for (const [options, goalStatus, conflictStatus] of [[focus, "exhausted", "disputed"], [off, "open", "open"]] as const) {
      const { s } = withEvidence();
      applyConflicts(s, { conflicts: [{ ...disagreement, critical: true }] }, 1, options, () => {});
      const settleGoal = s.goals.find((g) => g.settles === "C1")!;
      settleGoal.attempts = 1;
      const log: string[] = [];
      applyJudgments(s, judgment(settleGoal.id, 0, 1), [settleGoal], 2, options, (l) => log.push(l));
      expect([settleGoal.status, s.conflicts[0]!.status]).toEqual([goalStatus, conflictStatus]);
      if (options.focusFollowUp) expect(log.join("\n")).toContain("a settle goal gets one attempt");
    }
  });

  it("lets a conflict hold a goal only when it decides a claim the goal checks", () => {
    for (const critical of [false, true]) {
      const { s } = withEvidence();
      const q3 = goalOf(s, "Q3");
      q3.attempts = 1;
      s.conflicts.push(conflictOf({ about: "Q3", critical }));
      const log: string[] = [];
      applyJudgments(s, judgment("Q3", 2, 0, { outcome: "conflicting", missing: ["which value holds"] }), [q3], 1, focus, (l) => log.push(l));
      expect(q3).toMatchObject({ status: "answered", partsMet: 2 });
      expect(log[0]).toContain("no conflict about it decides a claim it checks");
    }
    // Q2 checks A2, and the conflict decides A2: the goal ends disputed with its conflict.
    const { s } = withEvidence();
    const q2 = goalOf(s, "Q2");
    q2.attempts = 1;
    s.conflicts.push(conflictOf({ about: "Q2", critical: true, claim: "A2" }));
    applyJudgments(s, judgment("Q2", 2, 0, { outcome: "conflicting", verdicts: [{ claim_id: "A2", verdict: "unsettled" }], missing: ["which value holds"] }), [q2], 1, focus, () => {});
    expect(q2.status).toBe("disputed");
    // Without the option, any disputed conflict about the goal holds it, as before.
    const before = withEvidence().s;
    const q3 = goalOf(before, "Q3");
    q3.attempts = 1;
    before.conflicts.push(conflictOf({ about: "Q3" }));
    applyJudgments(before, judgment("Q3", 2, 0, { outcome: "conflicting", missing: ["which value holds"] }), [q3], 1, off, () => {});
    expect(q3.status).toBe("disputed");
  });
});

describe("new goals (section 20)", () => {
  const proposal = (text: string, need: "necessary" | "completing", prompted_by: string[]): RoundReply["proposals"][number] => ({
    text, template: "T1", need, object_id: "O9", new_object: "", new_object_quote: "", prompted_by, leads_to: ["Q5"], done_when: "What the sources report.", source_hints: [],
  });

  it("makes no goal from a proposal that follows up a conflict", () => {
    const reply: RoundReply = { judgments: [], proposals: [proposal("Which index value for 2025 is the right one, 4% or 5%, in the official release?", "necessary", ["C1", "r1-b1-f1"])] };
    for (const [critical, why] of [[false, "it is not critical"], [true, "a critical conflict is followed up by its settle goal only"]] as const) {
      const log: string[] = [];
      expect(acceptProposals(withConflict(critical), reply, 1, focus, (l) => log.push(l))).toEqual([]);
      expect(log[0]).toContain(`follows up the conflict C1; ${why}`);
    }
    expect(acceptProposals(withConflict(false), reply, 1, off, () => {})).toHaveLength(1);
  });

  function withConflict(critical: boolean): EbdState {
    const { s } = withEvidence();
    s.conflicts.push(conflictOf({ critical }));
    return s;
  }

  it(`keeps at most ${FOCUS_NECESSARY} new goals of a round necessary`, () => {
    const texts = [
      "How do leasing companies set monthly payments for new vehicles after import duties change?",
      "Which provinces publish dealer inventory counts, and how often are those counts refreshed?",
      "What role do currency hedging contracts play for importers of vehicles assembled abroad?",
    ];
    const reply: RoundReply = { judgments: [], proposals: texts.map((t) => proposal(t, "necessary", ["r1-b1-f1"])) };
    const { s } = withEvidence();
    const log: string[] = [];
    expect(acceptProposals(s, reply, 1, focus, (l) => log.push(l)).map((g) => [g.need, g.level])).toEqual([["necessary", 2], ["necessary", 2], ["completing", 4]]);
    expect(log.join("\n")).toContain(`completing, because ${FOCUS_NECESSARY} new goals of this round are already necessary`);
    expect(acceptProposals(withEvidence().s, reply, 1, off, () => {}).map((g) => g.need)).toEqual(["necessary", "necessary", "necessary"]);
  });
});

describe("a main part of the answer that no finding mentions (section 26)", () => {
  const LEASING = "How do leasing companies set monthly payments for new vehicles after import duties change?";
  const INVENTORY = "Which provinces publish dealer inventory counts, and how often are those counts refreshed?";
  const HEDGING = "What role do currency hedging contracts play for importers of vehicles assembled abroad?";
  const proposal = (text: string, need: "necessary" | "completing", prompted_by: string[], extra: Partial<RoundReply["proposals"][number]> = {}): RoundReply["proposals"][number] => ({
    text, template: "T1", need, object_id: "O9", new_object: "", new_object_quote: "", prompted_by, leads_to: ["Q5"], done_when: "What the sources report.", source_hints: [], ...extra,
  });
  const cited = parseOptions({ focusFollowUp: true, uncitedParts: false });
  const accept = (proposals: RoundReply["proposals"], options = focus) => {
    const { s } = withEvidence();
    const log: string[] = [];
    const added = acceptProposals(s, { judgments: [], proposals }, 1, options, (l) => log.push(l));
    return { s, added, log: log.join("\n") };
  };

  it("sends the approved sentence, and the earlier one with the option off", () => {
    expect(ANALYST_FOCUS_SECTION).toContain(MAIN_PARTS_UNCITED);
    expect(analystSystem(true, true)).toContain("propose a necessary goal before you propose any detail. Cite the finding or gap that mentions it; when nothing mentions it, cite nothing.");
    expect(analystSystem(true, true, false)).toContain(MAIN_PARTS_CITED);
    expect(analystSystem(true, true, false)).not.toContain(MAIN_PARTS_UNCITED);
    expect(analystSystem(true, true, false)).toBe(analystSystem(true, true).replace(MAIN_PARTS_UNCITED, MAIN_PARTS_CITED));
    expect(analystSystem(false, false, false)).toBe(ANALYST_SYSTEM);
  });

  it("accepts a necessary goal that cites nothing, one step from the request", () => {
    const { added, log } = accept([proposal(LEASING, "necessary", [])]);
    expect(added).toHaveLength(1);
    expect(added[0]).toMatchObject({ need: "necessary", origin: { type: "uncovered" }, depth: 1, objectIds: ["O9"], leadsTo: ["Q5"], createdRound: 2 });
    expect(log).toContain("created (define, necessary, depth 1) for a main part of the answer that no finding mentions");
    // A citation of a line that does not exist is no citation.
    expect(accept([proposal(LEASING, "necessary", ["r9-b9-f9"])]).added[0]!.origin).toEqual({ type: "uncovered" });
    // A goal that cites a finding keeps its origin.
    expect(accept([proposal(LEASING, "necessary", ["r1-b1-f1"])]).added[0]!.origin).toEqual({ type: "finding", evidence: ["r1-b1-f1"] });
  });

  it("still rejects a detail that cites nothing, and every such goal with the option off or without the follow-up rules", () => {
    const detail = accept([proposal(LEASING, "completing", [])]);
    expect(detail.added).toEqual([]);
    expect(detail.log).toContain("only a necessary goal for a main part of the answer may cite nothing");
    for (const options of [cited, off, parseOptions({ uncitedParts: true })]) {
      const out = accept([proposal(LEASING, "necessary", [])], options);
      expect(out.added).toEqual([]);
      expect(out.log).toContain("rejected (cites no existing evidence or conflict)");
    }
  });

  it("counts it among the necessary goals of the round and never makes it a detail", () => {
    // Two necessary goals are taken: a third that cites nothing is rejected, one that cites a finding becomes completing.
    const third = accept([proposal(LEASING, "necessary", ["r1-b1-f1"]), proposal(INVENTORY, "necessary", []), proposal(HEDGING, "necessary", [])]);
    expect(third.added.map((g) => [g.origin.type, g.need])).toEqual([["finding", "necessary"], ["uncovered", "necessary"]]);
    expect(third.log).toContain(`rejected (cites nothing, and ${FOCUS_NECESSARY} new goals of this round are already necessary)`);
    const mixed = accept([proposal(LEASING, "necessary", []), proposal(INVENTORY, "necessary", []), proposal(HEDGING, "necessary", ["r1-b1-f1"])]);
    expect(mixed.added.map((g) => [g.origin.type, g.need])).toEqual([["uncovered", "necessary"], ["uncovered", "necessary"], ["finding", "completing"]]);
  });

  it("moves a goal attached to the answer asked for to an object of the goal it serves", () => {
    // O1 is "Why", the answer the client asks for. Q5 is about O10 and O11; Q7 is a synthesis question.
    const served = accept([proposal(LEASING, "necessary", [], { object_id: "O1" })]);
    expect(served.added[0]!.objectIds).toEqual(["O10"]);
    expect(served.log).toContain("an object of the goal it serves");
    const first = accept([proposal(LEASING, "necessary", [], { object_id: "O1", leads_to: ["Q7"] })]);
    expect(first.added[0]!.objectIds).toEqual(["O2"]);
    expect(first.log).toContain("the first object of the request that is not the answer");
  });

  it("takes no new term into the objects without a finding", () => {
    const { s, added, log } = accept([proposal(LEASING, "necessary", [], { new_object: "leasing companies", new_object_quote: "leasing companies" })]);
    expect(added[0]!.objectIds).toEqual(["O9"]);
    expect(s.objectsFound).toEqual([]);
    expect(log).toContain('the term "leasing companies" is not added to the objects, because no finding is cited for it');
  });

  it("warns about an empty citation only where it is not allowed", () => {
    const { s } = withEvidence();
    const reply = (need: "necessary" | "completing") => ({ judgments: [], proposals: [proposal(LEASING, need, [])] });
    expect(checkRound(reply("necessary"), s, [], true).warnings).toEqual([]);
    expect(checkRound(reply("completing"), s, [], true).warnings).toHaveLength(1);
    expect(checkRound(reply("necessary"), s, []).warnings).toHaveLength(1);
    expect(checkRound({ judgments: [], proposals: [proposal(LEASING, "necessary", ["r9-b9-f9"])] }, s, [], true).warnings[0]!.message).toContain("unknown: r9-b9-f9");
  });
});

describe("lean writer input (section 20)", () => {
  it("tells the writer the reading of the question, the premises that do not hold and at most three critical conflicts", () => {
    const { s } = withEvidence();
    goalOf(s, "Q1").verdicts = { A1: "supported" };
    goalOf(s, "Q4").verdicts = { A3: "contradicted" };
    for (const id of ["Q1", "Q4"]) Object.assign(goalOf(s, id), { status: "answered", settledRound: 1 });
    s.conflicts.push(
      conflictOf({ id: "C1", statement: "A detail differs.", critical: false }),
      conflictOf({ id: "C2", statement: "First critical point.", critical: true }),
      conflictOf({ id: "C3", statement: "Second critical point.", critical: true, status: "settled", settleGoal: "Q1" }),
      conflictOf({ id: "C4", statement: "Prices rose or fell.", critical: true, claim: "A2" }),
      conflictOf({ id: "C5", statement: "Fourth critical point.", critical: true }),
      conflictOf({ id: "C6", type: "time_dependent", statement: "Two rates.", condition: "10% until March; 25% since April.", critical: true, status: "settled" }),
      conflictOf({ id: "C7", statement: "The tariffs caused the rise or did not.", critical: true, claim: "A3" }),
    );
    expect(criticalForWriter(s).map((c) => c.id)).toEqual(["C4", "C2", "C3"]);
    const guidance = buildGuidance(s, true);
    expect(guidance).toContain(`${READING_LABEL} ${s.analysis.restated_request}`);
    expect(guidance).toContain(CRITICAL_HEADING);
    expect(guidance).toContain("- Prices rose or fell. Give both sides, each with the source the notes cite for it (statcan.gc.ca, news.example.org), and say which one the report follows and why, or that the evidence does not decide it.");
    expect(guidance).toContain("- Second critical point. This was researched further, and the notes show which account holds and why.");
    expect(guidance.split("\n").filter((l) => /critical point|rose or fell|detail differs|Two rates|caused the rise/.test(l))).toHaveLength(MAX_CRITICAL_LINES);
    // The premise that holds gets no line; the contradicted one does, and its conflict (C7) needs no second line.
    expect(guidance).not.toContain("The evidence supports this");
    expect(guidance).toContain("The evidence contradicts this; say so plainly early in the report.");
    expect(guidance).not.toMatch(/What each part of the report must contain|only partly established|Where the sources disagree|were not pursued/);
    // A goal cancelled with the contradicted premise is named only in the full guidance.
    goalOf(s, "Q6").status = "moot";
    expect(buildGuidance(s, true)).not.toContain("were not pursued");
    expect(buildGuidance(s)).toContain("These questions were not pursued because a premise they rely on was contradicted");
    // The full guidance still gives every conflict a line.
    expect(buildGuidance(s)).toContain("A detail differs.");
    expect(buildGuidance(s)).toContain("The evidence supports this.");
  });

  it("gives the reading of the question only when the question cannot be taken at its word", () => {
    const { s } = withEvidence();
    for (const [id, claim] of [["Q1", "A1"], ["Q2", "A2"], ["Q4", "A3"]] as const) Object.assign(goalOf(s, id), { status: "answered", settledRound: 1, verdicts: { [claim]: "supported" } });
    expect(buildGuidance(s, true)).not.toContain(READING_LABEL);
    // A premise without a verdict, or a term with several meanings, brings the reading in.
    goalOf(s, "Q4").verdicts = { A3: "unsettled" };
    expect(buildGuidance(s, true)).toContain(`${READING_LABEL} ${s.analysis.restated_request}`);
    // An unsettled premise is not to be presented as established; only the full guidance has the report say so.
    expect(buildGuidance(s, true)).toContain("The evidence neither confirms nor contradicts this; do not present it as established.");
    expect(buildGuidance(s)).toContain("The evidence does not establish this; state that it is not established.");
    goalOf(s, "Q4").verdicts = { A3: "supported" };
    s.analysis.rom.objects[3]!.readings = ["a tax on imports", "a price list"];
    expect(buildGuidance(s, true)).toContain(READING_LABEL);
    expect(buildGuidance(s)).not.toContain(READING_LABEL);
  });

  it("gives an outline only for a request with several parts, and never a section for disagreements", () => {
    const { s } = withEvidence();
    s.conflicts.push(conflictOf({ critical: true }));
    expect(buildOutline(s)).toContain(DISAGREEMENT_SECTION);
    expect(buildOutline(s, true)).toEqual(s.analysis.questions.filter((q) => q.route === "synthesis").map((q) => q.text));
    s.analysis.questions = s.analysis.questions.filter((q) => q.id !== "Q8");
    expect(buildOutline(s)).toHaveLength(2);
    expect(buildOutline(s, true)).toEqual([]);
    expect(buildSynthesis(s, { leanGuidance: true }).outline).toBeUndefined();
  });

  it("reads records made without the mark: a conflict is critical when its settle goal is necessary", () => {
    const { s } = withEvidence();
    applyConflicts(s, { conflicts: [disagreement, { ...disagreement, side_a: ["r1-b1-f2"], side_b: ["r1-b1-f3"], about: "Q1" }] }, 1, off, () => {});
    expect(s.conflicts.every((c) => c.critical === null)).toBe(true);
    const [first, second] = s.goals.filter((g) => g.settles);
    Object.assign(first!, { need: "necessary" });
    Object.assign(second!, { need: "completing" });
    expect(criticalForWriter(s).map((c) => c.id)).toEqual(["C1"]);
  });
});

// ---------------------------------------------------------------- follow-up briefs, through the skeleton

const EXTENSION: ExtensionReply = {
  subject: "2025 US tariffs and new-car prices in Canada",
  subject_object_ids: ["O4"],
  events: [
    { name: "Passing the cost on", need: "necessary", question: "How do importers and dealers pass the cost of the 2025 US tariffs on to buyers of new cars in Canada?", parts: [{ text: "importer and dealer margins", kind: "economic" }, { text: "price lists of the makers", kind: "built_digital" }], source_hints: [], feeds: ["Q7"] },
    { name: "Buyers' response", need: "necessary", question: "How did buyers of new cars in Canada respond to price changes after the 2025 US tariffs?", parts: [{ text: "sales volumes", kind: "economic" }, { text: "shift to used cars", kind: "social" }], source_hints: [], feeds: ["Q7"] },
  ],
  replaces: ["Q6"],
};

describe("a replaced question (section 20)", () => {
  it("is superseded once the necessary event goals that replaced it have been researched", () => {
    const s = stateOf();
    applyExtension(s, EXTENSION, () => {});
    const q6 = goalOf(s, "Q6");
    expect(s.map!.replaced.Q6).toEqual(["Q9", "Q10"]);
    expect(isSuperseded(s, q6)).toBe(false);
    goalOf(s, "Q9").attempts = 1;
    expect(isSuperseded(s, q6)).toBe(false);
    goalOf(s, "Q10").attempts = 1;
    expect(isSuperseded(s, q6)).toBe(true);
    expect(isSuperseded(s, goalOf(s, "Q3"))).toBe(false);
  });
});

describe("the order of a follow-up round (section 25)", () => {
  const notes = [
    "## [Q2] How are prices measured?",
    "### Cited Findings",
    "- The index rose 4% — [StatCan](https://www.statcan.gc.ca/a)",
    "- Dealers report lower prices — https://news.example.org/x.",
    "",
    "## [Q1] Did the US impose tariffs?",
    "### Cited Findings",
    "- Yes, in April 2025 — [Gov](https://gov.example/t)",
    "- The tariffs took effect in April 2025 — [Trade](https://trade.example/t)",
  ].join("\n");
  const brief: ResearchBrief = { id: "r1-b1", round: 1, objective: "o", keyQuestions: ["[Q2] q", "[Q1] q"], constraints: [], sourceHints: [], tag: "Q2,Q1" };
  const result: ResearchResult = { brief, status: "ok", notes, sources: [], queries: [], usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [] };
  const findings = (goal: string) => readResult(result).evidence.filter((e) => e.kind === "finding" && e.goalIds.includes(goal)).map((e) => e.id);
  const proposal = (text: string) => ({ text, template: "T1", need: "necessary", object_id: "O9", new_object: "", new_object_quote: "", prompted_by: [findings("Q1")[0]!], leads_to: ["Q8"], done_when: "What the sources report.", source_hints: [] });
  const proposals = [
    proposal("How do leasing companies set monthly payments for new vehicles after import duties change?"),
    proposal("Which provinces publish dealer inventory counts, and how often are those counts refreshed?"),
  ];

  /**
   * The plan after round 1, which served Q1 and Q2. The checker reports one critical disagreement
   * about Q2, and the analyst raises two necessary goals (Q10 and Q11) for parts of the answer. With
   * `claim`, the disagreement decides the claim Q2 checks, and Q2 waits for the settle goal (Q9).
   */
  async function followUp(options: Record<string, unknown>, remaining: number, settled: string[], claim = "", given: Record<string, unknown>[] = proposals) {
    const prev = stateOf();
    for (const id of settled) Object.assign(goalOf(prev, id), { status: "answered", attempts: 1, servedRounds: [1], settledRound: 1 });
    const conflict = { type: "source_vs_source", about: "Q2", statement: "One source reports a rise and another a fall of prices.", side_a: [findings("Q2")[0]!], side_b: [findings("Q2")[1]!], settle_by: "The official release.", condition: "", claim, critical: true };
    const q2 = claim
      ? { parts: [{ part: "the answer", met: false, evidence: [] }], outcome: "conflicting", verdicts: [{ claim_id: "A2", verdict: "unsettled" }], missing: ["which account holds"] }
      : { parts: [{ part: "the answer", met: true, evidence: findings("Q2") }], outcome: "answered", verdicts: [{ claim_id: "A2", verdict: "supported" }], missing: [] };
    const reply = {
      judgments: [{ goal_id: "Q2", ...q2 }, { goal_id: "Q1", parts: [{ part: "the answer", met: true, evidence: findings("Q1") }], outcome: "answered", verdicts: [{ claim_id: "A1", verdict: "supported" }], missing: [] }],
      proposals: given,
    };
    const model = {
      bindTools: (tools: { function: { name: string } }[]) => ({
        invoke: async () => {
          const name = tools[0]!.function.name;
          return new AIMessage({ content: "", tool_calls: [{ id: "c", name, args: name === "submit_conflicts" ? { conflicts: [conflict] } : reply, type: "tool_call" }] });
        },
      }),
    } as unknown as BaseChatModel;
    const step = await ebd.create({ focusFollowUp: true, ...options } as never).observe(prev, [result], { model, budget: { researchersTotal: 6, researchersUsed: 6 - remaining, researchersRemaining: remaining, toolCallsPerResearcher: 12 }, round: 2, runId: "t", today: E1.runDate });
    const state = step.state as EbdState;
    return { step, state, tags: step.decision.briefs.map((b) => b.tag) };
  }
  const others = ["Q3", "Q4", "Q5", "Q6"];

  it("sends the researchers to the missing parts of the answer first, and lets the settle goal wait", async () => {
    const { step, state, tags } = await followUp({}, 2, others);
    expect(state.goals.filter((g) => !g.settles && g.origin.type === "finding").map((g) => [g.id, g.need])).toEqual([["Q10", "necessary"], ["Q11", "necessary"]]);
    expect(goalOf(state, "Q9")).toMatchObject({ settles: "C1", need: "necessary", status: "open" });
    expect(tags).toEqual(["Q10", "Q11"]);
    expect(step.decision.rationale).toContain("Settling a disagreement waits (Q9)");
    // The disagreement is not dropped: the run is not complete while its settle goal is open.
    expect(step.decision.stop).toBe(false);
    expect(state.conflicts[0]).toMatchObject({ critical: true, status: "open", settleGoal: "Q9" });
  });

  it("gives the settle goal a researcher of its own when one is left", async () => {
    expect((await followUp({}, 3, others)).tags).toEqual(["Q10", "Q11", "Q9"]);
  });

  it("keeps the order of section 20 with the option off: the settle goal first, the two parts sharing a researcher", async () => {
    expect((await followUp({ mainPartsFirst: false }, 2, others)).tags).toEqual(["Q9", "Q10,Q11"]);
  });

  it("keeps a settle goal in its place when a part of the answer waits behind it", async () => {
    // Q5 depends on Q2, Q2 waits for the settle goal, and Q5 has never been asked.
    const { state, tags } = await followUp({}, 2, ["Q3"], "A2");
    expect(goalOf(state, "Q2")).toMatchObject({ status: "conflicting", waitingOn: "Q9" });
    expect(gatesAnswer(goalOf(state, "Q9"), state, focus)).toBe(true);
    expect(tags).toContain("Q9");
  });

  it("lets a settle goal wait when a goal waits for it but no part of the answer is held up", async () => {
    // Q5 is answered. Q4 depends on Q2 too, but it checks a claim, and a premise check does not wait.
    const { state, tags } = await followUp({}, 2, ["Q3", "Q5"], "A2");
    expect(goalOf(state, "Q2")).toMatchObject({ status: "conflicting", waitingOn: "Q9" });
    expect(gatesAnswer(goalOf(state, "Q9"), state, focus)).toBe(false);
    expect(tags).not.toContain("Q9");
    expect(tags).toContain("Q4");
  });

  it("changes nothing without focusFollowUp", async () => {
    const run = async (options: Record<string, unknown>) => {
      const { step } = await followUp({ focusFollowUp: false, ...options }, 3, others);
      return step.decision.briefs.map((b) => b.tag);
    };
    expect(await run({ mainPartsFirst: true })).toEqual(await run({ mainPartsFirst: false }));
  });

  it("serves a part of the answer that no finding mentions before the settle goal (section 26)", async () => {
    const uncited = proposals.map((p) => ({ ...p, prompted_by: [] }));
    const { state, tags, step } = await followUp({}, 2, others, "", uncited);
    expect(state.goals.filter((g) => g.origin.type === "uncovered").map((g) => [g.id, g.need, g.depth])).toEqual([["Q10", "necessary", 1], ["Q11", "necessary", 1]]);
    expect(tags).toEqual(["Q10", "Q11"]);
    expect(step.decision.stop).toBe(false);
    // With the option off the two proposals are rejected, and the settle goal is all that is left to serve.
    const without = await followUp({ uncitedParts: false }, 2, others, "", uncited);
    expect(without.state.goals.some((g) => g.origin.type === "uncovered")).toBe(false);
    expect(without.tags).toEqual(["Q9"]);
  });
});

describe("a claim check shares a researcher (section 26, option premiseRides)", () => {
  type Plan = (state: EbdState, ctx: unknown, lines: string[], progress: null) => { state: EbdState; decision: { briefs: ResearchBrief[] } };
  const planOf = (options: Record<string, unknown>, state: EbdState) => {
    const step = (ebd.create(options as never) as unknown as { plan: Plan }).plan(state, { budget: { researchersTotal: 6, researchersUsed: 0, researchersRemaining: 6, toolCallsPerResearcher: 12 }, round: 1, runId: "t", today: E1.runDate }, [], null);
    return { state: step.state, briefs: step.decision.briefs, tags: step.decision.briefs.map((b) => (b.tag ?? "").split(",")), log: step.state.step.events.join("\n") };
  };
  const group = (s: EbdState, ...ids: string[]) => ({ key: goalOf(s, ids[0]!).objectIds[0]!, goals: ids.map((id) => goalOf(s, id)) });
  const extended = () => {
    const s = stateOf();
    applyExtension(s, EXTENSION, () => {});
    return s;
  };

  it("names the goals that only check a claim of the question", () => {
    const s = stateOf();
    expect(s.goals.filter(isClaimCheck).map((g) => g.id)).toEqual(["Q1", "Q2", "Q4"]);
    expect(isClaimCheck({ ...goalOf(s, "Q1"), settles: "C1" })).toBe(false);
  });

  it("puts a check into the brief about its own object, else into the one that asks least, and first", () => {
    const s = stateOf();
    // Q4 and Q6 are about O5; no brief is about O4, the object of Q1.
    const out = shareChecks([group(s, "Q3", "Q5"), group(s, "Q5"), group(s, "Q6")], [goalOf(s, "Q4"), goalOf(s, "Q1")], s, { questionsPerBrief: 3 })!;
    expect(out.map((g) => g.goals.map((x) => x.id))).toEqual([["Q3", "Q5"], ["Q1", "Q5"], ["Q4", "Q6"]]);
  });

  it("leaves the round as it was when a check fits nowhere", () => {
    const s = stateOf();
    // A brief carries one check: two checks do not fit into one brief.
    expect(shareChecks([group(s, "Q3")], [goalOf(s, "Q1"), goalOf(s, "Q2")], s, { questionsPerBrief: 3 })).toBeNull();
    // A check joins only a brief with a necessary goal.
    expect(shareChecks([{ key: "O9", goals: [{ ...goalOf(s, "Q3"), need: "completing" }] }], [goalOf(s, "Q1")], s, { questionsPerBrief: 3 })).toBeNull();
    // The example question has three claims to check and one other goal ready in round 1.
    const plan = planOf({ premiseRides: true }, stateOf());
    expect(plan.tags).toEqual(planOf({ premiseRides: false, premiseSort: false }, stateOf()).tags);
    expect(plan.log).toContain("keep a researcher of their own");
  });

  it("never keeps a life-cycle step from being asked part by part", () => {
    const s = extended();
    const event = s.map!.events.find((e) => e.goalId === "Q9")!;
    const more = (n: number) => Array.from({ length: n }, (_, i) => ({ ...event.parts[0]!, id: `M9${i}`, text: `further part ${i + 1}` }));
    const options = { questionsPerBrief: 3, partQuestions: true };
    event.parts.push(...more(3));
    // Five parts and the check make six key questions.
    const joined = shareChecks([group(s, "Q9")], [goalOf(s, "Q1")], s, options)!;
    expect(joined[0]!.goals.map((g) => g.id)).toEqual(["Q1", "Q9"]);
    expect(askedByPart(joined[0]!, s, options).has("Q9")).toBe(true);
    // With a sixth part the check would make seven, and the step would be asked as one question.
    event.parts.push(...more(1).map((p) => ({ ...p, id: "M99" })));
    expect(shareChecks([group(s, "Q9")], [goalOf(s, "Q1")], s, options)).toBeNull();
  });

  it("gives every check a place in a brief that asks for content, in round 1", () => {
    const options = { partQuestions: true, maxPerRound: 6, premiseRides: false, premiseSort: false };
    const before = planOf(options, extended());
    const after = planOf({ ...options, premiseRides: true }, extended());
    const checksOnly = (p: typeof before) => p.tags.filter((t) => t.every((id) => isClaimCheck(goalOf(p.state, id))));
    expect(checksOnly(before).length).toBeGreaterThan(0);
    expect(checksOnly(after)).toEqual([]);
    // Every check is still asked in round 1, one to a brief, and leads its brief.
    expect(after.tags.flat().filter((id) => isClaimCheck(goalOf(after.state, id))).sort()).toEqual(["Q1", "Q2", "Q4"]);
    for (const t of after.tags) expect(t.filter((id) => isClaimCheck(goalOf(after.state, id))).length).toBeLessThanOrEqual(1);
    for (const t of after.tags) expect(t.slice(1).some((id) => isClaimCheck(goalOf(after.state, id)))).toBe(false);
    expect(after.briefs.length).toBeLessThan(before.briefs.length);
    for (const b of after.briefs) expect(b.keyQuestions.length).toBeLessThanOrEqual(MAX_PART_QUESTIONS);
    // The steps are still asked part by part.
    expect(after.briefs.flatMap((b) => b.keyQuestions).filter((k) => k.startsWith("[Q9] Passing the cost on: "))).toHaveLength(2);
    expect(after.log).toContain("asked in a brief that asks for content, with no researcher of their own");
    // After round 1 the option changes nothing.
    const later = () => Object.assign(extended(), { roundsObserved: 1 });
    expect(planOf({ ...options, premiseRides: true }, later()).tags).toEqual(planOf(options, later()).tags);
  });
});

function tagged(message: string, tag: string): string {
  return new RegExp(`<${tag}>\\n([\\s\\S]*?)\\n</${tag}>`).exec(message)?.[1] ?? "";
}

function evidenceLines(text: string): { id: string; text: string }[] {
  return text.split("\n").flatMap((l) => {
    const m = /^(r\d+-b\d+-[fg]\d+) (?:\[[^\]]*\] )?(.*)$/.exec(l);
    return m ? [{ id: m[1]!, text: m[2]! }] : [];
  });
}

const research = async (_q: string, brief: ResearchBrief): Promise<ResearchResult> => {
  const ids = (brief.tag ?? "").split(",");
  const notes = ids
    .map((id, i) => [`## ${brief.keyQuestions[i]}`, "### Cited Findings", `- A finding for ${id}${id === "Q2" ? " (RISE)" : ""}. — [Source](https://${id.toLowerCase()}-a.example/${id})`, `- Another finding for ${id}${id === "Q2" ? " (FALL)" : ""}. — [Source](https://${id.toLowerCase()}-b.example/${id})`, "### Gaps", `- Nothing more for ${id}.`].join("\n"))
    .join("\n\n");
  return { brief, status: "ok", notes, sources: [], queries: [], usage: { inputTokens: 0, outputTokens: 0, searches: 1, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [] };
};

/** The fake checker: one disagreement on Q2, a detail. */
function fakeConflicts(message: string) {
  const fresh = evidenceLines(tagged(message, "new_evidence"));
  const rise = fresh.find((l) => l.text.includes("(RISE)"));
  const fall = fresh.find((l) => l.text.includes("(FALL)"));
  if (!rise || !fall) return { conflicts: [] };
  return { conflicts: [{ type: "source_vs_source", about: "Q2", statement: "One source reports a rise and another a fall of the index.", side_a: [rise.id], side_b: [fall.id], settle_by: "The official release.", condition: "", claim: "", critical: false }] };
}

/** The fake analyst: every goal answered; after round 1 it proposes one necessary and one completing goal on the same object. */
function fakeRound(message: string) {
  const judgments = tagged(message, "served_goals").split(/\n(?=### )/).map((g) => {
    const id = /^### (Q\d+)/.exec(g)![1]!;
    const findings = evidenceLines(g).filter((l) => l.id.includes("-f")).map((l) => l.id);
    if (g.includes("Planned parts of the life-cycle step")) {
      const judge = (/^Judge only: (.*)$/m.exec(g)?.[1] ?? "").split(", ").filter((x) => /^M\d+$/.test(x));
      return { goal_id: id, parts: judge.map((m) => ({ part: `${m} part`, met: true, refuted: false, correction: "", evidence: findings })), outcome: "answered", verdicts: [], missing: [] };
    }
    const claims = [...g.matchAll(/^- (A\d+): /gm)].map((m) => m[1]!);
    return { goal_id: id, parts: [{ part: "the answer", met: true, evidence: findings }], outcome: "answered", verdicts: claims.map((c) => ({ claim_id: c, verdict: "supported" })), missing: [] };
  });
  const first = evidenceLines(tagged(message, "served_goals")).find((l) => l.id.startsWith("r1-") && l.id.includes("-f"));
  const proposals = first && message.includes("attempt 1") && !message.includes("r2-")
    ? [
        { text: "How do leasing companies set monthly payments for new vehicles after import duties change?", template: "T1", need: "necessary", object_id: "O9", new_object: "", new_object_quote: "", prompted_by: [first.id], leads_to: ["Q5"], done_when: "What leasing companies report.", source_hints: [] },
        { text: "Which provinces publish dealer inventory counts, and how often are those counts refreshed?", template: "T1", need: "completing", object_id: "O9", new_object: "", new_object_quote: "", prompted_by: [first.id], leads_to: ["Q5"], done_when: "The provinces and the refresh interval.", source_hints: [] },
      ]
    : [];
  return { judgments, proposals };
}

describe("ebd with focusFollowUp and leanGuidance through the skeleton", () => {
  it("follows up no detail, keeps necessary and completing goals in separate briefs and hands the writer the lean input", async () => {
    const calls: string[] = [];
    const schemas: Record<string, string> = {};
    const model = {
      bindTools: (tools: { function: { name: string; parameters: unknown } }[]) => ({
        invoke: async (messages: BaseMessage[]) => {
          const name = tools[0]!.function.name;
          const message = String(messages.at(-1)!.content);
          calls.push(name);
          schemas[name] = JSON.stringify(tools[0]!.function.parameters);
          const args = name === "submit_analysis" ? E1.analysis : name === "submit_premise_sort" ? { claims: E1.analysis.assumptions.map((x) => ({ id: x.id, verdict: "check", reason: "a specific fact" })) } : name === "submit_extension" ? EXTENSION : name === "submit_conflicts" ? fakeConflicts(message) : fakeRound(message);
          return new AIMessage({ content: "", tool_calls: [{ id: `c${calls.length}`, name, args: args as Record<string, unknown>, type: "tool_call" }] });
        },
      }),
    } as unknown as BaseChatModel;
    const decisions: DecisionRecord[] = [];
    let synthesis: { material: { label: string; notes: string }[]; outline?: string[]; guidance?: string } | undefined;
    const graph = buildResearchGraph({
      strategy: ebd.create({ focusFollowUp: true, leanGuidance: true }),
      strategyModel: model,
      research,
      write: async (_q, s) => ((synthesis = s), { report: "report", diagnostics: [] }),
      limits: { researchersTotal: 12, toolCallsPerResearcher: 12 },
      maxRounds: 8,
      concurrency: 4,
      runId: "t",
      today: E1.runDate,
      hooks: { onDecision: (d) => void decisions.push(d) },
    });
    const final = await graph.invoke(initialState(E1.request), { recursionLimit: 100 });
    const state = final.strategyState as EbdState;
    expect(state.stop?.kind).toBe("complete");
    expect(schemas.submit_conflicts).toContain('"critical"');

    // The disagreement is a detail: recorded, never followed up.
    expect(state.conflicts).toHaveLength(1);
    expect(state.conflicts[0]).toMatchObject({ critical: false, status: "disputed", settleGoal: null });
    expect(state.goals.some((g) => g.settles)).toBe(false);

    // After round 1, no brief holds a necessary goal together with a completing one.
    const needOf = (d: DecisionRecord, id: string) => (d.strategyState as EbdState).goals.find((g) => g.id === id)!.need;
    for (const d of decisions.slice(1)) {
      for (const b of d.accepted) expect(new Set((b.tag ?? "").split(",").map((id) => needOf(d, id))).size).toBe(1);
    }
    const grown = state.goals.filter((g) => g.origin.type === "finding");
    expect(grown.map((g) => [g.need, g.status])).toEqual([["necessary", "answered"], ["completing", "answered"]]);

    // The replaced question Q6 rode along in round 1 or was never served again once its events were researched.
    expect(goalOf(state, "Q6").servedRounds.every((r) => r === 1)).toBe(true);

    // Every premise holds, so the writer gets no reading of the question, and no line for the detail or for the premises.
    expect(synthesis!.guidance).not.toMatch(/The question was read as|rise and another a fall|The evidence supports this|What each part of the report must contain/);
    expect(synthesis!.outline).toEqual(E1.analysis.questions.filter((q) => q.route === "synthesis").map((q) => q.text));
  });
});
