import { useEffect, useState } from "react";
import type { Metrics } from "../server/telemetry";
export type Snapshot = {
  requestId?: string | null;
  model: string;
  busy: boolean;
  runtime: {
    context: number | null;
    slots: number | null;
    engine: string | null;
    modelFile?: string | null;
  };
  metrics: Metrics;
  usage: { requests: number; inputTokens: number; outputTokens: number };
  config: { temperature: number | null; maxOutputTokens: number | null; thinking: string };
};
const number = (n: number | null | undefined, digits = 0) =>
  n == null
    ? "—"
    : n.toLocaleString(undefined, { maximumFractionDigits: digits });
export function usePerformanceSnapshot() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const r = await fetch("/api/telemetry", { signal: abort.signal });
        if (!r.ok) throw new Error();
        setData(await r.json());
        setError(false);
      } catch {
        if (!abort.signal.aborted) setError(true);
      } finally {
        if (!abort.signal.aborted) timer = setTimeout(poll, 750);
      }
    }
    void poll();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, []);
  return { data, error };
}
export type NodePerformance = Pick<
  Snapshot,
  "model" | "runtime" | "metrics" | "config"
>;
export function nodePerformance(
  events: {
    status: string;
    id: string;
    requestId?: string;
    performance?: NodePerformance;
  }[],
  live?: Snapshot | null,
): NodePerformance | undefined {
  const latest = events.at(-1);
  if (
    latest?.status === "running" &&
    live?.requestId === (latest.requestId || latest.id)
  )
    return live;
  return latest?.performance;
}
export function PerformancePanel({
  data,
  label,
}: {
  data?: NodePerformance;
  label: string;
}) {
  const m = data?.metrics;
  const context = data?.runtime.context;
  const used =
    m?.inputTokens != null && m?.outputTokens != null
      ? m.inputTokens + m.outputTokens
      : null;
  return (
    <section className="performance-panel" aria-label="Node performance">
      <div className="performance-heading">
        <strong>{label}</strong>
      </div>
      <p>
        {data?.model || "No recorded metrics"} · {m?.phase || "not started"}
      </p>
      {!data && (
        <p>
          Run this node to record its performance. Older runs have no saved
          metrics.
        </p>
      )}
      <div className="performance-grid">
        <div>
          <small>Generation · tokens/s</small>
          <strong>{number(m?.tokensPerSecond, 1)}</strong>
        </div>
        <div>
          <small>Prefill · tokens/s</small>
          <strong>{number(m?.prefillPerSecond, 1)}</strong>
        </div>
        <div>
          <small>Input tokens</small>
          <strong>{number(m?.inputTokens)}</strong>
        </div>
        <div>
          <small>Output tokens</small>
          <strong>{number(m?.outputTokens)}</strong>
        </div>
        <div>
          <small>Elapsed</small>
          <strong>
            {m?.started ? `${number(m.elapsedMs / 1000, 1)}s` : "—"}
          </strong>
        </div>
        <div>
          <small>First content</small>
          <strong>
            {m?.firstTokenMs != null
              ? `${number(m.firstTokenMs / 1000, 2)}s`
              : "—"}
          </strong>
        </div>
      </div>
      <h4>Context window · this node</h4>
      <strong>{number(context)} tokens</strong>
      <p>
        Request input + output: {number(used)}
        {context && used != null
          ? ` / ${number(context)} (${number((used / context) * 100, 1)}%)`
          : ""}
      </p>
      <progress
        aria-label="Request context usage"
        max={context || 1}
        value={used ?? 0}
      />
      <h4>Node configuration</h4>
      <dl>
        <dt>Engine</dt>
        <dd>{data?.runtime.engine || "Not reported"}</dd>
        <dt>Model weights</dt>
        <dd>{data?.runtime.modelFile || "Not reported"}</dd>
        <dt>Concurrent slots</dt>
        <dd>{number(data?.runtime.slots)}</dd>
        <dt>Temperature</dt>
        <dd>{data?.config.temperature ?? "—"}</dd>
        <dt>Output limit</dt>
        <dd>{number(data?.config.maxOutputTokens)}</dd>
        <dt>Thinking</dt>
        <dd>{data?.config.thinking || "—"}</dd>
      </dl>
      <p className="performance-note">
        Updates every 0.75s. Speeds and token counts come from the provider;
        missing values stay —. During prefill the provider may not report
        progress. Only the selected node is shown. Completed metrics stay with
        its run history. Elapsed and first-content time include search where
        applicable. No token estimate is made from text length.
      </p>
    </section>
  );
}
