/**
 * EBD options (design section 13). Every option has a default, so an experiment
 * spec names only what it changes, e.g. { "conflicts": false } for the H1 ablation.
 *
 * Defaults follow the recommendations in design section 18 (D-C, D-E, D-F, L-7).
 * They are provisional until the team confirms them; each stays switchable here.
 */
import { z } from "zod";

export const OptionsSchema = z
  .object({
    /** How init runs the request analysis (D-F): one call with a code retry, or the tool-using analyst. */
    init: z.enum(["fixed", "agent"]).default("fixed"),
    /** Briefs per round; the platform runs 4 researchers at a time. */
    maxPerRound: z.number().int().min(1).max(20).default(4),
    /** Goals packed into one brief (D-C). */
    questionsPerBrief: z.number().int().min(1).max(6).default(3),
    /** Conflict checker on or off (H1 ablation). */
    conflicts: z.boolean().default(true),
    /** Grow goals from evidence; off gives a static EBD plan (tree-growth ablation). */
    newGoals: z.boolean().default(true),
    maxNewGoalsPerRound: z.number().int().min(0).max(20).default(4),
    maxOpenGoals: z.number().int().min(1).max(60).default(20),
    /** Derivation steps from the request a new goal may be. */
    maxDepth: z.number().int().min(0).max(5).default(2),
    /** Attempts before a goal is exhausted. */
    maxAttempts: z.number().int().min(1).max(5).default(2),
    /** Independent hosts needed for verification goals, numbers and dates. */
    evidenceFloor: z.number().int().min(1).max(5).default(2),
    /** One round of completing goals after "complete". */
    extraRound: z.boolean().default(true),
    /**
     * L-7: a verification goal is served in round 1 even when the analysis made it wait
     * for definition goals, because a refuted premise makes other goals moot.
     */
    premiseFirst: z.boolean().default(true),
    /**
     * D-E, review of 2026-10-21: keep researchers for the necessary request goals that have
     * never been served; briefs made only of goals added during the run use the rest.
     */
    reserveFirstTries: z.boolean().default(true),
  })
  .strict();

export type EbdOptions = z.infer<typeof OptionsSchema>;

export function parseOptions(options: unknown): EbdOptions {
  return OptionsSchema.parse(options ?? {});
}
