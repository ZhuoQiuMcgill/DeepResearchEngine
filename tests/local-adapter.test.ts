import { createServer } from "node:http";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { HumanMessage } from "@langchain/core/messages";
import { it, expect } from "vitest";
import { localProfile } from "../src/config/models.js";
import { UsageLedger } from "../src/observability/usage.js";
import { runLocal } from "../src/research/adapters/local.js";

it("bounds a parallel tool batch and returns correlated declined results before the final answer", async () => {
  const dir = mkdtempSync(join(tmpdir(), "local-research-"));
  const corpusPath = join(dir, "papers.json");
  writeFileSync(corpusPath, JSON.stringify([{ id: "paper", title: "Environment Based Design", url: "https://example.org/paper",
    text: "Environment analysis identifies objects and relationships.", sha256: "test" }]));
  const bodies: any[] = [];
  const server = createServer(async (req, res) => {
    const chunks = []; for await (const c of req) chunks.push(c);
    const body = JSON.parse(Buffer.concat(chunks).toString()); bodies.push(body);
    const message = bodies.length === 1 ? { role: "assistant", content: null, tool_calls: [
      { id: "search", type: "function", function: { name: "search_local_documents", arguments: '{"query":"environment"}' } },
      { id: "read", type: "function", function: { name: "read_local_document", arguments: '{"id":"paper","start":0}' } },
    ] } : { role: "assistant", content: "Environment analysis is a phase of EBD. [Paper](https://example.org/paper)" };
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ id: "controlled", object: "chat.completion", model: "local-test", choices: [{ index: 0,
      finish_reason: bodies.length === 1 ? "tool_calls" : "stop", message }], usage: { prompt_tokens: 10, completion_tokens: 3, total_tokens: 13 } }));
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const addr = server.address() as { port: number };
    const profile = { ...localProfile({ LOCAL_MODEL_BASE_URL: `http://127.0.0.1:${addr.port}/v1` }), corpusPath, toolCallsPerResearcher: 1 };
    const ledger = new UsageLedger(profile.pricing);
    const out = await runLocal(profile, { messages: [new HumanMessage("What is EBD?")], ledger, role: "researcher", signal: AbortSignal.timeout(10000) });
    expect(out.searches).toBe(1); expect(out.pageReads).toBe(0);
    expect(bodies).toHaveLength(2); expect(bodies[1].tool_choice).toBe("none");
    const results = bodies[1].messages.filter((m: any) => m.role === "tool");
    expect(results.map((r: any) => r.tool_call_id)).toEqual(["search", "read"]);
    expect(results[1].content).toContain("not executed");
    expect(out.sources.map(s => s.url)).toEqual(["https://example.org/paper"]);
    expect(ledger.byRole.researcher?.calls).toBe(2);
    expect(ledger.total().inputTokens).toBe(20);
  } finally { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); rmSync(dir, { recursive: true }); }
});
