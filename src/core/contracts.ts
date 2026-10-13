/**
 * Shared data contracts between the skeleton and research strategies.
 *
 * Fields are only ever added. Existing fields keep their meaning so that
 * strategies written against an earlier version keep working.
 */
import { z } from "zod";

export const ResearchBriefInputSchema = z.object({
  objective: z.string().min(1).describe("What this researcher must find out"),
  keyQuestions: z.array(z.string().min(1)).min(1).describe("Specific questions the notes must answer"),
  constraints: z.array(z.string()).default([]).describe("Bounds carried from the question: time, place, scope"),
  sourceHints: z.array(z.string()).default([]).describe("Kinds of sources to prioritise"),
  instructions: z.string().optional().describe("Extra researcher guidance; fills the researcher prompt's instructions slot"),
  priority: z.number().optional().describe("Higher runs first when the budget cannot cover every brief"),
  tag: z.string().optional().describe("Opaque label for the strategy's own bookkeeping"),
});
export type ResearchBriefInput = z.input<typeof ResearchBriefInputSchema>;

export const ResearchBriefSchema = ResearchBriefInputSchema.extend({
  id: z.string(),
  round: z.number().int().positive(),
});
export type ResearchBrief = z.infer<typeof ResearchBriefSchema>;

export const SourceSchema = z.object({
  url: z.string(),
  title: z.string().optional(),
  /** The URL appears in the notes text or in a provider citation. */
  cited: z.boolean(),
  /** Earliest completed researcher that supplied an inherited source. */
  originBriefId: z.string().optional(),
  /** What the tools actually obtained, not a model's claim to have read it. */
  readState: z.enum(["snippet", "read", "truncated", "failed"]).optional(),
});
export type Source = z.infer<typeof SourceSchema>;

export const UsageSchema = z.object({
  inputTokens: z.number().int().nonnegative(),
  outputTokens: z.number().int().nonnegative(),
  /** Search operations billed by the provider. */
  searches: z.number().int().nonnegative(),
  /** Page reads: Anthropic web_fetch uses, OpenAI open_page/find_in_page actions. */
  pageReads: z.number().int().nonnegative(),
});
export type Usage = z.infer<typeof UsageSchema>;

export const FailureKindSchema = z.enum(["provider", "timeout", "empty"]);
export type FailureKind = z.infer<typeof FailureKindSchema>;

export const ResearchResultSchema = z.object({
  brief: ResearchBriefSchema,
  status: z.enum(["ok", "failed"]),
  failure: z.object({ kind: FailureKindSchema, message: z.string() }).optional(),
  /** Markdown in the shared notes format. Empty when the researcher failed. */
  notes: z.string(),
  sources: z.array(SourceSchema),
  queries: z.array(z.string()),
  usage: UsageSchema,
  model: z.string(),
  durationMs: z.number().nonnegative(),
  /** URLs cited in the notes that the provider's tools did not report (possible memory citations). */
  unlistedCitations: z.array(z.string()).default([]),
  /** Non-fatal observations, e.g. a tool cap was hit or the notes did not parse. */
  diagnostics: z.array(z.string()).default([]),
});
export type ResearchResult = z.infer<typeof ResearchResultSchema>;

export const DecisionSchema = z.object({
  briefs: z.array(ResearchBriefInputSchema),
  /** True means no further research; any briefs in the same decision are ignored. */
  stop: z.boolean(),
  rationale: z.string(),
});
export type Decision = z.input<typeof DecisionSchema>;

export const SynthesisInputSchema = z.object({
  material: z
    .array(z.object({ label: z.string(), notes: z.string() }))
    .describe("Research notes in the order the writer should consider them"),
  outline: z.array(z.string()).optional().describe("Optional section guidance"),
  guidance: z.string().optional().describe("Optional extra writer guidance"),
  sourceRegistry: z.array(SourceSchema).optional().describe("Graph-supplied source access and origin metadata; never model-generated provenance"),
});
export type SynthesisInput = z.infer<typeof SynthesisInputSchema>;

export const BudgetViewSchema = z.object({
  researchersTotal: z.number().int().nonnegative(),
  researchersUsed: z.number().int().nonnegative(),
  researchersRemaining: z.number().int().nonnegative(),
  /** Tool-call cap each researcher works under, as configured for the model. */
  toolCallsPerResearcher: z.number().int().positive(),
});
export type BudgetView = z.infer<typeof BudgetViewSchema>;

export function emptyUsage(): Usage {
  return { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 };
}

export function addUsage(a: Usage, b: Usage): Usage {
  return {
    inputTokens: a.inputTokens + b.inputTokens,
    outputTokens: a.outputTokens + b.outputTokens,
    searches: a.searches + b.searches,
    pageReads: a.pageReads + b.pageReads,
  };
}
