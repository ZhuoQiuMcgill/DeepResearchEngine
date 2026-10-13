/**
 * Baseline strategy module: the reference implementation of a strategy plug-in.
 * It follows the coordinator of Claude Code's deep-research skill:
 * For definition questions, establish identity from sources first, then
 * decompose using those notes. Other questions use parallel decomposition
 * with one optional gap round. Both paths stop after at most two rounds.
 *
 * Like every strategy module it imports platform types from core/index.js only
 * and default-exports a StrategyModule.
 */
import { z } from "zod";
import {
  CONTRACT_VERSION,
  type JsonValue,
  type ResearchResult,
  type ResearchStrategy,
  type StrategyContext,
  type StrategyModule,
  type StrategyStep,
  type SynthesisInput,
} from "../../core/index.js";
import { gapPrompt, planPrompt } from "./prompts.js";
import { groundedBriefs, identityBrief, needsIdentityRound } from "./scope.js";

const BriefSchema = z.object({
  objective: z.string(),
  keyQuestions: z.array(z.string()),
  constraints: z.array(z.string()),
  sourceHints: z.array(z.string()),
});

const PlanSchema = z.object({
  rationale: z.string().describe("How you interpreted the question and why this decomposition"),
  interpretation: z
    .string()
    .describe("Only if the question is ambiguous: one plain sentence stating the meaning you chose (no instructions). Empty string when the question is clear"),
  briefs: z.array(BriefSchema).describe("Researcher assignments"),
});

const GapSchema = z.object({
  rationale: z.string().describe("Which critical gaps remain, or why none do"),
  briefs: z.array(BriefSchema).describe("New assignments targeting critical gaps; empty when no further round is needed"),
});

/** Options from the experiment config; all optional. */
const OptionsSchema = z
  .object({
    /** Maximum researchers per round; the skill's decomposition table goes up to 6. */
    maxPerRound: z.number().int().min(1).max(20).default(6),
  })
  .strict();
type BaselineOptions = z.infer<typeof OptionsSchema>;

type BaselineNote = {
  briefId: string;
  objective: string;
  notes: string;
};

/** Plain JSON so it round-trips through the skeleton unchanged. */
type BaselineState = {
  question: string;
  interpretation: string;
  rounds: number;
  identityFirst: boolean;
  notes: BaselineNote[];
  failures: { briefId: string; objective: string; failure: string }[];
};

export class BaselineStrategy implements ResearchStrategy<BaselineState> {
  readonly name = "baseline";

  constructor(private readonly options: BaselineOptions = OptionsSchema.parse({})) {}

  async init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<BaselineState>> {
    const maxBriefs = Math.min(this.options.maxPerRound, ctx.budget.researchersRemaining);
    const identityFirst = needsIdentityRound(input.question);
    if (identityFirst) {
      return {
        state: { question: input.question, interpretation: "", rounds: 0, identityFirst, notes: [], failures: [] },
        decision: { briefs: maxBriefs ? [identityBrief(input.question)] : [], stop: maxBriefs === 0,
          rationale: "Resolve the exact named concept from sources before decomposing into field-specific parallel assignments." },
      };
    }
    const planner = planPrompt.pipe(ctx.model.withStructuredOutput(PlanSchema, { method: "jsonSchema", name: "research_plan" }));
    const plan = await planner.invoke({ today: ctx.today, question: input.question, maxBriefs: String(maxBriefs), context: "No prior source notes. Do not assume a field or depend on another parallel assignment." });
    return {
      state: { question: input.question, interpretation: plan.interpretation.trim(), rounds: 0, identityFirst, notes: [], failures: [] },
      decision: { briefs: groundedBriefs(plan.briefs, input.question), stop: false, rationale: plan.rationale },
    };
  }

  async observe(state: BaselineState, results: ResearchResult[], ctx: StrategyContext): Promise<StrategyStep<BaselineState>> {
    const next: BaselineState = {
      ...state,
      rounds: state.rounds + 1,
      notes: [
        ...state.notes,
        ...results.filter((r) => r.status === "ok").map((r) => ({ briefId: r.brief.id, objective: r.brief.objective, notes: r.notes })),
      ],
      failures: [
        ...state.failures,
        ...results
          .filter((r) => r.status === "failed")
          .map((r) => ({ briefId: r.brief.id, objective: r.brief.objective, failure: `${r.failure?.kind}: ${r.failure?.message ?? ""}`.slice(0, 300) })),
      ],
    };
    // Both paths retain the two-round limit; identity discovery consumes round one.
    if (next.rounds >= 2) {
      return { state: next, decision: { briefs: [], stop: true, rationale: "The single follow-up round is complete." } };
    }
    if (ctx.budget.researchersRemaining === 0) {
      return { state: next, decision: { briefs: [], stop: true, rationale: "No researcher budget left for a follow-up round." } };
    }
    const summaries = results
      .map((r) =>
        r.status === "ok"
          ? `### Researcher ${r.brief.id}: ${r.brief.objective}\n${r.diagnostics.length ? `Problems observed: ${r.diagnostics.join("; ")}\n` : ""}${r.notes}`
          : `### Researcher ${r.brief.id}: ${r.brief.objective}\nFAILED (${r.failure?.kind}): ${r.failure?.message?.slice(0, 200) ?? ""}`,
      )
      .join("\n\n");
    const maxBriefs = Math.min(this.options.maxPerRound, ctx.budget.researchersRemaining);
    if (state.identityFirst) {
      const planner = planPrompt.pipe(ctx.model.withStructuredOutput(PlanSchema, { method: "jsonSchema", name: "grounded_research_plan" }));
      const plan = await planner.invoke({ today: ctx.today, question: state.question, summaries,
        context: `The identity discovery round has completed. Use the following source notes to scope independent assignments, not your prior guesses. If identity is unresolved, target exact-name discovery instead of assuming a domain.\n${summaries}`,
        maxBriefs: String(maxBriefs) });
      return { state: next, decision: { briefs: groundedBriefs(plan.briefs, state.question, summaries),
        stop: plan.briefs.length === 0, rationale: plan.rationale } };
    }
    const checker = gapPrompt.pipe(ctx.model.withStructuredOutput(GapSchema, { method: "jsonSchema", name: "gap_check" }));
    const gap = await checker.invoke({ today: ctx.today, question: state.question, summaries, maxBriefs: String(maxBriefs) });
    return {
      state: next,
      decision: { briefs: groundedBriefs(gap.briefs, state.question, summaries), stop: gap.briefs.length === 0, rationale: gap.rationale },
    };
  }

  async finalize(state: BaselineState): Promise<SynthesisInput> {
    return {
      material: state.notes.map((n) => ({ label: n.objective, notes: n.notes })),
      guidance: `Preserve the exact subject and any supplied acronym expansion in this question: ${state.question}\nDo not substitute a similarly named concept. If the notes fail to establish identity, say the identity remains unresolved. A bounded search cannot establish nonexistence or that the user's term is a misnomer. Exclude off-subject findings; distinguish related terms only when needed. ${state.interpretation ? `Provisional interpretation (subordinate to question and sources): ${state.interpretation}` : ""}`,
    };
  }
}

const baseline: StrategyModule = {
  name: "baseline",
  description: "Deep-research coordinator: source-first identity for definition questions, grounded parallel assignments, at most two rounds.",
  contractVersion: CONTRACT_VERSION,
  create: (options?: JsonValue) => new BaselineStrategy(OptionsSchema.parse(options ?? {})),
};
export default baseline;
