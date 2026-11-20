/**
 * EBD options (design section 13). Every option has a default, so an experiment spec names only what
 * it changes, e.g. { "maxPerRound": 3 }.
 *
 * Since the consolidation of 2026-11-19 (design section 32) the strategy is one approach, and the
 * options that switched between planners and follow-up rules are gone: `init`, `extend`,
 * `completeMap`, `partQuestions`, `premiseSort`, `premiseRides`, `stepsFirst`, `focusFollowUp`,
 * `leanGuidance`, `mainPartsFirst`, `uncitedParts`, `strictFollowUp` and `extraRound`. On 2026-11-20
 * the two switches `conflicts` and `newGoals`, which turned the conflict checker and the growth of
 * new goals off, went too (design section 39). What is left are limits and three scheduling rules
 * (`premiseFirst`, `reserveFirstTries`, `spread`). No setting turns the conflict checker or the new
 * goals off: the two limits that would do so at 0 start at 1.
 */
import { z } from "zod";

export const OptionsSchema = z
  .object({
    /** Briefs per round; the platform runs 4 researchers at a time. */
    maxPerRound: z.number().int().min(1).max(20).default(4),
    /** Goals packed into one brief (D-C). */
    questionsPerBrief: z.number().int().min(1).max(6).default(3),
    /** New goals a round, settle goals included. At least 1: 0 would turn new goals off (section 39). */
    maxNewGoalsPerRound: z.number().int().min(1).max(20).default(4),
    maxOpenGoals: z.number().int().min(1).max(60).default(20),
    /** Derivation steps from the request a new goal may be. At least 1: 0 would allow no new goal (section 39). */
    maxDepth: z.number().int().min(1).max(5).default(2),
    /** Attempts before a goal is exhausted. */
    maxAttempts: z.number().int().min(1).max(5).default(2),
    /** Independent hosts needed before a claim of the question counts as checked (section 20). */
    evidenceFloor: z.number().int().min(1).max(5).default(2),
    /**
     * L-7: a verification goal is served in round 1 even when it waits for other goals, because a
     * refuted premise makes other goals moot.
     */
    premiseFirst: z.boolean().default(true),
    /**
     * D-E, review of 2026-10-21: keep researchers for the necessary planned goals that have never
     * been served; briefs made only of goals added during the run use the rest.
     */
    reserveFirstTries: z.boolean().default(true),
    /**
     * Give every researcher of a round a goal of its own where the goals allow it. In the first round
     * every researcher goes to a main part of the answer, the necessary parts first (section 30); in
     * a later round shared briefs are split when researchers would otherwise sit idle (Lab 5 review,
     * change 3).
     */
    spread: z.boolean().default(true),
  })
  .strict();

export type EbdOptions = z.infer<typeof OptionsSchema>;

export function parseOptions(options: unknown): EbdOptions {
  return OptionsSchema.parse(options ?? {});
}
