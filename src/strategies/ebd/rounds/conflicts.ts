/**
 * The conflict checker (design section 9): one model call per round, before the
 * round analyst (D-D), so H1 is attributable to it and `conflicts: false` turns
 * it off. It cites evidence line IDs only; code checks every record and applies
 * its effects. A conflict without valid evidence on both sides is not recorded.
 */
import { z } from "zod";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { Issue } from "../request/index.js";
import { levelOf, newGoal, nextGoalId } from "../goals.js";
import type { EbdOptions } from "../options.js";
import { structuredCall, zodIssues, type CallOutcome, type Checked } from "../llm.js";
import { CONFLICT_TYPES, isSettled, type Conflict, type EbdState, type EvidenceLine, type Goal } from "../state.js";

export const CONFLICT_TOOL = "submit_conflicts";
const FRAME_FIELDS = ["time_frame", "place", "purpose"] as const;
const MAX_EARLIER = 60;

export const ConflictsApiSchema = z.object({
  conflicts: z.array(
    z.object({
      type: z.enum(CONFLICT_TYPES),
      about: z.string().describe("The goal ID (Q…) or object ID (O…) the conflict is about"),
      statement: z.string().describe("One neutral sentence: what the two sides say"),
      side_a: z.array(z.string()).describe("Evidence IDs of one side"),
      side_b: z.array(z.string()).describe("By type: evidence IDs, one assumption ID, one frame field, or one object ID"),
      settle_by: z.string().describe("What evidence would settle it; empty for off_target and time_dependent"),
      condition: z.string().describe("time_dependent only: when each side holds; otherwise empty"),
      claim: z.string().describe("The assumption ID (A…) whose truth this disagreement decides, or empty"),
    }),
  ),
});
export type ConflictsReply = z.infer<typeof ConflictsApiSchema>;
type ConflictItem = ConflictsReply["conflicts"][number];

export const CONFLICT_SYSTEM = `You are the conflict checker of a research team that follows Environment-Based Design (EBD). In EBD a conflict is two competing claims about one thing; the research continues until no undesired conflict is left open. Your job is narrow: compare this round's new evidence with the earlier evidence, the client's assumptions and the question's frame, and list the real conflicts. You do not judge which side is right and you do not summarise the research.

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
- If there is no conflict, return an empty list.

Reply by calling ${CONFLICT_TOOL} once with the whole list.`;

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
  return [
    `<run_date>${state.today}</run_date>`,
    `<question>\n${state.question}\n</question>`,
    `<frame>\n${frameText(state)}\n</frame>`,
    `<assumptions>\n${a.assumptions.map((x) => `${x.id}: ${x.claim}`).join("\n") || "(none)"}\n</assumptions>`,
    `<objects>\n${[...a.rom.objects.map((o) => `${o.id} "${o.text}": ${o.meaning}`), ...state.objectsFound.map((o) => `${o.id} "${o.text}": found in ${o.evidence}`)].join("\n")}\n</objects>`,
    `<goals>\n${state.goals.map((g) => `${g.id} [${g.objectIds.join(",")}] ${g.text}`).join("\n")}\n</goals>`,
    `<new_evidence>\n${fresh.filter((e) => e.kind === "finding").map(line).join("\n") || "(none)"}\n</new_evidence>`,
    `<earlier_evidence>\n${earlier.map(line).join("\n") || "(none)"}\n</earlier_evidence>`,
    `<recorded_conflicts>\n${state.conflicts.map((c) => `${c.id} ${c.type} (${c.status}) about ${c.about}: ${c.statement}`).join("\n") || "(none)"}\n</recorded_conflicts>`,
  ].join("\n");
}

/** Code checks of one reply (section 9). Errors carry the item's path, so the fallback can keep the valid items. */
/** A conflict without a claim decides no assumption (review of 2026-10-21). */
function withDefaultClaims(args: unknown): unknown {
  if (!args || typeof args !== "object" || Array.isArray(args)) return args;
  const list = (args as { conflicts?: unknown }).conflicts;
  if (!Array.isArray(list)) return args;
  return { ...args, conflicts: list.map((c) => (c && typeof c === "object" && !("claim" in c) ? { ...c, claim: "" } : c)) };
}

export function checkConflicts(args: unknown, state: EbdState, fresh: EvidenceLine[]): Checked<ConflictsReply> {
  const parsed = ConflictsApiSchema.safeParse(withDefaultClaims(args));
  if (!parsed.success) return { value: null, errors: zodIssues(parsed.error), warnings: [] };
  const errors: Issue[] = [];
  const warnings: Issue[] = [];
  const findings = new Set(state.evidence.filter((e) => e.kind === "finding").map((e) => e.id));
  const hosts = new Map(state.evidence.map((e) => [e.id, e.hosts]));
  const freshIds = new Set(fresh.map((e) => e.id));
  const goals = new Set(state.goals.map((g) => g.id));
  const objects = new Set([...state.analysis.rom.objects.map((o) => o.id), ...state.objectsFound.map((o) => o.id)]);
  const assumptions = new Set(state.analysis.assumptions.map((x) => x.id));

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
    }
    if (!evidenceIds.some((id) => freshIds.has(id))) err("a conflict must involve at least one new evidence line");
    if (!goals.has(c.about) && !objects.has(c.about)) err(`about: unknown goal or object ${c.about}`);
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
    system: CONFLICT_SYSTEM,
    message: conflictMessage(state, fresh),
    tool: { name: CONFLICT_TOOL, description: "Submit the conflicts found in this round's evidence (an empty list if none).", schema: ConflictsApiSchema },
    check: (args) => checkConflicts(args, state, fresh),
    fallback: (last, errors) => validConflicts(last, errors),
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
 *   settle goal: it is settled, and that goal's notes show which account holds;
 * - off_target, evidence_vs_frame and time_dependent: settled at once; the
 *   writer input handles them (section 12).
 */
export function applyConflicts(state: EbdState, reply: ConflictsReply, round: number, options: SettleLimits, log: (line: string) => void): Conflict[] {
  const added: Conflict[] = [];
  for (const c of reply.conflicts) {
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
      status: "open",
      createdRound: round,
      settledRound: null,
      settleGoal: null,
    };
    state.conflicts.push(conflict);
    added.push(conflict);
    if (c.type === "source_vs_source" || c.type === "evidence_vs_assumption") {
      const checking = checkedThisRound(state, c, round);
      if (checking) {
        conflict.status = "settled";
        conflict.settledRound = round;
        conflict.settleGoal = checking.id;
        log(`${conflict.id} (${c.type}) about ${c.about}: no settle goal, because ${checking.id} checks ${conflict.claim} on these findings and is judged in this round`);
        continue;
      }
      const about = state.goals.find((g) => g.id === c.about);
      const blocked = settleBlock(state, about, options, round);
      if (blocked || !about) {
        conflict.status = "disputed";
        conflict.settledRound = round;
        log(`${conflict.id} (${c.type}) about ${c.about}: disputed without a settle goal, because ${blocked}`);
        continue;
      }
      const goal = newGoal({
        id: nextGoalId(state),
        text: `Which account is correct, and under what conditions? ${c.statement}`,
        objectIds: about.objectIds,
        template: "T7",
        guideline: "G7",
        need: about.need,
        verifies: conflict.claim ? [conflict.claim] : [],
        doneWhen: c.settle_by,
        origin: { type: "conflict", conflict: conflict.id },
        depth: about.depth + 1,
        leadsTo: [about.id],
        createdRound: round + 1,
        settles: conflict.id,
      });
      state.goals.push(goal);
      conflict.settleGoal = goal.id;
      log(`${conflict.id} (${c.type}) about ${c.about}: settle goal ${goal.id} created`);
    } else {
      conflict.status = "settled";
      conflict.settledRound = round;
      log(`${conflict.id} (${c.type}) about ${c.about}: recorded and settled${c.condition ? ` (${c.condition})` : ""}`);
    }
  }
  return added;
}

/**
 * Which settle goals are necessary (Lab 4 review, 2026-10-26), run after the judgments of
 * every round. A settle goal is necessary while its disagreement decides a claim, or while a
 * goal waits for it because the round analyst judged that goal conflicting. Otherwise the
 * disagreement is about a detail the goal can be answered without (in the flight test, the
 * fastest itinerary's duration), so the settle goal is completing: it is served after the
 * necessary goals, from spare researchers, and its conflict does not hold up the stop. If it is
 * never served, the writer presents both sides.
 */
export function settlePriority(state: EbdState, log: (line: string) => void): void {
  for (const goal of state.goals) {
    if (!goal.settles || isSettled(goal)) continue;
    const decides = state.conflicts.find((c) => c.id === goal.settles)?.claim ?? null;
    const awaited = state.goals.some((w) => w.waitingOn === goal.id && w.status === "conflicting");
    const need = decides || awaited ? "necessary" : "completing";
    if (goal.need === need) continue;
    goal.need = need;
    goal.level = levelOf(goal.kind, need);
    log(`${goal.id}: ${need}, because ${decides ? `it decides ${decides}` : awaited ? "a goal waits for it" : "it decides no claim and no goal waits for it"}`);
  }
}
