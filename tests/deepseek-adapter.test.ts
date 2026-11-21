import { readFileSync } from "node:fs";
import { AIMessage, HumanMessage } from "@langchain/core/messages";
import { describe, expect, it } from "vitest";
import { PROFILES, type DeepSeekProfile } from "../src/config/models.js";
import { UsageLedger } from "../src/observability/usage.js";
import {
  MAX_RESEARCH_REQUESTS,
  NOTES_REQUEST,
  RESEARCH_REQUEST,
  cleanDeepSeekUrl,
  cleanDeepSeekUrlsInText,
  deepseekTools,
  parseDeepSeekResponse,
  runDeepSeek,
  type DeepSeekInvoke,
  type DeepSeekResponse,
} from "../src/research/adapters/deepseek.js";

/** The profile's mode, deep search, and the documented capped alternative. */
const deep = PROFILES.deepseek as DeepSeekProfile;
const capped: DeepSeekProfile = { ...deep, webSearch: { type: "web_search_20250305", maxUses: 12 } };

describe("deepseek profile", () => {
  it("uses DeepSeek's deep search with the shared soft budget", () => {
    expect(deep.webSearch).toEqual({ type: "deepseek_web_search" });
    expect(deep.toolCallsPerResearcher).toBe(12);
  });
});

/** Recorded Messages API responses, trimmed (see `_note` in each file). */
function fixture(name: string): DeepSeekResponse {
  const file = new URL(`./fixtures/deepseek/${name}.json`, import.meta.url);
  return (JSON.parse(readFileSync(file, "utf8")) as { response: DeepSeekResponse }).response;
}

const use = (id: string, input: Record<string, unknown>, name = "web_search") => ({ type: "server_tool_use", id, name, input });

describe("deepseek adapter: web_search_20250305 with max_uses", () => {
  const { output: out, cachedInputTokens } = parseDeepSeekResponse(fixture("web-search-capped"), capped);

  it("counts executed searches and keeps only their queries", () => {
    expect(out.searches).toBe(5);
    expect(out.pageReads).toBe(0);
    expect(out.queries).toEqual([
      "Environment Based Design EBD Zeng",
      '"Environment-Based Design" methodology proposed',
      'Zeng Cheng 1991 recursive logic design "a new logic for design"',
      'Yong Zeng Concordia "Environment-Based Design" research group EBD theory',
      'EBD "solution generation" "conflict identification" environment analysis active reactive conflict Zeng',
    ]);
  });

  it("reports the rejected attempt as a cap diagnostic, and the counters agree", () => {
    expect(out.diagnostics).toEqual([
      expect.stringMatching(/^tool cap reached: 1 web_search call\(s\) rejected \(max_uses_exceeded\) after 5 executed search\(es\), max_uses=12, e\.g\. .*design governing equation/),
    ]);
  });

  it("totals input tokens with cache hits and keeps the cached part", () => {
    expect(out.inputTokens).toBe(25563 + 31872);
    expect(cachedInputTokens).toBe(31872);
    expect(out.outputTokens).toBe(5715);
  });

  it("takes the notes from the text after the last tool result", () => {
    expect(out.notes.startsWith("## Who proposed EBD and when?")).toBe(true);
    expect(out.notes).not.toContain("I'll research");
  });

  it("lists every search result without DeepSeek's result markers", () => {
    expect(out.sources).toHaveLength(50);
    expect(out.sources.some((s) => /#\d+$/.test(s.url))).toBe(false);
    expect(out.sources.map((s) => s.url)).toContain("https://dl.acm.org/doi/10.3233/jid-2015-0004");
    expect(out.sources.find((s) => s.url.startsWith("https://ieeexplore.ieee.org/document/6912695"))?.title).toBeTruthy();
    expect(out.citedUrls).toEqual([]);
  });
});

describe("deepseek adapter: deepseek_web_search (deep search)", () => {
  const { output: out } = parseDeepSeekResponse(fixture("deep-search"), deep);

  it("counts search calls, page opens and every query", () => {
    expect(out.searches).toBe(2);
    expect(out.pageReads).toBe(4);
    expect(out.queries).toHaveLength(4);
    expect(out.queries[3]).toBe('"Environment-Based Design" "question-driven" Zeng');
  });

  it("keeps structured citations and opened pages, markers removed", () => {
    expect(out.citedUrls).toEqual([
      "https://asmedigitalcollection.asme.org/IDETC-CIE/proceedings-abstract/IDETC-CIE2011/54860/237/354151",
      "https://www.cambridge.org/core/journals/ai-edam/article/enhancing-triz-through-environmentbased-design-methodology-supported-by-a-large-language-model/C3305E839793A17763076FF8BF510E08",
      "https://dl.acm.org/doi/10.3233/jid-2015-0004",
      "https://ieeexplore.ieee.org/document/6912695",
    ]);
    expect(out.sources).toContainEqual({
      url: "https://ieeexplore.ieee.org/document/6912695",
      title: "Conflict identification in conceptual design: Algorithm and case study - Conflict identification in conceptual design: Algorithm and case study",
    });
    expect(out.sources).toHaveLength(13 + 7 + 4);
  });

  it("joins the final text blocks into the notes", () => {
    expect(out.notes).toContain("EBD is described as a question-driven design methodology.");
    expect(out.notes).toContain("Environment analysis is the first EBD activity");
  });

  it("states on every result that the cap is not enforced", () => {
    expect(out.diagnostics).toEqual([
      "tool-call cap not enforced: deepseek_web_search has no per-researcher limit; 6 tool call(s) against a cap of 12",
    ]);
  });
});

/** A model call that answers with the given recorded responses, one per call, and records what it was sent. */
function scripted(replies: (DeepSeekResponse | Error)[]) {
  const sent: { messages: number; last: string; toolChoice: string | undefined }[] = [];
  const invoke: DeepSeekInvoke = async (messages, options) => {
    sent.push({ messages: messages.length, last: String(messages.at(-1)?.content), toolChoice: options.tool_choice });
    const r = replies.shift();
    if (!r || r instanceof Error) throw r ?? new Error("no scripted reply");
    const meta = r.error ? { type: "error", error: r.error } : { stop_reason: r.stop_reason };
    return new AIMessage({ content: r.content as never, response_metadata: { usage: r.usage, ...meta } });
  };
  return { invoke, sent };
}

const callWith = (ledger: UsageLedger, signal = new AbortController().signal) => ({ messages: [new HumanMessage("brief")], ledger, role: "researcher", signal });

describe("deepseek adapter: replies that only announce the research", () => {
  const announcement = fixture("announcement");

  it("asks the model to go ahead, on the same conversation, and keeps the research reply", async () => {
    const { invoke, sent } = scripted([announcement, announcement, fixture("deep-search")]);
    const ledger = new UsageLedger(deep.pricing);
    const out = await runDeepSeek(deep, callWith(ledger), invoke);
    expect(sent).toEqual([
      { messages: 1, last: "brief", toolChoice: undefined },
      { messages: 3, last: RESEARCH_REQUEST, toolChoice: undefined },
      { messages: 3, last: RESEARCH_REQUEST, toolChoice: undefined },
    ]);
    expect(out.notes).toContain("EBD is described as a question-driven design methodology.");
    expect(out.notes).not.toContain("I'll");
    expect(out.searches).toBe(2);
    expect(out.pageReads).toBe(4);
    expect(out.inputTokens).toBe(2 * (1219 + 896) + 8790 + 19968);
    expect(out.diagnostics).toContain("the model only announced its research; it started after 2 follow-up turn(s)");
    expect(ledger.byRole.researcher?.calls).toBe(3);
  });

  it("returns no notes when the model never starts", async () => {
    const { invoke, sent } = scripted(Array.from({ length: MAX_RESEARCH_REQUESTS + 1 }, () => announcement));
    const out = await runDeepSeek(deep, callWith(new UsageLedger(deep.pricing)), invoke);
    expect(sent).toHaveLength(MAX_RESEARCH_REQUESTS + 1);
    expect(out.notes).toBe("");
    expect(out.diagnostics).toContain(`the model only announced its research; ${MAX_RESEARCH_REQUESTS} follow-up turn(s) did not start it`);
  });

  it("retries an error sent with HTTP 200 once and counts its tokens", async () => {
    const error: DeepSeekResponse = {
      content: [],
      error: { type: "api_error", message: "The model failed to generate a complete response. Please retry." },
      usage: { input_tokens: 29746, cache_read_input_tokens: 154112, output_tokens: 3345, server_tool_use: { web_search_requests: 4, web_fetch_requests: 12, tool_search: 16 } },
    };
    const { invoke } = scripted([error, fixture("deep-search")]);
    const out = await runDeepSeek(deep, callWith(new UsageLedger(deep.pricing)), invoke);
    expect(out.notes).toContain("question-driven");
    expect(out.inputTokens).toBe(29746 + 154112 + 8790 + 19968);
    expect(out.diagnostics).toContain(
      "provider error in a 200 response, retried once: api_error: The model failed to generate a complete response. Please retry.",
    );
    expect(out.diagnostics.some((d) => d.includes("disagrees"))).toBe(false);
  });

  it("counts page actions on the open page as reads without a source", () => {
    const { output } = parseDeepSeekResponse(
      {
        stop_reason: "end_turn",
        usage: { input_tokens: 1, output_tokens: 1, server_tool_use: { web_search_requests: 0, web_fetch_requests: 1, tool_search: 0 } },
        content: [
          use("p", { action: "find_in_page", url: "", pattern: "week" }, "deepseek_web_search"),
          { type: "web_fetch_tool_result", tool_use_id: "p", content: { type: "web_fetch_result", url: "", content: { type: "document", title: null } } },
          { type: "text", text: "## Q\n### Takeaway\nx" },
        ],
      },
      deep,
    );
    expect(output.pageReads).toBe(1);
    expect(output.sources).toEqual([]);
    expect(output.diagnostics.filter((d) => d.startsWith("web_fetch"))).toEqual([]);
  });
});

describe("deepseek adapter: tool_use stop without notes", () => {
  const stop = fixture("tool-use-stop");

  it("is reported when parsed on its own", () => {
    const { output } = parseDeepSeekResponse(stop, capped);
    expect(output.notes).toBe("");
    expect(output.searches).toBe(5);
    expect(output.diagnostics.at(-1)).toBe("unexpected stop_reason tool_use");
  });

  it("asks once for the notes with tools disabled and keeps the first call's searches", async () => {
    const { invoke, sent } = scripted([stop, fixture("continuation")]);
    const ledger = new UsageLedger(capped.pricing);
    const out = await runDeepSeek(capped, callWith(ledger), invoke);
    expect(sent).toEqual([
      { messages: 1, last: "brief", toolChoice: undefined },
      { messages: 3, last: NOTES_REQUEST, toolChoice: "none" },
    ]);
    expect(out.notes.startsWith("## At which university, laboratory or company")).toBe(true);
    expect(out.searches).toBe(5);
    expect(out.queries).toHaveLength(5);
    expect(out.inputTokens).toBe(23471 + 36096 + 24223 + 384);
    expect(out.outputTokens).toBe(1219 + 12767);
    expect(out.diagnostics).toEqual([
      expect.stringMatching(/^tool cap reached: 2 web_search call\(s\) rejected \(max_uses_exceeded\) after 5 executed search\(es\)/),
      "search loop ended with stop_reason tool_use and no notes; asked once for the notes with tools disabled",
    ]);
    expect(ledger.byRole.researcher).toMatchObject({ calls: 2, searches: 5, inputTokens: out.inputTokens, cachedInputTokens: 36096 + 384 });
  });

  it("keeps the first call's record when the continuation fails", async () => {
    const { invoke } = scripted([stop, new Error("400 bad request")]);
    const ledger = new UsageLedger(capped.pricing);
    const out = await runDeepSeek(capped, callWith(ledger), invoke);
    expect(out.notes).toBe("");
    expect(out.searches).toBe(5);
    expect(out.diagnostics.slice(-2)).toEqual([
      "unexpected stop_reason tool_use",
      "search loop ended with stop_reason tool_use and no notes; the continuation failed: 400 bad request",
    ]);
    expect(ledger.byRole.researcher?.calls).toBe(1);
  });

  it("lets a timeout during the continuation through", async () => {
    const controller = new AbortController();
    const { invoke } = scripted([stop]);
    const aborting: DeepSeekInvoke = async (messages, options) => {
      if (messages.length > 1) {
        controller.abort();
        throw Object.assign(new Error("Request was aborted."), { name: "AbortError" });
      }
      return invoke(messages, options);
    };
    await expect(runDeepSeek(capped, callWith(new UsageLedger(capped.pricing), controller.signal), aborting)).rejects.toThrow("aborted");
  });

  it("records a tool_use stop after deep search without continuing", async () => {
    // The capped fixture's blocks stand in for a deep-search reply; only the stop matters here.
    const { invoke, sent } = scripted([stop]);
    const ledger = new UsageLedger(deep.pricing);
    const out = await runDeepSeek(deep, callWith(ledger), invoke);
    expect(sent).toHaveLength(1);
    expect(out.notes).toBe("");
    expect(out.diagnostics.slice(-2)).toEqual([
      "unexpected stop_reason tool_use",
      "search loop ended with stop_reason tool_use and no notes; not continued, because DeepSeek does not re-read deep-search results in a follow-up turn",
    ]);
    expect(ledger.byRole.researcher?.calls).toBe(1);
  });

  it("does not continue a reply that ended normally", async () => {
    const { invoke, sent } = scripted([fixture("web-search-capped")]);
    await runDeepSeek(capped, callWith(new UsageLedger(capped.pricing)), invoke);
    expect(sent).toHaveLength(1);
  });
});

describe("deepseek adapter: failures and drift", () => {
  it("reports search and fetch errors in both result forms", () => {
    const { output } = parseDeepSeekResponse(
      {
        stop_reason: "end_turn",
        usage: { input_tokens: 10, output_tokens: 5, server_tool_use: { web_search_requests: 2, web_fetch_requests: 1, tool_search: 0 } },
        content: [
          use("a", { query: "q1" }),
          use("b", { query: "q2" }),
          use("c", { action: "open_page", url: "https://x.org/p#1" }, "deepseek_web_search"),
          { type: "web_search_tool_result", tool_use_id: "a", content: { type: "web_search_tool_result_error", error_code: "unavailable" } },
          { type: "web_search_tool_result", tool_use_id: "b", content: [{ type: "web_search_tool_result_error", error_code: "unavailable" }] },
          { type: "web_fetch_tool_result", tool_use_id: "c", content: { type: "web_fetch_tool_result_error", error_code: "url_not_accessible" } },
          { type: "text", text: "## Q\n### Gaps\n- No source found." },
        ],
      },
      capped,
    );
    expect(output.searches).toBe(0);
    expect(output.pageReads).toBe(0);
    expect(output.queries).toEqual([]);
    expect(output.sources).toEqual([]);
    expect(output.diagnostics).toEqual([
      'web_search error: unavailable for input {"query":"q1"}',
      'web_search error: unavailable for input {"query":"q2"}',
      'web_fetch error: url_not_accessible for input {"action":"open_page","url":"https://x.org/p#1"}',
    ]);
    expect(output.notes).toBe("## Q\n### Gaps\n- No source found.");
  });

  it("flags truncation, refusals, missing results and counter mismatches", () => {
    const base = { usage: { input_tokens: 1, output_tokens: 1, server_tool_use: { web_search_requests: 3, tool_search: 1 } } };
    const content = [use("a", { query: "q" }), { type: "web_search_tool_result", tool_use_id: "a", content: [{ type: "web_search_result", url: "https://a.org/x", title: "A" }] }, use("b", { query: "lost" })];
    const truncated = parseDeepSeekResponse({ ...base, stop_reason: "max_tokens", content }, capped).output;
    expect(truncated.diagnostics).toEqual([
      '1 tool call(s) without a result, e.g. {"query":"lost"}',
      "usage.server_tool_use disagrees with the response blocks: web_search_requests=3 (parsed 1)",
      "output truncated at max_tokens",
    ]);
    const refused = parseDeepSeekResponse({ usage: { input_tokens: 1, output_tokens: 0 }, stop_reason: "refusal", content: [] }, capped).output;
    expect(refused.diagnostics).toEqual(["the provider refused the request (stop_reason refusal)"]);
    expect(refused.notes).toBe("");
  });
});

describe("deepseek adapter: URLs and tools", () => {
  it("removes result markers and tracking parameters, keeping real fragments", () => {
    expect(cleanDeepSeekUrl("https://a.org/x.pdf#1#6#1")).toBe("https://a.org/x.pdf");
    expect(cleanDeepSeekUrl("https://a.org/x?utm_source=deepseek#1")).toBe("https://a.org/x");
    expect(cleanDeepSeekUrl("https://a.org/x#section-2")).toBe("https://a.org/x#section-2");
    expect(
      cleanDeepSeekUrlsInText("[A](https://a.org/x#1); https://b.org/y#1#6#1. Keep https://c.org/z#sec-2 and https://d.org/p#12abc"),
    ).toBe("[A](https://a.org/x); https://b.org/y. Keep https://c.org/z#sec-2 and https://d.org/p#12abc");
  });

  it("sends max_uses only with the capped search tool", () => {
    expect(deepseekTools(capped)).toEqual([{ type: "web_search_20250305", name: "web_search", max_uses: 12 }]);
    expect(deepseekTools(deep)).toEqual([{ type: "deepseek_web_search", name: "deepseek_web_search" }]);
  });
});
