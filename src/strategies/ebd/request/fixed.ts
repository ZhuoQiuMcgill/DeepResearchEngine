/**
 * Fixed mode of the request analysis (design section 5.3): code runs the scan,
 * one model call answers, the contract checks judge the reply, and one retry
 * gets the previous reply with the numbered errors. No scan or search tools.
 *
 * The reply comes through the same unforced submit_analysis tool as in agent
 * mode, so both modes differ only in who drives the loop. Two findings of
 * 2026-10-19 rule out the alternatives on Haiku: provider-enforced structured
 * output rejects this schema as too large (L4), and forced tool use switches
 * off Haiku's thinking, which agent mode keeps.
 */
import { HumanMessage, SystemMessage, type AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { Callbacks } from "@langchain/core/callbacks/manager";
import type { Runnable } from "@langchain/core/runnables";
import { checkAnalysis, salvage, type CheckResult } from "./checks.js";
import { requestMessage, retryMessage, systemPrompt } from "./prompt.js";
import { scanRequest } from "./scan.js";
import type { Analysis } from "./schema.js";
import { SUBMIT_TOOL, toolDefinitions } from "./tools.js";
import { stopReasonOf, textOf, usageOf, type AnalysisOutcome, type TraceEvent } from "./trace.js";

export type FixedInput = {
  question: string;
  today: string;
  model: BaseChatModel;
  /** Replies checked in total, the first included. */
  maxAttempts?: number;
  /** Ask the provider to enforce the analysis schema (too large for Anthropic's strict grammar). */
  strictSubmit?: boolean;
  callbacks?: Callbacks;
};

export async function runFixedAnalysis(input: FixedInput): Promise<AnalysisOutcome> {
  const started = Date.now();
  const maxAttempts = input.maxAttempts ?? 2;
  const scan = scanRequest(input.question, input.today);
  const submit = toolDefinitions({ strictSubmit: input.strictSubmit ?? false }).filter((t) => t.function.name === SUBMIT_TOOL);
  const model = input.model.bindTools!(submit) as Runnable<BaseMessage[], AIMessage>;
  const system = new SystemMessage(systemPrompt("fixed"));
  const trace: TraceEvent[] = [];
  const usage = { inputTokens: 0, outputTokens: 0, calls: 0 };
  let message = requestMessage(input.question, input.today, scan);
  let last: { analysis: Analysis; check: CheckResult } | null = null;
  let check: CheckResult = { analysis: null, errors: [], warnings: [] };
  let attempts = 0;
  let firstAccepted = false;

  while (attempts < maxAttempts) {
    attempts += 1;
    const t0 = Date.now();
    const ai = await model.invoke([system, new HumanMessage(message)], input.callbacks ? { callbacks: input.callbacks } : {});
    const u = usageOf(ai);
    usage.inputTokens += u.inputTokens;
    usage.outputTokens += u.outputTokens;
    usage.calls += 1;
    const call = (ai.tool_calls ?? []).find((c) => c.name === SUBMIT_TOOL);
    trace.push({ type: "model_turn", turn: attempts, stopReason: stopReasonOf(ai), text: textOf(ai).slice(0, 2000), toolCalls: (ai.tool_calls ?? []).map((c) => c.name), ...u, ms: Date.now() - t0 });

    const previous = call ? JSON.stringify(call.args) : textOf(ai);
    check = call
      ? checkAnalysis(call.args, { request: input.question, scan })
      : { analysis: null, errors: [{ code: "no_reply", path: "", message: "the reply did not call submit_analysis with the analysis" }], warnings: [] };
    if (check.analysis) last = { analysis: check.analysis, check };
    const accepted = check.analysis !== null && check.errors.length === 0;
    trace.push({ type: "check", attempt: attempts, accepted, errors: check.errors, warnings: check.warnings });
    if (accepted) {
      firstAccepted = attempts === 1;
      return outcome(check.analysis, true, false);
    }
    message = retryMessage(input.question, input.today, scan, previous, check.errors);
  }

  const fallback = last ? salvage(last.analysis, last.check.errors) : null;
  return outcome(fallback, false, Boolean(fallback));

  function outcome(analysis: Analysis | null, accepted: boolean, isFallback: boolean): AnalysisOutcome {
    return {
      mode: "fixed",
      analysis,
      accepted,
      fallback: isFallback,
      firstAccepted,
      attempts,
      errors: accepted ? [] : check.errors,
      warnings: check.warnings,
      scan,
      scans: 1,
      searches: { count: 0, queries: [], results: [] },
      turns: attempts,
      usage,
      stopReason: accepted ? "accepted" : "attempts exhausted",
      ms: Date.now() - started,
      trace,
    };
  }
}
