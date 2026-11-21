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
  /**
   * USD per million input tokens the provider served from its prompt cache.
   * Without it, cached tokens are priced at `inputPerM`.
   */
  cachedInputPerM?: (promptTokens: number) => number;
  outputPerM: (promptTokens: number) => number;
  /** USD per billed search operation. */
  perSearch: number;
}

interface ProfileBase {
  name: string;
  model: string;
  maxOutputTokens: number;
  /**
   * Output limit of the writer role, when it needs more than `maxOutputTokens`. On
   * Anthropic a limit above the SDK's non-streaming ceiling (~21.3k) streams the call.
   * Added 2026-11-21: EBD reports on Haiku and DeepSeek reports were cut at 21,000 tokens.
   */
  writerMaxOutputTokens?: number;
  /** Tool-call cap reported to strategies as `toolCallsPerResearcher`. */
  toolCallsPerResearcher: number;
  pricing: Pricing;
}

/** The Anthropic SDK refuses larger non-streaming `max_tokens` values. */
const ANTHROPIC_NON_STREAMING_MAX = 21_000;

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

/**
 * DeepSeek through two of its compatible endpoints (probes E9, docs/plan.md):
 * the researcher uses the Anthropic-compatible Messages endpoint, which carries
 * DeepSeek's web tools (and is the only one where `max_uses` caps web search);
 * strategy roles and the writer use the Responses endpoint, the only one that
 * honours a `json_schema` output format.
 */
export interface DeepSeekProfile extends ProfileBase {
  provider: "deepseek";
  /**
   * Thinking effort, sent as output_config.effort (Messages) and reasoning.effort
   * (Responses) with thinking enabled. DeepSeek accepts low, high and max and maps
   * a requested medium to high.
   */
  effort: "low" | "high" | "max";
  /**
   * Output limit of the researcher when it needs more than `maxOutputTokens`. Above the
   * Anthropic SDK's non-streaming ceiling (~21.3k) the researcher call streams, and the
   * adapter rebuilds the reply from the stream. Added 2026-11-21: 4 of 57 DeepSeek
   * researchers were cut at 21,000 tokens (thinking counts toward the limit).
   */
  researcherMaxOutputTokens?: number;
  /** Base URL for ChatAnthropic (researcher). */
  messagesBaseUrl: string;
  /** Base URL for ChatOpenAI with the Responses API (strategy roles, writer). */
  responsesBaseUrl: string;
  /**
   * `deepseek_web_search` (the profile's mode): deep thinking search with page opens, no
   * enforceable cap (the API ignored both `max_uses` and `max_tool_calls`); every result
   * carries a diagnostic saying so.
   * `web_search_20250305` with `max_uses` (alternative): plain searches, no page reads, cap
   * enforced by the API, which in E9 also stopped every request after 5 executed searches.
   */
  webSearch: { type: "web_search_20250305"; maxUses: number } | { type: "deepseek_web_search" };
}

export type ModelProfile = AnthropicProfile | OpenAIProfile | DeepSeekProfile;

/** Environment variable that holds the DeepSeek API key. */
export const DEEPSEEK_KEY_VAR = "DEEPSEEK_API_KEY";

export function deepseekApiKey(): string {
  const key = process.env[DEEPSEEK_KEY_VAR];
  if (!key) throw new Error(`${DEEPSEEK_KEY_VAR} is not set`);
  return key;
}

export const PROFILES: Record<string, ModelProfile> = {
  haiku: {
    name: "haiku",
    provider: "anthropic",
    model: "claude-haiku-5-5",
    effort: "medium",
    // Highest value the Anthropic SDK accepts without streaming (~21.3k); thinking counts toward it.
    maxOutputTokens: 21000,
    // The writer streams; Haiku 5.5 allows up to 128k output tokens.
    writerMaxOutputTokens: 64000,
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
  deepseek: {
    name: "deepseek",
    provider: "deepseek",
    // Served by DeepSeek-V4.1-Flash-1017 (pricing page and change log, 2026-10-17; the alias is upgraded in place). Web tools work on it (E9).
    model: "deepseek-flash",
    effort: "high",
    // Below the Anthropic SDK's non-streaming limit (~21.3k), which ChatAnthropic enforces for any model.
    maxOutputTokens: 21000,
    // The writer runs on ChatOpenAI (Responses), which has no such ceiling; DeepSeek allows 393k.
    writerMaxOutputTokens: 64000,
    // The researcher streams above 21,000; the adapter rebuilds the reply from the stream.
    researcherMaxOutputTokens: 64000,
    messagesBaseUrl: "https://api.deepseek.com/anthropic",
    responsesBaseUrl: "https://api.deepseek.com",
    // DeepSeek's built-in deep search (searches and page opens). It has no hard per-researcher
    // cap, so every result says so; runs are bounded by maxRounds and researchersTotal.
    // Documented alternative: { type: "web_search_20250305", maxUses: 12 }, capped by the API
    // (5 searches in effect) but searches only.
    webSearch: { type: "deepseek_web_search" },
    // Soft budget stated in the shared researcher prompt, the same for every model.
    toolCallsPerResearcher: 12,
    // https://api-docs.deepseek.com/quick_start/pricing (read 2026-11-20), USD per 1M tokens.
    // Off-peak rates. Peak hours (01:00-04:00 and 06:00-10:00 UTC, Monday to Friday,
    // except Chinese public holidays) bill at twice these rates; the estimate keeps
    // the off-peak rate so a run's cost depends on its tokens, not on the hour.
    pricing: {
      inputPerM: () => 0.15,
      cachedInputPerM: () => 0.003,
      outputPerM: () => 0.6,
      // Server-side search and fetch during model calls are unbilled since
      // 2026-11-18 12:00 UTC+8 (pricing page and Web Tools guide); only tokens are billed.
      perSearch: 0,
    },
  },
};

export function getProfile(name: string): ModelProfile {
  const profile = PROFILES[name];
  if (!profile) throw new Error(`Unknown model profile "${name}". Known: ${Object.keys(PROFILES).join(", ")}`);
  return profile;
}

/** A plain chat model for one role, without web tools. `role: "writer"` uses the writer's output limit. */
export function createChatModel(profile: ModelProfile, callbacks?: Callbacks, opts: { role?: "writer" } = {}): BaseChatModel {
  const maxTokens = opts.role === "writer" ? (profile.writerMaxOutputTokens ?? profile.maxOutputTokens) : profile.maxOutputTokens;
  if (profile.provider === "anthropic") {
    return new ChatAnthropic({
      model: profile.model,
      maxTokens,
      outputConfig: { effort: profile.effort },
      // invoke() still returns one message; usage and stop_reason are aggregated from the stream.
      ...(maxTokens > ANTHROPIC_NON_STREAMING_MAX ? { streaming: true, streamUsage: true } : {}),
      maxRetries: 2,
      callbacks,
    });
  }
  if (profile.provider === "deepseek") {
    // The Responses endpoint: the Messages endpoint ignores output_config.format and
    // Chat Completions rejects json_schema, which the baseline's planner needs (E9).
    // ChatOpenAI drops `reasoning` for non-OpenAI model names, so it goes in modelKwargs.
    return new ChatOpenAI({
      model: profile.model,
      apiKey: deepseekApiKey(),
      configuration: { baseURL: profile.responsesBaseUrl },
      useResponsesApi: true,
      modelKwargs: { reasoning: { effort: profile.effort } },
      maxTokens,
      maxRetries: 2,
      callbacks,
    });
  }
  return new ChatOpenAI({
    model: profile.model,
    useResponsesApi: true,
    reasoning: { effort: profile.reasoningEffort },
    maxTokens,
    maxRetries: 2,
    callbacks,
  });
}
