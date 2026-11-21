// E9: what DeepSeek's Messages endpoint streams for a deep-search researcher request.
//   npx tsx scripts/explore/e9-stream.ts <recorded request file> <tag> [max_tokens]
// Posts the recorded request again with stream: true (no LangChain) and saves the raw
// SSE text under local/explore-deepseek/sse-<tag>.txt. Headers, which carry the key,
// are never saved.
import "dotenv/config";
import { readFileSync, writeFileSync } from "node:fs";

const [file, tag = "x", maxTokens = "64000"] = process.argv.slice(2);
if (!file) throw new Error("usage: e9-stream.ts <recorded request file> <tag> [max_tokens]");
const key = process.env.DEEPSEEK_API_KEY ?? "";
if (!key) throw new Error("DEEPSEEK_API_KEY is not set");
const redact = (s: string) => s.split(key).join("<redacted>");

const rec = JSON.parse(readFileSync(file, "utf8")) as { request: Record<string, unknown> };
const body = { ...rec.request, stream: true, max_tokens: Number(maxTokens) };
const t0 = Date.now();
const res = await fetch("https://api.deepseek.com/anthropic/v1/messages", {
  method: "POST",
  headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" },
  body: JSON.stringify(body),
});
const text = await res.text();
writeFileSync(`local/explore-deepseek/sse-${tag}.txt`, redact(text));

// Summarise the events.
const counts: Record<string, number> = {};
const starts: Record<string, number> = {};
const deltas: Record<string, number> = {};
let messageStartUsage: unknown;
let messageDeltaUsage: unknown;
let messageDelta: unknown;
let last = "";
const unnamed: string[] = [];
for (const raw of text.split(/\r?\n\r?\n/)) {
  const lines = raw.split(/\r?\n/);
  const event = lines.find((l) => l.startsWith("event:"))?.slice(6).trim();
  const data = lines.filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("\n");
  if (!data) continue;
  let json: any;
  try {
    json = JSON.parse(data);
  } catch {
    unnamed.push(data.slice(0, 200));
    continue;
  }
  const type = String(json.type);
  if (!event) unnamed.push(data.slice(0, 300));
  counts[type] = (counts[type] ?? 0) + 1;
  last = type;
  if (type === "message_start") messageStartUsage = json.message?.usage;
  if (type === "message_delta") {
    messageDeltaUsage = json.usage;
    messageDelta = json.delta;
  }
  if (type === "content_block_start") starts[json.content_block?.type] = (starts[json.content_block?.type] ?? 0) + 1;
  if (type === "content_block_delta") deltas[json.delta?.type] = (deltas[json.delta?.type] ?? 0) + 1;
}
console.log(
  JSON.stringify(
    { status: res.status, contentType: res.headers.get("content-type"), ms: Date.now() - t0, bytes: text.length, counts, starts, deltas, messageStartUsage, messageDeltaUsage, messageDelta, last, unnamed: unnamed.slice(0, 3) },
    null,
    1,
  ),
);
