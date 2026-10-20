import { describe, expect, it } from "vitest";
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { runAgentAnalysis, type Grounding } from "./agent.js";
import { EXAMPLES } from "./examples.js";
import { runFixedAnalysis } from "./fixed.js";
import type { Analysis } from "./schema.js";

const E1 = EXAMPLES[0]!;
const bad = (): Analysis => {
  const a = structuredClone(E1.analysis);
  a.rom.objects[3]!.text = "tarifs";
  return a;
};
let n = 0;
const call = (name: string, args: unknown) => new AIMessage({ content: "", tool_calls: [{ id: `c${++n}`, name, args: args as Record<string, unknown>, type: "tool_call" }] });

/** A model whose bound runnable replays scripted turns and records what it was sent. */
function scripted(turns: AIMessage[]) {
  const seen: BaseMessage[][] = [];
  const runnable = { invoke: async (messages: BaseMessage[]) => (seen.push(messages), turns.shift() ?? new AIMessage("done")) };
  const model = { bindTools: () => runnable } as unknown as BaseChatModel;
  return { model, runnable, seen };
}

describe("agent mode", () => {
  it("scans, corrects a rejected submission and finishes on acceptance", async () => {
    const { model, seen } = scripted([call("scan_request", {}), call("submit_analysis", bad()), call("submit_analysis", E1.analysis)]);
    const out = await runAgentAnalysis({ question: E1.request, today: E1.runDate, model });
    expect(out).toMatchObject({ accepted: true, firstAccepted: false, attempts: 2, scans: 1, turns: 3, stopReason: "accepted" });
    const rejection = out.trace.find((e) => e.type === "tool_result" && e.name === "submit_analysis" && e.error);
    expect(JSON.stringify(rejection)).toContain("quote_not_in_request");
    expect(seen[2]!.at(-1)!.content).toContain("quote_not_in_request");
  });

  it("reminds once when a turn has no tool call", async () => {
    const { model } = scripted([new AIMessage("Here is my plan."), call("submit_analysis", E1.analysis)]);
    const out = await runAgentAnalysis({ question: E1.request, today: E1.runDate, model });
    expect(out.accepted).toBe(true);
    expect(out.trace.some((e) => e.type === "reminder")).toBe(true);
  });

  it("falls back after the last rejected submission", async () => {
    const { model } = scripted([call("submit_analysis", bad()), call("submit_analysis", bad()), call("submit_analysis", bad())]);
    const out = await runAgentAnalysis({ question: E1.request, today: E1.runDate, model });
    expect(out).toMatchObject({ accepted: false, fallback: true, attempts: 3, stopReason: "submissions exhausted" });
    expect(out.analysis).not.toBeNull();
  });

  it("answers an unknown tool with an error and goes on", async () => {
    const { model } = scripted([call("web_search", { query: "x" }), call("submit_analysis", E1.analysis)]);
    const out = await runAgentAnalysis({ question: E1.request, today: E1.runDate, model });
    expect(out.accepted).toBe(true);
    expect(out.trace.find((e) => e.type === "tool_result" && e.name === "web_search")).toMatchObject({ error: true });
  });

  it("counts grounding searches and accepts names from reported results only", async () => {
    const named = structuredClone(E1.analysis);
    named.questions[2]!.text += " Include Scotiabank.";
    named.grounding = [{ object_id: "O9", query: "economists expect new-car prices Canada 2026", url: "https://example.org/outlook", finding: "A bank outlook forecasts prices.", names: ["Scotiabank"] }];
    const { runnable } = scripted([call("submit_analysis", named)]);
    const remaining: number[] = [];
    const grounding: Grounding = {
      bind: (_tools, left) => (remaining.push(left), runnable as never),
      read: () => ({ billed: 1, queries: ["new-car price forecasts Canada 2026"], results: [{ url: "https://example.org/outlook", title: "Scotiabank auto outlook" }], errors: [] }),
    };
    const out = await runAgentAnalysis({ question: E1.request, today: E1.runDate, model: {} as BaseChatModel, grounding });
    expect(out.accepted).toBe(true);
    expect(out.searches.count).toBe(1);
    expect(remaining).toEqual([3]);
  });
});

describe("fixed mode", () => {
  it("retries once with the numbered errors", async () => {
    const { model, seen } = scripted([call("submit_analysis", bad()), call("submit_analysis", E1.analysis)]);
    const out = await runFixedAnalysis({ question: E1.request, today: E1.runDate, model });
    expect(out).toMatchObject({ accepted: true, firstAccepted: false, attempts: 2 });
    expect(String(seen[0]![1]!.content)).toContain("<spans>");
    expect(String(seen[1]![1]!.content)).toContain("<validation_errors>");
  });

  it("counts a reply without the tool call as a failed attempt", async () => {
    const { model } = scripted([new AIMessage("I think the analysis is ..."), call("submit_analysis", E1.analysis)]);
    const out = await runFixedAnalysis({ question: E1.request, today: E1.runDate, model });
    expect(out).toMatchObject({ accepted: true, attempts: 2 });
    expect(out.trace.find((e) => e.type === "check")).toMatchObject({ accepted: false, errors: [{ code: "no_reply" }] });
  });
});
