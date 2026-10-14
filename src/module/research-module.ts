/**
 * The research module: one question, one strategy, one model profile.
 * Builds the role models, the researcher and the writer, runs the skeleton
 * graph and returns the outcome. It writes no files and reads no CLI or
 * environment settings; the platform injects everything.
 */
import type { Callbacks } from "@langchain/core/callbacks/manager";
import { createChatModel, type ModelProfile } from "../config/models.js";
import { citationBinding, unknownCitations } from "../core/citations.js";
import type { ResearchResult, SynthesisInput } from "../core/contracts.js";
import type { ResearchStrategy } from "../core/strategy.js";
import { extractUrls } from "../core/urls.js";
import { buildResearchGraph, initialState, type DecisionRecord, type RunStateType, type SkeletonHooks, type StopReason } from "../graph/skeleton.js";
import type { UsageLedger } from "../observability/usage.js";
import { createResearcher } from "../research/researcher.js";
import { createWriter } from "../writer/writer.js";

export interface ResearchModuleInput {
  question: string;
  strategy: ResearchStrategy<any>;
  profile: ModelProfile;
  researchersTotal: number;
  maxRounds: number;
  concurrency: number;
  researcherTimeoutMs: number;
  runId: string;
  today: string;
  ledger: UsageLedger;
  hooks?: SkeletonHooks;
  /** Tracing callbacks; nested model calls inherit them. */
  callbacks?: Callbacks;
}

export interface CitationCheck {
  reportUrls: number;
  unknownUrls: string[];
  binding: ReturnType<typeof citationBinding>;
}

export interface ResearchModuleOutput {
  status: "ok" | "error";
  error?: string;
  report: string;
  results: ResearchResult[];
  decisions: DecisionRecord[];
  synthesis?: SynthesisInput;
  stopReason?: StopReason;
  researchersUsed: number;
  citationCheck: CitationCheck;
  diagnostics: string[];
}

export function citationCheck(report: string, results: ResearchResult[]): CitationCheck {
  return { reportUrls: extractUrls(report).length, unknownUrls: unknownCitations(report, results), binding: citationBinding(report, results) };
}

export async function runResearchModule(input: ResearchModuleInput): Promise<ResearchModuleOutput> {
  const { profile, ledger, today } = input;
  const graph = buildResearchGraph({
    strategy: input.strategy,
    strategyModel: createChatModel(profile, [ledger.handler("strategy")]),
    research: createResearcher({ profile, ledger, timeoutMs: input.researcherTimeoutMs, today }),
    write: createWriter(createChatModel(profile, [ledger.handler("writer")]), today),
    limits: { researchersTotal: input.researchersTotal, toolCallsPerResearcher: profile.toolCallsPerResearcher },
    maxRounds: input.maxRounds,
    concurrency: input.concurrency,
    runId: input.runId,
    today,
    ...(input.hooks ? { hooks: input.hooks } : {}),
  });

  let final: RunStateType | undefined;
  let error: string | undefined;
  try {
    final = (await graph.invoke(initialState(input.question), {
      recursionLimit: 100,
      callbacks: input.callbacks ?? [],
      runName: `research:${input.strategy.name}:${profile.name}`,
      metadata: { runId: input.runId, strategy: input.strategy.name, profile: profile.name },
    })) as RunStateType;
  } catch (err) {
    error = String((err as Error)?.stack ?? err);
  }

  const results = final?.results ?? [];
  const report = final?.report ?? "";
  return {
    status: error || !report ? "error" : "ok",
    ...(error ? { error } : {}),
    report,
    results,
    decisions: final?.decisions ?? [],
    ...(final?.synthesis ? { synthesis: final.synthesis } : {}),
    ...(final?.stopReason ? { stopReason: final.stopReason } : {}),
    researchersUsed: final?.researchersUsed ?? 0,
    citationCheck: citationCheck(report, results),
    diagnostics: [
      ...(final?.synthesisDiagnostics ?? []).map((d) => `synthesis: ${d}`),
      ...(final?.writerDiagnostics ?? []).map((d) => `writer: ${d}`),
      ...results.flatMap((r) => r.diagnostics.map((d) => `${r.brief.id}: ${d}`)),
    ],
  };
}
