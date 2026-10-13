import type { BaseMessage } from "@langchain/core/messages";
import type { Callbacks } from "@langchain/core/callbacks/manager";
import type { UsageLedger } from "../../observability/usage.js";
import type { Source } from "../../core/contracts.js";

/** What a provider adapter extracts from one researcher run. */
export interface AdapterOutput {
  /** Final notes text, URLs cleaned of tracking parameters. */
  notes: string;
  /** Every URL the provider reported: search results, opened pages, citations. */
  sources: Omit<Source, "cited">[];
  /** URLs the provider attached as structured citations to the final text. */
  citedUrls: string[];
  queries: string[];
  inputTokens: number;
  outputTokens: number;
  searches: number;
  pageReads: number;
  diagnostics: string[];
}

export interface AdapterCall {
  messages: BaseMessage[];
  ledger: UsageLedger;
  role: string;
  callbacks?: Callbacks;
  signal: AbortSignal;
  /** Supplied by the graph from completed prior rounds, never parsed from model text. */
  inheritedSources?: Source[];
}
