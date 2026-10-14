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
    return new AIMessage("The cost is 900 [Source](https://example.org/paper).");
  }, withStructuredOutput: () => ({ invoke: async (messages: any) => {
    inputs.push(messages); return { edits: [{ index: 0, text: "The cost is 500 [Source](https://example.org/paper)." }] };
  } }) };
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
  const model = { invoke: async () => { calls++; return new AIMessage("The cost is 900 [Source](https://example.org/paper). Other useful information remains."); },
    withStructuredOutput: () => ({ invoke: async () => { calls++; return { edits: [{ index: 0, text: "The cost is 900." }] }; } }) };
  const out = await createWriter(model as never, "2026-10-14")("What is the cost?", {
    material: [{ label: "Costs", notes: "- The cost is 500 [Source](https://example.org/paper)." }],
  });
  expect(calls).toBe(2);
  expect(out.report).not.toContain("900");
  expect(out.report).toContain("Other useful information remains.");
  expect(out.diagnostics).toContain("numeric source edits: 0 replaced, 1 omitted");
});

it("rejects a replacement citing an invented URL even when it contains no digits", async () => {
  const model = { invoke: async () => new AIMessage("The cost is 900 [Paper](https://example.org/paper). The method remains useful."),
    withStructuredOutput: () => ({ invoke: async () => ({ edits: [{ index: 0, text: "The price is unknown [Other](https://example.org/invented)." }] }) }) };
  const out = await createWriter(model as never, "2026-10-14")("Question", {
    material: [{ label: "Cost", notes: "- The cost is 500 [Paper](https://example.org/paper)." }],
    sourceRegistry: [{ url: "https://example.org/paper", cited: true }],
  });
  expect(out.report).not.toContain("invented");
  expect(out.report).toContain("The method remains useful.");
  expect(out.diagnostics).toContain("numeric source edits: 0 replaced, 1 omitted");
});
