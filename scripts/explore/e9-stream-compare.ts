// E9: check a streamed live replay against the non-streaming path on the same responses.
//   npx tsx scripts/explore/e9-stream-compare.ts <tag> <brief id>
// Reads the bodies e9-replay-brief.ts recorded (local/explore-deepseek/replay-<tag>-<brief>-*),
// then parses the same responses three ways and compares them:
//   live      the adapter output saved by the replay;
//   streamed  the recorded SSE served again to the streaming researcher;
//   plain     each recorded stream rebuilt into a JSON body and served to the non-streaming researcher.
import { readdirSync, readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";
import { HumanMessage } from "@langchain/core/messages";
import { PROFILES, type DeepSeekProfile } from "../../src/config/models.js";
import { UsageLedger } from "../../src/observability/usage.js";
import { assembleStream, deepseekInvoke, runDeepSeek } from "../../src/research/adapters/deepseek.js";

const [tag, briefId] = process.argv.slice(2);
if (!tag || !briefId) throw new Error("usage: e9-stream-compare.ts <tag> <brief id>");
const dir = "local/explore-deepseek";
const prefix = `replay-${tag}-${briefId}-`;
const calls = readdirSync(dir)
  .filter((f) => f.startsWith(prefix) && /-\d+-\d+\.json$/.test(f))
  .sort((a, b) => Number(a.match(/-(\d+)\.json$/)![1]) - Number(b.match(/-(\d+)\.json$/)![1]))
  .map((f) => JSON.parse(readFileSync(`${dir}/${f}`, "utf8")) as { request: { stream?: boolean; max_tokens?: number }; response: unknown });
const live = JSON.parse(readFileSync(`${dir}/${prefix}output.json`, "utf8")) as { output: unknown; ledger: unknown };

const streaming = PROFILES.deepseek as DeepSeekProfile;
const nonStreaming: DeepSeekProfile = { ...streaming, researcherMaxOutputTokens: undefined };

async function serve(profile: DeepSeekProfile, bodies: (string | object)[]) {
  const fetch = (async () => {
    const b = bodies.shift();
    return typeof b === "string"
      ? new Response(b, { status: 200, headers: { "content-type": "text/event-stream" } })
      : new Response(JSON.stringify(b), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof globalThis.fetch;
  const ledger = new UsageLedger(profile.pricing);
  const call = { messages: [new HumanMessage("brief")], ledger, role: "researcher", signal: new AbortController().signal };
  const output = await runDeepSeek(profile, call, deepseekInvoke(profile, call, { fetch, apiKey: "test-key" }));
  return { output, ledger: ledger.byRole };
}

const sse = calls.map((c) => (typeof c.response === "string" ? c.response : JSON.stringify(c.response)));
const streamed = await serve(streaming, [...sse]);
const plain = await serve(
  nonStreaming,
  calls.map((c) => (typeof c.response === "string" ? { type: "message", role: "assistant", ...assembleStream(c.response) } : (c.response as object))),
);
const o = streamed.output as { notes: string; searches: number; pageReads: number; queries: string[]; sources: unknown[]; citedUrls: string[]; inputTokens: number; outputTokens: number; diagnostics: string[] };
console.log(
  JSON.stringify({
    calls: calls.map((c) => ({ stream: c.request.stream ?? false, max_tokens: c.request.max_tokens, sse: typeof c.response === "string" })),
    liveEqualsStreamed: isDeepStrictEqual(live.output, streamed.output) && isDeepStrictEqual(live.ledger, streamed.ledger),
    streamedEqualsPlain: isDeepStrictEqual(streamed.output, plain.output) && isDeepStrictEqual(streamed.ledger, plain.ledger),
    summary: { notes: o.notes.length, searches: o.searches, pageReads: o.pageReads, queries: o.queries.length, sources: o.sources.length, citedUrls: o.citedUrls.length, inputTokens: o.inputTokens, outputTokens: o.outputTokens, diagnostics: o.diagnostics },
    lastStream: sse.length && typeof calls.at(-1)!.response === "string" ? { stop: assembleStream(sse.at(-1)!).stop_reason, outputTokens: assembleStream(sse.at(-1)!).usage?.output_tokens } : null,
  }),
);
