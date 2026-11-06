import { describe, expect, it } from "vitest";
import { fetchSession, langfuseConfig, type Observation } from "./traces.js";

const cfg = { publicKey: "pk-lf-test", secretKey: "sk-lf-test", baseUrl: "http://localhost:3000" };

function obs(id: string, startTime: string, extra: Partial<Observation> = {}): Observation {
  return { id, traceId: "t1", projectId: "p1", parentObservationId: null, type: "SPAN", name: id, startTime, endTime: startTime, ...extra };
}

describe("Langfuse traces for the run viewer", () => {
  it("reads the keys from the environment, and is off without them", () => {
    expect(langfuseConfig({ LANGFUSE_PUBLIC_KEY: "pk", LANGFUSE_SECRET_KEY: "sk", LANGFUSE_BASE_URL: "http://lf:3000/" })).toEqual({ publicKey: "pk", secretKey: "sk", baseUrl: "http://lf:3000" });
    expect(langfuseConfig({ LANGFUSE_PUBLIC_KEY: "pk" })).toBeNull();
  });

  it("finds the run's trace by session, reads all its observations by trace with every page, and cuts long inputs", async () => {
    const urls: URL[] = [];
    const auths: string[] = [];
    // The session is on the root observation only; the trace query returns the whole trace in two pages.
    const fake = (async (url: string | URL | Request, init?: RequestInit) => {
      const u = new URL(String(url));
      urls.push(u);
      auths.push(String((init?.headers as Record<string, string>).Authorization));
      const p = u.searchParams;
      const body = p.has("sessionId")
        ? { data: [obs("root", "2026-11-05T10:00:00Z")], meta: { cursor: null } }
        : p.get("cursor") === "next"
          ? { data: [obs("a", "2026-11-05T10:00:01Z")], meta: { cursor: null } }
          : { data: [obs("root", "2026-11-05T10:00:00Z"), obs("b", "2026-11-05T10:00:02Z", { input: "x".repeat(7000) })], meta: { cursor: "next" } };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;
    const out = await fetchSession(cfg, "run-1", { from: "2026-11-05T09:50:00Z", to: "2026-11-05T11:00:00Z" }, fake);
    expect(out.map((o) => o.id)).toEqual(["root", "a", "b"]);
    expect(out[2]!.input!.length).toBeLessThan(6100);
    expect(out[2]!.input).toContain("more characters in Langfuse");
    expect(urls[0]!.pathname).toBe("/api/public/v2/observations");
    expect(Object.fromEntries(urls[0]!.searchParams)).toMatchObject({ sessionId: "run-1", fromStartTime: "2026-11-05T09:50:00Z", limit: "1000" });
    expect(urls[0]!.searchParams.get("fields")).toContain("usage");
    expect(urls[1]!.searchParams.get("traceId")).toBe("t1");
    expect(urls[2]!.searchParams.get("cursor")).toBe("next");
    expect(new Set(auths)).toEqual(new Set([`Basic ${Buffer.from("pk-lf-test:sk-lf-test").toString("base64")}`]));
  });

  it("reports an HTTP error with its status", async () => {
    const fake = (async () => new Response("unauthorized", { status: 401 })) as typeof fetch;
    await expect(fetchSession(cfg, "run-1", { from: "a", to: "b" }, fake)).rejects.toThrow(/401/);
  });
});
