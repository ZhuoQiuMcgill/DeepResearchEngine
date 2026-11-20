/**
 * The premise sort (design section 27): one small model call after the request analysis and before
 * any search. For each claim the question takes for granted it says whether the team checks the
 * claim as a fact of its own or takes it as given. It never says whether a claim is true: without a
 * search that would be a guess, and a strategy may not search (docs/strategy-modules.md, rule 2).
 *
 * Code applies the result. A claim to check keeps its goal, which is asked in round 1. A planned
 * question that only checks claims taken as given stops being a check: it keeps its text as a
 * question for content, no verdict is asked for, and nothing waits for it. The evidence can still
 * overrule a claim taken as given: the conflict checker reports findings against it (section 9),
 * and the goal that settles such a conflict gives the claim its verdict.
 */
import { z } from "zod";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { levelOf } from "./goals.js";
import { structuredCall, zodIssues, type CallOutcome, type Checked } from "./llm.js";
import type { Issue } from "./request/index.js";
import type { EbdState } from "./state.js";

export const PREMISE_TOOL = "submit_premise_sort";

export const PREMISE_SYSTEM = `You are the premise sorter of a research team that follows Environment-Based Design (EBD). The request analysis has listed the claims that the client's question takes for granted. Before any search, you decide for each claim whether the team checks it as a fact of its own or takes it as given. You do not judge whether a claim is true, and you do not answer the question.

check: the claim states a specific fact that the question treats as settled and that could simply be wrong. Such a claim names a particular event that is said to have happened, a date or a period, a number or an amount, who did, made, won, said or decided something, the reason or cause of a particular event, a place, or a particular property of a named thing or person. If it were wrong, the question as asked would have to be corrected before it could be answered.

given: the claim only restates, in general terms, what the question itself asks about: that its subject exists, matters, has effects, can help, can work or can be done. It holds no particular event, date, number, name or cause. A claim that the question's own words spell out, such as the long form of an abbreviation, is given too. How far such a claim holds is what the research on the question shows, so it needs no check of its own.

Rules:
- Judge from the wording of the claim and of the question, never from what you believe to be true. A specific fact you are sure of is still check; a general restatement you doubt is still given.
- A question that asks why or how a particular thing happened, was done or was decided takes that thing for granted as a specific fact: check. This includes a cause stated as fact that the question asks to explain.
- A question that asks whether, which, what or how much takes at most a possibility for granted: given.
- A claim that joins a general part and a specific fact is check. When you cannot tell, choose check.
- Give one verdict for every claim listed, under its ID, with a reason of at most 15 words.

Examples:
- "Why did the city close its airport in 2019?" Claim: "The city closed its airport in 2019." check: a particular event with a date.
- "Which diets can lower blood pressure?" Claim: "Some diets can lower blood pressure." given: the possibility the question asks about.
- "Why is biodiversity important?" Claim: "Biodiversity is important." given: restates the subject in general terms.
- "How did the founder's 2010 patent change the market?" Claim: "The founder held a patent in 2010." check: who held what, and when.
- "Why does cold weather cause colds?" Claim: "Cold weather causes colds." check: a cause stated as fact, which the question asks to explain.

Reply by calling ${PREMISE_TOOL} once.`;

export const PremiseSchema = z.object({
  claims: z.array(
    z.object({
      id: z.string().describe("The claim's ID (A…)"),
      verdict: z.enum(["check", "given"]),
      reason: z.string().describe("At most 15 words: what in the claim decided it"),
    }),
  ),
});
export type PremiseReply = z.infer<typeof PremiseSchema>;

export function premiseMessage(state: Pick<EbdState, "question" | "analysis">): string {
  return [`<question>\n${state.question}\n</question>`, `<claims>\n${state.analysis.assumptions.map((x) => `${x.id}: ${x.claim}`).join("\n")}\n</claims>`].join("\n");
}

/** Code checks: one verdict for each claim of the analysis, and for no other. */
export function checkPremises(args: unknown, state: Pick<EbdState, "analysis">): Checked<PremiseReply> {
  const parsed = PremiseSchema.safeParse(args);
  if (!parsed.success) return { value: null, errors: zodIssues(parsed.error), warnings: [] };
  const errors: Issue[] = [];
  const known = new Set(state.analysis.assumptions.map((x) => x.id));
  const seen = new Set<string>();
  parsed.data.claims.forEach((c, i) => {
    if (!known.has(c.id)) errors.push({ code: "premise", path: `claims[${i}]`, message: `${c.id} is not a claim of the question; the claims are ${[...known].join(", ")}` });
    else if (seen.has(c.id)) errors.push({ code: "premise", path: `claims[${i}]`, message: `${c.id} has two verdicts` });
    seen.add(c.id);
  });
  const missing = [...known].filter((id) => !seen.has(id));
  if (missing.length) errors.push({ code: "premise", path: "claims", message: `no verdict for ${missing.join(", ")}` });
  return { value: parsed.data, errors, warnings: [] };
}

/** The fallback: the first verdict on each claim of the question. A claim left without one is checked. */
export function validPremises(reply: PremiseReply, state: Pick<EbdState, "analysis">): PremiseReply {
  const known = new Set(state.analysis.assumptions.map((x) => x.id));
  const seen = new Set<string>();
  return { claims: reply.claims.filter((c) => known.has(c.id) && !seen.has(c.id) && Boolean(seen.add(c.id))) };
}

export function runPremiseSort(model: BaseChatModel, state: Pick<EbdState, "question" | "analysis">): Promise<CallOutcome<PremiseReply>> {
  return structuredCall({
    model,
    role: "premise_sorter",
    system: PREMISE_SYSTEM,
    message: premiseMessage(state),
    tool: { name: PREMISE_TOOL, description: "Submit one verdict, check or given, for every claim listed.", schema: PremiseSchema },
    check: (args) => checkPremises(args, state),
    fallback: (last) => validPremises(last, state),
  });
}

/** The IDs of the claims taken as given. Empty when the sort is off, failed, or the state predates it. */
export function givenClaims(state: Pick<EbdState, "premises">): Set<string> {
  return new Set((state.premises?.given ?? []).map((g) => g.id));
}

/** Record the sort in the state. A claim without a verdict of "given" is checked. */
export function recordSort(state: EbdState, reply: PremiseReply, log: (line: string) => void): void {
  const claims = new Map(state.analysis.assumptions.map((x) => [x.id, x.claim]));
  state.premises = { given: reply.claims.filter((c) => c.verdict === "given" && claims.has(c.id)).map((c) => ({ id: c.id, reason: c.reason.trim().slice(0, 200) })) };
  for (const c of reply.claims) log(`${c.id} "${claims.get(c.id) ?? ""}": ${c.verdict === "given" ? "taken as given" : "to be checked"} (${c.reason.trim().slice(0, 200)})`);
}

/**
 * Apply the sort to the plan, after the extension step. Mutates the state and returns the IDs of the
 * planned questions that stopped being checks.
 *
 * A planned question loses the claims taken as given from what it verifies. When none is left it is
 * no longer a check: its kind follows its template without the verification, so its brief carries no
 * instruction to verify, and no verdict is asked for. With necessary life-cycle steps in the plan it
 * is then treated like a question the steps replace (section 19): a completing goal that shares a
 * researcher, and what waited for it waits for the steps instead. Without them it stays as it was
 * planned, and what waited for it no longer waits: nothing is verified first.
 */
export function applyGiven(state: EbdState, log: (line: string) => void): string[] {
  const given = givenClaims(state);
  if (!given.size) return [];
  const events = state.goals.filter((g) => g.origin.type === "assumed");
  const steps = events.filter((g) => g.need === "necessary").map((g) => g.id);
  const freed: string[] = [];
  for (const goal of state.goals) {
    if (goal.origin.type !== "request" || !goal.verifies.some((c) => given.has(c))) continue;
    const dropped = goal.verifies.filter((c) => given.has(c));
    goal.verifies = goal.verifies.filter((c) => !given.has(c));
    if (goal.verifies.length) {
      log(`${goal.id}: still checks ${goal.verifies.join(", ")}; ${dropped.join(", ")} taken as given`);
      continue;
    }
    goal.kind = ["T1", "T2", "T3", "T6"].includes(goal.template) ? "define" : "relate";
    if (state.map && steps.length) {
      goal.need = "completing";
      state.map.replaced[goal.id] ??= events.map((g) => g.id);
      for (const g of state.goals) {
        if (g.dependsOn.includes(goal.id)) g.dependsOn = [...new Set(g.dependsOn.flatMap((d) => (d === goal.id ? steps : [d])))].filter((d) => d !== g.id);
      }
    } else {
      for (const g of state.goals) g.dependsOn = g.dependsOn.filter((d) => d !== goal.id);
    }
    goal.level = levelOf(goal.kind, goal.need);
    freed.push(goal.id);
    log(`${goal.id}: no longer a check, because ${dropped.join(", ")} ${dropped.length > 1 ? "are" : "is"} taken as given; ${state.map && steps.length ? "it stays as a completing question beside the life-cycle steps" : "it stays as a question for content"}`);
  }
  return freed;
}
