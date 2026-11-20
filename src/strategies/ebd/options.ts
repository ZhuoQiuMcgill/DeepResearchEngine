/**
 * EBD options (design section 13). Every option has a default, so an experiment
 * spec names only what it changes, e.g. { "conflicts": false } for the H1 ablation.
 *
 * Defaults follow design section 18 (D-C, D-E, D-F, L-7), confirmed on 2026-11-05.
 * Each stays switchable here for ablations.
 */
import { z } from "zod";

export const OptionsSchema = z
  .object({
    /**
     * How init makes the first plan. "fixed" and "agent" run the request analysis (D-F: one call with
     * a code retry, or the tool-using analyst), followed by the premise sort and the problem
     * extension. "environment" (design section 28) makes the whole plan in one call: the main parts of
     * the answer with their key questions, the claims of the question sorted into checked and taken as
     * given, and what the client did not state. In that mode `extend`, `completeMap` and `premiseSort`
     * have nothing to do, and the key questions of a main part are always asked one by one. In the
     * first round every researcher goes to a main part of the answer, the necessary parts first, and
     * none is kept for a second try (section 30). Its prompt text was approved on 2026-11-19; off by
     * default until the final test (section 29.6).
     */
    init: z.enum(["fixed", "agent", "environment"]).default("fixed"),
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
    /** Lab 5 review, change 3: split shared briefs when researchers would otherwise sit idle this round. */
    spread: z.boolean().default(true),
    /**
     * Problem extension (design section 19): after the request analysis, the analyst answers "what is
     * the subject?" through its life cycle as a working assumption, and each event becomes a search
     * goal. Findings confirm, correct or refute the assumed parts. Off gives the plan built from the
     * request's words only. On by default since the prompt text was accepted (2026-11-11).
     */
    extend: z.boolean().default(true),
    /**
     * Follow-up on what the answer depends on (design section 20). The conflict checker marks the
     * critical conflicts; only those get a settle goal, which gets one attempt. A goal is searched
     * again only when most of it is unanswered or a client claim is undecided, and the round analyst
     * marks a new goal necessary only for a main part of the question. Off gives the earlier follow-up:
     * a settle goal for every disagreement and a second attempt for every partial goal.
     */
    focusFollowUp: z.boolean().default(false),
    /**
     * Writer input limited to what the notes do not show (design section 20): contradicted or
     * undecided premises and at most three critical conflicts. No outline for a single-part question,
     * no section for disagreements, no planned-contents line. Off gives the full guidance of section 12.
     */
    leanGuidance: z.boolean().default(false),
    /**
     * One key question per part of a life-cycle step (design section 21). The brief of an event goal
     * asks each planned part as its own key question, so the researcher answers and sources every part
     * and the notes get one section per part. Off gives one compound key question per goal, with the
     * parts listed in the instructions. Off by default until the brief text is approved.
     */
    partQuestions: z.boolean().default(false),
    /**
     * A complete environment map (design section 22). The extension analyst writes the life-cycle
     * events so that they carry the whole answer, starting with the event that answers the question
     * most directly, and the events replace every planned question they carry in full, unless it checks
     * a client assumption. Off gives the extension prompt accepted on 2026-11-11, in which an event
     * does not repeat a planned question. Off by default until the prompt text is approved.
     */
    completeMap: z.boolean().default(false),
    /**
     * The order of a follow-up round with `focusFollowUp` (design section 25, decided on 2026-11-18).
     * The researchers go first to the necessary goals that ask for a part of the answer; a goal that
     * settles a disagreement is served with the researchers left, before the completing goals. One
     * exception: a settle goal that a part of the answer waits behind keeps its place. Off gives the
     * order of section 20, in which the goal that settles a critical conflict comes first. Without
     * `focusFollowUp` the option changes nothing.
     */
    mainPartsFirst: z.boolean().default(true),
    /**
     * A main part of the answer that no finding mentions (design section 26, decided on 2026-11-19).
     * With `focusFollowUp`, the round analyst may propose a necessary goal for such a part and cite
     * nothing, and code accepts it as one of the two necessary new goals of the round. Off gives the
     * rule of section 10.2 for every proposal: one that cites no evidence is rejected. Without
     * `focusFollowUp` the option changes nothing.
     */
    uncitedParts: z.boolean().default(true),
    /**
     * A claim check shares a researcher (design sections 26 and 27; the user's decision of
     * 2026-11-19). In the first round a goal that only checks a claim the question takes for granted
     * is asked in the brief of a necessary goal that asks for content, as one more key question, and
     * takes no researcher of its own. The check is still made in round 1 (`premiseFirst`). Off gives
     * each necessary goal, the check included, a researcher of its own.
     */
    premiseRides: z.boolean().default(true),
    /**
     * Where the first round's researchers go when the plan has life-cycle steps (design section 27,
     * 2026-11-19). A planned question that the steps stand in for (one they replaced, or one that
     * stopped being a check) only rides along in a brief with room and takes no researcher of its own;
     * and a researcher that would sit idle goes to a step that shares a brief with another step before
     * it goes to any other goal. Off gives the allocation of sections 7 and 21.
     */
    stepsFirst: z.boolean().default(true),
    /**
     * The premise sort (design section 27; the user's decision of 2026-11-19). One model call after
     * the request analysis says for each claim the question takes for granted whether it is checked
     * as a fact of its own (a date, a number, who did what, a particular event or its cause) or taken
     * as given (it only restates what the question asks about). A claim taken as given gets no check
     * goal and no line for the writer; the conflict checker still reports findings that contradict
     * it. Off checks every claim, as before.
     */
    premiseSort: z.boolean().default(true),
    /**
     * After the first round a researcher goes only to a main part of the answer or to a claim of the
     * question (design section 29; the user's decision of 2026-11-19). Two rules:
     * - a disagreement between sources is reported, not researched again: a conflict gets a goal of
     *   its own only when it decides a claim of the question; every other disagreement is recorded
     *   as disputed at once, and the writer is told about it when it is critical;
     * - with `focusFollowUp`, a completing goal is never served after the first round, and there is
     *   no extra round of completing goals once the run is complete. A main part of the plan that no
     *   researcher has been asked about is not such a goal: it is still served (section 30).
     * In the 12 runs on new questions of 2026-11-18, 9 of the 20 follow-up researchers went to
     * settle a disagreement, 6 of them to one between sources only, and 6 of the 9 settled nothing;
     * in the live run of 2026-11-19 the sixth researcher went to a detail. Off gives the follow-up
     * of sections 9 and 20.
     */
    strictFollowUp: z.boolean().default(false),
  })
  .strict();

export type EbdOptions = z.infer<typeof OptionsSchema>;

export function parseOptions(options: unknown): EbdOptions {
  return OptionsSchema.parse(options ?? {});
}
