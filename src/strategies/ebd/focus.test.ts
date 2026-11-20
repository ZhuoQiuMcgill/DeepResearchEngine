/**
 * Critical conflicts, what is researched again, new goals and the writer's input (design sections 20,
 * 25, 26 and 29), without network. These are the rules of the one approach; until the consolidation of
 * section 32 each was an option that could be switched off.
 *
 * The states are built from a worked analysis (fixtures.ts), which has goals that wait for one another
 * and three claims to check, so the rules can be tried on more shapes than a plan of main parts gives.
 */
import { describe, expect, it } from "vitest";
import { AIMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { apiJsonSchema } from "./analysis.js";
import { askedByPart, isClaimCheck, shareChecks } from "./briefs.js";
import { EXAMPLES } from "./fixtures.js";
import { gatesAnswer, goalsFromAnalysis, newGoal, nextGoalId, treeMetrics } from "./goals.js";
import ebd from "./index.js";
import { parseOptions } from "./options.js";
import { ANALYST_FOCUS_SECTION, ANALYST_QUESTIONS_SECTION, FOCUS_NECESSARY, MAIN_PARTS_UNCITED, acceptProposals, analystMessage, analystSystem, applyJudgments, checkRound, type RoundReply } from "./rounds/analyst.js";
import { CONFLICT_CRITICAL_SECTION, CONFLICT_QUESTIONS_SECTION, applyConflicts, checkConflicts, conflictSystem, conflictsToolSchema, settlePriority } from "./rounds/conflicts.js";
import { readResult } from "./rounds/evidence.js";
import { isCritical, type Conflict, type EbdState, type Goal, type MapEvent } from "./state.js";
import { CRITICAL_HEADING, MAX_CRITICAL_LINES, READING_LABEL, buildGuidance, buildOutline, buildSynthesis, criticalForWriter } from "./synthesis.js";

const E1 = EXAMPLES[0]!;
const options = parseOptions({});

function stateOf(): EbdState {
  const analysis = structuredClone(E1.analysis);
  const goals = goalsFromAnalysis(analysis);
  return {
    question: E1.request,
    today: E1.runDate,
    init: { mode: "environment", accepted: true, fallback: false, attempts: 1, stopReason: "accepted" },
    analysis,
    goals,
    objectsFound: [],
    map: null,
    conflicts: [],
    evidence: [],
    results: [],
    roundsObserved: 0,
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
  it("puts the critical section after the plan's section, and the mark into the schema", () => {
    expect(conflictSystem(true)).toContain(`${CONFLICT_QUESTIONS_SECTION}\n\n${CONFLICT_CRITICAL_SECTION}`);
    expect(analystSystem(true)).toContain(`${ANALYST_QUESTIONS_SECTION}\n\n${ANALYST_FOCUS_SECTION}`);
    expect(JSON.stringify(apiJsonSchema(conflictsToolSchema(false)))).toContain('"critical"');
    expect(JSON.stringify(apiJsonSchema(conflictsToolSchema(true)))).toContain('"critical"');
  });

  it("shows the round analyst which conflicts are critical, and how many new goals may be necessary", () => {
    const { s } = withEvidence();
    s.conflicts.push(conflictOf({ critical: false }), conflictOf({ id: "C2", critical: true }));
    const message = analystMessage(s, 1, [goalOf(s, "Q2")], options);
    expect(message).toContain("C1 source_vs_source (not critical) about Q2");
    expect(message).toContain("C2 source_vs_source (critical) about Q2");
    expect(message).toContain(`New goals you may propose this round: 4, at most ${FOCUS_NECESSARY} of them necessary.`);
  });
});

describe("critical conflicts (sections 20 and 29)", () => {
  it("counts a mark left out as not critical, with a warning", () => {
    const { s, evidence } = withEvidence();
    const checked = checkConflicts({ conflicts: [disagreement] }, s, evidence);
    expect(checked.errors).toEqual([]);
    expect(checked.warnings[0]!.message).toContain("critical was left out");
    expect(checked.value!.conflicts[0]!.critical).toBe(false);
  });

  it("gives a settle goal only to a conflict that decides a claim of the question, and makes that goal necessary", () => {
    const { s } = withEvidence();
    const log: string[] = [];
    const detail = { ...disagreement, critical: false };
    const dependsOn = { ...disagreement, side_a: ["r1-b1-f2"], side_b: ["r1-b1-f3"], about: "Q1", critical: true };
    const claimed = { ...disagreement, side_a: ["r1-b1-f1"], side_b: ["r1-b1-f3"], about: "Q3", claim: "A2", critical: false };
    applyConflicts(s, { conflicts: [detail, dependsOn, claimed] }, 1, options, (l) => log.push(l));
    // The conflict that decides a claim is recorded first, is critical whatever its mark says, and is the only one researched again.
    expect(s.conflicts.map((c) => [c.about, c.claim, c.critical, c.status, c.settleGoal !== null])).toEqual([
      ["Q3", "A2", true, "open", true],
      ["Q2", null, false, "disputed", false],
      ["Q1", null, true, "disputed", false],
    ]);
    expect(log.join("\n")).toContain("not critical, so it gets no settle goal");
    expect(log.join("\n")).toContain("it decides no claim of the question, so it is reported and not researched again");
    settlePriority(s, () => {});
    expect(s.goals.filter((g) => g.settles).map((g) => [g.settles, g.need, g.level])).toEqual([["C1", "necessary", 1]]);
  });

  it("treats a conflict with a client claim at stake as critical whatever the mark says", () => {
    const { s } = withEvidence();
    applyConflicts(s, { conflicts: [{ ...disagreement, claim: "A2", critical: false }, { ...disagreement, type: "evidence_vs_assumption", about: "Q4", side_a: ["r1-b1-f2"], side_b: ["A3"], critical: false }] }, 1, options, () => {});
    expect(s.conflicts.map((c) => [c.critical, isCritical(c), c.settleGoal !== null])).toEqual([[true, true, true], [true, true, true]]);
  });
});

describe("what is searched again (section 20)", () => {
  it("searches a partial goal again only when most of it is unanswered", () => {
    for (const [met, unmet, status] of [[2, 1, "answered"], [1, 1, "answered"], [1, 2, "open"]] as const) {
      const { s } = withEvidence();
      const q3 = goalOf(s, "Q3");
      q3.attempts = 1;
      const log: string[] = [];
      const applied = applyJudgments(s, judgment("Q3", met, unmet), [q3], 1, options, (l) => log.push(l));
      expect([met, unmet, q3.status]).toEqual([met, unmet, status]);
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
      applyJudgments(s, reply, [q1], 1, options, (l) => log.push(l));
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
    const { s } = withEvidence();
    const q3 = goalOf(s, "Q3");
    q3.attempts = 1;
    // Q3 asks for dates and checks no claim; its one met part rests on one host.
    const reply = judgment("Q3", 1, 0);
    reply.judgments[0]!.parts[0]!.evidence = ["r1-b1-f1"];
    applyJudgments(s, reply, [q3], 1, options, () => {});
    expect(q3.status).toBe("answered");
  });

  it("gives a settle goal one attempt", () => {
    const { s } = withEvidence();
    applyConflicts(s, { conflicts: [{ ...disagreement, claim: "A2", critical: true }] }, 1, options, () => {});
    const settleGoal = s.goals.find((g) => g.settles === "C1")!;
    settleGoal.attempts = 1;
    const log: string[] = [];
    applyJudgments(s, judgment(settleGoal.id, 0, 1, { verdicts: [{ claim_id: "A2", verdict: "unsettled" }] }), [settleGoal], 2, options, (l) => log.push(l));
    expect([settleGoal.status, s.conflicts[0]!.status]).toEqual(["exhausted", "disputed"]);
    expect(log.join("\n")).toContain("a settle goal gets one attempt");
  });

  it("lets a conflict hold a goal only when it decides a claim the goal checks", () => {
    for (const critical of [false, true]) {
      const { s } = withEvidence();
      const q3 = goalOf(s, "Q3");
      q3.attempts = 1;
      s.conflicts.push(conflictOf({ about: "Q3", critical }));
      const log: string[] = [];
      applyJudgments(s, judgment("Q3", 2, 0, { outcome: "conflicting", missing: ["which value holds"] }), [q3], 1, options, (l) => log.push(l));
      expect(q3).toMatchObject({ status: "answered", partsMet: 2 });
      expect(log[0]).toContain("no conflict about it decides a claim it checks");
    }
    // Q2 checks A2, and the conflict decides A2: the goal ends disputed with its conflict.
    const { s } = withEvidence();
    const q2 = goalOf(s, "Q2");
    q2.attempts = 1;
    s.conflicts.push(conflictOf({ about: "Q2", critical: true, claim: "A2" }));
    applyJudgments(s, judgment("Q2", 2, 0, { outcome: "conflicting", verdicts: [{ claim_id: "A2", verdict: "unsettled" }], missing: ["which value holds"] }), [q2], 1, options, () => {});
    expect(q2.status).toBe("disputed");
  });
});

describe("new goals (section 20)", () => {
  const proposal = (text: string, need: "necessary" | "completing", prompted_by: string[]): RoundReply["proposals"][number] => ({
    text, template: "T1", need, object_id: "O9", new_object: "", new_object_quote: "", prompted_by, leads_to: ["Q5"], done_when: "What the sources report.", source_hints: [],
  });

  function withConflict(critical: boolean): EbdState {
    const { s } = withEvidence();
    s.conflicts.push(conflictOf({ critical }));
    return s;
  }

  it("makes no goal from a proposal that follows up a conflict", () => {
    const reply: RoundReply = { judgments: [], proposals: [proposal("Which index value for 2025 is the right one, 4% or 5%, in the official release?", "necessary", ["C1", "r1-b1-f1"])] };
    for (const [critical, why] of [[false, "it is not critical"], [true, "a critical conflict is followed up by its settle goal only"]] as const) {
      const log: string[] = [];
      expect(acceptProposals(withConflict(critical), reply, 1, options, (l) => log.push(l))).toEqual([]);
      expect(log[0]).toContain(`follows up the conflict C1; ${why}`);
    }
  });

  it(`keeps at most ${FOCUS_NECESSARY} new goals of a round necessary`, () => {
    const texts = [
      "How do leasing companies set monthly payments for new vehicles after import duties change?",
      "Which provinces publish dealer inventory counts, and how often are those counts refreshed?",
      "What role do currency hedging contracts play for importers of vehicles assembled abroad?",
    ];
    const reply: RoundReply = { judgments: [], proposals: texts.map((t) => proposal(t, "necessary", ["r1-b1-f1"])) };
    const { s } = withEvidence();
    const log: string[] = [];
    expect(acceptProposals(s, reply, 1, options, (l) => log.push(l)).map((g) => [g.need, g.level])).toEqual([["necessary", 2], ["necessary", 2], ["completing", 4]]);
    expect(log.join("\n")).toContain(`completing, because ${FOCUS_NECESSARY} new goals of this round are already necessary`);
  });
});

describe("a main part of the answer that no finding mentions (section 26)", () => {
  const LEASING = "How do leasing companies set monthly payments for new vehicles after import duties change?";
  const INVENTORY = "Which provinces publish dealer inventory counts, and how often are those counts refreshed?";
  const HEDGING = "What role do currency hedging contracts play for importers of vehicles assembled abroad?";
  const proposal = (text: string, need: "necessary" | "completing", prompted_by: string[], extra: Partial<RoundReply["proposals"][number]> = {}): RoundReply["proposals"][number] => ({
    text, template: "T1", need, object_id: "O9", new_object: "", new_object_quote: "", prompted_by, leads_to: ["Q5"], done_when: "What the sources report.", source_hints: [], ...extra,
  });
  const accept = (proposals: RoundReply["proposals"]) => {
    const { s } = withEvidence();
    const log: string[] = [];
    const added = acceptProposals(s, { judgments: [], proposals }, 1, options, (l) => log.push(l));
    return { s, added, log: log.join("\n") };
  };

  it("tells the analyst that such a part may be raised without a citation", () => {
    expect(ANALYST_FOCUS_SECTION).toContain(MAIN_PARTS_UNCITED);
    expect(analystSystem(true)).toContain("propose a necessary goal before you propose any detail. Cite the finding or gap that mentions it; when nothing mentions it, cite nothing.");
    expect(analystSystem(false)).toContain(MAIN_PARTS_UNCITED);
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

  it("still rejects a detail that cites nothing", () => {
    const detail = accept([proposal(LEASING, "completing", [])]);
    expect(detail.added).toEqual([]);
    expect(detail.log).toContain("only a necessary goal for a main part of the answer may cite nothing");
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

  it("warns about an empty citation only for a detail", () => {
    const { s } = withEvidence();
    const reply = (need: "necessary" | "completing") => ({ judgments: [], proposals: [proposal(LEASING, need, [])] });
    expect(checkRound(reply("necessary"), s, []).warnings).toEqual([]);
    expect(checkRound(reply("completing"), s, []).warnings).toHaveLength(1);
    expect(checkRound({ judgments: [], proposals: [proposal(LEASING, "necessary", ["r9-b9-f9"])] }, s, []).warnings[0]!.message).toContain("unknown: r9-b9-f9");
  });
});

describe("the writer's input (section 20)", () => {
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
    const guidance = buildGuidance(s);
    expect(guidance).toContain(`${READING_LABEL} ${s.analysis.restated_request}`);
    expect(guidance).toContain(CRITICAL_HEADING);
    expect(guidance).toContain("- Prices rose or fell. Give both sides, each with the source the notes cite for it (statcan.gc.ca, news.example.org), and say which one the report follows and why, or that the evidence does not decide it.");
    expect(guidance).toContain("- Second critical point. This was researched further, and the notes show which account holds and why.");
    expect(guidance.split("\n").filter((l) => /critical point|rose or fell|detail differs|Two rates|caused the rise/.test(l))).toHaveLength(MAX_CRITICAL_LINES);
    // The premise that holds gets no line; the contradicted one does, and its conflict (C7) needs no second line.
    expect(guidance).not.toContain("The evidence supports this");
    expect(guidance).toContain("The evidence contradicts this; say so plainly early in the report.");
    expect(guidance).not.toMatch(/What each part of the report must contain|only partly established|Where the sources disagree|were not pursued/);
    // A goal cancelled with the contradicted premise gets no line either: the premise line says what was contradicted.
    goalOf(s, "Q6").status = "moot";
    expect(buildGuidance(s)).not.toContain("were not pursued");
  });

  it("gives the reading of the question only when the question cannot be taken at its word", () => {
    const { s } = withEvidence();
    for (const [id, claim] of [["Q1", "A1"], ["Q2", "A2"], ["Q4", "A3"]] as const) Object.assign(goalOf(s, id), { status: "answered", settledRound: 1, verdicts: { [claim]: "supported" } });
    expect(buildGuidance(s)).not.toContain(READING_LABEL);
    // A premise without a verdict, or a term with several meanings, brings the reading in.
    goalOf(s, "Q4").verdicts = { A3: "unsettled" };
    expect(buildGuidance(s)).toContain(`${READING_LABEL} ${s.analysis.restated_request}`);
    // An unsettled premise is not to be presented as established; the report does not have to say that it is unsettled.
    expect(buildGuidance(s)).toContain("The evidence neither confirms nor contradicts this; do not present it as established.");
    goalOf(s, "Q4").verdicts = { A3: "supported" };
    s.analysis.rom.objects[3]!.readings = ["a tax on imports", "a price list"];
    expect(buildGuidance(s)).toContain(READING_LABEL);
  });

  it("gives an outline only for a request with several parts, and never a section for disagreements", () => {
    const { s } = withEvidence();
    s.conflicts.push(conflictOf({ critical: true }));
    expect(buildOutline(s)).toEqual(s.analysis.questions.filter((q) => q.route === "synthesis").map((q) => q.text));
    expect(buildOutline(s).join(" ")).not.toContain("disagree");
    s.analysis.questions = s.analysis.questions.filter((q) => q.id !== "Q8");
    expect(buildOutline(s)).toEqual([]);
    expect(buildSynthesis(s).outline).toBeUndefined();
  });

  it("reads records made without the mark: a conflict is critical when its settle goal is necessary", () => {
    const { s } = withEvidence();
    const settleGoal = (id: string, settles: string, need: Goal["need"]): Goal => ({ ...structuredClone(goalOf(s, "Q3")), id, settles, need });
    s.goals.push(settleGoal("Q90", "C1", "necessary"), settleGoal("Q91", "C2", "completing"));
    s.conflicts.push(conflictOf({ id: "C1", status: "open", settleGoal: "Q90" }), conflictOf({ id: "C2", status: "open", settleGoal: "Q91", about: "Q1" }));
    expect(s.conflicts.every((c) => c.critical === null)).toBe(true);
    expect(criticalForWriter(s).map((c) => c.id)).toEqual(["C1"]);
  });
});

// ---------------------------------------------------------------- the briefs of a follow-up round

describe("the order of a follow-up round (sections 25 and 29)", () => {
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
   * about Q2, and the analyst raises two necessary goals for parts of the answer. With `claim`, the
   * disagreement decides the claim Q2 checks: it gets the settle goal Q9, Q2 waits for it, and the two
   * new goals are Q10 and Q11. Without it the disagreement is only reported, and they are Q9 and Q10.
   */
  async function followUp(remaining: number, settled: string[], claim = "", given: Record<string, unknown>[] = proposals) {
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
    const step = await ebd.create({}).observe(prev, [result], { model, budget: { researchersTotal: 6, researchersUsed: 6 - remaining, researchersRemaining: remaining, toolCallsPerResearcher: 12 }, round: 2, runId: "t", today: E1.runDate });
    const state = step.state as EbdState;
    return { step, state, tags: step.decision.briefs.map((b) => b.tag) };
  }
  const others = ["Q3", "Q4", "Q5", "Q6"];

  it("reports a critical disagreement that decides no claim, and sends the researchers to the missing parts of the answer", async () => {
    const { step, state, tags } = await followUp(2, others);
    expect(state.goals.some((g) => g.settles)).toBe(false);
    expect(state.conflicts[0]).toMatchObject({ critical: true, status: "disputed", settleGoal: null });
    expect(state.goals.filter((g) => g.origin.type === "finding").map((g) => [g.id, g.need])).toEqual([["Q9", "necessary"], ["Q10", "necessary"]]);
    expect(tags).toEqual(["Q9", "Q10"]);
    expect(step.decision.stop).toBe(false);
  });

  it("keeps a settle goal in its place when a part of the answer waits behind it", async () => {
    // Q5 depends on Q2, Q2 waits for the settle goal, and Q5 has never been asked.
    const { state, tags } = await followUp(2, ["Q3"], "A2");
    expect(goalOf(state, "Q9")).toMatchObject({ settles: "C1", need: "necessary", status: "open", verifies: ["A2"] });
    expect(goalOf(state, "Q2")).toMatchObject({ status: "conflicting", waitingOn: "Q9" });
    expect(gatesAnswer(goalOf(state, "Q9"), state, options)).toBe(true);
    expect(tags).toContain("Q9");
  });

  it("lets a settle goal wait when a goal waits for it but no part of the answer is held up", async () => {
    // Q5 is answered. Q4 depends on Q2 too, but it checks a claim, and a premise check does not wait.
    const { step, state, tags } = await followUp(2, ["Q3", "Q5"], "A2");
    expect(goalOf(state, "Q2")).toMatchObject({ status: "conflicting", waitingOn: "Q9" });
    expect(gatesAnswer(goalOf(state, "Q9"), state, options)).toBe(false);
    expect(tags).not.toContain("Q9");
    expect(tags).toContain("Q4");
    expect(step.decision.rationale).toContain("Settling a disagreement waits (Q9)");
    // The disagreement is not dropped: the run is not complete while its settle goal is open.
    expect(step.decision.stop).toBe(false);
  });

  it("gives that settle goal a researcher of its own when one is left, after the parts of the answer", async () => {
    const { tags } = await followUp(6, ["Q3", "Q5"], "A2");
    expect(tags).toContain("Q9");
    expect(tags.at(-1)).toBe("Q9");
  });

  it("serves a part of the answer that no finding mentions (section 26)", async () => {
    const uncited = proposals.map((p) => ({ ...p, prompted_by: [] }));
    const { state, tags, step } = await followUp(2, others, "", uncited);
    expect(state.goals.filter((g) => g.origin.type === "uncovered").map((g) => [g.id, g.need, g.depth])).toEqual([["Q9", "necessary", 1], ["Q10", "necessary", 1]]);
    expect(tags).toEqual(["Q9", "Q10"]);
    expect(step.decision.stop).toBe(false);
  });
});

describe("a claim check shares a researcher (section 26)", () => {
  type Plan = (state: EbdState, ctx: unknown, lines: string[], progress: null) => { state: EbdState; decision: { briefs: ResearchBrief[] } };
  const planOf = (state: EbdState) => {
    const step = (ebd.create({}) as unknown as { plan: Plan }).plan(state, { budget: { researchersTotal: 6, researchersUsed: 0, researchersRemaining: 6, toolCallsPerResearcher: 12 }, round: 1, runId: "t", today: E1.runDate }, [], null);
    return { state: step.state, briefs: step.decision.briefs, tags: step.decision.briefs.map((b) => (b.tag ?? "").split(",")), log: step.state.step.events.join("\n") };
  };
  const group = (s: EbdState, ...ids: string[]) => ({ key: goalOf(s, ids[0]!).objectIds[0]!, goals: ids.map((id) => goalOf(s, id)) });
  /** A state with one main part of the plan, with this many key questions. */
  const withPart = (questions: number) => {
    const s = stateOf();
    const id = nextGoalId(s);
    const event: MapEvent = {
      id: "E1",
      name: "Passing the cost on",
      goalId: id,
      parts: Array.from({ length: questions }, (_, i) => ({ id: `M${i + 1}`, text: `How is the cost passed on, point ${i + 1}?`, kind: "economic" as const, origin: "assumed" as const, status: "assumed" as const, evidence: [], correction: null, replaces: null, by: null, round: null })),
    };
    s.map = { subject: "2025 US tariffs and new-car prices in Canada", objectIds: ["O4"], events: [event] };
    s.goals.push(newGoal({ id, text: "Establish how importers and dealers pass the cost of the tariffs on.", objectIds: ["O4"], template: "T1", guideline: "G1", need: "necessary", doneWhen: "Covers the key questions.", sourceHints: [], origin: { type: "assumed", event: "E1" }, depth: 0, leadsTo: ["Q7"], createdRound: 1 }));
    return { s, id };
  };

  it("names the goals that only check a claim of the question", () => {
    const s = stateOf();
    expect(s.goals.filter(isClaimCheck).map((g) => g.id)).toEqual(["Q1", "Q2", "Q4"]);
    expect(isClaimCheck({ ...goalOf(s, "Q1"), settles: "C1" })).toBe(false);
  });

  it("puts a check into the brief about its own object, else into the one that asks least, and first", () => {
    const s = stateOf();
    // Q4 and Q6 are about O5; no brief is about O4, the object of Q1.
    const out = shareChecks([group(s, "Q3", "Q5"), group(s, "Q5"), group(s, "Q6")], [goalOf(s, "Q4"), goalOf(s, "Q1")], s)!;
    expect(out.map((g) => g.goals.map((x) => x.id))).toEqual([["Q3", "Q5"], ["Q1", "Q5"], ["Q4", "Q6"]]);
  });

  it("leaves a check its own researcher when it fits nowhere", () => {
    const s = stateOf();
    // A brief carries one check: two checks do not fit into one brief.
    expect(shareChecks([group(s, "Q3")], [goalOf(s, "Q1"), goalOf(s, "Q2")], s)).toBeNull();
    // A check joins only a brief with a necessary goal.
    expect(shareChecks([{ key: "O9", goals: [{ ...goalOf(s, "Q3"), need: "completing" }] }], [goalOf(s, "Q1")], s)).toBeNull();
    // The example has three claims to check and one other goal ready in round 1, and no plan of main parts.
    expect(planOf(stateOf()).log).toContain("keep a researcher of their own");
  });

  it("never keeps a main part from being asked key question by key question", () => {
    // Five key questions and the check make six.
    const five = withPart(5);
    const joined = shareChecks([group(five.s, five.id)], [goalOf(five.s, "Q1")], five.s)!;
    expect(joined[0]!.goals.map((g) => g.id)).toEqual(["Q1", five.id]);
    expect(askedByPart(joined[0]!, five.s).has(five.id)).toBe(true);
    // With a sixth key question the check would make seven, and the part would be asked as one question.
    const six = withPart(6);
    expect(shareChecks([group(six.s, six.id)], [goalOf(six.s, "Q1")], six.s)).toBeNull();
  });
});
