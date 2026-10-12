import { describe, it, expect } from "vitest";
import { createWebTools, type WebProviders } from "../src/research/web-tools.js";
import { UsageLedger } from "../src/observability/usage.js";
import { localProfile, getProfile } from "../src/config/models.js";
import type { AdapterOutput } from "../src/research/adapters/types.js";
import { TavilySearch } from "@langchain/tavily";

function setup(providers: WebProviders) {
  const out: AdapterOutput = { notes: "", sources: [], citedUrls: [], queries: [], inputTokens: 0,
    outputTokens: 0, searches: 0, pageReads: 0, diagnostics: [] };
  const ledger = new UsageLedger(localProfile({}).pricing);
  const tools = createWebTools(out, { messages: [], ledger, role: "researcher", signal: AbortSignal.timeout(10000) }, providers);
  return { out, ledger, tools };
}
describe("managed web tools", () => {
  it("separates the web profile from offline research without recording a key", () => {
    expect(getProfile("local-web").name).toBe("local-web");
    expect((getProfile("local-web") as any).sourceMode).toBe("tavily-web");
    const serialized = JSON.stringify(new TavilySearch({ tavilyApiKey: "serialization-test-sentinel" }).toJSON());
    expect(serialized).not.toContain("serialization-test-sentinel");
  });
  it("only reads searched public URLs, bounds content, and counts actual operations", async () => {
    let reads = 0;
    const { out, ledger, tools } = setup({
      search: { invoke: async () => ({ results: [{ url: "https://example.org/paper", title: "Paper", content: "a".repeat(9000) },
        { url: "http://127.0.0.1/private", title: "Private" }] }) },
      extract: { invoke: async () => { reads++; return { results: [{ url: "https://example.org/paper", raw_content: "b".repeat(90000) }] }; } },
    });
    expect(await tools[1]!.invoke({ url: "https://example.org/not-seen" })).toContain("Read only");
    expect(reads).toBe(0);
    const s = JSON.parse(await tools[0]!.invoke({ query: "EBD" }));
    expect(s.results).toHaveLength(1); expect(s.results[0].content).toHaveLength(2400);
    const r = JSON.parse(await tools[1]!.invoke({ url: "https://example.org/paper" }));
    expect(r.results[0].text).toHaveLength(32000); expect(r.results[0].truncated).toBe(true);
    expect(reads).toBe(1); expect(out.queries).toEqual(["EBD"]);
    expect(ledger.total().searches).toBe(1); expect(ledger.total().pageReads).toBe(1);
    expect(ledger.total().calls).toBe(0);
  });
  it("does not turn a search-provider failure into a source", async () => {
    const { out, tools } = setup({ search: { invoke: async () => ({ error: "provider unavailable" }) },
      extract: { invoke: async () => ({ results: [] }) } });
    expect(await tools[0]!.invoke({ query: "EBD" })).toContain("no usable results");
    expect(out.sources).toEqual([]); expect(out.diagnostics).toHaveLength(1);
  });
});
