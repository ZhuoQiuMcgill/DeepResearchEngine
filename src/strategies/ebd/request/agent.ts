/**
 * Agent mode of the request analysis (Lab 3): a two-node LangGraph loop,
 * model ⇄ tools, that ends when submit_analysis accepts an analysis.
 *
 * The model decides which tools to call and when. Code fixes the limits (turns,
 * searches, scans, submissions), the gate (the contract checks behind
 * submit_analysis) and the fallback.
 *
 * Grounding search is an optional, injected adapter. Strategy code must stay
 * provider-neutral and must not search (contract v1), so in the project the
 * adapter is absent until the platform offers it (platform request P5).
 */
import { Annotation, END, START, StateGraph } from "@langchain/langgraph";
import { HumanMessage, SystemMessage, type AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { Callbacks } from "@langchain/core/callbacks/manager";
import type { Runnable, RunnableConfig } from "@langchain/core/runnables";
import { salvage } from "./checks.js";
import { REMINDER, requestMessage, systemPrompt } from "./prompt.js";
import { scanRequest } from "./scan.js";
import { createToolExecutor, toolDefinitions, type FunctionTool } from "./tools.js";
import { mergeTurn, stopReasonOf, textOf, usageOf, type AnalysisOutcome, type SearchResult, type TraceEvent } from "./trace.js";

export type AgentOptions = {
  maxTurns: number;
  maxSearches: number;
  maxSubmissions: number;
  maxScans: number;
  /** Continuations of an Anthropic pause_turn reply within one turn. */
  maxContinuations: number;
  /** Ask the provider to enforce the submit_analysis schema (too large for Anthropic's strict grammar). */
  strictSubmit: boolean;
};

export const AGENT_DEFAULTS: AgentOptions = { maxTurns: 6, maxSearches: 3, maxSubmissions: 3, maxScans: 2, maxContinuations: 3, strictSubmit: false };

/** What a provider adapter reports about the server-side searches in one reply. */
export type GroundingUse = { billed: number; queries: string[]; results: SearchResult[]; errors: string[] };

export type Grounding = {
  /**
   * The model with the custom tools plus web search, at most `maxSearches` per call.
   * Bound once per analysis: Anthropic binds thinking blocks to the exact tool list,
   * so a cap that shrank between turns would invalidate the replayed thinking
   * (exploration L3, 2026-10-19). Across turns the cap is enforced by the
   * instruction and checked from the trace.
   */
  bind(tools: FunctionTool[], maxSearches: number): Runnable<BaseMessage[], AIMessage>;
  read(message: AIMessage): GroundingUse;
};

export type AgentInput = {
  question: string;
  today: string;
  model: BaseChatModel;
  grounding?: Grounding;
  options?: Partial<AgentOptions>;
  callbacks?: Callbacks;
};

const State = Annotation.Root({
  messages: Annotation<BaseMessage[]>({ reducer: (a, b) => a.concat(b), default: () => [] }),
  turns: Annotation<number>,
  reminders: Annotation<number>,
  stopReason: Annotation<string>,
});
type StateType = typeof State.State;

export async function runAgentAnalysis(input: AgentInput): Promise<AnalysisOutcome> {
  const started = Date.now();
  const opts: AgentOptions = { ...AGENT_DEFAULTS, ...input.options };
  const scan = scanRequest(input.question, input.today);
  const tools = createToolExecutor({ request: input.question, scan, maxScans: opts.maxScans, maxSubmissions: opts.maxSubmissions, searchOffered: Boolean(input.grounding) });
  const definitions = toolDefinitions({ strictSubmit: opts.strictSubmit });
  const trace: TraceEvent[] = [];
  const searches = { count: 0, queries: [] as string[], results: [] as SearchResult[] };
  const usage = { inputTokens: 0, outputTokens: 0, calls: 0 };

  // Strictness is set per tool in the definitions, so no bind-level option is passed.
  // The tool list stays identical for every turn (see Grounding.bind).
  const model = input.grounding
    ? input.grounding.bind(definitions, opts.maxSearches)
    : (input.model.bindTools!(definitions) as Runnable<BaseMessage[], AIMessage>);

  async function agent(state: StateType, config?: RunnableConfig): Promise<Partial<StateType>> {
    const turn = state.turns + 1;
    const t0 = Date.now();
    let ai = (await model.invoke(state.messages, config)) as AIMessage;
    for (let k = 0; stopReasonOf(ai) === "pause_turn" && k < opts.maxContinuations; k++) {
      ai = mergeTurn(ai, (await model.invoke([...state.messages, ai], config)) as AIMessage);
    }
    const u = usageOf(ai);
    usage.inputTokens += u.inputTokens;
    usage.outputTokens += u.outputTokens;
    usage.calls += 1;
    trace.push({ type: "model_turn", turn, stopReason: stopReasonOf(ai), text: textOf(ai).slice(0, 2000), toolCalls: (ai.tool_calls ?? []).map((c) => c.name), ...u, ms: Date.now() - t0 });
    if (input.grounding) {
      const g = input.grounding.read(ai);
      if (g.billed || g.queries.length || g.errors.length) {
        searches.count += g.billed;
        searches.queries.push(...g.queries);
        searches.results.push(...g.results);
        tools.state.reported!.push(...g.results);
        trace.push({ type: "server_search", turn, queries: g.queries, results: g.results, billed: g.billed, errors: g.errors });
      }
    }
    return { messages: [ai], turns: turn };
  }

  async function runTools(state: StateType): Promise<Partial<StateType>> {
    const last = state.messages[state.messages.length - 1] as AIMessage;
    const messages: BaseMessage[] = [];
    for (const call of last.tool_calls ?? []) {
      trace.push({ type: "tool_call", turn: state.turns, id: call.id ?? "", name: call.name, args: call.args });
      const t0 = Date.now();
      const run = await tools.execute(call);
      trace.push({ type: "tool_result", turn: state.turns, id: call.id ?? "", name: call.name, result: run.result, error: run.error, ms: Date.now() - t0 });
      messages.push(run.message);
    }
    return { messages, ...(tools.state.accepted ? { stopReason: "accepted" } : {}) };
  }

  function remind(state: StateType): Partial<StateType> {
    trace.push({ type: "reminder", turn: state.turns, text: REMINDER });
    return { messages: [new HumanMessage(REMINDER)], reminders: state.reminders + 1 };
  }

  function afterAgent(state: StateType): "tools" | "remind" | "stop" {
    const last = state.messages[state.messages.length - 1] as AIMessage;
    if (last.tool_calls?.length) return "tools";
    if (state.reminders < 1 && state.turns < opts.maxTurns) return "remind";
    return "stop";
  }

  function afterTools(state: StateType): "agent" | "stop" | typeof END {
    if (tools.state.accepted) return END;
    if (tools.state.submissions >= opts.maxSubmissions || state.turns >= opts.maxTurns) return "stop";
    return "agent";
  }

  function stop(state: StateType): Partial<StateType> {
    const reason =
      tools.state.submissions >= opts.maxSubmissions ? "submissions exhausted" : state.turns >= opts.maxTurns ? "turn limit" : "no submission after the reminder";
    return { stopReason: reason };
  }

  const graph = new StateGraph(State)
    .addNode("agent", agent)
    .addNode("tools", runTools)
    .addNode("remind", remind)
    .addNode("stop", stop)
    .addEdge(START, "agent")
    .addConditionalEdges("agent", afterAgent, ["tools", "remind", "stop"])
    .addEdge("remind", "agent")
    .addConditionalEdges("tools", afterTools, ["agent", "stop", END])
    .addEdge("stop", END)
    .compile();

  const final = (await graph.invoke(
    {
      messages: [new SystemMessage(systemPrompt("agent", Boolean(input.grounding))), new HumanMessage(requestMessage(input.question, input.today))],
      turns: 0,
      reminders: 0,
      stopReason: "",
    },
    { recursionLimit: 4 * opts.maxTurns + 10, ...(input.callbacks ? { callbacks: input.callbacks } : {}), runName: "ebd:request-analysis:agent" },
  )) as StateType;

  const accepted = tools.state.accepted;
  const fallback = !accepted && tools.state.last ? salvage(tools.state.last.analysis, tools.state.last.check.errors) : null;
  return {
    mode: "agent",
    analysis: accepted ?? fallback,
    accepted: Boolean(accepted),
    fallback: !accepted && Boolean(fallback),
    firstAccepted: tools.state.firstAccepted,
    attempts: tools.state.submissions,
    errors: accepted ? [] : tools.state.lastErrors,
    warnings: tools.state.warnings,
    scan,
    scans: tools.state.scans,
    searches,
    turns: final.turns,
    usage,
    stopReason: final.stopReason || "unknown",
    ms: Date.now() - started,
    trace,
  };
}
