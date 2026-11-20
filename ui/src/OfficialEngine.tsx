import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ArrowUpRight, CheckCircle2, CircleAlert, Loader2, X } from "lucide-react";
import "./OfficialEngine.css";

type Props = {
  open: boolean;
  onClose: () => void;
  onOpenRun: (jobId: string) => void;
};
type Catalog = {
  profiles: string[];
  liveProfiles: string[];
};
type Job = {
  id: string;
  status: "running" | "complete" | "error";
  error?: string;
  result?: { runStatus?: string };
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

export function OfficialEngine({ open, onClose, onOpenRun }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [catalog, setCatalog] = useState<Catalog>();
  const [catalogError, setCatalogError] = useState("");
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [question, setQuestion] = useState("");
  const [strategy, setStrategy] = useState<"ebd" | "baseline">("ebd");
  const [researchProfile, setResearchProfile] = useState("");
  const [budget, setBudget] = useState("6");
  const [job, setJob] = useState<Job>();
  const [submitError, setSubmitError] = useState("");
  const [pending, setPending] = useState(false);
  const submitting = useRef(false);
  const [refreshError, setRefreshError] = useState(false);

  const running = job?.status === "running";
  const activeJobId = running ? job.id : undefined;
  const liveProfiles = catalog?.liveProfiles ?? [];
  const officialProfiles =
    catalog?.profiles.filter((profile) => liveProfiles.includes(profile)) ?? [];
  const selectedResearchProfile = officialProfiles.includes(researchProfile)
    ? researchProfile
    : (officialProfiles[0] ?? "");
  const parsedBudget = Number(budget);
  const canStartResearch =
    selectedResearchProfile &&
    Boolean(question.trim()) &&
    Number.isInteger(parsedBudget) &&
    parsedBudget >= 1 &&
    parsedBudget <= 12;
  const busy = running || pending;

  useEffect(() => {
    const element = dialog.current;
    if (open && element && !element.open) element.showModal();
    if (!open && element?.open) element.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (window.location.protocol === "file:") {
      setCatalogError(
        "The engine is unavailable in an offline preview. Open the integrated app to run research.",
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
    if (!open || !activeJobId) return;
    const id = activeJobId;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    function poll() {
      void engineRequest<Job>(`/jobs/${encodeURIComponent(id)}`, {
        signal: controller.signal,
      })
        .then((job) => {
          if (controller.signal.aborted) return;
          setRefreshError(false);
          setJob(job);
          if (job.status === "running") timer = setTimeout(poll, 1200);
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          if (error instanceof RequestFailure && error.status === 404) {
            setJob({
              id,
              status: "error",
              error:
                "The engine no longer reports this job. If it finished, its record may still be available on disk.",
            });
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
  }, [open, activeJobId]);

  function close() {
    dialog.current?.close();
    onClose();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canStartResearch || busy || submitting.current) return;
    submitting.current = true;
    setPending(true);
    setSubmitError("");
    setRefreshError(false);
    try {
      const newJob = await engineRequest<Job>("/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "research",
          question,
          strategy,
          profile: selectedResearchProfile,
          researchers: parsedBudget,
        }),
      });
      setJob(newJob);
    } catch (error) {
      setSubmitError(
        errorMessage(
          error,
          "The engine did not confirm that the job started. Check the service before retrying.",
        ),
      );
    } finally {
      submitting.current = false;
      setPending(false);
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
          <h2 id={titleId}>Research engine</h2>
        </div>
        <button
          type="button"
          onClick={close}
          aria-label="Close research engine"
        >
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      <div className="official-engine-body">
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
          <div className="official-engine-actions">
            <button
              type="submit"
              className="primary"
              disabled={busy || !canStartResearch}
            >
              Start research
            </button>
            {busy && (
              <span role="status" className="official-engine-progress">
                <Loader2 size={16} aria-hidden="true" />
                {pending
                  ? "Starting job…"
                  : refreshError
                    ? "Connection interrupted. Retrying…"
                    : "Research running."}
              </span>
            )}
          </div>
          {submitError && (
            <p className="official-engine-error" role="alert">
              {submitError}
            </p>
          )}
        </form>

        {job?.status === "error" && (
          <div className="official-engine-notice" role="alert">
            <CircleAlert size={18} aria-hidden="true" />
            <p>{job.error || "The job ended with an error."}</p>
          </div>
        )}
        {job?.status === "complete" && (
          <div className="official-engine-notice good">
            <CheckCircle2 size={18} aria-hidden="true" />
            <p role="status">
              {job.result?.runStatus === "error"
                ? "The research run ended with an error. Inspect the saved run record."
                : "Research complete. Inspect the report and decision trail."}
            </p>
            <button
              type="button"
              onClick={() => {
                close();
                onOpenRun(job.id);
              }}
            >
              Review run record <ArrowUpRight size={14} aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    </dialog>
  );
}
