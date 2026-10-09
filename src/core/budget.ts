/**
 * Researcher budget: the run-level cap on researchers. Per-researcher tool caps
 * are enforced by the provider APIs and only reported here.
 */
import {
  ResearchBriefInputSchema,
  type BudgetView,
  type Decision,
  type ResearchBrief,
  type ResearchBriefInput,
} from "./contracts.js";

export interface BudgetLimits {
  researchersTotal: number;
  toolCallsPerResearcher: number;
}

export function budgetView(limits: BudgetLimits, researchersUsed: number): BudgetView {
  return {
    researchersTotal: limits.researchersTotal,
    researchersUsed,
    researchersRemaining: Math.max(0, limits.researchersTotal - researchersUsed),
    toolCallsPerResearcher: limits.toolCallsPerResearcher,
  };
}

export interface AppliedDecision {
  /** Briefs that will run, with ids and round assigned. */
  accepted: ResearchBrief[];
  /** Briefs dropped because the budget ran out, highest priority kept first. */
  dropped: ResearchBriefInput[];
  /** Briefs ignored because the decision also said stop. */
  ignored: ResearchBriefInput[];
  /** Briefs that failed validation, with the reason. */
  invalid: { brief: unknown; reason: string }[];
  stop: boolean;
}

/**
 * Validate a decision and fit it to the remaining budget. Dropping is stable:
 * among equal priorities the strategy's order is kept.
 */
export function applyDecision(decision: Decision, round: number, budget: BudgetView): AppliedDecision {
  const valid: ResearchBriefInput[] = [];
  const invalid: AppliedDecision["invalid"] = [];
  for (const raw of decision.briefs ?? []) {
    const parsed = ResearchBriefInputSchema.safeParse(raw);
    if (parsed.success) valid.push(parsed.data);
    else invalid.push({ brief: raw, reason: parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ") });
  }
  if (decision.stop) {
    return { accepted: [], dropped: [], ignored: valid, invalid, stop: true };
  }
  const ranked = valid
    .map((brief, index) => ({ brief, index }))
    .sort((a, b) => (b.brief.priority ?? 0) - (a.brief.priority ?? 0) || a.index - b.index);
  const keep = ranked.slice(0, budget.researchersRemaining);
  const dropped = ranked.slice(budget.researchersRemaining).map((r) => r.brief);
  // Run kept briefs in the strategy's original order.
  const accepted = keep
    .sort((a, b) => a.index - b.index)
    .map(({ brief }, i) => ({ ...ResearchBriefInputSchema.parse(brief), id: `r${round}-b${i + 1}`, round }));
  return { accepted, dropped, ignored: [], invalid, stop: accepted.length === 0 };
}
