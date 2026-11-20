/**
 * The environment analysis in one call (design section 28), without network:
 * the checks of the analyst's reply, the analysis and the map built from it, the first-round briefs,
 * the cases without a usable plan, and one whole run through the real skeleton.
 */
import { describe, expect, it } from "vitest";
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { buildResearchGraph, initialState, type DecisionRecord } from "../../graph/skeleton.js";
import { PLAN_QUESTIONS_INSTRUCTION, VERIFY_INSTRUCTION } from "./briefs.js";
import { PLAN_LIMITS, PLAN_SYSTEM, PLAN_TOOL, analysisFromPlan, checkPlan, checkQuestion, planMessage, validParts, type PlanReply } from "./environment.js";
import ebd from "./index.js";
import { parseOptions } from "./options.js";
import type { EbdState } from "./state.js";

const QUESTION = "Why did the town of Ashby close its public library in 2019, and can a library help a small town?";
const TODAY = "2026-11-19";
const q = (text: string, kind: PlanReply["parts"][number]["questions"][number]["kind"] = "social") => ({ text, kind });
const PLAN: PlanReply = {
  status: "ok",
  status_reason: null,
  restated_request: "Explain why the town of Ashby closed its public library in 2019 and whether a public library can help a small town.",
  subject: "the closure of Ashby's public library",
  purpose: { value: "To understand the closure and what a library can do for a small town.", basis: "implied" },
  time_frame: { value: "Latest available evidence as of 2026-11-19.", basis: "default" },
  place: { value: "Ashby; other small towns for comparison.", basis: "implied" },
  directives: [{ kind: "report_format", text: "Present the reasons as a list.", quote: "not in the request" }],
  not_stated: ["Which Ashby is meant: cover the towns of that name with a public library and say which closed one."],
  terms: [],
  claims: [
    { claim: "The town of Ashby closed its public library in 2019.", verdict: "check", reason: "A particular event with a date." },
    { claim: "A library can help a small town.", verdict: "given", reason: "The possibility the question asks about." },
  ],
  parts: [
    { name: "The closure", need: "necessary", objective: "Establish whether, when and by whose decision the town of Ashby closed its public library.", questions: [q("Did the town of Ashby close its public library, and on what date?", "built_digital"), q("Which body decided to close the public library of Ashby, and what reasons did it record?"), q("What happened to the building and the collection of Ashby's public library after the closure?", "built_physical")], source_hints: ["council minutes", "local press"] },
    { name: "Reasons", need: "necessary", objective: "Establish the reasons given for closing the public library of Ashby and how far the evidence supports each.", questions: [q("What did the budget of the town of Ashby show for its public library in the years before the closure?", "economic"), q("How did use of Ashby's public library change before the closure (for example loans and visits)?"), q("Where do residents and the council of Ashby disagree about the reasons for the closure, and what does each side rest on?")], source_hints: ["council budgets"] },
    { name: "What a library does for a small town", need: "necessary", objective: "Establish what studies report about the effects of a public library on a small town.", questions: [q("What effects of public libraries on small towns do studies report (for example on literacy, employment or social contact)?"), q("What does running a public library cost a small town, and who pays?", "economic")], source_hints: ["library research"] },
    { name: "Alternatives", need: "completing", objective: "Establish what small towns have done instead of running a public library of their own.", questions: [q("Which alternatives to a town-run public library have small towns used (for example mobile libraries or volunteer-run libraries)?"), q("What do evaluations report about how well those alternatives serve residents?")], source_hints: [] },
  ],
};
const clone = (): PlanReply => structuredClone(PLAN);
const budget = { researchersTotal: 6, researchersUsed: 0, researchersRemaining: 6, toolCallsPerResearcher: 12 };

/** A model that answers the environment analyst with the given replies in turn, and counts the calls by tool. */
function planner(...replies: unknown[]) {
  const calls: string[] = [];
  const model = {
    bindTools: (tools: { function: { name: string } }[]) => ({
      invoke: async () => {
        const name = tools[0]!.function.name;
        calls.push(name);
        const args = replies[Math.min(calls.length, replies.length) - 1];
        return new AIMessage({ content: "", tool_calls: [{ id: `c${calls.length}`, name, args: args as Record<string, unknown>, type: "tool_call" }] });
      },
    }),
  } as unknown as BaseChatModel;
  return { model, calls };
}
const ctx = (model: BaseChatModel, runId = "t") => ({ model, budget, round: 1, runId, today: TODAY });
const create = (options: Record<string, unknown> = {}) => ebd.create(options as never);

describe("the environment analyst's reply (section 28)", () => {
  it("is asked about the request alone, and told that what it knows is a guess the evidence overrides", () => {
    expect(planMessage(QUESTION, TODAY)).toBe(`<run_date>${TODAY}</run_date>\n<client_request>\n${QUESTION}\n</client_request>`);
    expect(PLAN_SYSTEM).toContain("Everything you write is a guess that the evidence overrides");
    expect(PLAN_SYSTEM).toContain("give it a verdict from the wording alone, never from what you believe to be true");
    expect(PLAN_SYSTEM).toContain("Never correct the question yourself, and never drop what it asks.");
    expect(PLAN_SYSTEM).toContain(`Reply by calling ${PLAN_TOOL} once.`);
  });

  it("accepts a plan, and takes a list the reply leaves out as empty", () => {
    expect(checkPlan(clone())).toMatchObject({ errors: [], warnings: [] });
    const { directives: _d, not_stated: _n, terms: _t, claims: _c, status_reason: _s, ...bare } = clone();
    const checked = checkPlan(bare);
    expect(checked.errors).toEqual([]);
    expect(checked.value).toMatchObject({ directives: [], not_stated: [], terms: [], claims: [], status_reason: null });
  });

  it("cuts a list that is too long, with a warning and without a retry", () => {
    const long = clone();
    long.parts = [...long.parts, { ...long.parts[3]!, name: "Fifth" }, { ...long.parts[3]!, name: "Sixth" }];
    long.parts[0]!.questions = Array.from({ length: 7 }, (_, i) => q(`What is point ${i + 1} of the closure of Ashby's public library?`));
    const checked = checkPlan(long);
    expect(checked.errors).toEqual([]);
    expect(checked.value!.parts).toHaveLength(PLAN_LIMITS.parts);
    expect(checked.value!.parts[0]!.questions).toHaveLength(PLAN_LIMITS.questions);
    expect(checked.warnings.map((w) => w.path)).toEqual(expect.arrayContaining(["parts", "parts[0]"]));
  });

  it("rejects a part listed twice, a key question that refers to another one, and a plan without parts", () => {
    const bad = clone();
    bad.parts[1]!.name = "the closure";
    bad.parts[2]!.questions[0] = q("What do studies say about the previous question?");
    const messages = checkPlan(bad).errors.map((e) => `${e.path}: ${e.message}`);
    expect(messages.some((m) => m.startsWith("parts[1]") && m.includes("listed twice"))).toBe(true);
    expect(messages.some((m) => m.startsWith("parts[2].questions[0]") && m.includes("refers to another question"))).toBe(true);
    expect(checkPlan({ ...clone(), parts: [] }).errors.map((e) => e.path)).toEqual(["parts"]);
  });

  it("keeps an out-of-scope request without parts or claims", () => {
    const out = checkPlan({ status: "out_of_scope", status_reason: "The request asks for a poem.", restated_request: "The client asks for a poem.", subject: "a poem" });
    expect(out.errors).toEqual([]);
    expect(out.value).toMatchObject({ status: "out_of_scope", status_reason: "The request asks for a poem.", parts: [], claims: [] });
  });

  it("falls back to the parts no error points to, and cuts a key question whose only fault is its length", () => {
    const bad = clone();
    bad.parts[1]!.objective = "Explain the reasons named in the first question.";
    bad.parts[0]!.questions[0] = q(`Did the town of Ashby close its public library? ${"Give every detail. ".repeat(30)}`);
    bad.parts[2]!.questions[1] = q("And what about the earlier questions?");
    const checked = checkPlan(bad);
    const kept = validParts(checked.value!, checked.errors)!;
    expect(kept.parts.map((p) => p.name)).toEqual(["The closure", "Alternatives"]);
    expect(kept.parts[0]!.questions[0]!.text.length).toBeLessThanOrEqual(PLAN_LIMITS.question);
    const none = checkPlan({ ...clone(), parts: [{ ...clone().parts[0]!, questions: [q("One question only?")] }] });
    expect(validParts(none.value!, none.errors)).toBeNull();
  });
});

describe("the analysis built from a plan", () => {
  const a = analysisFromPlan(PLAN, QUESTION);

  it("has one object for the subject, the claims as assumptions, and no model of the wording", () => {
    expect(a.rom.objects.map((o) => [o.id, o.text, o.status])).toEqual([["O1", PLAN.subject, "self_evident"]]);
    expect(a.rom.relations).toEqual([]);
    expect(a.assumptions.map((x) => [x.id, x.claim])).toEqual([["A1", PLAN.claims[0]!.claim], ["A2", PLAN.claims[1]!.claim]]);
    expect(a.frame.time_frame).toEqual({ value: "Latest available evidence as of 2026-11-19.", basis: "default", evidence: [] });
  });

  it("plans one check for the claims marked check, and the client's question as the synthesis question", () => {
    expect(a.questions.map((x) => [x.id, x.route, x.template, x.verifies, x.depends_on])).toEqual([
      ["Q1", "search", "T7", ["A1"], []],
      ["Q2", "synthesis", "T1", [], ["Q1"]],
    ]);
    expect(a.questions[0]!.text).toBe("Is it true that: The town of Ashby closed its public library in 2019? What does the evidence show for this claim, and if it is wrong, what holds instead?");
    expect(checkQuestion(["A is so.", "B is so"])).toContain("Is it true that: A is so; and B is so? What does the evidence show for each of these claims");
    expect(a.questions[1]!.done_when).toContain("The closure; Reasons; What a library does for a small town; Alternatives");
    const none = analysisFromPlan({ ...clone(), claims: [clone().claims[1]!] }, QUESTION);
    expect(none.questions.map((x) => [x.id, x.route])).toEqual([["Q1", "synthesis"]]);
  });

  it("keeps a directive's quote only when the request holds those words, and gives an ambiguous term its readings", () => {
    expect(a.client_directives).toEqual([{ kind: "report_format", text: "Present the reasons as a list.", evidence: [] }]);
    const withTerm = analysisFromPlan({ ...clone(), terms: [{ term: "library", meaning: "a public lending library", other_meanings: ["a software library"] }, { term: "Ashby", meaning: "the town named in the request", other_meanings: [] }] }, QUESTION);
    expect(withTerm.rom.objects.slice(1).map((o) => [o.id, o.text, o.readings])).toEqual([["O2", "library", ["a public lending library", "a software library"]], ["O3", "Ashby", []]]);
  });
});

describe("init in the environment mode", () => {
  it("makes the whole first plan in one call: a goal for each main part, with its key questions as written", async () => {
    const { model, calls } = planner(PLAN);
    const step = await create().init({ question: QUESTION }, ctx(model));
    const s = step.state as EbdState;
    expect(calls).toEqual([PLAN_TOOL]);
    expect(s.step.calls.map((c) => c.role)).toEqual(["environment_analyst"]);
    expect(s.init).toMatchObject({ mode: "environment", accepted: true, fallback: false, attempts: 1 });
    expect(s.goals.map((g) => [g.id, g.kind, g.need, g.origin.type])).toEqual([
      ["Q1", "verify", "necessary", "request"],
      ["Q3", "define", "necessary", "assumed"],
      ["Q4", "define", "necessary", "assumed"],
      ["Q5", "define", "necessary", "assumed"],
      ["Q6", "define", "completing", "assumed"],
    ]);
    expect(s.map).toMatchObject({ subject: PLAN.subject });
    expect(s.map!.events.map((e) => [e.id, e.name, e.goalId, e.parts.length])).toEqual([["E1", "The closure", "Q3", 3], ["E2", "Reasons", "Q4", 3], ["E3", "What a library does for a small town", "Q5", 2], ["E4", "Alternatives", "Q6", 2]]);
    expect(s.premises).toEqual({ given: [{ id: "A2", reason: "The possibility the question asks about." }] });
    expect(s.plan).toEqual({ notStated: PLAN.not_stated });
    expect(step.decision.rationale).toContain("Environment analysis (one call, accepted after 1 attempt(s)): 4 main part(s) of the answer with 10 key questions, 2 claim(s) of the question.");
    expect(step.decision.rationale).toContain("Claims to check: A1");
    expect(step.decision.rationale).toContain("Taken as given, because they only restate what the question asks about: A2");
  });

  it("gives each necessary part a researcher, asks the check at the head of one of them, and tells the researcher what the questions are", async () => {
    const { model } = planner(PLAN);
    const step = await create().init({ question: QUESTION }, ctx(model));
    const briefs = step.decision.briefs;
    expect(briefs.map((b) => b.tag)).toEqual(expect.arrayContaining(["Q3", "Q4"]));
    // No researcher only checks the claim: the check leads a brief that asks for content.
    const carrier = briefs.find((b) => (b.tag ?? "").split(",").includes("Q1"))!;
    expect((carrier.tag ?? "").split(",").length).toBeGreaterThan(1);
    expect(carrier.keyQuestions[0]).toMatch(/^\[Q1\] Is it true that: The town of Ashby closed its public library in 2019\?/);
    expect(carrier.instructions).toContain(VERIFY_INSTRUCTION);
    // The key questions are asked as the analyst wrote them, under their goal's ID.
    const closure = briefs.find((b) => (b.tag ?? "").split(",").includes("Q3"))!;
    expect(closure.keyQuestions).toEqual(expect.arrayContaining(PLAN.parts[0]!.questions.map((x) => `[Q3] ${x.text}`)));
    expect(closure.instructions).toContain(`For [Q3], the objective is: ${PLAN.parts[0]!.objective} ${PLAN_QUESTIONS_INSTRUCTION}`);
    expect(closure.constraints).toContain(`Not stated by the client: ${PLAN.not_stated[0]}`);
    for (const b of briefs) expect(b.keyQuestions.length).toBeLessThanOrEqual(6);
    // Every necessary part is asked in round 1, each by its key questions.
    const asked = briefs.flatMap((b) => b.keyQuestions).join("\n");
    for (const part of PLAN.parts.slice(0, 3)) for (const x of part.questions) expect(asked).toContain(x.text);
  });

  it("makes one model call, and asks the key questions one by one", async () => {
    const { model, calls } = planner(PLAN);
    const step = await create().init({ question: QUESTION }, ctx(model));
    expect(calls).toEqual([PLAN_TOOL]);
    expect(step.decision.briefs.some((b) => b.keyQuestions.includes(`[Q4] ${PLAN.parts[1]!.questions[0]!.text}`))).toBe(true);
  });

  it("at most four parts are necessary, and a plan without a necessary part gets one", async () => {
    const five = clone();
    five.parts = [...five.parts.map((p) => ({ ...p, need: "necessary" as const })), { ...five.parts[3]!, name: "Fifth", need: "necessary" as const }];
    const a = await create().init({ question: QUESTION }, ctx(planner(five).model));
    expect((a.state as EbdState).goals.filter((g) => g.origin.type === "assumed").map((g) => g.need)).toEqual(["necessary", "necessary", "necessary", "necessary", "completing"]);
    const none = clone();
    none.parts = none.parts.map((p) => ({ ...p, need: "completing" as const }));
    const b = await create().init({ question: QUESTION }, ctx(planner(none).model));
    expect((b.state as EbdState).goals.filter((g) => g.origin.type === "assumed").map((g) => g.need)).toEqual(["necessary", "completing", "completing", "completing"]);
  });

  it("stops at once on a request that is out of scope", async () => {
    const { model } = planner({ status: "out_of_scope", status_reason: "The request asks for a poem.", restated_request: "The client asks for a poem.", subject: "a poem" });
    const step = await create().init({ question: "Write me a poem about libraries." }, ctx(model));
    expect(step.decision).toMatchObject({ briefs: [], stop: true });
    expect((step.state as EbdState).stop).toMatchObject({ kind: "out_of_scope", reason: "The request asks for a poem." });
  });

  it("retries once with the errors, and uses the valid parts when the retry fails too", async () => {
    const bad = clone();
    bad.parts[1]!.objective = "Explain the reasons named in the first question.";
    const { model, calls } = planner(bad, bad);
    const step = await create().init({ question: QUESTION }, ctx(model));
    const s = step.state as EbdState;
    expect(calls).toHaveLength(2);
    expect(s.init).toMatchObject({ accepted: false, fallback: true, attempts: 2, stopReason: "attempts exhausted" });
    expect(s.map!.events.map((e) => e.name)).toEqual(["The closure", "What a library does for a small town", "Alternatives"]);
    expect(s.problems[0]).toContain("environment analysis fell back to its valid parts after 2 attempts");
  });

  it("throws the first time a run gets no usable plan, and then plans the request itself as one question", async () => {
    const { model } = planner({ status: "ok" });
    const strategy = create();
    await expect(strategy.init({ question: QUESTION }, ctx(model))).rejects.toThrow("Environment analysis produced no usable plan");
    const step = await strategy.init({ question: QUESTION }, ctx(model));
    const s = step.state as EbdState;
    expect(s.init).toMatchObject({ mode: "environment", accepted: false, fallback: true, stopReason: "minimal plan" });
    expect(s.map).toBeNull();
    expect(s.goals.map((g) => [g.id, g.text])).toEqual([["Q1", QUESTION]]);
    expect(s.problems[0]).toContain("the plan is the request itself as one question");
    expect(step.decision.briefs).toHaveLength(1);
  });
});

// ---------------------------------------------------------------- one whole run, without network

function block(message: string, tag: string): string {
  return new RegExp(`<${tag}>\\n([\\s\\S]*?)\\n</${tag}>`).exec(message)?.[1] ?? "";
}

/** A researcher that answers every key question of its brief with two cited findings. */
const research = async (_q: string, brief: ResearchBrief): Promise<ResearchResult> => ({
  brief,
  status: "ok",
  notes: brief.keyQuestions
    .map((k, i) => {
      const check = k.startsWith("[Q1]");
      return [
        `## ${k}`,
        "### Takeaway",
        check ? "The library closed in 2021, not in 2019." : `Takeaway ${i + 1}.`,
        "### Cited Findings",
        `- ${check ? "The council closed the library on 30 June 2021 (CONTRADICTS)." : `A finding for key question ${i + 1}.`} — [Source](https://a${i}.example/${brief.id})`,
        `- ${check ? "The local paper reports the closure in 2021 (CONTRADICTS)." : `A second finding for key question ${i + 1}.`} — [Source](https://b${i}.example/${brief.id})`,
        "### Gaps",
        "- Nothing more was found.",
      ].join("\n");
    })
    .join("\n\n"),
  sources: [],
  queries: [],
  usage: { inputTokens: 0, outputTokens: 0, searches: 1, pageReads: 0 },
  model: "fake",
  durationMs: 0,
  unlistedCitations: [],
  diagnostics: [],
});

/** The round analyst: every key question listed under "Judge only" is met by the goal's first finding. */
function judge(message: string) {
  const judgments = block(message, "served_goals")
    .split(/\n(?=### )/)
    .map((g) => {
      const id = /^### (Q\d+)/.exec(g)![1]!;
      const findings = [...g.matchAll(/^(r\d+-b\d+-f\d+) (.*)$/gm)].map((m) => ({ id: m[1]!, text: m[2]! }));
      const first = findings[0]?.id;
      const claims = [...g.matchAll(/^- (A\d+): /gm)].map((m) => m[1]!);
      const planned = /^Judge only: (.*)$/m.exec(g)?.[1];
      const parts = planned !== undefined ? planned.split(", ").filter((p) => /^M\d+$/.test(p)).map((p) => ({ part: `${p} answered`, met: Boolean(first), evidence: first ? [first] : [] })) : [{ part: "the claim", met: Boolean(first), evidence: first ? [first] : [] }];
      return { goal_id: id, parts, outcome: first ? "answered" : "not_found", verdicts: claims.map((c) => ({ claim_id: c, verdict: findings.some((f) => f.text.includes("CONTRADICTS")) ? "contradicted" : "supported" })), missing: [] };
    });
  return { judgments, proposals: [] };
}

describe("a whole run in the environment mode, through the skeleton", () => {
  it("plans in one call, researches the main parts, judges the checked claim and hands the notes to the writer", async () => {
    const calls: string[] = [];
    const model = {
      bindTools: (tools: { function: { name: string } }[]) => ({
        invoke: async (messages: BaseMessage[]) => {
          const name = tools[0]!.function.name;
          calls.push(name);
          const args = name === PLAN_TOOL ? PLAN : name === "submit_conflicts" ? { conflicts: [] } : judge(String(messages.at(-1)!.content));
          return new AIMessage({ content: "", tool_calls: [{ id: `c${calls.length}`, name, args: args as Record<string, unknown>, type: "tool_call" }] });
        },
      }),
    } as unknown as BaseChatModel;
    const decisions: DecisionRecord[] = [];
    let synthesis: { material: { label: string; notes: string }[]; outline?: string[]; guidance?: string } | undefined;
    const graph = buildResearchGraph({
      strategy: create(),
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
    expect(calls[0]).toBe(PLAN_TOOL);
    expect(calls.filter((c) => c === PLAN_TOOL)).toHaveLength(1);
    expect(calls).not.toContain("submit_analysis");
    expect(calls).not.toContain("submit_premise_sort");
    expect(calls).not.toContain("submit_extension");
    // Round 1 serves the check and the three necessary parts with at most four researchers.
    const first = decisions[0]!.accepted.flatMap((b) => (b.tag ?? "").split(","));
    expect(first).toEqual(expect.arrayContaining(["Q1", "Q3", "Q4", "Q5"]));
    expect(decisions[0]!.accepted.length).toBeLessThanOrEqual(4);
    // Every key question of a researched part is confirmed in the map, and the goals are answered.
    const goal = (id: string) => state.goals.find((g) => g.id === id)!;
    for (const id of ["Q3", "Q4", "Q5"]) expect(goal(id).status).toBe("answered");
    expect(state.map!.events[0]!.parts.every((p) => p.status === "confirmed")).toBe(true);
    // The checked claim was contradicted; the claim taken as given gets no verdict and no line.
    expect(goal("Q1").verdicts).toEqual({ A1: "contradicted" });
    // Section 34: the contradicted claim is corrected in a sentence or two, and the question is then answered as asked.
    expect(synthesis!.guidance).toContain('The question takes for granted:\n- "The town of Ashby closed its public library in 2019."\nThe evidence in the notes contradicts this. Say so in the opening paragraph, in one or two sentences with the source. Then answer the question the client asked as fully as the notes allow: the correction is not the subject of the report.');
    expect(synthesis!.guidance).not.toContain("The question was read as");
    expect(synthesis!.guidance).not.toContain("A library can help a small town.");
    // No goal waited behind the check, so nothing was cancelled with it.
    expect(state.goals.filter((g) => g.status === "moot")).toEqual([]);
    expect(synthesis!.material.map((m) => m.label)).toEqual(expect.arrayContaining(PLAN.parts.slice(0, 3).map((p) => p.objective)));
  });
});
