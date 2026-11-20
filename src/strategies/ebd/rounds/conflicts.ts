/**
 * The conflict checker (design section 9): one model call per round, before the
 * round analyst (D-D). It cites evidence line IDs only; code checks every record
 * and applies its effects. A conflict without valid evidence on both sides is not
 * recorded.
 */
import { z } from "zod";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { Issue } from "../analysis.js";
import { liveParts, overwritePart, syncGoal } from "../map.js";
import { levelOf, newGoal, nextGoalId, settle } from "../goals.js";
import type { EbdOptions } from "../options.js";
import { structuredCall, zodIssues, type CallOutcome, type Checked } from "../llm.js";
import { CONFLICT_TYPES, PLAN_CONFLICT, isCritical, isSettled, type Conflict, type EbdState, type EvidenceLine, type Goal, type MapEvent, type MapPart } from "../state.js";

export const CONFLICT_TOOL = "submit_conflicts";
const FRAME_FIELDS = ["time_frame", "place", "purpose"] as const;
const MAX_EARLIER = 60;

const MAP_TYPES = [...CONFLICT_TYPES, PLAN_CONFLICT] as const;

const item = <T extends readonly [string, ...string[]]>(types: T) => ({
  type: z.enum(types),
  about: z.string().describe("The goal ID (Q…) or object ID (O…) the conflict is about"),
  statement: z.string().describe("One neutral sentence: what the two sides say"),
  side_a: z.array(z.string()).describe("Evidence IDs of one side"),
  side_b: z.array(z.string()).describe("By type: evidence IDs, one assumption ID, one frame field, or one object ID"),
  settle_by: z.string().describe("What evidence would settle it; empty for off_target and time_dependent"),
  condition: z.string().describe("time_dependent only: when each side holds; otherwise empty"),
  claim: z.string().describe("The assumption ID (A…) whose truth this disagreement decides, or empty"),
});
/** The critical mark (section 20). */
const CRITICAL = { critical: z.boolean().describe("true when the answer to the client's question depends on which side is right; false for a detail") };

/** The schema sent when the run has no plan (the plan of last resort), and the one sent with a plan. */
const ConflictsCriticalSchema = z.object({ conflicts: z.array(z.object({ ...item(CONFLICT_TYPES), ...CRITICAL })) });
const ConflictsMapCriticalSchema = z.object({ conflicts: z.array(z.object({ ...item(MAP_TYPES), ...CRITICAL })) });
/** What a reply may hold, whichever schema was sent. */
const ConflictsReplySchema = z.object({ conflicts: z.array(z.object({ ...item(MAP_TYPES), critical: z.boolean().optional() })) });
export type ConflictsReply = z.infer<typeof ConflictsReplySchema>;
type ConflictItem = ConflictsReply["conflicts"][number];

/** The tool schema to send: with the plan conflict type when the run has a plan. */
export function conflictsToolSchema(withMap: boolean) {
  return withMap ? ConflictsMapCriticalSchema : ConflictsCriticalSchema;
}

const CONFLICT_BODY = `You are the conflict checker of a research team that follows Environment-Based Design (EBD). In EBD a conflict is two competing claims about one thing; the research continues until no undesired conflict is left open. Your job is narrow: compare this round's new evidence with the earlier evidence, the client's assumptions and the question's frame, and list the real conflicts. You do not judge which side is right and you do not summarise the research.

Each evidence line has an ID such as r2-b1-f3 (a cited finding). Cite IDs only; never quote or paraphrase evidence as a side.

Conflict types:
- source_vs_source: findings from different sources give incompatible answers to the same thing (different values, dates, outcomes, or yes and no). side_a and side_b are evidence IDs. Two parts of one page or site (a header and a table, a summary and its body) are not two sources.
- evidence_vs_assumption: findings state something incompatible with a client assumption (for example, the client presupposes a ban and the sources report that no ban was adopted). side_b is the one assumption ID. Silence is not a contradiction: if the sources merely do not mention the claim, it is not a conflict.
- evidence_vs_frame: a finding falls outside the question's time frame or place but is presented as current or local. side_b is one frame field: time_frame, place or purpose.
- off_target: a finding is about a different referent that shares a name with an object of the question (another product, organisation or term with the same name or acronym). side_b is the one object ID. A finding that a goal asks for is not off_target: when a goal asks which meanings a name has, the findings that list the other meanings answer it.
- time_dependent: two findings differ only because they describe different times (or versions, editions, regions); both can be true. side_a and side_b are evidence IDs; condition says when each holds ("A as of 2024; B since the 2025 revision").

Rules:
- A conflict is about a fact: a value, a date, an event, whether something exists or happened. Report only disagreements that would change a fact the report states: a different value, a yes against a no, a different outcome. Not conflicts: differences of detail, rounding, a few minutes or percent, counting conventions, scope or emphasis; listings that describe different options (different itineraries, models or offers); and differing opinions, ratings or impressions of reviewers (comfortable against uncomfortable, impressive against disappointing), which are a range of views the report presents. Agreement is not reported.
- Report each disagreement once, with one type. When dates, versions, editions or regions explain the difference, it is time_dependent, not source_vs_source.
- side_a and side_b never share an evidence ID, and for source_vs_source they come from different sources.
- Every conflict involves at least one new evidence line. Earlier lines may be the other side.
- Do not repeat a conflict already recorded (listed under <recorded_conflicts>), even in other words.
- about: the goal the conflict bears on (Q…), or, for off_target, the object (O…).
- claim: for source_vs_source, the assumption ID (A…) if the two sides disagree on whether that assumption holds; otherwise empty. A disagreement about a detail (a value, a date, a list) decides an assumption only if the assumption states that detail. For evidence_vs_assumption, the assumption in side_b. For the other types, empty.
- statement: one neutral sentence of at most 300 characters naming what each side says.
- settle_by: for source_vs_source, evidence_vs_assumption and evidence_vs_frame, what evidence would settle it (a primary record, a later revision, an official source), at most 300 characters. Empty for off_target and time_dependent.
- If there is no conflict, return an empty list.`;

const CONFLICT_REPLY = `Reply by calling ${CONFLICT_TOOL} once with the whole list.`;

/**
 * Added when the run has a plan (sections 19, 28 and 29): its parts are the key questions of the main
 * parts of the answer. A finding against what a key question takes for granted overwrites it.
 */
export const CONFLICT_QUESTIONS_SECTION = `The plan's assumptions:
<plan> lists the key questions (M1, M2, …) of the plan: what the analyst expected each main part of the answer to need, written before any search. They, and every example they name, are the analyst's assumptions, not claims of the client, and the evidence overrides them. One more conflict type applies to them:
- evidence_vs_plan: findings state that what a key question takes for granted did not happen, does not exist or does not apply to this subject, so that it cannot be answered as asked (for example, a key question asks what reasons a court gave for a ruling, and the sources state that no such ruling was made). side_a is the finding IDs; side_b is the one key question's ID (M…); about is the goal the key question belongs to; statement says what the plan expected and what the findings state; settle_by, condition and claim are empty. Nothing has to be settled: the key question leaves the plan at once.
Silence is not a contradiction: a key question that the sources do not answer is not a conflict. A finding that answers a key question is not a conflict either, also when the answer is a no or names something else than the example in the question. Neither is a finding that only one item of a key question does not apply, or that it does not apply to one of several things the subject covers: that is information for the answer, and the key question stays in the plan.`;

/**
 * The critical mark (section 20). EBD starts from the critical conflict
 * (Zeng 2015, p. 13 and Table 6), so only the conflicts the answer depends on are followed up.
 * The last sentence was corrected on 2026-11-19 (section 26): since section 25 a critical conflict is
 * followed up in a round only when a researcher is left, so "one of them is settled in each round"
 * no longer held.
 */
export const CONFLICT_CRITICAL_SECTION = `Critical conflicts:
EBD does not resolve every conflict. It determines the critical ones, on which the solution depends, and starts with them. For each conflict, set critical:
- true when the answer to the client's question depends on which side is right: with one side the report would conclude, recommend or instruct something different than with the other. This covers whether the thing asked about exists, is allowed or is available at all; which of two compared things is ahead on a point the comparison turns on; whether a step the reader would take is required; and whether an effect the client asks about is real.
- false when the report's answer is the same with either side: a value that differs without changing the conclusion or the advice, a date or a count in the background, who said or measured something, a figure for one market, one case or one study among several.
For example, for a client choosing a vaccine for a child, a disagreement on whether the vaccine is approved for children is critical, and a disagreement on the year its maker was founded is not.
An evidence_vs_assumption conflict is always critical, and so is a source_vs_source conflict with a claim. A critical conflict that decides a claim of the question is researched again; any other critical conflict goes to the writer of the report as a point the answer depends on; the others are only recorded. Most conflicts are not critical. List the critical conflicts first, the one the answer depends on most at the top: the writer is told about three at most.`;

/** The mark a claim taken as given carries under <assumptions> (section 27). */
export const GIVEN_MARK = "(taken as given)";

/**
 * Added only when a claim of the question is taken as given (section 27). Such a claim restates what
 * the question asks about, so findings that say how far it holds are the answer, not a conflict with
 * it. In the runs of 2026-11-18 the checker reported "exercise can help" against reviews that found
 * no benefit for one kind of back pain, and the report then opened with a doubt. A finding that the
 * claim is false as a whole is still reported: that is how the evidence overrules it.
 */
export const CONFLICT_GIVEN_SECTION = `Assumptions taken as given:
Under <assumptions>, a claim marked ${GIVEN_MARK} only restates, in general terms, what the question asks about. The team did not check it as a fact of its own. For such a claim, report an evidence_vs_assumption conflict only when findings state that it is false as a whole (for example, the question asks why a food causes an illness, and the sources report that it causes none). Findings that limit or qualify it (it holds for some cases, groups or conditions and not for others, or its size is disputed) are part of the answer and no conflict with the assumption. A disagreement between sources about how far it holds is a source_vs_source conflict with an empty claim.`;

/**
 * The checker's instructions: the plan's key questions when the run has a plan, the section on claims
 * taken as given when the plan has one, and the critical mark.
 */
export function conflictSystem(withMap: boolean, withGiven = false): string {
  return [CONFLICT_BODY, ...(withMap ? [CONFLICT_QUESTIONS_SECTION] : []), ...(withGiven ? [CONFLICT_GIVEN_SECTION] : []), CONFLICT_CRITICAL_SECTION, CONFLICT_REPLY].join("\n\n");
}

/** The planned parts the evidence can still overwrite, with their events. */
function openParts(state: EbdState): { event: MapEvent; part: MapPart }[] {
  return (state.map?.events ?? []).flatMap((event) => event.parts.filter((part) => part.status === "assumed").map((part) => ({ event, part })));
}

function frameText(state: EbdState): string {
  const f = state.analysis.frame;
  return FRAME_FIELDS.map((k) => `${k}: ${f[k].value ?? "unknown"} (${f[k].basis})`).join("\n");
}

function line(e: EvidenceLine): string {
  return `${e.id} [${e.goalIds.join(",") || "-"}] ${e.text}`;
}

export function conflictMessage(state: EbdState, fresh: EvidenceLine[]): string {
  const a = state.analysis;
  const freshIds = new Set(fresh.map((e) => e.id));
  const freshObjects = new Set(state.goals.filter((g) => fresh.some((e) => e.goalIds.includes(g.id))).flatMap((g) => g.objectIds));
  const related = new Set(state.goals.filter((g) => g.objectIds.some((o) => freshObjects.has(o))).map((g) => g.id));
  const earlier = state.evidence
    .filter((e) => !freshIds.has(e.id) && e.kind === "finding" && e.goalIds.some((id) => related.has(id)))
    .slice(-MAX_EARLIER);
  const given = new Set((state.premises?.given ?? []).map((g) => g.id));
  return [
    `<run_date>${state.today}</run_date>`,
    `<question>\n${state.question}\n</question>`,
    `<frame>\n${frameText(state)}\n</frame>`,
    `<assumptions>\n${a.assumptions.map((x) => `${x.id}${given.has(x.id) ? ` ${GIVEN_MARK}` : ""}: ${x.claim}`).join("\n") || "(none)"}\n</assumptions>`,
    `<objects>\n${[...a.rom.objects.map((o) => `${o.id} "${o.text}": ${o.meaning}`), ...state.objectsFound.map((o) => `${o.id} "${o.text}": found in ${o.evidence}`)].join("\n")}\n</objects>`,
    `<goals>\n${state.goals.map((g) => `${g.id} [${g.objectIds.join(",")}] ${g.text}`).join("\n")}\n</goals>`,
    `<new_evidence>\n${fresh.filter((e) => e.kind === "finding").map(line).join("\n") || "(none)"}\n</new_evidence>`,
    `<earlier_evidence>\n${earlier.map(line).join("\n") || "(none)"}\n</earlier_evidence>`,
    `<recorded_conflicts>\n${state.conflicts.map((c) => `${c.id} ${c.type} (${c.status}) about ${c.about}: ${c.statement}`).join("\n") || "(none)"}\n</recorded_conflicts>`,
    ...(state.map ? [`<plan>\n${openParts(state).map(({ event, part }) => `${part.id} [${event.goalId}, part "${event.name}"] ${part.text}`).join("\n") || "(none)"}\n</plan>`] : []),
  ].join("\n");
}

/** Code checks of one reply (section 9). Errors carry the item's path, so the fallback can keep the valid items. */
/** A conflict without a claim decides no assumption (review of 2026-10-21). */
function withDefaultClaims(args: unknown, withMap = false): unknown {
  if (!args || typeof args !== "object" || Array.isArray(args)) return args;
  const list = (args as { conflicts?: unknown }).conflicts;
  if (!Array.isArray(list)) return args;
  // With an environment map the prompt says that some fields are empty for evidence_vs_plan, and the
  // model then leaves empty fields out of other conflicts too (7 rejected replies in the live batches
  // of 2026-11-11). A field left out counts as empty; the rules below still require what a type needs.
  const blanks = withMap ? { settle_by: "", condition: "" } : {};
  return { ...args, conflicts: list.map((c) => (c && typeof c === "object" ? { ...blanks, ...(!("claim" in c) ? { claim: "" } : {}), ...c } : c)) };
}

export function checkConflicts(args: unknown, state: EbdState, fresh: EvidenceLine[]): Checked<ConflictsReply> {
  const parsed = ConflictsReplySchema.safeParse(withDefaultClaims(args, Boolean(state.map)));
  if (!parsed.success) return { value: null, errors: zodIssues(parsed.error), warnings: [] };
  const errors: Issue[] = [];
  const warnings: Issue[] = [];
  // A mark left out counts as "not critical": the conflict is still recorded, and one with a client
  // claim at stake is critical whatever the mark says (isCritical).
  parsed.data.conflicts.forEach((c, i) => {
    if (c.critical !== undefined) return;
    c.critical = false;
    warnings.push({ code: "conflict", path: `conflicts[${i}]`, message: "critical was left out; counted as false" });
  });
  const findings = new Set(state.evidence.filter((e) => e.kind === "finding").map((e) => e.id));
  const hosts = new Map(state.evidence.map((e) => [e.id, e.hosts]));
  const freshIds = new Set(fresh.map((e) => e.id));
  const goals = new Set(state.goals.map((g) => g.id));
  const objects = new Set([...state.analysis.rom.objects.map((o) => o.id), ...state.objectsFound.map((o) => o.id)]);
  const assumptions = new Set(state.analysis.assumptions.map((x) => x.id));
  const planned = new Set(openParts(state).map((x) => x.part.id));

  parsed.data.conflicts.forEach((c, i) => {
    const path = `conflicts[${i}]`;
    const err = (message: string) => errors.push({ code: "conflict", path, message });
    const unknown = c.side_a.filter((id) => !findings.has(id));
    if (!c.side_a.length) err("side_a needs at least one evidence ID");
    if (unknown.length) err(`side_a: unknown finding IDs ${unknown.join(", ")}`);
    let evidenceIds = [...c.side_a];
    if (c.type === "source_vs_source" || c.type === "time_dependent") {
      const bad = c.side_b.filter((id) => !findings.has(id));
      if (!c.side_b.length) err("side_b needs at least one evidence ID");
      if (bad.length) err(`side_b: unknown finding IDs ${bad.join(", ")}`);
      if (c.side_a.some((id) => c.side_b.includes(id))) err("the same finding is on both sides");
      if (c.type === "source_vs_source" && sameSource(c.side_a, c.side_b, hosts)) {
        err("both sides cite the same source; two parts of one page or site are not a disagreement between sources (leave it out, or use time_dependent if dates explain it)");
      }
      evidenceIds = [...evidenceIds, ...c.side_b];
      if (c.type === "source_vs_source" && c.claim && !assumptions.has(c.claim)) err(`claim: unknown assumption ${c.claim}; use an assumption ID or leave it empty`);
    } else if (c.type === "evidence_vs_assumption") {
      if (c.side_b.length !== 1 || !assumptions.has(c.side_b[0]!)) err("side_b must be one assumption ID");
    } else if (c.type === "evidence_vs_frame") {
      if (c.side_b.length !== 1 || !(FRAME_FIELDS as readonly string[]).includes(c.side_b[0]!)) err("side_b must be one of time_frame, place, purpose");
    } else if (c.type === "off_target") {
      if (c.side_b.length !== 1 || !objects.has(c.side_b[0]!)) err("side_b must be one object ID");
    } else if (c.type === PLAN_CONFLICT) {
      if (c.side_b.length !== 1 || !planned.has(c.side_b[0]!)) err(`side_b must be one planned part ID listed under <plan>${planned.size ? "" : "; there is none, so leave this conflict out"}`);
    }
    if (!evidenceIds.some((id) => freshIds.has(id))) err("a conflict must involve at least one new evidence line");
    if (c.type !== PLAN_CONFLICT && !goals.has(c.about) && !objects.has(c.about)) err(`about: unknown goal or object ${c.about}`);
    if (!c.statement.trim() || c.statement.length > 300) err("statement must be one sentence of 1–300 characters");
    if (c.settle_by.length > 300) err("settle_by is longer than 300 characters");
    if (c.type === "time_dependent" && !c.condition.trim()) err("a time_dependent conflict needs its condition");
    if ((c.type === "source_vs_source" || c.type === "evidence_vs_assumption") && !c.settle_by.trim()) err("settle_by: say what evidence would settle it");
    const duplicate = state.conflicts.find((o) => o.status === "open" && o.type === c.type && sameSet(o.sideA, c.side_a) && sameSet(o.sideB, c.side_b));
    if (duplicate) warnings.push({ code: "duplicate_conflict", path, message: `repeats ${duplicate.id}; ignored` });
  });
  return { value: parsed.data, errors, warnings };
}

/** Do both sides rest on one and the same host? Lines without links cannot tell, so they never count as the same source. */
function sameSource(a: string[], b: string[], hosts: Map<string, string[]>): boolean {
  const of = (ids: string[]) => new Set(ids.flatMap((id) => hosts.get(id) ?? []));
  const ha = of(a);
  const hb = of(b);
  return ha.size > 0 && hb.size > 0 && [...ha].every((h) => hb.has(h)) && [...hb].every((h) => ha.has(h));
}

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x) => b.includes(x));
}

/** Keep only the items no error points to. */
export function validConflicts(reply: ConflictsReply, errors: Issue[]): ConflictsReply {
  const bad = new Set(errors.flatMap((e) => {
    const m = /^conflicts\[(\d+)\]/.exec(e.path);
    return m ? [Number(m[1])] : [];
  }));
  return { conflicts: reply.conflicts.filter((_, i) => !bad.has(i)) };
}

export function runConflictChecker(model: BaseChatModel, state: EbdState, fresh: EvidenceLine[]): Promise<CallOutcome<ConflictsReply>> {
  return structuredCall({
    model,
    role: "conflict_checker",
    system: conflictSystem(Boolean(state.map), Boolean(state.premises?.given.length)),
    message: conflictMessage(state, fresh),
    tool: { name: CONFLICT_TOOL, description: "Submit the conflicts found in this round's evidence (an empty list if none).", schema: conflictsToolSchema(Boolean(state.map)) },
    check: (args) => checkConflicts(args, state, fresh),
    fallback: (last, errors) => validConflicts(last, errors),
    lists: { ids: ["side_a", "side_b"], texts: [] },
  });
}

type SettleLimits = Pick<EbdOptions, "maxDepth" | "maxOpenGoals" | "maxNewGoalsPerRound">;

/**
 * Why a conflict gets no settle goal, or null when it gets one. Settle goals obey
 * the limits of new goals (section 10.2), and a goal has at most one open settle
 * goal at a time. Without these limits the first live runs (2026-10-20) grew
 * settle goals from the evidence of settle goals until the budget ran out.
 */
export function settleBlock(state: EbdState, about: Goal | undefined, options: SettleLimits, round: number): string | null {
  if (!about) return "it is not about a goal";
  if (about.need !== "necessary") return `${about.id} is a completing goal`;
  // Live round 3 (2026-10-20): a settle goal is where its disagreement is resolved, and a goal already
  // given up on gains nothing from one. Their conflicts are disputed, and the writer shows both sides.
  if (about.settles) return `${about.id} is itself settling a disagreement`;
  if (isSettled(about) && about.status !== "answered") return `${about.id} is already ${about.status}`;
  if (about.depth + 1 > options.maxDepth) return `a settle goal would be at depth ${about.depth + 1}, beyond maxDepth ${options.maxDepth}`;
  const pending = state.goals.find((g) => g.settles && !isSettled(g) && g.leadsTo.includes(about.id));
  if (pending) return `${about.id} already waits for the settle goal ${pending.id}`;
  const created = state.goals.filter((g) => g.createdRound === round + 1 && g.origin.type !== "request").length;
  if (created >= options.maxNewGoalsPerRound) return `the quota of ${options.maxNewGoalsPerRound} new goals per round is reached`;
  if (state.goals.filter((g) => !isSettled(g)).length >= options.maxOpenGoals) return `${options.maxOpenGoals} open goals reached`;
  return null;
}

/** The assumption a conflict decides: side_b of evidence_vs_assumption, the checker's claim for source_vs_source, otherwise none. */
export function claimOf(c: ConflictItem): string | null {
  if (c.type === "evidence_vs_assumption") return c.side_b[0] ?? null;
  return c.type === "source_vs_source" && c.claim ? c.claim : null;
}

/**
 * The goal that already checks the claim of an evidence_vs_assumption conflict on the same
 * findings in this round, or null (Lab 4 review, 2026-10-26). The round analyst judges that goal
 * next, on those findings, so a settle goal would only repeat the check: in the false-premise
 * test one spent 2 of 5 researchers re-proving a launch year the verification goal had already
 * contradicted. A disagreement between sources keeps its settle goal, which hands the researcher
 * both sides and what would settle them.
 */
export function checkedThisRound(state: EbdState, c: ConflictItem, round: number): Goal | null {
  const claim = c.type === "evidence_vs_assumption" ? claimOf(c) : null;
  if (!claim) return null;
  const served = new Set(state.results.filter((r) => r.round === round && r.status === "ok").flatMap((r) => r.goalIds));
  const onLines = new Set(c.side_a.flatMap((id) => state.evidence.find((e) => e.id === id)?.goalIds ?? []));
  const checking = state.goals.filter((g) => served.has(g.id) && !isSettled(g) && g.verifies.includes(claim) && onLines.has(g.id));
  return checking.find((g) => g.id === c.about) ?? checking[0] ?? null;
}

/**
 * Record the conflicts and apply their effects (section 9). Mutates the state.
 * - source_vs_source and evidence_vs_assumption: one settle goal, within the
 *   limits of settleBlock; otherwise the conflict is disputed at once, and the
 *   writer presents both sides. The settle goal checks a claim only when the
 *   disagreement decides it (`claimOf`). An evidence_vs_assumption conflict whose
 *   claim a goal served this round already checks on the same findings gets no
 *   settle goal yet: it waits for that goal's verdict (`resolveClaimChecks`);
 * - off_target, evidence_vs_frame and time_dependent: settled at once; the
 *   writer input handles them (section 12).
 * Section 20: each record keeps the critical mark, and a disagreement that is not
 * critical is recorded as disputed at once, without a settle goal.
 * Section 29: so is a critical one that decides no claim of the question; the writer
 * is told about it.
 */
export function applyConflicts(state: EbdState, reply: ConflictsReply, round: number, options: SettleLimits, log: (line: string) => void): Conflict[] {
  const added: Conflict[] = [];
  // Section 20: a conflict with a client claim at stake is handled first, so that it is never the one
  // left without a settle goal when a round has several critical conflicts.
  const items = [...reply.conflicts].sort((x, y) => Number(claimOf(y) !== null) - Number(claimOf(x) !== null));
  for (const c of items) {
    if (state.conflicts.some((o) => o.status === "open" && o.type === c.type && sameSet(o.sideA, c.side_a) && sameSet(o.sideB, c.side_b))) continue;
    const conflict: Conflict = {
      id: `C${state.conflicts.length + 1}`,
      type: c.type,
      about: c.about,
      statement: c.statement,
      sideA: c.side_a,
      sideB: c.side_b,
      settleBy: c.settle_by,
      condition: c.condition,
      claim: claimOf(c),
      critical: null,
      status: "open",
      createdRound: round,
      settledRound: null,
      settleGoal: null,
      checkedBy: null,
    };
    // A client claim at stake makes a conflict critical whatever the checker's mark says.
    conflict.critical = isCritical({ ...conflict, critical: c.critical === true });
    if (c.type === PLAN_CONFLICT) {
      // Section 19: a finding against a planned part overwrites it at once; nothing is left to settle.
      const hit = openParts(state).find((x) => x.part.id === c.side_b[0]);
      if (!hit || !state.map || !overwritePart(state.map, hit.part.id, c.side_a, "", conflict.id, round)) continue;
      conflict.about = hit.event.goalId;
      conflict.status = "settled";
      conflict.settledRound = round;
      state.conflicts.push(conflict);
      added.push(conflict);
      const goal = state.goals.find((g) => g.id === hit.event.goalId);
      if (goal) {
        syncGoal(goal, hit.event);
        if (!liveParts(hit.event).length && !isSettled(goal)) settle(goal, "moot", round);
      }
      log(`${conflict.id} (${c.type}): planned part ${hit.part.id} "${hit.part.text}" of ${hit.event.goalId} overwritten by ${c.side_a.join(", ")}; it leaves the plan`);
      continue;
    }
    state.conflicts.push(conflict);
    added.push(conflict);
    if (c.type === "source_vs_source" || c.type === "evidence_vs_assumption") {
      if (!conflict.critical) {
        conflict.status = "disputed";
        conflict.settledRound = round;
        log(`${conflict.id} (${c.type}) about ${c.about}: not critical, so it gets no settle goal; recorded as a disagreement about a detail`);
        continue;
      }
      // Section 29: a disagreement that decides no claim of the question is reported, not researched
      // again. In the 12 sealed runs of 2026-11-18, 6 of the 9 researchers sent to settle a
      // disagreement went to one between sources only, and 6 of the 9 settled nothing.
      if (conflict.claim === null) {
        conflict.status = "disputed";
        conflict.settledRound = round;
        log(`${conflict.id} (${c.type}) about ${c.about}: it decides no claim of the question, so it is reported and not researched again`);
        continue;
      }
      const checking = checkedThisRound(state, c, round);
      if (checking) {
        conflict.checkedBy = checking.id;
        log(`${conflict.id} (${c.type}) about ${c.about}: no settle goal yet, because ${checking.id} checks ${conflict.claim} on these findings and is judged in this round`);
        continue;
      }
      openSettleGoal(state, conflict, options, round, log);
    } else {
      conflict.status = "settled";
      conflict.settledRound = round;
      log(`${conflict.id} (${c.type}) about ${c.about}: recorded and settled${c.condition ? ` (${c.condition})` : ""}`);
    }
  }
  return added;
}

/**
 * Give a disagreement that decides a claim of the question its settle goal, or dispute it when
 * settleBlock forbids one. No other disagreement gets here (section 29).
 */
function openSettleGoal(state: EbdState, conflict: Conflict, options: SettleLimits, round: number, log: (line: string) => void): void {
  const about = state.goals.find((g) => g.id === conflict.about);
  const blocked = settleBlock(state, about, options, round);
  if (blocked || !about) {
    conflict.status = "disputed";
    conflict.settledRound = round;
    log(`${conflict.id} (${conflict.type}) about ${conflict.about}: disputed without a settle goal, because ${blocked}`);
    return;
  }
  const goal = newGoal({
    id: nextGoalId(state),
    text: `Which account is correct, and under what conditions? ${conflict.statement}`,
    objectIds: about.objectIds,
    template: "T7",
    guideline: "G7",
    need: about.need,
    verifies: conflict.claim ? [conflict.claim] : [],
    doneWhen: conflict.settleBy,
    origin: { type: "conflict", conflict: conflict.id },
    depth: about.depth + 1,
    leadsTo: [about.id],
    createdRound: round + 1,
    settles: conflict.id,
  });
  state.goals.push(goal);
  conflict.settleGoal = goal.id;
  log(`${conflict.id} (${conflict.type}) about ${conflict.about}: settle goal ${goal.id} created`);
}

/**
 * After the round analyst (Lab 5 review, change 2): a conflict that waited for a goal's verdict
 * on its claim is settled only when the verdict is supported or contradicted; that goal's notes
 * then show which account holds. Unsettled, or no verdict, leaves a real disagreement, which is
 * handled like any other: a settle goal within the limits, or disputed.
 */
export function resolveClaimChecks(state: EbdState, round: number, options: SettleLimits, log: (line: string) => void): void {
  for (const conflict of state.conflicts) {
    if (conflict.status !== "open" || !conflict.checkedBy || conflict.settleGoal) continue;
    const goal = state.goals.find((g) => g.id === conflict.checkedBy);
    const verdict = conflict.claim ? goal?.verdicts[conflict.claim] : undefined;
    if (verdict === "supported" || verdict === "contradicted") {
      conflict.status = "settled";
      conflict.settledRound = round;
      conflict.settleGoal = conflict.checkedBy;
      log(`${conflict.id}: settled by ${conflict.checkedBy}, which judged ${conflict.claim} ${verdict}`);
      continue;
    }
    log(`${conflict.id}: ${conflict.checkedBy} left ${conflict.claim} ${verdict ?? "without a verdict"}, so the disagreement stays open`);
    openSettleGoal(state, conflict, options, round, log);
  }
}

/**
 * Which settle goals are necessary (Lab 4 review, 2026-10-26), run after the judgments of
 * every round. A settle goal is necessary while its disagreement decides a claim, or while a
 * goal waits for it because the round analyst judged that goal conflicting. Otherwise the
 * disagreement is about a detail the goal can be answered without (in the flight test, the
 * fastest itinerary's duration), so the settle goal is completing: it is served after the
 * necessary goals, from spare researchers, and its conflict does not hold up the stop. If it is
 * never served, the writer presents both sides.
 * Section 20: a settle goal exists only for a critical conflict, which the answer depends on, so
 * it is necessary.
 */
export function settlePriority(state: EbdState, log: (line: string) => void): void {
  for (const goal of state.goals) {
    if (!goal.settles || isSettled(goal)) continue;
    const conflict = state.conflicts.find((c) => c.id === goal.settles);
    const decides = conflict?.claim ?? null;
    const awaited = state.goals.some((w) => w.waitingOn === goal.id && w.status === "conflicting");
    const critical = Boolean(conflict && isCritical(conflict));
    const need = decides || awaited || critical ? "necessary" : "completing";
    if (goal.need === need) continue;
    goal.need = need;
    goal.level = levelOf(goal.kind, need);
    log(`${goal.id}: ${need}, because ${decides ? `it decides ${decides}` : awaited ? "a goal waits for it" : critical ? "its conflict is critical" : "it decides no claim and no goal waits for it"}`);
  }
}
