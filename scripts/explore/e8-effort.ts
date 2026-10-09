// E8: the Haiku profile sends output_config.effort on plain, structured and
// web-tool calls, and the API accepts it.
import "dotenv/config";
import { z } from "zod";
import { HumanMessage } from "@langchain/core/messages";
import { createChatModel, getProfile, type AnthropicProfile } from "../../src/config/models.js";
import { runAnthropic } from "../../src/research/adapters/anthropic.js";
import { UsageLedger } from "../../src/observability/usage.js";

const sent: unknown[] = [];
const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: Parameters<typeof fetch>[0], init?: RequestInit) => {
  if (String(input).includes("api.anthropic.com") && typeof init?.body === "string") {
    sent.push(JSON.parse(init.body).output_config ?? null);
  }
  return realFetch(input, init);
}) as typeof fetch;

const profile = getProfile("haiku") as AnthropicProfile;
const model = createChatModel(profile);
const plain = await model.invoke("Reply with the single word: ok");
const structured = await model.withStructuredOutput(z.object({ answer: z.string() }), { method: "jsonSchema" }).invoke("What is 2+2? Answer in words.");
const research = await runAnthropic({ ...profile, webSearch: { ...profile.webSearch, maxUses: 1 }, webFetch: undefined }, {
  messages: [new HumanMessage("Search once: what is the capital of Canada? One sentence with the source URL.")],
  ledger: new UsageLedger(profile.pricing),
  role: "researcher",
  signal: AbortSignal.timeout(120_000),
});
console.log(JSON.stringify({ outputConfigsSent: sent, plain: String(plain.content).slice(0, 40), structured, research: { searches: research.searches, notes: research.notes.slice(0, 120) } }, null, 1));
