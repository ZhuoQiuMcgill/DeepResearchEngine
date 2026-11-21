import { describe, expect, it } from "vitest";
import { AIMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { createChatModel, getProfile } from "../src/config/models.js";
import { createWriter } from "../src/writer/writer.js";

const fakeModel = (msg: AIMessage) => ({ invoke: async () => msg }) as unknown as BaseChatModel;

describe("writer output limit", () => {
  it("raises only the writer's limit and streams it on Anthropic", () => {
    // Constructors only check that a key exists; nothing is sent.
    for (const k of ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"]) process.env[k] ??= "test-key-not-used";
    const haiku = getProfile("haiku");
    const writer = createChatModel(haiku, undefined, { role: "writer" }) as unknown as { maxTokens: number; streaming: boolean };
    const strategy = createChatModel(haiku) as unknown as { maxTokens: number; streaming: boolean };
    expect(writer.maxTokens).toBe(64000);
    expect(writer.streaming).toBe(true);
    expect(strategy.maxTokens).toBe(21000);
    expect(strategy.streaming).toBe(false);
    const luna = createChatModel(getProfile("luna"), undefined, { role: "writer" }) as unknown as { maxTokens: number };
    expect(luna.maxTokens).toBe(32000);
    const deepseek = createChatModel(getProfile("deepseek"), undefined, { role: "writer" }) as unknown as { maxTokens: number };
    expect(deepseek.maxTokens).toBe(64000);
  });

  it("flags a truncated report whether the stop reason is in response_metadata or additional_kwargs", async () => {
    const streamed = new AIMessage({ content: "cut", additional_kwargs: { stop_reason: "max_tokens" }, response_metadata: {} });
    const plain = new AIMessage({ content: "cut", response_metadata: { stop_reason: "max_tokens" } });
    const done = new AIMessage({ content: "whole", additional_kwargs: { stop_reason: "end_turn" }, response_metadata: {} });
    const synthesis = { material: [{ label: "a", notes: "## Q\n### Takeaway\nx" }] };
    expect((await createWriter(fakeModel(streamed), "2026-11-21")("Q?", synthesis)).diagnostics).toContain("report output truncated");
    expect((await createWriter(fakeModel(plain), "2026-11-21")("Q?", synthesis)).diagnostics).toContain("report output truncated");
    expect((await createWriter(fakeModel(done), "2026-11-21")("Q?", synthesis)).diagnostics).toEqual([]);
  });
});
