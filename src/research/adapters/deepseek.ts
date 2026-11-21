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
import { AIMessage, HumanMessage, type BaseMessage } from "@langchain/core/messages";
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

/** The Anthropic SDK refuses larger `max_tokens` values without streaming. */
export const NON_STREAMING_MAX_TOKENS = 21_000;

/** Server-sent events of one response body: event name (if any) and data. Comment lines are skipped. */
export function parseSse(text: string): { event?: string; data: string }[] {
  const events: { event?: string; data: string }[] = [];
  for (const raw of text.split(/\r?\n\r?\n/)) {
    let event: string | undefined;
    const data: string[] = [];
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length) events.push({ ...(event ? { event } : {}), data: data.join("\n") });
  }
  return events;
}

/**
 * Rebuild the Messages API response from DeepSeek's stream, as the non-streaming body
 * would carry it (E9 streaming probe, 2026-11-21):
 * - every block arrives whole in `content_block_start` (server tool inputs and results
 *   included); text, thinking, signatures and citations arrive as deltas;
 * - `message_start.usage` holds only the first prompt; the final `message_delta.usage`
 *   holds the whole call, `server_tool_use` counters included;
 * - a failure arrives as `event: error` with an error body and usage, like the HTTP 200
 *   error body of the non-streaming call.
 * A stream that ends without `message_stop` and without an error is marked as an error too.
 * LangChain's own stream handling cannot be used for this: it drops `web_fetch_tool_result`
 * blocks, replaces server tool inputs with "" and keeps only the first prompt's input tokens.
 */
export function assembleStream(text: string): DeepSeekResponse {
  const content: Block[] = [];
  const partialJson = new Map<number, string>();
  let startUsage: Block | undefined;
  let usage: Block | undefined;
  let stop_reason: string | null | undefined;
  let error: Block | undefined;
  let complete = false;
  for (const { data } of parseSse(text)) {
    let ev: Block;
    try {
      ev = JSON.parse(data) as Block;
    } catch {
      continue;
    }
    const index = Number(ev.index);
    if (ev.type === "message_start") startUsage = ev.message?.usage;
    else if (ev.type === "content_block_start" && ev.content_block) content[index] = structuredClone(ev.content_block);
    else if (ev.type === "content_block_delta" && content[index]) {
      const b = content[index]!;
      const d = (ev.delta ?? {}) as Block;
      if (d.type === "text_delta") b.text = String(b.text ?? "") + String(d.text ?? "");
      else if (d.type === "thinking_delta") b.thinking = String(b.thinking ?? "") + String(d.thinking ?? "");
      else if (d.type === "signature_delta") b.signature = d.signature;
      else if (d.type === "citations_delta" && d.citation) (b.citations ??= []).push(d.citation);
      else if (d.type === "input_json_delta") partialJson.set(index, (partialJson.get(index) ?? "") + String(d.partial_json ?? ""));
    } else if (ev.type === "content_block_stop" && partialJson.has(index) && content[index]) {
      try {
        content[index]!.input = JSON.parse(partialJson.get(index)!);
      } catch {
        // Keep the input from content_block_start.
      }
    } else if (ev.type === "message_delta") {
      if (ev.delta && "stop_reason" in ev.delta) stop_reason = ev.delta.stop_reason;
      if (ev.usage) usage = ev.usage;
    } else if (ev.type === "message_stop") complete = true;
    else if (ev.type === "error") {
      error = ev.error ?? { type: "error" };
      if (ev.usage) usage = ev.usage;
    }
  }
  if (!error && !complete) error = { type: "incomplete_stream", message: "the stream ended before message_stop" };
  return { content: content.filter(Boolean), usage: usage ?? startUsage, stop_reason, ...(error ? { error } : {}) };
}

/**
 * fetch for streamed calls: hands the SDK the same bytes, and keeps a copy of every chunk
 * before the SDK reads it, so the response can be rebuilt even when the SDK stops early
 * (error event, abort). A JSON error body is passed on as in `withErrorBodyContent`.
 */
function recordingStreamFetch(base: typeof fetch | undefined, onResponse: (r: Promise<DeepSeekResponse>) => void): typeof fetch {
  return async (input, init) => {
    const res = await (base ?? globalThis.fetch)(input, init);
    if (res.status !== 200 || !res.body || !(res.headers.get("content-type") ?? "").includes("event-stream")) {
      if (res.status === 200) {
        const body = (await res.clone().json().catch(() => undefined)) as Block | undefined;
        if (body?.type === "error") onResponse(Promise.resolve({ content: [], usage: body.usage, error: body.error ?? {} }));
      }
      return withErrorBodyContent(async () => res)(input, init);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let text = "";
    let finish!: () => void;
    onResponse(new Promise<DeepSeekResponse>((resolve) => (finish = () => resolve(assembleStream(text + decoder.decode())))));
    const copy = new ReadableStream<Uint8Array>({
      async pull(controller) {
        try {
          const { value, done } = await reader.read();
          if (done) {
            finish();
            controller.close();
            return;
          }
          text += decoder.decode(value, { stream: true });
          controller.enqueue(value);
        } catch (err) {
          finish();
          controller.error(err);
        }
      },
      async cancel(reason) {
        finish();
        await reader.cancel(reason).catch(() => undefined);
      },
    });
    const headers = new Headers(res.headers);
    headers.delete("content-length");
    headers.delete("content-encoding");
    return new Response(copy, { status: res.status, statusText: res.statusText, headers });
  };
}

/**
 * The response rebuilt from a stream, in the form `toResponse` reads. A failed stream keeps
 * only its error and usage, like the non-streaming error body: the blocks it streamed
 * before failing belong to a discarded attempt and are not counted as research.
 */
function streamedMessage(r: DeepSeekResponse): AIMessage {
  return new AIMessage({
    content: (r.error ? [] : r.content) as never,
    response_metadata: { usage: r.usage, stop_reason: r.stop_reason, ...(r.error ? { type: "error", error: r.error } : {}) },
  });
}

/**
 * The model call of the researcher; `options` replace the network and the key in tests.
 * Above the SDK's non-streaming limit the call streams, and the reply is rebuilt from the
 * stream (`assembleStream`) instead of LangChain's streamed message.
 */
export function deepseekInvoke(profile: DeepSeekProfile, call: AdapterCall, options: { fetch?: typeof fetch; apiKey?: string } = {}): DeepSeekInvoke {
  const maxTokens = profile.researcherMaxOutputTokens ?? profile.maxOutputTokens;
  const streaming = maxTokens > NON_STREAMING_MAX_TOKENS;
  let streamed: Promise<DeepSeekResponse> | undefined;
  const model = new ChatAnthropic({
    model: profile.model,
    apiKey: options.apiKey ?? deepseekApiKey(),
    anthropicApiUrl: profile.messagesBaseUrl,
    maxTokens,
    // Sent explicitly so a change of DeepSeek's default cannot alter runs; DeepSeek treats adaptive as enabled.
    thinking: { type: "adaptive" },
    outputConfig: { effort: profile.effort },
    // Raw request fields: LangChain's tool formatting rejects the deepseek_* tool types.
    invocationKwargs: { tools: deepseekTools(profile) },
    maxRetries: 2,
    // LangChain's streamed usage covers the first prompt only; the adapter records the real usage.
    ...(streaming ? { streaming: true, streamUsage: false } : {}),
    clientOptions: { fetch: streaming ? recordingStreamFetch(options.fetch, (r) => (streamed = r)) : withErrorBodyContent(options.fetch) },
    callbacks: call.callbacks,
  });
  if (!streaming) return async (messages, opts) => (await model.invoke(messages, opts as never)) as AIMessage;

  return async (messages, opts) => {
    streamed = undefined;
    let failure: unknown;
    try {
      await model.invoke(messages, opts as never);
    } catch (err) {
      failure = err;
    }
    // On abort the SDK ends the stream quietly and LangChain returns what it has; never use that.
    if (opts.signal.aborted) throw opts.signal.reason ?? failure ?? new DOMException("This operation was aborted", "AbortError");
    const pending = streamed as Promise<DeepSeekResponse> | undefined;
    const response = pending ? await pending : undefined;
    // HTTP errors and code errors are thrown as before; an error inside the stream is a reply.
    if (!response || (failure && !response.error)) throw failure ?? new Error("the streamed response was not recorded");
    return streamedMessage(response);
  };
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
