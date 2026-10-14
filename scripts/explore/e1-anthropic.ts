// E1/E2/E3: Anthropic built-in web tools through LangChain.js.
import "dotenv/config";
import { ChatAnthropic } from "@langchain/anthropic";

const version = process.argv[2] ?? "web_search_20260209";
const fetchVersion = process.argv[3] ?? "web_fetch_20260209";
const model = new ChatAnthropic({ model: "claude-haiku-5-5", maxTokens: 8000 });
const tools: Record<string, unknown>[] = [
  { type: version, name: "web_search", max_uses: 3 },
];
if (fetchVersion !== "none") tools.push({ type: fetchVersion, name: "web_fetch", max_uses: 2 });
const bound = model.bindTools(tools as never);
const t0 = Date.now();
try {
  const msg = await bound.invoke(
    "Search the web: what is Environment Based Design (EBD) by Yong Zeng? Give 3 facts, each with its source URL.",
  );
  const content = Array.isArray(msg.content) ? msg.content : [{ type: "text", text: msg.content }];
  const types = content.map((b: any) => b.type);
  const queries = content.filter((b: any) => b.type === "server_tool_use").map((b: any) => `${b.name}: ${JSON.stringify(b.input)}`);
  const results = content.filter((b: any) => String(b.type).endsWith("_tool_result"));
  const citations = content.flatMap((b: any) => (b.citations ?? []).map((c: any) => c.url));
  console.log(JSON.stringify({
    version, fetchVersion, ms: Date.now() - t0,
    blockTypes: types,
    queries,
    resultSummaries: results.map((r: any) => ({ type: r.type, isList: Array.isArray(r.content), n: Array.isArray(r.content) ? r.content.length : undefined, err: Array.isArray(r.content) ? undefined : r.content?.error_code ?? r.content?.type })),
    citations,
    stopReason: (msg.response_metadata as any)?.stop_reason,
    usage: (msg.response_metadata as any)?.usage,
    usageMetadata: msg.usage_metadata,
    textTail: content.filter((b: any) => b.type === "text").map((b: any) => b.text).join("").slice(-400),
  }, null, 1));
} catch (e: any) {
  console.log("ERROR", e?.status, String(e?.message ?? e).slice(0, 600));
}
