/**
 * The research strategy interface. Baseline and EBD both implement it; the
 * skeleton depends on nothing else. See docs/design.md section 3.
 */
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { BudgetView, Decision, ResearchResult, SynthesisInput } from "./contracts.js";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface StrategyContext {
  /** The arm's model. Strategies must not create their own models. */
  model: BaseChatModel;
  /** Researcher budget at the time of the call. */
  budget: BudgetView;
  /** 1-based round that briefs returned from this call would start. */
  round: number;
  runId: string;
}

export interface StrategyStep<S extends JsonValue> {
  /** Strategy-private state. Must round-trip through JSON unchanged. */
  state: S;
  decision: Decision;
}

export interface ResearchStrategy<S extends JsonValue = JsonValue> {
  readonly name: string;
  /** Analyse the question and choose the first briefs. */
  init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<S>>;
  /** Process one round of results (failures included) and choose the next briefs, or stop. */
  observe(state: S, results: ResearchResult[], ctx: StrategyContext): Promise<StrategyStep<S>>;
  /** Select and organise the material the shared writer receives. */
  finalize(state: S, ctx: StrategyContext): Promise<SynthesisInput>;
}
