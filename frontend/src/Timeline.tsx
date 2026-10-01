import { useEffect, useState } from "react";
import type { RunEvent } from "./workflow";

export function Timeline({
  events,
  live,
  onSelect,
}: {
  events: RunEvent[];
  live: boolean;
  onSelect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, [live]);
  const start = events.length ? Date.parse(events[0].time) : 0;
  const end = Math.max(
    start + 1,
    ...events.map((e) => Date.parse(e.time)),
    live ? now : 0,
  );
  const span = end - start;
  const groups = [...new Set(events.map((e) => e.nodeId))].map((id) => {
    const logs = events.filter((e) => e.nodeId === id);
    const first = logs[0],
      last = logs[logs.length - 1];
    const until = last.status === "running" ? end : Date.parse(last.time);
    return {
      id,
      logs,
      first,
      last,
      offset: Date.parse(first.time) - start,
      duration: Math.max(0, until - Date.parse(first.time)),
    };
  });
  return (
    <div className="waterfall" aria-label="Node execution timeline">
      <div className="waterfall-head">
        <span>Node / status</span>
        <span>Duration</span>
        <div className="time-ruler">
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <span key={t}>{((span * t) / 1000).toFixed(1)}s</span>
          ))}
        </div>
      </div>
      {groups.map((row) => (
        <div key={row.id}>
          <button
            className={`waterfall-row ${expanded === row.id ? "active" : ""}`}
            aria-expanded={expanded === row.id}
            onClick={() => {
              setExpanded(expanded === row.id ? null : row.id);
              onSelect(row.id);
            }}
          >
            <span className="waterfall-name">
              <strong>{row.first.label}</strong>
              <small>
                {row.last.status} · {row.logs.length} logs
              </small>
            </span>
            <span>{(row.duration / 1000).toFixed(2)}s</span>
            <span className="time-track">
              <span
                className={`time-bar ${row.last.status}`}
                style={{
                  left: `${(row.offset / span) * 100}%`,
                  width: `${Math.max(0.5, (row.duration / span) * 100)}%`,
                }}
              />
            </span>
          </button>
          {expanded === row.id && (
            <div className="node-logs">
              <div className="log-note">
                Recorded demo activity · elapsed time includes pauses
              </div>
              {row.logs.map((log) => (
                <article key={log.id}>
                  <div>
                    <time>{new Date(log.time).toLocaleTimeString()}</time> ·{" "}
                    {log.status}
                  </div>
                  <pre>{log.message}</pre>
                  {log.details && (
                    <>
                      <details>
                        <summary>Inputs and instructions</summary>
                        <pre>{log.details.input}</pre>
                        <pre>{log.details.instruction}</pre>
                      </details>
                      <p>
                        Configured model: {log.details.model} · Upstream nodes:{" "}
                        {log.details.upstream.join(", ") || "none"}
                      </p>
                    </>
                  )}
                </article>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
