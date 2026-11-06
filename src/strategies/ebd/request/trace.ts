/**
 * Provider-neutral record of one request analysis: every model turn, tool call
 * and result, in order. Server-side searches are added by the caller's
 * grounding adapter, because only it knows the provider's reply format.
 */
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { Analysis, Issue, ScanResult } from "./schema.js";

export type SearchResult = { url: string; title?: string };

export type TraceEvent =
  | { type: "model_turn"; turn: number; stopReason: string; text: string; toolCalls: string[]; inputTokens: number; outputTokens: number; ms: number }
  | { type: "server_search"; turn: number; queries: string[]; results: SearchResult[]; billed: number; errors: string[] }
  | { type: "tool_call"; turn: number; id: string; name: string; args: unknown }
  | { type: "tool_result"; turn: number; id: string; name: string; result: unknown; error: boolean; ms: number }
  | { type: "reminder"; turn: number; text: string }
  | { type: "check"; attempt: number; accepted: boolean; errors: Issue[]; warnings: Issue[] };

export type AnalysisOutcome = {
  mode: "agent" | "fixed";
  /** The accepted analysis, or the fallback; null when nothing usable remains. */
  analysis: Analysis | null;
  accepted: boolean;
  fallback: boolean;
  /** The first submission (agent) or the first reply (fixed) passed the checks. */
  firstAccepted: boolean;
  /** Submissions (agent) or checked replies (fixed). */
  attempts: number;
  /** Errors of the last rejected attempt; empty when accepted. */
  errors: Issue[];
  warnings: Issue[];
  scan: ScanResult;
  scans: number;
  searches: { count: number; queries: string[]; results: SearchResult[] };
  turns: number;
  usage: { inputTokens: number; outputTokens: number; calls: number };
  stopReason: string;
  ms: number;
  trace: TraceEvent[];
};

type Block = Record<string, unknown>;

export function textOf(message: BaseMessage): string {
  const c = message.content;
  if (typeof c === "string") return c;
  return (c as Block[]).filter((b) => b.type === "text").map((b) => String(b.text ?? "")).join("");
}

export function stopReasonOf(message: AIMessage): string {
  const meta = (message.response_metadata ?? {}) as Block;
  return String(meta.stop_reason ?? meta.finish_reason ?? meta.status ?? "");
}

export function usageOf(message: AIMessage): { inputTokens: number; outputTokens: number } {
  return { inputTokens: message.usage_metadata?.input_tokens ?? 0, outputTokens: message.usage_metadata?.output_tokens ?? 0 };
}

/** One assistant turn from a paused reply and its continuation (Anthropic pause_turn). */
export function mergeTurn(first: AIMessage, next: AIMessage): AIMessage {
  const blocks = (m: AIMessage): Block[] => (typeof m.content === "string" ? (m.content ? [{ type: "text", text: m.content }] : []) : (m.content as Block[]));
  const a = usageOf(first);
  const b = usageOf(next);
  return new AIMessage({
    content: [...blocks(first), ...blocks(next)] as never,
    tool_calls: [...(first.tool_calls ?? []), ...(next.tool_calls ?? [])],
    additional_kwargs: { ...first.additional_kwargs, ...next.additional_kwargs },
    response_metadata: next.response_metadata,
    usage_metadata: { input_tokens: a.inputTokens + b.inputTokens, output_tokens: a.outputTokens + b.outputTokens, total_tokens: a.inputTokens + b.inputTokens + a.outputTokens + b.outputTokens },
    ...(next.id ? { id: next.id } : {}),
  });
}
