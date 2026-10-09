/**
 * Platform: one run. Resolves the strategy module and model profile by name,
 * sets up records, usage accounting and tracing, runs the research module and
 * writes the run record.
 */
import { createHash, randomBytes } from "node:crypto";
import { getProfile, type ModelProfile } from "../config/models.js";
import type { ResearchResult } from "../core/contracts.js";
import type { JsonValue } from "../core/strategy.js";
import type { DecisionRecord } from "../graph/skeleton.js";
import { runResearchModule, type CitationCheck } from "../module/research-module.js";
import { startTracing } from "../observability/langfuse.js";
import { UsageLedger } from "../observability/usage.js";
import { RunRecorder } from "./recorder.js";
import { createStrategy } from "./strategies.js";

export interface StrategySelection {
  /** Strategy directory name under src/strategies/. */
  name: string;
  /** Passed to the module's create(); recorded with the run. */
  options?: JsonValue;
  /** Distinguishes configurations of one strategy, e.g. "ebd-no-conflicts". Defaults to name. */
  label?: string;
}

export interface RunSpec {
  question: string;
  strategy: StrategySelection;
  /** Model profile name, see src/config/models.ts. */
  profile: string;
  researchersTotal: number;
  maxRounds: number;
  concurrency: number;
  researcherTimeoutMs: number;
  /** Directory that receives the run record directory. */
  outDir: string;
  /** Extra identifiers recorded with the run, e.g. experiment, task, repeat. */
  tags?: Record<string, string | number>;
}

export interface RunSummary {
  runId: string;
  dir: string;
  status: "ok" | "error";
  error?: string;
  question: string;
  strategy: { name: string; label: string; options?: JsonValue };
  profile: string;
  model: string;
  tags: Record<string, string | number>;
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
  citationCheck: CitationCheck;
  diagnostics: string[];
}

function profileRecord(p: ModelProfile) {
  const { pricing, ...rest } = p;
  return rest;
}

function makeRunId(label: string, profile: string, question: string): string {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "-");
  const hash = createHash("sha256").update(question).digest("hex").slice(0, 6);
  return `${stamp}-${label}-${profile}-${hash}-${randomBytes(2).toString("hex")}`;
}

export async function runOne(spec: RunSpec, log: (line: string) => void = () => {}): Promise<RunSummary> {
  const profile = getProfile(spec.profile);
  const label = spec.strategy.label ?? spec.strategy.name;
  const runId = makeRunId(label, profile.name, spec.question);
  const recorder = new RunRecorder(spec.outDir, runId);
  const today = new Date().toISOString().slice(0, 10);
  await recorder.init({ ...spec, profile: profileRecord(profile), today }, spec.question);
  const ledger = new UsageLedger(profile.pricing);
  const started = Date.now();

  const tracing = await startTracing({ runId, tags: [label, profile.name] });
  let out: Awaited<ReturnType<typeof runResearchModule>>;
  try {
    const strategy = await createStrategy(spec.strategy.name, spec.strategy.options);
    out = await runResearchModule({
      question: spec.question,
      strategy,
      profile,
      researchersTotal: spec.researchersTotal,
      maxRounds: spec.maxRounds,
      concurrency: spec.concurrency,
      researcherTimeoutMs: spec.researcherTimeoutMs,
      runId,
      today,
      ledger,
      ...(tracing.handler ? { callbacks: [tracing.handler] } : {}),
      hooks: {
        onDecision: async (d: DecisionRecord) => {
          await recorder.onDecision(d);
          log(`[${runId}] ${d.phase} -> round ${d.round}: ${d.accepted.length} brief(s)${d.dropped.length ? `, ${d.dropped.length} dropped` : ""}${d.invalid.length ? `, ${d.invalid.length} invalid` : ""}${d.stop ? ", stop" : ""}`);
        },
        onResult: async (r: ResearchResult) => {
          await recorder.onResult(r);
          log(`[${runId}] ${r.brief.id} ${r.status} ${Math.round(r.durationMs / 1000)}s searches=${r.usage.searches} reads=${r.usage.pageReads}${r.diagnostics.length ? ` diag=${r.diagnostics.length}` : ""}`);
        },
        onSynthesis: (s, d) => recorder.onSynthesis(s, d),
      },
    });
  } catch (err) {
    // Strategy loading or setup failed before the graph ran.
    out = {
      status: "error",
      error: String((err as Error)?.stack ?? err),
      report: "",
      results: [],
      decisions: [],
      researchersUsed: 0,
      citationCheck: { reportUrls: 0, unknownUrls: [], binding: { checked: 0, unbound: 0, examples: [] } },
      diagnostics: [],
    };
  } finally {
    await tracing.flush().catch(() => {});
  }

  if (out.error) await recorder.text("error.txt", out.error);
  if (out.report) await recorder.text("report.md", out.report);
  const total = ledger.total();
  const summary: RunSummary = {
    runId,
    dir: recorder.dir,
    status: out.status,
    ...(out.error ? { error: out.error.split("\n")[0]! } : {}),
    question: spec.question,
    strategy: { name: spec.strategy.name, label, ...(spec.strategy.options !== undefined ? { options: spec.strategy.options } : {}) },
    profile: profile.name,
    model: profile.model,
    tags: spec.tags ?? {},
    ...(out.stopReason ? { stopReason: out.stopReason } : {}),
    rounds: Math.max(0, ...out.results.map((r) => r.brief.round)),
    researchersUsed: out.researchersUsed,
    researchersBudget: spec.researchersTotal,
    results: { ok: out.results.filter((r) => r.status === "ok").length, failed: out.results.filter((r) => r.status === "failed").length },
    searches: total.searches,
    pageReads: total.pageReads,
    usageByRole: ledger.byRole,
    totalTokens: { input: total.inputTokens, output: total.outputTokens },
    costUsdEstimate: Math.round(total.costUsd * 10000) / 10000,
    durationMs: Date.now() - started,
    citationCheck: out.citationCheck,
    diagnostics: out.diagnostics,
  };
  await recorder.json("summary.json", summary);
  return summary;
}
