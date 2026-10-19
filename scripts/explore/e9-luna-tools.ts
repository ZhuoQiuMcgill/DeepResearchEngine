// E9: can the strategy model (Luna, Responses API) run a tool loop with strict custom
// function tools and OpenAI's built-in code interpreter in the same call?
import "dotenv/config";
import { z } from "zod";
import { tool } from "@langchain/core/tools";
import { AIMessage, HumanMessage, ToolMessage, type BaseMessage } from "@langchain/core/messages";
import { createChatModel, getProfile } from "../../src/config/models.js";

const roundStatus = tool(async () => JSON.stringify({ researchers: [{ id: "r1-b1", searches: 9, inputTokens: 41000 }, { id: "r1-b2", searches: 12, inputTokens: 52000 }] }), {
  name: "get_round_status",
  description: "Usage of each researcher in the round just finished.",
  schema: z.object({}).strict(),
});
const finish = tool(async ({ reason }) => `stopped: ${reason}`, {
  name: "finish_research",
  description: "Stop the research.",
  schema: z.object({ reason: z.string() }).strict(),
});

const model = createChatModel(getProfile("luna"));
const bound = model.bindTools!([roundStatus, finish, { type: "code_interpreter", container: { type: "auto" } }], { strict: true, include: ["code_interpreter_call.outputs"] } as any);
const messages: BaseMessage[] = [new HumanMessage(
  "Call get_round_status, then use the code interpreter to compute the mean input tokens per researcher, then call finish_research with the mean in the reason.",
)];
for (let turn = 1; turn <= 5; turn++) {
  const t0 = Date.now();
  const ai = (await bound.invoke(messages)) as AIMessage;
  messages.push(ai);
  const builtins = ((ai.additional_kwargs as any)?.tool_outputs ?? []).map((o: any) => ({ type: o.type, code: o.code, outputs: o.outputs }));
  console.log(`turn ${turn} (${Date.now() - t0} ms): tool_calls=${JSON.stringify(ai.tool_calls?.map((c) => ({ name: c.name, args: c.args })))}`);
  console.log(`  builtin=${JSON.stringify(builtins).slice(0, 600)}`);
  console.log(`  text=${JSON.stringify(typeof ai.content === "string" ? ai.content : ai.content).slice(0, 300)}`);
  console.log(`  usage=${JSON.stringify(ai.usage_metadata)}`);
  if (!ai.tool_calls?.length) break;
  for (const call of ai.tool_calls) {
    const out = call.name === "get_round_status" ? await roundStatus.invoke({}) : await finish.invoke(call.args as { reason: string });
    messages.push(new ToolMessage({ content: String(out), tool_call_id: call.id! }));
  }
  if (ai.tool_calls.some((c) => c.name === "finish_research")) break;
}
