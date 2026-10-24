/**
 * From goals to researcher briefs (design section 7). Ranking works on goals;
 * packing groups the top ready goals by their primary object, at most
 * `questionsPerBrief` per brief and `maxPerRound` briefs per round. One slot
 * goes to the necessary goal that has waited longest.
 */
import type { ResearchBriefInput } from "../../core/index.js";
import type { Analysis } from "./request/index.js";
import { longestWaiting, type Ranked } from "./goals.js";
import type { EbdOptions } from "./options.js";
import type { Conflict, EbdState, Goal } from "./state.js";

export const VERIFY_INSTRUCTION =
  "State whether the evidence supports, contradicts or does not settle the claim. Look specifically for evidence that contradicts it. Give each source's finding with its date and scope; report disagreements, do not resolve them.";

const PRIMARY_SOURCES = "primary records; at least two independent publishers";

type Group = { key: string; goals: Goal[] };

function keyOf(goal: Goal): string {
  return goal.objectIds[0] ?? goal.id;
}

/** Greedy packing in rank order. Goals that do not fit wait for a later round. */
export function pack(goals: Goal[], options: Pick<EbdOptions, "maxPerRound" | "questionsPerBrief">): Group[] {
  const groups: Group[] = [];
  for (const goal of goals) {
    const key = keyOf(goal);
    const open = groups.find((g) => g.key === key && g.goals.length < options.questionsPerBrief);
    if (open) open.goals.push(goal);
    else if (groups.length < options.maxPerRound) groups.push({ key, goals: [goal] });
  }
  return groups;
}

/** Pack the ranked goals; if the longest-waiting necessary goal missed out, it takes the place of the lowest-ranked packed goals. */
export function selectGroups(ranked: Ranked[], options: Pick<EbdOptions, "maxPerRound" | "questionsPerBrief">): { groups: Group[]; reserve: string | null } {
  const goals = ranked.map((r) => r.goal);
  const groups = pack(goals, options);
  const reserve = longestWaiting(ranked);
  const packed = (gs: Group[]) => gs.flatMap((g) => g.goals);
  if (!reserve || packed(groups).includes(reserve)) return { groups, reserve: null };
  const chosen = packed(groups).sort((a, b) => goals.indexOf(a) - goals.indexOf(b));
  while (chosen.length) {
    chosen.pop();
    const retry = pack([...chosen, reserve], options);
    if (packed(retry).includes(reserve)) return { groups: retry, reserve: reserve.id };
  }
  return { groups, reserve: null };
}

/** A necessary request goal that has never been served. */
export function isFirstTry(goal: Goal): boolean {
  return goal.origin.type === "request" && goal.need === "necessary" && goal.status === "open" && goal.attempts === 0;
}

/** Never held back by the first-try reserve: a brief with a request goal, or with a settle goal a request goal waits for. */
function isProtected(group: Group, state: EbdState): boolean {
  return group.goals.some((g) => g.origin.type === "request" || state.goals.some((w) => w.waitingOn === g.id && w.origin.type === "request"));
}

export type Selection = {
  groups: Group[];
  reserve: string | null;
  /** Goals held back for first tries. */
  held: Goal[];
  /** The first tries the held researchers are kept for, and how many researchers that is. */
  reservedFor: Goal[];
  researchersKept: number;
  /** Holding back would have left no brief at all, so nothing was held. */
  released: boolean;
};

/**
 * The first-try reserve (section 7): researchers stay available for the necessary request
 * goals that have never been served, counting those still waiting for their dependencies.
 * A brief made only of goals added during the run is served only from researchers beyond
 * that reserve; its goals wait, and the freed slots go to the next ranked goals.
 */
export function selectWithReserve(
  ranked: Ranked[],
  state: EbdState,
  budget: number,
  options: Pick<EbdOptions, "maxPerRound" | "questionsPerBrief" | "reserveFirstTries">,
): Selection {
  const first = selectGroups(ranked, options);
  const nothing = { held: [], reservedFor: [], researchersKept: 0, released: false };
  if (!options.reserveFirstTries || budget <= 0) return { ...first, ...nothing };
  let selection = first;
  let candidates = ranked;
  const held: Goal[] = [];
  for (;;) {
    const served = new Set(selection.groups.flatMap((g) => g.goals.map((x) => x.id)));
    const reservedFor = state.goals.filter((g) => isFirstTry(g) && !served.has(g.id));
    const researchersKept = pack(reservedFor, { ...options, maxPerRound: Number.MAX_SAFE_INTEGER }).length;
    let room = budget - selection.groups.filter((g) => isProtected(g, state)).length - researchersKept;
    const groups = selection.groups.filter((g) => isProtected(g, state) || room-- > 0);
    const now = selection.groups.filter((g) => !groups.includes(g)).flatMap((g) => g.goals);
    if (!now.length) {
      if (!groups.length && held.length) return { ...first, ...nothing, released: true };
      return { groups, reserve: selection.reserve, held, reservedFor, researchersKept, released: false };
    }
    held.push(...now);
    candidates = candidates.filter((r) => !now.includes(r.goal));
    selection = selectGroups(candidates, options);
  }
}

function frameConstraints(a: Analysis): string[] {
  const out: string[] = [];
  for (const [label, f] of [["Time frame", a.frame.time_frame], ["Place", a.frame.place]] as const) {
    if (f.value !== null && f.basis !== "unknown") out.push(`${label} (${f.basis}): ${f.value}`);
  }
  return out;
}

/** The reading the question fixes, e.g. an acronym's spelled-out expansion (section 7). */
function readingConstraints(a: Analysis, objectIds: string[]): string[] {
  const spans = new Set(objectIds);
  return a.rom.objects
    .filter((o) => spans.has(o.id) && o.readings.length === 0 && o.status === "needs_question" && /\(.+\)|[A-Z]{2,}/.test(o.text))
    .map((o) => `"${o.text}" means: ${o.meaning}`);
}

/**
 * Who must follow each kind of client directive (sections 7 and 12).
 * Researchers get what limits the evidence; the writer gets what shapes the
 * report; scope limits and unclassified directives go to both, so none is lost.
 */
const DIRECTIVE_READERS: Record<Analysis["client_directives"][number]["kind"], { researchers: boolean; writer: boolean; label: string }> = {
  source_preference: { researchers: true, writer: false, label: "Client source preference" },
  scope_limit: { researchers: true, writer: true, label: "Client scope limit" },
  report_format: { researchers: false, writer: true, label: "Client report format" },
  other: { researchers: true, writer: true, label: "Client directive" },
};

/** One line per directive, with the client's own words next to the analyst's wording. */
export function directiveLines(a: Analysis, reader: "researchers" | "writer"): string[] {
  return a.client_directives
    .filter((d) => DIRECTIVE_READERS[d.kind][reader])
    .map((d) => `${DIRECTIVE_READERS[d.kind].label}: ${d.text}${d.evidence.length ? ` (client's words: ${d.evidence.map((e) => `"${e}"`).join("; ")})` : ""}`);
}

/** A disclosed default purpose; time and place defaults are already in the frame constraints. */
function defaultConstraints(a: Analysis): string[] {
  const p = a.frame.purpose;
  return p.basis === "default" && p.value !== null ? [`Assumed purpose (not stated by the client): ${p.value}`] : [];
}

/** At most 3 verbatim takeaways from earlier notes on the same object, as orientation (from round 2). */
function earlierTakeaways(state: EbdState, goals: Goal[]): string[] {
  const objects = new Set(goals.flatMap((g) => g.objectIds));
  const related = new Set(state.goals.filter((g) => g.objectIds.some((o) => objects.has(o))).map((g) => g.id));
  const out: string[] = [];
  for (const r of [...state.results].reverse()) {
    for (const s of r.sections) {
      if (s.takeaway && s.goalIds.some((id) => related.has(id)) && !out.includes(s.takeaway)) out.push(s.takeaway);
      if (out.length >= 3) return out;
    }
  }
  return out;
}

function settleInstruction(goal: Goal, conflicts: Conflict[], state: EbdState): string {
  const c = conflicts.find((x) => x.id === goal.settles);
  if (!c) return "";
  const side = (ids: string[]) => ids.map((id) => state.evidence.find((e) => e.id === id)?.text ?? id).join(" | ");
  return `This goal settles a disagreement: ${c.statement} One side: ${side(c.sideA)} The other side: ${side(c.sideB)} What would settle it: ${c.settleBy} Report what the evidence shows for each side; do not resolve it beyond the evidence.`;
}

function claimOf(goal: Goal, a: Analysis): string {
  const claims = a.assumptions.filter((x) => goal.verifies.includes(x.id)).map((x) => `'${x.claim}'`);
  return claims.length ? ` The claim: ${claims.join(" and ")}.` : "";
}

/** One brief per group (section 7). `position` orders the platform's drop rule like EBD's own ranking. */
export function briefFor(group: Group, position: number, state: EbdState): ResearchBriefInput {
  const a = state.analysis;
  const goals = group.goals;
  const objectText = a.rom.objects.find((o) => o.id === group.key)?.text ?? group.key;
  const level = Math.min(...goals.map((g) => g.level));
  const hints = [...new Set(goals.flatMap((g) => g.sourceHints))];
  if (goals.some((g) => g.kind === "verify" || g.kind === "settle")) hints.push(PRIMARY_SOURCES);

  const instructions: string[] = goals.map((g) => {
    const parts = [`For [${g.id}], a sufficient answer contains: ${g.doneWhen}`];
    if (g.kind === "verify") parts.push(`${VERIFY_INSTRUCTION}${claimOf(g, a)}`);
    if (g.kind === "settle") parts.push(settleInstruction(g, state.conflicts, state));
    if (g.retryNote) parts.push(g.retryNote);
    return parts.filter(Boolean).join(" ");
  });
  const takeaways = state.roundsObserved > 0 ? earlierTakeaways(state, goals) : [];
  if (takeaways.length) {
    instructions.push(`Earlier notes on this topic, for orientation only (re-find and cite sources yourself):\n${takeaways.map((t) => `- ${t}`).join("\n")}`);
  }

  return {
    objective: goals.length === 1 ? goals[0]!.text : `Answer the key questions below about "${objectText}".`,
    keyQuestions: goals.map((g) => `[${g.id}] ${g.text}${g.missing.length && g.attempts > 0 ? ` Still missing: ${g.missing.join("; ")}` : ""}`),
    constraints: [...frameConstraints(a), ...readingConstraints(a, goals.flatMap((g) => g.objectIds)), ...defaultConstraints(a), ...directiveLines(a, "researchers")],
    sourceHints: [...new Set(hints)].slice(0, 5),
    instructions: instructions.join("\n"),
    priority: 100 - 10 * level - position,
    tag: goals.map((g) => g.id).join(","),
  };
}
