/**
 * Researcher adapter for DeepSeek on its Anthropic-compatible Messages endpoint
 * with server-side web search (probes E9, docs/plan.md).
 *
 * DeepSeek runs the search loop server-side in one call. Replies that only announce
 * the research get a follow-up turn (see RESEARCH_REQUEST), and an error body sent
 * with HTTP 200 is retried once.
 *
 * - `deepseek_web_search` (deep thinking search, the profile's mode): searches
 *   and page opens; no cap can be set, and every result says so.
 * - `web_search_20250305` (alternative): the API enforces `max_uses` and answers
 *   further attempts with `max_uses_exceeded`, but in E9 it also rejected every
 *   search after the 5th with `max_uses: 12`. When the model kept trying, the
 *   server sometimes ended the turn with `stop_reason: "tool_use"` and no notes.
 *   The adapter then sends the reply back once with a user turn asking for the
 *   notes and `tool_choice: "none"`; re-sending the reply as the last message is
 *   rejected (400). After deep search this would not help: DeepSeek drops the
 *   deep-search blocks from a follow-up turn, so such a stop is only recorded.
 */
import { ChatAnthropic } from "@langchain/anthropic";
import { HumanMessage, type AIMessage, type BaseMessage } from "@langchain/core/messages";
import { deepseekApiKey, type DeepSeekProfile } from "../../config/models.js";
import { parseNotes } from "../../core/notes.js";
import { cleanUrl, cleanUrlsInText } from "../../core/urls.js";
import type { AdapterCall, AdapterOutput } from "./types.js";

type Block = Record<string, any>;

/** The parts of a Messages API response that the adapter reads. */
export interface DeepSeekResponse {
  content: Block[];
  usage?: Block;
  stop_reason?: string | null;
  /** Error body that DeepSeek sent with HTTP 200, usage included. */
  error?: Block;
}

export interface DeepSeekParsed {
  output: AdapterOutput;
  /** Part of `output.inputTokens` served from DeepSeek's context cache. */
  cachedInputTokens: number;
}

/**
 * DeepSeek appends result markers such as `#1` or `#1#6#1` to URLs in search
 * results, page opens and citations. They are not part of the page address.
 */
const MARKERS = /(?:#\d+)+$/;
const MARKERS_IN_TEXT = /(https?:\/\/[^\s<>"'\]`#]+)(?:#\d+)+(?![\w#/-])/g;

/** Tracking parameters and DeepSeek's result markers removed. */
export function cleanDeepSeekUrl(url: string): string {
  return cleanUrl(url).replace(MARKERS, "");
}

export function cleanDeepSeekUrlsInText(text: string): string {
  return cleanUrlsInText(text).replace(MARKERS_IN_TEXT, "$1");
}

/** Server tool definitions sent as raw request fields. */
export function deepseekTools(profile: DeepSeekProfile): Block[] {
  return profile.webSearch.type === "deepseek_web_search"
    ? [{ type: "deepseek_web_search", name: "deepseek_web_search" }]
    : [{ type: profile.webSearch.type, name: "web_search", max_uses: profile.webSearch.maxUses }];
}

/** The user turn of the one continuation after a `tool_use` stop without notes. */
export const NOTES_REQUEST = "The search tool is no longer available. Write your notes now from the results above, in the required format.";

export type DeepSeekInvoke = (messages: BaseMessage[], options: { signal: AbortSignal; tool_choice?: "none" }) => Promise<AIMessage>;

/**
 * fetch for the Messages endpoint. DeepSeek sometimes answers HTTP 200 with an error body
 * that has `type`, `error` and `usage` but no `content` ("The model failed to generate a
 * complete response", after a deep search had run for a while). ChatAnthropic then throws
 * "Cannot read properties of undefined (reading 'length')" in
 * anthropicResponseToChatMessages, and the error and its billed usage are lost. Five
 * researchers of the 2026-11-21 ResearchRubrics experiment failed this way. Adding an empty
 * `content` lets the adapter see the error body, count its tokens and retry once.
 */
export function withErrorBodyContent(base?: typeof fetch): typeof fetch {
  return async (input, init) => {
    const res = await (base ?? globalThis.fetch)(input, init);
    if (res.status !== 200) return res;
    let body: unknown;
    try {
      body = await res.clone().json();
    } catch {
      return res;
    }
    const b = body as Block | null;
    if (!b || typeof b !== "object" || b.type !== "error" || Array.isArray(b.content)) return res;
    const headers = new Headers(res.headers);
    headers.delete("content-length");
    headers.delete("content-encoding");
    return new Response(JSON.stringify({ ...b, content: [] }), { status: res.status, statusText: res.statusText, headers });
  };
}

/** The model call of the researcher; `options` replace the network and the key in tests. */
export function deepseekInvoke(profile: DeepSeekProfile, call: AdapterCall, options: { fetch?: typeof fetch; apiKey?: string } = {}): DeepSeekInvoke {
  const model = new ChatAnthropic({
    model: profile.model,
    apiKey: options.apiKey ?? deepseekApiKey(),
    anthropicApiUrl: profile.messagesBaseUrl,
    maxTokens: profile.maxOutputTokens,
    // Sent explicitly so a change of DeepSeek's default cannot alter runs; DeepSeek treats adaptive as enabled.
    thinking: { type: "adaptive" },
    outputConfig: { effort: profile.effort },
    // Raw request fields: LangChain's tool formatting rejects the deepseek_* tool types.
    invocationKwargs: { tools: deepseekTools(profile) },
    maxRetries: 2,
    clientOptions: { fetch: withErrorBodyContent(options.fetch) },
    callbacks: call.callbacks,
  });
  return async (messages, opts) => (await model.invoke(messages, opts as never)) as AIMessage;
}

/**
 * The user turn sent after a reply that only announced its research. In deep-search mode
 * 13 of 20 first replies in the E9 acceptance runs were one sentence ("I'll start by
 * searching ...") with no thinking and no tool call, and the turn ended. The same request
 * sent again (thinking enabled, adaptive or omitted, a system line, or the Responses
 * endpoint) searched in 2 of 18 tries. This turn started the research in about half of the
 * tries (8 of 16 in the accepted runs; every researcher started within 4).
 */
export const RESEARCH_REQUEST = "Go ahead with your research now.";
/**
 * Follow-up turns after a reply without research, each a fresh sample of the same
 * conversation. 8 leaves about 0.4% of announcing researchers without notes at a 50% rate;
 * a failed try costs about a second and 2-3k input tokens.
 */
export const MAX_RESEARCH_REQUESTS = 8;

/** True when a reply neither used a tool nor wrote notes in the shared format. */
export function isAnnouncement(res: DeepSeekResponse): boolean {
  if (res.error || res.stop_reason !== "end_turn") return false;
  if (res.content.some((b) => b.type === "server_tool_use" || String(b.type).endsWith("_tool_result"))) return false;
  const text = res.content.filter((b) => b.type === "text").map((b) => b.text ?? "").join("");
  return !parseNotes(text).parsed;
}

export function toResponse(msg: AIMessage): DeepSeekResponse {
  const meta = (msg.response_metadata ?? {}) as Block;
  const content: Block[] = Array.isArray(msg.content) ? (msg.content as Block[]) : [{ type: "text", text: String(msg.content) }];
  // DeepSeek can answer HTTP 200 with an error body ("The model failed to generate a complete response").
  return { content, usage: meta.usage, stop_reason: meta.stop_reason, ...(meta.type === "error" ? { error: meta.error ?? {} } : {}) };
}

/** `invoke` replaces the model call in tests. */
export async function runDeepSeek(profile: DeepSeekProfile, call: AdapterCall, invoke?: DeepSeekInvoke): Promise<AdapterOutput> {
  const send = invoke ?? deepseekInvoke(profile, call);
  const responses: DeepSeekResponse[] = [];
  const extra: string[] = [];
  let errorRetries = 1;

  /** One model call, recorded in the ledger; an error body is retried once. */
  const ask = async (messages: BaseMessage[], options: { signal: AbortSignal; tool_choice?: "none" }) => {
    for (;;) {
      const msg = await send(messages, options);
      const response = toResponse(msg);
      responses.push(response);
      const { output, cachedInputTokens } = parseDeepSeekResponses([response], profile);
      call.ledger.record(call.role, {
        inputTokens: output.inputTokens,
        outputTokens: output.outputTokens,
        cachedInputTokens,
        searches: output.searches,
        pageReads: output.pageReads,
      });
      if (response.error && errorRetries-- > 0) {
        extra.push(`provider error in a 200 response, retried once: ${errorText(response.error)}`);
        continue;
      }
      return { msg, response };
    }
  };

  let conversation = call.messages;
  let { msg, response } = await ask(conversation, { signal: call.signal });
  if (isAnnouncement(response)) {
    const asked = [...call.messages, msg, new HumanMessage(RESEARCH_REQUEST)];
    let tries = 0;
    while (tries < MAX_RESEARCH_REQUESTS && isAnnouncement(response)) {
      tries += 1;
      ({ msg, response } = await ask(asked, { signal: call.signal }));
    }
    conversation = asked;
    extra.push(
      response.error
        ? `the model only announced its research; follow-up turn ${tries} ended with a provider error`
        : isAnnouncement(response)
          ? `the model only announced its research; ${tries} follow-up turn(s) did not start it`
          : `the model only announced its research; it started after ${tries} follow-up turn(s)`,
    );
  }

  const stoppedWithoutNotes = response.stop_reason === "tool_use" && !parseDeepSeekResponses([response], profile).output.notes;
  if (stoppedWithoutNotes && profile.webSearch.type === "deepseek_web_search") {
    // E9: a follow-up turn after deep search had about 100 input tokens, sent through LangChain or
    // raw, so the model would write the notes from memory. Record the stop and do not continue.
    extra.push(
      "search loop ended with stop_reason tool_use and no notes; not continued, because DeepSeek does not re-read deep-search results in a follow-up turn",
    );
  } else if (stoppedWithoutNotes) {
    // Verified for web_search_20250305: the follow-up turn re-reads the search results.
    try {
      await ask([...conversation, msg, new HumanMessage(NOTES_REQUEST)], { signal: call.signal, tool_choice: "none" });
      extra.push("search loop ended with stop_reason tool_use and no notes; asked once for the notes with tools disabled");
    } catch (err) {
      if (call.signal.aborted) throw err;
      extra.push(`search loop ended with stop_reason tool_use and no notes; the continuation failed: ${String((err as Error)?.message ?? err).slice(0, 300)}`);
    }
  }
  const { output } = parseDeepSeekResponses(responses, profile);
  output.diagnostics.push(...extra);
  return output;
}

function errorText(error: Block): string {
  return `${error.type ?? "error"}: ${String(error.message ?? "").slice(0, 200)}`;
}

const PAGE_ACTIONS = new Set(["open_page", "find_in_page", "read_link"]);

function queriesOf(use: Block | undefined): string[] {
  const input = use?.input ?? {};
  if (Array.isArray(input.queries)) return input.queries.map(String);
  return input.query ? [String(input.query)] : [];
}

/** The error code of a web_search_tool_result, in either the array or the object form. */
function searchError(content: unknown): string | undefined {
  if (!Array.isArray(content)) {
    const code = (content as Block | undefined)?.error_code;
    return code ? String(code) : "malformed_result";
  }
  const err = content.find((r: Block) => r?.error_code);
  return err && !content.some((r: Block) => r?.url) ? String(err.error_code) : undefined;
}

/** Usage of several responses added up, `server_tool_use` counters included. */
function sumUsage(responses: DeepSeekResponse[]): Block {
  const total: Block = {};
  for (const r of responses) {
    for (const [k, v] of Object.entries(r.usage ?? {})) {
      if (typeof v === "number") total[k] = (total[k] ?? 0) + v;
      else if (k === "server_tool_use" && v && typeof v === "object") {
        const counters = (total.server_tool_use ??= {}) as Block;
        for (const [c, n] of Object.entries(v)) if (typeof n === "number") counters[c] = (counters[c] ?? 0) + n;
      }
    }
  }
  return total;
}

/** Turn one Messages API response into the adapter output. Pure, for fixture tests. */
export function parseDeepSeekResponse(res: DeepSeekResponse, profile: DeepSeekProfile): DeepSeekParsed {
  return parseDeepSeekResponses([res], profile);
}

/**
 * All responses of one researcher in order: the first reply, follow-up turns after a reply
 * that only announced its research, error-body retries and the capped mode's continuation.
 * Notes come from the last usable reply; tools, sources and tokens from all of them.
 */
export function parseDeepSeekResponses(responses: DeepSeekResponse[], profile: DeepSeekProfile): DeepSeekParsed {
  const usage = sumUsage(responses);
  const cachedInputTokens = usage.cache_read_input_tokens ?? 0;
  const out: AdapterOutput = {
    notes: "",
    sources: [],
    citedUrls: [],
    queries: [],
    // input_tokens excludes cache hits on this endpoint; the total matches LangChain's usage_metadata.
    inputTokens: (usage.input_tokens ?? 0) + cachedInputTokens + (usage.cache_creation_input_tokens ?? 0),
    outputTokens: usage.output_tokens ?? 0,
    searches: 0,
    pageReads: 0,
    diagnostics: [],
  };

  // Notes are the text the last usable reply wrote after its last tool result; earlier text is narration.
  const final = [...responses].reverse().find((r) => !r.error);
  if (final && !isAnnouncement(final)) {
    const content = final.content ?? [];
    let lastResult = -1;
    content.forEach((b, i) => {
      if (typeof b.type === "string" && b.type.endsWith("_tool_result")) lastResult = i;
    });
    const textBlocks = content.slice(lastResult + 1).filter((b) => b.type === "text");
    out.notes = cleanDeepSeekUrlsInText(textBlocks.map((b) => b.text ?? "").join("")).trim();
  }

  const inputOf = (use: Block | undefined) => JSON.stringify(use?.input ?? null).slice(0, 160);
  const rejected: string[] = [];
  let unanswered: Block[] = [];
  const mismatches: string[] = [];
  let countersMissing = false;

  for (const res of responses) {
    const blocks = res.content ?? [];
    const uses = new Map<string, Block>();
    for (const b of blocks) if (b.type === "server_tool_use" && b.id) uses.set(String(b.id), b);
    const answered = new Set<string>();
    let searchBlocks = 0;
    let fetchBlocks = 0;
    let successfulQueries = 0;

    for (const b of blocks) {
      if (b.type === "web_search_tool_result" || b.type === "web_fetch_tool_result") {
        const use = uses.get(String(b.tool_use_id));
        answered.add(String(b.tool_use_id));
        const action: string = use?.input?.action ?? (b.type === "web_fetch_tool_result" ? "open_page" : "search");
        if (b.type === "web_search_tool_result") {
          searchBlocks += 1;
          const error = searchError(b.content);
          if (error === "max_uses_exceeded") {
            rejected.push(inputOf(use));
            continue;
          }
          if (error) {
            out.diagnostics.push(`web_search error: ${error} for input ${inputOf(use)}`);
            continue;
          }
          const results = (b.content as Block[]).filter((r) => r?.url);
          if (PAGE_ACTIONS.has(action)) out.pageReads += 1;
          else {
            out.searches += 1;
            const queries = queriesOf(use);
            out.queries.push(...queries);
            if (results.length) successfulQueries += queries.length;
          }
          for (const r of results) out.sources.push({ url: cleanDeepSeekUrl(String(r.url)), ...(r.title ? { title: String(r.title) } : {}) });
        } else {
          fetchBlocks += 1;
          const c = b.content ?? {};
          if (c.error_code) {
            out.diagnostics.push(`web_fetch error: ${c.error_code} for input ${inputOf(use)}`);
            continue;
          }
          // Deep search's open_page and find_in_page with url "" act on the page already open:
          // a page read without a new source.
          out.pageReads += 1;
          const title = c.content?.title ?? c.title;
          if (c.url) out.sources.push({ url: cleanDeepSeekUrl(String(c.url)), ...(title ? { title: String(title) } : {}) });
        }
      } else if (b.type === "text" && Array.isArray(b.citations)) {
        for (const c of b.citations) if (c?.url) out.citedUrls.push(cleanDeepSeekUrl(String(c.url)));
      }
    }
    unanswered = [...unanswered, ...[...uses.entries()].filter(([id]) => !answered.has(id)).map(([, u]) => u)];

    // The provider's counters must agree with the blocks; a mismatch means the format changed.
    // An error body carries the counters of work whose blocks were not returned, so it is skipped.
    const counters = res.usage?.server_tool_use as Block | undefined;
    if (res.error) continue;
    if (counters) {
      const check = (name: string, parsed: number) => {
        if (typeof counters[name] === "number" && counters[name] !== parsed) mismatches.push(`${name}=${counters[name]} (parsed ${parsed})`);
      };
      check("web_search_requests", searchBlocks);
      check("web_fetch_requests", fetchBlocks);
      check("tool_search", successfulQueries);
    } else if (searchBlocks + fetchBlocks > 0) countersMissing = true;
  }

  if (unanswered.length) out.diagnostics.push(`${unanswered.length} tool call(s) without a result, e.g. ${inputOf(unanswered[0])}`);
  if (profile.webSearch.type === "deepseek_web_search") {
    const calls = out.searches + out.pageReads;
    out.diagnostics.push(
      `tool-call cap not enforced: deepseek_web_search has no per-researcher limit; ${calls} tool call(s) against a cap of ${profile.toolCallsPerResearcher}`,
    );
  } else if (rejected.length) {
    // DeepSeek also rejected searches beyond the 5th of a request with max_uses=12 (E9).
    out.diagnostics.push(
      `tool cap reached: ${rejected.length} web_search call(s) rejected (max_uses_exceeded) after ${out.searches} executed search(es), max_uses=${profile.webSearch.maxUses}, e.g. ${rejected[0]}`,
    );
  }
  if (mismatches.length) out.diagnostics.push(`usage.server_tool_use disagrees with the response blocks: ${mismatches.join(", ")}`);
  if (countersMissing) out.diagnostics.push("usage.server_tool_use missing although tools ran");

  const last = responses.at(-1);
  if (last?.error) out.diagnostics.push(`provider error in a 200 response: ${errorText(last.error)}`);
  const stop = final?.stop_reason;
  if (stop === "max_tokens") out.diagnostics.push("output truncated at max_tokens");
  else if (stop === "refusal") out.diagnostics.push("the provider refused the request (stop_reason refusal)");
  else if (stop && stop !== "end_turn") out.diagnostics.push(`unexpected stop_reason ${stop}`);

  return { output: out, cachedInputTokens };
}
