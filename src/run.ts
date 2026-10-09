/**
 * Runs one research question end to end with a given strategy and model
 * profile, and writes the run record.
 */
import { createHash } from "node:crypto";
import { getProfile, createChatModel, type ModelProfile } from "./config/models.js";
import type { RunConfig } from "./config/run-config.js";
import type { ResearchResult } from "./core/contracts.js";
import { citationBinding, unknownCitations } from "./core/citations.js";
import { extractUrls } from "./core/urls.js";
import { buildResearchGraph, initialState, type DecisionRecord, type RunStateType } from "./graph/skeleton.js";
import { startTracing } from "./observability/langfuse.js";
import { UsageLedger } from "./observability/usage.js";
import { RunRecorder } from "./records/recorder.js";
import { createResearcher } from "./research/researcher.js";
import { createStrategy } from "./strategies/registry.js";
import { createWriter } from "./writer/writer.js";

export interface RunSummary {
  runId: string;
  dir: string;
  status: "ok" | "error";
  error?: string;
  question: string;
  strategy: string;
  profile: string;
  model: string;
  stopReason?: string;
  rounds: number;
  researchersUsed: number;
  researchersBudget: number;
  results: { ok: number; failed: number };
  searches: number;
  pageReads: number;
  usageByRole: UsageLedger["byRole"];
  totalTokens: { input: number; output: number };
  costUsdEstimate: number;
  durationMs: number;
  citationCheck: ReturnType<typeof citationCheck>;
  diagnostics: string[];
}

function profileRecord(p: ModelProfile) {
  const { pricing, ...rest } = p;
  return rest;
}

export function makeRunId(config: RunConfig, question: string): string {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "-");
  const hash = createHash("sha256").update(question).digest("hex").slice(0, 6);
  return `${stamp}-${config.strategy}-${config.profile}-${hash}`;
}

export function citationCheck(report: string, results: ResearchResult[]) {
  return { reportUrls: extractUrls(report).length, unknownUrls: unknownCitations(report, results), binding: citationBinding(report, results) };
}

export async function runResearch(question: string, config: RunConfig, log: (line: string) => void = () => {}): Promise<RunSummary> {
  const profile = getProfile(config.profile);
  const runId = makeRunId(config, question);
  const recorder = new RunRecorder(config.outDir, runId);
  await recorder.init({ ...config, profile: profileRecord(profile) }, question);
  const tracing = await startTracing({ runId, tags: [config.strategy, profile.name] });
  const ledger = new UsageLedger(profile.pricing);
  const today = new Date().toISOString().slice(0, 10);
  const started = Date.now();

  const graph = buildResearchGraph({
    strategy: createStrategy(config.strategy),
    strategyModel: createChatModel(profile, [ledger.handler("strategy")]),
    research: createResearcher({ profile, ledger, timeoutMs: config.researcherTimeoutMs, today }),
    write: createWriter(createChatModel(profile, [ledger.handler("writer")]), today),
    limits: { researchersTotal: config.researchersTotal, toolCallsPerResearcher: profile.toolCallsPerResearcher },
    maxRounds: config.maxRounds,
    concurrency: config.concurrency,
    runId,
    hooks: {
      onDecision: async (d: DecisionRecord) => {
        await recorder.onDecision(d);
        log(`[${runId}] ${d.phase} -> round ${d.round}: ${d.accepted.length} brief(s)${d.dropped.length ? `, ${d.dropped.length} dropped` : ""}${d.stop ? ", stop" : ""}`);
      },
      onResult: async (r: ResearchResult) => {
        await recorder.onResult(r);
        log(`[${runId}] ${r.brief.id} ${r.status} ${Math.round(r.durationMs / 1000)}s searches=${r.usage.searches} reads=${r.usage.pageReads} cited=${r.sources.filter((s) => s.cited).length}${r.diagnostics.length ? ` diag=${r.diagnostics.length}` : ""}`);
      },
      onSynthesis: (s, d) => recorder.onSynthesis(s, d),
    },
  });

  let final: RunStateType | undefined;
  let error: string | undefined;
  try {
    final = (await graph.invoke(initialState(question), {
      recursionLimit: 100,
      callbacks: tracing.handler ? [tracing.handler] : [],
      runName: `research:${config.strategy}:${profile.name}`,
      metadata: { runId, strategy: config.strategy, profile: profile.name },
    })) as RunStateType;
  } catch (err) {
    error = String((err as Error)?.stack ?? err);
    await recorder.text("error.txt", error);
  } finally {
    await tracing.flush().catch(() => {});
  }

  const results = final?.results ?? [];
  const report = final?.report ?? "";
  if (report) await recorder.text("report.md", report);
  const total = ledger.total();
  const diagnostics = [
    ...(final?.synthesisDiagnostics ?? []).map((d) => `synthesis: ${d}`),
    ...(final?.writerDiagnostics ?? []).map((d) => `writer: ${d}`),
    ...results.flatMap((r) => r.diagnostics.map((d) => `${r.brief.id}: ${d}`)),
  ];
  const summary: RunSummary = {
    runId,
    dir: recorder.dir,
    status: error || !report ? "error" : "ok",
    ...(error ? { error: error.split("\n")[0] } : {}),
    question,
    strategy: config.strategy,
    profile: profile.name,
    model: profile.model,
    ...(final?.stopReason ? { stopReason: final.stopReason } : {}),
    rounds: Math.max(0, ...results.map((r) => r.brief.round)),
    researchersUsed: final?.researchersUsed ?? 0,
    researchersBudget: config.researchersTotal,
    results: { ok: results.filter((r) => r.status === "ok").length, failed: results.filter((r) => r.status === "failed").length },
    searches: total.searches,
    pageReads: total.pageReads,
    usageByRole: ledger.byRole,
    totalTokens: { input: total.inputTokens, output: total.outputTokens },
    costUsdEstimate: Math.round(total.costUsd * 10000) / 10000,
    durationMs: Date.now() - started,
    citationCheck: citationCheck(report, results),
    diagnostics,
  };
  await recorder.json("summary.json", summary);
  return summary;
}
