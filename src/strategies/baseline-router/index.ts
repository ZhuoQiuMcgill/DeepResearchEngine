/**
 * Baseline-router strategy: the baseline with a tool-using follow-up router.
 *
 * Planning, researchers, finalize and the writer are the baseline's, unchanged:
 * init and finalize delegate to the baseline module. Only the decision after
 * round 1 differs. The baseline makes it in one structured call over every note;
 * here a router agent looks at the round through tools (budget and usage, one
 * researcher's notes, one researcher's sources, and the provider's built-in
 * code interpreter where there is one) and ends by launching follow-up
 * researchers or finishing. Its tool trace is kept in the strategy state, so it
 * appears in the run record's decisions.
 */
import { z } from "zod";
import { AIMessage, HumanMessage, ToolMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import {
  CONTRACT_VERSION,
  summarizeNotes,
  type JsonValue,
  type ResearchResult,
  type ResearchStrategy,
  type StrategyContext,
  type StrategyModule,
  type StrategyStep,
  type SynthesisInput,
} from "../../core/index.js";
import baseline from "../baseline/index.js";
import { DECIDE_NOW, routerPrompt } from "./prompts.js";
import { buildRouterTools, type Outcome } from "./tools.js";

const OptionsSchema = z
  .object({
    /** Passed to the baseline planner; also caps the follow-up round. */
    maxPerRound: z.number().int().min(1).max(20).default(6),
    /** Most model calls the router may make for one decision. */
    maxRouterCalls: z.number().int().min(2).max(20).default(10),
  })
  .strict();
type RouterOptions = z.infer<typeof OptionsSchema>;

const TRACE_CHARS = 2_000;

/** One step of the router's work, kept as plain JSON. */
type RouterStep =
  | { kind: "tool"; name: string; args: JsonValue; ok: boolean; result: string; ms: number }
  | { kind: "code"; code: string; output: string }
  | { kind: "text"; text: string };

type RouterLog = {
  round: number;
  outcome: "launch" | "finish" | "fallback";
  rationale: string;
  modelCalls: number;
  inputTokens: number;
  outputTokens: number;
  builtinTool: string;
  steps: RouterStep[];
};

/** The baseline's state plus the router's trace. Plain JSON. */
type RouterState = {
  question: string;
  interpretation: string;
  rounds: number;
  notes: { briefId: string; objective: string; notes: string }[];
  failures: { briefId: string; objective: string; failure: string }[];
  router: RouterLog[];
};

export class BaselineRouterStrategy implements ResearchStrategy<RouterState> {
  readonly name = "baseline-router";
  private readonly inner: ResearchStrategy<any>;

  constructor(private readonly options: RouterOptions = OptionsSchema.parse({})) {
    this.inner = baseline.create({ maxPerRound: options.maxPerRound });
  }

  async init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<RouterState>> {
    const step = await this.inner.init(input, ctx);
    return { state: { ...(step.state as Omit<RouterState, "router">), router: [] }, decision: step.decision };
  }

  async observe(state: RouterState, results: ResearchResult[], ctx: StrategyContext): Promise<StrategyStep<RouterState>> {
    // Same bookkeeping as the baseline, so finalize sees the same notes.
    const next: RouterState = {
      ...state,
      rounds: state.rounds + 1,
      notes: [
        ...state.notes,
        ...results.filter((r) => r.status === "ok").map((r) => ({ briefId: r.brief.id, objective: r.brief.objective, notes: r.notes })),
      ],
      failures: [
        ...state.failures,
        ...results
          .filter((r) => r.status === "failed")
          .map((r) => ({ briefId: r.brief.id, objective: r.brief.objective, failure: `${r.failure?.kind}: ${r.failure?.message ?? ""}`.slice(0, 300) })),
      ],
    };
    if (next.rounds >= 2) {
      return { state: next, decision: { briefs: [], stop: true, rationale: "The single follow-up round is complete." } };
    }
    if (ctx.budget.researchersRemaining === 0) {
      return { state: next, decision: { briefs: [], stop: true, rationale: "No researcher budget left for a follow-up round." } };
    }

    const maxBriefs = Math.min(this.options.maxPerRound, ctx.budget.researchersRemaining);
    const { outcome, log } = await this.route(state.question, results, ctx, maxBriefs);
    const stateOut: RouterState = { ...next, router: [...next.router, log] };
    if (outcome.kind === "launch") {
      return { state: stateOut, decision: { briefs: outcome.briefs, stop: false, rationale: outcome.rationale } };
    }
    return { state: stateOut, decision: { briefs: [], stop: true, rationale: outcome.rationale } };
  }

  async finalize(state: RouterState, ctx: StrategyContext): Promise<SynthesisInput> {
    return this.inner.finalize(state, ctx);
  }

  /** The router agent: a tool loop that ends with launch_followups or finish_research. */
  private async route(question: string, results: ResearchResult[], ctx: StrategyContext, maxBriefs: number) {
    const tools = buildRouterTools({ results, budget: ctx.budget, maxBriefs, round: ctx.round });
    const builtin = builtinTool(ctx.model);
    const definitions = builtin ? [...tools.definitions, builtin.definition] : tools.definitions;
    const model = ctx.model.bindTools!(definitions, builtin?.callOptions ?? {});
    const overview = results
      .map((r) =>
        r.status === "ok"
          ? `### ${r.brief.id}: ${r.brief.objective}\n${summarizeNotes(r.notes)}`
          : `### ${r.brief.id}: ${r.brief.objective}\nFAILED (${r.failure?.kind ?? "unknown"})`,
      )
      .join("\n\n");
    const messages: BaseMessage[] = await routerPrompt.formatMessages({
      today: ctx.today,
      question,
      maxBriefs: String(maxBriefs),
      overview,
    });

    const log: RouterLog = {
      round: ctx.round,
      outcome: "fallback",
      rationale: "",
      modelCalls: 0,
      inputTokens: 0,
      outputTokens: 0,
      builtinTool: builtin?.name ?? "none",
      steps: [],
    };
    let nudged = false;
    for (let call = 0; call < this.options.maxRouterCalls && !tools.outcome(); call++) {
      const ai = (await model.invoke(messages)) as AIMessage;
      messages.push(ai);
      log.modelCalls += 1;
      log.inputTokens += ai.usage_metadata?.input_tokens ?? 0;
      log.outputTokens += ai.usage_metadata?.output_tokens ?? 0;
      for (const out of builtinOutputs(ai)) log.steps.push(out);
      const text = textOf(ai);
      if (text) log.steps.push({ kind: "text", text: clip(text) });

      if (!ai.tool_calls?.length) {
        if (nudged) break;
        nudged = true;
        messages.push(new HumanMessage(DECIDE_NOW));
        continue;
      }
      for (const tc of ai.tool_calls) {
        const started = Date.now();
        const res = tools.run(tc.name, tc.args);
        log.steps.push({ kind: "tool", name: tc.name, args: toJson(tc.args), ok: res.ok, result: clip(res.text), ms: Date.now() - started });
        messages.push(new ToolMessage({ content: res.text, tool_call_id: tc.id ?? tc.name }));
      }
    }

    const outcome: Outcome = tools.outcome() ?? {
      kind: "finish",
      rationale: `The router made no decision within ${this.options.maxRouterCalls} model calls, so no follow-up round is launched.`,
    };
    log.outcome = tools.outcome() ? outcome.kind : "fallback";
    log.rationale = outcome.rationale;
    return { outcome, log };
  }
}

/** The provider's built-in code tool, where the platform's model supports one. */
function builtinTool(model: BaseChatModel) {
  const type = (model as unknown as { _llmType?: () => string })._llmType?.();
  if (type === "openai") {
    return {
      name: "code_interpreter",
      definition: { type: "code_interpreter", container: { type: "auto" } },
      callOptions: { strict: true, include: ["code_interpreter_call.outputs"] } as Record<string, unknown>,
    };
  }
  // Other providers run the router with the custom tools only (not tested yet).
  return undefined;
}

/** Code the built-in interpreter ran in this response, with its output. */
function builtinOutputs(ai: AIMessage): RouterStep[] {
  const items = (ai.additional_kwargs as { tool_outputs?: { type?: string; code?: string; outputs?: { type?: string; logs?: string }[] | null }[] })
    .tool_outputs;
  return (items ?? [])
    .filter((o) => o.type === "code_interpreter_call")
    .map((o) => ({
      kind: "code" as const,
      code: clip(o.code ?? ""),
      output: clip((o.outputs ?? []).map((x) => x.logs ?? `[${x.type}]`).join("\n")),
    }));
}

function textOf(ai: AIMessage): string {
  if (typeof ai.content === "string") return ai.content.trim();
  return ai.content
    .map((b) => ((b as { type?: string }).type === "text" ? String((b as { text?: string }).text ?? "") : ""))
    .join("")
    .trim();
}

function clip(s: string): string {
  return s.length > TRACE_CHARS ? `${s.slice(0, TRACE_CHARS)}… (${s.length - TRACE_CHARS} more characters)` : s;
}

function toJson(v: unknown): JsonValue {
  return JSON.parse(JSON.stringify(v ?? null)) as JsonValue;
}

const baselineRouter: StrategyModule = {
  name: "baseline-router",
  description:
    "Baseline with a tool-using follow-up router: after round 1 an agent inspects budget, notes and sources with tools and launches follow-up researchers or finishes.",
  contractVersion: CONTRACT_VERSION,
  create: (options?: JsonValue) => new BaselineRouterStrategy(OptionsSchema.parse(options ?? {})),
};
export default baselineRouter;
