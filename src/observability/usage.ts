/**
 * Per-role token and cost accounting. Every role (strategy, researcher,
 * writer) gets its own model instance with a handler that reports here.
 */
import { BaseCallbackHandler } from "@langchain/core/callbacks/base";
import type { LLMResult } from "@langchain/core/outputs";
import type { Pricing } from "../config/models.js";

export interface RoleUsage {
  calls: number;
  /** All input tokens, cached ones included. */
  inputTokens: number;
  /** Part of `inputTokens` the provider reported as served from its prompt cache, where recorded. */
  cachedInputTokens: number;
  outputTokens: number;
  searches: number;
  pageReads: number;
  costUsd: number;
}

const empty = (): RoleUsage => ({ calls: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0, costUsd: 0 });

export class UsageLedger {
  readonly byRole: Record<string, RoleUsage> = {};

  constructor(private readonly pricing: Pricing) {}

  record(
    role: string,
    u: { inputTokens: number; outputTokens: number; cachedInputTokens?: number; searches?: number; pageReads?: number },
  ): void {
    const r = (this.byRole[role] ??= empty());
    const searches = u.searches ?? 0;
    const cached = Math.min(Math.max(u.cachedInputTokens ?? 0, 0), u.inputTokens);
    const cachedRate = this.pricing.cachedInputPerM ?? this.pricing.inputPerM;
    r.calls += 1;
    r.inputTokens += u.inputTokens;
    r.cachedInputTokens += cached;
    r.outputTokens += u.outputTokens;
    r.searches += searches;
    r.pageReads += u.pageReads ?? 0;
    r.costUsd +=
      ((u.inputTokens - cached) * this.pricing.inputPerM(u.inputTokens)) / 1e6 +
      (cached * cachedRate(u.inputTokens)) / 1e6 +
      (u.outputTokens * this.pricing.outputPerM(u.inputTokens)) / 1e6 +
      searches * this.pricing.perSearch;
  }

  total(): RoleUsage {
    const t = empty();
    for (const r of Object.values(this.byRole)) {
      t.calls += r.calls;
      t.inputTokens += r.inputTokens;
      t.cachedInputTokens += r.cachedInputTokens;
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
            type Usage = { input_tokens?: number; output_tokens?: number; input_token_details?: { cache_read?: number } };
            const msg = (gen as { message?: { usage_metadata?: Usage } }).message;
            const um = msg?.usage_metadata;
            if (um) {
              ledger.record(role, {
                inputTokens: um.input_tokens ?? 0,
                outputTokens: um.output_tokens ?? 0,
                cachedInputTokens: um.input_token_details?.cache_read ?? 0,
              });
            }
          }
        }
      },
    });
  }
}
