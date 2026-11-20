/**
 * The plan's map during a run (design sections 19 and 28): each main part of the answer is an event
 * with its key questions as parts. The parts are what the plan expects, never evidence: a finding
 * confirms, corrects or refutes each one (rounds/analyst.ts, rounds/conflicts.ts), and none reaches
 * the writer as a fact. This module keeps a part's goal in step with the map.
 */
import type { EnvironmentMap, Goal, MapEvent, MapPart } from "./state.js";

/** The longest text of a part that the findings put in place of a refuted one. */
const FOUND_PART_MAX = 140;

/** The parts still in the plan: every part the evidence has not refuted. */
export function liveParts(event: MapEvent): MapPart[] {
  return event.parts.filter((p) => p.status !== "refuted");
}

/** The completion criterion of an event goal, rebuilt from the map whenever a part changes. */
export function doneWhenOf(event: MapEvent): string {
  return `Covers, as far as the sources report them: ${liveParts(event).map((p) => p.text).join("; ")}.`;
}

/**
 * Keep an event goal in step with its map event: the parts still planned, those the evidence
 * confirmed, and those still to find. The goal's generic fields then serve the briefs, the stop
 * rules and the run viewer unchanged.
 */
export function syncGoal(goal: Goal, event: MapEvent): void {
  const live = liveParts(event);
  const confirmed = live.filter((p) => p.status === "confirmed");
  goal.doneWhen = doneWhenOf(event);
  goal.partsTotal = live.length;
  goal.partsMet = confirmed.length;
  goal.missing = live.filter((p) => p.status === "assumed").map((p) => p.text);
  goal.metParts = confirmed.map((p) => ({ part: p.text, evidence: p.evidence, round: p.round ?? 0 }));
  goal.evidence = [...new Set([...goal.evidence, ...confirmed.flatMap((p) => p.evidence)])];
}

/**
 * The share of an event's parts that must be confirmed for the event to count as researched.
 * Below it the goal gets its second attempt; from it on, the parts still assumed are left as
 * unfound. In the first live runs (2026-11-11) every event goal that had confirmed 3 or 4 of 5
 * parts was retried for the last one or two, and the retries of the flight run found none of them,
 * while the last researchers went to them instead of new questions.
 */
export const EVENT_COVERED = 0.5;

/** Has the research confirmed enough of the event's parts? */
export function isCovered(event: MapEvent): boolean {
  const live = liveParts(event);
  return live.length > 0 && live.filter((p) => p.status === "confirmed").length >= live.length * EVENT_COVERED;
}

/** The parts no source reported, once the event counts as researched: they are not searched again. */
export function closeEvent(event: MapEvent, round: number): MapPart[] {
  const open = event.parts.filter((p) => p.status === "assumed");
  for (const p of open) Object.assign(p, { status: "unfound", by: "round analyst", round });
  return open;
}

/** The next free part number of the map. */
export function nextPartId(map: EnvironmentMap): string {
  const used = map.events.flatMap((e) => e.parts.map((p) => Number(p.id.slice(1)) || 0));
  return `M${Math.max(0, ...used) + 1}`;
}

/**
 * The evidence overrides an assumed part: it leaves the plan, and what the findings say instead,
 * if they say, enters the map as a found part. Returns false when the part is not an assumption
 * any more (already confirmed or refuted), so a later claim cannot undo a judgment.
 */
export function overwritePart(map: EnvironmentMap, partId: string, evidence: string[], correction: string, by: string, round: number): boolean {
  const event = map.events.find((e) => e.parts.some((p) => p.id === partId));
  const part = event?.parts.find((p) => p.id === partId);
  if (!event || !part || part.status !== "assumed") return false;
  part.status = "refuted";
  part.evidence = evidence;
  part.correction = correction.trim() || null;
  part.by = by;
  part.round = round;
  if (part.correction) {
    event.parts.push({ id: nextPartId(map), text: part.correction.slice(0, FOUND_PART_MAX), kind: part.kind, origin: "found", status: "confirmed", evidence, correction: null, replaces: part.id, by, round });
  }
  return true;
}

/** One line per event for the decision rationale. */
export function mapSummary(map: EnvironmentMap): string {
  return `Environment map of "${map.subject}": ${map.events.map((e) => `${e.id} ${e.name} (${e.goalId}, ${e.parts.length} parts)`).join("; ")}.`;
}
