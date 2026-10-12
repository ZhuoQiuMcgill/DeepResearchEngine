/**
 * Per-role token and cost accounting. Every role (strategy, researcher,
 * writer) gets its own model instance with a handler that reports here.
 */
import { BaseCallbackHandler } from "@langchain/core/callbacks/base";
import type { LLMResult } from "@langchain/core/outputs";
import type { Pricing } from "../config/models.js";

export interface RoleUsage {
  calls: number;
  inputTokens: number;
  outputTokens: number;
  searches: number;
  pageReads: number;
  costUsd: number;
}

export class UsageLedger {
  readonly byRole: Record<string, RoleUsage> = {};

  constructor(private readonly pricing: Pricing) {}

  recordTools(role: string, u: { searches: number; pageReads: number }): void {
    const r = (this.byRole[role] ??= { calls: 0, inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0, costUsd: 0 });
    r.searches += u.searches;
    r.pageReads += u.pageReads;
    r.costUsd += u.searches * this.pricing.perSearch;
  }

  record(role: string, u: { inputTokens: number; outputTokens: number; searches?: number; pageReads?: number }): void {
    const r = (this.byRole[role] ??= { calls: 0, inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0, costUsd: 0 });
    const searches = u.searches ?? 0;
    r.calls += 1;
    r.inputTokens += u.inputTokens;
    r.outputTokens += u.outputTokens;
    r.searches += searches;
    r.pageReads += u.pageReads ?? 0;
    r.costUsd +=
      (u.inputTokens * this.pricing.inputPerM(u.inputTokens)) / 1e6 +
      (u.outputTokens * this.pricing.outputPerM(u.inputTokens)) / 1e6 +
      searches * this.pricing.perSearch;
  }

  total(): RoleUsage {
    const t: RoleUsage = { calls: 0, inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0, costUsd: 0 };
    for (const r of Object.values(this.byRole)) {
      t.calls += r.calls;
      t.inputTokens += r.inputTokens;
      t.outputTokens += r.outputTokens;
      t.searches += r.searches;
      t.pageReads += r.pageReads;
      t.costUsd += r.costUsd;
    }
    return t;
  }

  /** Callback handler that records token usage of every chat model call under `role`. */
  handler(role: string): BaseCallbackHandler {
    const ledger = this;
    return BaseCallbackHandler.fromMethods({
      handleLLMEnd(output: LLMResult) {
        for (const gens of output.generations) {
          for (const gen of gens) {
            const msg = (gen as { message?: { usage_metadata?: { input_tokens?: number; output_tokens?: number } } }).message;
            const um = msg?.usage_metadata;
            if (um) ledger.record(role, { inputTokens: um.input_tokens ?? 0, outputTokens: um.output_tokens ?? 0 });
          }
        }
      },
    });
  }
}
