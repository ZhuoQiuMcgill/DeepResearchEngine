/**
 * Platform: experiments. An experiment spec is the single place where tasks,
 * strategies (with options), models, repeats and budgets are chosen; nothing
 * else needs to change to switch them.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { z } from "zod";
import { getProfile } from "../config/models.js";
import { TASKS } from "../config/tasks.js";
import type { JsonValue } from "../core/strategy.js";
import { runOne, type RunSummary } from "./run.js";
import { listStrategies } from "./strategies.js";

const JsonSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([z.string(), z.number(), z.boolean(), z.null(), z.array(JsonSchema), z.record(z.string(), JsonSchema)]),
);

export const ExperimentSpecSchema = z
  .object({
    name: z.string().regex(/^[a-z0-9][a-z0-9_-]*$/i, "letters, digits, - and _ only"),
    description: z.string().optional(),
    /** Task ids from src/config/tasks.ts, or explicit questions (used verbatim). */
    tasks: z
      .array(z.union([z.string(), z.object({ id: z.string(), question: z.string().min(1) })]))
      .min(1),
    /** Strategy directory names, or { name, options, label } for configured variants. */
    strategies: z
      .array(z.union([z.string(), z.object({ name: z.string(), options: JsonSchema.optional(), label: z.string().optional() })]))
      .min(1),
    /** Model profile names from src/config/models.ts. */
    models: z.array(z.string()).min(1),
    repeats: z.number().int().min(1).default(1),
    budget: z.object({ researchersTotal: z.number().int().min(1).default(10) }).default({ researchersTotal: 10 }),
    maxRounds: z.number().int().min(1).default(8),
    /** Researchers running at once inside one run (engineering limit only). */
    concurrency: z.number().int().min(1).default(4),
    /** Runs executing at once. */
    parallelRuns: z.number().int().min(1).default(2),
    researcherTimeoutMs: z.number().int().min(10_000).default(8 * 60_000),
    outDir: z.string().default("local/experiments"),
  })
  .strict();
export type ExperimentSpec = z.input<typeof ExperimentSpecSchema>;

interface Job {
  taskId: string;
  question: string;
  strategy: { name: string; options?: JsonValue; label: string };
  model: string;
  repeat: number;
}

/** Validate names up front so a typo fails before any money is spent. */
export function planJobs(raw: ExperimentSpec): { spec: z.infer<typeof ExperimentSpecSchema>; jobs: Job[] } {
  const spec = ExperimentSpecSchema.parse(raw);
  const available = new Set(listStrategies());
  const tasks = spec.tasks.map((t) => {
    if (typeof t !== "string") return t;
    const question = TASKS[t];
    if (!question) throw new Error(`Unknown task "${t}". Known: ${Object.keys(TASKS).join(", ")}`);
    return { id: t, question };
  });
  const strategies = spec.strategies.map((s) => (typeof s === "string" ? { name: s, label: s } : { ...s, label: s.label ?? s.name }));
  for (const s of strategies) if (!available.has(s.name)) throw new Error(`Unknown strategy "${s.name}". Available: ${[...available].join(", ")}`);
  const labels = strategies.map((s) => s.label);
  if (new Set(labels).size !== labels.length) throw new Error("Each strategy configuration needs a distinct label");
  for (const m of spec.models) getProfile(m);
  const jobs: Job[] = [];
  for (let repeat = 1; repeat <= spec.repeats; repeat++)
    for (const t of tasks)
      for (const strategy of strategies)
        for (const model of spec.models) jobs.push({ taskId: t.id, question: t.question, strategy, model, repeat });
  return { spec, jobs };
}

export interface ExperimentResult {
  dir: string;
  summaries: (RunSummary & { taskId: string; repeat: number })[];
}

export async function runExperiment(raw: ExperimentSpec, log: (line: string) => void = () => {}): Promise<ExperimentResult> {
  const { spec, jobs } = planJobs(raw);
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "-");
  const dir = join(spec.outDir, `${spec.name}-${stamp}`);
  await mkdir(join(dir, "runs"), { recursive: true });
  await writeFile(join(dir, "spec.json"), JSON.stringify(spec, null, 2), "utf8");
  log(`experiment ${spec.name}: ${jobs.length} run(s) -> ${dir}`);

  const summaries: ExperimentResult["summaries"] = [];
  let next = 0;
  const worker = async () => {
    while (next < jobs.length) {
      const job = jobs[next++]!;
      const s = await runOne(
        {
          question: job.question,
          strategy: job.strategy,
          profile: job.model,
          researchersTotal: spec.budget.researchersTotal,
          maxRounds: spec.maxRounds,
          concurrency: spec.concurrency,
          researcherTimeoutMs: spec.researcherTimeoutMs,
          outDir: join(dir, "runs"),
          tags: { experiment: spec.name, task: job.taskId, repeat: job.repeat },
        },
        log,
      );
      summaries.push({ ...s, taskId: job.taskId, repeat: job.repeat });
      log(`done ${summaries.length}/${jobs.length}: ${job.strategy.label}/${job.model}/${job.taskId}#${job.repeat} ${s.status}`);
    }
  };
  await Promise.all(Array.from({ length: Math.min(spec.parallelRuns, jobs.length) }, worker));

  summaries.sort((a, b) => a.taskId.localeCompare(b.taskId) || a.strategy.label.localeCompare(b.strategy.label) || a.profile.localeCompare(b.profile) || a.repeat - b.repeat);
  await writeFile(join(dir, "summaries.json"), JSON.stringify(summaries, null, 2), "utf8");
  await writeFile(join(dir, "results.md"), resultsTable(summaries), "utf8");
  return { dir, summaries };
}

export function resultsTable(summaries: ExperimentResult["summaries"]): string {
  const head = "| task | strategy | model | # | status | stop | researchers | ok/failed | searches | cost | time | unknown URLs | run |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|";
  const rows = summaries.map((s) =>
    `| ${s.taskId} | ${s.strategy.label} | ${s.profile} | ${s.repeat} | ${s.status} | ${s.stopReason ?? "-"} | ${s.researchersUsed}/${s.researchersBudget} | ${s.results.ok}/${s.results.failed} | ${s.searches} | $${s.costUsdEstimate.toFixed(3)} | ${Math.round(s.durationMs / 1000)}s | ${s.citationCheck.unknownUrls.length} | ${s.runId} |`,
  );
  return [head, ...rows].join("\n") + "\n";
}
