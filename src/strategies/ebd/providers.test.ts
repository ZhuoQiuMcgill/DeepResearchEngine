/**
 * EBD's model calls through the real OpenAI adapter: LangChain's ChatOpenAI on the
 * Responses API with reasoning, as the platform builds the Luna profile. The network is
 * replaced by replies in the Responses API's shape. EBD has not yet run live on Luna
 * (design section 16.1); this checks EBD's side of the wire, what it sends and that it
 * reads a function call back, not how the model behaves.
 */
import { describe, expect, it } from "vitest";
import { ChatOpenAI } from "@langchain/openai";
import { structuredCall } from "./llm.js";
import { runFixedAnalysis } from "./request/index.js";
import { EXAMPLES } from "./request/examples.js";
import { CONFLICT_TOOL, ConflictsApiSchema } from "./rounds/conflicts.js";

type Sent = { url: string; body: Record<string, unknown> & { tools?: Record<string, unknown>[]; input?: unknown } };

/** A Luna-configured model whose requests are recorded and answered from `replies`, one per call. */
function lunaWith(replies: object[][]) {
  const sent: Sent[] = [];
  const fetch = async (url: string | URL | Request, init?: RequestInit): Promise<Response> => {
    sent.push({ url: String(url), body: JSON.parse(String(init?.body)) });
    const output = replies.shift() ?? [text("(no scripted reply)")];
    const body = {
      id: `resp_${sent.length}`,
      object: "response",
      created_at: 0,
      status: "completed",
      model: "gpt-6-luna",
      output,
      usage: { input_tokens: 1200, output_tokens: 80, total_tokens: 1280, input_tokens_details: { cached_tokens: 0 }, output_tokens_details: { reasoning_tokens: 40 } },
    };
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  };
  const model = new ChatOpenAI({ model: "gpt-6-luna", useResponsesApi: true, reasoning: { effort: "medium" }, maxTokens: 32000, maxRetries: 0, apiKey: "test-key", configuration: { fetch } });
  return { model, sent };
}

const functionCall = (name: string, args: unknown) => ({ type: "function_call", id: "fc_1", call_id: "call_1", name, arguments: JSON.stringify(args), status: "completed" });
const reasoning = () => ({ type: "reasoning", id: "rs_1", summary: [] });
function text(t: string) {
  return { type: "message", id: "msg_1", role: "assistant", status: "completed", content: [{ type: "output_text", text: t, annotations: [] }] };
}

const conflicts = (model: ChatOpenAI) =>
  structuredCall({
    model,
    role: "conflict_checker",
    system: "You are the conflict checker.",
    message: "<new_evidence>(none)</new_evidence>",
    tool: { name: CONFLICT_TOOL, description: "Submit the conflicts.", schema: ConflictsApiSchema },
    check: (args) => {
      const parsed = ConflictsApiSchema.safeParse(args);
      return parsed.success ? { value: parsed.data, errors: [], warnings: [] } : { value: null, errors: [{ code: "schema", path: "", message: parsed.error.message }], warnings: [] };
    },
    fallback: (v) => v,
  });

describe("EBD on the OpenAI adapter (Luna profile, offline)", () => {
  it("sends one unforced, non-strict function tool with reasoning, and reads the function call back", async () => {
    const { model, sent } = lunaWith([[reasoning(), functionCall(CONFLICT_TOOL, { conflicts: [] })]]);
    const out = await conflicts(model);
    expect(out).toMatchObject({ accepted: true, fallback: false, value: { conflicts: [] } });
    expect(sent).toHaveLength(1);
    expect(sent[0]!.url).toMatch(/\/responses$/);
    const body = sent[0]!.body;
    expect(body).toMatchObject({ model: "gpt-6-luna", reasoning: { effort: "medium" } });
    expect(body.tool_choice ?? "auto").toBe("auto");
    expect(body.tools).toHaveLength(1);
    expect(body.tools![0]).toMatchObject({ type: "function", name: CONFLICT_TOOL, strict: false, parameters: { type: "object" } });
    expect((body.tools![0]!.parameters as { required: string[] }).required).toContain("conflicts");
    expect(out.calls[0]).toMatchObject({ inputTokens: 1200, outputTokens: 80, accepted: true });
  });

  it("retries once with the error list when the reply answers in text instead of calling the tool", async () => {
    const { model, sent } = lunaWith([[reasoning(), text("There are no conflicts.")], [functionCall(CONFLICT_TOOL, { conflicts: [] })]]);
    const out = await conflicts(model);
    expect(out.accepted).toBe(true);
    expect(out.calls.map((c) => c.accepted)).toEqual([false, true]);
    expect(out.calls[0]!.errors[0]).toMatchObject({ code: "no_reply" });
    expect(JSON.stringify(sent[1]!.body.input)).toContain("validation_errors");
  });

  it("runs the request analysis in its default mode and accepts a valid analysis", async () => {
    const E1 = EXAMPLES[0]!;
    const { model, sent } = lunaWith([[reasoning(), functionCall("submit_analysis", E1.analysis)]]);
    const out = await runFixedAnalysis({ question: E1.request, today: E1.runDate, model });
    expect(out).toMatchObject({ accepted: true, fallback: false, attempts: 1 });
    expect(out.analysis!.questions.length).toBe(E1.analysis.questions.length);
    expect(sent[0]!.body.tools!.map((t) => [t.name, t.strict])).toEqual([["submit_analysis", false]]);
  });
});
