/**
 * Everything a strategy module may import from the platform. Strategy code
 * imports from here only; other platform internals may change.
 */
export {
  CONTRACT_VERSION,
  type JsonValue,
  type ResearchStrategy,
  type StrategyContext,
  type StrategyModule,
  type StrategyStep,
} from "./strategy.js";
export {
  BudgetViewSchema,
  DecisionSchema,
  ResearchBriefInputSchema,
  ResearchBriefSchema,
  ResearchResultSchema,
  SynthesisInputSchema,
  type BudgetView,
  type Decision,
  type FailureKind,
  type ResearchBrief,
  type ResearchBriefInput,
  type ResearchResult,
  type Source,
  type SynthesisInput,
  type Usage,
} from "./contracts.js";
export { parseNotes, summarizeNotes, type NotesSection, type ParsedNotes } from "./notes.js";
