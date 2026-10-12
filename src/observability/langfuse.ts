/**
 * Optional tracing to a self-hosted Langfuse instance. Enabled only when
 * LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set.
 *
 * The OpenTelemetry SDK is global, so it is started once per process and shut
 * down once at exit; each run gets its own callback handler and only flushes.
 */
import type { BaseCallbackHandler } from "@langchain/core/callbacks/base";

export interface Tracing {
  handler?: BaseCallbackHandler;
  info(): { enabled: boolean; traceId?: string; url?: string };
  /** Flush this run's spans; the SDK keeps running for other runs. */
  flush(): Promise<void>;
}

interface Provider {
  flush(): Promise<void>;
  shutdown(): Promise<void>;
}

let provider: Promise<Provider | undefined> | undefined;

function enabled(): boolean {
  return Boolean(process.env.LANGFUSE_PUBLIC_KEY && process.env.LANGFUSE_SECRET_KEY);
}

export function tracingBaseURL(env: NodeJS.ProcessEnv = process.env): string {
  const base = env.LANGFUSE_BASE_URL || "http://localhost:3000";
  const url = new URL(base);
  if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) || url.username || url.password || url.search || url.hash)
    throw new Error("This demo exports traces only to loopback self-hosted Langfuse.");
  return base.replace(/\/$/, "");
}

async function startProvider(): Promise<Provider | undefined> {
  if (!enabled()) return undefined;
  const { NodeSDK } = await import("@opentelemetry/sdk-node");
  const { LangfuseSpanProcessor } = await import("@langfuse/otel");
  const processor = new LangfuseSpanProcessor({ baseUrl: tracingBaseURL() });
  const sdk = new NodeSDK({ spanProcessors: [processor] });
  sdk.start();
  return { flush: () => processor.forceFlush(), shutdown: () => sdk.shutdown() };
}

export async function startTracing(meta: { runId: string; tags: string[] }): Promise<Tracing> {
  provider ??= startProvider();
  const p = await provider;
  if (!p) return { flush: async () => {}, info: () => ({ enabled: false }) };
  const { CallbackHandler } = await import("@langfuse/langchain");
  const handler = new CallbackHandler({ sessionId: meta.runId, tags: meta.tags, traceMetadata: { runId: meta.runId } });
  return { handler: handler as unknown as BaseCallbackHandler, flush: () => p.flush(), info: () => {
    const traceId = handler.last_trace_id ?? undefined;
    const project = process.env.LANGFUSE_PROJECT_ID;
    return { enabled: true, ...(traceId ? { traceId } : {}), ...(traceId && project ? {
      url: `${tracingBaseURL()}/project/${encodeURIComponent(project)}/traces/${traceId}` } : {}) };
  } };
}

/** Flush and stop tracing; call once before the process exits. */
export async function shutdownTracing(): Promise<void> {
  const p = await provider;
  if (!p) return;
  await p.flush().catch(() => {});
  await p.shutdown().catch(() => {});
}
