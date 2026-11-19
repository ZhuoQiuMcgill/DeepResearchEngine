import { useEffect, useId, useRef } from "react";
import { ArrowRight, Globe2, ListOrdered } from "lucide-react";
import { executionOrder, type Workflow } from "./workflow";
import "./WorkflowPreflight.css";

type Props = {
  workflow: Workflow;
  model?: { profile: "local" | "api"; name: string };
  onClose: () => void;
  onStart: () => void;
};

function preview(workflow: Workflow) {
  try {
    if (!workflow.question.trim())
      throw new Error("Enter a research question before starting.");
    if (workflow.question.length > 6000)
      throw new Error("Keep the research question within 6,000 characters.");

    const byId = new Map(workflow.nodes.map((node) => [node.id, node]));
    const order = executionOrder(workflow.nodes, workflow.edges).map((id) =>
      byId.get(id)!,
    );
    return { order, error: null };
  } catch (error) {
    return {
      order: [],
      error:
        error instanceof Error
          ? error.message
          : "Review the workflow configuration.",
    };
  }
}

export function WorkflowPreflight({
  workflow,
  model,
  onClose,
  onStart,
}: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const back = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const questionId = useId();
  const orderId = useId();
  const { order, error } = preview(workflow);
  const hasSearch = order.some((node) => node.data.role === "Searcher");

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    element.showModal();
    back.current?.focus({ preventScroll: true });
    return () => element.close();
  }, []);

  function dismiss(action: () => void) {
    dialog.current?.close();
    action();
  }

  return (
    <dialog
      ref={dialog}
      className="workflow-preflight"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        dismiss(onClose);
      }}
    >
      <h2 id={titleId}>Review before running</h2>

      <section aria-labelledby={questionId}>
        <h3 id={questionId}>Research question</h3>
        <p className="workflow-preflight-question" tabIndex={0}>
          {workflow.question.trim()
            ? workflow.question
            : "No question entered."}
        </p>
      </section>

      {error ? (
        <p className="workflow-preflight-error" role="alert">
          {error}
        </p>
      ) : (
        <section aria-labelledby={orderId}>
          <h3 id={orderId}>
            <ListOrdered size={16} aria-hidden="true" />
            Execution order{" "}
            <span>
              {order.length} {order.length === 1 ? "task" : "tasks"}
            </span>
          </h3>
          <ol
            tabIndex={order.length > 4 ? 0 : undefined}
            aria-labelledby={orderId}
          >
            {order.map(({ id, data }) => (
              <li key={id}>
                <strong>{data.label}</strong> <span>{data.role}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="workflow-preflight-scope">
        <Globe2 size={17} aria-hidden="true" />
        <div>
          {model ? (
            <>
              <p>
                <strong>
                  {model.profile === "api" ? "API model" : "Local Qwen"}
                </strong>
                {` · ${model.name}`}. Tasks run one at a time. Keep this tab
                open during the run.
              </p>
              {model.profile === "api" && (
                <p>
                  The provider receives your question, task instructions, and
                  any source snippets or earlier results used by the task.
                </p>
              )}
            </>
          ) : (
            <p>Connect a model to start this workflow.</p>
          )}
          {hasSearch && (
            <p>
              Search tasks send query text based on the question and task title
              to DuckDuckGo. They use public result snippets and links as source
              material.
            </p>
          )}
        </div>
      </div>

      <div className="workflow-preflight-actions">
        <button type="button" ref={back} onClick={() => dismiss(onClose)}>
          Back to workflow
        </button>
        <button
          type="button"
          className="primary"
          onClick={() => dismiss(onStart)}
          disabled={Boolean(error) || !model}
        >
          Start run <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
    </dialog>
  );
}
