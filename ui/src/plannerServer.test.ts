import { createServer } from "node:http";
import { afterEach, describe, it, expect, vi } from "vitest";
import { plannerPlugin } from "../server/planner";
const realFetch = globalThis.fetch;
const servers: ReturnType<typeof createServer>[] = [];
afterEach(async () => {
  vi.unstubAllGlobals();
  await Promise.all(
    servers.splice(0).map(
      (s) =>
        new Promise<void>((resolve) => {
          s.close(() => resolve());
          s.closeAllConnections();
        }),
    ),
  );
});
async function launch(env: Record<string, string>) {
  let middleware: any;
  const plugin = plannerPlugin(env);
  (plugin.configureServer as Function)({
    middlewares: {
      use(fn: unknown) {
        middleware = fn;
      },
    },
  });
  const server = createServer((req, res) =>
    middleware(req, res, () => {
      res.statusCode = 404;
      res.end();
    }),
  );
  servers.push(server);
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const address = server.address() as { port: number };
  return `http://127.0.0.1:${address.port}`;
}
describe("planner HTTP adapter with fixture provider", () => {
  it("reports missing configuration without generating a template", async () => {
    const url = await launch({});
    const r = await realFetch(url + "/api/plan", {
      method: "POST",
      body: JSON.stringify({ question: "hello" }),
    });
    expect(r.status).toBe(503);
    expect(await r.json()).not.toHaveProperty("plan");
  });
  it("forwards the exact request and keeps the API key on the server", async () => {
    const provider = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            choices: [
              {
                message: { content: JSON.stringify({ tasks: [{ id: "a" }] }) },
              },
            ],
          }),
        ),
    );
    vi.stubGlobal("fetch", provider);
    const url = await launch({
      PLANNER_BASE_URL: "http://provider.invalid/v1",
      PLANNER_MODEL: "fixture-model",
      PLANNER_API_KEY: "fixture-secret",
    });
    const r = await realFetch(url + "/api/plan", {
      method: "POST",
      headers: { Origin: url },
      body: JSON.stringify({ question: "用7个搜索智能体研究太阳能" }),
    });
    expect(r.status).toBe(200);
    const result = await r.text();
    expect(result).not.toContain("fixture-secret");
    const options = (
      provider.mock.calls[0] as unknown as [unknown, RequestInit]
    )[1];
    expect(JSON.parse(options.body as string).messages[1].content).toBe(
      "用7个搜索智能体研究太阳能",
    );
    expect(JSON.parse(options.body as string).model).toBe("fixture-model");
  });
  it("rejects foreign origins and propagates provider failures without secrets", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () => new Response("private upstream detail", { status: 401 }),
      ),
    );
    const url = await launch({
      PLANNER_BASE_URL: "http://provider.invalid/v1",
      PLANNER_MODEL: "fixture-model",
    });
    const denied = await realFetch(url + "/api/plan", {
      method: "POST",
      headers: { Origin: "https://other.invalid" },
      body: "{}",
    });
    expect(denied.status).toBe(403);
    const response = await realFetch(url + "/api/plan", {
      method: "POST",
      body: JSON.stringify({ question: "topic" }),
    });
    expect(response.status).toBe(502);
    expect(await response.text()).not.toContain("private upstream detail");
  });
});

it("refuses a context smaller than the configured project minimum", async () => {
  const provider = vi.fn(
    async () =>
      new Response(
        JSON.stringify({ default_generation_settings: { n_ctx: 8192 } }),
      ),
  );
  vi.stubGlobal("fetch", provider);
  const url = await launch({
    PLANNER_BASE_URL: "http://provider.invalid/v1",
    PLANNER_MODEL: "fixture-model",
    PLANNER_MIN_CONTEXT: "262144",
  });
  const response = await realFetch(url + "/api/plan", {
    method: "POST",
    body: JSON.stringify({ question: "research topic" }),
  });
  expect(response.status).toBe(503);
  expect((await response.json()).error).toContain("262,144");
  expect(provider).toHaveBeenCalledTimes(1);
});

it("reads the active NInfer context from its model catalog", async () => {
  const provider = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          data: [
            { id: "ninfer-test", owned_by: "ninfer", max_model_len: 262144 },
          ],
        }),
      ),
  );
  vi.stubGlobal("fetch", provider);
  const url = await launch({
    PLANNER_BASE_URL: "http://provider.invalid/v1",
    PLANNER_MODEL: "ninfer-test",
    PLANNER_ENGINE: "ninfer",
  });
  const r = await realFetch(url + "/api/telemetry");
  const data = await r.json();
  expect(data.runtime.context).toBe(262144);
  expect(data.runtime.engine).toBe("NInfer");
  expect(data.config.temperature).toBe(0);
});

it("runs a search node with actual retrieved snippets passed to the model", async () => {
  const provider = vi.fn(async (target: unknown, options?: RequestInit) => {
    if (String(target).startsWith("https://html.duckduckgo.com/"))
      return new Response(
        '<div class="result"><a class="result__a" href="https://reactflow.dev/">React Flow</a><div class="result__snippet">Node editor</div></div>',
      );
    const payload = JSON.parse(options?.body as string);
    const input = JSON.parse(payload.messages[1].content);
    expect(input.searchResults[0].url).toBe("https://reactflow.dev/");
    expect(input.upstream).toEqual(["Scope from parent"]);
    return Response.json({
      choices: [{ message: { content: "A node editor with a source." } }],
    });
  });
  vi.stubGlobal("fetch", provider);
  const url = await launch({
    PLANNER_BASE_URL: "http://provider.invalid/v1",
    PLANNER_MODEL: "fixture-model",
  });
  const response = await realFetch(url + "/api/node", {
    method: "POST",
    body: JSON.stringify({
      question: "React Flow",
      node: {
        role: "Searcher",
        label: "Documentation",
        prompt: "Find sources",
        model: "fixture-model",
        budget: 2,
      },
      upstream: ["Scope from parent"],
    }),
  });
  expect(response.status).toBe(200);
  const result = await response.json();
  expect(result.output).toContain("https://reactflow.dev/");
  expect(result.performance.model).toBe("fixture-model");
  expect(result.performance.metrics.phase).toBe("complete");
  expect(result.performance.metrics.elapsedMs).toBeGreaterThanOrEqual(0);
  expect(provider).toHaveBeenCalledTimes(2);
});
it("stops on empty search results before calling the model", async () => {
  const provider = vi.fn(
    async () => new Response("<form>Service unavailable</form>"),
  );
  vi.stubGlobal("fetch", provider);
  const url = await launch({
    PLANNER_BASE_URL: "http://provider.invalid/v1",
    PLANNER_MODEL: "fixture-model",
  });
  const response = await realFetch(url + "/api/node", {
    method: "POST",
    body: JSON.stringify({
      question: "Topic",
      node: {
        role: "Searcher",
        label: "Search",
        prompt: "Find sources",
        model: "fixture-model",
        budget: 2,
      },
      upstream: [],
    }),
  });
  expect(response.status).toBe(502);
  expect((await response.json()).error).toContain("no usable results");
  expect(provider).toHaveBeenCalledTimes(1);
});
