/**
 * EBD's model calls through the real OpenAI adapter: LangChain's ChatOpenAI on the
 * Responses API with reasoning, as the platform builds the Luna profile. The network is
 * replaced by replies in the Responses API's shape. EBD has not yet run live on Luna
 * (design section 16.1); this checks EBD's side of the wire, what it sends and that it
 * reads a function call back, not how the model behaves.
 */
import { describe, expect, it } from "vitest";
import { ChatOpenAI } from "@langchain/openai";
import { PLAN_TOOL, runEnvironmentAnalysis, type PlanReply } from "./environment.js";
import { structuredCall } from "./llm.js";
import { CONFLICT_TOOL, conflictsToolSchema } from "./rounds/conflicts.js";

/** The schema the conflict checker is sent for a run without a plan. */
const ConflictsSchema = conflictsToolSchema(false);

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
    tool: { name: CONFLICT_TOOL, description: "Submit the conflicts.", schema: ConflictsSchema },
    check: (args) => {
      const parsed = ConflictsSchema.safeParse(args);
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

  it("runs the environment analysis and accepts a valid plan", async () => {
    const q = (text: string) => ({ text, kind: "social" as const });
    const none = { value: null, basis: "unknown" as const };
    const plan: PlanReply = {
      status: "ok",
      status_reason: null,
      restated_request: "Explain why the town of Ashby closed its public library in 2019.",
      subject: "the closure of Ashby's public library",
      purpose: none,
      time_frame: none,
      place: none,
      directives: [],
      not_stated: [],
      terms: [],
      claims: [{ claim: "The town of Ashby closed its public library in 2019.", verdict: "check", reason: "A particular event with a date." }],
      parts: [
        { name: "The closure", need: "necessary", objective: "Establish whether, when and by whose decision the town of Ashby closed its public library.", questions: [q("Did the town of Ashby close its public library, and on what date?"), q("Which body decided to close the public library of Ashby?"), q("What happened to the building of Ashby's public library after the closure?")], source_hints: ["council minutes"] },
        { name: "Reasons", need: "necessary", objective: "Establish the reasons given for closing the public library of Ashby.", questions: [q("What did the budget of the town of Ashby show for its public library before the closure?"), q("How did use of Ashby's public library change before the closure?"), q("Which alternatives to closing the public library did the council of Ashby consider?")], source_hints: [] },
      ],
    };
    const { model, sent } = lunaWith([[reasoning(), functionCall(PLAN_TOOL, plan)]]);
    const out = await runEnvironmentAnalysis(model, "Why did the town of Ashby close its public library in 2019?", "2026-11-19");
    expect(out).toMatchObject({ accepted: true, fallback: false });
    expect(out.calls).toHaveLength(1);
    expect(out.value!.parts.map((p) => p.name)).toEqual(["The closure", "Reasons"]);
    expect(sent[0]!.body.tools!.map((t) => [t.name, t.strict])).toEqual([[PLAN_TOOL, false]]);
  });
});
