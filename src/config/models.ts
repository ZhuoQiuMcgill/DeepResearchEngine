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
  /** Sent explicitly as output_config.effort so a provider default change cannot alter runs. */
  effort: "low" | "medium" | "high" | "xhigh" | "max";
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

export interface LocalProfile extends ProfileBase {
  provider: "local";
  baseURL: string;
  contextWindowTokens: number;
  corpusPath: string;
  sourceMode?: "local-corpus" | "tavily-web";
}
export type ModelProfile = AnthropicProfile | OpenAIProfile | LocalProfile;

export function localProfile(env: NodeJS.ProcessEnv = process.env): LocalProfile {
  const baseURL = env.LOCAL_MODEL_BASE_URL || "http://127.0.0.1:18086/v1";
  const url = new URL(baseURL);
  if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) || url.username || url.password || url.search || url.hash)
    throw new Error("Local model URL must be a loopback endpoint without credentials, query or fragment.");
  const contextWindowTokens = Number(env.LOCAL_MODEL_CONTEXT_TOKENS || 262144);
  if (!Number.isSafeInteger(contextWindowTokens) || contextWindowTokens < 8192) throw new Error("Invalid local context window.");
  return {
    name: "local", provider: "local", model: env.LOCAL_MODEL_NAME || "qwen38-local-256k",
    baseURL, contextWindowTokens, corpusPath: env.LOCAL_CORPUS_PATH || "local/ebd-corpus.json",
    maxOutputTokens: 8192, toolCallsPerResearcher: 8,
    pricing: { inputPerM: () => 0, outputPerM: () => 0, perSearch: 0 },
  };
}

export const PROFILES: Record<string, ModelProfile> = {
  haiku: {
    name: "haiku",
    provider: "anthropic",
    model: "claude-haiku-5-5",
    effort: "medium",
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
  if (name === "local") return localProfile();
  if (name === "local-web") return { ...localProfile(), name: "local-web", sourceMode: "tavily-web" };
  const profile = PROFILES[name];
  if (!profile) throw new Error(`Unknown model profile "${name}". Known: ${[...Object.keys(PROFILES), "local", "local-web"].join(", ")}`);
  return profile;
}

/** A plain chat model for one role, without web tools. */
export function createChatModel(profile: ModelProfile, callbacks?: Callbacks): BaseChatModel {
  if (profile.provider === "local") {
    return new ChatOpenAI({ model: profile.model, useResponsesApi: false,
      apiKey: "local-no-key", configuration: { baseURL: profile.baseURL },
      modelKwargs: { chat_template_kwargs: { enable_thinking: false } },
      maxTokens: profile.maxOutputTokens, temperature: 0.2, maxRetries: 0, callbacks });
  }
  if (profile.provider === "anthropic") {
    return new ChatAnthropic({
      model: profile.model,
      maxTokens: profile.maxOutputTokens,
      outputConfig: { effort: profile.effort },
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
