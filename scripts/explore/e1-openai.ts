// E1/E2: OpenAI built-in web search through LangChain.js (Responses API).
import "dotenv/config";
import { ChatOpenAI } from "@langchain/openai";

const maxCalls = Number(process.argv[2] ?? 4);
const effort = process.argv[3] ?? "medium";
const model = new ChatOpenAI({
  model: "gpt-6-luna",
  useResponsesApi: true,
  reasoning: { effort: effort as never },
  modelKwargs: { max_tool_calls: maxCalls },
});
const bound = model.bindTools([{ type: "web_search", search_context_size: "medium" } as never]);
const t0 = Date.now();
try {
  const msg = await bound.invoke(
    process.env.Q ?? "Search the web: what is Environment Based Design (EBD) by Yong Zeng? Give 3 facts, each with its source URL.",
    { include: ["web_search_call.action.sources"] } as never,
  );
  const content = Array.isArray(msg.content) ? msg.content : [{ type: "text", text: msg.content }];
  const outputs = ((msg.additional_kwargs as any).tool_outputs ?? []) as any[];
  console.log(JSON.stringify({
    maxCalls, effort, ms: Date.now() - t0,
    blockTypes: content.map((b: any) => b.type),
    annotations: content.flatMap((b: any) => (b.annotations ?? []).map((a: any) => a.url ?? a.type)),
    toolOutputs: outputs.map((o) => ({ type: o.type, status: o.status, action: o.action?.type, queries: o.action?.queries ?? o.action?.query, url: o.action?.url, sources: o.action?.sources?.length })),
    usage: msg.usage_metadata,
    metaKeys: Object.keys(msg.response_metadata ?? {}),
    textTail: content.filter((b: any) => b.type === "text").map((b: any) => b.text).join("").slice(-300),
  }, null, 1));
} catch (e: any) {
  console.log("ERROR", e?.status, String(e?.message ?? e).slice(0, 800));
}
