/**
 * Researcher adapter for OpenAI models with the Responses API web_search tool.
 * The tool-call cap is passed as `max_tool_calls`.
 */
import { ChatOpenAI } from "@langchain/openai";
import type { AIMessage } from "@langchain/core/messages";
import type { OpenAIProfile } from "../../config/models.js";
import { cleanUrl, cleanUrlsInText } from "../../core/urls.js";
import type { AdapterCall, AdapterOutput } from "./types.js";

type Block = Record<string, any>;

export async function runOpenAI(profile: OpenAIProfile, call: AdapterCall): Promise<AdapterOutput> {
  const model = new ChatOpenAI({
    model: profile.model,
    useResponsesApi: true,
    reasoning: { effort: profile.reasoningEffort },
    maxTokens: profile.maxOutputTokens,
    maxRetries: 2,
    modelKwargs: { max_tool_calls: profile.webSearch.maxToolCalls },
    callbacks: call.callbacks,
  }).bindTools([{ type: "web_search", search_context_size: profile.webSearch.searchContextSize } as never]);

  const msg = (await model.invoke(call.messages, {
    signal: call.signal,
    include: ["web_search_call.action.sources"],
  } as never)) as AIMessage;

  const content: Block[] = Array.isArray(msg.content) ? (msg.content as Block[]) : [{ type: "text", text: String(msg.content) }];
  const outputs: Block[] = ((msg.additional_kwargs as Block)?.tool_outputs ?? []) as Block[];
  const out: AdapterOutput = {
    notes: cleanUrlsInText(content.filter((b) => b.type === "text").map((b) => b.text ?? "").join("")).trim(),
    sources: [],
    citedUrls: [],
    queries: [],
    inputTokens: msg.usage_metadata?.input_tokens ?? 0,
    outputTokens: msg.usage_metadata?.output_tokens ?? 0,
    searches: 0,
    pageReads: 0,
    diagnostics: [],
  };

  let unfinished = 0;
  for (const o of outputs) {
    if (o.type !== "web_search_call") continue;
    const action = o.action ?? {};
    if (o.status !== "completed") {
      unfinished += 1;
      continue;
    }
    if (action.type === "search") {
      out.searches += 1;
      for (const q of action.queries ?? (action.query ? [action.query] : [])) out.queries.push(String(q));
      for (const s of action.sources ?? []) if (s?.url) out.sources.push({ url: cleanUrl(s.url) });
    } else if (action.type === "open_page" || action.type === "find_in_page") {
      out.pageReads += 1;
      if (action.url) out.sources.push({ url: cleanUrl(action.url) });
    }
  }
  for (const b of content) {
    for (const a of b.annotations ?? []) {
      if (a?.url) {
        out.citedUrls.push(cleanUrl(a.url));
        out.sources.push({ url: cleanUrl(a.url), title: a.title });
      }
    }
  }
  if (unfinished) out.diagnostics.push(`tool cap reached: ${unfinished} web_search call(s) not executed`);
  const meta = msg.response_metadata as Block | undefined;
  if (meta?.status === "incomplete") out.diagnostics.push(`response incomplete: ${JSON.stringify(meta.incomplete_details ?? {})}`);

  call.ledger.record(call.role, {
    inputTokens: out.inputTokens,
    outputTokens: out.outputTokens,
    searches: out.searches,
    pageReads: out.pageReads,
  });
  return out;
}
