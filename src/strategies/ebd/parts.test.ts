/**
 * A main part asked by its key questions (design sections 21 and 28), without network: the brief asks
 * each key question of a main part as a key question of its own, the notes sections map back to the
 * part's goal, and a brief never asks more than six key questions.
 */
import { describe, expect, it } from "vitest";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { MAX_PART_QUESTIONS, PLANNED_PARTS_INSTRUCTION, PLAN_QUESTIONS_INSTRUCTION, askedByPart, askedParts, briefFor, fitBrief, questionCount, spread } from "./briefs.js";
import { EXAMPLES } from "./fixtures.js";
import { goalsFromAnalysis, newGoal, nextGoalId, treeMetrics } from "./goals.js";
import { doneWhenOf, syncGoal } from "./map.js";
import { readResult } from "./rounds/evidence.js";
import type { EbdState, Goal, MapEvent } from "./state.js";
import { buildMaterial } from "./synthesis.js";

const E2 = EXAMPLES[1]!;

/** Four main parts of an answer to "Which electric car is best for cold winters these days?". */
const PARTS: { name: string; need: Goal["need"]; objective: string; questions: string[] }[] = [
  {
    name: "Buying",
    need: "necessary",
    objective: "Establish what choosing and buying an electric car for cold winters involves in 2026.",
    questions: ["Which electric cars on sale in 2026 are sold with a heat pump?", "What do electric cars with a winter package cost?", "Which purchase incentives apply to electric cars in cold regions?", "How long are the waiting times for electric cars with all-wheel drive?"],
  },
  {
    name: "Driving in the cold",
    need: "necessary",
    objective: "Establish how electric cars drive at low temperatures.",
    questions: ["How much driving range do electric cars lose at low temperatures?", "How much energy does cabin heating use in an electric car in winter?", "How do electric cars handle on snow and ice?", "What do independent cold-weather tests of electric cars show?", "What do owners of electric cars in cold regions report?"],
  },
  {
    name: "Charging in winter",
    need: "necessary",
    objective: "Establish how charging an electric car works in winter.",
    questions: ["How much slower is fast charging of an electric car in the cold?", "Which electric cars precondition the battery before charging?", "How reliable are public chargers in winter?", "What does home charging of an electric car cost in winter?"],
  },
  {
    name: "Owning over the years",
    need: "completing",
    objective: "Establish what owning an electric car in a cold climate involves over the years.",
    questions: ["How does a battery age in a cold climate?", "What does the warranty of an electric car cover in cold regions?", "How well do electric cars resist road salt?", "What is the resale value of electric cars in cold regions?"],
  },
];

/** The example's analysis (goals Q1 to Q3) with a plan of four main parts: Q4 Buying (4 key questions), Q5 Driving in the cold (5), Q6 Charging in winter (4), Q7 Owning over the years (4, completing). */
function planned(): EbdState {
  const analysis = structuredClone(E2.analysis);
  const goals = goalsFromAnalysis(analysis);
  const state: EbdState = {
    question: E2.request,
    today: E2.runDate,
    init: { mode: "environment", accepted: true, fallback: false, attempts: 1, stopReason: "accepted" },
    analysis,
    goals,
    objectsFound: [],
    map: { subject: "electric cars for cold winters", objectIds: ["O2"], events: [] },
    conflicts: [],
    evidence: [],
    results: [],
    roundsObserved: 0,
    stop: null,
    tree: treeMetrics(goals),
    step: { phase: "init", round: 0, calls: [], events: [] },
    problems: [],
  };
  let m = 0;
  PARTS.forEach((p, i) => {
    const event: MapEvent = {
      id: `E${i + 1}`,
      name: p.name,
      goalId: nextGoalId(state),
      parts: p.questions.map((text) => ({ id: `M${++m}`, text, kind: "economic" as const, origin: "assumed" as const, status: "assumed" as const, evidence: [], correction: null, replaces: null, by: null, round: null })),
    };
    const goal = newGoal({ id: event.goalId, text: p.objective, objectIds: ["O2"], template: "T1", guideline: "G1", need: p.need, doneWhen: doneWhenOf(event), sourceHints: [], origin: { type: "assumed", event: event.id }, depth: 0, leadsTo: [], createdRound: 1 });
    syncGoal(goal, event);
    state.map!.events.push(event);
    state.goals.push(goal);
  });
  return state;
}

const goal = (state: EbdState, id: string): Goal => state.goals.find((g) => g.id === id)!;
const asked = (id: string, i: number) => `[${id}] ${PARTS[i]!.questions.join(`|[${id}] `)}`.split("|");

function resultOf(brief: ReturnType<typeof briefFor>, notes: string): ResearchResult {
  const full: ResearchBrief = { id: "r1-b1", round: 1, objective: brief.objective, keyQuestions: brief.keyQuestions, constraints: [], sourceHints: [], tag: brief.tag };
  return { brief: full, status: "ok", notes, sources: [], queries: [], usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [] };
}

describe("a main part asked by its key questions", () => {
  it("has the plan's goals where the tests expect them", () => {
    const state = planned();
    expect(state.map!.events.map((e) => [e.goalId, e.name, e.parts.length])).toEqual([["Q4", "Buying", 4], ["Q5", "Driving in the cold", 5], ["Q6", "Charging in winter", 4], ["Q7", "Owning over the years", 4]]);
    expect(["Q4", "Q5", "Q6", "Q7"].map((id) => goal(state, id).need)).toEqual(["necessary", "necessary", "necessary", "completing"]);
  });

  it("asks each key question of the part as written, under the goal's ID", () => {
    const state = planned();
    const brief = briefFor({ key: "O2", goals: [goal(state, "Q5")] }, 0, state);
    expect(brief.keyQuestions).toEqual(asked("Q5", 1));
    expect(brief.keyQuestions).toHaveLength(5);
    // The part's objective is the brief's objective and is repeated in the instructions; the key questions are expectations.
    expect(brief.objective).toBe(goal(state, "Q5").text);
    expect(brief.instructions).toBe(`For [Q5], the objective is: ${goal(state, "Q5").text} ${PLAN_QUESTIONS_INSTRUCTION}`);
    expect(brief.instructions).toContain("expectations, not facts");
    expect(brief.tag).toBe("Q5");
  });

  it("asks a goal by its key questions only while the brief stays within the limit, a necessary goal first", () => {
    const state = planned();
    // Q6 (necessary, 4 key questions) and Q7 (completing, 4) share a researcher: 4 + 1 key questions.
    const shared = { key: "O2", goals: [goal(state, "Q6"), goal(state, "Q7")] };
    expect([...askedByPart(shared, state)]).toEqual(["Q6"]);
    const brief = briefFor(shared, 0, state);
    expect(brief.keyQuestions).toEqual([...asked("Q6", 2), `[Q7] ${goal(state, "Q7").text}`]);
    expect(brief.instructions).toContain(`For [Q6], the objective is: ${goal(state, "Q6").text}`);
    // The part asked as one question has its key questions listed in the instructions.
    expect(brief.instructions).toContain(`For [Q7], the plan expects an answer to cover these questions: ${PARTS[3]!.questions.join(" ")} ${PLANNED_PARTS_INSTRUCTION}`);
    // Three parts in one brief: only the first fits (4 + 1 + 1).
    const three = { key: "O2", goals: [goal(state, "Q4"), goal(state, "Q5"), goal(state, "Q6")] };
    expect([...askedByPart(three, state)]).toEqual(["Q4"]);
    expect(briefFor(three, 0, state).keyQuestions).toHaveLength(MAX_PART_QUESTIONS);
    // A goal that is not a main part of the plan keeps its one question.
    const mixed = { key: "O2", goals: [goal(state, "Q2"), goal(state, "Q5")] };
    expect([...askedByPart(mixed, state)]).toEqual(["Q5"]);
    expect(briefFor(mixed, 0, state).keyQuestions[0]).toBe(`[Q2] ${goal(state, "Q2").text}`);
  });

  it("asks only the key questions still open on a second attempt, and none that the evidence refuted", () => {
    const state = planned();
    const q5 = goal(state, "Q5");
    const parts = state.map!.events[1]!.parts;
    Object.assign(parts[0]!, { status: "confirmed", evidence: ["r1-b1-f1"] });
    Object.assign(parts[1]!, { status: "refuted", evidence: ["r1-b1-f2"] });
    q5.attempts = 1;
    expect(askedParts(state, q5).map((p) => p.id)).toEqual(["M7", "M8", "M9"]);
    expect(briefFor({ key: "O2", goals: [q5] }, 0, state).keyQuestions).toEqual(asked("Q5", 1).slice(2));
  });

  it("maps every section to its goal, by the ID in the heading or by key-question order", () => {
    const state = planned();
    const brief = briefFor({ key: "O2", goals: [goal(state, "Q6"), goal(state, "Q7")] }, 0, state);
    const section = (title: string, i: number) => [`## ${title}`, "### Takeaway", `Takeaway ${i}.`, "### Cited Findings", `- Finding ${i}. — [S](https://host${i}.example/x)`, "### Gaps", `- Gap ${i}.`].join("\n");
    // The researcher copies the key questions as headings.
    const copied = readResult(resultOf(brief, brief.keyQuestions.map(section).join("\n\n")));
    expect(copied.record.sections.map((s) => [s.goalIds.join(), s.mappedBy])).toEqual([["Q6", "id"], ["Q6", "id"], ["Q6", "id"], ["Q6", "id"], ["Q7", "id"]]);
    expect(copied.evidence.filter((e) => e.kind === "finding").map((e) => e.goalIds.join())).toEqual(["Q6", "Q6", "Q6", "Q6", "Q7"]);
    // The researcher drops the IDs but keeps one section per key question.
    const bare = readResult(resultOf(brief, brief.keyQuestions.map((q, i) => section(q.replace(/^\[Q\d+\]\s*/, ""), i)).join("\n\n")));
    expect(bare.record.sections.map((s) => [s.goalIds.join(), s.mappedBy])).toEqual([["Q6", "order"], ["Q6", "order"], ["Q6", "order"], ["Q6", "order"], ["Q7", "order"]]);
    // Fewer sections than key questions and no IDs: the brief's goals.
    const merged = readResult(resultOf(brief, [section("Charging", 0), section("Owning", 1), section("Other", 2)].join("\n\n")));
    expect(merged.record.sections.every((s) => s.mappedBy === "brief" && s.goalIds.join() === "Q6,Q7")).toBe(true);
  });

  it("in a later round gives each necessary goal a researcher before a brief of completing goals has one to itself", () => {
    const g = (id: string, need: Goal["need"], key: string) => ({ ...goal(planned(), "Q5"), id, need, objectIds: [key] });
    // Three necessary goals on one object, and two completing ones on objects of their own (a plan of 2026-11-18).
    const groups = [
      { key: "A", goals: [g("Q4", "necessary", "A"), g("Q5", "necessary", "A"), g("Q6", "necessary", "A")] },
      { key: "A", goals: [g("Q1", "completing", "A"), g("Q7", "completing", "A")] },
      { key: "B", goals: [g("Q2", "completing", "B")] },
    ];
    const ids = (out: typeof groups) => out.map((x) => x.goals.map((y) => y.id));
    const regroup = (within: number) => ({ within, load: (x: (typeof groups)[number]) => x.goals.length });
    // The smaller brief of completing goals joins the other one, and each necessary goal has a researcher.
    expect(ids(spread(groups, 4, 6, regroup(3)))).toEqual([["Q4"], ["Q1", "Q7", "Q2"], ["Q6"], ["Q5"]]);
    // When the other brief of completing goals is full, the goal rides with a necessary goal, never with the brief being split.
    expect(ids(spread(groups, 4, 6, regroup(2)))).toEqual([["Q4"], ["Q1", "Q7"], ["Q6", "Q2"], ["Q5"]]);
    // One brief of completing goals: it rides with the brief that asks the fewest key questions.
    const one = [{ key: "V", goals: [g("Q1", "necessary", "V")] }, { key: "A", goals: [g("Q4", "necessary", "A"), g("Q5", "necessary", "A")] }, { key: "A", goals: [g("Q7", "completing", "A")] }, { key: "A", goals: [g("Q6", "necessary", "A")] }];
    const load = (x: (typeof groups)[number]) => (x.goals[0]!.id === "Q6" ? 5 : x.goals.length);
    expect(ids(spread(one, 4, 6, { within: 3, load }))).toEqual([["Q1", "Q7"], ["Q4"], ["Q6"], ["Q5"]]);
    // Nothing moves when no brief holds two necessary goals, or when no brief has room.
    const single = [{ key: "A", goals: [g("Q4", "necessary", "A")] }, { key: "A", goals: [g("Q1", "completing", "A")] }, { key: "B", goals: [g("Q2", "completing", "B")] }];
    expect(ids(spread(single, 3, 6, regroup(3)))).toEqual([["Q4"], ["Q1"], ["Q2"]]);
    expect(ids(spread(one, 4, 6, regroup(1)))).toEqual(ids(one));
  });

  it("asks a completing part by its key questions only in a brief without a necessary goal", () => {
    const state = planned();
    // Q7 (completing, 4 key questions) rides with Q2 (necessary, not a main part): it keeps one key question.
    const riding = { key: "O2", goals: [goal(state, "Q2"), goal(state, "Q7")] };
    expect(goal(state, "Q2").need).toBe("necessary");
    expect(askedByPart(riding, state).size).toBe(0);
    expect(questionCount(riding, state)).toBe(2);
    // On its own it is asked by its key questions.
    const own = { key: "O2", goals: [goal(state, "Q7")] };
    expect([...askedByPart(own, state)]).toEqual(["Q7"]);
    expect(questionCount(own, state)).toBe(4);
  });

  it("leaves a completing goal out of a brief when it keeps a necessary part from being asked by its key questions", () => {
    const state = planned();
    const ids = (goals: Goal[]) => goals.map((x) => x.id);
    const q1 = goal(state, "Q1");
    q1.need = "completing";
    // Q5 (necessary, 5 key questions) with the completing part Q7 and the completing goal Q1: 5 + 1 + 1 key questions are one too many.
    const crowded = { key: "O2", goals: [goal(state, "Q5"), goal(state, "Q7"), q1] };
    expect(askedByPart(crowded, state).size).toBe(0);
    const fitted = fitBrief(crowded, state);
    expect(ids(fitted.group.goals)).toEqual(["Q5", "Q7"]);
    expect(ids(fitted.left)).toEqual(["Q1"]);
    expect(briefFor(fitted.group, 0, state).keyQuestions).toHaveLength(MAX_PART_QUESTIONS);
    // Nothing is left out when the necessary part is asked by its key questions anyway, or when leaving goals out would not help.
    const roomy = { key: "O2", goals: [goal(state, "Q6"), goal(state, "Q7")] };
    expect(fitBrief(roomy, state)).toEqual({ group: roomy, left: [] });
    const two = { key: "O2", goals: [goal(state, "Q2"), goal(state, "Q7")] };
    expect(fitBrief(two, state).left).toEqual([]);
    const completingOnly = { key: "O2", goals: [goal(state, "Q7"), q1] };
    expect(fitBrief(completingOnly, state).left).toEqual([]);
  });

  it("hands the writer every section under its goal", () => {
    const state = planned();
    const brief = briefFor({ key: "O2", goals: [goal(state, "Q6")] }, 0, state);
    const notes = brief.keyQuestions.map((q, i) => [`## ${q}`, "### Takeaway", `Takeaway ${i}.`, "### Cited Findings", `- Finding ${i}. — [S](https://host${i}.example/x)`].join("\n")).join("\n\n");
    const { record, evidence } = readResult(resultOf(brief, notes));
    state.results.push(record);
    state.evidence.push(...evidence);
    const material = buildMaterial(state);
    expect(material).toHaveLength(1);
    expect(material[0]!.label).toBe(goal(state, "Q6").text);
    for (const q of brief.keyQuestions) expect(material[0]!.notes).toContain(`## ${q}`);
    expect(material[0]!.notes.match(/### Takeaway/g)).toHaveLength(4);
  });
});
