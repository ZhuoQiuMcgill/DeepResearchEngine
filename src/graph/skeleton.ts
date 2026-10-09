/**
 * The shared research skeleton: plan -> research (parallel) -> observe ->
 * ... -> finalize -> write. Strategy, researcher and writer are injected, so
 * the graph itself contains no provider or strategy logic.
 */
import { isDeepStrictEqual } from "node:util";
import { Annotation, END, Send, START, StateGraph } from "@langchain/langgraph";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { applyDecision, budgetView, type BudgetLimits } from "../core/budget.js";
import {
  SynthesisInputSchema,
  type ResearchBrief,
  type ResearchBriefInput,
  type ResearchResult,
  type SynthesisInput,
} from "../core/contracts.js";
import type { JsonValue, ResearchStrategy, StrategyContext, StrategyStep } from "../core/strategy.js";
import type { ResearchFn } from "../research/researcher.js";
import type { WriteFn } from "../writer/writer.js";

export interface DecisionRecord {
  phase: "init" | "observe";
  /** Round the accepted briefs start. */
  round: number;
  rationale: string;
  stop: boolean;
  accepted: ResearchBrief[];
  dropped: ResearchBriefInput[];
  ignored: ResearchBriefInput[];
  invalid: { brief: unknown; reason: string }[];
  budgetBefore: number;
  strategyState: JsonValue;
  at: string;
}

export type StopReason = "strategy-stop" | "no-briefs" | "budget-exhausted" | "max-rounds";

export interface SkeletonHooks {
  onDecision?(record: DecisionRecord): void | Promise<void>;
  onResult?(result: ResearchResult): void | Promise<void>;
  onSynthesis?(synthesis: SynthesisInput, diagnostics: string[]): void | Promise<void>;
}

export interface SkeletonDeps {
  strategy: ResearchStrategy<any>;
  strategyModel: BaseChatModel;
  research: ResearchFn;
  write: WriteFn;
  limits: BudgetLimits;
  maxRounds: number;
  concurrency: number;
  runId: string;
  hooks?: SkeletonHooks;
}

const RunState = Annotation.Root({
  question: Annotation<string>,
  round: Annotation<number>,
  strategyState: Annotation<JsonValue>,
  pending: Annotation<ResearchBrief[]>,
  researchersUsed: Annotation<number>,
  results: Annotation<ResearchResult[]>({ reducer: (a, b) => a.concat(b), default: () => [] }),
  decisions: Annotation<DecisionRecord[]>({ reducer: (a, b) => a.concat(b), default: () => [] }),
  stopReason: Annotation<StopReason | undefined>,
  synthesis: Annotation<SynthesisInput | undefined>,
  synthesisDiagnostics: Annotation<string[]>,
  report: Annotation<string>,
  writerDiagnostics: Annotation<string[]>,
});
export type RunStateType = typeof RunState.State;

interface ResearchTask {
  question: string;
  brief: ResearchBrief;
}

/** Limit concurrent researchers; the limit is an engineering setting only. */
function semaphore(limit: number) {
  let active = 0;
  const queue: (() => void)[] = [];
  return async <T>(fn: () => Promise<T>): Promise<T> => {
    if (active >= limit) await new Promise<void>((resolve) => queue.push(resolve));
    active += 1;
    try {
      return await fn();
    } finally {
      active -= 1;
      queue.shift()?.();
    }
  };
}

function checkedState(state: JsonValue): JsonValue {
  const copy = JSON.parse(JSON.stringify(state ?? null)) as JsonValue;
  if (!isDeepStrictEqual(copy, state ?? null)) {
    throw new Error("Strategy state must round-trip through JSON unchanged (see docs/design.md section 3).");
  }
  return copy;
}

export function buildResearchGraph(deps: SkeletonDeps) {
  const { strategy, limits, maxRounds, hooks } = deps;
  const limit = semaphore(Math.max(1, deps.concurrency));

  const ctx = (round: number, used: number): StrategyContext => ({
    model: deps.strategyModel,
    budget: budgetView(limits, used),
    round,
    runId: deps.runId,
  });

  async function applyStep(
    phase: DecisionRecord["phase"],
    step: StrategyStep<JsonValue>,
    round: number,
    used: number,
  ): Promise<Partial<RunStateType>> {
    const strategyState = checkedState(step.state);
    const budget = budgetView(limits, used);
    const applied =
      round > maxRounds
        ? { ...applyDecision(step.decision, round, { ...budget, researchersRemaining: 0 }) }
        : applyDecision(step.decision, round, budget);
    const record: DecisionRecord = {
      phase,
      round,
      rationale: step.decision.rationale,
      stop: step.decision.stop,
      accepted: applied.accepted,
      dropped: applied.dropped,
      ignored: applied.ignored,
      invalid: applied.invalid,
      budgetBefore: budget.researchersRemaining,
      strategyState,
      at: new Date().toISOString(),
    };
    await hooks?.onDecision?.(record);
    let stopReason: StopReason | undefined;
    if (applied.accepted.length === 0) {
      if (step.decision.stop) stopReason = "strategy-stop";
      else if (round > maxRounds) stopReason = "max-rounds";
      else if (budget.researchersRemaining === 0) stopReason = "budget-exhausted";
      else stopReason = "no-briefs";
    }
    return {
      strategyState,
      round,
      pending: applied.accepted,
      researchersUsed: used + applied.accepted.length,
      decisions: [record],
      stopReason,
    };
  }

  const graph = new StateGraph(RunState)
    .addNode(
      "plan",
      async (state: RunStateType) => {
        const step = await strategy.init({ question: state.question }, ctx(1, 0));
        return applyStep("init", step, 1, 0);
      },
      { retryPolicy: { maxAttempts: 3 } },
    )
    .addNode("research", async (task: ResearchTask) => {
      const result = await limit(() => deps.research(task.question, task.brief));
      await hooks?.onResult?.(result);
      return { results: [result] };
    })
    .addNode(
      "observe",
      async (state: RunStateType) => {
        const roundResults = state.results.filter((r) => r.brief.round === state.round);
        const next = state.round + 1;
        const step = await strategy.observe(state.strategyState, roundResults, ctx(next, state.researchersUsed));
        return applyStep("observe", step, next, state.researchersUsed);
      },
      { retryPolicy: { maxAttempts: 3 } },
    )
    .addNode(
      "finalize",
      async (state: RunStateType) => {
        const raw = await strategy.finalize(state.strategyState, ctx(state.round, state.researchersUsed));
        const parsed = SynthesisInputSchema.safeParse(raw);
        const diagnostics: string[] = [];
        let synthesis: SynthesisInput;
        if (parsed.success) synthesis = parsed.data;
        else {
          diagnostics.push(`invalid SynthesisInput, falling back to all notes: ${parsed.error.message.slice(0, 500)}`);
          synthesis = {
            material: state.results.filter((r) => r.status === "ok").map((r) => ({ label: r.brief.objective, notes: r.notes })),
          };
        }
        if (synthesis.material.length === 0) diagnostics.push("synthesis has no material");
        await hooks?.onSynthesis?.(synthesis, diagnostics);
        return { synthesis, synthesisDiagnostics: diagnostics };
      },
      { retryPolicy: { maxAttempts: 3 } },
    )
    .addNode(
      "write",
      async (state: RunStateType) => {
        const out = await deps.write(state.question, state.synthesis!);
        return { report: out.report, writerDiagnostics: out.diagnostics };
      },
      { retryPolicy: { maxAttempts: 3 } },
    )
    .addEdge(START, "plan")
    .addConditionalEdges("plan", dispatch, ["research", "finalize"])
    .addEdge("research", "observe")
    .addConditionalEdges("observe", dispatch, ["research", "finalize"])
    .addEdge("finalize", "write")
    .addEdge("write", END);

  function dispatch(state: RunStateType) {
    if (state.stopReason || state.pending.length === 0) return "finalize";
    return state.pending.map((brief) => new Send("research", { question: state.question, brief } satisfies ResearchTask));
  }

  return graph.compile();
}

export function initialState(question: string): Partial<RunStateType> {
  return {
    question,
    round: 0,
    strategyState: null,
    pending: [],
    researchersUsed: 0,
    stopReason: undefined,
    synthesis: undefined,
    synthesisDiagnostics: [],
    report: "",
    writerDiagnostics: [],
  };
}
