/**
 * Researcher adapter for Anthropic models with the server-side web_search and
 * web_fetch tools. Continues `pause_turn` responses a bounded number of times.
 */
import { ChatAnthropic } from "@langchain/anthropic";
import type { AIMessage, BaseMessage } from "@langchain/core/messages";
import type { AnthropicProfile } from "../../config/models.js";
import { cleanUrl, cleanUrlsInText } from "../../core/urls.js";
import type { AdapterCall, AdapterOutput } from "./types.js";

type Block = Record<string, any>;

export async function runAnthropic(profile: AnthropicProfile, call: AdapterCall): Promise<AdapterOutput> {
  const tools: Record<string, unknown>[] = [
    { type: profile.webSearch.type, name: "web_search", max_uses: profile.webSearch.maxUses },
  ];
  if (profile.webFetch) tools.push({ type: profile.webFetch.type, name: "web_fetch", max_uses: profile.webFetch.maxUses });
  const model = new ChatAnthropic({
    model: profile.model,
    maxTokens: profile.maxOutputTokens,
    maxRetries: 2,
    callbacks: call.callbacks,
  }).bindTools(tools as never);

  const out: AdapterOutput = {
    notes: "",
    sources: [],
    citedUrls: [],
    queries: [],
    inputTokens: 0,
    outputTokens: 0,
    searches: 0,
    pageReads: 0,
    diagnostics: [],
  };
  const blocks: Block[] = [];
  let messages: BaseMessage[] = call.messages;
  let stopReason: string | undefined;

  for (let attempt = 0; attempt <= profile.maxContinuations; attempt++) {
    const msg = (await model.invoke(messages, { signal: call.signal })) as AIMessage;
    const content: Block[] = Array.isArray(msg.content) ? (msg.content as Block[]) : [{ type: "text", text: String(msg.content) }];
    blocks.push(...content);
    const usage = (msg.response_metadata as Block | undefined)?.usage ?? {};
    const searches = usage.server_tool_use?.web_search_requests ?? 0;
    const pageReads = usage.server_tool_use?.web_fetch_requests ?? 0;
    const inputTokens = msg.usage_metadata?.input_tokens ?? 0;
    const outputTokens = msg.usage_metadata?.output_tokens ?? 0;
    call.ledger.record(call.role, { inputTokens, outputTokens, searches, pageReads });
    out.inputTokens += inputTokens;
    out.outputTokens += outputTokens;
    out.searches += searches;
    out.pageReads += pageReads;
    stopReason = (msg.response_metadata as Block | undefined)?.stop_reason;
    if (stopReason !== "pause_turn") break;
    messages = [...messages, msg];
  }
  if (stopReason === "pause_turn") out.diagnostics.push(`still paused after ${profile.maxContinuations} continuations`);
  if (stopReason === "max_tokens") out.diagnostics.push("output truncated at max_tokens");

  // Notes are the text written after the last tool result; earlier text is narration.
  let lastResult = -1;
  blocks.forEach((b, i) => {
    if (typeof b.type === "string" && b.type.endsWith("_tool_result")) lastResult = i;
  });
  const textBlocks = blocks.slice(lastResult + 1).filter((b) => b.type === "text");
  out.notes = cleanUrlsInText(textBlocks.map((b) => b.text ?? "").join("")).trim();

  const inputs = new Map<string, unknown>();
  for (const b of blocks) if (b.type === "server_tool_use" && b.id) inputs.set(b.id, b.input);
  const inputOf = (id: string) => JSON.stringify(inputs.get(id) ?? null).slice(0, 160);

  for (const b of blocks) {
    if (b.type === "server_tool_use") {
      if (b.name === "web_search" && b.input?.query) out.queries.push(String(b.input.query));
    } else if (b.type === "web_search_tool_result") {
      if (Array.isArray(b.content)) {
        for (const r of b.content) if (r?.url) out.sources.push({ url: cleanUrl(r.url), title: r.title });
      } else if (b.content?.error_code) {
        out.diagnostics.push(`web_search error: ${b.content.error_code} for input ${inputOf(b.tool_use_id)}`);
      }
    } else if (b.type === "web_fetch_tool_result") {
      const c = b.content ?? {};
      if (c.error_code) out.diagnostics.push(`web_fetch error: ${c.error_code} for input ${inputOf(b.tool_use_id)}`);
      else if (c.url) out.sources.push({ url: cleanUrl(c.url), title: c.content?.title });
    } else if (b.type === "text" && Array.isArray(b.citations)) {
      for (const c of b.citations) if (c?.url) out.citedUrls.push(cleanUrl(c.url));
    }
  }
  return out;
}
