import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  ClipboardList,
  Download,
  FolderOpen,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { importEngineRun, type EngineRun } from "./engineRun";
import "./EngineRunReview.css";

const sections = [
  "Overview",
  "Decisions",
  "Sources & notes",
  "Report",
  "Review",
] as const;
type Section = (typeof sections)[number];
const choices = [
  "Accept",
  "Accept with a note",
  "Run again",
  "Set aside",
] as const;
type Review = {
  runId: string;
  decision: (typeof choices)[number];
  reviewer: string;
  reason: string;
  reviewedAt: string;
  replacementRunId?: string;
};

const stopDescriptions: Record<string, string> = {
  complete:
    "The strategy met its stopping conditions. Review the sources before relying on the report.",
  saturated: "Another round was unlikely to resolve the remaining goals.",
  budget:
    "The researcher ceiling was reached. Check the remaining goals and the report's gaps.",
  out_of_scope:
    "The strategy ended the run because the question fell outside its scope.",
  researcher_failures:
    "The researchers failed. Check the recorded errors before starting a fresh run.",
};

const display = (text: string) => text.replace(/[_-]+/g, " ");
const count = (value: number | undefined) => value?.toLocaleString() ?? "—";
const storeKey = (run: EngineRun) =>
  run.reviewKey && `inse-engine-review-v1:${run.reviewKey}`;

function readReview(run: EngineRun): Review | null {
  try {
    const key = storeKey(run);
    if (!key) return null;
    const review = JSON.parse(localStorage.getItem(key) || "null");
    return review?.runId === run.runId && choices.includes(review.decision)
      ? review
      : null;
  } catch {
    return null;
  }
}

function downloadFile(name: string, value: string, type: string) {
  const url = URL.createObjectURL(new Blob([value], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Markdown({ text }: { text: string }) {
  return (
    <div className="report-content engine-markdown">
      <ReactMarkdown
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          img: () => null,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function RunOverview({
  run,
  onReview,
}: {
  run: EngineRun;
  onReview: () => void;
}) {
  const { metrics } = run;
  const stop = run.stopKind || run.stopReason;
  const metricsRows = [
    [
      "Researchers used / ceiling",
      `${count(run.researchersUsed)} / ${count(run.researchersBudget)}`,
    ],
    ["Rounds", count(run.roundCount)],
    ["Searches", count(metrics.searches)],
    ["Page reads", count(metrics.pageReads)],
    ["Input tokens", count(metrics.inputTokens)],
    ["Output tokens", count(metrics.outputTokens)],
    [
      "Estimated cost",
      metrics.costUsd === undefined
        ? "—"
        : `$${metrics.costUsd.toFixed(4)} USD`,
    ],
    [
      "Elapsed time",
      metrics.durationMs === undefined
        ? "—"
        : `${(metrics.durationMs / 1000).toFixed(1)} s`,
    ],
  ];
  return (
    <>
      <div className="engine-overview">
        <section className="engine-card">
          <h3>Run settings</h3>
          <dl className="engine-settings">
            <dt>Strategy</dt>
            <dd>{run.strategy}</dd>
            <dt>Model</dt>
            <dd>{run.model || "—"}</dd>
            <dt>Profile</dt>
            <dd>{run.profile || "—"}</dd>
            <dt>Engine commit</dt>
            <dd>{run.commit ? <code>{run.commit}</code> : "—"}</dd>
          </dl>
        </section>
        <section className="engine-card">
          <h3>How the run ended</h3>
          <strong className="engine-status">
            {display(stop || run.status)}
          </strong>
          <p>
            {(stop && stopDescriptions[stop]) ||
              run.stopReason ||
              "See the recorded decisions for details."}
          </p>
          {run.assumptions.length > 0 && (
            <details>
              <summary>Recorded assumptions</summary>
              <ul>
                {run.assumptions.map((item) => (
                  <li key={item.id}>
                    {item.claim}
                    {item.verdict ? ` · ${display(item.verdict)}` : ""}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      </div>
      <dl className="engine-metrics">
        {metricsRows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <section className="engine-card">
        <div className="engine-row">
          <h3>Things to check</h3>
          <button onClick={onReview}>Open review</button>
        </div>
        <RunFlags run={run} />
      </section>
    </>
  );
}

function RunFlags({ run }: { run: EngineRun }) {
  return run.warnings.length ? (
    <ul className="engine-flags">
      {run.warnings.map((warning, i) => (
        <li key={i}>{warning}</li>
      ))}
    </ul>
  ) : (
    <p>No review flags in the imported record.</p>
  );
}

function RunDecisions({ run }: { run: EngineRun }) {
  return (
    <>
      <h3>Strategy decisions</h3>
      {run.decisions.length === 0 && (
        <p>Include events.jsonl to inspect the strategy decisions.</p>
      )}
      <div className="engine-details">
        {run.decisions.map((decision, index) => (
          <details key={index}>
            <summary>
              <span>
                {decision.phase === "init"
                  ? "Initial plan"
                  : `After round ${decision.round}`}
              </span>
              <small>
                {decision.stop
                  ? "Stop"
                  : `${decision.accepted.length} accepted`}
                {decision.dropped ? ` · ${decision.dropped} dropped` : ""}
              </small>
            </summary>
            <div className="engine-detail-body">
              {decision.rationale && <p>{decision.rationale}</p>}
              {decision.budgetBefore !== undefined && (
                <p>
                  Researchers remaining before decision: {decision.budgetBefore}
                  .
                </p>
              )}
              {decision.accepted.map((brief, i) => (
                <div key={`${brief.id}-${i}`} className="engine-brief">
                  <strong>{brief.objective || brief.id}</strong>
                  {brief.keyQuestions.length > 0 && (
                    <ul>
                      {brief.keyQuestions.map((question, j) => (
                        <li key={j}>{question}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
              {decision.actions.length > 0 && (
                <ul>
                  {decision.actions.map((action, i) => (
                    <li key={i}>{action}</li>
                  ))}
                </ul>
              )}
            </div>
          </details>
        ))}
      </div>
      {run.goals.length > 0 && (
        <>
          <h3>EBD goals</h3>
          <div className="engine-details">
            {run.goals.map((goal) => (
              <details key={goal.id}>
                <summary>
                  <span>{goal.text}</span>
                  <small>{display(goal.status)}</small>
                </summary>
                <div className="engine-detail-body">
                  <p>
                    {[
                      goal.id,
                      goal.need,
                      goal.createdRound === undefined
                        ? null
                        : `Created in round ${goal.createdRound}`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  {goal.doneWhen && (
                    <p>Completion condition: {goal.doneWhen}</p>
                  )}
                  {goal.missing.length > 0 && (
                    <ul>
                      {goal.missing.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  )}
                  {goal.evidenceIds.length > 0 && (
                    <ul>
                      {goal.evidenceIds.map((id) => (
                        <li key={id}>
                          {run.evidence.find((item) => item.id === id)?.text ||
                            id}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </details>
            ))}
          </div>
        </>
      )}
      {run.conflicts.length > 0 && (
        <>
          <h3>Recorded conflicts</h3>
          <div className="engine-details">
            {run.conflicts.map((conflict) => (
              <details key={conflict.id}>
                <summary>
                  <span>{conflict.statement}</span>
                  <small>{display(conflict.status)}</small>
                </summary>
                <div className="engine-detail-body">
                  {conflict.condition && <p>{conflict.condition}</p>}
                  {[conflict.sideA, conflict.sideB].map((side, i) =>
                    side.length ? (
                      <div key={i}>
                        <strong>Side {i === 0 ? "A" : "B"}</strong>
                        <ul>
                          {side.map((id, j) => (
                            <li key={j}>
                              {run.evidence.find((item) => item.id === id)
                                ?.text || id}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null,
                  )}
                </div>
              </details>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function RunSources({ run }: { run: EngineRun }) {
  const [query, setQuery] = useState("");
  const [citedOnly, setCitedOnly] = useState(false);
  const filter = query.trim().toLowerCase();
  const sources = run.sources.filter(
    (source) =>
      (!citedOnly || source.cited) &&
      `${source.title || ""} ${source.url}`.toLowerCase().includes(filter),
  );
  return (
    <>
      <div className="engine-row engine-source-filters">
        <h3>Sources</h3>
        <input
          type="search"
          aria-label="Filter sources"
          placeholder="Filter by title or URL"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <label>
          <input
            type="checkbox"
            checked={citedOnly}
            onChange={(e) => setCitedOnly(e.target.checked)}
          />{" "}
          Cited in notes
        </label>
      </div>
      {sources.length ? (
        <ul className="engine-source-list">
          {sources.map((source) => (
            <li key={source.url}>
              <a href={source.url} target="_blank" rel="noopener noreferrer">
                {source.title || source.url} <ArrowUpRight size={14} />
              </a>
              <small>
                {source.cited
                  ? "Cited in researcher notes"
                  : "Reported by a researcher"}
                {source.briefIds.length
                  ? ` · ${source.briefIds.join(", ")}`
                  : ""}
              </small>
            </li>
          ))}
        </ul>
      ) : (
        <p>
          {run.sources.length
            ? "No sources match these filters."
            : "No source records in this import. Include the results folder for more detail."}
        </p>
      )}
      <h3>Researcher notes</h3>
      <div className="engine-details">
        {run.results.map((result) => (
          <details key={result.id}>
            <summary>
              <span>{result.objective || result.id}</span>
              <small>
                {result.round !== undefined ? `Round ${result.round} · ` : ""}
                {display(result.status)}
              </small>
            </summary>
            <div className="engine-detail-body">
              {result.failure && (
                <p className="engine-warning">{result.failure}</p>
              )}
              {result.queries.length > 0 && (
                <p>Search queries: {result.queries.join(" · ")}</p>
              )}
              {result.notes && <Markdown text={result.notes} />}
            </div>
          </details>
        ))}
        {run.results.length === 0 && (
          <p>No researcher results in this import.</p>
        )}
        {run.writerInput && (
          <details>
            <summary>Writer input</summary>
            <div className="engine-detail-body">
              {run.writerInput.guidance && (
                <Markdown text={run.writerInput.guidance} />
              )}
              {run.writerInput.outline.length > 0 && (
                <ul>
                  {run.writerInput.outline.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              )}
              {run.writerInput.materials.map((item, i) => (
                <details key={i}>
                  <summary>{item.label}</summary>
                  <Markdown text={item.notes} />
                </details>
              ))}
              {run.writerInput.diagnostics.length > 0 && (
                <ul>
                  {run.writerInput.diagnostics.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              )}
            </div>
          </details>
        )}
      </div>
    </>
  );
}

function ReviewForm({ run }: { run: EngineRun }) {
  const [saved, setSaved] = useState(() => readReview(run));
  const [decision, setDecision] = useState<Review["decision"]>(
    saved?.decision || "Accept",
  );
  const [reviewer, setReviewer] = useState(saved?.reviewer || "");
  const [reason, setReason] = useState(saved?.reason || "");
  const [replacementRunId, setReplacementRunId] = useState(
    saved?.replacementRunId || "",
  );
  const [notice, setNotice] = useState("");

  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!reviewer.trim() || !reason.trim()) {
      setNotice("Enter your name and a reason for this decision.");
      return;
    }
    if (decision === "Run again" && replacementRunId.trim() === run.runId) {
      setNotice("Enter the ID of the fresh run when it is available.");
      return;
    }
    const review: Review = {
      runId: run.runId,
      decision,
      reviewer: reviewer.trim(),
      reason: reason.trim(),
      reviewedAt: new Date().toISOString(),
      ...(decision === "Run again" && replacementRunId.trim()
        ? { replacementRunId: replacementRunId.trim() }
        : {}),
    };
    setSaved(review);
    const key = storeKey(run);
    if (!key) {
      setNotice(
        "Download your review to keep it. This import has no run identifier.",
      );
      return;
    }
    try {
      localStorage.setItem(key, JSON.stringify(review));
      setNotice("Review saved on this device.");
    } catch {
      setNotice(
        "Browser storage is unavailable. Download your review to keep it.",
      );
    }
  }

  return (
    <div className="engine-review-grid">
      <section className="engine-card">
        <h3>Things to check</h3>
        <RunFlags run={run} />
      </section>
      <form className="engine-card engine-review-form" onSubmit={save}>
        <h3>Record a decision</h3>
        <label className="engine-field">
          Decision
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value as Review["decision"])}
          >
            {choices.map((choice) => (
              <option key={choice}>{choice}</option>
            ))}
          </select>
        </label>
        <label className="engine-field">
          Reviewer
          <input
            required
            maxLength={120}
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
          />
        </label>
        <label className="engine-field">
          Reason
          <textarea
            required
            rows={3}
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        {decision === "Run again" && (
          <>
            <label className="engine-field">
              Fresh run ID (when available)
              <input
                maxLength={160}
                value={replacementRunId}
                onChange={(e) => setReplacementRunId(e.target.value)}
              />
            </label>
            <p>
              For a technical failure, start a fresh run from the engine and
              keep both records.
            </p>
          </>
        )}
        <div className="engine-row engine-form-actions">
          <button className="primary" type="submit">
            Save review
          </button>
          {saved && (
            <button
              type="button"
              onClick={() =>
                downloadFile(
                  "review.json",
                  JSON.stringify({ ...saved, flags: run.warnings }, null, 2),
                  "application/json",
                )
              }
            >
              <Download size={15} /> Download saved review
            </button>
          )}
        </div>
        {saved && (
          <small>
            Last recorded by {saved.reviewer} ·{" "}
            {new Date(saved.reviewedAt).toLocaleString()}
          </small>
        )}
        <div role="status">{notice}</div>
      </form>
    </div>
  );
}

export function EngineRunReview({
  open,
  onClose,
  jobId,
}: {
  open: boolean;
  onClose: () => void;
  jobId?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const files = useRef<HTMLInputElement>(null);
  const [run, setRun] = useState<EngineRun | null>(null);
  const [section, setSection] = useState<Section>("Overview");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const element = dialog.current;
    if (open && element && !element.open) element.showModal();
    if (!open && element?.open) element.close();
  }, [open]);

  useEffect(() => {
    if (!open || !jobId) return;
    const controller = new AbortController();
    setRun(null);
    setBusy(true);
    setError("");
    setSection("Overview");
    async function readEngineJob() {
      try {
        const response = await fetch(
          `/api/engine/jobs/${encodeURIComponent(jobId!)}/files`,
          {
            signal: controller.signal,
          },
        );
        const record = await response.json();
        if (!response.ok)
          throw new Error(record.error ?? "Could not open the engine record.");
        const run = await importEngineRun(
          record.files.map(
            ({
              name,
              relativePath,
              text,
            }: {
              name: string;
              relativePath: string;
              text: string;
            }) => ({
              name,
              webkitRelativePath: relativePath,
              text: async () => text,
            }),
          ),
        );
        if (!controller.signal.aborted) setRun(run);
      } catch (err) {
        if (!controller.signal.aborted)
          setError(
            err instanceof Error
              ? err.message
              : "Could not open the engine record.",
          );
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }
    void readEngineJob();
    return () => {
      controller.abort();
      setBusy(false);
    };
  }, [open, jobId]);

  async function load(list: FileList | null) {
    if (!list?.length || busy) return;
    setBusy(true);
    setError("");
    try {
      setRun(await importEngineRun(list));
      setSection("Overview");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "The run files could not be opened.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      className="engine-review"
      ref={dialog}
      aria-labelledby="engine-review-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="engine-review-header">
        <div>
          <div className="eyebrow">DEEPRESEARCH ENGINE</div>
          <h2 id="engine-review-title">Review an engine run</h2>
        </div>
        <button aria-label="Close engine run review" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
      <div className="engine-review-body" aria-busy={busy}>
        <input
          hidden
          type="file"
          ref={folder}
          {...{ webkitdirectory: "" }}
          onChange={(e) => {
            void load(e.target.files);
            e.target.value = "";
          }}
        />
        <input
          hidden
          type="file"
          ref={files}
          multiple
          accept=".json,.jsonl,.md,.txt"
          onChange={(e) => {
            void load(e.target.files);
            e.target.value = "";
          }}
        />
        <div className="engine-row engine-import-actions">
          <button
            className={run ? "" : "primary"}
            disabled={busy}
            onClick={() => folder.current?.click()}
          >
            <FolderOpen size={16} />{" "}
            {run ? "Open another run folder" : "Open run folder"}
          </button>
          <button disabled={busy} onClick={() => files.current?.click()}>
            Select run files
          </button>
          {busy && <span role="status">Reading run record…</span>}
        </div>
        {error && (
          <p role="alert" className="engine-warning">
            {error}
          </p>
        )}
        {!run ? (
          <div className="engine-empty">
            <div className="engine-empty-icon">
              <ClipboardList size={25} />
            </div>
            <h3>Open a completed or failed run</h3>
            <p>
              Select the output folder for one Baseline or EBD run from
              DeepResearchEngine. Read its strategy decisions, open sources, and
              record your review.
            </p>
            <p>
              For a folder, choose the one containing <code>summary.json</code>.
              For individual files, include the summary and any available
              report, events or researcher results. Files are read on this
              device.
            </p>
          </div>
        ) : (
          <>
            <div className="engine-run-heading">
              <div className="engine-run-meta">
                <span>{run.strategy}</span>
                <code>{run.runId}</code>
              </div>
              <h3>{run.question}</h3>
            </div>
            <nav className="engine-review-nav" aria-label="Run record sections">
              {sections.map((name) => (
                <button
                  key={name}
                  aria-current={section === name ? "page" : undefined}
                  onClick={() => setSection(name)}
                >
                  {name}
                </button>
              ))}
            </nav>
            <div className="engine-section" key={`${run.runId}-${section}`}>
              {section === "Overview" && (
                <RunOverview run={run} onReview={() => setSection("Review")} />
              )}
              {section === "Decisions" && <RunDecisions run={run} />}
              {section === "Sources & notes" && <RunSources run={run} />}
              {section === "Report" &&
                (run.report ? (
                  <>
                    <div className="engine-row">
                      <h3>Final report</h3>
                      <button
                        onClick={() =>
                          downloadFile(
                            "report.md",
                            run.report || "",
                            "text/markdown;charset=utf-8",
                          )
                        }
                      >
                        <Download size={15} /> Download report
                      </button>
                    </div>
                    <Markdown text={run.report} />
                  </>
                ) : (
                  <p>
                    No report in this import. Open the folder again with
                    report.md if the engine produced one.
                  </p>
                ))}
              {section === "Review" && <ReviewForm run={run} />}
            </div>
          </>
        )}
      </div>
    </dialog>
  );
}
