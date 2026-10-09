/**
 * Model profiles. A profile fixes everything model-specific for one arm: the
 * model id, generation settings, built-in web tool settings and prices used
 * for cost estimates.
 */
import { ChatAnthropic } from "@langchain/anthropic";
import { ChatOpenAI } from "@langchain/openai";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { Callbacks } from "@langchain/core/callbacks/manager";

export interface Pricing {
  /**
   * USD per million input tokens, by prompt size tier. The 2026-10-09 bills
   * priced every call at the base rate, including server-side search loops
   * whose cumulative input exceeded the long-prompt threshold, so the
   * profiles use the base rate only.
   */
  inputPerM: (promptTokens: number) => number;
  outputPerM: (promptTokens: number) => number;
  /** USD per billed search operation. */
  perSearch: number;
}

interface ProfileBase {
  name: string;
  model: string;
  maxOutputTokens: number;
  /** Tool-call cap reported to strategies as `toolCallsPerResearcher`. */
  toolCallsPerResearcher: number;
  pricing: Pricing;
}

export interface AnthropicProfile extends ProfileBase {
  provider: "anthropic";
  webSearch: { type: string; maxUses: number };
  webFetch?: { type: string; maxUses: number };
  /** Bounded continuation of `pause_turn` responses. */
  maxContinuations: number;
}

export interface OpenAIProfile extends ProfileBase {
  provider: "openai";
  reasoningEffort: "minimal" | "low" | "medium" | "high";
  webSearch: { searchContextSize: "low" | "medium" | "high"; maxToolCalls: number };
}

export type ModelProfile = AnthropicProfile | OpenAIProfile;

export const PROFILES: Record<string, ModelProfile> = {
  haiku: {
    name: "haiku",
    provider: "anthropic",
    model: "claude-haiku-5-5",
    // Highest value the Anthropic SDK accepts without streaming (~21.3k); thinking counts toward it.
    maxOutputTokens: 21000,
    // Direct (basic) tool versions: with the dynamic-filtering versions Haiku's
    // generated code often called web_search with a malformed input (round 1).
    webSearch: { type: "web_search_20250305", maxUses: 8 },
    webFetch: { type: "web_fetch_20250910", maxUses: 4 },
    toolCallsPerResearcher: 12,
    maxContinuations: 3,
    pricing: {
      inputPerM: () => 0.1,
      outputPerM: () => 0.5,
      // Billed per query: each web_search use is one search.
      perSearch: 0.01,
    },
  },
  luna: {
    name: "luna",
    provider: "openai",
    model: "gpt-6-luna",
    maxOutputTokens: 32000,
    reasoningEffort: "medium",
    webSearch: { searchContextSize: "medium", maxToolCalls: 12 },
    toolCallsPerResearcher: 12,
    pricing: {
      inputPerM: () => 0.1,
      outputPerM: () => 0.5,
      // Billed per web_search call; one call often carries several queries.
      perSearch: 0.01,
    },
  },
};

export function getProfile(name: string): ModelProfile {
  const profile = PROFILES[name];
  if (!profile) throw new Error(`Unknown model profile "${name}". Known: ${Object.keys(PROFILES).join(", ")}`);
  return profile;
}

/** A plain chat model for one role, without web tools. */
export function createChatModel(profile: ModelProfile, callbacks?: Callbacks): BaseChatModel {
  if (profile.provider === "anthropic") {
    return new ChatAnthropic({
      model: profile.model,
      maxTokens: profile.maxOutputTokens,
      maxRetries: 2,
      callbacks,
    });
  }
  return new ChatOpenAI({
    model: profile.model,
    useResponsesApi: true,
    reasoning: { effort: profile.reasoningEffort },
    maxTokens: profile.maxOutputTokens,
    maxRetries: 2,
    callbacks,
  });
}
