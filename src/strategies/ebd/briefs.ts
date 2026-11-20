/**
 * From goals to researcher briefs (design section 7). Ranking works on goals;
 * packing groups the top ready goals by their primary object, at most
 * `questionsPerBrief` per brief and `maxPerRound` briefs per round. One slot
 * goes to the necessary goal that has waited longest.
 */
import type { ResearchBriefInput } from "../../core/index.js";
import type { Analysis } from "./analysis.js";
import { assumptionVerdicts, longestWaiting, refutedObjects, type Ranked } from "./goals.js";
import type { EbdOptions } from "./options.js";
import { eventOf, isPlanned, type Conflict, type EbdState, type Goal, type MapPart } from "./state.js";

export const VERIFY_INSTRUCTION =
  "State whether the evidence supports, contradicts or does not settle the claim. Look specifically for evidence that contradicts it. Give each source's finding with its date and scope; report disagreements, do not resolve them.";

/**
 * For a main part that shares a researcher and is asked as one question, with its key questions listed
 * in the instructions (section 19): they are the plan's assumptions, and the sources decide.
 */
export const PLANNED_PARTS_INSTRUCTION =
  "These parts are what the plan expects this step to involve, not facts. Report what the sources actually say about each. When the sources show that a part does not exist or does not apply here, say so plainly and cite them. Add any other main point that the sources treat as part of this step.";

/**
 * For a main part asked by its key questions (sections 21 and 28): each key question is a key question
 * of the brief, so the researcher answers and sources each one. The key questions were written in full
 * by the environment analyst, who may name what it knows as examples: they are expectations, and the
 * sources decide.
 */
export const PLAN_QUESTIONS_INSTRUCTION =
  "Its key questions are what the plan expects this part of the answer to need. They, and every example they name, are expectations, not facts. Report what the sources actually say on each. When the sources show that something a key question takes for granted did not happen, does not exist or does not apply, say so plainly under that key question and cite them. Put any other main point that the sources treat as part of this topic under the key question it is closest to.";

/**
 * A brief asks at most this many key questions: the most the baseline's planner
 * gave one researcher in the comparison of 2026-11-10 (3 to 6, 3.9 on average), and the most parts an
 * event may have. A brief that would ask more keeps one key question per goal.
 */
export const MAX_PART_QUESTIONS = 6;

const PRIMARY_SOURCES = "primary records; at least two independent publishers";

type Group = { key: string; goals: Goal[] };
/**
 * Section 21: how `spread` may move completing goals in a later round. `within` is the goals a brief may hold; `load` is
 * the key questions a brief asks. Section 27: with `step`, which says whether a goal is a main part
 * of the plan, a researcher that would sit idle goes to a part that shares a brief with another part
 * before it goes to any other goal.
 */
export type Regroup = { within: number; load: (group: Group) => number; step?: (goal: Goal) => boolean };

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

/**
 * Lab 5 review, change 3: when fewer briefs than free researchers were packed, split shared
 * briefs, the lowest-ranked goal of the largest brief first, until every free researcher has a
 * brief or every brief has one goal. In the Lab 4 flight run, rounds 1 and 2 sent one researcher
 * each, with every ready goal in one brief, although four could run. `slots` is the number of
 * researchers this round may use: the round limit and the budget less the first-try reserve.
 *
 * Two kinds of split, in this order:
 * - a necessary goal leaves a brief that keeps another necessary goal (the brief with the most
 *   necessary goals gives up its lowest-ranked one); this is always worth a researcher;
 * - any other split leaves a brief of completing goals only. It is made only while, after this
 *   round, one researcher stays for each necessary goal served this round, in case it needs a
 *   retry. `free` is the researchers this round and later, less the first-try reserve.
 * Live rounds of 2026-11-05: in round 9 such splits found the disagreement over nonstop flights
 * and covered the headset's app ecosystem with researchers to spare; in round 10 they took the
 * last researchers, so two necessary headset goals got no retry and a necessary transit goal of
 * the flight run was never served.
 */
export function spread(groups: Group[], slots: number, free: number = slots, regroup: Regroup | null = null): Group[] {
  const out = groups.map((g) => ({ key: g.key, goals: [...g.goals] }));
  const necessary = (g: Group) => g.goals.filter((x) => x.need === "necessary").length;
  // Section 21: when no researcher is free and a brief
  // still holds two necessary goals, the smallest brief made of completing goals only gives up its
  // researcher. Its goals move to other briefs with room: another brief of completing goals first,
  // then the brief that asks the fewest key questions, and never the brief about to be split. In 9 of
  // the 44 plans recorded up to 2026-11-18, two necessary goals of the plan shared a researcher in
  // round 1 while a brief of completing goals had one to itself.
  const freeOne = (from: Group): boolean => {
    if (!regroup) return false;
    const give = out.filter((g) => necessary(g) === 0).sort((a, b) => a.goals.length - b.goals.length)[0];
    if (!give) return false;
    const size = new Map(out.filter((g) => g !== give && g !== from).map((g) => [g, g.goals.length]));
    const load = (g: Group) => regroup.load(g) + size.get(g)! - g.goals.length;
    const moves: [Goal, Group][] = [];
    for (const goal of give.goals) {
      const target = [...size.keys()]
        .filter((g) => size.get(g)! < regroup.within)
        .sort((a, b) => Number(necessary(a) > 0) - Number(necessary(b) > 0) || load(a) - load(b))[0];
      if (!target) return false;
      moves.push([goal, target]);
      size.set(target, size.get(target)! + 1);
    }
    for (const [goal, target] of moves) target.goals.push(goal);
    out.splice(out.indexOf(give), 1);
    return true;
  };
  for (;;) {
    const from = out.reduce<Group | null>((best, g) => (necessary(g) > 1 && (!best || necessary(g) > necessary(best)) ? g : best), null);
    if (!from) break;
    if (out.length >= slots && !freeOne(from)) break;
    const goal = from.goals.filter((x) => x.need === "necessary").at(-1)!;
    from.goals.splice(from.goals.indexOf(goal), 1);
    out.push({ key: keyOf(goal), goals: [goal] });
  }
  const retries = out.reduce((n, g) => n + necessary(g), 0);
  const step = regroup?.step;
  const steps = (g: Group) => (step ? g.goals.filter(step).length : 0);
  while (out.length < slots && free - (out.length + 1) >= retries) {
    // Section 27: first a main part out of a brief that holds two or more, so that each is asked
    // part by part. In 3 of 14 replayed plans of 2026-11-19 the free researcher went to a planned
    // overview question with one key question, while two steps still shared a researcher.
    const crowded = out.reduce<Group | null>((best, g) => (steps(g) > 1 && (!best || steps(g) > steps(best)) ? g : best), null);
    if (crowded && step) {
      const goal = crowded.goals.filter(step).at(-1)!;
      crowded.goals.splice(crowded.goals.indexOf(goal), 1);
      out.push({ key: keyOf(goal), goals: [goal] });
      continue;
    }
    const largest = out.reduce<Group | null>((best, g) => (g.goals.length > 1 && (!best || g.goals.length > best.goals.length) ? g : best), null);
    if (!largest) break;
    const goal = largest.goals.pop()!;
    out.push({ key: keyOf(goal), goals: [goal] });
  }
  return out;
}

/**
 * Section 30: the first round of the plan. Every researcher of
 * the round goes to a main part of the answer, and none is kept for a second try:
 * - as many researchers as parts, or more: each part has a researcher to itself;
 * - fewer researchers than parts, more than necessary parts: each necessary part has a researcher to
 *   itself, and the completing parts share the researchers left;
 * - no more researchers than necessary parts: the necessary parts share the researchers, and the
 *   completing parts are returned as `riders`, to be asked as one question each in a brief with room.
 * `parts` is in rank order. In the replay of 2026-11-19 on 69 saved plans, `spread` kept one researcher
 * for a second try of each necessary part: with the baseline's 3 to 5 researchers a run used 2.7 to
 * 3.2 of them, and 14% to 27% of the parts were asked as one question while a researcher sat idle. In
 * the 12 saved runs on new questions, 2 of 44 necessary planned goals got a second try.
 */
export function partsFirst(parts: Goal[], slots: number): { groups: Group[]; riders: Goal[] } {
  const n = Math.max(1, slots);
  const alone = (g: Goal): Group => ({ key: keyOf(g), goals: [g] });
  const deal = (goals: Goal[], briefs: number): Group[] => {
    const out: Group[] = [];
    goals.forEach((g, i) => (i < briefs ? out.push(alone(g)) : out[i % briefs]!.goals.push(g)));
    return out;
  };
  const necessary = parts.filter((g) => g.need === "necessary");
  const completing = parts.filter((g) => g.need !== "necessary");
  if (n >= parts.length) return { groups: [...necessary, ...completing].map(alone), riders: [] };
  if (n > necessary.length) return { groups: [...necessary.map(alone), ...deal(completing, n - necessary.length)], riders: [] };
  return { groups: deal(necessary, n), riders: completing };
}

/** A necessary request goal that has never been served. */
export function isFirstTry(goal: Goal): boolean {
  return isPlanned(goal) && goal.need === "necessary" && goal.status === "open" && goal.attempts === 0;
}

/** Never held back by the first-try reserve: a brief with a request goal, or with a settle goal a request goal waits for. */
function isProtected(group: Group, state: EbdState): boolean {
  return group.goals.some((g) => isPlanned(g) || state.goals.some((w) => w.waitingOn === g.id && isPlanned(w)));
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

/**
 * Time frame and place. A field taken from the request's words is left out when all those words
 * name a refuted date: in the Lab 4 telescope run the false launch year ("in 2018") still reached
 * later briefs as "Time frame (explicit): 2018". A frame built from other words too is kept.
 */
function frameConstraints(a: Analysis, refutedDates: string[]): string[] {
  const out: string[] = [];
  for (const [label, f] of [["Time frame", a.frame.time_frame], ["Place", a.frame.place]] as const) {
    if (f.value === null || f.basis === "unknown") continue;
    const refuted = f.basis === "explicit" && f.evidence.length > 0 && f.evidence.every((q) => refutedDates.some((t) => q.toLowerCase().includes(t.toLowerCase())));
    if (refuted) continue;
    out.push(`${label} (${f.basis}): ${f.value}`);
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

/** Section 28: what the answer depends on and the client did not state, with the main cases to cover. */
function notStatedConstraints(state: Pick<EbdState, "plan">): string[] {
  return (state.plan?.notStated ?? []).map((t) => `Not stated by the client: ${t}`);
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

/**
 * The planned parts of an event goal that its researcher is asked about: those the evidence has
 * neither confirmed nor refuted. On a first attempt that is every part of the step; on a second
 * attempt, the parts still missing.
 */
export function askedParts(state: Pick<EbdState, "map">, goal: Goal): MapPart[] {
  return (eventOf(state, goal)?.parts ?? []).filter((p) => p.status === "assumed");
}

/**
 * Section 21: the goals of a brief whose planned parts are asked as key questions, one per part.
 * The goals are taken in rank order, and a goal is asked by part while the
 * brief stays within MAX_PART_QUESTIONS; every other goal of the brief keeps its one key question. In
 * a brief with a necessary goal only necessary goals are asked by part, so a completing goal that
 * shares the researcher never takes more of the brief than the goal the report depends on. In the
 * batch of 2026-11-11 a researcher with one compound key question made 4.5 searches on average and
 * one with two or three made 7.1; the baseline's researchers, with 3.9 key questions each, made 6.6
 * and reported 36 findings against 26.
 */
export function askedByPart(group: Group, state: Pick<EbdState, "map">): Set<string> {
  const out = new Set<string>();
  const mainOnly = group.goals.some((g) => g.need === "necessary");
  let total = group.goals.length;
  for (const g of group.goals) {
    const parts = askedParts(state, g).length;
    if (!parts || (mainOnly && g.need !== "necessary") || total - 1 + parts > MAX_PART_QUESTIONS) continue;
    out.add(g.id);
    total += parts - 1;
  }
  return out;
}

/**
 * Section 21: a completing goal that shares a brief with a necessary goal is left for a later round
 * when it keeps that goal from being asked by part. The completing goals go from the end, and only
 * as many as let one more necessary goal be asked by part.
 * In the dry run of 2026-11-18 a necessary step with five parts shared a brief with a completing step
 * and a replaced overview question, and the three were asked as three compound questions.
 */
export function fitBrief(group: Group, state: Pick<EbdState, "map">): { group: Group; left: Goal[] } {
  const riders = group.goals.filter((g) => g.need !== "necessary");
  if (riders.length === group.goals.length) return { group, left: [] };
  let goals = group.goals;
  let asked = askedByPart(group, state).size;
  for (let k = 1; k <= riders.length; k++) {
    const out = riders.slice(riders.length - k);
    const without = group.goals.filter((g) => !out.includes(g));
    const size = askedByPart({ key: group.key, goals: without }, state).size;
    if (size > asked) [goals, asked] = [without, size];
  }
  return { group: { key: group.key, goals }, left: group.goals.filter((g) => !goals.includes(g)) };
}

/** The key questions a brief of these goals asks (section 21): one per goal, or one per part for a goal asked by part. */
export function questionCount(group: Group, state: Pick<EbdState, "map">): number {
  const byPart = askedByPart(group, state);
  return group.goals.reduce((n, g) => n + (byPart.has(g.id) ? askedParts(state, g).length : 1), 0);
}

/** A goal that only checks a claim the question takes for granted (section 26). */
export function isClaimCheck(goal: Goal): boolean {
  return goal.kind === "verify" && goal.verifies.length > 0 && !goal.settles;
}

/**
 * Section 26: the claim checks of the first round join briefs that ask for content, as one key
 * question each, so that none takes a researcher of its own. A check joins a brief that holds a
 * necessary goal and no other check: the brief about its own object first, then the brief that asks
 * the fewest key questions. It leads the brief. It never joins a brief in which it would keep a
 * necessary goal from being asked part by part, or that would then ask more than MAX_PART_QUESTIONS
 * key questions (section 21). Returns null when a check fits nowhere.
 */
export function shareChecks(groups: Group[], checks: Goal[], state: Pick<EbdState, "map">): Group[] | null {
  const out = groups.map((g) => ({ key: g.key, goals: [...g.goals] }));
  for (const check of checks) {
    const fits = (g: Group) => !g.goals.some(isClaimCheck) && g.goals.some((x) => x.need === "necessary") && hasRoom(g, check, state);
    const target = roomiest(out.filter(fits), check, state);
    if (!target) return null;
    target.goals.unshift(check);
  }
  return out;
}

/**
 * Can the goal join the brief as one more key question? The brief stays within MAX_PART_QUESTIONS, and
 * every goal asked part by part stays so (section 21).
 */
function hasRoom(group: Group, goal: Goal, state: Pick<EbdState, "map">): boolean {
  const joined = { key: group.key, goals: [goal, ...group.goals] };
  return questionCount(joined, state) <= MAX_PART_QUESTIONS && askedByPart(joined, state).size >= askedByPart(group, state).size;
}

/** The brief a goal joins: the one about its own object first, then the one that asks the fewest key questions. */
function roomiest(groups: Group[], goal: Goal, state: Pick<EbdState, "map">): Group | undefined {
  const own = (g: Group) => Number(g.key === keyOf(goal));
  return [...groups].sort((a, b) => own(b) - own(a) || questionCount(a, state) - questionCount(b, state))[0];
}

/**
 * Sections 27 and 30: completing parts that only ride along. Each joins a brief with room for one
 * more key question, after the goals the brief was made for; one that fits nowhere waits. Used in
 * the first round when it has no more researchers than the plan has necessary parts.
 */
export function shareRiders(groups: Group[], riders: Goal[], state: Pick<EbdState, "map">): { groups: Group[]; waiting: Goal[] } {
  const out = groups.map((g) => ({ key: g.key, goals: [...g.goals] }));
  const waiting: Goal[] = [];
  for (const rider of riders) {
    const target = roomiest(out.filter((g) => hasRoom(g, rider, state)), rider, state);
    if (target) target.goals.push(rider);
    else waiting.push(rider);
  }
  return { groups: out, waiting };
}

/** One brief per group (section 7). `position` orders the platform's drop rule like EBD's own ranking. */
export function briefFor(group: Group, position: number, state: EbdState): ResearchBriefInput {
  const a = state.analysis;
  const goals = group.goals;
  const byPart = askedByPart(group, state);
  const objectText = [...a.rom.objects, ...state.objectsFound].find((o) => o.id === group.key)?.text ?? group.key;
  // Only refuted dates: a contradicted claim also refutes its context objects (a place, a product) only loosely.
  const refutedDates = [...refutedObjects(state, assumptionVerdicts(state, false))].flatMap((id) => a.rom.objects.find((o) => o.id === id && o.kind === "number_or_date")?.text ?? []);
  const level = Math.min(...goals.map((g) => g.level));
  const hints = [...new Set(goals.flatMap((g) => g.sourceHints))];
  if (goals.some((g) => g.kind === "verify" || g.kind === "settle")) hints.push(PRIMARY_SOURCES);

  const instructions: string[] = goals.map((g) => {
    const event = eventOf(state, g);
    // Section 28: the parts of a main part of the answer are full key questions, asked as written.
    const parts = event
      ? byPart.has(g.id)
        ? [`For [${g.id}], the objective is: ${g.text} ${PLAN_QUESTIONS_INSTRUCTION}`]
        : [`For [${g.id}], the plan expects an answer to cover these questions: ${event.parts.filter((p) => p.status !== "refuted").map((p) => p.text).join(" ")} ${PLANNED_PARTS_INSTRUCTION}`]
      : [`For [${g.id}], a sufficient answer contains: ${g.doneWhen}`];
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
    keyQuestions: goals.flatMap((g) => {
      // Section 21: each key question is asked under its goal's ID, so its notes section maps to the goal.
      if (byPart.has(g.id)) return askedParts(state, g).map((p) => `[${g.id}] ${p.text}`);
      return [`[${g.id}] ${g.text}${g.missing.length && g.attempts > 0 ? ` Still missing: ${g.missing.join("; ")}` : ""}`];
    }),
    constraints: [...frameConstraints(a, refutedDates), ...readingConstraints(a, goals.flatMap((g) => g.objectIds)), ...defaultConstraints(a), ...notStatedConstraints(state), ...directiveLines(a, "researchers")],
    sourceHints: [...new Set(hints)].slice(0, 5),
    instructions: instructions.join("\n"),
    priority: 100 - 10 * level - position,
    tag: goals.map((g) => g.id).join(","),
  };
}
