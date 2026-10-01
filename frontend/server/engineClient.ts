import { Buffer } from "node:buffer";
export type Profile = {
  profile_ref: string;
  model_ref: string;
  provider: string;
};
export type Activity = {
  event: {
    event_id: string;
    kind: string;
    producer_timestamp: string;
    payload: Record<string, unknown>;
  };
  receipt: { recorded_seq: number };
};
export class EngineClient {
  constructor(readonly base: string) {
    const u = new URL(base);
    if (
      !["127.0.0.1", "localhost", "[::1]"].includes(u.hostname) ||
      !["http:", "https:"].includes(u.protocol) ||
      u.username ||
      u.password
    )
      throw new Error("Use a loopback Engine service URL.");
  }
  async call(path: string, body?: unknown, signal?: AbortSignal): Promise<any> {
    const r = await fetch(this.base + path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(30000)])
        : AbortSignal.timeout(30000),
      redirect: "error",
    });
    const data = await r.json();
    if (!r.ok)
      throw new Error(
        `${data.error?.code || r.status}: ${data.error?.message || "Engine request failed"}`,
      );
    return data;
  }
  async artifact(runId: string, id: string, signal?: AbortSignal) {
    const chunks: Buffer[] = [];
    let offset = 0;
    for (;;) {
      const part = await this.call(
        `/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(id)}?start=${offset}&max_bytes=65536`,
        undefined,
        signal,
      );
      if (
        part.encoding !== "base64" ||
        part.start !== offset ||
        part.next_offset < offset ||
        (!part.eof && part.next_offset === offset)
      )
        throw new Error("Engine returned an invalid artifact offset.");
      const bytes = Buffer.from(part.data, "base64");
      if (bytes.length !== part.next_offset - offset)
        throw new Error("Engine artifact chunk is incomplete.");
      chunks.push(bytes);
      offset = part.next_offset;
      if (offset > 8 * 1024 * 1024)
        throw new Error(
          "Report exceeds the 8 MiB UI limit. Read it with the Engine API.",
        );
      if (part.eof) return Buffer.concat(chunks).toString("utf8");
    }
  }
  async run(
    profile: Profile,
    instructions: string,
    input: string,
    tools: { name: string; revision: number }[],
    signal: AbortSignal,
    onActivity: (a: Activity) => void,
    onRun: (id: string) => void,
    toolBudget = 32,
  ) {
    toolBudget = Math.max(1, Math.min(32, Math.floor(toolBudget) || 1));
    const id = "ui_" + crypto.randomUUID().replaceAll("-", "");
    await this.call(
      "/agents",
      {
        schema_version: 1,
        agent_id: id,
        revision: 1,
        profile_ref: profile.profile_ref,
        model_ref: profile.model_ref,
        instructions,
        input_schema: { type: "string" },
        output_schema: { type: "string" },
        allowed_tools: tools,
        finalize_on_limit: true,
        limits: {
          max_run_seconds: 600,
          max_model_calls: 16,
          max_tool_calls: toolBudget,
          max_tool_attempts: toolBudget,
          ...(profile.provider === "ninfer" ? {
            max_context_tokens: 262144 - 4096,
            max_model_seconds: 180,
          } : {}),
        },
      },
      signal,
    );
    // Admission can finish after a browser disconnect. Keep the handle so it can be cancelled.
    const handle = await this.call("/runs", {
      schema_version: 1,
      agent_id: id,
      revision: 1,
      input,
      timeout_seconds: 600,
      limits: { model_calls: 16, tool_calls: toolBudget },
      metadata: { client: "inse-691-ui" },
    });
    const runId = handle.run_id;
    onRun(runId);
    const cancel = () => {
      void this.call(`/runs/${encodeURIComponent(runId)}/cancel`, {}).catch(
        () => {},
      );
    };
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
    let settled = false;
    let cursor = 0;
    const seen = new Set<string>();
    const drain = async () => {
      let more = true;
      while (more) {
        const page = await this.call(
          `/runs/${encodeURIComponent(runId)}/events?after_seq=${cursor}&limit=100`,
          undefined,
          signal,
        );
        for (const row of page.events) {
          if (!seen.has(row.event.event_id)) {
            seen.add(row.event.event_id);
            onActivity(row);
          }
        }
        if (page.has_more && page.next_after_seq <= cursor)
          throw new Error("Engine event cursor did not advance.");
        cursor = page.next_after_seq;
        more = page.has_more;
      }
    };
    try {
      for (;;) {
        signal.throwIfAborted();
        const status = await this.call(
          `/runs/${encodeURIComponent(runId)}`,
          undefined,
          signal,
        );
        await drain();
        if (!status.active) { settled = true; break; }
        await new Promise<void>((resolve) => setTimeout(resolve, 500));
      }
      const result = await this.call(
        `/runs/${encodeURIComponent(runId)}/result`,
        undefined,
        signal,
      );
      if (
        result.status !== "succeeded" ||
        result.recording_status !== "complete" ||
        result.persistence_state !== "committed" ||
        !result.available ||
        !result.output_ref
      )
        throw new Error(
          `${result.error?.code || result.status}: ${result.error?.message || "Run did not produce a complete saved report."} (run ${runId})`,
        );
      const output = await this.artifact(
        runId,
        result.output_ref.artifact_id,
        signal,
      );
      const usage = await this.call(
        `/runs/${encodeURIComponent(runId)}/usage`,
        undefined,
        signal,
      );
      return { output, runId, usage: usage.usage };
    } catch (error) {
      if (!settled && !signal.aborted) await this.call(`/runs/${encodeURIComponent(runId)}/cancel`, {}).catch(() => {});
      throw error;
    } finally {
      signal.removeEventListener("abort", cancel);
    }
  }
}
