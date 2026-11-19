import { expect, it } from "vitest";
import { freshMetrics, readModelResponse } from "../server/telemetry";
it("reads split UTF-8 SSE chunks and provider token timings", async () => {
  const encoder = new TextEncoder();
  const wire =
    "data: " +
    JSON.stringify({
      choices: [{ delta: { content: "你好" } }],
      timings: { predicted_n: 2, predicted_per_second: 99 },
    }) +
    "\r\n\r\n" +
    "data: " +
    JSON.stringify({
      choices: [],
      usage: { prompt_tokens: 20, completion_tokens: 2 },
    }) +
    "\n\ndata: [DONE]\n\n";
  const bytes = encoder.encode(wire);
  const stream = new ReadableStream({
    start(c) {
      for (let i = 0; i < bytes.length; i += 7)
        c.enqueue(bytes.slice(i, i + 7));
      c.close();
    },
  });
  const metrics = { ...freshMetrics(), started: Date.now() };
  const result = await readModelResponse(
    new Response(stream, { headers: { "Content-Type": "text/event-stream" } }),
    metrics,
  );
  expect(result.choices[0].message.content).toBe("你好");
  expect(metrics.outputTokens).toBe(2);
  expect(metrics.inputTokens).toBe(20);
  expect(metrics.tokensPerSecond).toBe(99);
});
it("does not count content chunks or characters as tokens", async () => {
  const metrics = freshMetrics();
  const r = new Response(
    'data: {"choices":[{"delta":{"content":"some long output"}}]}\n\ndata: [DONE]\n\n',
    { headers: { "Content-Type": "text/event-stream" } },
  );
  await readModelResponse(r, metrics);
  expect(metrics.characters).toBe(16);
  expect(metrics.outputTokens).toBeNull();
  expect(metrics.tokensPerSecond).toBeNull();
});
