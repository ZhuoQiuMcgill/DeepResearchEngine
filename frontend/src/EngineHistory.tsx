import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
export function EngineHistory({ onClose }: { onClose: () => void }) {
  const [runs, setRuns] = useState<any[]>([]),
    [output, setOutput] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/engine-runs", { signal: abort.signal })
      .then((r) => r.json())
      .then((d) => {
        if (d.error) throw new Error(d.error);
        setRuns(d.runs);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, []);
  return (
    <div
      className="modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="history-modal"
        role="dialog"
        aria-label="Engine history"
        style={{
          width: "min(950px,92vw)",
          maxHeight: "85vh",
          overflow: "auto",
        }}
      >
        <div className="activity-heading">
          <strong>Engine history · saved runs</strong>
          <button onClick={onClose}>Close</button>
        </div>
        {error && <p role="alert">{error}</p>}
        {runs.map((r) => (
          <button
            className="history-row"
            key={r.run_id}
            onClick={async () => {
              setError("");
              setOutput("Loading…");
              try {
                const d = await (
                  await fetch(
                    "/api/engine-result?id=" + encodeURIComponent(r.run_id),
                  )
                ).json();
                if (d.error) throw new Error(d.error);
                setOutput(
                  d.output ||
                    `${d.result.status}: ${d.result.error?.message || "No saved report"}`,
                );
              } catch (e) {
                setError((e as Error).message);
                setOutput("");
              }
            }}
          >
            {r.agent_ref?.agent_id || r.run_id} · {r.status}
          </button>
        ))}
        {!runs.length && !error && <p>No saved Engine runs.</p>}
        <article className="report-content">
          <ReactMarkdown components={{ img: () => null }}>
            {output}
          </ReactMarkdown>
        </article>
      </section>
    </div>
  );
}
