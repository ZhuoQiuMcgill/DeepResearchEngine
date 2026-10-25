/**
 * Routed-review strategy: baseline-router with a review team in front of the
 * router. Not a baseline: it is the stronger, non-EBD arm.
 *
 * After every round, one notes reviewer per successful researcher assesses that
 * researcher's notes (in parallel), and the conflict checker compares the
 * figures researchers report for the same quantity (whenever two or more
 * researchers reported figures). After round 1 the router starts from those
 * findings and launches follow-up researchers or finishes. After round 2 the
 * strategy stops, and finalize passes the disagreements still open to the
 * writer as guidance. Planning, researchers and the writer are the baseline's.
 */
import { z } from "zod";
import { AIMessage, HumanMessage, ToolMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import {
  CONTRACT_VERSION,
  type JsonValue,
  type ResearchResult,
  type ResearchStrategy,
  type StrategyContext,
  type StrategyModule,
  type StrategyStep,
  type SynthesisInput,
} from "../../core/index.js";
import baseline from "../baseline/index.js";
import { checkFigures, disagreements, type CheckRecord } from "./checker.js";
import { DECIDE_NOW, routerPrompt } from "./prompts.js";
import { reviewNotes, type Figure, type Review } from "./reviewer.js";
import { buildRouterTools, type Outcome } from "./tools.js";

const OptionsSchema = z
  .object({
    /** Passed to the baseline planner; also caps the follow-up round. */
    maxPerRound: z.number().int().min(1).max(20).default(6),
    /** Most model calls the router may make for one decision. */
    maxRouterCalls: z.number().int().min(2).max(20).default(10),
  })
  .strict();
type Options = z.infer<typeof OptionsSchema>;

const TRACE_CHARS = 2_000;

type RouterStep =
  | { kind: "tool"; name: string; args: JsonValue; ok: boolean; result: string; ms: number }
  | { kind: "text"; text: string };

type RouterLog = {
  round: number;
  outcome: "launch" | "finish" | "fallback";
  rationale: string;
  modelCalls: number;
  inputTokens: number;
  outputTokens: number;
  steps: RouterStep[];
};

/** The baseline's state plus the review team's records and the router's trace. Plain JSON. */
type RoutedState = {
  question: string;
  interpretation: string;
  rounds: number;
  notes: { briefId: string; objective: string; notes: string }[];
  failures: { briefId: string; objective: string; failure: string }[];
  reviews: Review[];
  checks: CheckRecord[];
  router: RouterLog[];
};

export class RoutedReviewStrategy implements ResearchStrategy<RoutedState> {
  readonly name = "routed-review";
  private readonly inner: ResearchStrategy<any>;

  constructor(private readonly options: Options = OptionsSchema.parse({})) {
    this.inner = baseline.create({ maxPerRound: options.maxPerRound });
  }

  async init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<RoutedState>> {
    const step = await this.inner.init(input, ctx);
    return { state: { ...(step.state as Omit<RoutedState, "reviews" | "checks" | "router">), reviews: [], checks: [], router: [] }, decision: step.decision };
  }

  async observe(state: RoutedState, results: ResearchResult[], ctx: StrategyContext): Promise<StrategyStep<RoutedState>> {
    const ok = results.filter((r) => r.status === "ok");
    // Static part of the orchestration: every round is reviewed, then checked.
    const reviews = await Promise.all(ok.map((result) => reviewNotes(ctx.model, { question: state.question, today: ctx.today, result })));
    const allReviews = [...state.reviews, ...reviews];
    const check = await checkFigures(ctx.model, { question: state.question, figures: allReviews.flatMap((v) => v.figures), round: state.rounds + 1 });

    const next: RoutedState = {
      ...state,
      rounds: state.rounds + 1,
      notes: [...state.notes, ...ok.map((r) => ({ briefId: r.brief.id, objective: r.brief.objective, notes: r.notes }))],
      failures: [
        ...state.failures,
        ...results
          .filter((r) => r.status === "failed")
          .map((r) => ({ briefId: r.brief.id, objective: r.brief.objective, failure: `${r.failure?.kind}: ${r.failure?.message ?? ""}`.slice(0, 300) })),
      ],
      reviews: allReviews,
      checks: [...state.checks, check],
    };
    if (next.rounds >= 2) {
      return { state: next, decision: { briefs: [], stop: true, rationale: "The single follow-up round is complete; its notes were reviewed and checked." } };
    }
    if (ctx.budget.researchersRemaining === 0) {
      return { state: next, decision: { briefs: [], stop: true, rationale: "No researcher budget left for a follow-up round." } };
    }

    // Dynamic part: the router decides whether a follow-up round goes out, and what it researches.
    const maxBriefs = Math.min(this.options.maxPerRound, ctx.budget.researchersRemaining);
    const { outcome, log } = await this.route(state.question, results, reviews, check, allReviews, ctx, maxBriefs);
    const stateOut: RoutedState = { ...next, router: [...next.router, log] };
    if (outcome.kind === "launch") {
      return { state: stateOut, decision: { briefs: outcome.briefs, stop: false, rationale: outcome.rationale } };
    }
    return { state: stateOut, decision: { briefs: [], stop: true, rationale: outcome.rationale } };
  }

  async finalize(state: RoutedState, ctx: StrategyContext): Promise<SynthesisInput> {
    const synthesis = await this.inner.finalize(state, ctx);
    const figures = new Map(state.reviews.flatMap((v) => v.figures).map((f) => [f.id, f]));
    const conflicts = conflictGuidance(state.checks.at(-1), figures);
    if (!conflicts) return synthesis;
    return { ...synthesis, guidance: [synthesis.guidance, conflicts].filter(Boolean).join("\n\n") };
  }

  /** The router agent: a tool loop that ends with launch_followups or finish_research. */
  private async route(
    question: string,
    results: ResearchResult[],
    reviews: Review[],
    check: CheckRecord,
    allReviews: Review[],
    ctx: StrategyContext,
    maxBriefs: number,
  ) {
    const tools = buildRouterTools({ results, reviews, check, budget: ctx.budget, maxBriefs, round: ctx.round });
    const model = ctx.model.bindTools!(tools.definitions, strictOptions(ctx.model));
    const figures = new Map(allReviews.flatMap((v) => v.figures).map((f) => [f.id, f]));
    const messages: BaseMessage[] = await routerPrompt.formatMessages({
      today: ctx.today,
      question,
      maxBriefs: String(maxBriefs),
      overview: overview(results, reviews, check, figures),
    });

    const log: RouterLog = { round: ctx.round, outcome: "fallback", rationale: "", modelCalls: 0, inputTokens: 0, outputTokens: 0, steps: [] };
    let nudged = false;
    for (let call = 0; call < this.options.maxRouterCalls && !tools.outcome(); call++) {
      const ai = (await model.invoke(messages)) as AIMessage;
      messages.push(ai);
      log.modelCalls += 1;
      log.inputTokens += ai.usage_metadata?.input_tokens ?? 0;
      log.outputTokens += ai.usage_metadata?.output_tokens ?? 0;
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

/** What the router sees first: each researcher's review and the checker's findings. Exported for unit tests. */
export function overview(results: ResearchResult[], reviews: Review[], check: CheckRecord, figures: Map<string, Figure>): string {
  const reviewOf = new Map(reviews.map((v) => [v.briefId, v]));
  const researchers = results.map((r) => {
    const head = `### ${r.brief.id}: ${r.brief.objective}`;
    if (r.status === "failed") return `${head}\nFAILED (${r.failure?.kind ?? "unknown"})`;
    const v = reviewOf.get(r.brief.id);
    if (!v?.ok) return `${head}\nReview unavailable${v ? ` (${v.error})` : ""}; use read_notes.`;
    const lines = r.brief.keyQuestions.map((q, i) => {
      const k = v.keyQuestions.find((x) => x.number === i + 1);
      if (!k) return `- Q${i + 1} not assessed: ${q}`;
      return `- Q${i + 1} ${k.status}, sourced ${k.sourced}: ${q}${k.gap ? ` Gap: ${k.gap}` : ""}`;
    });
    lines.push(`Figures reported: ${v.figures.length}.${v.warnings.length ? ` Warnings: ${v.warnings.join(" | ")}` : ""}`);
    return `${head}\n${lines.join("\n")}`;
  });
  return [
    "Round 1, as the notes reviewers assessed it. Use read_notes for a researcher's full notes.",
    researchers.join("\n\n"),
    `## Figure check\n${checkSummary(check, figures)}`,
  ].join("\n\n");
}

function checkSummary(check: CheckRecord, figures: Map<string, Figure>): string {
  if (!check.ran) return `The conflict checker did not run: ${check.reason}.`;
  const found = disagreements(check);
  const pairs = check.groups.flatMap((g) => g.pairs);
  const count = (v: string) => pairs.filter((p) => p.verdict === v).length;
  const lines = [`The checker compared ${check.figures} figures; ${check.groups.length} quantity group(s) were reported by more than one researcher.`];
  for (const { group, pair } of found) {
    const a = figures.get(pair.a)!;
    const b = figures.get(pair.b)!;
    lines.push(
      `- CONFLICT, ${group.quantity}: ${a.briefId} ${show(a, pair.aBase, pair.baseUnit)} vs ${b.briefId} ${show(b, pair.bBase, pair.baseUnit)}; difference ${pct(pair.difference)}. Quotes: "${a.quote}" / "${b.quote}"`,
    );
  }
  lines.push(
    `${found.length ? `${found.length} conflicting pair(s)` : "No conflict"}; ${count("agree")} pair(s) agree; ${count("over_time")} pair(s) differ between dates (a change over time, not a conflict); ${count("incomparable")} pair(s) could not be compared (units or missing dates).`,
  );
  return lines.join("\n");
}

/** Writer guidance for the disagreements left after the last check. Exported for unit tests. */
export function conflictGuidance(check: CheckRecord | undefined, figures: Map<string, Figure>): string {
  const found = disagreements(check);
  if (!found.length) return "";
  const line = ({ group, pair }: (typeof found)[number]) => {
    const a = figures.get(pair.a)!;
    const b = figures.get(pair.b)!;
    const cite = (f: Figure) => `"${f.quote}"${f.url ? ` (${f.url})` : ""}`;
    return `- ${group.quantity}: ${cite(a)} against ${cite(b)}${a.unit !== b.unit ? ` (${show(a, pair.aBase, pair.baseUnit)} vs ${show(b, pair.bBase, pair.baseUnit)})` : ""}.`;
  };
  return `Researchers disagree on these figures. Give both values with their sources, and say which source is more authoritative where that is clear:\n${found.map(line).join("\n")}`;
}

function show(f: Figure, base: number | null, baseUnit: string): string {
  const stated = `${f.qualifier === "exact" ? "" : `${f.qualifier} `}${f.value} ${f.unit}`.trim();
  return base !== null && baseUnit && f.unit !== baseUnit ? `${stated} (${base} ${baseUnit})` : stated;
}

function pct(d: number | null): string {
  return d === null ? "n/a" : `${(d * 100).toFixed(1)}%`;
}

/** Strict tool schemas where the provider supports them (OpenAI). */
function strictOptions(model: BaseChatModel): Record<string, unknown> {
  const type = (model as unknown as { _llmType?: () => string })._llmType?.();
  return type === "openai" ? { strict: true } : {};
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

const routedReview: StrategyModule = {
  name: "routed-review",
  description:
    "Not a baseline: baseline planning and writing, with notes reviewers and a conflict checker after every round, and a tool-using router that decides the follow-up round from their findings.",
  contractVersion: CONTRACT_VERSION,
  create: (options?: JsonValue) => new RoutedReviewStrategy(OptionsSchema.parse(options ?? {})),
};
export default routedReview;
