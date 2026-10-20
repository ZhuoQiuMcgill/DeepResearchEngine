/**
 * The analyst's custom tools, bound to one run:
 * - scan_request: the never-drop scan of the request (no arguments);
 * - submit_analysis: the contract checks; the only way to finish.
 *
 * Definitions are plain function tools whose JSON Schemas carry only types,
 * enums and required fields, so both providers accept them with strict: true.
 * The executor keeps the run's state (scans, submissions, the accepted analysis).
 */
import { ToolMessage } from "@langchain/core/messages";
import type { ToolCall } from "@langchain/core/messages/tool";
import { checkAnalysis, counts, type CheckResult } from "./checks.js";
import { AnalysisApiSchema, ScanInputSchema, apiJsonSchema, type Analysis, type ScanResult, type SubmitOutput } from "./schema.js";
import type { SearchResult } from "./trace.js";

export const SCAN_TOOL = "scan_request";
export const SUBMIT_TOOL = "submit_analysis";

/**
 * A function tool with its own strict flag. LangChain reads `function.strict`
 * for Anthropic and the top-level `strict` for OpenAI, so both are set and no
 * bind-level strict option is passed.
 */
export type FunctionTool = {
  type: "function";
  strict: boolean;
  function: { name: string; description: string; parameters: Record<string, unknown>; strict: boolean };
};

/**
 * `strictSubmit` asks the provider to enforce the analysis schema while it
 * generates. Anthropic rejects that schema as too large for its strict grammar
 * (exploration L4, 2026-10-19), so the default is off: submissions are checked
 * by code instead. The scan tool, with no arguments, is always strict.
 */
export function toolDefinitions(options: { strictSubmit: boolean } = { strictSubmit: false }): FunctionTool[] {
  const tool = (name: string, description: string, parameters: Record<string, unknown>, strict: boolean): FunctionTool => ({
    type: "function",
    strict,
    function: { name, description, parameters, strict },
  });
  return [
    tool(
      SCAN_TOOL,
      "List the spans of the client request that the analysis must keep: negations, restrictors, quantifiers, comparisons, modal verbs, numbers, dates, relative times with date windows resolved from the run date, names, acronym pairs, quoted text, links and question words. Takes no arguments; the request and run date are already bound.",
      apiJsonSchema(ScanInputSchema),
      true,
    ),
    tool(
      SUBMIT_TOOL,
      "Submit the whole request analysis. The system checks verbatim quotes, references, routes and order, span coverage, names and lengths. Accepted: your work is done. Rejected: the result lists numbered errors with their paths; correct exactly those and submit the whole analysis again. At most 3 submissions.",
      apiJsonSchema(AnalysisApiSchema),
      options.strictSubmit,
    ),
  ];
}

export type ToolState = {
  scan: ScanResult;
  scans: number;
  submissions: number;
  accepted: Analysis | null;
  firstAccepted: boolean;
  /** The last structurally valid submission and its check, for the fallback. */
  last: { analysis: Analysis; check: CheckResult } | null;
  lastErrors: CheckResult["errors"];
  warnings: CheckResult["warnings"];
  /** Search results the provider reported so far; undefined when search is not offered. */
  reported: SearchResult[] | undefined;
};

export type ToolRun = { message: ToolMessage; result: unknown; error: boolean };

export function createToolExecutor(input: { request: string; scan: ScanResult; maxScans: number; maxSubmissions: number; searchOffered: boolean }) {
  const state: ToolState = {
    scan: input.scan,
    scans: 0,
    submissions: 0,
    accepted: null,
    firstAccepted: false,
    last: null,
    lastErrors: [],
    warnings: [],
    reported: input.searchOffered ? [] : undefined,
  };

  const reply = (call: ToolCall, result: unknown, error: boolean): ToolRun => ({
    message: new ToolMessage({ tool_call_id: call.id ?? "", name: call.name, content: JSON.stringify(result), status: error ? "error" : "success" }),
    result,
    error,
  });

  function scan(call: ToolCall): ToolRun {
    state.scans += 1;
    if (state.scans > input.maxScans) {
      return reply(call, { error: `scan_request can be called at most ${input.maxScans} times; its result does not change.` }, true);
    }
    return reply(call, state.scan, false);
  }

  function submit(call: ToolCall): ToolRun {
    if (state.accepted) return reply(call, { error: "The analysis was already accepted; your work is done." }, true);
    if (state.submissions >= input.maxSubmissions) return reply(call, { error: "No submissions left." }, true);
    state.submissions += 1;
    const check = checkAnalysis(call.args, { request: input.request, scan: state.scan, ...(state.reported ? { reported: state.reported } : {}) });
    if (check.analysis) state.last = { analysis: check.analysis, check };
    state.warnings = check.warnings;
    const accepted = check.analysis !== null && check.errors.length === 0;
    if (accepted) {
      state.accepted = check.analysis;
      state.firstAccepted = state.submissions === 1;
      state.lastErrors = [];
    } else {
      state.lastErrors = check.errors;
    }
    const out: SubmitOutput = {
      accepted,
      submission: state.submissions,
      submissions_left: input.maxSubmissions - state.submissions,
      errors: accepted ? [] : check.errors.map((e, i) => ({ n: i + 1, ...e })),
      warnings: check.warnings,
      counts: check.analysis ? counts(check.analysis) : null,
    };
    return reply(call, out, !accepted);
  }

  async function execute(call: ToolCall): Promise<ToolRun> {
    if (call.name === SCAN_TOOL) return scan(call);
    if (call.name === SUBMIT_TOOL) return submit(call);
    return reply(call, { error: `Unknown tool "${call.name}". The tools are ${SCAN_TOOL} and ${SUBMIT_TOOL}${state.reported ? ", plus the provider's web_search" : ""}.` }, true);
  }

  return { state, execute };
}
