import { it, expect } from "vitest";
import { AIMessage } from "@langchain/core/messages";
import { createWriter } from "../src/writer/writer.js";
it("marks a locally truncated report rather than silently presenting it as complete", async () => {
  const model = { invoke: async () => new AIMessage({ content: "An unfinished report",
    response_metadata: { finish_reason: "length" } }) };
  const out = await createWriter(model as never, "2026-10-12")("What is EBD (Environment Based Design)?", { material: [] });
  expect(out.diagnostics).toContain("report output truncated");
});

it("uses one source-preserving revision to correct an unsupported number", async () => {
  const inputs: any[] = [];
  const model = { invoke: async (messages: any) => {
    inputs.push(messages);
    return new AIMessage(inputs.length === 1 ? "The cost is 900 [Source](https://example.org/paper)." : "The cost is 500 [Source](https://example.org/paper).");
  } };
  const out = await createWriter(model as never, "2026-10-14")("What is the cost?", {
    material: [{ label: "Costs", notes: "- The cost is 500 [Source](https://example.org/paper)." }],
  });
  expect(inputs).toHaveLength(2);
  expect(inputs[1][0].content).toBe(inputs[0][0].content);
  expect(inputs[1].at(-1).content).toContain("900");
  expect(out.report).toContain("500");
  expect(out.diagnostics.some(d => d.includes("issues remain"))).toBe(false);
});

it("cannot escape numerical support checks by dropping a citation and never loops", async () => {
  let calls = 0;
  const model = { invoke: async () => new AIMessage(++calls === 1 ? "The cost is 900 [Source](https://example.org/paper)." : "The cost is 900.") };
  const out = await createWriter(model as never, "2026-10-14")("What is the cost?", {
    material: [{ label: "Costs", notes: "- The cost is 500 [Source](https://example.org/paper)." }],
  });
  expect(calls).toBe(2);
  expect(out.diagnostics).toContain("numeric citation issues remain after bounded revision: 1 unit(s)");
});
