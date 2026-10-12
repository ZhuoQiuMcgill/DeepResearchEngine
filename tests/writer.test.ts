import { it, expect } from "vitest";
import { AIMessage } from "@langchain/core/messages";
import { createWriter } from "../src/writer/writer.js";
it("marks a locally truncated report rather than silently presenting it as complete", async () => {
  const model = { invoke: async () => new AIMessage({ content: "An unfinished report",
    response_metadata: { finish_reason: "length" } }) };
  const out = await createWriter(model as never, "2026-10-12")("What is EBD (Environment Based Design)?", { material: [] });
  expect(out.diagnostics).toContain("report output truncated");
});
