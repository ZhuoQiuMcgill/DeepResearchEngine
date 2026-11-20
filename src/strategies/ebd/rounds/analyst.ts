/**
 * The round analyst (design section 10): one model call per round. For each
 * goal served in the round it splits done_when into parts and marks each part
 * met or not, citing evidence line IDs; for goals that check claims it gives a
 * verdict on each claim. It may propose new goals, each citing the line that
 * prompted it; with the follow-up rules of section 20, a necessary goal for a
 * main part of the answer that no finding mentions cites nothing (section 26).
 * Code applies the evidence floor, settles goals, accepts or
 * rejects proposals and makes goals moot. The model never decides whether the
 * research as a whole is sufficient (section 11).
 */
import { z } from "zod";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { GUIDELINES, TEMPLATES, type Issue } from "../analysis.js";
import { assumptionVerdicts, newGoal, nextGoalId, requeueOrExhaust, settle, synthesisQuestions } from "../goals.js";
import { structuredCall, zodIssues, type CallOutcome, type Checked } from "../llm.js";
import type { EbdOptions } from "../options.js";
import { EVENT_COVERED, closeEvent, isCovered, liveParts, overwritePart, syncGoal } from "../map.js";
import { eventOf, isCritical, isSettled, type EbdState, type EvidenceLine, type Goal, type MapEvent, type MapPart } from "../state.js";
import { independentHosts } from "./evidence.js";

export const ANALYST_TOOL = "submit_round_analysis";

const PART = {
  part: z.string().describe("One part of done_when"),
  met: z.boolean(),
  evidence: z.array(z.string()).describe("Finding IDs that meet this part; empty when not met"),
};
/** With an environment map (section 19): a planned part can also be refuted by the findings. */
const MAP_PART = {
  part: z.string().describe("One part of done_when, or a planned part starting with its ID (M…)"),
  met: z.boolean(),
  refuted: z.boolean().optional().describe("Planned parts only: true when a cited finding states the part does not exist or does not apply"),
  correction: z.string().optional().describe("For a refuted part: what the findings say instead, in a few words; otherwise empty"),
  evidence: z.array(z.string()).describe("Finding IDs that meet or refute this part; empty otherwise"),
};

const roundSchema = <P extends z.ZodRawShape>(part: P) => z.object({
  judgments: z.array(
    z.object({
      goal_id: z.string(),
      parts: z.array(z.object(part)),
      outcome: z.enum(["answered", "partial", "not_found", "conflicting"]),
      verdicts: z
        .array(z.object({ claim_id: z.string(), verdict: z.enum(["supported", "contradicted", "unsettled"]) }))
        .describe("One entry per claim to verify (A…); empty for a goal without claims"),
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
/** The schema sent without a map of main parts, which happens only with the plan of last resort. */
export const RoundApiSchema = roundSchema(PART);
export const RoundMapSchema = roundSchema(MAP_PART);
export type RoundReply = z.infer<typeof RoundMapSchema>;

const GUIDELINE_FOR: Record<string, (typeof GUIDELINES)[number]> = { T1: "G1", T2: "G1", T3: "G1", T4: "G6", T5: "G6", T6: "G2", T7: "G7" };
const NUMERIC = /\b(numbers?|amounts?|prices?|costs?|fares?|dates?|percent(age)?s?|rates?|figures?|how much|how many)\b/i;

const ANALYST_BODY = `You are the round analyst of a research team that follows Environment-Based Design (EBD). Researchers have just answered some research goals. For each goal served in this round you judge, part by part, whether the evidence meets the goal's done_when. You may also propose new goals that the evidence shows are needed. You never decide whether the research as a whole is finished; code does that from your judgments.

Evidence lines have IDs: r2-b1-f3 is a cited finding, r2-b1-g1 is a gap the researcher reported. Conflicts have IDs C1, C2, …. Cite IDs only.

## Judgments: one per goal listed under <served_goals>
- parts: split done_when into its parts (usually 2–5). When a goal lists "Parts already met", those parts stay met: list only the parts under "Judge only these parts", and give the outcome on them alone (answered when all of them are met). For each part, met is true only if a cited finding states it; list those finding IDs in evidence. A gap line never meets a part. Inferences, general knowledge and your own reasoning never meet a part.
- Currency: "as of <run date>" or "the latest available evidence" is met by the most recent evidence the sources give, such as a current official page or the latest dated report. It does not require a page's capture date or a source dated on the run date.
- outcome:
  - answered: every part is met;
  - partial: some parts are met, some are not;
  - not_found: no part is met;
  - conflicting: the findings for this goal disagree and a conflict about it is listed under <conflicts>.
- verdicts, for a goal with "Claims to verify": one entry per claim, each judged on its own: supported if findings state the claim holds; contradicted if findings state it does not hold; unsettled if the findings do not decide it or disagree. The claims of one goal are independent: one can hold while another does not. For a goal without claims: an empty list.
- missing: the unmet parts in a few words each, so the next researcher knows what to look for. Empty when answered.

## Proposals: new goals (EBD: each answer is analysed as new objects and relations, which raise new questions)
Propose a goal only when the evidence shows the research needs it:
- a term that a necessary goal needs but that is not yet defined (for example, which products are "the current flagships" once a finding names them): template T1, the term as new_object, copied exactly from the prompting finding as new_object_quote;
- a part or life-cycle event of an object that a synthesis question depends on: T1 or T3. This includes a step that the findings reveal and no goal covers; for example, a finding that a product must be imported brings in import rules, duties and delivery time. It also includes a main part or step that the findings only name: when findings list an object's main parts or steps but none says what one of them involves, propose a goal for that one if a synthesis question needs it explained, even when the part of a goal that asks for the list is met (for example, findings name a vaccine trial's three phases but describe only the first). Ask what the step requires, checking the same kinds as the request analysis: natural; built, physical and digital (documents, data, laws, software); economic (costs, prices, time); social (people and organisations). Propose such a goal when the step could change the answer to a synthesis question, even if that question does not name the step; the finding that reveals the step is what prompted it;
- a relation the findings state but leave unverified or contested: T7.
Each proposal attaches to an existing object (object_id), cites what prompted it (prompted_by), and serves a necessary goal or a synthesis question (leads_to). Write the question so that a researcher who sees only it can act: full names, place and time. Keep the client's scope: do not narrow a new goal to one case of something the client did not state (one region, one customer group, one budget) because a finding describes that case; ask for the main cases, or for the case the request itself implies. Do not propose a goal that repeats an existing goal, asks for the final answer itself, merely re-asks a partial goal (partial goals are re-served automatically), or only asks for a date or a capture of a value already found. Propose at most the number given in <limits>; return [] when nothing is needed.`;

const ANALYST_REPLY = `Reply by calling ${ANALYST_TOOL} once with all judgments and proposals.`;

/**
 * Added when the run has a plan (sections 19, 28 and 29): the parts of a goal are the key questions of
 * a main part of the answer, and each is judged on its own.
 */
export const ANALYST_QUESTIONS_SECTION = `## Key questions: goals for a main part of the answer
Some goals list "Key questions" (M1, M2, …) instead of done_when. The analyst wrote these questions before any search, as what it expected one main part of the answer to need. They, and every example they name, are assumptions, and the evidence overrides them. For such a goal, give one parts entry for each key question listed under "Judge only", with part starting with the question's ID ("M4 …"):
- met is true when cited findings answer the key question, also when the answer is a no or names something else than the example in the question; list the finding IDs in evidence.
- refuted is true when a cited finding states that what the key question takes for granted did not happen, does not exist or does not apply to this subject, so that it cannot be answered as asked (for example, it asks what reasons a court gave for a ruling, and the sources state that no such ruling was made). List the finding IDs in evidence, set met to false, and write what the findings say instead in correction, in a few words, or leave it empty. Silence never refutes: a key question that the sources do not answer is neither met nor refuted, and a gap line never refutes. A finding that only one item of a key question does not apply, or that it does not apply to one of several things the subject covers, is information for the answer: the key question is met, not refuted.
- otherwise met and refuted are both false.
For such a goal the outcome is answered when every key question judged is met or refuted, partial when some are and not_found when none is; missing lists the key questions that are neither met nor refuted, in a few words each. Do not give such a goal the outcome conflicting: a disagreement between sources about one fact is recorded under <conflicts> and does not change what the part of the answer needs. For every other goal, leave refuted false and correction empty.
A key question that stays unanswered is searched again only when most key questions of its goal are unanswered. When the report needs it, propose a goal for it as above: write the question with what the findings now show (the actual options, places or organisations they name) and cite the gap or finding that prompts it. A main part of the answer that the findings treat and no goal covers is also a reason for a proposal.`;

/** The new goals of one round that may be necessary (section 20); settle goals are counted apart. */
export const FOCUS_NECESSARY = 2;

/**
 * The sentence of the follow-up section on the main parts of the answer (section 26, approved on
 * 2026-11-19): a main part that no source happened to mention can be raised without a citation.
 */
export const MAIN_PARTS_UNCITED = "For each main part that the findings mention only in passing or not at all, propose a necessary goal before you propose any detail. Cite the finding or gap that mentions it; when nothing mentions it, cite nothing.";

/**
 * What deserves another researcher (section 20). EBD collects "the necessary and sufficient information"
 * and determines "the focus at each stage" (Zeng 2015, p. 15); its questioning goes width first
 * (Zeng 2020, section 4.2).
 */
export const ANALYST_FOCUS_SECTION = `## Follow-up: what deserves another researcher
What is searched after a round must be what the client's answer depends on. Code decides from your judgments what is searched again, so judge the content, not the sources:
- A part asks for content. A wish about the source is not a part, and it is not missing: a primary or official source in place of a secondary one, a full text read directly, the date of a page or a publication, a second confirmation. When a cited finding states what a part asks for, the part is met.
- The verdict on a claim is yours to give from the findings. No finding has to state it, and a verdict is never a part or missing. A claim that a name or an abbreviation stands for something is supported when sources use it that way, also when the name has other meanings.
- missing lists only content that the findings do not give. A goal is searched again only when most of its parts are unmet or a claim to verify is still unsettled.
- Conflicts are handled by code, not by proposals. Under <conflicts>, each conflict is marked critical or not critical: code gives a goal of its own only to a conflict that decides a claim of the question; any other disagreement between sources is reported to the client as it stands and is not researched again. Never propose a goal to settle a conflict, to check it again or to find the exact value. Do not give a goal the outcome conflicting because of a conflict that decides none of its claims: judge its parts.
- need of a proposal. necessary: a main part of the client's question that the findings cover only in passing or not at all, so that a reader would call the report incomplete without it. completing: anything that sharpens an answer the findings already give, such as a more exact value, date or name, the figures of one study, one more market, region, case or group of users, a better source for something already found, or a price or a place of sale that the client did not ask about.
- Main parts come before details. After judging, compare the findings with what a full answer to the client's question needs: the main parts a reader would expect it to cover. ${MAIN_PARTS_UNCITED} Mark at most ${FOCUS_NECESSARY} proposals necessary, those a full answer needs most, and list them first.`;

/** The analyst's instructions: the section on key questions when the run has a plan, and the follow-up section. */
export function analystSystem(withMap: boolean): string {
  return [ANALYST_BODY, ...(withMap ? [ANALYST_QUESTIONS_SECTION] : []), ANALYST_FOCUS_SECTION, ANALYST_REPLY].join("\n\n");
}

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
    const event = eventOf(state, g);
    if (event) {
      const mark = (p: MapPart) => (p.status === "assumed" ? "" : ` [${p.status}${p.evidence.length ? `: ${p.evidence.join(", ")}` : ""}]`);
      const judge = event.parts.filter((p) => p.status === "assumed").map((p) => p.id);
      return [
        `### ${g.id} (kind ${g.kind}, ${g.need}, attempt ${g.attempts})`,
        `Question: ${g.text}`,
        `Key questions of the main part "${event.name}":`,
        ...event.parts.map((p) => `- ${p.id}${mark(p)} ${p.text}`),
        `Judge only: ${judge.join(", ") || "(none left)"}`,
        ...(g.settles ? [`Settles conflict ${g.settles}`] : []),
        "Evidence:",
        ...(lines.length ? lines.map(evidenceLine) : ["(none: the researcher reported nothing for this goal)"]),
      ].join("\n");
    }
    return [
      `### ${g.id} (kind ${g.kind}, ${g.need}, attempt ${g.attempts})`,
      `Question: ${g.text}`,
      `done_when: ${g.doneWhen}`,
      ...(claims(g).length ? ["Claims to verify:", ...claims(g).map((c) => `- ${c}`)] : []),
      ...(g.settles ? [`Settles conflict ${g.settles}`] : []),
      ...(g.metParts.length
        ? [
            "Parts already met (kept from earlier rounds; do not judge them again):",
            ...g.metParts.map((p) => `- ${p.part} [${p.evidence.join(", ")}]`),
            `Judge only these parts: ${g.missing.join("; ") || "(none recorded; judge what done_when still needs)"}`,
          ]
        : g.missing.length
          ? [`Missing after the last attempt: ${g.missing.join("; ")}`]
          : []),
      "Evidence:",
      ...(lines.length ? lines.map(evidenceLine) : ["(none: the researcher reported nothing for this goal)"]),
    ].join("\n");
  });
  const openGoals = state.goals.filter((g) => !isSettled(g)).length;
  const allowed = Math.max(0, Math.min(options.maxNewGoalsPerRound - createdThisRound(state, round), options.maxOpenGoals - openGoals));
  const roundConflicts = state.conflicts.filter((c) => c.createdRound === round);
  return [
    `<run_date>${state.today}</run_date>`,
    `<question>\n${state.question}\n</question>`,
    `<objects>\n${[...a.rom.objects.map((o) => `${o.id} "${o.text}": ${o.meaning}`), ...state.objectsFound.map((o) => `${o.id} "${o.text}" (found in ${o.evidence})`)].join("\n")}\n</objects>`,
    `<synthesis_questions>\n${synthesisQuestions(a).map((q) => `${q.id} ${q.text}`).join("\n")}\n</synthesis_questions>`,
    `<existing_goals>\n${state.goals.map((g) => `${g.id} [${g.status}, ${g.need}] ${g.text}`).join("\n")}\n</existing_goals>`,
    `<conflicts>\n${roundConflicts.map((c) => `${c.id} ${c.type}${typeof c.critical === "boolean" ? (isCritical(c) ? " (critical)" : " (not critical)") : ""} about ${c.about}: ${c.statement}`).join("\n") || "(none)"}\n</conflicts>`,
    `<served_goals>\n${goalBlock.join("\n\n")}\n</served_goals>`,
    `<limits>\nNew goals you may propose this round: ${allowed}${allowed > FOCUS_NECESSARY ? `, at most ${FOCUS_NECESSARY} of them necessary` : ""}.${allowed === 0 ? " Return proposals: []." : ""}\n</limits>`,
  ].join("\n");
}

/**
 * Missing lists count as empty: a reply without proposals proposes nothing (live test round 4:
 * Haiku left the field out), and a judgment without verdicts judges no claim, which the checks
 * reject only for an answered goal that has claims.
 */
function withDefaults(args: unknown): unknown {
  if (!args || typeof args !== "object" || Array.isArray(args)) return args;
  const out: Record<string, unknown> = { ...args };
  if (!("proposals" in out)) out.proposals = [];
  if (Array.isArray(out.judgments)) out.judgments = out.judgments.map((j) => (j && typeof j === "object" && !Array.isArray(j) && !("verdicts" in j) ? { ...j, verdicts: [] } : j));
  return out;
}

/**
 * Code checks (section 10.1). Judgment errors are retried; proposals are accepted or rejected later by acceptProposals.
 * A necessary proposal may cite nothing (section 26), so an empty prompted_by is no warning for it.
 */
export function checkRound(args: unknown, state: EbdState, served: Goal[]): Checked<RoundReply> {
  const parsed = RoundMapSchema.safeParse(withDefaults(args));
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
    // A goal of the environment map is judged on its planned parts; code computes its outcome from them.
    const event = eventOf(state, goal);
    const open = event ? event.parts.filter((p) => p.status === "assumed").map((p) => p.id) : [];
    if (!j.parts.length && (!event || open.length)) err("parts: split done_when into at least one part");
    j.parts.forEach((p, k) => {
      // With an environment map, a gap line cited as the reason a part is unmet, or next to the findings
      // that meet a part, is dropped instead of rejected: it changes no judgment. In the live batches of
      // 2026-11-11 such citations alone rejected 19 of 52 first replies, and every retry resends the whole round.
      const gaps = p.evidence.filter((id) => !findings.has(id) && evidence.has(id));
      if (state.map && gaps.length && ((!p.met && !p.refuted) || p.evidence.some((id) => findings.has(id)))) {
        p.evidence = p.evidence.filter((id) => !gaps.includes(id));
        warnings.push({ code: "judgment", path, message: `parts[${k}]: gap line ${gaps.join(", ")} is not evidence for a part; ignored` });
      }
      if (p.met && !p.evidence.length) err(`parts[${k}] is met but cites no finding`);
      const unknown = p.evidence.filter((id) => !findings.has(id));
      if (unknown.length) err(`parts[${k}]: ${unknown.join(", ")} ${unknown.some((id) => evidence.has(id)) ? "is a gap line, which cannot meet a part" : "is not a finding ID"}`);
      if (!event) return;
      if (!partOf(event, p.part)) err(`parts[${k}]: start part with the ID of a planned part of ${goal.id}; to judge: ${open.join(", ") || "none"}`);
      if (p.refuted && p.met) err(`parts[${k}] cannot be both met and refuted`);
      if (p.refuted && !p.evidence.length) err(`parts[${k}] is refuted but cites no finding; a part the sources do not mention is not refuted`);
    });
    const met = j.parts.filter((p) => p.met).length;
    if (!event) {
      if (j.outcome === "answered" && met !== j.parts.length) err("answered needs every part met");
      if (j.outcome === "partial" && (met === 0 || met === j.parts.length)) err("partial needs some parts met and some not");
      if (j.outcome === "not_found" && met > 0) err("not_found cannot have met parts");
      if (j.outcome !== "answered" && !j.missing.length) err("missing: name the unmet parts");
    }
    const judgedClaims = new Set<string>();
    j.verdicts.forEach((v, k) => {
      if (!goal.verifies.includes(v.claim_id)) {
        err(`verdicts[${k}]: ${v.claim_id} is not a claim of ${goal.id}; ${goal.verifies.length ? `its claims are ${goal.verifies.join(", ")}` : "it has no claims, so verdicts is []"}`);
      } else if (judgedClaims.has(v.claim_id)) err(`verdicts[${k}]: ${v.claim_id} is judged twice`);
      judgedClaims.add(v.claim_id);
    });
    const unjudged = goal.verifies.filter((c) => !judgedClaims.has(c));
    if (j.outcome === "answered" && unjudged.length) err(`a goal with claims to verify needs a verdict on each (supported, contradicted or unsettled); missing: ${unjudged.join(", ")}`);
  });
  for (const id of servedIds) if (!judged.has(id)) errors.push({ code: "judgment_missing", path: "judgments", message: `no judgment for ${id}` });

  reply.proposals.forEach((p, i) => {
    const path = `proposals[${i}]`;
    const unknown = p.prompted_by.filter((id) => !evidence.has(id) && !conflicts.has(id));
    if (!p.prompted_by.length && p.need === "necessary") return;
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
    const event = eventOf(state, goal);
    const parts = j.parts
      .filter((p) => !event || partOf(event, p.part))
      .map((p) => {
        const evidence = p.evidence.filter((id) => findings.has(id));
        const refuted = Boolean(event && p.refuted && !p.met && evidence.length > 0);
        return { part: p.part, met: p.met && evidence.length > 0, evidence, ...(event ? { refuted, correction: refuted ? (p.correction ?? "") : "" } : {}) };
      });
    if (!parts.length && !event) continue;
    const met = parts.filter((p) => p.met).length;
    const computed = met === parts.length ? "answered" : met > 0 ? "partial" : "not_found";
    let outcome: RoundReply["judgments"][number]["outcome"] =
      j.outcome === "conflicting" ? "conflicting" : OUTCOME_RANK[computed] < OUTCOME_RANK[j.outcome] ? computed : j.outcome;
    // Keep the first verdict on each of the goal's own claims.
    const verdicts: RoundReply["judgments"][number]["verdicts"] = [];
    for (const v of j.verdicts) if (goal.verifies.includes(v.claim_id) && !verdicts.some((x) => x.claim_id === v.claim_id)) verdicts.push(v);
    const missing = [...j.missing];
    const unjudged = goal.verifies.filter((c) => !verdicts.some((v) => v.claim_id === c));
    if (outcome === "answered" && unjudged.length) {
      outcome = "partial";
      missing.push(`a verdict on ${unjudged.join(", ")}`);
    }
    if (outcome !== "answered" && !missing.length) missing.push(...parts.filter((p) => !p.met).map((p) => p.part));
    judgments.push({ goal_id: j.goal_id, parts, outcome, verdicts, missing });
  }
  return { judgments, proposals: reply.proposals };
}

export function runRoundAnalyst(model: BaseChatModel, state: EbdState, round: number, served: Goal[], options: EbdOptions): Promise<CallOutcome<RoundReply>> {
  return structuredCall({
    model,
    role: "round_analyst",
    system: analystSystem(Boolean(state.map)),
    message: analystMessage(state, round, served, options),
    tool: { name: ANALYST_TOOL, description: "Submit the judgments of the served goals and any new goals the evidence calls for.", schema: state.map ? RoundMapSchema : RoundApiSchema },
    check: (args) => checkRound(args, state, served),
    fallback: (last) => repairRound(last, state, served),
    lists: { ids: ["evidence", "prompted_by", "leads_to"], texts: ["missing", "source_hints"] },
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

/** The share of its parts from which a goal counts as answered in the main (section 20); the same share closes an event of the map. */
const MOSTLY_ANSWERED = EVENT_COVERED;

/** Has every client claim the goal checks a verdict of supported or contradicted? True for a goal without claims. */
function claimsDecided(goal: Goal): boolean {
  return goal.verifies.every((c) => goal.verdicts[c] === "supported" || goal.verdicts[c] === "contradicted");
}

/**
 * Section 20: does an unsettled conflict hold the goal, so that it waits for the settle goal? Only a
 * conflict that decides a claim the goal checks: then the goal's verdict depends on it. Any other
 * disagreement, critical or not, is about one fact inside the goal's answer; a critical one has its
 * own settle goal, and the goal is judged on its parts. Before, a premise check with every part met
 * and its claim supported waited for a disagreement about one food (replays of 2026-11-11).
 */
function heldByConflict(state: EbdState, goal: Goal): boolean {
  return state.conflicts.some((c) => (c.status === "open" || c.status === "disputed") && c.claim !== null && goal.verifies.includes(c.claim) && (c.about === goal.id || goal.objectIds.includes(c.about)));
}

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
    // Lab 5 review, change 1: parts met in earlier rounds stay met; this judgment covers the rest.
    // A kept part the analyst lists again is not counted twice. A conflicting judgment locks
    // nothing, because its findings disagree.
    let outcome = j.outcome;
    const event = eventOf(state, goal);
    if (event && state.map) {
      // Section 19: the findings confirm or refute each planned part, and the outcome follows from the map.
      let changed = 0;
      for (const p of j.parts) {
        const part = partOf(event, p.part);
        if (!part || part.status !== "assumed" || !p.evidence.length) continue;
        if (p.refuted && !p.met) {
          if (overwritePart(state.map, part.id, p.evidence, p.correction ?? "", "round analyst", round)) {
            changed += 1;
            log(`${goal.id}: planned part ${part.id} "${part.text}" refuted by ${p.evidence.join(", ")}${part.correction ? `; the findings say instead: ${part.correction}` : ""} → it leaves the plan`);
          }
        } else if (p.met) {
          Object.assign(part, { status: "confirmed", evidence: p.evidence, by: "round analyst", round });
          changed += 1;
        }
      }
      syncGoal(goal, event);
      if (!liveParts(event).length) {
        settle(goal, "moot", round);
        goal.retryNote = null;
        out.settled.push(goal.id);
        log(`${goal.id}: the evidence refuted every planned part of "${event.name}" → moot`);
        continue;
      }
      // The goal asks what the step involves, so a disagreement about one fact does not hold it open:
      // the conflict keeps its own record and settle goal. Once enough parts are confirmed the event is
      // researched, and the parts no source reported are not searched again.
      if (isCovered(event)) {
        const unfound = closeEvent(event, round);
        syncGoal(goal, event);
        if (unfound.length) log(`${goal.id}: ${goal.partsMet} of ${goal.partsTotal} planned parts confirmed; not reported by the sources found, and not searched again: ${unfound.map((p) => `${p.id} "${p.text}"`).join("; ")}`);
        outcome = "answered";
      } else {
        outcome = changed || goal.partsMet ? "partial" : "not_found";
      }
    } else {
      // Section 20: a conflict holds a goal only when it decides a claim the goal checks. A goal judged
      // conflicting over any other disagreement is judged on its parts, like any other goal.
      if (outcome === "conflicting" && !goal.settles && !heldByConflict(state, goal)) {
        const met = j.parts.filter((p) => p.met).length;
        const unjudged = goal.verifies.filter((c) => !j.verdicts.some((v) => v.claim_id === c));
        outcome = met === 0 ? "not_found" : met < j.parts.length || unjudged.length ? "partial" : "answered";
        log(`${goal.id}: judged conflicting, but no conflict about it decides a claim it checks → judged on its parts (${outcome})`);
      }
      const keptText = new Set(goal.metParts.map((p) => partKey(p.part)));
      const judgedParts = j.parts.filter((p) => !keptText.has(partKey(p.part)));
      const metParts = judgedParts.filter((p) => p.met);
      const cited = [...new Set(j.parts.filter((p) => p.met).flatMap((p) => p.evidence))];
      const kept = goal.metParts.length;
      if (outcome !== "conflicting") goal.metParts.push(...metParts.map((p) => ({ part: p.part, evidence: p.evidence, round })));
      goal.partsTotal = kept + judgedParts.length;
      goal.partsMet = kept + metParts.length;
      goal.evidence = [...new Set([...goal.evidence, ...cited])];
      // What a judgment that was "conflicting" lists as missing is the disagreement itself, which no longer holds the goal.
      goal.missing = j.outcome === "conflicting" && outcome === "answered" ? [] : j.missing;
    }

    // An event goal asks what a step involves; its parts are assumptions, so the floor for checked facts does not apply.
    // Section 20: the floor guards the client's claims only. For any other number or
    // date a second source is a wish about the sources, and no researcher is spent on it.
    if (outcome === "answered" && !event && needsFloor(goal) && goal.verifies.length > 0) {
      const hosts = independentHosts(goal.evidence.map((id) => byId.get(id)).filter((e): e is EvidenceLine => Boolean(e)));
      if (hosts < options.evidenceFloor) {
        outcome = "partial";
        goal.missing = [`confirmation from at least ${options.evidenceFloor} independent sources (found ${hosts})`];
        log(`${goal.id}: answered, but the evidence floor needs ${options.evidenceFloor} independent hosts and found ${hosts} → partial`);
      }
    }
    for (const v of j.verdicts) if (goal.verifies.includes(v.claim_id)) goal.verdicts[v.claim_id] = v.verdict;

    // A settle goal whose sources still disagree ends disputed, and so do its conflict and the goal
    // waiting for it: a settle goal gets no settle goal of its own (settleBlock). Before this, it could
    // find its own conflict below and wait on itself, leaving the waiting goal "conflicting" for good.
    if (outcome === "conflicting" && goal.settles) {
      settle(goal, "disputed", round);
      out.settled.push(goal.id);
      log(`${goal.id}: its sources still disagree → disputed`);
      resolveSettle(state, goal, "exhausted", round, log);
      continue;
    }
    if (outcome === "conflicting") {
      const conflict = state.conflicts.find((c) => c.status === "open" && c.settleGoal && c.settleGoal !== goal.id && (c.about === goal.id || goal.objectIds.includes(c.about)));
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
      log(`${goal.id}: answered (${goal.partsMet}/${goal.partsTotal} parts${claimText(goal)})`);
      resolveSettle(state, goal, "answered", round, log);
      continue;
    }
    // Section 20: a goal is searched again only when most of it is unanswered, or when a client claim
    // it checks is still undecided. Over the 90 recorded runs before this rule, 63 planned goals with
    // at least half their parts met were searched again; 11 ended answered, gaining 0.4 parts on average.
    // A goal that checks client claims is there for its verdicts: once each claim is supported or
    // contradicted on enough independent sources, it is done, whatever its other parts say. In the
    // replays of 2026-11-11 such a goal was sent out again for "an explicit verdict" and for source
    // dates, with its claim already judged supported, and the goal that waited for it was never served.
    if (outcome === "partial" && !event && !goal.settles && claimsDecided(goal)) {
      const checks = goal.verifies.length > 0;
      const hosts = checks ? independentHosts(goal.evidence.map((id) => byId.get(id)).filter((e): e is EvidenceLine => Boolean(e))) : 0;
      const mostly = goal.partsTotal > 0 && goal.partsMet / goal.partsTotal >= MOSTLY_ANSWERED;
      if (checks ? hosts >= options.evidenceFloor : mostly) {
        settle(goal, "answered", round);
        goal.retryNote = null;
        out.settled.push(goal.id);
        log(
          checks
            ? `${goal.id}: ${claimText(goal).slice(2)} on ${hosts} independent sources → answered (${goal.partsMet}/${goal.partsTotal} parts); not searched again: ${goal.missing.join("; ") || "(nothing named)"}`
            : `${goal.id}: ${goal.partsMet} of ${goal.partsTotal} parts met → answered in the main; not searched again: ${goal.missing.join("; ") || "(nothing named)"}`,
        );
        continue;
      }
    }
    const note = outcome === "not_found" ? "The previous search found nothing for this question; try a different angle: other terms, other kinds of sources, or the primary record." : null;
    // Section 20: a settle goal gets one attempt. Of 26 second attempts at settle goals in the recorded
    // runs, one settled its disagreement.
    const single = Boolean(goal.settles);
    const r = requeueOrExhaust(goal, round, single ? 1 : options.maxAttempts, note);
    if (r === "exhausted") {
      out.exhausted.push(goal.id);
      out.settled.push(goal.id);
      resolveSettle(state, goal, "exhausted", round, log);
    } else {
      out.requeued.push(goal.id);
      if (goal.partsMet > before) out.advanced.push(goal.id);
    }
    log(`${goal.id}: ${outcome} (${goal.partsMet}/${goal.partsTotal} parts) → ${r}${single && r === "exhausted" ? " (a settle goal gets one attempt)" : ""}${goal.missing.length ? `; missing: ${goal.missing.join("; ")}` : ""}`);
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
    // The settled account replaces the verdict given while the sources disagreed, but only on the claim
    // the disagreement decided; a settle goal about a detail leaves the verdicts as judged (section 9).
    for (const claim of goal.verifies.filter((c) => waiting.verifies.includes(c))) {
      const verdict = how === "answered" ? (goal.verdicts[claim] ?? waiting.verdicts[claim]) : "unsettled";
      if (verdict) waiting.verdicts[claim] = verdict;
    }
    log(`${waiting.id}: ${waiting.status} after ${goal.id}`);
  }
  log(`${conflict.id}: ${conflict.status}`);
}

/** The planned part a judged part names: by its leading ID, or by the same text. */
export function partOf(event: MapEvent, text: string): MapPart | null {
  const id = /^\W*(M\d+)\b/.exec(text)?.[1];
  if (id) return event.parts.find((p) => p.id === id) ?? null;
  return event.parts.find((p) => partKey(p.text) === partKey(text)) ?? null;
}

/** A part's text for comparison: lower case, words only. */
function partKey(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/** ", claims A1 supported, A2 contradicted" for the log; empty for a goal without verdicts. */
function claimText(goal: Goal): string {
  const entries = Object.entries(goal.verdicts);
  return entries.length ? `, ${entries.length > 1 ? "claims" : "claim"} ${entries.map(([c, v]) => `${c} ${v}`).join(", ")}` : "";
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

const STOPWORDS = new Set(
  "a an and are as at be by can did do does for from has have how in is it its of on or that the their these this those to was were what when where which who why will with".split(" "),
);

/** Content words, singular: "dates" and "date" count as one. */
function contentWords(text: string): Set<string> {
  return new Set((text.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((w) => !STOPWORDS.has(w)).map((w) => (w.length > 3 ? w.replace(/s$/, "") : w)));
}

/** Shared content words over all content words of both texts. */
function overlap(a: string, b: string): number {
  const x = contentWords(a);
  const y = contentWords(b);
  return [...x].filter((w) => y.has(w)).length / Math.max(1, new Set([...x, ...y]).size);
}

/** The share of `part`'s content words that `text` contains. */
function coverage(part: string, text: string): number {
  const x = contentWords(part);
  const y = contentWords(text);
  return [...x].filter((w) => y.has(w)).length / Math.max(1, x.size);
}

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x) => b.includes(x));
}

/**
 * Accept or reject each proposal (section 10.2). Accepted proposals become goals
 * served from the next round. Returns the new goals; rejections are logged.
 */
export function acceptProposals(state: EbdState, reply: RoundReply | null, round: number, options: EbdOptions, log: (line: string) => void): Goal[] {
  if (!reply?.proposals.length) return [];
  const objects = new Set([...state.analysis.rom.objects.map((o) => o.id), ...state.objectsFound.map((o) => o.id)]);
  const necessary = new Set(state.goals.filter((g) => g.need === "necessary").map((g) => g.id));
  const synthesis = new Set(synthesisQuestions(state.analysis).map((q) => q.id));
  const byEvidence = new Map(state.evidence.map((e) => [e.id, e]));
  const added: Goal[] = [];

  reply.proposals.forEach((p, i) => {
    const reject = (why: string) => log(`proposal ${i + 1} rejected (${why}): ${p.text.slice(0, 160)}`);
    const prompts = p.prompted_by.filter((id) => byEvidence.has(id) || state.conflicts.some((c) => c.id === id));
    // Section 26: a main part of the answer that no finding mentions has nothing to cite. Such a
    // proposal is accepted, but only as one of the necessary new goals of the
    // round: a detail still has to grow from a finding. Before, a part that no source happened to
    // mention could not be raised at all, and in 8 of the 17 saved runs no missing part was raised.
    const uncited = !prompts.length;
    if (uncited) {
      if (p.need !== "necessary") return reject("cites no existing evidence or conflict; only a necessary goal for a main part of the answer may cite nothing");
      if (added.filter((g) => g.need === "necessary").length >= FOCUS_NECESSARY) return reject(`cites nothing, and ${FOCUS_NECESSARY} new goals of this round are already necessary`);
    }
    // Section 20: conflicts are followed up by their settle goals only, within the limits of settleBlock.
    // In the replays of 2026-11-11 the analyst asked again for disagreements the checker had marked as
    // details, and for a critical one that code had refused a settle goal.
    const followed = state.conflicts.find((c) => prompts.includes(c.id));
    if (followed) return reject(`follows up the conflict ${followed.id}; ${isCritical(followed) ? "a critical conflict is followed up by its settle goal only" : "it is not critical"}`);
    if (!objects.has(p.object_id)) return reject(`unknown object ${p.object_id}`);
    // The plan never searches the product (the answer the client asks for), and neither do
    // new goals (Lab 4 flight run: two goals attached to "How"). Since the live round of 2026-11-05 the
    // test is what the goal asks, not where it is attached: in the flight run the transit and visa
    // goals were attached to "How" only because the question has no object for them, and were lost.
    // A goal that asks for the final answer is rejected; any other moves to the object of the goal
    // whose evidence prompted it.
    let objectId = p.object_id;
    const leads = p.leads_to.filter((id) => necessary.has(id) || synthesis.has(id));
    const product = state.analysis.rom.objects.find((o) => o.id === p.object_id && o.role === "product");
    if (product) {
      // Near-identical, sharing most content words, or adding almost nothing to a synthesis question:
      // "Why did the tariffs raise prices?" restates a longer synthesis question in a few of its words.
      const answer = synthesisQuestions(state.analysis).find((q) => similar(q.text, p.text) || overlap(q.text, p.text) >= 0.45 || coverage(p.text, q.text) >= 0.75);
      if (answer) return reject(`asks for the final answer (${answer.id}), attached to "${product.text}", the answer the client asks for`);
      const products = new Set(state.analysis.rom.objects.filter((o) => o.role === "product").map((o) => o.id));
      const prompting = prompts.flatMap((id) => byEvidence.get(id)?.goalIds ?? [state.conflicts.find((c) => c.id === id)?.about ?? ""]);
      // Section 26: a goal that cites nothing has no prompting goal. It takes an object of the necessary
      // goal it serves, or the first object of the request that is not the answer asked for.
      const served = leads.flatMap((id) => state.goals.find((g) => g.id === id)?.objectIds ?? []).find((o) => !products.has(o));
      const target = uncited
        ? (served ?? state.analysis.rom.objects.find((o) => !products.has(o.id))?.id)
        : prompting.flatMap((id) => state.goals.find((g) => g.id === id)?.objectIds ?? []).find((o) => !products.has(o));
      if (!target) return reject(`attaches to "${product.text}", the answer the client asks for, and ${uncited ? "the request has no other object" : "the goals that prompted it have no other object"}`);
      log(`proposal ${i + 1}: moved from "${product.text}" (the answer the client asks for) to ${target}, ${uncited ? (served ? "an object of the goal it serves" : "the first object of the request that is not the answer") : "an object of the goal whose evidence prompted it"}`);
      objectId = target;
    }
    if (!leads.length) return reject("leads to no necessary goal or synthesis question");
    if (!p.text.trim() || p.text.length > 400 || !p.done_when.trim() || p.done_when.length > 400) return reject("text or done_when empty or longer than 400 characters");
    const parents = prompts.flatMap((id) => byEvidence.get(id)?.goalIds ?? [state.conflicts.find((c) => c.id === id)?.about ?? ""]);
    const depth = 1 + Math.max(0, ...parents.map((id) => state.goals.find((g) => g.id === id)?.depth ?? 0));
    if (depth > options.maxDepth) return reject(`depth ${depth} exceeds maxDepth ${options.maxDepth}`);
    let objectIds = [objectId];
    // A new object enters the object model only with the goal it came with.
    let found: EbdState["objectsFound"][number] | null = null;
    if (p.new_object.trim() && uncited) {
      // A new term enters the object model only with the finding that introduced it; the goal keeps its existing object.
      log(`proposal ${i + 1}: the term "${p.new_object.trim().slice(0, 80)}" is not added to the objects, because no finding is cited for it`);
    } else if (p.new_object.trim()) {
      const quoteFound = prompts.some((id) => byEvidence.get(id)?.kind === "finding" && byEvidence.get(id)!.text.toLowerCase().includes(p.new_object_quote.trim().toLowerCase()));
      if (!p.new_object_quote.trim() || !quoteFound) return reject("a new object needs a quote copied exactly from a prompting finding");
      const existing = state.objectsFound.find((o) => o.text.toLowerCase() === p.new_object.trim().toLowerCase());
      if (existing) objectIds = [existing.id, objectId];
      else {
        const used = [...state.analysis.rom.objects, ...state.objectsFound].map((o) => Number(o.id.slice(1)) || 0);
        const id = `O${Math.max(0, ...used) + 1}`;
        const evidenceId = prompts.find((x) => byEvidence.get(x)?.text.toLowerCase().includes(p.new_object_quote.trim().toLowerCase()))!;
        found = { id, text: p.new_object.trim(), parent: objectId, quote: p.new_object_quote.trim(), evidence: evidenceId, round };
        objectIds = [id, objectId];
      }
    }
    // Same type and objects is a duplicate only if the questions also overlap: "commissioning dates",
    // "development history" and "total cost" of one telescope are three questions (Lab 4, 2026-10-26).
    const duplicate = state.goals.find(
      (g) => similar(g.text, p.text) || (g.template === p.template && sameSet(g.objectIds, objectIds) && overlap(g.text, p.text) >= 0.45),
    );
    if (duplicate) return reject(`duplicates ${duplicate.id}`);
    // A part a retried goal still misses is already asked for by its retry.
    for (const g of state.goals.filter((x) => x.servedRounds.includes(round) && !isSettled(x))) {
      const part = g.missing.find((m) => coverage(m, p.text) >= 0.75);
      if (part) return reject(`re-asks "${part.slice(0, 80)}", which ${g.id} still looks for in its retry`);
    }
    if (createdThisRound(state, round) >= options.maxNewGoalsPerRound) return reject(`quota of ${options.maxNewGoalsPerRound} new goals per round reached (settle goals included)`);
    if (state.goals.filter((g) => !isSettled(g)).length >= options.maxOpenGoals) return reject(`${options.maxOpenGoals} open goals reached`);
    const kind = byEvidence.get(prompts[0]!)?.kind;
    // Section 20: at most FOCUS_NECESSARY new goals of a round are necessary; a further one is completing.
    let need = p.need;
    if (need === "necessary" && added.filter((g) => g.need === "necessary").length >= FOCUS_NECESSARY) {
      need = "completing";
      log(`proposal ${i + 1}: completing, because ${FOCUS_NECESSARY} new goals of this round are already necessary`);
    }
    const goal = newGoal({
      id: nextGoalId(state),
      text: p.text.trim(),
      objectIds,
      template: p.template,
      guideline: GUIDELINE_FOR[p.template]!,
      need,
      doneWhen: p.done_when.trim(),
      sourceHints: p.source_hints.slice(0, 3),
      origin: uncited ? { type: "uncovered" } : byEvidence.has(prompts[0]!) ? { type: kind === "gap" ? "gap" : "finding", evidence: prompts } : { type: "conflict", conflict: prompts[0]! },
      depth,
      leadsTo: leads,
      createdRound: round + 1,
    });
    if (found) state.objectsFound.push(found);
    state.goals.push(goal);
    added.push(goal);
    log(`${goal.id} created (${goal.kind}, ${goal.need}, depth ${depth}) ${uncited ? "for a main part of the answer that no finding mentions" : `from ${prompts.join(", ")}`}: ${goal.text.slice(0, 160)}`);
  });
  return added;
}

/** Verdicts for the rationale and the writer. */
export function verdictSummary(state: EbdState): string[] {
  const verdicts = assumptionVerdicts(state);
  return state.analysis.assumptions.map((x) => `${x.id} ${verdicts[x.id] ?? "not yet judged"}: ${x.claim}`);
}
