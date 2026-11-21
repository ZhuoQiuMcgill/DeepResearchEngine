import { readFileSync } from "node:fs";
import { ChatAnthropic } from "@langchain/anthropic";
import { HumanMessage } from "@langchain/core/messages";
import { describe, expect, it } from "vitest";
import { PROFILES, type DeepSeekProfile } from "../src/config/models.js";
import { UsageLedger } from "../src/observability/usage.js";
import {
  RESEARCH_REQUEST,
  assembleStream,
  deepseekInvoke,
  runDeepSeek,
  type DeepSeekResponse,
} from "../src/research/adapters/deepseek.js";

/** The profile streams the researcher (64,000 output tokens); the variant does not (21,000). */
const streaming = PROFILES.deepseek as DeepSeekProfile;
const nonStreaming: DeepSeekProfile = { ...streaming, researcherMaxOutputTokens: undefined };

/**
 * Recorded DeepSeek streams (2026-11-21, scripts/explore/e9-stream.ts), trimmed by merging
 * consecutive deltas of one block, shortening thinking text and search snippets; every
 * other event is kept as recorded. `stream-deep-search`: a complete deep search (26 tool
 * calls). `stream-error`: a stream that ended with `event: error` after 29 s.
 */
const sse = (name: string) => readFileSync(new URL(`./fixtures/deepseek/${name}.sse`, import.meta.url), "utf8");
const json = (name: string) =>
  (JSON.parse(readFileSync(new URL(`./fixtures/deepseek/${name}.json`, import.meta.url), "utf8")) as { response: DeepSeekResponse }).response;
const complete = sse("stream-deep-search");
const errored = sse("stream-error");

/** A reply as DeepSeek streams it, for replies recorded without streaming. */
function toSse(r: DeepSeekResponse): string {
  const ev = (type: string, data: object) => `event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`;
  let out = ev("message_start", { message: { id: "m", type: "message", role: "assistant", model: "deepseek-flash", content: [], usage: { input_tokens: 10, output_tokens: 0 } } });
  r.content.forEach((b, index) => {
    if (b.type === "text") {
      out += ev("content_block_start", { index, content_block: { type: "text", text: "" } });
      out += ev("content_block_delta", { index, delta: { type: "text_delta", text: b.text } });
    } else if (b.type === "thinking") {
      out += ev("content_block_start", { index, content_block: { type: "thinking", thinking: "", signature: "" } });
      out += ev("content_block_delta", { index, delta: { type: "thinking_delta", thinking: b.thinking } });
      out += ev("content_block_delta", { index, delta: { type: "signature_delta", signature: "sig" } });
    } else out += ev("content_block_start", { index, content_block: b });
    out += ev("content_block_stop", { index });
  });
  out += ev("message_delta", { delta: { stop_reason: r.stop_reason, stop_sequence: null }, usage: r.usage });
  return out + ev("message_stop", {});
}

/** A fetch that answers each request with the next body: a string as SSE, an object as JSON. */
function serving(bodies: (string | object | Response)[]) {
  const requests: Record<string, any>[] = [];
  const fetch: typeof globalThis.fetch = async (_input, init) => {
    requests.push(JSON.parse(String(init?.body)));
    const b = bodies.shift();
    if (b instanceof Response) return b;
    if (typeof b === "string") return new Response(b, { status: 200, headers: { "content-type": "text/event-stream" } });
    return new Response(JSON.stringify(b ?? { type: "error", error: { type: "test", message: "no scripted reply" } }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, requests };
}

async function run(profile: DeepSeekProfile, bodies: (string | object | Response)[], signal = new AbortController().signal) {
  const { fetch, requests } = serving(bodies);
  const ledger = new UsageLedger(profile.pricing);
  const call = { messages: [new HumanMessage("brief")], ledger, role: "researcher", signal };
  const out = await runDeepSeek(profile, call, deepseekInvoke(profile, call, { fetch, apiKey: "test-key" }));
  return { out, requests, ledger };
}

const asMessage = (r: DeepSeekResponse) => ({ type: "message", role: "assistant", ...r });

describe("deepseek stream: the reply is rebuilt from the events", () => {
  const r = assembleStream(complete);
  const blocks = (type: string) => r.content.filter((b) => b.type === type);

  it("keeps every block, input and result", () => {
    expect(blocks("thinking")).toHaveLength(9);
    expect(blocks("server_tool_use")).toHaveLength(26);
    expect(blocks("web_search_tool_result")).toHaveLength(5);
    expect(blocks("web_fetch_tool_result")).toHaveLength(21);
    const actions = blocks("server_tool_use").map((b) => b.input.action);
    expect(actions.filter((a) => a === "search")).toHaveLength(5);
    expect(actions.filter((a) => a === "open_page")).toHaveLength(17);
    expect(actions.filter((a) => a === "find_in_page")).toHaveLength(4);
    expect(blocks("server_tool_use").flatMap((b) => b.input.queries ?? [])).toHaveLength(20);
    expect(blocks("web_search_tool_result").flatMap((b) => b.content).filter((x) => x.url)).toHaveLength(157);
    expect(blocks("thinking").every((b) => b.signature === "sig")).toBe(true);
  });

  it("joins the text deltas into the complete notes", () => {
    const text = blocks("text").map((b) => b.text).join("");
    expect(text).toHaveLength(26497);
    expect(text.endsWith("utility function on which its safety guarantee depends.")).toBe(true);
  });

  it("takes the usage of the whole call from message_delta, not message_start", () => {
    expect(r.usage).toMatchObject({ input_tokens: 45174, cache_read_input_tokens: 214144, output_tokens: 25177 });
    expect(r.usage?.server_tool_use).toEqual({ web_search_requests: 5, web_fetch_requests: 21, tool_search: 20, tool_fetch: 2, tool_image_search: 0 });
    expect(r.stop_reason).toBe("end_turn");
    expect(r.error).toBeUndefined();
  });

  it("turns an error event into an error body with its usage", () => {
    const e = assembleStream(errored);
    expect(e.error).toEqual({ type: "api_error", message: "The model failed to generate a complete response. Please retry." });
    expect(e.usage).toMatchObject({ input_tokens: 30620, cache_read_input_tokens: 96640, output_tokens: 2799 });
  });

  it("marks a stream that ends without message_stop as an error", () => {
    const cut = complete.slice(0, complete.indexOf("event: message_delta"));
    expect(assembleStream(cut).error).toEqual({ type: "incomplete_stream", message: "the stream ended before message_stop" });
  });

  it("is needed: LangChain's own streamed message loses blocks, inputs and usage", async () => {
    const { fetch } = serving([complete]);
    const model = new ChatAnthropic({
      model: streaming.model,
      apiKey: "test-key",
      anthropicApiUrl: streaming.messagesBaseUrl,
      maxTokens: 64000,
      streaming: true,
      streamUsage: true,
      maxRetries: 0,
      invocationKwargs: { tools: [{ type: "deepseek_web_search", name: "deepseek_web_search" }] },
      clientOptions: { fetch },
    });
    const msg = await model.invoke("brief");
    const content = msg.content as Record<string, any>[];
    expect(content.filter((b) => b.type === "web_fetch_tool_result")).toHaveLength(0);
    expect(content.filter((b) => b.type === "server_tool_use").every((b) => b.input === "")).toBe(true);
    expect(msg.usage_metadata?.input_tokens).toBe(136 + 1152);
  });
});

describe("deepseek stream: the researcher", () => {
  it("streams above 21,000 tokens and parses exactly like the non-streaming call", async () => {
    const streamed = await run(streaming, [complete]);
    const plain = await run(nonStreaming, [asMessage(assembleStream(complete))]);
    expect(streamed.requests[0]).toMatchObject({ stream: true, max_tokens: 64000 });
    expect(plain.requests[0]).toMatchObject({ max_tokens: 21000 });
    expect(plain.requests[0]!.stream).toBeFalsy();
    expect(streamed.out).toEqual(plain.out);
    expect(streamed.ledger.byRole).toEqual(plain.ledger.byRole);
    const out = streamed.out;
    expect(out.searches).toBe(5);
    expect(out.pageReads).toBe(21);
    expect(out.queries).toHaveLength(20);
    expect(out.notes.endsWith("utility function on which its safety guarantee depends.")).toBe(true);
    expect(out.inputTokens).toBe(45174 + 214144);
    expect(out.outputTokens).toBe(25177);
    expect(out.diagnostics).toEqual(["tool-call cap not enforced: deepseek_web_search has no per-researcher limit; 26 tool call(s) against a cap of 12"]);
    expect(streamed.ledger.byRole.researcher).toMatchObject({ calls: 1, cachedInputTokens: 214144, searches: 5, pageReads: 21 });
  });

  it("retries an error event once and counts its tokens", async () => {
    const { out, ledger } = await run(streaming, [errored, complete]);
    expect(out.notes.endsWith("guarantee depends.")).toBe(true);
    expect(out.searches).toBe(5);
    expect(out.inputTokens).toBe(30620 + 96640 + 45174 + 214144);
    expect(out.diagnostics).toContain("provider error in a 200 response, retried once: api_error: The model failed to generate a complete response. Please retry.");
    expect(ledger.byRole.researcher?.calls).toBe(2);
  });

  it("leaves no notes when the error event comes twice", async () => {
    const { out } = await run(streaming, [errored, errored]);
    expect(out.notes).toBe("");
    expect(out.diagnostics).toContain("provider error in a 200 response: api_error: The model failed to generate a complete response. Please retry.");
  });

  it("retries a stream cut before message_stop", async () => {
    const cut = complete.slice(0, complete.indexOf("event: message_delta"));
    const { out } = await run(streaming, [cut, complete]);
    expect(out.notes.endsWith("guarantee depends.")).toBe(true);
    expect(out.diagnostics).toContain("provider error in a 200 response, retried once: incomplete_stream: the stream ended before message_stop");
  });

  it("still catches a JSON error body", async () => {
    const { out } = await run(streaming, [json("error-body") as object, complete]);
    expect(out.notes.endsWith("guarantee depends.")).toBe(true);
    expect(out.diagnostics).toContain("provider error in a 200 response, retried once: api_error: The model failed to generate a complete response. Please retry.");
  });

  it("sends the follow-up turn after an announcement, with the rebuilt reply in the history", async () => {
    const { out, requests } = await run(streaming, [toSse(json("announcement")), complete]);
    expect(requests).toHaveLength(2);
    const history = requests[1]!.messages as { role: string; content: any }[];
    expect(history.map((m) => m.role)).toEqual(["user", "assistant", "user"]);
    expect(history[1]!.content.map((b: { type: string }) => b.type)).toEqual(["thinking", "text"]);
    expect(history[1]!.content[0].signature).toBe("sig");
    expect(JSON.stringify(history[2]!.content)).toContain(RESEARCH_REQUEST);
    expect(out.notes.endsWith("guarantee depends.")).toBe(true);
    expect(out.diagnostics).toContain("the model only announced its research; it started after 1 follow-up turn(s)");
  });

  it("throws on abort instead of returning the partial stream", async () => {
    const controller = new AbortController();
    const head = complete.slice(0, complete.indexOf("event: content_block_start", 2000));
    const stalled = (_input: unknown, init?: RequestInit) => {
      const body = new ReadableStream<Uint8Array>({
        start(c) {
          c.enqueue(new TextEncoder().encode(head));
          init?.signal?.addEventListener("abort", () => c.error(new DOMException("This operation was aborted", "AbortError")));
        },
      });
      return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
    };
    setTimeout(() => controller.abort(new DOMException("The operation timed out.", "TimeoutError")), 100);
    const ledger = new UsageLedger(streaming.pricing);
    const call = { messages: [new HumanMessage("brief")], ledger, role: "researcher", signal: controller.signal };
    const fetch = (async (input: unknown, init?: RequestInit) => stalled(input, init)) as typeof globalThis.fetch;
    await expect(runDeepSeek(streaming, call, deepseekInvoke(streaming, call, { fetch, apiKey: "test-key" }))).rejects.toMatchObject({ name: "TimeoutError" });
    expect(ledger.byRole.researcher).toBeUndefined();
  });

  it("throws HTTP errors as before", async () => {
    const bad = new Response(JSON.stringify({ type: "error", error: { type: "invalid_request_error", message: "bad request" } }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
    await expect(run(streaming, [bad])).rejects.toMatchObject({ status: 400 });
  });
});
