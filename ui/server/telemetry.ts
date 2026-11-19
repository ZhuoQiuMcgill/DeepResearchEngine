export type Metrics = {
  phase: string;
  started: number;
  elapsedMs: number;
  firstTokenMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  tokensPerSecond: number | null;
  prefillPerSecond: number | null;
  characters: number;
};
export const freshMetrics = (): Metrics => ({
  phase: "idle",
  started: 0,
  elapsedMs: 0,
  firstTokenMs: null,
  inputTokens: null,
  outputTokens: null,
  tokensPerSecond: null,
  prefillPerSecond: null,
  characters: 0,
});
const finite = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null;
export function updateMetrics(metrics: Metrics, data: any) {
  metrics.inputTokens =
    finite(data.usage?.prompt_tokens) ??
    finite(data.timings?.prompt_n) ??
    metrics.inputTokens;
  metrics.outputTokens =
    finite(data.usage?.completion_tokens) ??
    finite(data.timings?.predicted_n) ??
    metrics.outputTokens;
  metrics.tokensPerSecond =
    finite(data.timings?.predicted_per_second) ?? metrics.tokensPerSecond;
  metrics.prefillPerSecond =
    finite(data.timings?.prompt_per_second) ?? metrics.prefillPerSecond;
}
export async function readModelResponse(response: Response, metrics: Metrics) {
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    const data = await response.json();
    updateMetrics(metrics, data);
    return data;
  }
  let content = "",
    pending = "";
  const decoder = new TextDecoder();
  const consume = (line: string) => {
    if (!line.startsWith("data:")) return;
    const payload = line.slice(5).trim();
    if (!payload || payload === "[DONE]") return;
    const data = JSON.parse(payload);
    if (data.error) throw new Error("Provider stream failed");
    updateMetrics(metrics, data);
    const delta = data.choices?.[0]?.delta?.content;
    if (typeof delta === "string" && delta.length) {
      if (metrics.firstTokenMs === null)
        metrics.firstTokenMs = Date.now() - metrics.started;
      metrics.phase = "generating";
      content += delta;
      metrics.characters = content.length;
    }
  };
  if (!response.body) throw new Error("Missing stream");
  const reader = response.body.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      pending += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      let index;
      while ((index = pending.indexOf("\n")) >= 0) {
        consume(pending.slice(0, index).replace(/\r$/, ""));
        pending = pending.slice(index + 1);
      }
      if (content.length + pending.length > 2000000)
        throw new Error("Model response too large");
      if (done) {
        if (pending.trim()) consume(pending);
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }
  return { choices: [{ message: { content } }] };
}
