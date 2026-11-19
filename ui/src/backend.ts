/** Proposed independent backend contract. Not enabled by the demo UI. */
import { clean, type Workflow, type RunEvent } from "./workflow";
export async function startRemoteRun(
  baseUrl: string,
  workflow: Workflow,
  signal?: AbortSignal,
): Promise<string> {
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow: clean(workflow) }),
    signal,
  });
  if (!response.ok) throw new Error(`Run request failed (${response.status})`);
  const body = await response.json();
  if (typeof body.runId !== "string" || !body.runId)
    throw new Error("Backend returned no run ID.");
  return body.runId;
}
export function subscribeRun(
  baseUrl: string,
  runId: string,
  onEvent: (event: RunEvent) => void,
  onError: (error: Error) => void,
): () => void {
  const stream = new EventSource(
    `${baseUrl.replace(/\/$/, "")}/runs/${encodeURIComponent(runId)}/events`,
  );
  stream.onmessage = (message) => {
    try {
      const e = JSON.parse(message.data);
      if (
        !["running", "done", "failed"].includes(e.status) ||
        !["id", "nodeId", "label", "message", "time"].every(
          (k) => typeof e[k] === "string",
        )
      )
        throw new Error("Invalid run event.");
      onEvent(e);
    } catch (error) {
      onError(error as Error);
    }
  };
  stream.onerror = () => {
    stream.close();
    onError(new Error("Run event stream disconnected."));
  };
  return () => stream.close();
}
