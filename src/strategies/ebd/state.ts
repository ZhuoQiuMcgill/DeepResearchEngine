/**
 * EBD state (design sections 6, 8, 9, 11 and 14). Plain JSON: declared with
 * `type`, and never holding `undefined`, so it round-trips through the skeleton
 * unchanged. The platform records it after every step, which makes the goal
 * tree, the conflicts and the stop kind measurable from events.jsonl.
 */
import type { Analysis, Issue } from "./request/index.js";

/** verify: checks a client assumption or a relation; settle: created for a conflict. */
export type GoalKind = "verify" | "settle" | "define" | "relate";

/** Settled statuses are answered, exhausted, disputed and moot. */
export type GoalStatus = "open" | "conflicting" | "answered" | "exhausted" | "disputed" | "moot";

export type Verdict = "supported" | "contradicted" | "unsettled";

/** Why a goal exists: the request, or the evidence line or conflict that prompted it. */
export type Origin =
  | { type: "request" }
  | { type: "finding" | "gap"; evidence: string[] }
  | { type: "conflict"; conflict: string }
  /** A life-cycle event of the environment map: the analyst's working answer, which the evidence overrides. */
  | { type: "assumed"; event: string }
  /** A main part of the answer that the round analyst found in no finding of the round (section 26). */
  | { type: "uncovered" };

export type Goal = {
  /** Q-number: the analysis question's ID, or the next free one for a new goal. */
  id: string;
  text: string;
  objectIds: string[];
  template: string;
  guideline: string;
  need: "necessary" | "completing";
  dependsOn: string[];
  verifies: string[];
  doneWhen: string;
  sourceHints: string[];
  kind: GoalKind;
  /** Priority level 1–4 (section 6.3). */
  level: number;
  origin: Origin;
  /** Derivation steps from the request: 0 for request goals. */
  depth: number;
  /** Synthesis questions or necessary goals a new goal leads to (section 10.2). */
  leadsTo: string[];
  status: GoalStatus;
  attempts: number;
  createdRound: number;
  servedRounds: number[];
  settledRound: number | null;
  /** Parts of done_when still missing, from the last judgment. */
  missing: string[];
  partsMet: number;
  partsTotal: number;
  /**
   * Parts met so far, kept with the findings that met them (Lab 5 review, change 1). Later
   * rounds judge only the missing parts, so a part met in round 1 is not judged unmet in round 2.
   */
  metParts: { part: string; evidence: string[]; round: number }[];
  /** Attempts whose researcher failed (Lab 5 review, change 8). */
  failedAttempts: number;
  /** Evidence line IDs that support the judgment. */
  evidence: string[];
  /**
   * For goals that check claims: what the evidence says about each claim, by assumption ID.
   * One goal can check several claims that differ (Lab 4, 2026-10-26: "NASA launched the
   * telescope" holds while "in 2018" does not), so each claim has its own verdict.
   */
  verdicts: Record<string, Verdict>;
  /** For settle goals: the conflict they settle. */
  settles: string | null;
  /** For a conflicting goal: the settle goal it waits for. */
  waitingOn: string | null;
  /** Extra researcher instruction for the next attempt, e.g. a new angle. */
  retryNote: string | null;
};

/** One Cited Findings or Gaps bullet of a researcher's notes (section 8). */
export type EvidenceLine = {
  /** `r2-b1-f3` for a finding, `r2-b1-g1` for a gap. */
  id: string;
  briefId: string;
  round: number;
  kind: "finding" | "gap";
  goalIds: string[];
  /** Index of the section in the result's sections. */
  section: number;
  text: string;
  /** Raw line indexes in the result's notes, the bullet and its continuation lines. */
  lines: number[];
  hosts: string[];
};

export type NotesSectionRef = {
  title: string;
  goalIds: string[];
  /** How the section was mapped: by its [Qn] prefix, by key-question order, or to all goals of the brief. */
  mappedBy: "id" | "order" | "brief";
  /** Raw line range [start, end) in the notes, heading included. */
  start: number;
  end: number;
  takeaway: string;
};

export type ResultRecord = {
  briefId: string;
  round: number;
  goalIds: string[];
  status: "ok" | "failed";
  failure: string | null;
  notes: string;
  sections: NotesSectionRef[];
};

export const CONFLICT_TYPES = ["source_vs_source", "evidence_vs_assumption", "evidence_vs_frame", "off_target", "time_dependent"] as const;
/** evidence_vs_plan exists only with an environment map: a finding against a planned part, which it overwrites. */
export const PLAN_CONFLICT = "evidence_vs_plan" as const;
export type ConflictType = (typeof CONFLICT_TYPES)[number] | typeof PLAN_CONFLICT;

export type Conflict = {
  /** C1, C2, … */
  id: string;
  type: ConflictType;
  /** The goal or object the conflict is about. */
  about: string;
  statement: string;
  sideA: string[];
  /** Evidence IDs, an assumption ID, a frame field or an object ID, by type. */
  sideB: string[];
  settleBy: string;
  /** For time_dependent conflicts: the condition under which each side holds. */
  condition: string;
  /** The assumption the disagreement decides, which its settle goal checks; null for a disagreement about a detail. */
  claim: string | null;
  /**
   * Does the answer to the client's question depend on which side is right (design section 20)?
   * Null when the conflict checker was not asked; records made before the field existed lack it.
   */
  critical?: boolean | null;
  status: "open" | "settled" | "disputed";
  createdRound: number;
  settledRound: number | null;
  /** The goal whose notes settle it: its settle goal, or the goal that already checked its claim in the same round (section 9). */
  settleGoal: string | null;
  /**
   * A goal served this round that checks the conflict's claim on the same findings. The conflict
   * stays open until the round analyst's verdict on that claim: supported or contradicted settles
   * it; unsettled makes it an ordinary disagreement (Lab 5 review, change 2).
   */
  checkedBy: string | null;
};

/** An object the evidence introduced (section 10.2): it enters the ROM only with a verbatim quote from a finding line. */
export type FoundObject = {
  /** Continues the analysis's O numbering. */
  id: string;
  text: string;
  /** The existing object it attaches to. */
  parent: string;
  quote: string;
  /** The finding line the quote comes from. */
  evidence: string;
  round: number;
};

export const ENV_KINDS = ["natural", "built_physical", "built_digital", "economic", "social"] as const;
export type EnvKind = (typeof ENV_KINDS)[number];

/**
 * One part of a life-cycle event (design section 19). "assumed" parts are the analyst's working
 * answer, made before any search; a finding confirms or refutes each, and a refuted part leaves the
 * plan. A part is "unfound" when its event was researched and the sources found did not report it:
 * it is not searched again. "found" parts are what the findings say instead of a refuted part.
 */
export type MapPart = {
  /** M1, M2, … across the whole map. */
  id: string;
  text: string;
  kind: EnvKind;
  origin: "assumed" | "found";
  status: "assumed" | "confirmed" | "refuted" | "unfound";
  /** The findings that confirmed or refuted it. */
  evidence: string[];
  /** For a refuted part: what the findings say instead, if they say. */
  correction: string | null;
  /** For a found part: the assumed part it replaces. */
  replaces: string | null;
  /** How it was overwritten: by the round analyst's judgment or by a conflict. */
  by: string | null;
  round: number | null;
};

export type MapEvent = {
  /** E1, E2, … */
  id: string;
  name: string;
  /** The search goal that researches the event. */
  goalId: string;
  parts: MapPart[];
};

/** The environment map: the subject's life-cycle events and what each involves (design section 19). */
export type EnvironmentMap = {
  subject: string;
  objectIds: string[];
  events: MapEvent[];
  /** Planned questions the event goals replaced, with the goals that replaced them. */
  replaced: Record<string, string[]>;
  /**
   * Section 28 (`init: "environment"`): the events are the main parts of the answer and their parts
   * are key questions written in full by the environment analyst. A brief asks them as written.
   * Absent for a map of life-cycle steps, whose parts are short noun phrases.
   */
  questions?: boolean;
};

/** researcher_failures: every necessary goal is settled, but some ended only because their researchers failed. */
export type StopKind = "complete" | "saturated" | "budget" | "out_of_scope" | "researcher_failures";

/** One model call of a strategy step, kept for the run viewer and for audits. */
export type CallRecord = {
  role: "request_analyst" | "premise_sorter" | "extension_analyst" | "environment_analyst" | "conflict_checker" | "round_analyst";
  attempt: number;
  accepted: boolean;
  errors: Issue[];
  warnings: Issue[];
  /** The user message sent (the system prompt is fixed per role and not repeated). */
  input: string;
  /** The tool arguments, or the reply text when the model did not call the tool. */
  reply: string;
  inputTokens: number;
  outputTokens: number;
  ms: number;
};

/** What one step did, replaced at every step so the record of each decision shows its own work. */
export type StepLog = {
  phase: "init" | "observe";
  /** The round whose results were read (0 for init). */
  round: number;
  calls: CallRecord[];
  /** Code actions in order: goals created, settled, rejected proposals, stop checks. */
  events: string[];
};

export type Tree = {
  goals: number;
  byOrigin: Record<string, number>;
  byDepth: Record<string, number>;
  byStatus: Record<string, number>;
  createdPerRound: Record<string, number>;
  settledPerRound: Record<string, number>;
  maxDepth: number;
};

export type EbdState = {
  question: string;
  today: string;
  init: { mode: string; accepted: boolean; fallback: boolean; attempts: number; stopReason: string };
  analysis: Analysis;
  goals: Goal[];
  objectsFound: FoundObject[];
  /** Null when the extension step is off, or gave no usable reply. */
  map: EnvironmentMap | null;
  /**
   * Section 27: the claims of the question that are taken as given instead of checked, each with
   * the sorter's reason. Absent or null when the premise sort is off or gave no usable reply: every
   * claim is then checked. States recorded before 2026-11-19 do not have the field.
   */
  premises?: { given: { id: string; reason: string }[] } | null;
  /**
   * Section 28 (`init: "environment"`): what the answer depends on and the client did not state, each
   * with the main cases to cover, as the environment analyst wrote them. The briefs carry them as
   * constraints. Absent in the other init modes.
   */
  plan?: { notStated: string[] } | null;
  conflicts: Conflict[];
  evidence: EvidenceLine[];
  results: ResultRecord[];
  /** Rounds whose results have been read. */
  roundsObserved: number;
  extraRoundServed: boolean;
  stop: { kind: StopKind; round: number; reason: string } | null;
  /** Tree metrics for H-9 (section 14), recomputed after every step. */
  tree: Tree;
  step: StepLog;
  /** Problems that did not stop the run: fallbacks, rejected proposals, unmapped notes. */
  problems: string[];
};

export const SETTLED: readonly GoalStatus[] = ["answered", "exhausted", "disputed", "moot"];

export function isSettled(goal: Goal): boolean {
  return SETTLED.includes(goal.status);
}

/**
 * A critical conflict (design section 20): the answer depends on which side is right. A conflict
 * with a client claim at stake always is; otherwise the conflict checker's mark decides.
 */
export function isCritical(conflict: Conflict): boolean {
  return conflict.type === "evidence_vs_assumption" || conflict.claim !== null || conflict.critical === true;
}

/** A goal of the opening plan: from the request analysis or from the environment map. */
export function isPlanned(goal: Goal): boolean {
  return goal.origin.type === "request" || goal.origin.type === "assumed";
}

/** The map event a goal researches, or null. */
export function eventOf(state: Pick<EbdState, "map">, goal: Goal): MapEvent | null {
  const origin = goal.origin;
  return origin.type === "assumed" ? (state.map?.events.find((e) => e.id === origin.event) ?? null) : null;
}

/** A main part of the plan that no researcher has been asked about yet (section 30). */
export function isUnaskedPart(state: Pick<EbdState, "map">, goal: Goal): boolean {
  return eventOf(state, goal) !== null && goal.status === "open" && goal.attempts === 0;
}
