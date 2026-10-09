// E4: withStructuredOutput on both models for planning-style calls.
import "dotenv/config";
import { z } from "zod";
import { ChatAnthropic } from "@langchain/anthropic";
import { ChatOpenAI } from "@langchain/openai";

const Plan = z.object({
  rationale: z.string().describe("Why this decomposition"),
  briefs: z.array(z.object({
    objective: z.string(),
    keyQuestions: z.array(z.string()),
    sourceHints: z.array(z.string()),
  })).describe("1-6 research briefs"),
});
const prompt = "Decompose the research question into 3 non-overlapping research briefs: compare meta quest 3 and apple vision pro";
const models = {
  haiku: new ChatAnthropic({ model: "claude-haiku-5-5", maxTokens: 8000 }),
  luna: new ChatOpenAI({ model: "gpt-6-luna", useResponsesApi: true, reasoning: { effort: "low" } }),
};
for (const [name, m] of Object.entries(models)) {
  for (const method of [undefined, "jsonSchema", "functionCalling"] as const) {
    const t0 = Date.now();
    try {
      const out = await m.withStructuredOutput(Plan, method ? { method } : undefined).invoke(prompt);
      console.log(name, method ?? "default", "ok", Date.now() - t0, "ms", out.briefs.length, "briefs");
    } catch (e: any) {
      console.log(name, method ?? "default", "ERROR", String(e?.message ?? e).slice(0, 300));
    }
  }
}
