/**
 * The goal table (design sections 6, 10 and 11): building it from the request
 * analysis, readiness, the code-computed order, settling goals, making goals
 * moot, the stop rules and the tree metrics. Pure functions; no model calls.
 */
import type { Analysis, AnalysisQuestion } from "./request/index.js";
import type { EbdOptions } from "./options.js";
import { isSettled, type Conflict, type EbdState, type Goal, type GoalKind, type Origin, type Tree, type Verdict } from "./state.js";

const DEFINE = new Set(["T1", "T2", "T3", "T6"]);

/** Section 6.3: kind from the template, and settle for a goal created to settle a conflict. */
export function kindOf(template: string, verifies: string[], settles: string | null): GoalKind {
  if (settles) return "settle";
  if (template === "T7" || verifies.length) return "verify";
  return DEFINE.has(template) ? "define" : "relate";
}

const KIND_ORDER: Record<GoalKind, number> = { settle: 0, verify: 0, define: 1, relate: 2 };

/** Level 1–4 (section 6.3). Completing goals are level 4 whatever their kind. */
export function levelOf(kind: GoalKind, need: Goal["need"]): number {
  if (kind === "settle") return 1;
  if (need === "completing") return 4;
  return 1 + KIND_ORDER[kind];
}

export function newGoal(fields: {
  id: string;
  text: string;
  objectIds: string[];
  template: string;
  guideline: string;
  need: Goal["need"];
  dependsOn?: string[];
  verifies?: string[];
  doneWhen: string;
  sourceHints?: string[];
  origin: Origin;
  depth: number;
  leadsTo?: string[];
  createdRound: number;
  settles?: string | null;
}): Goal {
  const verifies = fields.verifies ?? [];
  const kind = kindOf(fields.template, verifies, fields.settles ?? null);
  return {
    id: fields.id,
    text: fields.text,
    objectIds: fields.objectIds,
    template: fields.template,
    guideline: fields.guideline,
    need: fields.need,
    dependsOn: fields.dependsOn ?? [],
    verifies,
    doneWhen: fields.doneWhen,
    sourceHints: fields.sourceHints ?? [],
    kind,
    level: levelOf(kind, fields.need),
    origin: fields.origin,
    depth: fields.depth,
    leadsTo: fields.leadsTo ?? [],
    status: "open",
    attempts: 0,
    createdRound: fields.createdRound,
    servedRounds: [],
    settledRound: null,
    missing: [],
    partsMet: 0,
    partsTotal: 0,
    evidence: [],
    verdict: null,
    settles: fields.settles ?? null,
    waitingOn: null,
    retryNote: null,
  };
}

/** One goal per search question of the analysis; synthesis questions stay in the analysis (section 6). */
export function goalsFromAnalysis(a: Analysis): Goal[] {
  return a.questions
    .filter((q) => q.route === "search")
    .map((q) =>
      newGoal({
        id: q.id,
        text: q.text,
        objectIds: q.object_ids,
        template: q.template,
        guideline: q.guideline,
        need: q.need,
        dependsOn: q.depends_on,
        verifies: q.verifies,
        doneWhen: q.done_when,
        sourceHints: q.source_hints,
        origin: { type: "request" },
        depth: 0,
        createdRound: 1,
      }),
    );
}

export function synthesisQuestions(a: Analysis): AnalysisQuestion[] {
  return a.questions.filter((q) => q.route === "synthesis");
}

/** The next free Q number: new goals continue the analysis numbering. */
export function nextGoalId(state: Pick<EbdState, "analysis" | "goals">): string {
  const used = [...state.analysis.questions.map((q) => q.id), ...state.goals.map((g) => g.id)].map((id) => Number(id.slice(1)) || 0);
  return `Q${Math.max(0, ...used) + 1}`;
}

// ---------------------------------------------------------------- readiness and order

/** Section 6.2: every goal it depends on is settled. With premiseFirst (L-7) a verification goal does not wait. */
export function isReady(goal: Goal, byId: Map<string, Goal>, options: Pick<EbdOptions, "maxAttempts" | "premiseFirst">): boolean {
  if (goal.status !== "open" || goal.attempts >= options.maxAttempts) return false;
  if (options.premiseFirst && goal.kind === "verify" && goal.origin.type === "request") return true;
  return goal.dependsOn.every((d) => {
    const dep = byId.get(d);
    return !dep || isSettled(dep);
  });
}

/** Unsettled necessary goals and synthesis questions that depend on the goal, directly or through other goals. */
export function reach(goal: Goal, state: Pick<EbdState, "goals" | "analysis">): number {
  const dependents = new Map<string, string[]>();
  const add = (from: string, to: string) => dependents.set(from, [...(dependents.get(from) ?? []), to]);
  for (const g of state.goals) {
    for (const d of g.dependsOn) add(d, g.id);
    for (const t of g.leadsTo) add(g.id, t);
  }
  for (const q of synthesisQuestions(state.analysis)) for (const d of q.depends_on) add(d, q.id);
  const byId = new Map(state.goals.map((g) => [g.id, g]));
  const seen = new Set<string>();
  const stack = [...(dependents.get(goal.id) ?? [])];
  while (stack.length) {
    const id = stack.pop()!;
    if (seen.has(id)) continue;
    seen.add(id);
    stack.push(...(dependents.get(id) ?? []));
  }
  return [...seen].filter((id) => {
    const g = byId.get(id);
    return g ? g.need === "necessary" && !isSettled(g) : true;
  }).length;
}

/** Constraint relations into the goal's objects whose constraining object is still undefined (Wang & Zeng 2009, Table 2). */
export function undefinedConstraints(goal: Goal, state: Pick<EbdState, "goals" | "analysis">): number {
  const objects = new Map(state.analysis.rom.objects.map((o) => [o.id, o]));
  const defined = new Set(state.goals.filter((g) => g.status === "answered").flatMap((g) => g.objectIds));
  return state.analysis.rom.relations.filter(
    (r) => r.type === "constraint" && goal.objectIds.includes(r.to) && objects.get(r.from)?.status === "needs_question" && !defined.has(r.from),
  ).length;
}

export type Ranked = { goal: Goal; reach: number; undefinedConstraints: number };

/** Section 6.3: level, then reach, undefined constraints, depth, attempts, age, table order. */
export function rankReady(state: EbdState, options: EbdOptions): Ranked[] {
  const byId = new Map(state.goals.map((g) => [g.id, g]));
  const order = new Map(state.goals.map((g, i) => [g.id, i]));
  return state.goals
    .filter((g) => isReady(g, byId, options))
    .map((goal) => ({ goal, reach: reach(goal, state), undefinedConstraints: undefinedConstraints(goal, state) }))
    .sort(
      (a, b) =>
        a.goal.level - b.goal.level ||
        KIND_ORDER[a.goal.kind] - KIND_ORDER[b.goal.kind] ||
        b.reach - a.reach ||
        b.undefinedConstraints - a.undefinedConstraints ||
        a.goal.depth - b.goal.depth ||
        a.goal.attempts - b.goal.attempts ||
        a.goal.createdRound - b.goal.createdRound ||
        order.get(a.goal.id)! - order.get(b.goal.id)!,
    );
}

/** The ready necessary goal that has waited longest since it was created or last served (the reserve slot). */
export function longestWaiting(ranked: Ranked[]): Goal | null {
  const waitingSince = (g: Goal) => Math.max(g.createdRound, ...g.servedRounds);
  const necessary = ranked.map((r) => r.goal).filter((g) => g.need === "necessary");
  if (!necessary.length) return null;
  return necessary.reduce((best, g) => (waitingSince(g) < waitingSince(best) ? g : best));
}

// ---------------------------------------------------------------- settling

/** Does the goal judge a client claim? Verification goals, and settle goals that inherit the claim of the goal they settle. */
export function judgesClaim(goal: Goal): boolean {
  return goal.kind === "verify" || goal.verifies.length > 0;
}

export function settle(goal: Goal, status: Goal["status"], round: number): void {
  goal.status = status;
  goal.settledRound = isSettledStatus(status) ? round : null;
}

function isSettledStatus(status: Goal["status"]): boolean {
  return status === "answered" || status === "exhausted" || status === "disputed" || status === "moot";
}

/** A failed or unproductive attempt: re-queue, or exhaust after maxAttempts (section 10.1). */
export function requeueOrExhaust(goal: Goal, round: number, maxAttempts: number, note: string | null): "requeued" | "exhausted" {
  if (goal.attempts >= maxAttempts) {
    settle(goal, "exhausted", round);
    if (judgesClaim(goal) && goal.verdict === null) goal.verdict = "unsettled";
    return "exhausted";
  }
  goal.status = "open";
  goal.retryNote = note;
  return "requeued";
}

/** Verdict on each assumption: contradicted wins over unsettled, which wins over supported. */
export function assumptionVerdicts(state: Pick<EbdState, "analysis" | "goals">): Record<string, Verdict | null> {
  const out: Record<string, Verdict | null> = {};
  for (const x of state.analysis.assumptions) {
    const verdicts = state.goals.filter((g) => g.verifies.includes(x.id) && g.verdict && isSettled(g)).map((g) => g.verdict!);
    out[x.id] = verdicts.includes("contradicted") ? "contradicted" : verdicts.includes("unsettled") ? "unsettled" : verdicts.includes("supported") ? "supported" : null;
  }
  return out;
}

/**
 * Section 10.2: when an assumption is contradicted, the goals that rely on it
 * (that depend, directly or through other goals, on a goal verifying it) become moot.
 */
export function mootDependents(state: EbdState, round: number): string[] {
  const contradicted = new Set(Object.entries(assumptionVerdicts(state)).filter(([, v]) => v === "contradicted").map(([id]) => id));
  if (!contradicted.size) return [];
  const roots = new Set(state.goals.filter((g) => g.verifies.some((v) => contradicted.has(v))).map((g) => g.id));
  const relies = new Set<string>();
  for (let changed = true; changed; ) {
    changed = false;
    for (const g of state.goals) {
      if (roots.has(g.id) || relies.has(g.id)) continue;
      if (g.dependsOn.some((d) => roots.has(d) || relies.has(d))) {
        relies.add(g.id);
        changed = true;
      }
    }
  }
  const mooted: string[] = [];
  for (const g of state.goals) {
    if (relies.has(g.id) && !isSettled(g)) {
      settle(g, "moot", round);
      mooted.push(g.id);
    }
  }
  return mooted;
}

// ---------------------------------------------------------------- stop rules

/** Is the conflict about a necessary goal, or about an object of one? */
export function onNecessary(conflict: Conflict, goals: Goal[]): boolean {
  return goals.some((g) => g.need === "necessary" && (g.id === conflict.about || g.objectIds.includes(conflict.about)));
}

/** Section 11, "complete": every necessary goal settled, every assumption judged, no open conflict on a necessary goal. */
export function isComplete(state: EbdState): { complete: boolean; reason: string } {
  const open = state.goals.filter((g) => g.need === "necessary" && !isSettled(g));
  // An assumption still needs a verdict while a goal that verifies it is unsettled; one whose checks all became moot does not block.
  const verdicts = assumptionVerdicts(state);
  const unjudged = state.analysis.assumptions
    .filter((x) => verdicts[x.id] === null && state.goals.some((g) => g.verifies.includes(x.id) && !isSettled(g)))
    .map((x) => x.id);
  const conflicts = state.conflicts.filter((c) => c.status === "open" && onNecessary(c, state.goals));
  const parts = [
    open.length ? `necessary goals open: ${open.map((g) => g.id).join(", ")}` : "",
    unjudged.length ? `assumptions without a verdict: ${unjudged.join(", ")}` : "",
    conflicts.length ? `open conflicts on necessary goals: ${conflicts.map((c) => c.id).join(", ")}` : "",
  ].filter(Boolean);
  return { complete: parts.length === 0, reason: parts.length ? parts.join("; ") : "every necessary goal is settled, every assumption has a verdict and no conflict on a necessary goal is open" };
}

/** Progress a round made on necessary goals: settled or with more parts met. */
export type RoundProgress = { settled: string[]; advanced: string[]; newConflicts: number; newNecessary: number; allFailed: boolean };

/** Section 11, "saturated": no necessary goal settled or advanced, no new conflict and no new necessary goal. Rounds where every researcher failed do not count. */
export function isSaturated(p: RoundProgress): boolean {
  return !p.allFailed && p.settled.length === 0 && p.advanced.length === 0 && p.newConflicts === 0 && p.newNecessary === 0;
}

// ---------------------------------------------------------------- tree metrics (H-9)

export function treeMetrics(goals: Goal[]): Tree {
  const count = (keys: (string | number | null)[]) =>
    keys.reduce<Record<string, number>>((acc, k) => {
      if (k === null) return acc;
      acc[String(k)] = (acc[String(k)] ?? 0) + 1;
      return acc;
    }, {});
  return {
    goals: goals.length,
    byOrigin: count(goals.map((g) => g.origin.type)),
    byDepth: count(goals.map((g) => g.depth)),
    byStatus: count(goals.map((g) => g.status)),
    createdPerRound: count(goals.map((g) => g.createdRound)),
    settledPerRound: count(goals.map((g) => g.settledRound)),
    maxDepth: Math.max(0, ...goals.map((g) => g.depth)),
  };
}
