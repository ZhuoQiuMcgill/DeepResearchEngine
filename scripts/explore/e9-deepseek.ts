// E9: DeepSeek web tools and structured output through LangChain.js.
//   npx tsx scripts/explore/e9-deepseek.ts <probe> [model]
// Probes go to the Anthropic-compatible endpoint with ChatAnthropic. Raw
// response bodies are saved under local/explore-deepseek/ (ignored by Git)
// for fixtures; request headers, which carry the key, are never saved.
import "dotenv/config";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { ChatAnthropic } from "@langchain/anthropic";
import { ChatOpenAI } from "@langchain/openai";
import { AIMessage, HumanMessage, SystemMessage } from "@langchain/core/messages";
import { z } from "zod";

const probe = process.argv[2] ?? "ping";
const modelId = process.argv[3] ?? "deepseek-flash";
const key = process.env.DEEPSEEK_API_KEY ?? "";
if (!key) throw new Error("DEEPSEEK_API_KEY is not set");
const redact = (s: string) => (key ? s.split(key).join("<redacted>") : s);
const outDir = "local/explore-deepseek";
mkdirSync(outDir, { recursive: true });
let n = 0;

/** fetch that saves request and response bodies (never headers). */
const recordingFetch: typeof fetch = async (input, init) => {
  const res = await fetch(input, init);
  const text = await res.clone().text();
  const file = `${outDir}/${probe}-${modelId}-${process.argv[5] ?? "x"}-${process.pid}-${++n}.json`;
  let body: unknown = text;
  try {
    body = JSON.parse(text);
  } catch {}
  let request: unknown = init?.body;
  try {
    request = JSON.parse(String(init?.body));
  } catch {}
  writeFileSync(file, redact(JSON.stringify({ url: String(input), status: res.status, request, response: body }, null, 1)));
  return res;
};

function anthropic(extra: Record<string, unknown> = {}) {
  return new ChatAnthropic({
    model: modelId,
    apiKey: key,
    anthropicApiUrl: "https://api.deepseek.com/anthropic",
    maxTokens: 21000,
    maxRetries: 0,
    clientOptions: { fetch: recordingFetch },
    ...extra,
  });
}

function summarize(msg: any) {
  const content: any[] = Array.isArray(msg.content) ? msg.content : [{ type: "text", text: msg.content }];
  return {
    blockTypes: content.map((b) => b.type),
    toolUses: content
      .filter((b) => b.type === "server_tool_use")
      .map((b) => ({ name: b.name, kind: b.kind, input: b.input })),
    results: content
      .filter((b) => String(b.type).endsWith("_tool_result"))
      .map((b) => ({
        type: b.type,
        kind: b.kind,
        n: Array.isArray(b.content) ? b.content.length : undefined,
        err: Array.isArray(b.content) ? undefined : b.content?.error_code,
        url: Array.isArray(b.content) ? undefined : b.content?.url,
      })),
    citations: content.flatMap((b) => (b.citations ?? []).map((c: any) => `${c.type} ${c.url}`)),
    stopReason: msg.response_metadata?.stop_reason,
    usage: msg.response_metadata?.usage,
    usageMetadata: msg.usage_metadata,
    textTail: content
      .filter((b) => b.type === "text")
      .map((b) => b.text)
      .join("")
      .slice(-500),
  };
}

const RESEARCH =
  "Research with web search: what is Environment Based Design (EBD) by Yong Zeng, and what are its three main activities? " +
  "Search at least three times with different queries. Give 4 facts, each with its source URL.";
// Asks for more searches than the observed limit, one per step, to find where rejection starts.
const MANY =
  "Use web search exactly 10 times, one query per step, each on a different subtopic of Environment Based Design (EBD) by Yong Zeng: " +
  "origin, ROM, environment analysis, conflict identification, solution generation, design governing equation, applications, " +
  "criticism, recent papers, related methods. Then list each query with one finding and its URL.";

const t0 = Date.now();
try {
  if (probe === "ping") {
    const msg = await anthropic({ outputConfig: { effort: "high" } }).invoke("Reply with the single word: pong");
    console.log(JSON.stringify(summarize(msg), null, 1));
  } else if (probe === "ws-maxuses") {
    // Anthropic tool type with max_uses: is the cap enforced?
    const cap = Number(process.argv[4] ?? 2);
    const type = process.argv[5] ?? "web_search_20250305";
    const thinking = process.argv[7] === "off" ? { thinking: { type: "disabled" } } : {};
    const m = anthropic({ outputConfig: { effort: "high" }, ...thinking }).bindTools([{ type, name: "web_search", max_uses: cap }] as never);
    const msg = await m.invoke(process.argv[6] === "many" ? MANY : RESEARCH);
    console.log(JSON.stringify({ cap, type, ...summarize(msg) }, null, 1));
  } else if (probe === "ds-search") {
    // Native deepseek_web_search, thinking on (default) or off.
    const thinking = process.argv[4] ?? "default";
    const maxUses = process.argv[5] ? { max_uses: Number(process.argv[5]) } : {};
    const extra: Record<string, unknown> = {
      outputConfig: { effort: "high" },
      invocationKwargs: { tools: [{ type: "deepseek_web_search", name: "deepseek_web_search", ...maxUses }] },
    };
    if (thinking === "off") extra.thinking = { type: "disabled" };
    const msg = await anthropic(extra).invoke(RESEARCH);
    console.log(JSON.stringify({ thinking, ...summarize(msg) }, null, 1));
  } else if (probe === "ws-fetch") {
    // Haiku-like pair: web_search_20250305 + web_fetch_20250910.
    const m = anthropic({ outputConfig: { effort: "high" } }).bindTools([
      { type: "web_search_20250305", name: "web_search", max_uses: 3 },
      { type: "web_fetch_20250910", name: "web_fetch", max_uses: 2 },
    ] as never);
    const msg = await m.invoke(RESEARCH);
    console.log(JSON.stringify(summarize(msg), null, 1));
  } else if (probe === "structured") {
    // Baseline path: withStructuredOutput(schema, { method: "jsonSchema", name }).
    const Plan = z.object({
      rationale: z.string(),
      briefs: z.array(z.object({ objective: z.string(), keyQuestions: z.array(z.string()) })).describe("1-3 briefs"),
    });
    const m = anthropic({ outputConfig: { effort: "high" } });
    const s = m.withStructuredOutput(Plan, { method: "jsonSchema", name: "research_plan", includeRaw: true });
    const out: any = await s.invoke("Decompose into 2 research briefs: compare meta quest 3 and apple vision pro");
    console.log(JSON.stringify({ parsed: out.parsed, raw: summarize(out.raw) }, null, 1));
  } else if (probe === "submit-tool") {
    // EBD path: unforced OpenAI-format submit tool, not strict.
    const tool = {
      type: "function",
      strict: false,
      function: {
        name: "submit_plan",
        description: "Submit the plan.",
        strict: false,
        parameters: {
          type: "object",
          properties: {
            items: { type: "array", items: { type: "object", properties: { id: { type: "string" }, kind: { type: "string", enum: ["object", "relation"] } }, required: ["id", "kind"] } },
          },
          required: ["items"],
        },
      },
    };
    const m = anthropic({ outputConfig: { effort: "high" } }).bindTools([tool] as never);
    const msg: any = await m.invoke([
      new SystemMessage("You analyse questions. Always answer by calling submit_plan."),
      new HumanMessage("List two objects and one relation in: What is EBD (Environment Based Design)?"),
    ]);
    console.log(JSON.stringify({ toolCalls: msg.tool_calls, ...summarize(msg) }, null, 1));
  } else if (probe === "resp-search") {
    // Responses API with deepseek_web_search: is max_tool_calls enforced?
    const cap = process.argv[4] ? Number(process.argv[4]) : undefined;
    const effort = process.argv[5] ?? "high";
    const m = new ChatOpenAI({
      model: modelId,
      apiKey: key,
      configuration: { baseURL: "https://api.deepseek.com", fetch: recordingFetch },
      maxRetries: 0,
      useResponsesApi: true,
      modelKwargs: { reasoning: { effort } },
      maxTokens: 32000,
      ...(cap !== undefined ? { modelKwargs: { reasoning: { effort }, max_tool_calls: cap } } : {}),
    }).bindTools([{ type: "deepseek_web_search" } as never]);
    const msg: any = await m.invoke(RESEARCH, { include: ["web_search_call.action.sources"] } as never);
    const outputs: any[] = msg.additional_kwargs?.tool_outputs ?? [];
    const content: any[] = Array.isArray(msg.content) ? msg.content : [{ type: "text", text: msg.content }];
    console.log(
      JSON.stringify(
        {
          cap,
          effort,
          calls: outputs.map((o) => ({ type: o.type, kind: o.kind, status: o.status, action: { ...o.action, sources: o.action?.sources?.length } })),
          annotations: content.flatMap((b) => (b.annotations ?? []).map((a: any) => `${a.type} ${a.url}`)),
          meta: { status: msg.response_metadata?.status, incomplete: msg.response_metadata?.incomplete_details, usage: msg.response_metadata?.usage },
          usageMetadata: msg.usage_metadata,
          textTail: content.filter((b) => b.type === "text").map((b) => b.text).join("").slice(-400),
        },
        null,
        1,
      ),
    );
  } else if (probe === "resp-submit-tool") {
    // EBD path on the Responses route: unforced OpenAI-format submit tool.
    const tool = {
      type: "function",
      strict: false,
      function: {
        name: "submit_plan",
        description: "Submit the plan.",
        strict: false,
        parameters: {
          type: "object",
          properties: {
            items: { type: "array", items: { type: "object", properties: { id: { type: "string" }, kind: { type: "string", enum: ["object", "relation"] } }, required: ["id", "kind"] } },
          },
          required: ["items"],
        },
      },
    };
    const m = new ChatOpenAI({
      model: modelId,
      apiKey: key,
      configuration: { baseURL: "https://api.deepseek.com", fetch: recordingFetch },
      maxRetries: 0,
      useResponsesApi: true,
      modelKwargs: { reasoning: { effort: "high" } },
    }).bindTools([tool] as never);
    const msg: any = await m.invoke([
      new SystemMessage("You analyse questions. Always answer by calling submit_plan."),
      new HumanMessage("List two objects and one relation in: What is EBD (Environment Based Design)?"),
    ]);
    console.log(JSON.stringify({ toolCalls: msg.tool_calls, usage: msg.usage_metadata, meta: msg.response_metadata?.usage }, null, 1));
  } else if (probe === "continue") {
    // Continue a recorded researcher reply that stopped with stop_reason tool_use:
    //   continue <model> <recorded file> user|assistant
    const rec = JSON.parse(readFileSync(process.argv[4]!, "utf8"));
    const mode = process.argv[5] ?? "user";
    const system = typeof rec.request.system === "string" ? rec.request.system : (rec.request.system ?? []).map((b: any) => b.text).join("");
    const history = [
      ...(system ? [new SystemMessage(system)] : []),
      ...rec.request.messages.map((m: any) => new HumanMessage({ content: m.content })),
      new AIMessage({ content: rec.response.content }),
      ...(mode === "user"
        ? [new HumanMessage("Your search budget is used up. Write your notes now from the results above, in the required format.")]
        : []),
    ];
    const m = anthropic({
      outputConfig: { effort: "high" },
      thinking: { type: "adaptive" },
      invocationKwargs: { tools: rec.request.tools },
    });
    const msg: any = await m.invoke(history, { tool_choice: "none" } as never);
    console.log(JSON.stringify({ mode, ...summarize(msg) }, null, 1));
  } else if (probe === "replay-raw") {
    // Re-post a recorded researcher request with another thinking setting:
    //   replay-raw <model> <recorded file> enabled|adaptive|omit|max|nudge
    // "max": adaptive thinking at effort max. "nudge": the recorded reply plus a user turn asking to go on.
    const rec = JSON.parse(readFileSync(process.argv[4]!, "utf8"));
    const mode = process.argv[5] ?? "enabled";
    const { thinking: _t, ...rest } = rec.request;
    const body = {
      ...rest,
      ...(mode === "enabled" ? { thinking: { type: "enabled", budget_tokens: 16000 } } : mode === "omit" ? {} : { thinking: { type: "adaptive" } }),
      ...(mode === "max" ? { output_config: { effort: "max" } } : {}),
      ...(mode === "suffix"
        ? {
            system:
              (typeof rec.request.system === "string" ? rec.request.system : rec.request.system.map((b: any) => b.text).join("")) +
              "\n\nStart your research with the web search tool right away. Write no text before your research is done; your only text is the final notes.",
          }
        : {}),
      ...(mode === "nudge"
        ? {
            messages: [
              ...rec.request.messages,
              { role: "assistant", content: rec.response.content },
              { role: "user", content: "Go ahead with your research now." },
            ],
          }
        : {}),
    };
    const res = await recordingFetch("https://api.deepseek.com/anthropic/v1/messages", {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" },
      body: JSON.stringify(body),
    });
    const json: any = await res.json();
    const blocks: any[] = json.content ?? [];
    console.log(
      JSON.stringify({
        mode,
        status: res.status,
        stop: json.stop_reason,
        usage: json.usage,
        toolUses: blocks.filter((b) => b.type === "server_tool_use").length,
        textHead: blocks.filter((b) => b.type === "text").map((b) => b.text).join("").slice(0, 120),
        error: json.error,
      }),
    );
  } else if (probe === "replay-responses") {
    // The same recorded researcher request on the Responses endpoint with deepseek_web_search.
    const rec = JSON.parse(readFileSync(process.argv[4]!, "utf8"));
    const text = (c: any) => (typeof c === "string" ? c : (c ?? []).map((b: any) => b.text ?? "").join(""));
    const body = {
      model: modelId,
      instructions: text(rec.request.system),
      input: rec.request.messages.map((m: any) => ({ role: m.role, content: text(m.content) })),
      tools: [{ type: "deepseek_web_search" }],
      reasoning: { effort: "high" },
      max_output_tokens: 21000,
    };
    const res = await recordingFetch("https://api.deepseek.com/responses", {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${key}` },
      body: JSON.stringify(body),
    });
    const json: any = await res.json();
    const out: any[] = json.output ?? [];
    const calls = out.filter((o) => o.type === "web_search_call");
    console.log(
      JSON.stringify({
        status: res.status,
        respStatus: json.status,
        incomplete: json.incomplete_details,
        usage: json.usage,
        calls: calls.length,
        actions: calls.map((c) => c.action?.type).join(","),
        textHead: out.filter((o) => o.type === "message").flatMap((o) => o.content ?? []).map((c: any) => c.text ?? "").join("").slice(0, 120),
        error: json.error,
      }),
    );
  } else if (probe === "continue-raw") {
    // As "continue user", but posted without LangChain so every block of the reply is sent back.
    const rec = JSON.parse(readFileSync(process.argv[4]!, "utf8"));
    const body = {
      model: modelId,
      max_tokens: 21000,
      thinking: { type: "adaptive" },
      output_config: { effort: "high" },
      tools: rec.request.tools,
      tool_choice: { type: "none" },
      ...(rec.request.system ? { system: rec.request.system } : {}),
      messages: [
        ...rec.request.messages,
        { role: "assistant", content: rec.response.content },
        { role: "user", content: "The search tool is no longer available. Write your notes now from the results above, in the required format." },
      ],
    };
    const res = await recordingFetch("https://api.deepseek.com/anthropic/v1/messages", {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" },
      body: JSON.stringify(body),
    });
    const json: any = await res.json();
    console.log(JSON.stringify({ status: res.status, usage: json.usage, stop: json.stop_reason, error: json.error, textTail: (json.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("").slice(-600) }, null, 1));
  } else if (probe === "openai-structured") {
    // Fallback route: ChatOpenAI on Chat Completions with jsonSchema.
    const Plan = z.object({ rationale: z.string(), briefs: z.array(z.object({ objective: z.string() })) });
    const m = new ChatOpenAI({
      model: modelId,
      apiKey: key,
      configuration: { baseURL: "https://api.deepseek.com", fetch: recordingFetch },
      maxRetries: 0,
      ...(process.argv[4] === "responses" ? { useResponsesApi: true } : {}),
    });
    const out: any = await m
      .withStructuredOutput(Plan, { method: "jsonSchema", name: "research_plan", includeRaw: true })
      .invoke("Decompose into 2 research briefs: compare meta quest 3 and apple vision pro");
    console.log(JSON.stringify({ parsed: out.parsed }, null, 1));
  } else {
    throw new Error(`unknown probe ${probe}`);
  }
  console.log(`${probe} ${modelId} ok in ${Date.now() - t0} ms`);
} catch (e: any) {
  console.log(`${probe} ${modelId} ERROR after ${Date.now() - t0} ms`, e?.status ?? "", redact(String(e?.message ?? e)).slice(0, 1500));
}
