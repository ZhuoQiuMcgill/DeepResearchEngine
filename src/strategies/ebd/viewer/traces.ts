/**
 * Langfuse traces for the run viewer.
 *
 * When the LANGFUSE_* variables are set, the platform traces every run to the team's
 * self-hosted Langfuse: LangChain's callback handler (@langfuse/langchain) records each
 * LangGraph step and each LangChain model call as an observation, with the run ID as the
 * session (src/observability/langfuse.ts). This module reads a run's observations back
 * through the public API (GET /api/public/v2/observations, filtered by session) and caches
 * a copy under local/viewer/traces/, so the pages still open without Langfuse running.
 *
 * Inputs and outputs are cut to MAX_IO characters in the copy; the full text stays in
 * Langfuse, which each page links to.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

export const TRACE_DIR = resolve("local/viewer/traces");
const MAX_IO = 6000;
const FIELDS = "core,basic,time,io,metadata,model,usage,metrics";

/** The fields of an observation the viewer uses (Observations API v2 field groups). */
export type Observation = {
  id: string;
  traceId: string;
  projectId: string;
  parentObservationId: string | null;
  type: string;
  name: string | null;
  startTime: string;
  endTime: string | null;
  level?: string;
  statusMessage?: string | null;
  model?: string | null;
  input?: string | null;
  output?: string | null;
  metadata?: unknown;
  usageDetails?: Record<string, number>;
  costDetails?: Record<string, number>;
  totalCost?: number | null;
  latency?: number | null;
  timeToFirstToken?: number | null;
};

export type RunTrace = {
  sessionId: string;
  baseUrl: string;
  projectId: string | null;
  fetchedAt: string;
  observations: Observation[];
};

export type LangfuseConfig = { publicKey: string; secretKey: string; baseUrl: string };

/** The Langfuse keys from the environment, or null when tracing is not configured. */
export function langfuseConfig(env: NodeJS.ProcessEnv = process.env): LangfuseConfig | null {
  const publicKey = env.LANGFUSE_PUBLIC_KEY?.trim();
  const secretKey = env.LANGFUSE_SECRET_KEY?.trim();
  if (!publicKey || !secretKey) return null;
  return { publicKey, secretKey, baseUrl: (env.LANGFUSE_BASE_URL?.trim() || "http://localhost:3000").replace(/\/+$/, "") };
}

function cut(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > MAX_IO ? `${text.slice(0, MAX_IO)}… [${text.length - MAX_IO} more characters in Langfuse]` : text;
}

/** All pages of one observations query. */
async function query(cfg: LangfuseConfig, filter: Record<string, string>, fetchImpl: typeof fetch): Promise<Observation[]> {
  const auth = `Basic ${Buffer.from(`${cfg.publicKey}:${cfg.secretKey}`).toString("base64")}`;
  const out: Observation[] = [];
  let cursor: string | null = null;
  do {
    const params = new URLSearchParams({ ...filter, fields: FIELDS, limit: "1000" });
    if (cursor) params.set("cursor", cursor);
    const res = await fetchImpl(`${cfg.baseUrl}/api/public/v2/observations?${params}`, { headers: { Authorization: auth } });
    if (!res.ok) throw new Error(`Langfuse returned ${res.status}: ${(await res.text()).slice(0, 300)}`);
    const body = (await res.json()) as { data: Observation[]; meta?: { cursor?: string | null } };
    out.push(...body.data);
    cursor = body.meta?.cursor ?? null;
  } while (cursor);
  return out;
}

/**
 * Every observation of one session within a start-time window. The session is a trace-level
 * attribute, which the LangChain handler may set on the root observation only, so the run's
 * traces are found by session and their observations are then read by trace ID.
 */
export async function fetchSession(cfg: LangfuseConfig, sessionId: string, window: { from: string; to: string }, fetchImpl: typeof fetch = fetch): Promise<Observation[]> {
  const bounds = { fromStartTime: window.from, toStartTime: window.to };
  const tagged = await query(cfg, { ...bounds, sessionId }, fetchImpl);
  const byId = new Map(tagged.map((o) => [o.id, o]));
  for (const traceId of new Set(tagged.map((o) => o.traceId))) {
    for (const o of await query(cfg, { ...bounds, traceId }, fetchImpl)) byId.set(o.id, o);
  }
  return [...byId.values()].map((o) => ({ ...o, input: cut(o.input), output: cut(o.output) })).sort((a, b) => a.startTime.localeCompare(b.startTime));
}

export function tracePath(runId: string): string {
  return join(TRACE_DIR, `${runId}.json`);
}

/** The cached trace of a run, if one was fetched. */
export function readTrace(runId: string): RunTrace | null {
  const path = tracePath(runId);
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, "utf8")) as RunTrace;
  } catch {
    return null;
  }
}

type RunInfo = { runId: string; dir: string };

/** The start-time window of a run: its first and last record, with margins for clock skew and the writer. */
function windowOf(dir: string): { from: string; to: string } | null {
  const events = existsSync(join(dir, "events.jsonl")) ? readFileSync(join(dir, "events.jsonl"), "utf8").split("\n").filter(Boolean) : [];
  const times = events.flatMap((l) => {
    try {
      return [Date.parse((JSON.parse(l) as { at: string }).at)];
    } catch {
      return [];
    }
  });
  if (!times.length) return null;
  return { from: new Date(Math.min(...times) - 10 * 60_000).toISOString(), to: new Date(Math.max(...times) + 30 * 60_000).toISOString() };
}

/**
 * Fetch and cache the trace of every finished run that has none cached yet (or of all, with
 * refresh). Runs that sent no trace (Langfuse off at the time) are skipped quietly.
 */
export async function syncTraces(runs: RunInfo[], options: { refresh?: boolean; cfg?: LangfuseConfig | null; log?: (line: string) => void } = {}) {
  const cfg = options.cfg === undefined ? langfuseConfig() : options.cfg;
  const log = options.log ?? (() => {});
  const counts = { fetched: 0, cached: 0, none: 0, failed: 0 };
  if (!cfg) return { ...counts, enabled: false };
  mkdirSync(TRACE_DIR, { recursive: true });
  for (const run of runs) {
    if (!options.refresh && readTrace(run.runId)) {
      counts.cached++;
      continue;
    }
    // A run still in progress would give a partial trace.
    if (!existsSync(join(run.dir, "summary.json"))) continue;
    const window = windowOf(run.dir);
    if (!window) continue;
    try {
      const observations = await fetchSession(cfg, run.runId, window);
      if (!observations.length) {
        counts.none++;
        continue;
      }
      const trace: RunTrace = { sessionId: run.runId, baseUrl: cfg.baseUrl, projectId: observations[0]!.projectId ?? null, fetchedAt: new Date().toISOString(), observations };
      writeFileSync(tracePath(run.runId), JSON.stringify(trace), "utf8");
      counts.fetched++;
      log(`trace of ${run.runId}: ${observations.length} observations`);
    } catch (err) {
      counts.failed++;
      log(`trace of ${run.runId} not fetched: ${(err as Error).message}`);
    }
  }
  return { ...counts, enabled: true };
}
