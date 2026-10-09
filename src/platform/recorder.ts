/**
 * Local run records under local/runs/<runId>/. They are the input for
 * analysis and later blind judging, and are independent of Langfuse.
 */
import { mkdir, writeFile, appendFile } from "node:fs/promises";
import { join } from "node:path";
import type { ResearchResult, SynthesisInput } from "../core/contracts.js";
import type { DecisionRecord, SkeletonHooks } from "../graph/skeleton.js";

export class RunRecorder implements SkeletonHooks {
  readonly dir: string;

  constructor(outDir: string, readonly runId: string) {
    this.dir = join(outDir, runId);
  }

  async init(config: unknown, question: string): Promise<void> {
    await mkdir(join(this.dir, "results"), { recursive: true });
    await this.json("config.json", config);
    await writeFile(join(this.dir, "question.txt"), question, "utf8");
  }

  async event(type: string, data: unknown): Promise<void> {
    await appendFile(join(this.dir, "events.jsonl"), JSON.stringify({ type, at: new Date().toISOString(), data }) + "\n", "utf8");
  }

  async onDecision(record: DecisionRecord): Promise<void> {
    await this.event("decision", record);
  }

  async onResult(result: ResearchResult): Promise<void> {
    const base = join(this.dir, "results", result.brief.id);
    await writeFile(`${base}.md`, result.notes || `(failed: ${result.failure?.kind}: ${result.failure?.message})`, "utf8");
    await writeFile(`${base}.json`, JSON.stringify(result, null, 2), "utf8");
    await this.event("result", {
      id: result.brief.id,
      status: result.status,
      failure: result.failure,
      usage: result.usage,
      sources: result.sources.length,
      cited: result.sources.filter((s) => s.cited).length,
      queries: result.queries.length,
      durationMs: result.durationMs,
      diagnostics: result.diagnostics,
    });
  }

  async onSynthesis(synthesis: SynthesisInput, diagnostics: string[]): Promise<void> {
    await this.json("synthesis.json", { synthesis, diagnostics });
  }

  async json(name: string, data: unknown): Promise<void> {
    await writeFile(join(this.dir, name), JSON.stringify(data, null, 2), "utf8");
  }

  async text(name: string, data: string): Promise<void> {
    await writeFile(join(this.dir, name), data, "utf8");
  }
}
