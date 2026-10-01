import type { RunEvent } from "./workflow";
export async function readNodeStream(
  response: Response,
  onActivity: (event: any) => void,
  onRun: (id: string) => void,
) {
  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.error || "Engine request failed.");
  }
  if (!response.body) throw new Error("Engine response stream missing.");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let pending = "",
    result: any;
  const consume = (line: string) => {
    if (!line.trim()) return;
    const row = JSON.parse(line);
    if (row.type === "error") throw new Error(row.error);
    if (row.type === "activity") onActivity(row.activity);
    if (row.type === "run") onRun(row.runId);
    if (row.type === "result") result = row;
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      pending += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      let i;
      while ((i = pending.indexOf("\n")) >= 0) {
        consume(pending.slice(0, i));
        pending = pending.slice(i + 1);
      }
      if (done) break;
    }
    consume(pending);
    if (!result)
      throw new Error(
        "Engine connection ended before the result arrived. Inspect Engine history before starting another run.",
      );
    return result;
  } finally {
    reader.releaseLock();
  }
}
export function activityEvent(
  row: any,
  nodeId: string,
  label: string,
): RunEvent {
  return {
    id: row.event.event_id,
    nodeId,
    label,
    status: "running",
    time: row.event.producer_timestamp,
    message: `${row.event.kind}\n${JSON.stringify(row.event.payload, null, 2)}`,
  };
}
