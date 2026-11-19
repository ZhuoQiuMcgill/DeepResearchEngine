import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  Beaker,
  CheckCircle2,
  CircleAlert,
  FlaskConical,
  Loader2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import "./OfficialEngine.css";

type Props = {
  open: boolean;
  onClose: () => void;
  onOpenRun: (jobId: string) => void;
};
type Case = { id: string; title: string; objective: string; question: string };
type Catalog = {
  profiles: string[];
  cases: Case[];
  liveProfiles: string[];
};
type JobKind = "research" | "evaluation";
type Job = {
  id: string;
  kind: JobKind;
  status: "running" | "complete" | "error";
  error?: string;
  result?: unknown;
};
type Request =
  | {
      kind: "research";
      question: string;
      strategy: "baseline" | "ebd";
      profile: string;
      researchers: number;
    }
  | {
      kind: "evaluation";
      mode: "fixture" | "live";
      caseId?: string;
      profile?: string;
    };

class RequestFailure extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function engineRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/engine${path}`, options);
  const contentType = response.headers.get("Content-Type") || "";
  if (!contentType.includes("application/json")) {
    throw new RequestFailure(
      "Connect to the engine server to use this console.",
      response.status,
    );
  }
  const data = await response.json();
  if (!response.ok) {
    const message =
      typeof data.error === "string"
        ? data.error
        : "The engine request could not be completed.";
    throw new RequestFailure(message, response.status);
  }
  return data as T;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof RequestFailure ? error.message : fallback;
}

type Score = {
  rubricVersion: string;
  passed: number;
  total: number;
  rubricScore: number;
  taskSuccess: boolean;
  checks: { id: string; detail: string; passed: boolean }[];
};
type Metrics = Partial<
  Record<
    | "latencyMs"
    | "inputTokens"
    | "outputTokens"
    | "modelInvocations"
    | "externalToolCalls"
    | "guardrailEventCount",
    number | null
  >
>;
type EvaluationArm = {
  arm?: "single-turn-direct" | "ebd-engine";
  label?: string;
  model?: string;
  output: string;
  error?: string;
  status?: "ok" | "error";
  score: Score | null;
  metrics: Metrics;
};
type EvaluationCase = {
  caseId: string;
  objective: string;
  question: string;
  sources: { id: string; date: string; text: string }[];
};
type FixtureGuardrails = {
  disclaimer: string;
  benignReportPreserved: boolean;
  directInstructionQuarantined: boolean;
  findings: { rule: string; action: string; count: number; message: string }[];
};
type EvaluationReport =
  | {
      mode: "fixture-replay";
      disclaimer: string;
      metricDefinitions: Record<string, string>;
      cases: (EvaluationCase & { referenceOutputs: EvaluationArm[] })[];
      guardrailChecks?: FixtureGuardrails;
    }
  | (EvaluationCase & {
      mode: "live-paired";
      profile: string;
      metricDefinitions: Record<string, string>;
      confounds: string[];
      arms: EvaluationArm[];
    });

const caseTitles: Record<string, string> = {
  "dated-conflict": "Dated evidence conflict",
  "untrusted-report": "Untrusted report content",
};
const armTitles: Record<string, string> = {
  "single-turn-direct": "Direct baseline · one model call",
  "ebd-engine": "EBD engine · research workflow",
  "passing-reference": "Passing reference",
  "failing-reference": "Failing reference",
};
const metricTitles: Record<string, string> = {
  rubricScore: "Rubric score",
  taskSuccess: "Task success",
  latencyMs: "Elapsed time",
  tokens: "Token usage",
  guardrailEventCount: "Guardrail events",
  limitations: "Limitations",
};
const formatCount = (value: number | null | undefined) =>
  value == null ? "—" : value.toLocaleString();
const formatSeconds = (value: number | null | undefined) =>
  value == null
    ? "—"
    : `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })} s`;

function EvaluationCaseResults({
  test,
  title,
  arms,
  live,
}: {
  test: EvaluationCase;
  title: string;
  arms: EvaluationArm[];
  live: boolean;
}) {
  return (
    <section className="official-engine-result-card">
      <h4>{title}</h4>
      <p>{test.objective}</p>
      <details className="official-engine-details">
        <summary>Question and source packet</summary>
        <blockquote>{test.question}</blockquote>
        <ul>
          {test.sources.map((source) => (
            <li key={source.id}>
              <strong>
                {source.id} · {source.date}
              </strong>{" "}
              {source.text}
            </li>
          ))}
        </ul>
      </details>
      <div className="official-engine-table-wrap">
        <table>
          <caption className="official-engine-visually-hidden">
            Evaluation comparison for {title}
          </caption>
          <thead>
            <tr>
              <th scope="col">{live ? "Arm" : "Reference output"}</th>
              <th scope="col">Rubric score</th>
              <th scope="col">Task success</th>
              {live && (
                <>
                  <th scope="col">Elapsed</th>
                  <th scope="col">Model calls</th>
                  <th scope="col">Tool calls</th>
                  <th scope="col">Input tokens</th>
                  <th scope="col">Output tokens</th>
                  <th scope="col">Guardrail events</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {arms.map((arm) => {
              const key = arm.arm ?? arm.label ?? "unknown";
              return (
                <tr key={key}>
                  <th scope="row">
                    {armTitles[key] ?? key}
                    {arm.model && <small>{arm.model}</small>}
                  </th>
                  <td>
                    {arm.score
                      ? `${arm.score.passed}/${arm.score.total} (${Math.round(arm.score.rubricScore * 100)}%)`
                      : "—"}
                  </td>
                  <td>
                    {arm.status === "error"
                      ? "Arm failed"
                      : !arm.score
                        ? "—"
                        : arm.score.taskSuccess
                          ? "Passed"
                          : "Fell short"}
                  </td>
                  {live && (
                    <>
                      <td>{formatSeconds(arm.metrics.latencyMs)}</td>
                      <td>{formatCount(arm.metrics.modelInvocations)}</td>
                      <td>{formatCount(arm.metrics.externalToolCalls)}</td>
                      <td>{formatCount(arm.metrics.inputTokens)}</td>
                      <td>{formatCount(arm.metrics.outputTokens)}</td>
                      <td>{formatCount(arm.metrics.guardrailEventCount)}</td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="official-engine-arm-details">
        {arms.map((arm) => {
          const key = arm.arm ?? arm.label ?? "unknown";
          return (
            <details className="official-engine-details" key={key}>
              <summary>{armTitles[key] ?? key} response and scoring</summary>
              {arm.error && (
                <p className="official-engine-error">{arm.error}</p>
              )}
              {arm.output && (
                <div className="official-engine-answer">
                  <ReactMarkdown skipHtml components={{ img: () => null }}>
                    {arm.output}
                  </ReactMarkdown>
                </div>
              )}
              {arm.score && (
                <ul className="official-engine-checks">
                  {arm.score.checks.map((check) => (
                    <li key={check.id}>
                      <strong>{check.passed ? "Pass" : "Miss"}</strong>{" "}
                      {check.detail}
                    </li>
                  ))}
                </ul>
              )}
            </details>
          );
        })}
      </div>
    </section>
  );
}

function EvaluationResults({
  result,
  cases,
  caseId,
}: {
  result: unknown;
  cases: Case[];
  caseId?: string;
}) {
  const report = result as EvaluationReport | undefined;
  if (
    !report ||
    (report.mode !== "fixture-replay" && report.mode !== "live-paired")
  ) {
    return (
      <p role="status">
        The evaluation completed. This console could not read the report.
      </p>
    );
  }
  const live = report.mode === "live-paired";
  const titleFor = (id: string) =>
    cases.find((item) => item.id === id)?.title ?? caseTitles[id] ?? id;
  const fixtureCases =
    report.mode === "fixture-replay"
      ? report.cases.filter((test) => !caseId || test.caseId === caseId)
      : [];
  const guardrails =
    report.mode === "fixture-replay" &&
    fixtureCases.some((test) => test.caseId === "untrusted-report")
      ? report.guardrailChecks
      : undefined;
  return (
    <section
      className="official-engine-results"
      aria-label="Evaluation results"
    >
      <div className="official-engine-results-heading">
        <h3>Evaluation results</h3>
        <span>{live ? "Live comparison" : "Fixture replay"}</span>
      </div>
      {live ? (
        <>
          <p className="official-engine-muted">
            Compared on profile <strong>{report.profile}</strong>. Unreported
            measurements appear as —.
          </p>
          <EvaluationCaseResults
            test={report}
            title={titleFor(report.caseId)}
            arms={report.arms}
            live
          />
          <details className="official-engine-details official-engine-limitations">
            <summary>What this comparison measures</summary>
            <ul>
              {report.confounds.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </details>
        </>
      ) : (
        <>
          <p className="official-engine-muted">{report.disclaimer}</p>
          {fixtureCases.map((test) => (
            <EvaluationCaseResults
              key={test.caseId}
              test={test}
              title={titleFor(test.caseId)}
              arms={test.referenceOutputs}
              live={false}
            />
          ))}
          {guardrails && (
            <details className="official-engine-details official-engine-limitations">
              <summary>Notes guardrail fixture check</summary>
              <p>{guardrails.disclaimer}</p>
              <ul>
                <li>
                  Benign report text preserved:{" "}
                  <strong>
                    {guardrails.benignReportPreserved ? "Yes" : "No"}
                  </strong>
                </li>
                <li>
                  Direct instruction quarantined:{" "}
                  <strong>
                    {guardrails.directInstructionQuarantined ? "Yes" : "No"}
                  </strong>
                </li>
                {guardrails.findings.map((finding) => (
                  <li key={finding.rule}>
                    {finding.message} ({finding.action}, {finding.count})
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      <details className="official-engine-details official-engine-limitations">
        <summary>How to read the scores</summary>
        <dl>
          {Object.entries(report.metricDefinitions).map(
            ([name, definition]) => (
              <div key={name}>
                <dt>{metricTitles[name] ?? name}</dt>
                <dd>{definition}</dd>
              </div>
            ),
          )}
        </dl>
      </details>
    </section>
  );
}

export function OfficialEngine({ open, onClose, onOpenRun }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [view, setView] = useState<JobKind>("research");
  const [catalog, setCatalog] = useState<Catalog>();
  const [catalogError, setCatalogError] = useState("");
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [question, setQuestion] = useState("");
  const [strategy, setStrategy] = useState<"ebd" | "baseline">("ebd");
  const [researchProfile, setResearchProfile] = useState("");
  const [budget, setBudget] = useState("6");
  const [evaluationMode, setEvaluationMode] = useState<"fixture" | "live">(
    "fixture",
  );
  const [caseId, setCaseId] = useState("");
  const [evaluationProfile, setEvaluationProfile] = useState("");
  const [evaluatedCaseId, setEvaluatedCaseId] = useState<string>();
  const [jobs, setJobs] = useState<Partial<Record<JobKind, Job>>>({});
  const [submitError, setSubmitError] = useState<
    Partial<Record<JobKind, string>>
  >({});
  const [pending, setPending] = useState<JobKind>();
  const submitting = useRef(false);
  const [refreshError, setRefreshError] = useState(false);

  const runningJob = Object.values(jobs).find(
    (entry) => entry?.status === "running",
  );
  const activeJobId = runningJob?.id;
  const activeJobKind = runningJob?.kind;
  const currentJob = jobs[view];
  const researchResult = jobs.research?.result as
    { runStatus?: string } | undefined;
  const liveProfiles = catalog?.liveProfiles ?? [];
  const officialProfiles =
    catalog?.profiles.filter((profile) => liveProfiles.includes(profile)) ?? [];
  const cases = catalog?.cases ?? [];
  const selectedResearchProfile = officialProfiles.includes(researchProfile)
    ? researchProfile
    : (officialProfiles[0] ?? "");
  const selectedEvaluationProfile = liveProfiles.includes(evaluationProfile)
    ? evaluationProfile
    : (liveProfiles[0] ?? "");
  const selectedCase = cases.find((item) => item.id === caseId) ?? cases[0];
  const parsedBudget = Number(budget);
  const canStartResearch =
    selectedResearchProfile &&
    Boolean(question.trim()) &&
    Number.isInteger(parsedBudget) &&
    parsedBudget >= 1 &&
    parsedBudget <= 12;
  const canStartEvaluation =
    Boolean(selectedCase) &&
    (evaluationMode === "fixture" || Boolean(selectedEvaluationProfile));
  const busy = Boolean(activeJobId || pending);

  useEffect(() => {
    const element = dialog.current;
    if (open && element && !element.open) element.showModal();
    if (!open && element?.open) element.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (window.location.protocol === "file:") {
      setCatalogError(
        "The engine is unavailable in an offline preview. Open the integrated app to run research or evaluations.",
      );
      return;
    }
    const controller = new AbortController();
    setCatalogError("");
    void engineRequest<Catalog>("", { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        if (
          !Array.isArray(result.profiles) ||
          !Array.isArray(result.cases) ||
          !Array.isArray(result.liveProfiles)
        )
          throw new Error("Invalid engine catalog");
        setCatalog(result);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setCatalog(undefined);
        setCatalogError(
          errorMessage(
            error,
            "The engine service is unavailable. Start the integration server and try again.",
          ),
        );
      });
    return () => controller.abort();
  }, [open, catalogRevision]);

  useEffect(() => {
    if (!open || !activeJobId || !activeJobKind) return;
    const id = activeJobId;
    const kind = activeJobKind;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    function poll() {
      void engineRequest<Job>(`/jobs/${encodeURIComponent(id)}`, {
        signal: controller.signal,
      })
        .then((job) => {
          if (controller.signal.aborted) return;
          setRefreshError(false);
          setJobs((previous) => ({ ...previous, [kind]: job }));
          if (job.status === "running") timer = setTimeout(poll, 1200);
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          if (error instanceof RequestFailure && error.status === 404) {
            setJobs((previous) => ({
              ...previous,
              [kind]: {
                id,
                kind,
                status: "error",
                error:
                  "The engine no longer reports this job. If it finished, its record may still be available on disk.",
              },
            }));
            return;
          }
          setRefreshError(true);
          timer = setTimeout(poll, 2500);
        });
    }
    poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [open, activeJobId, activeJobKind]);

  function close() {
    dialog.current?.close();
    onClose();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || submitting.current) return;
    let request: Request;
    if (view === "research") {
      if (!canStartResearch) return;
      request = {
        kind: "research",
        question,
        strategy,
        profile: selectedResearchProfile,
        researchers: parsedBudget,
      };
    } else {
      if (!canStartEvaluation || !selectedCase) return;
      request = {
        kind: "evaluation",
        mode: evaluationMode,
        caseId: selectedCase.id,
        ...(evaluationMode === "live" && {
          profile: selectedEvaluationProfile,
        }),
      };
    }
    submitting.current = true;
    setPending(request.kind);
    setSubmitError((previous) => ({ ...previous, [request.kind]: "" }));
    setRefreshError(false);
    try {
      const job = await engineRequest<Job>("/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      if (request.kind === "evaluation") setEvaluatedCaseId(request.caseId);
      setJobs((previous) => ({ ...previous, [request.kind]: job }));
    } catch (error) {
      setSubmitError((previous) => ({
        ...previous,
        [request.kind]: errorMessage(
          error,
          "The engine did not confirm that the job started. Check the service before retrying.",
        ),
      }));
    } finally {
      submitting.current = false;
      setPending(undefined);
    }
  }

  return (
    <dialog
      ref={dialog}
      className="official-engine"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <header className="official-engine-header">
        <div>
          <div className="eyebrow">DEEPRESEARCH ENGINE</div>
          <h2 id={titleId}>Engine &amp; Evaluation</h2>
        </div>
        <button
          type="button"
          onClick={close}
          aria-label="Close Engine and Evaluation"
        >
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      <div className="official-engine-body">
        <nav className="official-engine-nav" aria-label="Engine views">
          <button
            type="button"
            aria-current={view === "research" ? "page" : undefined}
            onClick={() => setView("research")}
          >
            <FlaskConical size={16} aria-hidden="true" /> Research
          </button>
          <button
            type="button"
            aria-current={view === "evaluation" ? "page" : undefined}
            onClick={() => setView("evaluation")}
          >
            <Beaker size={16} aria-hidden="true" /> Evaluation
          </button>
        </nav>

        {catalogError ? (
          <div className="official-engine-notice" role="alert">
            <CircleAlert size={18} aria-hidden="true" />
            <p>{catalogError}</p>
            {window.location.protocol !== "file:" && (
              <button
                type="button"
                onClick={() => setCatalogRevision((revision) => revision + 1)}
              >
                Retry
              </button>
            )}
          </div>
        ) : (
          !catalog && <p role="status">Connecting to the engine server…</p>
        )}

        <form className="official-engine-form" onSubmit={submit}>
          {view === "research" ? (
            <>
              <label className="official-engine-question">
                Research question
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  rows={4}
                  maxLength={6000}
                  required
                />
              </label>
              <div className="official-engine-fields">
                <label>
                  Strategy
                  <select
                    value={strategy}
                    onChange={(event) =>
                      setStrategy(
                        event.target.value === "baseline" ? "baseline" : "ebd",
                      )
                    }
                  >
                    <option value="ebd">EBD</option>
                    <option value="baseline">Baseline</option>
                  </select>
                </label>
                <label>
                  Model profile
                  <select
                    value={selectedResearchProfile}
                    disabled={!officialProfiles.length}
                    onChange={(event) => setResearchProfile(event.target.value)}
                  >
                    {!officialProfiles.length && (
                      <option value="">No API profile configured</option>
                    )}
                    {officialProfiles.map((profile) => (
                      <option key={profile}>{profile}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Researcher budget
                  <input
                    type="number"
                    min={1}
                    max={12}
                    step={1}
                    value={budget}
                    onChange={(event) => setBudget(event.target.value)}
                    required
                  />
                </label>
              </div>
              <p className="official-engine-muted">
                The provider receives the question and any material the engine
                uses in its research. The run can use up to eight rounds and
                four concurrent tasks.
              </p>
            </>
          ) : (
            <>
              <div className="official-engine-fields evaluation">
                <label>
                  Mode
                  <select
                    value={evaluationMode}
                    onChange={(event) =>
                      setEvaluationMode(
                        event.target.value === "live" ? "live" : "fixture",
                      )
                    }
                  >
                    <option value="fixture">Fixture replay</option>
                    <option value="live" disabled={!liveProfiles.length}>
                      Live comparison
                    </option>
                  </select>
                </label>
                <label>
                  Case
                  <select
                    value={selectedCase?.id ?? ""}
                    disabled={!cases.length}
                    onChange={(event) => setCaseId(event.target.value)}
                  >
                    {!cases.length && (
                      <option value="">No cases available</option>
                    )}
                    {cases.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.title}
                      </option>
                    ))}
                  </select>
                </label>
                {evaluationMode === "live" && (
                  <label>
                    Model profile
                    <select
                      value={selectedEvaluationProfile}
                      onChange={(event) =>
                        setEvaluationProfile(event.target.value)
                      }
                    >
                      {liveProfiles.map((profile) => (
                        <option key={profile}>{profile}</option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              {selectedCase && (
                <div className="official-engine-case">
                  <strong>{selectedCase.title}</strong>
                  <p>{selectedCase.objective}</p>
                  <blockquote>{selectedCase.question}</blockquote>
                </div>
              )}
              <p className="official-engine-muted">
                {evaluationMode === "fixture"
                  ? "Fixture replay uses saved answers to show how scoring works. It needs no API credentials."
                  : "Live comparison sends the case question and source packet to the selected API provider and may incur usage charges."}
              </p>
            </>
          )}
          <div className="official-engine-actions">
            <button
              type="submit"
              className="primary"
              disabled={
                busy ||
                !(view === "research" ? canStartResearch : canStartEvaluation)
              }
            >
              {view === "research" ? "Start research" : "Run evaluation"}
            </button>
            {(runningJob || pending) && (
              <span role="status" className="official-engine-progress">
                <Loader2 size={16} aria-hidden="true" />
                {pending
                  ? "Starting job…"
                  : refreshError
                    ? "Connection interrupted. Retrying…"
                    : runningJob?.kind === "research"
                      ? "Research running…"
                      : "Evaluation running…"}
              </span>
            )}
          </div>
          {submitError[view] && (
            <p className="official-engine-error" role="alert">
              {submitError[view]}
            </p>
          )}
        </form>

        {currentJob?.status === "error" && (
          <div className="official-engine-notice" role="alert">
            <CircleAlert size={18} aria-hidden="true" />
            <p>{currentJob.error || "The job ended with an error."}</p>
          </div>
        )}
        {currentJob?.status === "complete" &&
          currentJob.kind === "research" && (
            <div className="official-engine-notice good">
              <CheckCircle2 size={18} aria-hidden="true" />
              <p role="status">
                {researchResult?.runStatus === "error"
                  ? "The research run ended with an error. Inspect the saved run record."
                  : "Research complete. Inspect the report and decision trail."}
              </p>
              <button
                type="button"
                onClick={() => {
                  close();
                  onOpenRun(currentJob.id);
                }}
              >
                Review run record <ArrowUpRight size={14} aria-hidden="true" />
              </button>
            </div>
          )}
        {currentJob?.status === "complete" &&
          currentJob.kind === "evaluation" && (
            <EvaluationResults
              result={currentJob.result}
              cases={cases}
              caseId={evaluatedCaseId}
            />
          )}
      </div>
    </dialog>
  );
}
