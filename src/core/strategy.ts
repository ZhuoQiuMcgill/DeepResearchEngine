/**
 * The strategy plug-in contract, version 1. Baseline and EBD both implement
 * it; the research module depends on nothing else. See docs/strategy-modules.md.
 */
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { BudgetView, Decision, ResearchResult, SynthesisInput } from "./contracts.js";

/** Contract version. Fields are only ever added within a major version. */
export const CONTRACT_VERSION = "1";

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
  /** The run's date (YYYY-MM-DD), shared by every component of the run. */
  today: string;
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
  /**
   * Select and organise the material the shared writer receives. Material must
   * be researcher notes: selected, ordered or excerpted by whole lines, never
   * rewritten or extended. The strategy's own analysis goes into `outline` or
   * `guidance`.
   */
  finalize(state: S, ctx: StrategyContext): Promise<SynthesisInput>;
}

/**
 * What a strategy directory exports as its default export:
 * `src/strategies/<name>/index.ts`. The platform loads it by name.
 */
export interface StrategyModule {
  /** Must equal the directory name. */
  name: string;
  description: string;
  /** Contract version the module was written against. */
  contractVersion: string;
  /** Build a strategy for one run. `options` comes from the experiment config. */
  create(options?: JsonValue): ResearchStrategy<any>;
}
