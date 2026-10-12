/** Send a clearly labelled connectivity span, then confirm ingestion via the public API. */
import "dotenv/config";
import { RunnableLambda } from "@langchain/core/runnables";
import { startTracing, shutdownTracing, tracingBaseURL } from "../src/observability/langfuse.js";
const t = await startTracing({ runId: `connectivity-${Date.now()}`, tags: ["connectivity-check", "no-model"] });
if (!t.handler) throw new Error("Configure self-hosted Langfuse keys in the ignored .env first.");
try {
  await RunnableLambda.from(async () => ({ connected: true, modelCalled: false }))
    .invoke({ purpose: "trace export connectivity only" }, { callbacks: [t.handler], runName: "Langfuse connectivity check" });
  await t.flush();
  const info = t.info();
  const headers = { Authorization: `Basic ${Buffer.from(`${process.env.LANGFUSE_PUBLIC_KEY}:${process.env.LANGFUSE_SECRET_KEY}`).toString("base64")}` };
  let status = 404;
  for (let attempt = 0; attempt < 12; attempt++) {
    const r = await fetch(`${tracingBaseURL()}/api/public/v2/observations?traceId=${info.traceId}`, { headers });
    status = r.status;
    if (!r.ok) throw new Error(`Observation lookup returned HTTP ${status}.`);
    const body = await r.json() as { data?: unknown[] };
    if (body.data?.length) { console.log(JSON.stringify({ ...info, ingested: true, modelCalled: false })); break; }
    status = 404;
    await new Promise(resolve => setTimeout(resolve, 1500));
  }
  if (status !== 200) throw new Error("Trace did not appear after export.");
} finally { await shutdownTracing(); }
