/**
 * Part questions (design section 21) without network: the brief of an event goal asks one key
 * question per planned part, the notes sections map back to the goal, and with the option off the
 * brief is the earlier one.
 */
import { describe, expect, it } from "vitest";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { MAX_PART_QUESTIONS, PART_QUESTIONS_INSTRUCTION, PLANNED_PARTS_INSTRUCTION, askedByPart, askedParts, briefFor, fitBrief, questionCount, spread } from "./briefs.js";
import { EXAMPLE_COMPLETE, EXAMPLE_NOW, EXTENSION_SYSTEM, PLANNED_COMPLETE, PLANNED_NOW, RELEVANCE_COMPLETE, RELEVANCE_NOW, applyExtension, checkExtension, extensionSystem, type ExtensionReply } from "./extension.js";
import { goalsFromAnalysis, treeMetrics } from "./goals.js";
import { parseOptions } from "./options.js";
import { EXAMPLES } from "./request/examples.js";
import { readResult } from "./rounds/evidence.js";
import type { EbdState, Goal } from "./state.js";
import { buildMaterial } from "./synthesis.js";

const E2 = EXAMPLES[1]!;
const ON = { partQuestions: true };

/** The worked example of the extension prompt: events Q4 Buying (4 parts), Q5 Driving in the cold (5), Q6 Charging in winter (4), Q7 Owning over the years (4, completing). */
function extended(): EbdState {
  const analysis = structuredClone(E2.analysis);
  const goals = goalsFromAnalysis(analysis);
  const state: EbdState = {
    question: E2.request,
    today: E2.runDate,
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
  const json = /^(\{"subject".*\})$/m.exec(EXTENSION_SYSTEM)?.[1];
  if (!json) throw new Error("the worked example's extension was not found in the prompt");
  applyExtension(state, JSON.parse(json) as ExtensionReply, () => {});
  return state;
}

const goal = (state: EbdState, id: string): Goal => state.goals.find((g) => g.id === id)!;

function resultOf(brief: ReturnType<typeof briefFor>, notes: string): ResearchResult {
  const full: ResearchBrief = { id: "r1-b1", round: 1, objective: brief.objective, keyQuestions: brief.keyQuestions, constraints: [], sourceHints: [], tag: brief.tag };
  return { brief: full, status: "ok", notes, sources: [], queries: [], usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [] };
}

describe("part questions", () => {
  it("is off by default, and the brief is then the earlier one", () => {
    expect(parseOptions({}).partQuestions).toBe(false);
    const state = extended();
    const group = { key: "O2", goals: [goal(state, "Q5")] };
    const before = briefFor(group, 0, state);
    expect(briefFor(group, 0, state, { partQuestions: false })).toEqual(before);
    expect(before.keyQuestions).toEqual([`[Q5] ${goal(state, "Q5").text}`]);
    expect(before.instructions).toContain(PLANNED_PARTS_INSTRUCTION);
    expect(askedByPart(group, state, {}).size).toBe(0);
  });

  it("asks one key question per planned part of the step, under the goal's ID", () => {
    const state = extended();
    const brief = briefFor({ key: "O2", goals: [goal(state, "Q5")] }, 0, state, ON);
    expect(brief.keyQuestions).toEqual([
      "[Q5] Driving in the cold: driving range lost at low temperatures",
      "[Q5] Driving in the cold: cabin heating system and its energy use",
      "[Q5] Driving in the cold: traction and handling on snow and ice",
      "[Q5] Driving in the cold: results of independent cold-weather tests",
      "[Q5] Driving in the cold: what owners in cold regions report",
    ]);
    // The step's own question stays the objective and is repeated in the instructions; the parts are still expectations.
    expect(brief.objective).toBe(goal(state, "Q5").text);
    expect(brief.instructions).toBe(`For [Q5], the question is: ${goal(state, "Q5").text} ${PART_QUESTIONS_INSTRUCTION}`);
    expect(brief.instructions).toContain("expectations, not facts");
    expect(brief.instructions).not.toContain("look for what the sources report on");
    expect(brief.tag).toBe("Q5");
  });

  it("asks a goal by part only while the brief stays within the limit, a necessary goal first", () => {
    const state = extended();
    // Q6 (necessary, 4 parts) and Q7 (completing, 4 parts) share a researcher: 4 + 1 key questions.
    const shared = { key: "O2", goals: [goal(state, "Q6"), goal(state, "Q7")] };
    expect([...askedByPart(shared, state, ON)]).toEqual(["Q6"]);
    const brief = briefFor(shared, 0, state, ON);
    expect(brief.keyQuestions).toHaveLength(5);
    expect(brief.keyQuestions.slice(0, 4).every((q) => q.startsWith("[Q6] Charging in winter: "))).toBe(true);
    expect(brief.keyQuestions[4]).toBe(`[Q7] ${goal(state, "Q7").text}`);
    expect(brief.instructions).toContain(`For [Q6], the question is: ${goal(state, "Q6").text}`);
    expect(brief.instructions).toContain("For [Q7], look for what the sources report on: battery ageing in cold climates;");
    // Three events in one brief: only the first fits (4 + 1 + 1).
    const three = { key: "O2", goals: [goal(state, "Q4"), goal(state, "Q5"), goal(state, "Q6")] };
    expect([...askedByPart(three, state, ON)]).toEqual(["Q4"]);
    expect(briefFor(three, 0, state, ON).keyQuestions).toHaveLength(MAX_PART_QUESTIONS);
    // A goal that is not a life-cycle step keeps its one question.
    const mixed = { key: "O2", goals: [goal(state, "Q2"), goal(state, "Q5")] };
    expect([...askedByPart(mixed, state, ON)]).toEqual(["Q5"]);
    expect(briefFor(mixed, 0, state, ON).keyQuestions[0]).toBe(`[Q2] ${goal(state, "Q2").text}`);
  });

  it("asks only the parts still open on a second attempt, and none that the evidence refuted", () => {
    const state = extended();
    const q5 = goal(state, "Q5");
    const parts = state.map!.events[1]!.parts;
    Object.assign(parts[0]!, { status: "confirmed", evidence: ["r1-b1-f1"] });
    Object.assign(parts[1]!, { status: "refuted", evidence: ["r1-b1-f2"] });
    q5.attempts = 1;
    expect(askedParts(state, q5).map((p) => p.id)).toEqual(["M7", "M8", "M9"]);
    expect(briefFor({ key: "O2", goals: [q5] }, 0, state, ON).keyQuestions).toEqual([
      "[Q5] Driving in the cold: traction and handling on snow and ice",
      "[Q5] Driving in the cold: results of independent cold-weather tests",
      "[Q5] Driving in the cold: what owners in cold regions report",
    ]);
  });

  it("maps every part section to its goal, by the ID in the heading or by key-question order", () => {
    const state = extended();
    const brief = briefFor({ key: "O2", goals: [goal(state, "Q6"), goal(state, "Q7")] }, 0, state, ON);
    const section = (title: string, i: number) => [`## ${title}`, "### Takeaway", `Takeaway ${i}.`, "### Cited Findings", `- Finding ${i}. — [S](https://host${i}.example/x)`, "### Gaps", `- Gap ${i}.`].join("\n");
    // The researcher copies the key questions as headings.
    const copied = readResult(resultOf(brief, brief.keyQuestions.map(section).join("\n\n")));
    expect(copied.record.sections.map((s) => [s.goalIds.join(), s.mappedBy])).toEqual([["Q6", "id"], ["Q6", "id"], ["Q6", "id"], ["Q6", "id"], ["Q7", "id"]]);
    expect(copied.evidence.filter((e) => e.kind === "finding").map((e) => e.goalIds.join())).toEqual(["Q6", "Q6", "Q6", "Q6", "Q7"]);
    // The researcher drops the IDs but keeps one section per key question.
    const bare = readResult(resultOf(brief, brief.keyQuestions.map((q, i) => section(q.replace(/^\[Q\d+\]\s*/, ""), i)).join("\n\n")));
    expect(bare.record.sections.map((s) => [s.goalIds.join(), s.mappedBy])).toEqual([["Q6", "order"], ["Q6", "order"], ["Q6", "order"], ["Q6", "order"], ["Q7", "order"]]);
    // Fewer sections than key questions and no IDs: the brief's goals, as before.
    const merged = readResult(resultOf(brief, [section("Charging", 0), section("Owning", 1), section("Other", 2)].join("\n\n")));
    expect(merged.record.sections.every((s) => s.mappedBy === "brief" && s.goalIds.join() === "Q6,Q7")).toBe(true);
  });

  it("gives each necessary goal a researcher before a brief of completing goals has one to itself", () => {
    const g = (id: string, need: Goal["need"], key: string) => ({ ...goal(extended(), "Q5"), id, need, objectIds: [key] });
    // Three necessary steps on one object, and two completing questions on objects of their own (a plan of 2026-11-18).
    const groups = [
      { key: "A", goals: [g("Q4", "necessary", "A"), g("Q5", "necessary", "A"), g("Q6", "necessary", "A")] },
      { key: "A", goals: [g("Q1", "completing", "A"), g("Q7", "completing", "A")] },
      { key: "B", goals: [g("Q2", "completing", "B")] },
    ];
    const ids = (out: typeof groups) => out.map((x) => x.goals.map((y) => y.id));
    const regroup = (within: number) => ({ within, load: (x: (typeof groups)[number]) => x.goals.length });
    // Without the option: one split fills the fourth slot, and two necessary steps share a researcher.
    expect(ids(spread(groups, 4, 6))).toEqual([["Q4", "Q5"], ["Q1", "Q7"], ["Q2"], ["Q6"]]);
    // With it: the smaller brief of completing goals joins the other one, and each necessary step has a researcher.
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

  it("asks a completing goal by part only in a brief without a necessary goal", () => {
    const state = extended();
    // Q7 (completing, 4 parts) rides with the request goal Q2 (necessary, no parts): it keeps one key question.
    const riding = { key: "O2", goals: [goal(state, "Q2"), goal(state, "Q7")] };
    expect(askedByPart(riding, state, ON).size).toBe(0);
    expect(questionCount(riding, state, ON)).toBe(2);
    // On its own it is asked by part.
    const own = { key: "O2", goals: [goal(state, "Q7")] };
    expect([...askedByPart(own, state, ON)]).toEqual(["Q7"]);
    expect(questionCount(own, state, ON)).toBe(4);
    expect(questionCount(own, state, {})).toBe(1);
  });

  it("leaves a completing goal for a later round when it keeps a necessary goal from being asked by part", () => {
    const state = extended();
    const ids = (goals: Goal[]) => goals.map((x) => x.id);
    const q1 = goal(state, "Q1");
    // Q5 (necessary, 5 parts) with the completing step Q7 and the replaced overview Q1: 5 + 1 + 1 key questions are one too many.
    const crowded = { key: "O2", goals: [goal(state, "Q5"), goal(state, "Q7"), q1] };
    expect(q1.need).toBe("completing");
    expect(askedByPart(crowded, state, ON).size).toBe(0);
    const fitted = fitBrief(crowded, state, ON);
    expect(ids(fitted.group.goals)).toEqual(["Q5", "Q7"]);
    expect(ids(fitted.left)).toEqual(["Q1"]);
    expect(briefFor(fitted.group, 0, state, ON).keyQuestions).toHaveLength(MAX_PART_QUESTIONS);
    // Nothing is left when the necessary goal is asked by part anyway, when leaving goals would not help, or without the option.
    const roomy = { key: "O2", goals: [goal(state, "Q6"), goal(state, "Q7")] };
    expect(fitBrief(roomy, state, ON)).toEqual({ group: roomy, left: [] });
    const two = { key: "O2", goals: [goal(state, "Q2"), goal(state, "Q7")] };
    expect(fitBrief(two, state, ON).left).toEqual([]);
    expect(fitBrief(crowded, state, {}).left).toEqual([]);
    const completingOnly = { key: "O2", goals: [goal(state, "Q7"), q1] };
    expect(fitBrief(completingOnly, state, ON).left).toEqual([]);
  });

  it("hands the writer every part section under its goal", () => {
    const state = extended();
    const brief = briefFor({ key: "O2", goals: [goal(state, "Q6")] }, 0, state, ON);
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

describe("the complete map variant of the extension prompt (section 22)", () => {
  it("is off by default and leaves the accepted prompt untouched", () => {
    expect(parseOptions({}).completeMap).toBe(false);
    expect(extensionSystem()).toBe(EXTENSION_SYSTEM);
    expect(extensionSystem(false)).toBe(EXTENSION_SYSTEM);
  });

  it("rewords exactly three passages of the accepted prompt and the example's replaced questions", () => {
    for (const now of [RELEVANCE_NOW, PLANNED_NOW, EXAMPLE_NOW, '"replaces":["Q1"]}']) expect(EXTENSION_SYSTEM.split(now)).toHaveLength(2);
    const variant = extensionSystem(true);
    for (const now of [RELEVANCE_NOW, PLANNED_NOW, EXAMPLE_NOW]) expect(variant).not.toContain(now);
    for (const proposed of [RELEVANCE_COMPLETE, PLANNED_COMPLETE, EXAMPLE_COMPLETE, '"replaces":["Q1","Q2"]}']) expect(variant).toContain(proposed);
    // Everything else is the accepted text.
    const restored = variant.replace(RELEVANCE_COMPLETE, RELEVANCE_NOW).replace(PLANNED_COMPLETE, PLANNED_NOW).replace(EXAMPLE_COMPLETE, EXAMPLE_NOW).replace('"replaces":["Q1","Q2"]}', '"replaces":["Q1"]}');
    expect(restored).toBe(EXTENSION_SYSTEM);
  });

  it("accepts the variant's worked example, in which the events replace both planned questions", () => {
    const state = extended();
    const json = /^(\{"subject".*\})$/m.exec(extensionSystem(true))?.[1];
    const reply = JSON.parse(json!) as ExtensionReply;
    expect(reply.replaces).toEqual(["Q1", "Q2"]);
    const checked = checkExtension(reply, { question: state.question, analysis: state.analysis });
    expect(checked.errors).toEqual([]);
    expect(checked.warnings).toEqual([]);
    // Applied to a fresh state: both planned questions become completing overviews.
    const fresh = extended();
    fresh.goals = goalsFromAnalysis(fresh.analysis);
    fresh.map = null;
    applyExtension(fresh, reply, () => {});
    expect(Object.keys(fresh.map!.replaced)).toEqual(["Q1", "Q2"]);
    expect(fresh.goals.filter((g) => g.origin.type === "request").map((g) => g.need)).toEqual(["completing", "completing"]);
  });
});
