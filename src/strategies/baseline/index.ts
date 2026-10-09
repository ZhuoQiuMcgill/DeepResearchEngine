/**
 * Baseline strategy: the reference implementation of ResearchStrategy.
 * It follows the coordinator of Claude Code's deep-research skill:
 * decompose once, run researchers in parallel, optionally one extra round for
 * critical gaps, then hand every note to the writer.
 */
import { z } from "zod";
import type { ResearchResult, SynthesisInput } from "../../core/contracts.js";
import type { ResearchStrategy, StrategyContext, StrategyStep } from "../../core/strategy.js";
import { gapPrompt, planPrompt } from "./prompts.js";

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

/** Maximum researchers per round, following the skill's decomposition table. */
const MAX_PER_ROUND = 6;

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
  notes: BaselineNote[];
  failures: { briefId: string; objective: string; failure: string }[];
};

const today = () => new Date().toISOString().slice(0, 10);

export class BaselineStrategy implements ResearchStrategy<BaselineState> {
  readonly name = "baseline";

  async init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<BaselineState>> {
    const maxBriefs = Math.min(MAX_PER_ROUND, ctx.budget.researchersRemaining);
    const planner = planPrompt.pipe(ctx.model.withStructuredOutput(PlanSchema, { method: "jsonSchema", name: "research_plan" }));
    const plan = await planner.invoke({ today: today(), question: input.question, maxBriefs: String(maxBriefs) });
    return {
      state: { question: input.question, interpretation: plan.interpretation.trim(), rounds: 0, notes: [], failures: [] },
      decision: { briefs: plan.briefs, stop: false, rationale: plan.rationale },
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
    // The skill allows exactly one optional follow-up round.
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
    const maxBriefs = Math.min(MAX_PER_ROUND, ctx.budget.researchersRemaining);
    const checker = gapPrompt.pipe(ctx.model.withStructuredOutput(GapSchema, { method: "jsonSchema", name: "gap_check" }));
    const gap = await checker.invoke({ today: today(), question: state.question, summaries, maxBriefs: String(maxBriefs) });
    return {
      state: next,
      decision: { briefs: gap.briefs, stop: gap.briefs.length === 0, rationale: gap.rationale },
    };
  }

  async finalize(state: BaselineState): Promise<SynthesisInput> {
    return {
      material: state.notes.map((n) => ({ label: n.objective, notes: n.notes })),
      ...(state.interpretation
        ? { guidance: `The question was read as follows: ${state.interpretation} Mention this reading only where it changes the answer, and do not open the report with it.` }
        : {}),
    };
  }
}
