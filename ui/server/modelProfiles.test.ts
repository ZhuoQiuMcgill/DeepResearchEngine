import { EventEmitter } from "node:events";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Connect } from "vite";
import { afterEach, expect, it, vi } from "vitest";
import { plannerPlugin } from "./planner";

afterEach(() => vi.unstubAllGlobals());

function requestHandler(env: Record<string, string>) {
  let middleware: Connect.NextHandleFunction;
  const install = plannerPlugin(env).configureServer as (server: {
    middlewares: { use: (handler: Connect.NextHandleFunction) => void };
  }) => void;
  install({ middlewares: { use: (handler) => (middleware = handler) } });

  return async (url: string, body?: Record<string, unknown>) => {
    const req = Object.assign(
      Readable.from(body ? [Buffer.from(JSON.stringify(body))] : []),
      { url, method: body ? "POST" : "GET", headers: {} },
    );
    const res = Object.assign(new EventEmitter(), {
      statusCode: 200,
      writableEnded: false,
      destroyed: false,
      payload: "",
      setHeader() {},
      end(payload: string) {
        this.payload = payload;
        this.writableEnded = true;
      },
    });
    await middleware(
      req as unknown as IncomingMessage,
      res as unknown as ServerResponse,
      () => {
        throw new Error("Expected planner route");
      },
    );
    return { status: res.statusCode, data: JSON.parse(res.payload) };
  };
}

it("routes both model profiles and keeps API flags, credentials and telemetry separate", async () => {
  const provider = vi.fn(async (target: URL | string, init?: RequestInit) => {
    const url = new URL(target);
    if (url.pathname.endsWith("/models"))
      return Response.json({
        data: [{ id: "local-qwen", owned_by: "ninfer", max_model_len: 262144 }],
      });
    return Response.json({
      choices: [
        { message: { content: JSON.stringify({ tasks: [{ id: "a" }] }) } },
      ],
    });
  });
  vi.stubGlobal("fetch", provider);
  const request = requestHandler({
    PLANNER_BASE_URL: "http://127.0.0.1:18086/v1",
    PLANNER_MODEL: "local-qwen",
    PLANNER_ENGINE: "ninfer",
    PLANNER_ENABLE_THINKING: "false",
    PLANNER_MIN_CONTEXT: "262144",
    PLANNER_REMOTE_BASE_URL: "https://provider.invalid/v1",
    PLANNER_REMOTE_MODEL: "remote-model",
    PLANNER_REMOTE_API_KEY: "fixture-secret",
  });

  const catalog = await request("/api/planner");
  expect(catalog.data).toEqual({
    configured: true,
    model: "local-qwen",
    defaultProfile: "local",
    profiles: [
      { id: "local", model: "local-qwen" },
      { id: "api", model: "remote-model" },
    ],
  });

  expect(
    (
      await request("/api/plan", {
        question: "Explain EBD",
        profile: "invalid",
      })
    ).status,
  ).toBe(400);
  expect(provider).not.toHaveBeenCalled();

  const api = await request("/api/node", {
    profile: "api",
    requestId: "api-request",
    question: "Explain EBD",
    node: {
      role: "Writer",
      prompt: "Explain",
      label: "Writer",
      model: "local-model",
    },
    upstream: [],
  });
  expect(api.status).toBe(200);
  expect(api.data.performance.model).toBe("remote-model");
  expect(provider).toHaveBeenCalledTimes(1);
  const [apiUrl, apiInit] = provider.mock.calls[0];
  expect(String(apiUrl)).toBe("https://provider.invalid/v1/chat/completions");
  expect(new Headers(apiInit?.headers).get("Authorization")).toBe(
    "Bearer fixture-secret",
  );
  const apiBody = JSON.parse(apiInit?.body as string);
  expect(apiBody.model).toBe("remote-model");
  expect(apiBody).not.toHaveProperty("enable_thinking");
  expect(apiBody).not.toHaveProperty("timings_per_token");
  expect(apiBody).not.toHaveProperty("chat_template_kwargs");

  const apiTelemetry = await request("/api/telemetry?profile=api");
  expect(apiTelemetry.data).toMatchObject({
    profile: "api",
    requestId: "api-request",
    runtime: { context: null },
  });
  expect(provider).toHaveBeenCalledTimes(1);
  const local = await request("/api/plan", {
    question: "Explain EBD",
    requestId: "local-request",
  });
  expect(local.status).toBe(200);
  expect(local.data.model).toBe("local-qwen");
  const [localUrl, localInit] = provider.mock.calls[2];
  expect(String(localUrl)).toBe("http://127.0.0.1:18086/v1/chat/completions");
  expect(new Headers(localInit?.headers).get("Authorization")).toBeNull();
  expect(JSON.parse(localInit?.body as string)).toMatchObject({
    enable_thinking: false,
    model: "local-qwen",
  });
  const localTelemetry = await request("/api/telemetry?profile=local");
  expect(localTelemetry.data).toMatchObject({
    profile: "local",
    requestId: "local-request",
    runtime: { context: 262144 },
  });
  expect((await request("/api/telemetry?profile=api")).data.requestId).toBe(
    "api-request",
  );
});

it("retains an API-only setup and rejects unavailable local selection", async () => {
  const provider = vi.fn(async () =>
    Response.json({ choices: [{ message: { content: '{"tasks":[]}' } }] }),
  );
  vi.stubGlobal("fetch", provider);
  const request = requestHandler({
    PLANNER_BASE_URL: "https://provider.invalid/v1",
    PLANNER_MODEL: "legacy-api-model",
  });
  expect((await request("/api/planner")).data.defaultProfile).toBe("api");
  expect(
    (await request("/api/plan", { question: "Explain EBD", profile: "local" }))
      .status,
  ).toBe(503);
  expect(provider).not.toHaveBeenCalled();
  expect(
    (await request("/api/plan", { question: "Explain EBD" })).data.model,
  ).toBe("legacy-api-model");
  expect(provider).toHaveBeenCalledTimes(1);
});
