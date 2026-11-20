/**
 * The premise sort (design section 27), without network: the checks of the sorter's reply, what a
 * claim taken as given changes in the plan, in the conflict checker's input and in the writer's
 * input, and the sort inside init.
 */
import { describe, expect, it } from "vitest";
import { AIMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { VERIFY_INSTRUCTION, isClaimCheck, shareRiders, spread } from "./briefs.js";
import { applyExtension, isSuperseded, type ExtensionReply } from "./extension.js";
import { goalsFromAnalysis, isComplete, refutedObjects, treeMetrics } from "./goals.js";
import ebd from "./index.js";
import { PREMISE_SYSTEM, PREMISE_TOOL, applyGiven, checkPremises, givenClaims, premiseMessage, recordSort, validPremises, type PremiseReply } from "./premises.js";
import { EXAMPLES } from "./request/examples.js";
import { CONFLICT_GIVEN_SECTION, CONFLICT_SYSTEM, GIVEN_MARK, conflictMessage, conflictSystem } from "./rounds/conflicts.js";
import type { EbdState, Goal } from "./state.js";
import { READING_LABEL, buildGuidance } from "./synthesis.js";

const E1 = EXAMPLES[0]!;
const EXTENSION: ExtensionReply = {
  subject: "2025 US tariffs and new-car prices in Canada",
  subject_object_ids: ["O4"],
  events: [
    { name: "Passing the cost on", need: "necessary", question: "How do importers and dealers pass the cost of the 2025 US tariffs on to buyers of new cars in Canada?", parts: [{ text: "importer and dealer margins", kind: "economic" }, { text: "price lists of the makers", kind: "built_digital" }], source_hints: [], feeds: ["Q7"] },
    { name: "Buyers' response", need: "necessary", question: "How did buyers of new cars in Canada respond to price changes after the 2025 US tariffs?", parts: [{ text: "sales volumes", kind: "economic" }, { text: "shift to used cars", kind: "social" }], source_hints: [], feeds: ["Q7"] },
  ],
  replaces: ["Q6"],
};

function stateOf(map = false): EbdState {
  const analysis = structuredClone(E1.analysis);
  const goals = goalsFromAnalysis(analysis);
  const s: EbdState = {
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
  if (map) applyExtension(s, EXTENSION, () => {});
  return s;
}
const goalOf = (s: EbdState, id: string) => s.goals.find((g) => g.id === id)!;
const sort = (...given: string[]): PremiseReply => ({ claims: E1.analysis.assumptions.map((x) => ({ id: x.id, verdict: given.includes(x.id) ? "given" : "check", reason: "why" })) });
/** A state in which the claims named are taken as given and the plan has been adjusted. */
function sorted(given: string[], map = false): { s: EbdState; log: string[]; freed: string[] } {
  const s = stateOf(map);
  const log: string[] = [];
  recordSort(s, sort(...given), (l) => log.push(l));
  const freed = applyGiven(s, (l) => log.push(l));
  return { s, log, freed };
}

describe("the sorter's reply (section 27)", () => {
  it("asks about the question and its claims only, and never whether a claim is true", () => {
    const message = premiseMessage(stateOf());
    expect(message).toContain(`<question>\n${E1.request}\n</question>`);
    for (const x of E1.analysis.assumptions) expect(message).toContain(`${x.id}: ${x.claim}`);
    expect(PREMISE_SYSTEM).toContain("You do not judge whether a claim is true");
    expect(PREMISE_SYSTEM).toContain("When you cannot tell, choose check.");
    expect(PREMISE_SYSTEM).toContain(`Reply by calling ${PREMISE_TOOL} once.`);
  });

  it("needs one verdict for each claim and for no other", () => {
    const s = stateOf();
    expect(checkPremises(sort("A2"), s).errors).toEqual([]);
    expect(checkPremises({ claims: sort().claims.slice(0, 2) }, s).errors[0]!.message).toBe("no verdict for A3");
    expect(checkPremises({ claims: [...sort().claims, { id: "A9", verdict: "given", reason: "x" }] }, s).errors[0]!.message).toContain("A9 is not a claim of the question");
    expect(checkPremises({ claims: [...sort().claims, { id: "A1", verdict: "given", reason: "x" }] }, s).errors[0]!.message).toBe("A1 has two verdicts");
    expect(checkPremises({ claims: [{ id: "A1", verdict: "true", reason: "x" }] }, s).value).toBeNull();
  });

  it("keeps the first valid verdict on each claim when the reply stays faulty; a claim without one is checked", () => {
    const s = stateOf();
    const kept = validPremises({ claims: [{ id: "A2", verdict: "given", reason: "a" }, { id: "A2", verdict: "check", reason: "b" }, { id: "A9", verdict: "given", reason: "c" }] }, s);
    expect(kept.claims).toEqual([{ id: "A2", verdict: "given", reason: "a" }]);
    recordSort(s, kept, () => {});
    expect([...givenClaims(s)]).toEqual(["A2"]);
    expect(givenClaims(stateOf()).size).toBe(0);
  });
});

describe("a claim taken as given in the plan (section 27)", () => {
  it("stops its question being a check, and nothing waits for that question", () => {
    const waiting = stateOf().goals.filter((g) => g.dependsOn.includes("Q2")).map((g) => g.id);
    expect(waiting.length).toBeGreaterThan(0);
    const { s, log, freed } = sorted(["A2"]);
    const q2 = goalOf(s, "Q2");
    expect(freed).toEqual(["Q2"]);
    // Q2 has the template of a defining question, so without its claim it is one.
    expect(q2).toMatchObject({ verifies: [], kind: "define", need: "necessary", level: 2 });
    expect(isClaimCheck(q2)).toBe(false);
    expect(s.goals.some((g) => g.dependsOn.includes("Q2"))).toBe(false);
    // The other claims are checked as before.
    expect(s.goals.filter(isClaimCheck).map((g) => g.id)).toEqual(["Q1", "Q4"]);
    expect(log.join("\n")).toContain('A2 "New-car prices in Canada');
    expect(log.join("\n")).toContain("Q2: no longer a check, because A2 is taken as given; it stays as a question for content");
  });

  it("puts the question beside the life-cycle steps when the plan has necessary ones", () => {
    const before = stateOf(true).goals.filter((g) => g.dependsOn.includes("Q2")).map((g) => g.id);
    const { s } = sorted(["A2"], true);
    const q2 = goalOf(s, "Q2");
    expect(q2).toMatchObject({ verifies: [], kind: "define", need: "completing", level: 4 });
    expect(s.map!.replaced.Q2).toEqual(["Q9", "Q10"]);
    for (const id of before) expect(goalOf(s, id).dependsOn).toEqual(expect.arrayContaining(["Q9", "Q10"]));
    // Like a replaced question, it is not asked again once the steps have been researched.
    expect(isSuperseded(s, q2)).toBe(false);
    goalOf(s, "Q9").attempts = 1;
    goalOf(s, "Q10").attempts = 1;
    expect(isSuperseded(s, q2)).toBe(true);
  });

  it("changes nothing when no claim is taken as given, and needs no verdict on a claim that is", () => {
    const none = sorted([]);
    expect(none.freed).toEqual([]);
    expect(none.s.goals).toEqual(stateOf().goals);
    // With every other necessary goal settled, the claim taken as given does not hold up the stop.
    const { s } = sorted(["A2"]);
    for (const g of s.goals) Object.assign(g, { status: "answered", settledRound: 1, verdicts: Object.fromEntries(g.verifies.map((c) => [c, "supported"])) });
    expect(isComplete(s).complete).toBe(true);
  });

  it("holds like a supported claim when another claim is contradicted", () => {
    const refuted = (given: string[]) => {
      const { s } = sorted(given);
      Object.assign(goalOf(s, "Q4"), { status: "answered", settledRound: 1, verdicts: { A3: "contradicted" } });
      return refutedObjects(s);
    };
    const without = refuted([]);
    const withGiven = refuted(["A1", "A2"]);
    expect(without.size).toBeGreaterThan(0);
    expect(withGiven.size).toBeLessThan(without.size);
    for (const o of withGiven) expect(without.has(o)).toBe(true);
  });
});

describe("a claim taken as given and the evidence (section 27)", () => {
  it("marks the claim for the conflict checker and adds the section only then", () => {
    const { s } = sorted(["A2"]);
    const message = conflictMessage(s, []);
    expect(message).toContain(`A2 ${GIVEN_MARK}: `);
    expect(message).toContain("\nA1: ");
    expect(conflictMessage(stateOf(), [])).not.toContain(GIVEN_MARK);
    expect(conflictSystem(false, false, false)).toBe(CONFLICT_SYSTEM);
    expect(conflictSystem(true, true, false)).not.toContain(CONFLICT_GIVEN_SECTION);
    expect(conflictSystem(false, false, true)).toContain(CONFLICT_GIVEN_SECTION);
    expect(CONFLICT_GIVEN_SECTION).toContain("only when findings state that it is false as a whole");
  });

  it("tells the writer nothing about a claim taken as given, unless the evidence contradicted it", () => {
    for (const lean of [false, true]) {
      const { s } = sorted(["A2"]);
      for (const g of s.goals) Object.assign(g, { status: "answered", settledRound: 1, verdicts: Object.fromEntries(g.verifies.map((c) => [c, "supported"])) });
      const quiet = buildGuidance(s, lean);
      const claim = E1.analysis.assumptions.find((x) => x.id === "A2")!.claim;
      expect(quiet).not.toContain(claim);
      expect(quiet).not.toContain("This could not be checked");
      if (lean) expect(quiet).not.toContain(READING_LABEL);
      // A goal that settles a conflict about the claim found it false: the writer is told plainly.
      s.goals.push({ ...structuredClone(goalOf(s, "Q1")), id: "Q20", settles: "C1", kind: "settle", verifies: ["A2"], verdicts: { A2: "contradicted" }, status: "answered" } as Goal);
      expect(buildGuidance(s, lean)).toContain(`The question presupposes: "${claim}" The evidence contradicts this; say so plainly early in the report.`);
    }
    // A claim that was to be checked and got no verdict keeps its line.
    const unchecked = stateOf();
    expect(buildGuidance(unchecked, true)).toContain("This could not be checked; do not present it as established.");
  });
});

describe("the sort inside init (section 27)", () => {
  const ctx = (model: BaseChatModel) => ({ model, budget: { researchersTotal: 6, researchersUsed: 0, researchersRemaining: 6, toolCallsPerResearcher: 12 }, round: 1, runId: "t", today: E1.runDate });
  function modelWith(premises: unknown): { model: BaseChatModel; calls: string[] } {
    const calls: string[] = [];
    const model = {
      bindTools: (tools: { function: { name: string } }[]) => ({
        invoke: async () => {
          const name = tools[0]!.function.name;
          calls.push(name);
          const args = name === "submit_analysis" ? E1.analysis : name === PREMISE_TOOL ? premises : EXTENSION;
          return new AIMessage({ content: "", tool_calls: [{ id: `c${calls.length}`, name, args: args as Record<string, unknown>, type: "tool_call" }] });
        },
      }),
    } as unknown as BaseChatModel;
    return { model, calls };
  }

  it("sorts after the request analysis and plans without a check of the claim taken as given", async () => {
    const { model, calls } = modelWith(sort("A2"));
    const step = await ebd.create({}).init({ question: E1.request }, ctx(model));
    const s = step.state as EbdState;
    expect(calls).toEqual(["submit_analysis", PREMISE_TOOL, "submit_extension"]);
    expect(s.step.calls.map((c) => c.role)).toEqual(["request_analyst", "premise_sorter", "extension_analyst"]);
    expect(s.premises).toEqual({ given: [{ id: "A2", reason: "why" }] });
    expect(goalOf(s, "Q2")).toMatchObject({ verifies: [], need: "completing" });
    expect(step.decision.rationale).toContain("Taken as given, because they only restate what the question asks about: A2 ");
    expect(step.decision.rationale).toMatch(/Assumptions to verify: A1 .* A3 /);
    // No brief asks a researcher to verify that claim.
    const claim = E1.analysis.assumptions.find((x) => x.id === "A2")!.claim;
    for (const b of step.decision.briefs) expect((b.instructions ?? "").split("\n").filter((l) => l.includes(VERIFY_INSTRUCTION)).join("\n")).not.toContain(claim);
    expect(s.problems).toEqual([]);
  });

  it("checks every claim when the option is off or the sorter gives no usable reply", async () => {
    const off = modelWith(sort("A2"));
    const plain = (await ebd.create({ premiseSort: false }).init({ question: E1.request }, ctx(off.model))).state as EbdState;
    expect(off.calls).toEqual(["submit_analysis", "submit_extension"]);
    expect(plain.premises ?? null).toBeNull();
    expect(goalOf(plain, "Q2").verifies).toEqual(["A2"]);

    const bad = modelWith({ nothing: true });
    const s = (await ebd.create({}).init({ question: E1.request }, ctx(bad.model))).state as EbdState;
    expect(bad.calls.filter((c) => c === PREMISE_TOOL)).toHaveLength(2);
    expect(s.premises ?? null).toBeNull();
    expect(goalOf(s, "Q2").verifies).toEqual(["A2"]);
    expect(s.problems).toEqual(["premise sort gave no usable reply; every claim of the question is checked"]);
  });
});

describe("where the first round's researchers go (section 27, option stepsFirst)", () => {
  type Plan = (state: EbdState, ctx: unknown, lines: string[], progress: null) => { decision: { briefs: { tag?: string }[] } };
  const tagsOf = (options: Record<string, unknown>, s: EbdState) =>
    (ebd.create(options as never) as unknown as { plan: Plan }).plan(s, { budget: { researchersTotal: 6, researchersUsed: 0, researchersRemaining: 6, toolCallsPerResearcher: 12 }, round: 1, runId: "t", today: E1.runDate }, [], null).decision.briefs.map((b) => b.tag);

  it("lets a question that stopped being a check ride along instead of taking a researcher", () => {
    // Planned like any goal, the former check Q2 has a researcher to itself, and the two steps share one.
    expect(tagsOf({ stepsFirst: false, premiseRides: false }, sorted(["A2"], true).s)).toEqual(["Q1", "Q4,Q9,Q10", "Q3", "Q2"]);
    // With the defaults it rides with a question for content, each check rides too, and each step has its brief.
    expect(tagsOf({}, sorted(["A2"], true).s)).toEqual(["Q1,Q9", "Q3,Q2", "Q4,Q10"]);
  });

  it("changes nothing after round 1, and nothing without life-cycle steps", () => {
    const later = () => Object.assign(sorted(["A2"], true).s, { roundsObserved: 1 });
    expect(tagsOf({ stepsFirst: true }, later())).toEqual(tagsOf({ stepsFirst: false }, later()));
    expect(tagsOf({ stepsFirst: true, premiseRides: false }, sorted(["A2"]).s)).toEqual(tagsOf({ stepsFirst: false, premiseRides: false }, sorted(["A2"]).s));
  });

  it("puts a rider into a brief with room, after its goals, and lets it wait when none has room", () => {
    const s = stateOf();
    const rider: Goal = { ...goalOf(s, "Q5"), need: "completing" };
    const groups = [{ key: "O9", goals: [goalOf(s, "Q3")] }];
    const joined = shareRiders(groups, [rider], s, { questionsPerBrief: 3 });
    expect(joined.groups.map((g) => g.goals.map((x) => x.id))).toEqual([["Q3", "Q5"]]);
    expect(joined.waiting).toEqual([]);
    const full = shareRiders(groups, [rider], s, { questionsPerBrief: 1 });
    expect(full.groups.map((g) => g.goals.map((x) => x.id))).toEqual([["Q3"]]);
    expect(full.waiting.map((g) => g.id)).toEqual(["Q5"]);
  });
});

describe("a researcher that would sit idle (section 27)", () => {
  it("goes to a life-cycle step that shares a brief with another step, before any other goal", () => {
    const s = stateOf(true);
    const [q3, q5, q9, q10] = ["Q3", "Q5", "Q9", "Q10"].map((id) => goalOf(s, id)) as [Goal, Goal, Goal, Goal];
    const completing = (g: Goal): Goal => ({ ...g, need: "completing" });
    // One necessary goal with two riders, and two completing steps that share a brief.
    const groups = [{ key: "a", goals: [q3, completing(q5), completing(goalOf(s, "Q6"))] }, { key: "b", goals: [completing(q9), completing(q10)] }];
    const step = (g: Goal) => g.origin.type === "assumed";
    const regroup = { within: 3, load: (g: { goals: Goal[] }) => g.goals.length };
    const tags = (out: { goals: Goal[] }[]) => out.map((g) => g.goals.map((x) => x.id).join(","));
    expect(tags(spread(groups, 3, 6, { ...regroup, step }))).toEqual(["Q3,Q5,Q6", "Q9", "Q10"]);
    // Without the preference the largest brief gives up its last goal, a planned question.
    expect(tags(spread(groups, 3, 6, regroup))).toEqual(["Q3,Q5", "Q9,Q10", "Q6"]);
  });
});
