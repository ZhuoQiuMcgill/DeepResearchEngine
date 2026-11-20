/**
 * The one approach of design sections 29 and 30, without network: the one-call plan, the first round
 * for any number of researchers, and the follow-up rules. The rules themselves, the wording each agent
 * gets, whole runs through the skeleton, and the texts as approved.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { buildResearchGraph, initialState, type DecisionRecord } from "../../graph/skeleton.js";
import { PLANNED_PARTS_INSTRUCTION, PLAN_QUESTIONS_INSTRUCTION, VERIFY_INSTRUCTION, partsFirst } from "./briefs.js";
import { PLAN_SYSTEM, PLAN_TOOL, checkQuestion, type PlanReply } from "./environment.js";
import ebd from "./index.js";
import { parseOptions } from "./options.js";
import { ANALYST_FOCUS_SECTION, ANALYST_QUESTIONS_SECTION, analystMessage, analystSystem } from "./rounds/analyst.js";
import { CONFLICT_CRITICAL_SECTION, CONFLICT_GIVEN_SECTION, CONFLICT_QUESTIONS_SECTION, applyConflicts, conflictMessage, conflictSystem, type ConflictsReply } from "./rounds/conflicts.js";
import type { EbdState } from "./state.js";
import { CRITICAL_HEADING, READING_LABEL } from "./synthesis.js";

/** The one approach needs no settings (design section 32). */
const APPROACH = {} as const;
/** What the code tells each agent about a disagreement between sources (section 29). */
const CHECKER_ON_DISPUTES = "A critical conflict that decides a claim of the question is researched again; any other critical conflict goes to the writer of the report as a point the answer depends on";
const ANALYST_ON_DISPUTES = "code gives a goal of its own only to a conflict that decides a claim of the question";
const QUESTION = "Why did the town of Ashby close its public library in 2019?";
const TODAY = "2026-11-19";
const q = (text: string) => ({ text, kind: "social" as const });
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
const budget = { researchersTotal: 6, researchersUsed: 0, researchersRemaining: 6, toolCallsPerResearcher: 12 };

function block(message: string, tag: string): string {
  return new RegExp(`<${tag}>\\n([\\s\\S]*?)\\n</${tag}>`).exec(message)?.[1] ?? "";
}

/** A state after init with the one-call plan. */
async function planned(): Promise<EbdState> {
  const model = {
    bindTools: (tools: { function: { name: string } }[]) => ({ invoke: async () => new AIMessage({ content: "", tool_calls: [{ id: "c", name: tools[0]!.function.name, args: PLAN as Record<string, unknown>, type: "tool_call" }] }) }),
  } as unknown as BaseChatModel;
  const step = await ebd.create(APPROACH as never).init({ question: QUESTION }, { model, budget, round: 1, runId: "t", today: TODAY });
  return step.state as EbdState;
}
const LIMITS = { maxDepth: 2, maxOpenGoals: 20, maxNewGoalsPerRound: 4 };
const dispute = (claim: string): ConflictsReply => ({
  conflicts: [{ type: "source_vs_source", about: "Q3", statement: "One source says the council decided, another that the mayor did.", side_a: ["r1-b1-f1"], side_b: ["r1-b1-f2"], settle_by: "The council minutes.", condition: "", claim, critical: true }],
});

describe("a disagreement between sources is reported, not researched again (section 29)", () => {
  it("has no switch: the options that chose a planner or a follow-up rule are gone", () => {
    for (const gone of ["init", "extend", "completeMap", "partQuestions", "premiseSort", "premiseRides", "stepsFirst", "focusFollowUp", "leanGuidance", "mainPartsFirst", "uncitedParts", "strictFollowUp", "extraRound"]) {
      expect(() => parseOptions({ [gone]: true }), gone).toThrow();
    }
    // The two ablation switches of the platform's experiments stay.
    expect(parseOptions({ conflicts: false, newGoals: false })).toMatchObject({ conflicts: false, newGoals: false, spread: true });
  });

  it("gives no settle goal to a critical disagreement that decides no claim of the question", async () => {
    const s = await planned();
    const log: string[] = [];
    const added = applyConflicts(s, dispute(""), 1, LIMITS, (l) => log.push(l));
    expect(added).toHaveLength(1);
    expect(added[0]).toMatchObject({ status: "disputed", critical: true, settleGoal: null, claim: null });
    expect(s.goals.some((g) => g.settles)).toBe(false);
    expect(log.join("\n")).toContain("it decides no claim of the question, so it is reported and not researched again");
  });

  it("still gives a settle goal to a disagreement that decides a claim of the question", async () => {
    const withClaim = await planned();
    applyConflicts(withClaim, dispute("A1"), 1, LIMITS, () => {});
    const settle = withClaim.goals.find((g) => g.settles)!;
    expect(settle).toMatchObject({ settles: "C1", verifies: ["A1"], need: "necessary" });
  });
});

describe("the wording each agent gets in the one approach", () => {
  it("speaks of key questions and of reported disagreements, never of life-cycle steps", () => {
    const checker = conflictSystem(true);
    expect(checker).toContain(CONFLICT_QUESTIONS_SECTION);
    expect(checker).toContain(CONFLICT_CRITICAL_SECTION);
    expect(checker).toContain(CHECKER_ON_DISPUTES);
    expect(checker).not.toContain("life-cycle");
    expect(checker).not.toContain(CONFLICT_GIVEN_SECTION);
    const analyst = analystSystem(true);
    expect(analyst).toContain(ANALYST_QUESTIONS_SECTION);
    expect(analyst).toContain(ANALYST_FOCUS_SECTION);
    expect(analyst).toContain(ANALYST_ON_DISPUTES);
    expect(analyst).not.toContain("one life-cycle step of the subject");
  });

  it("adds the section on claims taken as given only when the plan has one, and leaves out the plan's section for the plan of last resort", () => {
    expect(conflictSystem(true, true)).toContain(CONFLICT_GIVEN_SECTION);
    // Section 24.4: the plan of last resort has no main parts, so neither agent is told about key questions.
    expect(conflictSystem(false)).not.toContain(CONFLICT_QUESTIONS_SECTION);
    expect(conflictSystem(false)).toContain(CONFLICT_CRITICAL_SECTION);
    expect(analystSystem(false)).not.toContain(ANALYST_QUESTIONS_SECTION);
    expect(analystSystem(false)).toContain(ANALYST_FOCUS_SECTION);
  });

  it("labels the plan's key questions as such in both messages", async () => {
    const s = await planned();
    expect(conflictMessage(s, [])).toContain('M1 [Q3, part "The closure"] Did the town of Ashby close its public library, and on what date?');
    const served = s.goals.filter((g) => g.id === "Q3");
    expect(analystMessage(s, 1, served, parseOptions(APPROACH))).toContain('Key questions of the main part "The closure":');
  });

  it("plans a request that names no referent for the likely cases, by the prompt's own rule", () => {
    expect(PLAN_SYSTEM).toContain('A request that points at something without naming it ("the earthquake", "the new law") is not out of scope when research can still serve the client: list it under not_stated, and plan for the most likely cases and name them.');
  });
});

// ---------------------------------------------------------------- one whole run, without network

const research = async (_q: string, brief: ResearchBrief): Promise<ResearchResult> => ({
  brief,
  status: "ok",
  notes: brief.keyQuestions
    .map((k, i) =>
      [
        `## ${k}`,
        "### Takeaway",
        `Takeaway ${i + 1}.`,
        "### Cited Findings",
        `- ${k.includes("Which body decided") ? "The council decided the closure (COUNCIL)." : `A finding for key question ${i + 1}.`} — [Source](https://a${i}.example/${brief.id})`,
        `- ${k.includes("Which body decided") ? "The mayor decided the closure alone (MAYOR)." : `A second finding for key question ${i + 1}.`} — [Source](https://b${i}.example/${brief.id})`,
        "### Gaps",
        "- Nothing more was found.",
      ].join("\n"),
    )
    .join("\n\n"),
  sources: [],
  queries: [],
  usage: { inputTokens: 0, outputTokens: 0, searches: 1, pageReads: 0 },
  model: "fake",
  durationMs: 0,
  unlistedCitations: [],
  diagnostics: [],
});

/** The conflict checker: the council against the mayor, marked critical, deciding no claim. */
function conflicts(message: string) {
  const fresh = [...block(message, "new_evidence").matchAll(/^(r\d+-b\d+-f\d+) (?:\[[^\]]*\] )?(.*)$/gm)].map((m) => ({ id: m[1]!, text: m[2]! }));
  const a = fresh.find((l) => l.text.includes("(COUNCIL)"));
  const b = fresh.find((l) => l.text.includes("(MAYOR)"));
  return { conflicts: a && b ? [{ type: "source_vs_source", about: "Q3", statement: "One source says the council decided the closure, another that the mayor decided it alone.", side_a: [a.id], side_b: [b.id], settle_by: "The council minutes.", condition: "", claim: "", critical: true }] : [] };
}

function judge(message: string, propose = false) {
  const judgments = block(message, "served_goals")
    .split(/\n(?=### )/)
    .map((g) => {
      const id = /^### (Q\d+)/.exec(g)![1]!;
      const all = [...g.matchAll(/^(r\d+-b\d+-f\d+) /gm)].map((m) => m[1]!);
      const first = all[0];
      const claims = [...g.matchAll(/^- (A\d+): /gm)].map((m) => m[1]!);
      const listed = /^Judge only: (.*)$/m.exec(g)?.[1];
      // A claim needs findings from two independent hosts (section 10.1), so the check cites both.
      const parts = listed !== undefined ? listed.split(", ").filter((p) => /^M\d+$/.test(p)).map((p) => ({ part: `${p} answered`, met: Boolean(first), evidence: first ? [first] : [] })) : [{ part: "the claim", met: Boolean(first), evidence: all }];
      return { goal_id: id, parts, outcome: first ? "answered" : "not_found", verdicts: claims.map((c) => ({ claim_id: c, verdict: "supported" })), missing: [] };
    });
  // After round 1: one main part the findings leave out, and one detail.
  const prompt = /^(r1-b\d+-f\d+) /m.exec(message)?.[1];
  const shared = { template: "T1", object_id: "O1", new_object: "", new_object_quote: "", prompted_by: prompt ? [prompt] : [], leads_to: ["Q2"], source_hints: [] };
  const proposals = propose && prompt
    ? [
        { ...shared, text: "What did the town of Ashby offer readers in place of its public library after the closure?", need: "necessary", done_when: "Names what replaced the library, with its source." },
        { ...shared, text: "How many books did the public library of Ashby hold in its last year?", need: "completing", done_when: "Gives the number, with its source." },
      ]
    : [];
  return { judgments, proposals };
}

describe("a whole run of the one approach, through the skeleton", () => {
  it("researches the main parts once, reports the disagreement to the writer and sends no researcher to settle it", async () => {
    const systems: Record<string, string> = {};
    const model = {
      bindTools: (tools: { function: { name: string } }[]) => ({
        invoke: async (messages: BaseMessage[]) => {
          const name = tools[0]!.function.name;
          systems[name] = String(messages[0]!.content);
          const args = name === PLAN_TOOL ? PLAN : name === "submit_conflicts" ? conflicts(String(messages.at(-1)!.content)) : judge(String(messages.at(-1)!.content));
          return new AIMessage({ content: "", tool_calls: [{ id: "c", name, args: args as Record<string, unknown>, type: "tool_call" }] });
        },
      }),
    } as unknown as BaseChatModel;
    const decisions: DecisionRecord[] = [];
    let synthesis: { material: { label: string; notes: string }[]; outline?: string[]; guidance?: string } | undefined;
    const graph = buildResearchGraph({
      strategy: ebd.create(APPROACH as never),
      strategyModel: model,
      research,
      write: async (_q, s) => ((synthesis = s), { report: "report", diagnostics: [] }),
      limits: { researchersTotal: 6, toolCallsPerResearcher: 12 },
      maxRounds: 6,
      concurrency: 4,
      runId: "t",
      today: TODAY,
      hooks: { onDecision: (d) => void decisions.push(d) },
    });
    const final = await graph.invoke(initialState(QUESTION), { recursionLimit: 100 });
    const state = final.strategyState as EbdState;
    expect(final.stopReason).toBe("strategy-stop");
    expect(state.stop).toMatchObject({ kind: "complete" });
    expect(state.problems).toEqual([]);
    // One round: two researchers for the two main parts, the check riding with one of them.
    expect(decisions[0]!.accepted).toHaveLength(2);
    expect(state.results.every((r) => r.round === 1)).toBe(true);
    // The disagreement is recorded as disputed, marked critical, and has no goal.
    expect(state.conflicts).toHaveLength(1);
    expect(state.conflicts[0]).toMatchObject({ type: "source_vs_source", status: "disputed", critical: true, settleGoal: null });
    expect(state.goals.some((g) => g.settles)).toBe(false);
    // The writer is told about it as a point the answer depends on, in the lean guidance.
    expect(synthesis!.guidance).toContain(CRITICAL_HEADING);
    expect(synthesis!.guidance).toContain("One source says the council decided the closure, another that the mayor decided it alone.");
    // The two researched main parts are the suggested outline (section 34).
    expect(synthesis!.outline).toEqual(["The closure", "Reasons"]);
    // The agents got the wording of this approach.
    expect(systems.submit_conflicts).toContain(CONFLICT_QUESTIONS_SECTION);
    expect(systems.submit_conflicts).toContain(CHECKER_ON_DISPUTES);
    expect(systems.submit_round_analysis).toContain(ANALYST_QUESTIONS_SECTION);
    expect(systems.submit_round_analysis).toContain(ANALYST_ON_DISPUTES);
  });
  it("after the first round sends a researcher to a missing main part, and never to a detail", async () => {
    const model = {
      bindTools: (tools: { function: { name: string } }[]) => ({
        invoke: async (messages: BaseMessage[]) => {
          const name = tools[0]!.function.name;
          const message = String(messages.at(-1)!.content);
          const args = name === PLAN_TOOL ? PLAN : name === "submit_conflicts" ? { conflicts: [] } : judge(message, !message.includes("r2-b1-f1"));
          return new AIMessage({ content: "", tool_calls: [{ id: "c", name, args: args as Record<string, unknown>, type: "tool_call" }] });
        },
      }),
    } as unknown as BaseChatModel;
    const decisions: DecisionRecord[] = [];
    const graph = buildResearchGraph({
      strategy: ebd.create(APPROACH as never),
      strategyModel: model,
      research,
      write: async () => ({ report: "report", diagnostics: [] }),
      limits: { researchersTotal: 6, toolCallsPerResearcher: 12 },
      maxRounds: 6,
      concurrency: 4,
      runId: "t",
      today: TODAY,
      hooks: { onDecision: (d) => void decisions.push(d) },
    });
    const final = await graph.invoke(initialState(QUESTION), { recursionLimit: 100 });
    const state = final.strategyState as EbdState;
    const main = state.goals.find((g) => g.text.startsWith("What did the town of Ashby offer readers"))!;
    const detail = state.goals.find((g) => g.text.startsWith("How many books"))!;
    expect(main).toMatchObject({ need: "necessary", status: "answered", attempts: 1 });
    expect(detail).toMatchObject({ need: "completing", status: "open", attempts: 0 });
    // Round 2 holds the one brief for the missing main part; the detail is never researched.
    expect(decisions.map((d) => d.accepted.map((b) => b.tag))).toEqual([["Q1,Q3", "Q4"], [main.id], []]);
    expect(state.results).toHaveLength(3);
    expect(state.stop).toMatchObject({ kind: "complete" });
  });
});

// ---------------------------------------------------------------- the first round with fewer researchers than six (section 30)

/** The plan above with two completing parts: four main parts, the shape of most saved plans. */
const PLAN4: PlanReply = {
  ...PLAN,
  parts: [
    ...PLAN.parts,
    { name: "After the closure", need: "completing", objective: "Establish what replaced the public library of Ashby and how residents of Ashby reach books since the closure.", questions: [q("What replaced the public library of Ashby after the closure?"), q("How far is the nearest public library from the town of Ashby?"), q("Which mobile or online library services reach the town of Ashby?"), q("How did residents of Ashby respond to the closure of the public library?")], source_hints: [] },
    { name: "Other towns", need: "completing", objective: "Establish how common the closure of a public library was among towns like Ashby in the same years.", questions: [q("How many public libraries closed in the county of Ashby between 2015 and 2020?"), q("Which reasons did towns like Ashby give for closing a public library?"), q("Which towns like Ashby kept their public library open, and how?"), q("What does research say about the effects of closing a public library in a small town?")], source_hints: [] },
  ],
};
const planModel = (plan: PlanReply, after: (name: string, message: string) => unknown = () => ({ conflicts: [] })) =>
  ({
    bindTools: (tools: { function: { name: string } }[]) => ({
      invoke: async (messages: BaseMessage[]) => {
        const name = tools[0]!.function.name;
        const args = name === PLAN_TOOL ? plan : after(name, String(messages.at(-1)!.content));
        return new AIMessage({ content: "", tool_calls: [{ id: "c", name, args: args as Record<string, unknown>, type: "tool_call" }] });
      },
    }),
  }) as unknown as BaseChatModel;

/** The first round's briefs for a plan and a number of researchers. */
async function firstRound(plan: PlanReply, researchers: number, options: Record<string, unknown> = APPROACH) {
  const step = await ebd.create(options as never).init({ question: QUESTION }, { model: planModel(plan), budget: { researchersTotal: researchers, researchersUsed: 0, researchersRemaining: researchers, toolCallsPerResearcher: 12 }, round: 1, runId: "t", today: TODAY });
  return { briefs: step.decision.briefs, state: step.state as EbdState, shape: step.decision.briefs.map((b) => `${b.tag}:${b.keyQuestions.length}`) };
}

describe("the first round of the plan uses every researcher it has for a main part (section 30)", () => {
  // Goals: Q1 the check of the claim, Q2 the client's question (written, not searched), Q3 and Q4 the
  // necessary parts, Q5 and Q6 the completing parts; each part has 4 key questions.
  it("deals the parts over the researchers, the necessary parts first", async () => {
    const { state } = await firstRound(PLAN4, 6);
    const parts = state.goals.filter((g) => ["Q3", "Q4", "Q5", "Q6"].includes(g.id));
    const ids = (n: number) => {
      const dealt = partsFirst(parts, n);
      return { groups: dealt.groups.map((g) => g.goals.map((x) => x.id).join("+")), riders: dealt.riders.map((x) => x.id) };
    };
    expect(ids(6)).toEqual({ groups: ["Q3", "Q4", "Q5", "Q6"], riders: [] });
    expect(ids(4)).toEqual({ groups: ["Q3", "Q4", "Q5", "Q6"], riders: [] });
    expect(ids(3)).toEqual({ groups: ["Q3", "Q4", "Q5+Q6"], riders: [] });
    expect(ids(2)).toEqual({ groups: ["Q3", "Q4"], riders: ["Q5", "Q6"] });
    expect(ids(1)).toEqual({ groups: ["Q3+Q4"], riders: ["Q5", "Q6"] });
  });

  it("gives each main part a researcher when there are as many researchers as parts, and keeps none back", async () => {
    for (const researchers of [4, 5, 6]) {
      const { shape, briefs } = await firstRound(PLAN4, researchers);
      // The check leads the brief of a necessary part; every part is asked key question by key question.
      expect(shape).toEqual(["Q1,Q3:5", "Q4:4", "Q5:4", "Q6:4"]);
      expect(briefs.every((b) => !b.instructions?.includes("the plan expects an answer to cover these questions"))).toBe(true);
    }
  });

  it("with three researchers gives each necessary part one, and the completing parts share the third", async () => {
    const { shape, briefs, state } = await firstRound(PLAN4, 3);
    expect(shape).toEqual(["Q1,Q3:5", "Q4:4", "Q5,Q6:5"]);
    // The first completing part is asked key question by key question, the second as one question with its key questions listed.
    expect(briefs[2]!.keyQuestions.filter((k) => k.startsWith("[Q5] "))).toHaveLength(4);
    expect(briefs[2]!.keyQuestions.filter((k) => k.startsWith("[Q6] "))).toEqual([`[Q6] ${PLAN4.parts[3]!.objective}`]);
    expect(briefs[2]!.instructions).toContain(`For [Q6], the plan expects an answer to cover these questions: ${PLAN4.parts[3]!.questions.map((x) => x.text).join(" ")}`);
    expect(state.step.events.join("\n")).toContain("first round of the plan: 3 researcher(s) for 4 main part(s); 1 brief(s) hold more than one part");
  });

  it("with two researchers asks each necessary part in full, and a completing part rides as one question in each brief", async () => {
    const { shape, briefs, state } = await firstRound(PLAN4, 2);
    expect(shape).toEqual(["Q1,Q3,Q6:6", "Q4,Q5:5"]);
    expect(briefs[0]!.keyQuestions.filter((k) => k.startsWith("[Q3] "))).toHaveLength(4);
    expect(briefs[1]!.keyQuestions.filter((k) => k.startsWith("[Q4] "))).toHaveLength(4);
    expect(state.step.events.join("\n")).toContain("Q5, Q6 asked as one question in the brief of a necessary part");
  });

  it("with one researcher asks the necessary parts and the check, and a completing part only where the brief has room", async () => {
    const { shape, state } = await firstRound(PLAN4, 1);
    expect(shape).toEqual(["Q1,Q3,Q4:6"]);
    expect(state.step.events.join("\n")).toContain("Q5, Q6 not asked this round");
  });

  it("is part of spreading the researchers: with `spread` off the goals are packed as before", async () => {
    const { shape, state } = await firstRound(PLAN4, 4, { ...APPROACH, spread: false });
    expect(shape).not.toEqual(["Q1,Q3:5", "Q4:4", "Q5:4", "Q6:4"]);
    expect(state.step.events.join(" | ")).not.toContain("first round of the plan:");
  });

  it("runs once through the skeleton with the baseline's four researchers: four briefs, one round", async () => {
    const decisions: DecisionRecord[] = [];
    const graph = buildResearchGraph({
      strategy: ebd.create(APPROACH as never),
      strategyModel: planModel(PLAN4, (name, message) => (name === "submit_conflicts" ? { conflicts: [] } : judge(message))),
      research,
      write: async () => ({ report: "report", diagnostics: [] }),
      limits: { researchersTotal: 4, toolCallsPerResearcher: 12 },
      maxRounds: 6,
      concurrency: 4,
      runId: "t",
      today: TODAY,
      hooks: { onDecision: (d) => void decisions.push(d) },
    });
    const final = await graph.invoke(initialState(QUESTION), { recursionLimit: 100 });
    const state = final.strategyState as EbdState;
    expect(decisions[0]!.accepted.map((b) => b.tag)).toEqual(["Q1,Q3", "Q4", "Q5", "Q6"]);
    expect(state.results).toHaveLength(4);
    expect(state.goals.filter((g) => ["Q3", "Q4", "Q5", "Q6"].includes(g.id)).every((g) => g.status === "answered" && g.attempts === 1)).toBe(true);
    expect(state.stop).toMatchObject({ kind: "complete" });
    expect(state.problems).toEqual([]);
  });

  it("after the first round still asks a main part of the plan that no researcher was asked about", async () => {
    // One researcher a round: the two necessary parts and the check fill the first brief, so the completing part waits.
    const plan3: PlanReply = { ...PLAN4, parts: PLAN4.parts.slice(0, 3) };
    const decisions: DecisionRecord[] = [];
    const graph = buildResearchGraph({
      strategy: ebd.create({ ...APPROACH, maxPerRound: 1 } as never),
      strategyModel: planModel(plan3, (name, message) => (name === "submit_conflicts" ? { conflicts: [] } : judge(message))),
      research,
      write: async () => ({ report: "report", diagnostics: [] }),
      limits: { researchersTotal: 6, toolCallsPerResearcher: 12 },
      maxRounds: 6,
      concurrency: 4,
      runId: "t",
      today: TODAY,
      hooks: { onDecision: (d) => void decisions.push(d) },
    });
    const final = await graph.invoke(initialState(QUESTION), { recursionLimit: 100 });
    const state = final.strategyState as EbdState;
    expect(decisions.map((d) => d.accepted.map((b) => b.tag))).toEqual([["Q1,Q3,Q4"], ["Q5"], []]);
    expect(state.goals.find((g) => g.id === "Q5")).toMatchObject({ need: "completing", status: "answered", attempts: 1 });
    expect(state.stop).toMatchObject({ kind: "complete" });
    expect(state.results).toHaveLength(2);
  });
});

// ---------------------------------------------------------------- the approved texts

/**
 * The writer's fixed words, as approved: on 2026-11-19 (section 29.1), and on 2026-11-20 (section 34)
 * the lines on a contradicted claim, on the question's main terms and on sources. Gone since then:
 * the lines "say so plainly early in the report" and "neither confirms nor contradicts", and the
 * block of what the client did not state.
 */
const WRITER_LINES = [
  "Do not open the report with these notes, and do not mention the research process.",
  "Follow the client's directives:",
  "This comes before everything below: answer the question first, give each disagreement and each gap at most one sentence, and leave out detail the client did not ask for.",
  READING_LABEL,
  "The question takes for granted:",
  "The evidence in the notes contradicts this. Say so in the opening paragraph, in one or two sentences with the source. Then answer the question the client asked as fully as the notes allow: the correction is not the subject of the report.",
  "What the evidence shows about the question's premises:",
  "This could not be checked; do not present it as established.",
  "Early in the report, say what the question's main terms mean and how they are defined or measured, in a sentence or two each, with the source the notes give.",
  "Build first on the strongest sources in the notes: official statistics, peer-reviewed studies and primary documents before commentary. Give each figure with its year and what it measures, and say where the evidence is thin or disputed.",
  CRITICAL_HEADING,
  "Give both sides, each with the source the notes cite for it",
  "and say which one the report follows and why, or that the evidence does not decide it.",
  "This was researched further, and the notes show which account holds and why.",
  "Both hold, at different times:",
  "Evidence to keep apart:",
  "Leave them out, and distinguish the terms only where needed.",
  "Use it only as context and say so.",
  "No reliable source was found for these; say so where relevant instead of guessing:",
  "These questions could not be researched because of technical failures, not for lack of sources. Do not claim that no source exists; where relevant, say only that the report does not cover them:",
];

describe("the prompt texts of the one approach, approved on 2026-11-19 (section 29.1) and 2026-11-20 (section 34)", () => {
  const mark = (text: string) => createHash("sha256").update(text, "utf8").digest("hex").slice(0, 16);

  // A different mark means that a text sent to a model has changed. Show the behaviour design lead
  // the exact text, now and proposed, and put the new mark here only after the approval.
  it("are unchanged", () => {
    expect({
      planner: mark(PLAN_SYSTEM),
      conflictChecker: mark(conflictSystem(true, true)),
      roundAnalyst: mark(analystSystem(true)),
      briefs: mark([PLAN_QUESTIONS_INSTRUCTION, VERIFY_INSTRUCTION, PLANNED_PARTS_INSTRUCTION, checkQuestion(["A."]), checkQuestion(["A.", "B."])].join("\n")),
      // The planner's mark was cd18be9484f760a6 until 2026-11-20, when two passages on the question's claims were approved (section 34).
    }).toEqual({ planner: "ee23db334e24e08c", conflictChecker: "e0a4526da75d4b7d", roundAnalyst: "101bd7ad1de0159c", briefs: "685b46f749cd9d47" });
  });

  it("no longer sends the writer the lines that were taken out on 2026-11-20", () => {
    const source = readFileSync(new URL("./synthesis.ts", import.meta.url), "utf8");
    for (const gone of ["The evidence contradicts this; say so plainly early in the report.", "The evidence neither confirms nor contradicts this; do not present it as established.", "The client did not state these; they were assumed."]) expect(source).not.toContain(gone);
  });

  it("include the writer's lines word for word", () => {
    const source = readFileSync(new URL("./synthesis.ts", import.meta.url), "utf8");
    for (const line of WRITER_LINES) expect(source).toContain(line);
  });
});
