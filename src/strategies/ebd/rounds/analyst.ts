/**
 * The round analyst (design section 10): one model call per round. For each
 * goal served in the round it splits done_when into parts and marks each part
 * met or not, citing evidence line IDs; for verification goals it gives the
 * verdict on the claim. It may propose new goals, each citing the line that
 * prompted it. Code applies the evidence floor, settles goals, accepts or
 * rejects proposals and makes goals moot. The model never decides whether the
 * research as a whole is sufficient (section 11).
 */
import { z } from "zod";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { GUIDELINES, TEMPLATES, type Issue } from "../request/index.js";
import { assumptionVerdicts, judgesClaim, newGoal, nextGoalId, requeueOrExhaust, settle, synthesisQuestions } from "../goals.js";
import { structuredCall, zodIssues, type CallOutcome, type Checked } from "../llm.js";
import type { EbdOptions } from "../options.js";
import { isSettled, type EbdState, type EvidenceLine, type Goal } from "../state.js";
import { independentHosts } from "./evidence.js";

export const ANALYST_TOOL = "submit_round_analysis";

export const RoundApiSchema = z.object({
  judgments: z.array(
    z.object({
      goal_id: z.string(),
      parts: z.array(
        z.object({
          part: z.string().describe("One part of done_when"),
          met: z.boolean(),
          evidence: z.array(z.string()).describe("Finding IDs that meet this part; empty when not met"),
        }),
      ),
      outcome: z.enum(["answered", "partial", "not_found", "conflicting"]),
      verdict: z.enum(["supported", "contradicted", "unsettled", "not_applicable"]).describe("Verification goals: what the evidence says about the claim. Other goals: not_applicable"),
      missing: z.array(z.string()).describe("The parts still missing; empty when answered"),
    }),
  ),
  proposals: z.array(
    z.object({
      text: z.string().describe("The new question, self-contained: full names, place and time"),
      template: z.enum(TEMPLATES),
      need: z.enum(["necessary", "completing"]),
      object_id: z.string().describe("The existing object (O…) the new goal attaches to"),
      new_object: z.string().describe("A new term the evidence introduced, or empty"),
      new_object_quote: z.string().describe("For a new term: the words copied exactly from a prompting finding; otherwise empty"),
      prompted_by: z.array(z.string()).describe("The finding, gap or conflict IDs that prompted it"),
      leads_to: z.array(z.string()).describe("The necessary goals (Q…) or synthesis questions it serves"),
      done_when: z.string(),
      source_hints: z.array(z.string()).describe("Up to 3 generic kinds of sources"),
    }),
  ),
});
export type RoundReply = z.infer<typeof RoundApiSchema>;

const GUIDELINE_FOR: Record<string, (typeof GUIDELINES)[number]> = { T1: "G1", T2: "G1", T3: "G1", T4: "G6", T5: "G6", T6: "G2", T7: "G7" };
const NUMERIC = /\b(numbers?|amounts?|prices?|costs?|fares?|dates?|percent(age)?s?|rates?|figures?|how much|how many)\b/i;

export const ANALYST_SYSTEM = `You are the round analyst of a research team that follows Environment-Based Design (EBD). Researchers have just answered some research goals. For each goal served in this round you judge, part by part, whether the evidence meets the goal's done_when. You may also propose new goals that the evidence shows are needed. You never decide whether the research as a whole is finished; code does that from your judgments.

Evidence lines have IDs: r2-b1-f3 is a cited finding, r2-b1-g1 is a gap the researcher reported. Conflicts have IDs C1, C2, …. Cite IDs only.

## Judgments: one per goal listed under <served_goals>
- parts: split done_when into its parts (usually 2–5). For each part, met is true only if a cited finding states it; list those finding IDs in evidence. A gap line never meets a part. Inferences, general knowledge and your own reasoning never meet a part.
- Currency: "as of <run date>" or "the latest available evidence" is met by the most recent evidence the sources give, such as a current official page or the latest dated report. It does not require a page's capture date or a source dated on the run date.
- outcome:
  - answered: every part is met;
  - partial: some parts are met, some are not;
  - not_found: no part is met;
  - conflicting: the findings for this goal disagree and a conflict about it is listed under <conflicts>.
- verdict, for a goal with a "Claim to verify": supported if findings state the claim holds; contradicted if findings state it does not hold; unsettled if the findings do not decide it or disagree. For a goal without a claim: not_applicable.
- missing: the unmet parts in a few words each, so the next researcher knows what to look for. Empty when answered.

## Proposals: new goals (EBD: each answer is analysed as new objects and relations, which raise new questions)
Propose a goal only when the evidence shows the research needs it:
- a term that a necessary goal needs but that is not yet defined (for example, which products are "the current flagships" once a finding names them): template T1, the term as new_object, copied exactly from the prompting finding as new_object_quote;
- a part or life-cycle event of an object that a synthesis question depends on: T1 or T3. This includes a step that the findings reveal and no goal covers; for example, a finding that a product must be imported brings in import rules, duties and delivery time. Ask what the step requires, checking the same kinds as the request analysis: natural; built, physical and digital (documents, data, laws, software); economic (costs, prices, time); social (people and organisations). Propose such a goal when the step could change the answer to a synthesis question, even if that question does not name the step; the finding that reveals the step is what prompted it;
- a relation the findings state but leave unverified or contested: T7.
Each proposal attaches to an existing object (object_id), cites what prompted it (prompted_by), and serves a necessary goal or a synthesis question (leads_to). Write the question so that a researcher who sees only it can act: full names, place and time. Keep the client's scope: do not narrow a new goal to one case of something the client did not state (one region, one customer group, one budget) because a finding describes that case; ask for the main cases, or for the case the request itself implies. Do not propose a goal that repeats an existing goal, asks for the final answer itself, merely re-asks a partial goal (partial goals are re-served automatically), or only asks for a date or a capture of a value already found. Propose at most the number given in <limits>; return [] when nothing is needed.

Reply by calling ${ANALYST_TOOL} once with all judgments and proposals.`;

function evidenceLine(e: EvidenceLine): string {
  return `${e.id} ${e.text}`;
}

/** The goals served in the round: every goal named in a brief tag of the round's results. */
export function servedGoals(state: EbdState, round: number): Goal[] {
  const ids = new Set(state.results.filter((r) => r.round === round).flatMap((r) => r.goalIds));
  return state.goals.filter((g) => ids.has(g.id));
}

export function analystMessage(state: EbdState, round: number, served: Goal[], options: EbdOptions): string {
  const a = state.analysis;
  const claims = (g: Goal) => a.assumptions.filter((x) => g.verifies.includes(x.id)).map((x) => `${x.id}: ${x.claim}`);
  const goalBlock = served.map((g) => {
    const lines = state.evidence.filter((e) => e.goalIds.includes(g.id));
    return [
      `### ${g.id} (kind ${g.kind}, ${g.need}, attempt ${g.attempts})`,
      `Question: ${g.text}`,
      `done_when: ${g.doneWhen}`,
      ...(claims(g).length ? [`Claim to verify: ${claims(g).join(" | ")}`] : []),
      ...(g.settles ? [`Settles conflict ${g.settles}`] : []),
      ...(g.missing.length ? [`Missing after the last attempt: ${g.missing.join("; ")}`] : []),
      "Evidence:",
      ...(lines.length ? lines.map(evidenceLine) : ["(none: the researcher reported nothing for this goal)"]),
    ].join("\n");
  });
  const openGoals = state.goals.filter((g) => !isSettled(g)).length;
  const allowed = options.newGoals ? Math.max(0, Math.min(options.maxNewGoalsPerRound - createdThisRound(state, round), options.maxOpenGoals - openGoals)) : 0;
  const roundConflicts = state.conflicts.filter((c) => c.createdRound === round);
  return [
    `<run_date>${state.today}</run_date>`,
    `<question>\n${state.question}\n</question>`,
    `<objects>\n${[...a.rom.objects.map((o) => `${o.id} "${o.text}": ${o.meaning}`), ...state.objectsFound.map((o) => `${o.id} "${o.text}" (found in ${o.evidence})`)].join("\n")}\n</objects>`,
    `<synthesis_questions>\n${synthesisQuestions(a).map((q) => `${q.id} ${q.text}`).join("\n")}\n</synthesis_questions>`,
    `<existing_goals>\n${state.goals.map((g) => `${g.id} [${g.status}, ${g.need}] ${g.text}`).join("\n")}\n</existing_goals>`,
    `<conflicts>\n${roundConflicts.map((c) => `${c.id} ${c.type} about ${c.about}: ${c.statement}`).join("\n") || "(none)"}\n</conflicts>`,
    `<served_goals>\n${goalBlock.join("\n\n")}\n</served_goals>`,
    `<limits>\nNew goals you may propose this round: ${allowed}.${allowed === 0 ? " Return proposals: []." : ""}\n</limits>`,
  ].join("\n");
}

/** Code checks (section 10.1). Judgment errors are retried; proposals are accepted or rejected later by acceptProposals. */
export function checkRound(args: unknown, state: EbdState, served: Goal[]): Checked<RoundReply> {
  // A reply without proposals proposes nothing (live test round 4: Haiku left the field out).
  const input = args && typeof args === "object" && !Array.isArray(args) && !("proposals" in args) ? { ...args, proposals: [] } : args;
  const parsed = RoundApiSchema.safeParse(input);
  if (!parsed.success) return { value: null, errors: zodIssues(parsed.error), warnings: [] };
  const reply = parsed.data;
  const errors: Issue[] = [];
  const warnings: Issue[] = [];
  const findings = new Set(state.evidence.filter((e) => e.kind === "finding").map((e) => e.id));
  const evidence = new Set(state.evidence.map((e) => e.id));
  const conflicts = new Set(state.conflicts.map((c) => c.id));
  const servedIds = new Set(served.map((g) => g.id));
  const judged = new Map<string, number>();

  reply.judgments.forEach((j, i) => {
    const path = `judgments[${i}]`;
    const err = (message: string) => errors.push({ code: "judgment", path, message });
    const goal = served.find((g) => g.id === j.goal_id);
    if (!goal) {
      err(`${j.goal_id} was not served in this round; judge only the goals under <served_goals>`);
      return;
    }
    if (judged.has(j.goal_id)) err(`${j.goal_id} is judged twice`);
    judged.set(j.goal_id, i);
    if (!j.parts.length) err("parts: split done_when into at least one part");
    j.parts.forEach((p, k) => {
      if (p.met && !p.evidence.length) err(`parts[${k}] is met but cites no finding`);
      const unknown = p.evidence.filter((id) => !findings.has(id));
      if (unknown.length) err(`parts[${k}]: ${unknown.join(", ")} ${unknown.some((id) => evidence.has(id)) ? "is a gap line, which cannot meet a part" : "is not a finding ID"}`);
    });
    const met = j.parts.filter((p) => p.met).length;
    if (j.outcome === "answered" && met !== j.parts.length) err("answered needs every part met");
    if (j.outcome === "partial" && (met === 0 || met === j.parts.length)) err("partial needs some parts met and some not");
    if (j.outcome === "not_found" && met > 0) err("not_found cannot have met parts");
    if (j.outcome !== "answered" && !j.missing.length) err("missing: name the unmet parts");
    if (judgesClaim(goal) && j.outcome === "answered" && j.verdict === "not_applicable") err("a goal with a claim to verify needs a verdict: supported, contradicted or unsettled");
    if (!judgesClaim(goal) && j.verdict !== "not_applicable") err(`${goal.id} has no claim to verify; its verdict is not_applicable`);
  });
  for (const id of servedIds) if (!judged.has(id)) errors.push({ code: "judgment_missing", path: "judgments", message: `no judgment for ${id}` });

  reply.proposals.forEach((p, i) => {
    const path = `proposals[${i}]`;
    const unknown = p.prompted_by.filter((id) => !evidence.has(id) && !conflicts.has(id));
    if (!p.prompted_by.length || unknown.length) warnings.push({ code: "proposal", path, message: `prompted_by must cite existing evidence or conflict IDs${unknown.length ? `; unknown: ${unknown.join(", ")}` : ""}` });
  });
  return { value: reply, errors, warnings };
}

const OUTCOME_RANK = { not_found: 0, partial: 1, answered: 2 } as const;

/**
 * The fallback after the last failed attempt (section 5.3): keep the valid parts.
 * Evidence IDs that are not findings are dropped, a met part without evidence
 * becomes unmet, and the outcome is recomputed from the parts, never above what
 * the analyst said. A judgment of a goal that was not served, or a repeated one,
 * is dropped; goals left without a judgment become partial when applied.
 */
export function repairRound(reply: RoundReply, state: EbdState, served: Goal[]): RoundReply {
  const findings = new Set(state.evidence.filter((e) => e.kind === "finding").map((e) => e.id));
  const seen = new Set<string>();
  const judgments: RoundReply["judgments"] = [];
  for (const j of reply.judgments) {
    const goal = served.find((g) => g.id === j.goal_id);
    if (!goal || seen.has(j.goal_id)) continue;
    seen.add(j.goal_id);
    const parts = j.parts.map((p) => {
      const evidence = p.evidence.filter((id) => findings.has(id));
      return { part: p.part, met: p.met && evidence.length > 0, evidence };
    });
    if (!parts.length) continue;
    const met = parts.filter((p) => p.met).length;
    const computed = met === parts.length ? "answered" : met > 0 ? "partial" : "not_found";
    let outcome: RoundReply["judgments"][number]["outcome"] =
      j.outcome === "conflicting" ? "conflicting" : OUTCOME_RANK[computed] < OUTCOME_RANK[j.outcome] ? computed : j.outcome;
    const verdict = judgesClaim(goal) ? j.verdict : "not_applicable";
    const missing = [...j.missing];
    if (judgesClaim(goal) && outcome === "answered" && verdict === "not_applicable") {
      outcome = "partial";
      missing.push("a verdict on the claim");
    }
    if (outcome !== "answered" && !missing.length) missing.push(...parts.filter((p) => !p.met).map((p) => p.part));
    judgments.push({ goal_id: j.goal_id, parts, outcome, verdict, missing });
  }
  return { judgments, proposals: reply.proposals };
}

export function runRoundAnalyst(model: BaseChatModel, state: EbdState, round: number, served: Goal[], options: EbdOptions): Promise<CallOutcome<RoundReply>> {
  return structuredCall({
    model,
    role: "round_analyst",
    system: ANALYST_SYSTEM,
    message: analystMessage(state, round, served, options),
    tool: { name: ANALYST_TOOL, description: "Submit the judgments of the served goals and any new goals the evidence calls for.", schema: RoundApiSchema },
    check: (args) => checkRound(args, state, served),
    fallback: (last) => repairRound(last, state, served),
  });
}

/** New goals made in this round, settle goals included: they share maxNewGoalsPerRound. */
function createdThisRound(state: EbdState, round: number): number {
  return state.goals.filter((g) => g.createdRound === round + 1 && g.origin.type !== "request").length;
}

/** Does the goal need findings from independent hosts (section 10.1)? Verification goals, numbers and dates do. */
export function needsFloor(goal: Goal): boolean {
  return goal.kind === "verify" || goal.kind === "settle" || goal.guideline === "G3" || NUMERIC.test(goal.doneWhen);
}

export type Applied = { settled: string[]; advanced: string[]; requeued: string[]; exhausted: string[] };

/**
 * Apply the judgments (section 10.1). Mutates the state. Served goals without a
 * valid judgment are treated as partial.
 */
export function applyJudgments(state: EbdState, reply: RoundReply | null, served: Goal[], round: number, options: EbdOptions, log: (line: string) => void): Applied {
  const out: Applied = { settled: [], advanced: [], requeued: [], exhausted: [] };
  const byId = new Map(state.evidence.map((e) => [e.id, e]));
  for (const goal of served) {
    if (isSettled(goal)) continue;
    const j = reply?.judgments.find((x) => x.goal_id === goal.id);
    const before = goal.partsMet;
    if (!j) {
      goal.retryNote = null;
      const r = requeueOrExhaust(goal, round, options.maxAttempts, null);
      (r === "exhausted" ? out.exhausted : out.requeued).push(goal.id);
      if (r === "exhausted") out.settled.push(goal.id);
      log(`${goal.id}: no valid judgment, treated as partial → ${r}`);
      continue;
    }
    const metParts = j.parts.filter((p) => p.met);
    const cited = [...new Set(metParts.flatMap((p) => p.evidence))];
    goal.partsTotal = j.parts.length;
    goal.partsMet = metParts.length;
    goal.evidence = [...new Set([...goal.evidence, ...cited])];
    goal.missing = j.missing;
    let outcome = j.outcome;

    if (outcome === "answered" && needsFloor(goal)) {
      const hosts = independentHosts(goal.evidence.map((id) => byId.get(id)).filter((e): e is EvidenceLine => Boolean(e)));
      if (hosts < options.evidenceFloor) {
        outcome = "partial";
        goal.missing = [`confirmation from at least ${options.evidenceFloor} independent sources (found ${hosts})`];
        log(`${goal.id}: answered, but the evidence floor needs ${options.evidenceFloor} independent hosts and found ${hosts} → partial`);
      }
    }
    if (judgesClaim(goal) && j.verdict !== "not_applicable") goal.verdict = j.verdict;

    if (outcome === "conflicting") {
      const conflict = state.conflicts.find((c) => c.status === "open" && c.settleGoal && (c.about === goal.id || goal.objectIds.includes(c.about)));
      if (conflict) {
        goal.status = "conflicting";
        goal.waitingOn = conflict.settleGoal;
        log(`${goal.id}: conflicting, waits for ${conflict.settleGoal} (${conflict.id})`);
        if (goal.partsMet > before) out.advanced.push(goal.id);
        continue;
      }
      // A disagreement that cannot get a settle goal (settleBlock) is disputed, and so is the goal.
      const disputed = state.conflicts.find((c) => c.status === "disputed" && (c.about === goal.id || goal.objectIds.includes(c.about)));
      if (disputed) {
        settle(goal, "disputed", round);
        out.settled.push(goal.id);
        log(`${goal.id}: conflicting, and ${disputed.id} has no settle goal → disputed`);
        continue;
      }
      outcome = "partial";
      goal.missing = goal.missing.length ? goal.missing : ["agreement between the sources"];
      log(`${goal.id}: judged conflicting but no conflict record exists → partial`);
    }

    if (outcome === "answered") {
      settle(goal, "answered", round);
      goal.retryNote = null;
      out.settled.push(goal.id);
      log(`${goal.id}: answered (${goal.partsMet}/${goal.partsTotal} parts${goal.verdict ? `, claim ${goal.verdict}` : ""})`);
      resolveSettle(state, goal, "answered", round, log);
      continue;
    }
    const note = outcome === "not_found" ? "The previous search found nothing for this question; try a different angle: other terms, other kinds of sources, or the primary record." : null;
    const r = requeueOrExhaust(goal, round, options.maxAttempts, note);
    if (r === "exhausted") {
      out.exhausted.push(goal.id);
      out.settled.push(goal.id);
      resolveSettle(state, goal, "exhausted", round, log);
    } else {
      out.requeued.push(goal.id);
      if (goal.partsMet > before) out.advanced.push(goal.id);
    }
    log(`${goal.id}: ${outcome} (${goal.partsMet}/${goal.partsTotal} parts) → ${r}${goal.missing.length ? `; missing: ${goal.missing.join("; ")}` : ""}`);
  }
  return out;
}

/** When a settle goal settles, its conflict and the goal waiting on it settle too (sections 9 and 10.1). */
function resolveSettle(state: EbdState, goal: Goal, how: "answered" | "exhausted", round: number, log: (line: string) => void): void {
  if (!goal.settles) return;
  const conflict = state.conflicts.find((c) => c.id === goal.settles);
  if (!conflict || conflict.status !== "open") return;
  conflict.status = how === "answered" ? "settled" : "disputed";
  conflict.settledRound = round;
  for (const waiting of state.goals.filter((g) => g.waitingOn === goal.id && g.status === "conflicting")) {
    settle(waiting, how === "answered" ? "answered" : "disputed", round);
    waiting.evidence = [...new Set([...waiting.evidence, ...goal.evidence])];
    // The settled account replaces the verdict given while the sources disagreed, but only when the
    // disagreement decided the claim; a settle goal about a detail leaves the verdict as judged (section 9).
    if (judgesClaim(waiting) && judgesClaim(goal)) waiting.verdict = how === "answered" ? (goal.verdict ?? waiting.verdict) : "unsettled";
    log(`${waiting.id}: ${waiting.status} after ${goal.id}`);
  }
  log(`${conflict.id}: ${conflict.status}`);
}

function words(text: string): Set<string> {
  return new Set(text.toLowerCase().match(/[a-z0-9]+/g) ?? []);
}

function similar(a: string, b: string): boolean {
  const x = words(a);
  const y = words(b);
  const shared = [...x].filter((w) => y.has(w)).length;
  return shared / Math.max(1, new Set([...x, ...y]).size) >= 0.7;
}

/**
 * Accept or reject each proposal (section 10.2). Accepted proposals become goals
 * served from the next round. Returns the new goals; rejections are logged.
 */
export function acceptProposals(state: EbdState, reply: RoundReply | null, round: number, options: EbdOptions, log: (line: string) => void): Goal[] {
  if (!reply?.proposals.length) return [];
  if (!options.newGoals) {
    log(`${reply.proposals.length} proposal(s) ignored: newGoals is off`);
    return [];
  }
  const objects = new Set([...state.analysis.rom.objects.map((o) => o.id), ...state.objectsFound.map((o) => o.id)]);
  const necessary = new Set(state.goals.filter((g) => g.need === "necessary").map((g) => g.id));
  const synthesis = new Set(synthesisQuestions(state.analysis).map((q) => q.id));
  const byEvidence = new Map(state.evidence.map((e) => [e.id, e]));
  const added: Goal[] = [];

  reply.proposals.forEach((p, i) => {
    const reject = (why: string) => log(`proposal ${i + 1} rejected (${why}): ${p.text.slice(0, 160)}`);
    const prompts = p.prompted_by.filter((id) => byEvidence.has(id) || state.conflicts.some((c) => c.id === id));
    if (!prompts.length) return reject("cites no existing evidence or conflict");
    if (!objects.has(p.object_id)) return reject(`unknown object ${p.object_id}`);
    const leads = p.leads_to.filter((id) => necessary.has(id) || synthesis.has(id));
    if (!leads.length) return reject("leads to no necessary goal or synthesis question");
    if (!p.text.trim() || p.text.length > 400 || !p.done_when.trim() || p.done_when.length > 400) return reject("text or done_when empty or longer than 400 characters");
    const parents = prompts.flatMap((id) => byEvidence.get(id)?.goalIds ?? [state.conflicts.find((c) => c.id === id)?.about ?? ""]);
    const depth = 1 + Math.max(0, ...parents.map((id) => state.goals.find((g) => g.id === id)?.depth ?? 0));
    if (depth > options.maxDepth) return reject(`depth ${depth} exceeds maxDepth ${options.maxDepth}`);
    let objectIds = [p.object_id];
    if (p.new_object.trim()) {
      const quoteFound = prompts.some((id) => byEvidence.get(id)?.kind === "finding" && byEvidence.get(id)!.text.toLowerCase().includes(p.new_object_quote.trim().toLowerCase()));
      if (!p.new_object_quote.trim() || !quoteFound) return reject("a new object needs a quote copied exactly from a prompting finding");
      const existing = state.objectsFound.find((o) => o.text.toLowerCase() === p.new_object.trim().toLowerCase());
      if (existing) objectIds = [existing.id, p.object_id];
      else {
        const used = [...state.analysis.rom.objects, ...state.objectsFound].map((o) => Number(o.id.slice(1)) || 0);
        const id = `O${Math.max(0, ...used) + 1}`;
        const evidenceId = prompts.find((x) => byEvidence.get(x)?.text.toLowerCase().includes(p.new_object_quote.trim().toLowerCase()))!;
        state.objectsFound.push({ id, text: p.new_object.trim(), parent: p.object_id, quote: p.new_object_quote.trim(), evidence: evidenceId, round });
        objectIds = [id, p.object_id];
      }
    }
    const duplicate = state.goals.find((g) => (g.template === p.template && g.objectIds[0] === objectIds[0]) || similar(g.text, p.text));
    if (duplicate) return reject(`duplicates ${duplicate.id}`);
    if (createdThisRound(state, round) >= options.maxNewGoalsPerRound) return reject(`quota of ${options.maxNewGoalsPerRound} new goals per round reached (settle goals included)`);
    if (state.goals.filter((g) => !isSettled(g)).length >= options.maxOpenGoals) return reject(`${options.maxOpenGoals} open goals reached`);
    const kind = byEvidence.get(prompts[0]!)?.kind;
    const goal = newGoal({
      id: nextGoalId(state),
      text: p.text.trim(),
      objectIds,
      template: p.template,
      guideline: GUIDELINE_FOR[p.template]!,
      need: p.need,
      doneWhen: p.done_when.trim(),
      sourceHints: p.source_hints.slice(0, 3),
      origin: byEvidence.has(prompts[0]!) ? { type: kind === "gap" ? "gap" : "finding", evidence: prompts } : { type: "conflict", conflict: prompts[0]! },
      depth,
      leadsTo: leads,
      createdRound: round + 1,
    });
    state.goals.push(goal);
    added.push(goal);
    log(`${goal.id} created (${goal.kind}, ${goal.need}, depth ${depth}) from ${prompts.join(", ")}: ${goal.text.slice(0, 160)}`);
  });
  return added;
}

/** Verdicts for the rationale and the writer. */
export function verdictSummary(state: EbdState): string[] {
  const verdicts = assumptionVerdicts(state);
  return state.analysis.assumptions.map((x) => `${x.id} ${verdicts[x.id] ?? "not yet judged"}: ${x.claim}`);
}
