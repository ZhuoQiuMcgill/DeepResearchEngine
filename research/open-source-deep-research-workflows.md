# Open-Source Deep Research Workflows

Research date: 2026-09-09. 16 projects profiled in depth; 177 more listed in the appendix. Every profile was written from primary sources by one agent and then fact-checked by an independent adversarial agent.

## Executive summary

The sixteen projects profiled here span three orders of magnitude in popularity, from DR Tulu at 707 stars to ByteDance's DeerFlow at 82,139, and they are not variations on one design. They fall into four orchestration families. Deterministic graphs and fixed pipelines (Google's Gemini LangGraph quickstart, Stanford's STORM, dzhng's deep-research) hard-code the control flow and let the model fill slots. Supervisor architectures with parallel sub-agents (LangChain's Open Deep Research, deepagents, GPT Researcher, Hugging Face's smolagents example) fan work out to isolated researchers and merge compressed findings. Single-agent iterative loops (DeerFlow, Khoj, PaperQA2, Dexter) put everything in one tool-calling loop and manage context instead of topology. Finally, RL-trained open-weight models (Alibaba's Tongyi DeepResearch, MiroThinker, Ai2's DR Tulu, WebThinker) move the planning intelligence into the weights and ship a deliberately thin harness.

Maturity varies more than star counts suggest. Genuinely maintained and productized: GPT Researcher (three years of releases, committed eval logs), PaperQA2, Khoj, Local Deep Research, deepagents (active but pre-1.0 and breaking), DeerFlow (daily commits, one release, 919 open items). Frozen or dormant: LangChain's Open Deep Research was archived read-only on 2026-08-21, STORM's last commit was 2025-09-30, the Gemini quickstart has not moved since 2025-06-18, dzhng's last functional change was 2025-05-27, and the smolagents example has been effectively frozen since late 2025. Among the open-weight releases, Tongyi has been quiet since February 2026 and MiroThinker's main branch since March.

No vendor open-sourced its actual product, and the gap is not subtle. Google published a DevRel template with four nodes and no maintainer. Hugging Face published a GAIA answer machine with no citation layer at all. ByteDance rewrote DeerFlow into a general SuperAgent harness where deep research is one prompt file among twenty-three skills, and features its own commercial search service. LangChain archived its research graph and now points at a general harness. MiroMind's best system, H1, has no released weights. The closest thing to product parity is the RL-trained weights, where the model is the artifact and the repository is a benchmark rig.

Three takeaways. First, stars track launch timing and framing, not research depth: the 19.7k-star dzhng repo has no per-claim attribution, while the 707-star DR Tulu has citation grounding trained into the policy. Second, citation handling is the weakest layer almost everywhere; only four projects verify anything mechanically. Third, the real engineering has migrated from orchestration into context management, page summarization before context entry, sub-agent isolation, and compaction with recoverable history.

## Taxonomy

### Graph and state-machine pipelines

These hard-code the control flow in code, so depth, breadth and stopping are explicit constructs rather than model judgment. They are the easiest to reason about and the least adaptive.

- **Gemini Fullstack LangGraph Quickstart** (Google, Apache-2.0): four LangGraph nodes, Send-based parallel fan-out with operator.add reducers, and a reflection node whose is_sufficient flag plus a loop counter governs depth. Frozen since June 2025.
- **STORM / Co-STORM** (Stanford OVAL, MIT): four fixed DSPy stages, with parallel persona-conditioned writer/expert dialogues as the research phase; Co-STORM adds a turn-policy discourse manager over a shared mind map. Dormant since September 2025.
- **deep-research (dzhng)** (MIT): a self-recursive async function, breadth halving per level, no tool loop at all; every LLM call is a single-shot structured generation. Feature-frozen, widely forked.

### Supervisor plus parallel sub-agents

A lead agent decomposes the task and delegates to researchers with isolated context, whose findings are compressed before returning. This is the archetype most people mean by "deep research agent" and the one with the clearest cost controls.

- **Open Deep Research (LangChain, MIT, archived)**: nested LangGraph state machines, a supervisor bound to exactly three tools, asyncio.gather over researcher subgraphs with a concurrency cap, per-researcher compression. The canonical reference, now read-only.
- **deepagents** (LangChain, MIT): not a research system but the harness beneath one, wrapping create_agent in middleware for filesystem offload, subagent delegation, summarization and permissions; the research pipeline lives in one example's prompts.
- **GPT Researcher** (Assaf Elovic, Apache-2.0): plan once, then flat asyncio fan-out over sub-queries with embedding-based compression; a separate recursive deep mode and a LangGraph editor/reviewer/reviser app ship in the same repo.
- **smolagents open_deep_research** (Hugging Face, Apache-2.0): a two-level manager/worker pair, a code-writing CodeAgent over a text-browser ToolCallingAgent, with re-planning every four steps and a remaining-steps budget. A GAIA reproduction, not a report writer.

### Single-agent iterative loops

One tool-calling loop does everything, with budgets and context engineering standing in for topology. Delegation, where it exists, is bounded to one level and often discouraged.

- **DeerFlow** (ByteDance, MIT): a single LangChain create_agent loop wrapped in roughly twenty-five ordered middlewares, with capped task/batch_task delegation and citation verification against a tool-receipt ledger.
- **Khoj** (Khoj Inc., AGPL-3.0): five iterations of plan-then-parallel-tool-fan-out over personal documents and the web, with a mid-run interrupt queue for user steering and no clarification by design.
- **PaperQA2** (FutureHouse, Apache-2.0): a ReAct tool-selection loop over an aviary environment, with two-stage retrieval (embedding recall then per-chunk LLM summarization and relevance scoring) and strict citation-key discipline.
- **Dexter** (Virat Singh, MIT by README only): a ten-iteration loop with read-only, non-recursive parallel subagents, heavy context compaction, and structured financial data tools alongside web search.

### RL-trained open-weight research models

Here the orchestration is in the weights. The repositories ship thin harnesses, benchmark runners and checkpoints, and the interesting artifact is the model rather than the graph.

- **Tongyi DeepResearch** (Alibaba, Apache-2.0): a 30B-A3B MoE trained end to end, driven by a single ReAct loop with goal-conditioned page extraction; the Heavy multi-agent mode behind the headline numbers is unreleased.
- **MiroThinker** (MiroMind, Apache-2.0): 30B and 235B open weights, recency-based context retention keeping only the last five tool observations, rollback guards for malformed tags, duplicate queries and empty results, and fourteen benchmark harnesses.
- **DR Tulu** (Ai2, Apache-2.0): an 8B policy trained with evolving-rubric RL, emitting snippet-ID citations as a trained behavior, shipped with its SFT and RL data, trainer and eval harness.
- **WebThinker** (RUC-NLPIR, MIT): a single continuous generation with special-token tool interception, a nested Deep Web Explorer sub-loop and incremental section drafting, plus DPO-trained 7B/14B/32B checkpoints.

### Full-stack applications with a UI

These are the projects a non-engineer could actually use. Each also appears above under its orchestration archetype; the distinguishing feature is delivery surface rather than control flow.

- **DeerFlow**: Next.js web UI, FastAPI gateway with a LangGraph-compatible API, a Textual TUI, scheduled tasks and seven IM transports.
- **Khoj**: web UI on port 42110 plus Desktop, Obsidian, Emacs, Android and WhatsApp clients, backed by Django and pgvector.
- **Local Deep Research**: FastAPI and Socket.IO web UI, authenticated REST API, Python client and an MCP server.
- **Gemini Fullstack LangGraph Quickstart**: React chat UI streaming a live activity timeline of graph nodes, the clearest demonstration of making a research loop visible.

### Local and private-first tools

The stacks that can run with nothing leaving the machine, either because retrieval is local or because the weights are.

- **Local Deep Research** (LearningCircuit, MIT): Ollama plus SearXNG runs the whole loop offline, with per-user SQLCipher encryption, six egress scopes that filter the agent's tool list, and signed images with SBOMs.
- **PaperQA2**: retrieval is a local tantivy index over your own PDFs; external calls are metadata enrichment, not discovery.
- **Khoj**: self-hostable with a local model via any OpenAI-compatible endpoint, indexing your own corpus in pgvector.
- **Tongyi DeepResearch, MiroThinker, DR Tulu**: open weights make the reasoning local even when search is not, with DR Tulu the cheapest at 8B.

### Other and domain-specialized

Two projects are not general research engines at all, and one is a benchmark artifact wearing a research agent's name.

- **Dexter**: finance-specific, with statements, segments, insider trades, institutional holdings, SEC section extraction and a screener behind the loop.
- **PaperQA2**: scientific literature only, with journal-quality scoring, retraction checks and DOI resolution, and no built-in web search.
- **smolagents open_deep_research**: a GAIA reproduction with no citation handling, valuable as a teaching skeleton rather than as a deliverable-producing system.

## Comparison

| Project | Maintainer | License | Stars | Language | Orchestration | LLMs | Search backends | Benchmarks | Best fit |
|---|---|---|---|---|---|---|---|---|---|
| DeerFlow | ByteDance | MIT | 82.1k | Python + TS | Single create_agent loop, ~25 middlewares, capped subagents | Any OpenAI-compatible, config-driven | 13 (DuckDuckGo default, Tavily, Brave, Serper, Exa, InfoQuest) | None published | Self-hosted multi-skill agent platform with UI and IM delivery |
| Khoj | Khoj Inc. | AGPL-3.0 | 37.2k | Python | Single loop, parallel tool fan-out, 5 iterations | OpenAI, Anthropic, Google, OpenAI-compatible | Serper, Exa, Firecrawl, Google PSE, SearXNG | FRAMES 63.5, SimpleQA 86.0 (self, 2024) | Assistant over your own notes plus the web |
| STORM / Co-STORM | Stanford OVAL | MIT | 31.3k | Python | Fixed 4-stage pipeline, parallel persona dialogues; Co-STORM turn policy | litellm (any) | 11 (Bing, You, Serper, Brave, SearXNG, DuckDuckGo, Tavily, Azure) | FreshWiki self-report; DeepScholar-Bench third-party, weak | Wikipedia-style surveys, citable academic baseline |
| GPT Researcher | Assaf Elovic | Apache-2.0 | 29.4k | Python | Plan-and-execute, asyncio sub-queries; recursive deep mode; LangGraph app | 27 providers, 3 model tiers | 21 retrievers, Tavily default | SimpleQA 92.9 (self); DeepResearchGym best citation precision | Embeddable report generator with many pluggable backends |
| smolagents open_deep_research | Hugging Face | Apache-2.0 | 29.3k (parent repo) | Python | Manager CodeAgent + browser ToolCallingAgent, re-plan every 4 steps | LiteLLM (any); default o1 | Serper only (SerpApi for google: addresses) | GAIA val 55.15 (self), 49.7 (third-party) | Minimal readable agent skeleton to fork |
| deepagents | LangChain | MIT | 29.2k | Python (+ TS port) | Middleware-wrapped ReAct supervisor with task subagents | Any LangChain tool-calling model | None in SDK; example uses Tavily | Model evals only; no research-pipeline score | Harness for long-horizon agents you will prompt yourself |
| Dexter | Virat Singh | MIT (README only, no LICENSE file) | 27.6k | TypeScript | ReAct loop (max 10) + one-level parallel read-only subagents | OpenAI, Anthropic, Google, xAI, DeepSeek, Moonshot, Ollama | Exa, Perplexity, Tavily, LangSearch, X | None published; 50-question in-tree rubric eval | Financial research over filings and fundamentals |
| Tongyi DeepResearch | Alibaba Tongyi Lab | Apache-2.0 | 19.9k | Python | Single ReAct loop over RL-trained 30B-A3B weights | Own weights via vLLM or OpenRouter | Serper only (web + scholar) | HLE 32.9, BrowseComp 43.4, GAIA 70.9, xbench 75.0 (self) | Open weights for hard multi-hop search |
| deep-research (dzhng) | David Zhang | MIT (package.json says ISC) | 19.7k | TypeScript | Recursive breadth/depth tree, no tool loop | OpenAI, Fireworks, any OpenAI-compatible | Firecrawl only | None | Teaching and forking a minimal research loop |
| Gemini Fullstack LangGraph Quickstart | Google (DevRel) | Apache-2.0 (backend pyproject says MIT) | 18.3k | Python + TS | LangGraph 4-node graph, Send fan-out, reflection-gated loop | Gemini only | Gemini google_search grounding only | None | Learning LangGraph and grounded citation plumbing |
| Open Deep Research (LangChain) | LangChain (archived) | MIT | 12.7k | Python | Supervisor + parallel researcher subgraphs, per-agent compression | Any via init_chat_model, 4 roles | Tavily, OpenAI/Anthropic native search, MCP | DeepResearch Bench RACE 0.4943 | Fork-and-own supervisor baseline, teaching material |
| PaperQA2 | FutureHouse | Apache-2.0 | 9.2k | Python | ReAct tool selection over aviary env; optional RL-trainable agents | litellm (any) | Local tantivy index; Crossref, Semantic Scholar, OpenAlex metadata | LitQA2 66.0 accuracy / 85.2 precision; AstaBench third-party retrieval | Cited QA over a PDF corpus you already hold |
| Local Deep Research | LearningCircuit | MIT | 9.1k | Python | Pluggable strategies; default LangGraph supervisor + subagents | Ollama, LM Studio, vLLM, OpenAI, Anthropic, Gemini, OpenRouter | 30+ (arXiv, PubMed, Semantic Scholar, SearXNG, Tavily, Brave, local docs) | Self-reported, partly self-graded SimpleQA and xbench | Private, local-first research with academic sources |
| MiroThinker | MiroMind | Apache-2.0 | 8.4k | Python | ReAct loop over RL-trained weights, keep-last-5 context, rollbacks | Own 30B/235B weights; anthropic, openai, qwen clients | Serper (plus Sogou, blacklisted in 1.7) | BrowseComp 74.0, GAIA 82.7, HLE 42.9 (self) | Self-hosted SOTA-class browsing agent on your GPUs |
| WebThinker | RUC-NLPIR | MIT | 1.5k | Python | Single-generation loop, token interception, nested Deep Web Explorer | Any OpenAI-compatible; QwQ-32B + auxiliary instruct model | Bing, Serper | GAIA 48.5, HLE 15.8, WebWalkerQA 46.5 (self) | Studying or training interleaved reasoning agents |
| DR Tulu | Ai2 | Apache-2.0 | 707 | Python | Single RL-trained ReAct loop over MCP tools, forced-synthesis fallback | DR-Tulu-8B via vLLM; litellm for debugging | Serper, Semantic Scholar, PubMed, Jina, Crawl4AI, local BM25/FAISS | DeepResearch Bench 45.4; long-form average 65.6 (self) | Cheap cited long-form research with trained attribution |

## Recommendations for building your own engine

### What to read for each layer

For planning, read LangChain's Open Deep Research first. Its write_research_brief node collapses an entire conversation into one string, and its think_tool is a no-op that forces reflection into the transcript rather than into a separate node, which is a cheap trick worth stealing. Then read smolagents for periodic re-planning: it re-plans every four steps in summary mode, with the old plan stripped so it cannot anchor the new one, and tells the model how many steps remain. STORM is the outlier worth studying for breadth, since its personas generate diverse questions that a single planner will not think to ask.

For parallel research, LangChain's supervisor is again the cleanest: it slices delegation calls to a concurrency cap and returns an error message to the supervisor telling it to retry with fewer units, which beats silently dropping work. The Gemini quickstart shows the LangGraph idiom properly, Send fan-out with operator.add reducers on the merge, and offsets branch identifiers so citation handles stay unique across loops. Dexter and deepagents both demonstrate the constraint that matters most: delegation exactly one level deep, subagents read-only and unable to recurse, only a final message returning to the parent.

For source reading, Tongyi DeepResearch has the best idea in the set. Pages are fetched through Jina, then compressed by a separate summarizer model against the caller's stated goal, so raw HTML never enters the agent's context. MiroThinker's keep-last-five tool observations, retaining the full thought trace but discarding old observations, is the complementary move. smolagents has the strongest non-HTML coverage, converting PDFs, spreadsheets, slides, audio and archives to markdown.

For citations, only four projects verify anything. The Gemini quickstart recovers character-level grounding spans from the API, splices markers in mechanically, then drops sources that did not survive into the final text. PaperQA2 keys every context and enumerates invalid citation formats in the prompt. DeerFlow cross-checks parsed citations against a harvested tool-receipt ledger. DR Tulu trains snippet-ID attribution into the policy. Everything else is a prompt instruction and a trailing URL dump.

For evaluation, GPT Researcher commits its run logs, PaperQA2 ships the exact configs used in its papers, and DR Tulu publishes trainer, data and harness together.

### Recurring patterns and pitfalls

Two-tier retrieval (cheap recall, then per-chunk LLM scoring or summarization) shows up wherever quality is measured. Budgets, not planners, do the real depth control everywhere. Common failures to avoid: plan-once-never-revisit, snippet-only search that never reads a page, iteration counters that a wide parallel turn burns instantly, exception handlers that swallow a whole research branch, and documentation that drifts from the code within months. Assume every published score is self-reported until you find a third party who reran it.

## Detailed project reports

### 1. DeerFlow

Repository: https://github.com/bytedance/deer-flow
License: MIT | Stars: 82,139 (2026-09-09) | Language: Python | Pattern: Single LangGraph create_agent tool-calling loop (lead agent) plus middleware chain, with bounded optional sub-agent delegation via task/batch_task
Fact-check: minor-issues, 5 corrections applied

#### Overview

DeerFlow (Deep Exploration and Efficient Research Flow) is maintained by ByteDance at `bytedance/deer-flow`, MIT-licensed, with Python as the primary language for the backend harness and TypeScript/Next.js for the web frontend. As of 2026-09-09 the GitHub API reports 82,139 stars and 11,321 forks. The tracker holds 528 open issues and 391 open pull requests (919 combined, which is what the API's `open_issues_count` field reports). The repository was created 2025-05-07 and last pushed 2026-09-09 (latest commit `0d49253`, "fix(infoquest): bound HTTP connect and read waits (#5315)"), so it is under daily development.

The important thing to know is that the project the original "plan then research then cited report" description refers to is gone. DeerFlow 2.0 is described in the repo as "a ground-up rewrite. It shares no code with v1"; the original Deep Research framework lives on the `main-1.x` branch, and active development moved to 2.0. The current self-description is "an open-source long-horizon SuperAgent harness that researches, codes, and creates." Deep research is now one skill among roughly twenty-three, not the product.

Release history is thin relative to the star count: the only published GitHub release is `v2.0.0` on 2026-06-25, preceded by tags `v2.0-m0` through `v2.0.0-rc1`. `backend/pyproject.toml` already declares `2.1.0`, and the CHANGELOG's Unreleased section accumulates toward the 2.1.0 milestone with a long list of breaking changes. The README notes DeerFlow took the #1 GitHub Trending spot on 2026-02-28 after the v2 launch. Maturity: architecturally serious and heavily engineered, but young as a 2.x line, with a changelog that breaks config shapes between minor versions.

#### Workflow architecture

The orchestration pattern is a single tool-calling agent loop, not a research-specific state machine. `assemble_lead_agent()` in `backend/packages/harness/deerflow/agents/lead_agent/agent.py` builds the graph with LangChain's prebuilt `create_agent(model=..., tools=..., middleware=..., system_prompt=..., state_schema=get_thread_state_schema(mode))`; `make_lead_agent(config)` (line 757) just returns `.graph` and is the LangGraph Server ABI declared in `backend/langgraph.json`. There are no hand-written `StateGraph`/`add_node` calls in the lead agent. Everything that looks like a pipeline is either middleware or prompt.

The middleware chain, documented in `docs/ARCHITECTURE.md` and assembled by `build_middlewares()` in `agent.py` (lines 457-735), is where the control flow actually lives. Order matters, because LangChain dispatches middleware hooks in list order (and `after_model` hooks in reverse), and the actual append order is: InputSanitization, ToolOutputBudget, ToolResultSanitization, ThreadData (workspace/uploads/outputs paths), Uploads, Sandbox acquisition, DynamicContext, SkillActivation, DeferredToolPromotionAudit, SkillToolPolicy, DurableContext, Summarization (context reduction), Todo, TokenUsage, Title, Memory, ViewImage, MCP routing, DeferredToolFilter, SystemMessageCoalescing, SubagentLimit, LoopDetection, TokenBudget, any custom or configured middleware, TerminalResponse, ModelLengthFinishReason, SafetyFinishReason, and Clarification last. Note in particular that Todo precedes Title and Memory precedes ViewImage. State is `ThreadState`, extending LangGraph's `AgentState` with `sandbox`, `artifacts`, `thread_data`, `title`, `todos`, `viewed_images`.

Mapping the requested deep-research stages onto this:

- Clarification is a tool, not a phase. `tools/builtins/clarification_tool.py` defines `ask_clarification` with `clarification_type` in `{missing_info, ambiguous_requirement, approach_choice, risk_confirmation, suggestion}` plus structured form fields; it is `return_direct` and `ClarificationMiddleware` interrupts the run to surface it. Non-interactive runs (scheduled tasks) drop it entirely.
- Planning is optional plan mode. `_create_todo_list_middleware(is_plan_mode)` returns a `TodoMiddleware` extending LangChain's `TodoListMiddleware`. Its notable behavior: when the model emits a final response with incomplete todos, it queues a reminder and jumps back to the model node to prevent premature exit, and it re-injects the todo list if summarization scrolled the original `write_todos` call out of context.
- Query generation, search, page reading, gap analysis and depth/breadth control are all prompt-level, in `skills/public/deep-research/SKILL.md`. That skill defines four phases: Broad Exploration (survey, identify dimensions, map territory), Deep Dive (specific queries, multiple phrasings, `web_fetch` for full content, follow references), Diversity and Validation (a table forcing facts/data, examples, expert opinion, trends, comparisons, and criticisms), and a Synthesis Check gate of five checkboxes that instructs the model to keep researching if any answer is no. Temporal-precision rules and a "stopping after 1-2 searches" anti-pattern list are included. Depth control is therefore model judgment against a checklist, not a loop counter.
- Delegation is bounded and deliberately discouraged. `tools/builtins/task_tool.py` exposes `task`; the prompt section "Subagent Routing: Delegate Only for Clear Net Benefit" states "Default to direct execution" and enforces hard per-response and per-run caps, backed by `SubagentLimitMiddleware(max_concurrent=..., max_total=...)`. Built-in subagents are only `general-purpose` and `bash_agent` (`subagents/builtins/`); the general-purpose prompt forbids recursive `task` calls. `batch_task` is a separate durable mode for large independent item sets with idempotency keys and restart recovery.
- Citation handling is prompt-mandated plus machine-checked. `prompt.py` requires inline `[citation:TITLE](URL)` after every claim sourced from `web_search`/`web_fetch` and a final Sources section using plain markdown links. On top of that, `agents/middlewares/receipt_verification.py` provides `verify_receipt_citations(report_text, receipts)`, which parses citations out of a subagent report and cross-checks them against harvested tool receipts, returning `citation_resolved` and a `no_citation_claims` weak-negative signal. `config.example.yaml` has `verification.receipts_enabled: true` and an optional LLM judge (`judge_enabled: false`).

Text diagram:

```
user msg (wrapped in BEGIN/END USER INPUT, treated as untrusted)
  -> Gateway RunManager -> run_agent() -> StreamBridge (SSE)
     -> middleware chain: sanitize -> threaddata -> uploads -> sandbox
        -> dynamic ctx -> skills -> durable ctx -> summarize
        -> todo(plan mode) -> title -> memory -> viewimage -> ...
        -> clarification (last)
        -> [ create_agent loop ]
             model  <-->  tools
                          |- web_search / web_fetch     (search + read)
                          |- bash / read_file / write_file / str_replace / ls
                          |- describe_skill  (progressive skill load)
                          |- ask_clarification  --> interrupt to user
                          |- task ------> subagent (own create_agent loop,
                          |                no nested task; receipt ledger)
                          |- batch_task -> durable batch runtime
                          `- MCP tools
             loop exits when no tool calls AND todos complete
        -> present_files -> /mnt/user-data/outputs (report, deck, podcast)
```

#### Key components

Model support is config-driven and provider-agnostic: `config.yaml` `models:` entries name a `use:` import path (for example `deerflow.models.patched_deepseek:PatchedChatDeepSeek`) plus `context_window`, `supports_thinking`, `supports_vision`, `supports_reasoning_effort`, and `when_thinking_enabled/disabled` bodies. `reflection/resolvers.py` hints at `langchain-openai`, `langchain-anthropic`, `langchain-google-genai` and `langchain-deepseek` packages. The README recommends Doubao-Seed-2.0-Code, DeepSeek v3.2 and Kimi 2.5 and says any OpenAI-compatible API works.

`config.example.yaml` under `tools:` carries thirteen `web_search_tool` entries: `ddg_search` (the enabled default, uncommented, no key), `searxng`, `serper`, `serply`, `brave`, `tavily`, `infoquest` (BytePlus), `tencent_wsa` (Tencent Cloud WSA), `exa`, `firecrawl`, `groundroute` (a cost router), `fastcrw` and `sofya` (`deerflow.community.sofya.tools:web_search_tool`, `SOFYA_API_KEY`, `max_results` capped at 20, with a `search_depth` basic/snippets option; a `deerflow/community/sofya/` package sits alongside the other providers). Image search is offered separately. Reading is a separate `web_fetch` tool with nine providers, of which the file states only one may be active at a time: Jina AI (the only uncommented, default one, line 1030), Browserless (906), Crawl4AI (930), Exa (1024), InfoQuest (1040), Firecrawl (1051), GroundRoute (1060), fastCRW (1069) and Sofya (1080). Stateful agentic browser control is a separate tool group. Knowledge retrieval adds RAGFlow and LightRAG under a shared `knowledge_search` name.

Memory is pluggable via `memory.manager_class` (default `deermem`, also `mem0`, `noop`, OpenViking) with `mode: middleware` for passive background extraction or an experimental `tool` mode exposing `memory_search/add/update/delete`. Sandboxing is an abstract `SandboxProvider`: `LocalSandboxProvider` for dev, `AioSandboxProvider` for Docker, plus E2B, BoxLite and OpenSandbox community providers and a Kubernetes provisioner. Context engineering includes summarization, `tool_output` externalization above 12,000 chars, deferred tool discovery (`tool_search`, `auto_promote_top_k: 3`) and deferred skill discovery via `describe_skill`.

Surfaces: nginx on 2026 fronting a Next.js 16 frontend and a FastAPI Gateway that also serves a LangGraph-compatible runtime at `/api/langgraph`, so stock LangGraph SDK clients work. There is a Textual TUI (`uv pip install 'deerflow-harness[tui]'`, then `deerflow`, with `--print`, `--json`, `--continue`, `--resume`, `--recursion-limit`), an embedded `DeerFlowClient` Python client, scheduled tasks, and IM channels. The README's IM Channels table lists seven transports: Telegram, Slack, Feishu/Lark, WeChat (Tencent iLink), WeCom, DingTalk and Buzz (a Nostr relay over WebSocket, NIP-42). The adjacent `channel_connections` paragraph, covering user-bound connections, names eight bindable providers by adding Discord. MCP servers are first-class with OAuth, tool namespacing and a durable `McpTaskService` for long-running remote tasks. Extensibility also runs through Markdown skills, `custom_agents` in config, and Python entry-point extensions. Tracing covers LangSmith, Langfuse and Monocle with an `X-Trace-Id` on every response.

#### Getting started

```bash
git clone https://github.com/bytedance/deer-flow.git
cd deer-flow
make setup      # interactive wizard: LLM provider, web search, sandbox/bash policy
make install
make dev        # open http://localhost:2026
```

Docker is the recommended path:

```bash
make docker-init    # pull the sandbox image once
make docker-start   # hot-reload dev stack
make up             # production compose
make doctor         # verify config
make support-bundle # generate an issue report
```

Required keys: none strictly, because the default `web_search` is DuckDuckGo and the default sandbox is local. You need one LLM key (for example `$OPENAI_API_KEY`, `$VOLCENGINE_API_KEY`) written to `.env` by the wizard, and optionally `TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`, `SERPER_API_KEY`, `EXA_API_KEY`, `FIRECRAWL_API_KEY` or a Jina key. Prerequisites are Python 3.12+, Node 22+, pnpm 10.26.2+. Sizing guidance: 4 vCPU / 8 GB for local and Docker dev, 8+ vCPU / 16+ GB for production. A Helm chart ships at `deploy/helm/deer-flow`. Nginx binds to loopback by default and the README carries an explicit security notice about non-loopback deployment.

#### Evaluation and benchmarks

There are no official benchmark numbers. A grep across the repository for GAIA, BrowseComp, HLE, DeepResearch Bench, xbench and SWE-bench returns zero hits in any Markdown, YAML or Python file, and the README publishes no scores. The only public data point is community issue #2820, an RFC on recursion limits, which reports qualitatively that GAIA and SWE-bench runs "scored significantly lower than direct model calls on the same tasks" because agents exhaust the default recursion limit of 150 turns during exploration before implementing a fix, and proposes raising it to 250+. No percentages are given. The sister project LLM Space is pitched as the tool for benchmarking harness performance, but no published results were found.

#### Strengths

The engineering discipline is unusual for a repo this popular. The harness/app boundary (`deerflow.*` never imports `app.*`) is enforced by a CI test, the compose default-bind-host rule is pinned by a test, and version drift across `pyproject.toml`, `package.json` and the Helm chart blocks publishing. Failure modes that usually go unhandled are handled explicitly: loop detection, token budgets, empty-AIMessage retries, length-capped completions, provider safety terminations, dangling tool calls, read-before-write. Provider breadth is genuine, with thirteen search backends and nine page readers behind two stable tool names. Citation verification against a tool-receipt ledger is a real mechanism, not a prompt promise. The surface count is high: web UI, LangGraph-SDK-compatible API, TUI, Python client, seven IM transports (eight bindable providers once Discord's user-bound connections are counted), scheduled tasks. Prompt-injection posture is deliberate, with untrusted-input markers and a system-context confidentiality rule.

#### Weaknesses and limitations

The deep research capability is thinner than the description suggests. It is a single prompt file, so query generation, breadth, depth and gap analysis are entirely model judgment against a checklist, with no programmatic iteration budget, no per-section researcher fan-out, and no reflection loop you can tune. Delegation is actively discouraged by the prompt and hard-capped, which means "supervisor plus parallel researchers" is not what you get by default. The project inherits LangChain and LangGraph wholesale, including their abstractions and breaking changes. The 2.1.0 Unreleased changelog is dominated by breaking config and API changes, so upgrades are not free. The operational footprint is large for a research tool: four services, sandboxes, a database, nginx. No benchmark evidence exists, and the one community measurement is negative. The launch prominently features BytePlus InfoQuest, ByteDance's own commercial search and crawl service, and InfoQuest churn shows up in the most recent commit. Only one release has ever been cut, against an open queue of 528 issues and 391 pull requests.

#### Best fit

Use DeerFlow if you want a self-hosted, long-horizon agent platform where research is one job among many, you need sandboxed code execution and file artifacts (reports, decks, podcasts) delivered to real users through a web UI or Slack/Feishu, and you are comfortable operating a four-service stack and tracking a fast-moving 2.x line. Its skills catalogue (`deep-research`, `github-deep-research`, `systematic-literature-review`, `consulting-analysis`, `ppt-generation`, `podcast-generation`) makes it strong for teams delivering polished multi-format deliverables.

Do not use it if you want a tunable research pipeline. Against LangChain's own `open_deep_research`, DeerFlow trades an explicit, inspectable research graph for a general harness where research is prompt-shaped; against a lightweight tool like GPT Researcher it trades install simplicity for sandboxes, memory, MCP and multi-channel delivery. Specific capability claims about those two alternatives are unverified here. If your requirement is auditable, parameterized depth-and-breadth control over a citation pipeline, DeerFlow 2.0 is the wrong shape and the `main-1.x` branch, or a purpose-built research graph, fits better.

#### Sources

- https://github.com/bytedance/deer-flow
- https://api.github.com/repos/bytedance/deer-flow
- https://github.com/bytedance/deer-flow/issues
- https://raw.githubusercontent.com/bytedance/deer-flow/main/README.md
- https://github.com/bytedance/deer-flow/blob/main/docs/ARCHITECTURE.md
- https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/agents/lead_agent/agent.py
- https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/agents/lead_agent/prompt.py
- https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/tools/builtins/task_tool.py
- https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/tools/builtins/clarification_tool.py
- https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/agents/middlewares/receipt_verification.py
- https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/agents/middlewares/todo_middleware.py
- https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/subagents/builtins/general_purpose.py
- https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/reflection/resolvers.py
- https://github.com/bytedance/deer-flow/blob/main/skills/public/deep-research/SKILL.md
- https://github.com/bytedance/deer-flow/blob/main/config.example.yaml
- https://github.com/bytedance/deer-flow/blob/main/CHANGELOG.md
- https://github.com/bytedance/deer-flow/blob/main/Install.md
- https://github.com/bytedance/deer-flow/releases
- https://github.com/bytedance/deer-flow/issues/2820
- https://deerflow.tech
- https://dev.to/arshtechpro/deerflow-20-what-it-is-how-it-works-and-why-developers-should-pay-attention-3ip3
- https://www.cstack.ai/blog/deerflow-is-cool-but-do-you-know-your-stack
- https://kiledjian.com/2026/03/06/deerflow-bytedances-opensource-ai-agent.html


### 2. Khoj

Repository: https://github.com/khoj-ai/khoj
License: AGPL-3.0 | Stars: 37,230 (2026-09-09) | Language: Python | Pattern: Single-agent tool-calling loop with per-iteration parallel tool fan-out
Fact-check: minor-issues, 4 corrections applied

#### Overview

Khoj is a self-hostable "AI second brain": a Django plus FastAPI server that indexes your personal documents, searches the web, and answers questions with citations. Deep research is not a separate product but a mode inside the chat pipeline, triggered by the `/research` slash command or auto-selected by the router.

It is maintained by Khoj Inc. under the `khoj-ai` GitHub organization. The prompt file states "You were created by Khoj Inc." (`src/khoj/processor/conversation/prompts.py`). GitHub reports 73 contributors.

Metadata from the GitHub API on 2026-09-09: 37,230 stars, 2,464 forks, 148 open issues, license AGPL-3.0, primary language Python, repository created 2021-08-16. The oldest of 173 tagged releases is `v0.1.5-alpha` (2022-08-15); the newest is `2.0.0-beta.28` (2026-03-26). The most recent commit on `master` is dated 2026-08-02, so the tree is roughly five weeks stale as of today. Maturity is high for the surrounding product (multi-year history, packaged on PyPI and GHCR, desktop/Obsidian/Emacs/Android clients, an enterprise offering) but the research mode itself has been described by the maintainers as beta since its November 2024 launch, and the operator sub-module carries an explicit "experimental" label.

#### Workflow architecture

The orchestration pattern is a **single-agent tool-calling loop with parallel tool fan-out per iteration**. There is no supervisor, no researcher sub-agents, no LangGraph-style graph, and no RL-trained policy. State is a plain Python list of `ResearchIteration` objects.

The loop lives in `research()` in `src/khoj/routers/research.py`. Per iteration:

1. **Planning.** `apick_next_tool()` builds a system prompt from `prompts.plan_function_execution` and a dynamically filtered tool list (`tools_for_research_llm` in `src/khoj/utils/helpers.py`), then calls the model with native tool schemas via `send_message_to_model_wrapper(..., deepthought=True)`. Planning is interleaved rather than up front: the prompt says "Create a multi-step plan and intelligently iterate on the plan", and the model re-plans on every turn with the full iteration history in context. There is no separate outline or report skeleton step.
2. **Clarification.** Deliberately absent. The prompt instructs: "Do not ask the user to confirm or clarify assumptions for information gathering tasks and non-destructive actions ... decide what the most reasonable assumption is, proceed with it, and document it."
3. **Tool availability gating.** Document tools are hidden if the user has no indexed entries; web tools are hidden unless web search is enabled; the code tool requires a sandbox; the operator tool requires `is_operator_enabled()`. Agent-scoped tool allowlists are mapped through `input_tools_to_research_tools`.
4. **Query generation and search.** The `search_web` tool calls `search_online()` in `src/khoj/processor/tools/online_search.py`, which expands the request into up to `max_online_searches` (hardcoded 3) subqueries with `generate_online_subqueries()`, subtracts any subquery already run in earlier iterations, then fires all subqueries concurrently with `asyncio.gather`. In research mode this returns search-engine snippets only: `execute_tool()` calls `search_online(..., max_webpages_to_read=0)`, and the auto-read block inside `search_online` is separately gated behind `AUTO_READ_WEBPAGE = is_env_var_true("KHOJ_AUTO_READ_WEBPAGE")`, which returns early when unset. Under any default configuration, `search_web` reads no pages at all.
5. **Page reading and extraction.** Page reading in research mode happens exclusively through the separate `read_webpage` tool, whose URL list the model chooses. `read_webpages_content()` fetches those URLs, `scrape_webpage_with_fallback()` walks the enabled scrapers in priority order until one returns content, and `extract_from_webpage()` passes the raw page to `extract_relevant_info()` so only query-relevant excerpts enter context.
6. **Reflection and gap analysis.** Implicit, not a dedicated node. Each iteration is compressed into a `summarizedResult` string wrapped in `<iteration_N_results>` tags containing `<document_references>`, `<online_results>`, `<code_results>`, `<browser_operator_results>`, `<mcp_tool_results>` and `<warning>` sections, appended to history by `construct_iteration_history()`. The next planning call reads that and decides what is still missing. Two cheap anti-loop guards exist: a repeated `(tool, args)` combination injects the warning "Repeated tool, query combination detected ... Try something different", and duplicate subqueries or document queries are filtered out before execution.
7. **Depth and breadth control.** Breadth is the number of tool calls the model emits in one turn, executed in parallel via `asyncio.gather(*[execute_tool(...)])`. Streaming tools (currently `operate_computer`) are split out and run sequentially. Depth is a hard iteration cap: `MAX_ITERATIONS = int(os.getenv("KHOJ_RESEARCH_ITERATIONS", 5))`. Note that `current_iteration` increments once per tool result, so a wide turn consumes several of the five iterations. Other budgets are constants in `research()`, and they are not equally binding: `max_document_searches = 7` is enforced (passed as `n=` to `search_documents`) and `max_online_searches = 3` is enforced (passed as `max_queries=` to `generate_online_subqueries`), while `max_webpages_to_read = 1` is never enforced in code — it is only interpolated into the `read_webpage` tool's description string shown to the planner, so it is soft prompt guidance rather than a limit.
8. **Termination.** The loop exits when the cap is hit, when the model replies with plain text instead of a tool call (parsed as `ConversationCommand.Text`, setting `should_terminate`), or on cancellation.
9. **Synthesis and citations.** Synthesis happens outside the loop. `api_chat.py` collects `online_results`, `code_results` and `compiled_references`, then calls `agenerate_chat_response()` to write the answer. Citation style is prompt-enforced, not programmatic: `prompts.personality` requires "inline citations to documents and websites referenced ... in markdown format", with the example `"The weather today is sunny [1](https://weather.com)."` References are also returned to the client as a structured payload.

```
/research query
   |
   v
research()                              src/khoj/routers/research.py
 while iter < MAX_ITERATIONS (5)
   |
   |-- interrupt_queue? --> splice new user instruction, clear `previous_iterations`
   |                        (iteration counter and MAX_ITERATIONS budget are NOT reset)
   |
   |-- apick_next_tool()  [plan_function_execution + tool schemas + full history]
   |         -> 1..N ToolCalls (+ repeat-detector warnings)
   |
   |-- fan-out
   |     operate_computer ....... sequential, streams status
   |     everything else ........ asyncio.gather(execute_tool, ...)
   |        search_web ....... subqueries -> Serper|Exa|Firecrawl|Google|SearXNG
   |                           (snippets only; max_webpages_to_read=0)
   |        read_webpage ..... scraper fallback -> extract_relevant_info
   |        semantic_search_files | regex_search_files | view_file | list_files
   |        run_code ........ E2B or Terrarium sandbox
   |        <mcp_server>/<tool>
   |
   |-- summarizedResult = <iteration_N_results> ... </iteration_N_results>
   |         appended to previous_iterations  (the entire state)
   v
agenerate_chat_response()               src/khoj/routers/api_chat.py
   final answer + inline markdown citations + references payload
```

#### Key components

**LLM providers.** `ChatModel.ModelType` in `src/khoj/database/models/__init__.py` offers exactly three: `openai`, `anthropic`, `google`. Local and third-party models are reached through the OpenAI-compatible path, since `AiModelApi` carries an `api_base_url`; docs cover Ollama, LM Studio, LiteLLM, GCP Vertex and generic OpenAI proxies.

**Search providers.** Serper.dev, Exa, Firecrawl, Google Programmable Search, and self-hosted SearXNG. They are appended in that fixed order and tried until one returns a non-empty result set.

**Scraping stack.** `WebScraper.WebScraperType` supports Firecrawl, Olostep, Exa and Direct (plain aiohttp fetch), configured per-instance in the Django admin with a priority field.

**Retrieval.** pgvector over documents indexed from PDF, Markdown, org-mode, Word, Notion and images, with a bi-encoder default of `thenlper/gte-small` and cross-encoder reranker `mixedbread-ai/mxbai-rerank-xsmall-v1`.

**Memory and state.** `UserMemory` is a pgvector-backed long-term memory derived from conversations, injected as `relevant_memories`. Research state is persisted per message (`researchContext`), so an interrupted run can resume from `previous_iterations`.

**Structured output.** Native provider tool calling with JSON schemas per tool, plus a tolerant `load_complex_json` parser and a fallback that treats unparseable output as the final answer.

**Human in the loop.** Real: an `interrupt_queue` lets the user inject a new instruction mid-run (status message "Incorporate New Instruction"), and a `cancellation_event` aborts. Note that an interrupt folds the prior history into `research_conversation_history` and clears `previous_iterations`, but leaves `current_iteration` untouched, so redirection does not buy a fresh depth budget. Clarifying questions are suppressed by design.

**Computer use.** `src/khoj/processor/operator/` gives the agent a containerized browser or desktop; its README says only Anthropic models are currently enabled.

**Surfaces.** Web UI on port 42110, Django admin, REST routers (`api_chat.py`, `api_agents.py`, `api_content.py`, `api_memories.py`, `api_automation.py`), a `khoj` CLI, and clients for Desktop, Obsidian, Emacs, Android and WhatsApp. There is no OpenAI-compatible `/chat/completions` endpoint in `api_chat.py`.

**Extensibility.** Full MCP client support (`src/khoj/processor/tools/mcp.py`) over stdio and SSE. Servers are registered in the `McpServer` table and their tools appear to the planner namespaced as `server/tool`. This is not covered in the documentation directory.

#### Getting started

Docker is the recommended path:

```shell
mkdir ~/.khoj && cd ~/.khoj
wget https://raw.githubusercontent.com/khoj-ai/khoj/master/docker-compose.yml
# edit KHOJ_ADMIN_PASSWORD, KHOJ_DJANGO_SECRET_KEY and one model key
docker-compose up
```

Pip install with a local model stack:

```shell
python -m pip install 'khoj[local]'
USE_EMBEDDED_DB="true" khoj --anonymous-mode
```

Then open `http://localhost:42110`. Required keys: at least one of `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or `OPENAI_BASE_URL` pointing at Ollama/vLLM/LM Studio. Optional research keys: `SERPER_DEV_API_KEY`, `EXA_API_KEY`, `FIRECRAWL_API_KEY`, `GOOGLE_SEARCH_API_KEY` plus `GOOGLE_SEARCH_ENGINE_ID`, or `KHOJ_SEARXNG_URL`; the bundled compose file wires up SearXNG so web search works with no paid key. Raise depth with `KHOJ_RESEARCH_ITERATIONS`; `KHOJ_AUTO_READ_WEBPAGE` re-enables the auto-read path inside `search_online`, which is off by default. Chat models, web scrapers and MCP servers are configured through the admin panel. Deployment options: docker-compose, pip on a host, the hosted app at app.khoj.dev, or Khoj Enterprise on-prem.

#### Evaluation and benchmarks

The only published numbers are the maintainers' own, in "Evaluating Khoj for Helpfulness" (2024-11-22), judged by `gemini-1.5-pro-002` over 200 sampled questions.

Google FRAMES, backing model `gemini-1.5-flash-002`: general mode 27.1%, default mode 42.0%, research mode 63.5%. Reference points given in the post: `gemini-1.5-flash-001` baseline 26.3%, `gemini-1.5-pro` 66%, and a 66.5% ceiling with perfect retrieval. Enabling the code interpreter moved default mode from 35.68% to 42.0%.

OpenAI SimpleQA, same backing model: general 10.0%, default 84.0%, research 86.0%, against an `o1-preview` baseline of 43.5% and human performance of 94.4%.

The harness is committed at `tests/evals/eval.py` and pulls `google/frames-benchmark` plus `parasail-ai/frames-benchmark-wikipedia` from Hugging Face, so the FRAMES run is reproducible. No GAIA, BrowseComp, HLE, DeepResearch Bench or xbench-DeepSearch results exist for Khoj, and I found no independent third-party benchmark of its research mode.

#### Strengths

Personal documents and the open web are first-class peers in the same loop, which almost no other deep research tool does: the planner can grep your notes, view a line range, then go verify a claim online. Provider optionality is unusually broad at both the model layer and the search and scrape layers, with automatic fallback chains so a Serper outage degrades to SearXNG rather than failing. Mid-run steering through the interrupt queue is a genuinely useful affordance that most plan-and-execute systems lack. It is a real product with real clients rather than a research demo, and it publishes a reproducible eval harness.

#### Weaknesses and limitations

The research loop is shallow by the standards of 2026 deep research systems: five iterations, and at most three subqueries per web search. Search itself is snippet-only in research mode — `search_web` passes `max_webpages_to_read=0`, and the auto-read path inside `search_online` stays off unless `KHOJ_AUTO_READ_WEBPAGE` is set — so full page text enters the loop only when the model separately calls `read_webpage`. How many URLs that reads is the model's choice; the `max_webpages_to_read = 1` constant appears only inside the tool's description text shown to the planner and is not enforced anywhere. Of the budgets in `research()`, the document-search cap of 7 and the online-subquery cap of 3 are real hardcoded limits rather than user settings, and only the iteration cap is exposed as an environment variable. Because the iteration counter advances per tool result, a wide parallel turn burns the budget fast, and interrupting mid-run does not reset that counter. There is no report outline, no section-wise writing, no length target, and no verification pass, so output is a chat answer rather than a structured multi-page report. Citations rest entirely on prompt instructions with no programmatic check that a cited URL was actually read. Reflection has no dedicated prompt; gap analysis is whatever the planner infers from tagged history, and the anti-loop mechanism is exact-match deduplication that a slightly reworded query defeats. Published scores are self-reported, a year and a half old, and use a now-superseded model. Self-hosting drags in Postgres with pgvector, Django and an admin panel, which is heavy if you only want research. AGPL-3.0 will deter some commercial embedders. Master has not moved since early August 2026, and the team's attention appears partly redirected to a separate project, Pipali (unverified).

#### Best fit

Khoj suits an individual or small team that already keeps a large personal corpus, wants one self-hosted assistant over notes plus the web, and values privacy and provider choice over report depth. It is a poor fit if you need long analyst-grade reports with verified citations.

Against **open-deep-research** style projects, Khoj trades research depth and report structure for a persistent document index, a real UI and multi-client access. Against **Perplexity** or **ChatGPT deep research**, it trades raw quality and depth for self-hosting, AGPL source, personal-document grounding and the ability to point it at a local model. If deep research is the whole job, a purpose-built agent with configurable breadth and depth will produce better reports; if deep research over your own knowledge base is the job, Khoj's design is the differentiator.

#### Sources

- https://github.com/khoj-ai/khoj
- https://raw.githubusercontent.com/khoj-ai/khoj/master/README.md
- https://api.github.com/repos/khoj-ai/khoj
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/routers/research.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/routers/api_chat.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/processor/tools/online_search.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/processor/tools/mcp.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/utils/helpers.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/processor/conversation/prompts.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/processor/conversation/utils.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/database/models/__init__.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/processor/operator/README.md
- https://raw.githubusercontent.com/khoj-ai/khoj/master/tests/evals/eval.py
- https://raw.githubusercontent.com/khoj-ai/khoj/master/documentation/docs/get-started/setup.mdx
- https://raw.githubusercontent.com/khoj-ai/khoj/master/documentation/docs/features/online_search.md
- https://raw.githubusercontent.com/khoj-ai/khoj/master/documentation/docs/features/chat.md
- https://blog.khoj.dev/posts/evaluate-khoj-quality/
- https://docs.khoj.dev


### 3. STORM / Co-STORM

Repository: https://github.com/stanford-oval/storm
License: MIT | Stars: 31,257 (as of 2026-09-09) | Language: Python | Pattern: Fixed-stage plan-and-execute pipeline with parallel persona-conditioned dialogue simulation; Co-STORM adds a turn-policy multi-agent discourse state machine over a shared mind map
Fact-check: minor-issues, 4 corrections applied

#### Overview

STORM is a knowledge curation system from the Stanford Open Virtual Assistant Lab (OVAL) that writes Wikipedia-style, citation-bearing articles from web search. It ships as the `knowledge-storm` Python package (`setup.py` declares version 1.1.1, authors Yijia Shao and Yucheng Jiang, `license="MIT License"`, classifier `Development Status :: 3 - Alpha`, `python_requires=">=3.10"`). The `LICENSE` file is MIT, copyright 2024 Stanford Open Virtual Assistant Lab. Primary language is Python. The repo showed 31,257 stars and 2.9k forks on 2026-09-09. First commit is 2024-04-08; first tag `v0.1.0` is dated 2024-04-22, `v1.0.0` (Co-STORM) 2024-09-25, `v1.1.0` (litellm) 2025-01-22, across 27 distinct git authors.

Two peer-reviewed papers back it: STORM at NAACL 2024 (arXiv 2402.14207) and Co-STORM at EMNLP 2024 main (arXiv 2408.15232). The README says the hosted preview at storm.genie.stanford.edu has been tried by over 70,000 people. Maturity is that of a well-cited academic reference implementation no longer actively developed: the newest commit on `main` is 2025-09-30, roughly eleven months back, the tracker shows 59 open issues, there is no test suite, and `requirements.txt` pins `dspy_ai==2.4.9`.

#### Workflow architecture

STORM is not a ReAct agent and does not use tool calling. It is a **fixed-stage plan-and-execute pipeline whose research stage is parallel persona-conditioned dialogue simulation**, built on DSPy `Signature`/`Module` primitives. Co-STORM layers on a **turn-based multi-agent discourse state machine with a shared mind map**.

The STORM control flow is `STORMWikiRunner.run()` in `knowledge_storm/storm_wiki/engine.py`, which calls four modules in strict order, each gated by a flag (`do_research`, `do_generate_outline`, `do_generate_article`, `do_polish_article`) and each able to load its predecessor's output from disk instead of recomputing it.

1. **Clarification.** None. STORM takes a bare topic string and starts. Co-STORM substitutes `CoStormRunner.warm_start()`, called "a mini-STORM" in its own docstring, which builds a shared conceptual space up front.
2. **Perspective discovery (planning).** `StormPersonaGenerator` in `modules/persona_generator.py` prompts for related Wikipedia URLs (`FindRelatedTopic`), fetches each page's title and table of contents via `get_wiki_page_title_and_toc(url)`, then derives writer personas with `GenPersona`. Breadth control here is personas, not a task list.
3. **Query generation, search, answering.** `TopicExpert.forward()` in `modules/knowledge_curation.py` is the loop body: `QuestionToQuery` splits a question into at most `max_search_queries` queries, `Retriever.retrieve()` searches, and `AnswerQuestion` writes an answer with inline `[n]` citations over retrieved snippets truncated to 1000 words. On empty retrieval it returns a fixed refusal string rather than hallucinating.
4. **Depth loop.** `ConvSimulator.forward()` alternates `WikiWriter` (next persona-conditioned question, seeing only the last 4 turns in full) and `TopicExpert` for `max_turn` iterations. It stops on the turn budget or the writer emitting the literal string "Thank you so much for your help!". STORM has no reflection or gap-analysis module.
5. **Breadth parallelism.** `StormKnowledgeCurationModule._run_conversation()` runs one conversation per persona in a `ThreadPoolExecutor` bounded by `max_thread_num`, packing results into a `StormInformationTable`.
6. **Outline.** `StormOutlineGenerationModule.generate_outline()` drafts from parametric knowledge (`NaiveOutlineGen`), then revises against the transcripts (`WritePageOutlineFromConv`).
7. **Section writing.** `StormArticleGenerationModule.generate_article()` writes first-level sections in parallel threads, skipping any titled introduction, conclusion or summary. Retrieval here is embedding based, not web: `StormInformationTable.retrieve_information()` encodes the section query and takes top-k already-collected snippets by cosine similarity.
8. **Polish and citations.** `StormArticlePolishingModule` adds a lead section (`WriteLeadSection`) and optionally deduplicates (`PolishPage`). Then `StormArticle.post_processing()` calls `prune_empty_nodes()` and `reorder_reference_index()`, which pre-order traverses the section tree, collects indices via `parse_citation_indices`, and renumbers with `update_citation_index` so the bibliography matches reading order.

Co-STORM replaces the fixed pipeline with a policy function. `DiscourseManager.get_next_turn_policy()` in `knowledge_storm/collaborative_storm/engine.py` returns a `TurnPolicySpec` naming the next speaker plus three flags (`should_reorganize_knowledge_base`, `should_update_experts_list`, `should_polish_utterance`). Branch order: simulated user, RAG-only baseline, a one-shot `next_turn_moderator_override`, then the moderator if `_should_generate_question()` finds `moderator_override_N_consecutive_answering_turn` consecutive non-questioning turns, otherwise an expert popped and rotated off `self.experts`. That moderator trigger is Co-STORM's real gap-analysis mechanism. `CoStormRunner.step()` executes one turn and inserts it into the mind map (`KnowledgeNode` and `KnowledgeBase` in `knowledge_storm/dataclass.py`, with `reorganize()`, `insert_node()`, `merge_single_child_nodes()`). `generate_report()` is `knowledge_base.to_report()`: mind map nodes become section headings, written paragraph by paragraph in `collaborative_storm/modules/article_generation.py`.

```
STORM:
topic
  -> persona_generator (related wiki TOCs -> N personas)
  -> [persona 1] WikiWriter <-> TopicExpert (queries -> retriever -> cited answer)  x max_conv_turn
     [persona 2] ...  (parallel threads)
     [persona N] ...
  -> StormInformationTable (snippets + urls, embedded)
  -> NaiveOutlineGen -> WritePageOutlineFromConv
  -> per-section: embedding retrieval -> WriteSection (parallel)
  -> WriteLeadSection + PolishPage -> reorder_reference_index -> article

Co-STORM:
topic -> warm_start (mini-STORM) -> mind map
  loop: get_next_turn_policy -> {moderator | expert_i | user utterance | pure_rag}
        -> generate_utterance -> insert into mind map -> maybe reorganize
  -> knowledge_base.to_report()
```

#### Key components

LLM access goes through litellm (`LitellmModel` in `knowledge_storm/lm.py`), so any litellm-supported provider works; `examples/storm_examples/` has scripts for OpenAI, Claude, Gemini, Mistral, Groq, DeepSeek and Ollama. STORM splits models by role (`set_conv_simulator_lm`, `set_question_asker_lm`, `set_outline_gen_lm`, `set_article_gen_lm`, `set_article_polish_lm`); Co-STORM has six roles including `discourse_manage_lm` and `knowledge_base_lm`.

`knowledge_storm/rm.py` defines eleven retrievers: `YouRM`, `BingSearch`, `VectorRM`, `StanfordOvalArxivRM`, `SerperRM`, `BraveRM`, `SearXNG`, `DuckDuckGoSearchRM`, `TavilySearchRM`, `GoogleSearch`, `AzureAISearch`. Reading is light: search-API snippets plus `trafilatura`'s `extract` in `knowledge_storm/utils.py`, not a browser. `VectorRM` grounds on user documents via `qdrant-client` and `langchain-qdrant`. Embeddings run through `Encoder` in `encoder.py` over litellm, with `openai`, `azure` and `together` types and disk caching.

State is file based for STORM (`conversation_log.json`, `storm_gen_outline.txt`, `url_to_info.json`) and object based for Co-STORM (`CoStormRunner.to_dict()`/`from_dict()` serialize the mind map and expert list). Structured output is DSPy signatures, not JSON-schema function calling. Human-in-the-loop is Co-STORM only, via `step(user_utterance=...)`. The only UI is the Streamlit app `frontend/demo_light/storm.py`; there is no REST API server and no MCP support anywhere in the tree.

#### Getting started

```bash
pip install knowledge-storm
```

From source:

```bash
git clone https://github.com/stanford-oval/storm.git
cd storm
conda create -n storm python=3.11
conda activate storm
pip install -r requirements.txt
```

Create `secrets.toml` in the repo root for the example scripts:

```toml
OPENAI_API_KEY="your_openai_api_key"
OPENAI_API_TYPE="openai"
BING_SEARCH_API_KEY="your_bing_search_api_key"
ENCODER_API_TYPE="openai"
```

Run STORM, then Co-STORM:

```bash
python examples/storm_examples/run_storm_wiki_gpt.py \
    --output-dir $OUTPUT_DIR --retriever bing \
    --do-research --do-generate-outline \
    --do-generate-article --do-polish-article

python examples/costorm_examples/run_costorm_gpt.py \
    --output-dir $OUTPUT_DIR --retriever bing
```

For the UI, follow the sequence in `frontend/demo_light/README.md`: work from inside that directory and give the demo its own copy of the secrets file under `.streamlit/`. Streamlit resolves `.streamlit/secrets.toml` relative to the working directory, so launching from the repo root against the repo-root `secrets.toml` leaves the demo with no API keys and puts `DEMO_WORKING_DIR` in the wrong place.

```bash
cd frontend/demo_light
pip install -r requirements.txt
mkdir -p .streamlit
cp ../../secrets.toml .streamlit/secrets.toml
streamlit run storm.py
```

Deployment options are the library, the CLI example scripts and the Streamlit demo; no Dockerfile or hosted-API path is in the repo.

#### Evaluation and benchmarks

There are no GAIA, BrowseComp, HLE, xbench-DeepSearch or DeepResearch Bench numbers for STORM or Co-STORM. The projects predate that benchmark wave and use their own datasets: FreshWiki (100 most-edited Wikipedia articles from February 2022 to September 2023) and WildSeek.

Self-reported: the STORM paper claims articles are 25 percent absolute more likely to be judged organized and 10 percent broader in coverage than the best baseline. The Co-STORM paper reports 70 percent of participants preferred it to a search engine and 78 percent to a RAG chatbot; the abstract gives no participant count.

The one independent benchmark I found is DeepScholar-Bench (arXiv 2508.20033). Its Table 2 row is labeled **STORM (Llama-4)**: organization .119, nugget coverage .183, relevance rate .218, reference coverage .003, document importance .006, citation precision .238 and claim coverage .586. The benchmark evaluated only that Llama-4 backend, not the GPT-4o configuration the repo ships as its default, so the figures are not directly comparable to a stock STORM run — backend choice moves scores enormously within the same table, with DeepScholar-base going from .254 organization on Llama-4 to .825 on GPT-4.1. Taking the published row at face value, STORM (Llama-4) is last among the open-source systems on four of the seven metrics: organization (.119 versus .206 and .309), nugget coverage, reference coverage and document importance. Its .119 organization score is also the lowest of any system in the table, human exemplars included. Claim coverage (.586, the highest of the three open-source systems) is its one comparative strength. Absolute numbers are low across the board: both the abstract and the introduction state that no system exceeded a score of 19 percent across all metrics. The paper reports the seven metrics separately and gives no composite aggregate score.

#### Strengths

Perspective-guided question asking is load-bearing and has been widely copied; GPT Researcher cites the STORM paper as an influence. Peer review at two ACL venues plus released datasets make it one of the few such systems with a real paper trail. The modular design is honest: every stage has an abstract interface in `knowledge_storm/interface.py`, so swapping a retriever or section writer is a subclass, not a fork. Per-role model configuration lets you spend a cheap model on the thousands of conversation-simulation calls and a strong one only on article generation. Retriever coverage is broad, `VectorRM` supports private corpora, disk checkpoints make partial reruns cheap, and citation renumbering happens in code rather than in a prompt.

#### Weaknesses and limitations

Development has stopped; the last commit is 2025-09-30 and `dspy_ai` is pinned to 2.4.9. The README itself admits the system "cannot produce publication-ready articles." Retrieval is shallow by default (`search_top_k=3`, `max_conv_turn=3`, `max_perspective=3`) and leans on search-API snippets, with `TopicExpert` using only `r.snippets[:1]` per result; the near-zero reference coverage of the DeepScholar-Bench Llama-4 run is the visible consequence, though whether the default GPT-4o setup does better on that metric is unverified. There is no verification pass, no adaptive stopping beyond a turn budget and a magic phrase, and no re-search during section writing, so a gap found at writing time cannot be filled. Output is locked to the Wikipedia article shape. There is no MCP, no tool-calling extensibility, no API server and no test suite.

#### Best fit

Best for researchers wanting a citable baseline for multi-agent research writing, teams needing broad Wikipedia-style surveys or pre-writing outlines, and anyone grounding a report on a private corpus via `VectorRM`. Poor fit for maintained production pipelines, precise multi-hop factual questions, or browser-driven agentic tasks. Against GPT Researcher, STORM has the stronger research pedigree and better outline structure but far weaker maintenance and no MCP or tool ecosystem. Against LangGraph's open_deep_research, STORM is simpler to reason about and cheaper to configure per role, but lacks supervisor plus parallel sub-agent scaling, tool extensibility and an active release cadence.

#### Sources

- https://github.com/stanford-oval/storm
- https://raw.githubusercontent.com/stanford-oval/storm/main/README.md
- https://github.com/stanford-oval/storm/blob/main/setup.py
- https://github.com/stanford-oval/storm/blob/main/LICENSE
- https://github.com/stanford-oval/storm/blob/main/requirements.txt
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/engine.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/knowledge_curation.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/article_generation.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/storm_dataclass.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/persona_generator.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/collaborative_storm/engine.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/dataclass.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/rm.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/encoder.py
- https://github.com/stanford-oval/storm/blob/main/knowledge_storm/interface.py
- https://github.com/stanford-oval/storm/blob/main/frontend/demo_light/README.md
- https://github.com/stanford-oval/storm/commits/main.atom
- https://github.com/stanford-oval/storm/issues
- https://arxiv.org/abs/2402.14207
- https://www.arxiv.org/abs/2408.15232
- https://arxiv.org/html/2508.20033v1
- https://huggingface.co/datasets/EchoShao8899/FreshWiki
- https://huggingface.co/datasets/YuchengJiang/WildSeek
- https://storm.genie.stanford.edu/
- https://www.digitalapplied.com/blog/open-source-deep-research-agents-2026-guide


### 4. GPT Researcher

Repository: https://github.com/assafelovic/gpt-researcher
License: Apache-2.0 | Stars: 29,378 (GitHub API, 2026-09-09) | Language: Python | Pattern: Plan-and-execute with parallel asyncio sub-agents, plus a recursive tree-search deep mode and an optional LangGraph supervisor state machine
Fact-check: major-issues, 8 corrections applied

#### Overview

GPT Researcher is an autonomous research agent that turns a single query into a long, cited report drawn from web search, local documents, or MCP-connected data sources. It is maintained by Assaf Elovic (also the author of the project's architecture blog post, and associated with Tavily, the default search backend) in the repository `assafelovic/gpt-researcher`, with a large contributor base and a Discord community. The license is Apache-2.0, confirmed three ways: the repo's `LICENSE` file, the GitHub API license field (`license.spdx_id` = `Apache-2.0`), and the README's own disclaimer line ("We are sharing codes for academic purposes under the Apache 2 license"). Downstream metadata disagrees with all three: gptr.dev's FAQ structured data states "GPT Researcher is MIT-licensed and free to use", and the PyPI package metadata for `gpt-researcher` 0.16.0 reports `license: MIT`. The `LICENSE` file governs. Primary language is Python (GitHub API `language`). Stars: 29,378 as of 2026-09-09 per the GitHub API; the repo page rounds this to 29.4k with 3,989 forks.

The repository was created 2023-05-12, which makes it one of the earliest open deep-research agents, predating vendor deep-research modes. The launch blog post "How we built GPT Researcher" is dated 2023-09-22. Most recent activity: last push 2026-08-27, repo metadata updated 2026-09-09, latest release v3.6.1 published Aug 24. This is a mature, actively released project: a versioned PyPI package (`gpt-researcher`), Docker images, Terraform, a `tests/` suite, an `evals/` suite, and 37 open issues plus 46 open pull requests at time of writing (the GitHub API's `open_issues_count` of 83 is the sum of the two, since it counts PRs as issues).

#### Workflow architecture

The core library uses a plan-and-execute pattern, not a ReAct loop. `gpt_researcher/agent.py` defines the `GPTResearcher` façade, which composes seven "skills": `ResearchConductor` (`skills/researcher.py`), `ReportGenerator` (`skills/writer.py`), `ContextManager` (`skills/context_manager.py`), `BrowserManager` (`skills/browser.py`), `SourceCurator` (`skills/curator.py`), `DeepResearchSkill` (`skills/deep_research.py`), and `ImageGenerator`.

There is no clarification turn in the standard flow. `GPTResearcher.conduct_research()` branches immediately: if `report_type == ReportType.DeepResearch` it delegates to `_handle_deep_research`, otherwise it calls `choose_agent()` (`actions/agent_creator.py`) to synthesize a task-specific agent persona and role prompt, then hands off to `ResearchConductor.conduct_research()`.

Planning happens in `ResearchConductor.plan_research()`. It first runs one scoping search through `retrievers[0]`, then passes those results to `plan_research_outline()` in `actions/query_processing.py`, which calls `generate_sub_queries()`. That function prompts the *strategic* LLM (default `openai:gpt-5.4`, `REASONING_EFFORT` medium) with `generate_search_queries_prompt` and parses the result with `json_repair`, capped at `MAX_ITERATIONS` (default 3). The original query is appended to the sub-query list unless this is a `subtopic_report`.

Execution is flat parallelism, not a supervisor loop. `_get_context_by_web_search()` runs `asyncio.gather` over `_process_sub_query()` for every sub-query. Each sub-query independently searches its retrievers (`_search`), filters already-seen URLs (`_get_new_urls`, `visited_urls`), scrapes via `scraper_manager.browse_urls()` (`_extract_content`), and compresses (`_summarize_content`). Compression is embedding-based rather than LLM-summarization-only: `ContextManager.get_similar_content_by_query()` builds a `ContextCompressor` over the scraped pages using `memory.get_embeddings()` and returns the top `max_results=10` chunks. The per-sub-query strings are then joined into one context blob.

There is no explicit reflection or gap-analysis stage in the standard path: the plan is generated once and executed. Reflection exists only in deep-research mode. `DeepResearchSkill` implements a recursive tree search with configurable breadth and depth (`DEEP_RESEARCH_BREADTH` 3, `DEEP_RESEARCH_DEPTH` 2, `DEEP_RESEARCH_CONCURRENCY` 4). `generate_search_queries()` produces `breadth` queries each with a `researchGoal`; `process_query()` spawns a *nested* `GPTResearcher` per query under an `asyncio.Semaphore`, sharing `visited_urls` and MCP config. `process_research_results()` then asks the strategic LLM at high reasoning effort (`ReasoningEfforts.High.value`, temperature 0.4, `max_tokens` 4000) for a JSON object against an explicit schema — `{"learnings": [{"insight": "...", "sourceUrl": "..."}], "followUpQuestions": [...]}`, with the prompt instructing "Return valid JSON only". `parse_research_results_response()` runs `_load_repaired_json()` on the response first and returns on the dict branch; the `LEARNING_LINE_PATTERN` / `QUESTION_LINE_PATTERN` line regexes (`Learning [source_url]: <insight>`, `Question: <question>`) plus a bare-URL heuristic are reached only when JSON parsing yields neither learnings nor questions. `generate_search_queries()` / `parse_search_queries_response()` has the same JSON-first, regex-fallback shape. Depth control is explicit: `new_breadth = max(2, breadth // 2)`, `new_depth = depth - 1`, and the follow-up questions plus the prior research goal become the next query. Context is trimmed by `trim_context_to_word_limit`.

Synthesis is `ReportGenerator.write_report()` calling `generate_report()` in `actions/report_generation.py`, with `TOTAL_WORDS` 1200 and `REPORT_FORMAT` "APA" by default; `agent.py` also exposes `write_introduction`, `write_report_conclusion`, `get_subtopics`, `extract_headers`, `table_of_contents`, and `add_references(report_markdown, visited_urls)` for the citation section.

The `multi_agents/` directory is a genuinely different orchestration: a LangGraph `StateGraph(ResearchState)` in `multi_agents/agents/orchestrator.py`. Nodes are `browser`, `planner`, `researcher`, `writer`, `fact_checker`, `visualizer`, `publisher`, and `human`; edges run `browser -> planner -> human`, `researcher -> writer -> fact_checker`, `visualizer -> publisher -> END`, with two `add_conditional_edges` routed by `_route_human_feedback` and `_route_fact_check`. The README describes this as an 8-agent team (Human, Chief Editor, Researcher, Editor, Reviewer, Revisor, Writer, Publisher) inspired by the STORM paper. An AG2 variant lives in `multi_agents/ag2/`.

```
query
 |
 v  choose_agent()  ->  persona + role prompt
 |
 v  plan_research(): 1 scoping search -> generate_sub_queries() [strategic LLM]
 |
 +---> asyncio.gather over sub-queries -------------------+
 |        sub-q1: search -> dedupe urls -> scrape -> embed-compress
 |        sub-q2: search -> dedupe urls -> scrape -> embed-compress
 |        sub-qN: (+ optional MCP retriever, fast|deep|disabled)
 +--------------------------------------------------------+
 |
 v  joined context  ->  generate_report()  ->  add_references()

deep mode only:
 generate_search_queries(breadth) -> nested GPTResearcher per query (semaphore)
   -> parse JSON {learnings, followUpQuestions} (json_repair)
      -> fallback: "Learning [url]:" / "Question:" line regexes
   -> recurse(max(2, breadth//2), depth-1)
```

#### Key components

`_SUPPORTED_PROVIDERS` in `gpt_researcher/llm_provider/generic/base.py` lists 27 backends including openai, anthropic, azure_openai, bedrock, google_vertexai, google_genai, ollama, vllm_openai, groq, deepseek, xai, mistralai, together, openrouter, and litellm (the remainder: cohere, fireworks, huggingface, dashscope, gigachat, aimlapi, netmind, forge, avian, minimax, atlascloud, nebius). Models are configured in three tiers: `FAST_LLM`, `SMART_LLM`, `STRATEGIC_LLM` (defaults `openai:gpt-5.4-mini` and `openai:gpt-5.4`).

Search: 21 retrievers under `gpt_researcher/retrievers/`, all exported from `retrievers/__init__.py` — tavily as default (`DEFAULT_CONFIG['RETRIEVER'] = 'tavily'`), plus serper, serpapi, searchapi, google, bing, brave (`brave/brave.py`), duckduckgo, searx, exa, arxiv, semantic_scholar, pubmed_central, openalex (`openalex/openalex.py`), bocha, xquik, getxapi, groundroute (`groundroute/groundroute.py`), crw (`crw/crw.py`), custom, and mcp. Scraping: `BeautifulSoupScraper` (default `SCRAPER=bs`), `WebBaseLoaderScraper`, `PyMuPDFScraper`, `ArxivScraper`, `BrowserScraper`, `NoDriverScraper`, `TavilyExtract`, `FireCrawl`, with `MAX_SCRAPER_WORKERS` 15.

State is in-process: `visited_urls`, `research_sources`, `research_images`, and per-step cost accounting (`get_costs`, `get_step_costs`). Memory is embedding-backed (`EMBEDDING=openai:text-embedding-3-small`, `SIMILARITY_THRESHOLD` 0.42) with a `vector_store/` wrapper for LangChain vector stores. `ReportSource` supports web, local, azure, langchain_documents, langchain_vectorstore, static, and hybrid. Structured output is prompt-declared rather than API-enforced: both sub-query generation and deep-research learning extraction request a JSON object against a stated schema, parse it leniently with `json_repair`, and fall back to line-prefix regexes when the model returns prose instead.

Human-in-the-loop exists only in the LangGraph app (`agents/human.py`, `plan_review.py`, `include_human_feedback` in `task.json`). Surfaces: FastAPI + WebSocket server (`main.py` -> `backend/server/app.py`), a lightweight HTML/JS frontend, a NextJS frontend, `cli.py`, the pip package, Docker Compose, Terraform, a Claude Skill (`npx skills add assafelovic/gpt-researcher`), and an MCP server that now lives in the separate `assafelovic/gptr-mcp` repo. GPT Researcher is also an MCP *client*: `RETRIEVER=tavily,mcp` plus `mcp_configs`, with `MCP_STRATEGY` of fast, deep, or disabled. LangSmith tracing is supported.

#### Evaluation and benchmarks

Unlike most projects in this space, real numbers exist. The repo ships `evals/simple_evals/`, adapted from OpenAI's simple-evals SimpleQA methodology, and commits its run logs. `evals/simple_evals/logs/SimpleQA Eval 100 Problems 2-22-25.txt` reports 100/100 queries completing with 92 CORRECT, 7 INCORRECT, 1 NOT_ATTEMPTED, accuracy 0.929, F1 0.925, total cost $9.60, average $0.096 per query. A second suite, `evals/hallucination_eval/`, compares reports against source material.

Independently, DeepResearchGym (arXiv 2505.19253, CMU, ICTIR 2026) evaluates GPT-Researcher alongside Perplexity sonar-deepsearch, OpenAI gpt4-search-preview, OpenDeepSearch, HuggingFace-DeepSearch, Search-o1, and Search-R1. Reading its Table 2 requires care, because the table has two column groups: systems run against a **commercial search API** and systems run inside the **DRGym sandbox API**. In the commercial group GPT-Researcher scores key-point recall 60.61, citation precision 89.11, citation recall 94.29, clarity 86.37, insightfulness 81.52; Perplexity sonar-deepsearch scores KPR 72.50, citation precision 55.65, citation recall 99.22, clarity 89.50, insightfulness 89.26. So GPT-Researcher leads citation precision there by roughly 33 points, while Perplexity leads key-point recall, citation recall, clarity and insightfulness. In the DRGym group GPT-Researcher scores KPR 64.67, citation precision 85.36, citation recall 90.82, clarity 83.70, insightfulness 78.01, and tops every reported metric (KPR: OpenDeepSearch 42.81, HF-DeepSearch 35.22, Search-o1 29.93, Search-R1 4.95; citation precision: 81.32, 0.10, 0.00, 0.00). gptr.dev quotes exactly the DRGym figures — "Precision 85.36%", "Clarity 83.70%", "Key Point Recall 64.67%", each tagged #1 — and those #1 tags hold for that column. The nuance worth flagging is narrower than a contradiction: the FAQ's phrasing "#1 ... ahead of Perplexity Deep Research and OpenAI Deep Research" reads as a head-to-head, but neither Perplexity nor gpt4-search-preview was run in the DRGym sandbox at all (every DRGym cell is "–"), and in the commercial setting where Perplexity does appear, GPT-Researcher's genuine win is on citation precision. No GAIA, BrowseComp, HLE, DeepResearch Bench, or xbench-DeepSearch results were found. Self-reported cost/latency: about 3 minutes per standard task per the 2023 blog post, and about 5 minutes and $0.40 per deep-research run on o3-mini high effort per the README.

#### Strengths

Longevity and polish: three years of releases, a real test and eval suite, committed benchmark logs, and multiple deployment surfaces. Breadth of pluggability is the standout: 27 LLM providers, 21 retrievers, 8 scrapers, 7 report sources, all swappable by environment variable. Parallelism is genuine and cheap, since `asyncio.gather` over independent sub-queries avoids the sequential-tool-call tax of ReAct agents. Citation discipline is measurably good per DeepResearchGym, where GPT-Researcher posts the best citation precision of any system in either column group. MCP client support plus local and hybrid document sources make it practical for mixing private data with web search. Two orchestration options ship in one repo: the fast library flow and the LangGraph reviewer/reviser graph with a human gate.

#### Weaknesses and limitations

The standard pipeline plans once and never revisits: no reflection, no coverage gap analysis, no adaptive stopping. Only `deep` mode recurses, and its depth schedule is a fixed halving heuristic rather than an information-driven decision. Deep-research reflection does ask for a JSON schema and repair-parse it, with line regexes as a fallback — defensive layering rather than a brittle contract — but nothing validates the parsed learnings beyond that, and the fallback path is lossier than the JSON path; whether malformed output triggers a retry is unverified. Recursion re-instantiates whole `GPTResearcher` objects, which is heavy and makes cost hard to bound. No clarification turn in the library path, and human-in-the-loop is confined to the LangGraph app. State is in-memory only, so there is no resumable run or durable checkpoint in the core flow. The default stack leans on OpenAI plus Tavily, both paid. There is one real case of documentation drift, and it is about licensing rather than benchmarks: gptr.dev's FAQ structured data says "GPT Researcher is MIT-licensed and free to use" and PyPI metadata for `gpt-researcher` 0.16.0 reports `license: MIT`, while the repo's `LICENSE` file, its README disclaimer, and the GitHub API all say Apache-2.0. A third-party survey (digitalapplied) counted 191 open issues at its time of writing; that figure is not comparable to today's 37 issues / 46 PRs split, and the same article's complaint about report formatting, source rendering and failure handling is a category-wide observation — it argues that none of the open-source deep-research agents it surveys matches a vendor deep-research mode for out-of-the-box polish — not a verdict on GPT Researcher specifically.

#### Best fit

Best for engineers who want a report-generating research component they can embed and reconfigure: a pip import with a two-call API (`conduct_research()`, `write_report()`), swappable providers, and an existing FastAPI/WebSocket server to copy. Also good for teams that need private data blended with web search via MCP or `DOC_PATH`.

Compared with STORM (stanford-oval/storm), which is outline-first and Wikipedia-article shaped with a Co-STORM human-in-the-loop discourse protocol, GPT Researcher is report-first, far more configurable at the provider level, and better instrumented, but weaker on structured outline construction. Compared with LangChain's open_deep_research or similar graph-native agents, GPT Researcher offers less principled state management and no checkpointing, but ships far more retriever and scraper integrations plus a production frontend. If you want measured citation quality and many pluggable backends today, pick GPT Researcher; if you want a reflective, resumable graph you will heavily customize, look at a LangGraph-native alternative.

#### Sources

- https://github.com/assafelovic/gpt-researcher
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/README.md
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/LICENSE
- https://api.github.com/repos/assafelovic/gpt-researcher
- https://github.com/search?q=repo%3Aassafelovic%2Fgpt-researcher+is%3Aissue+is%3Aopen
- https://github.com/assafelovic/gpt-researcher/releases
- https://pypi.org/project/gpt-researcher/
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/gpt_researcher/agent.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/gpt_researcher/skills/researcher.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/gpt_researcher/skills/deep_research.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/gpt_researcher/skills/writer.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/gpt_researcher/skills/context_manager.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/gpt_researcher/actions/query_processing.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/gpt_researcher/config/variables/default.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/gpt_researcher/utils/enum.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/gpt_researcher/llm_provider/generic/base.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/gpt_researcher/retrievers/__init__.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/gpt_researcher/scraper/__init__.py
- https://github.com/assafelovic/gpt-researcher/tree/master/gpt_researcher/retrievers
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/multi_agents/README.md
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/multi_agents/agents/orchestrator.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/evals/README.md
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/evals/simple_evals/logs/SimpleQA%20Eval%20100%20Problems%202-22-25.txt
- https://github.com/assafelovic/gpt-researcher/tree/master/evals
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/main.py
- https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/cli.py
- https://docs.gptr.dev/blog/building-gpt-researcher
- https://gptr.dev/
- https://arxiv.org/abs/2505.19253
- https://arxiv.org/html/2505.19253v1
- https://dl.acm.org/doi/10.1145/3805713.3820409
- https://www.digitalapplied.com/blog/open-source-deep-research-agents-2026-guide
- https://github.com/assafelovic/gptr-mcp


### 5. smolagents open_deep_research

Repository: https://github.com/huggingface/smolagents
License: Apache-2.0 | Stars: 29,262 as of 2026-09-09 | Language: Python | Pattern: Two-level manager/worker hierarchy: code-writing CodeAgent ReAct loop with periodic re-planning delegating to a ToolCallingAgent browser sub-agent
Fact-check: minor-issues, 7 corrections applied

#### Overview

Open Deep Research is not a standalone repository. It is an example directory, `examples/open_deep_research/`, inside Hugging Face's `smolagents` library, which describes itself as "a barebones library for agents that think in code" (GitHub API). It was contributed by Aymeric Roucher in PR #317, merged 2025-02-04, the same day as the launch blog post "Open-source DeepResearch - Freeing our search agents." Maintainer is Hugging Face; the blog credits Aymeric Roucher, Albert Villanova del Moral, merve, Thomas Wolf and Clementine Fourrier.

License is Apache-2.0 and primary language is Python (GitHub API). The parent repo had 29,262 stars, 2,946 forks and 803 open issues as of 2026-09-09, created 2024-12-05, last pushed 2026-08-25. On PyPI, `smolagents` first released 0.1.0 on 2024-12-27 and 1.26.0 on 2026-05-29 (41 releases). The example itself is never versioned or published to PyPI; the last commit touching its directory was 2025-12-17 ("Fix run_gaia.py token_counts when managed agent is called more than once (#1878)").

Maturity: the underlying framework is mature and heavily maintained. The Open Deep Research example is a maintained but essentially frozen reference implementation, updated only for dependency and API drift. It is a GAIA benchmark reproduction, not a productized research product.

#### Workflow architecture

The orchestration pattern is a two-level manager/worker hierarchy built on smolagents' generic multi-step ReAct loop, with periodic re-planning. There is no graph, state machine, or RL-trained policy.

`create_agent()` in `examples/open_deep_research/run.py` builds the whole system in about 40 lines. The manager is a `CodeAgent` (`max_steps=12`, `planning_interval=4`, `additional_authorized_imports=["*"]`) holding two tools, `visualizer` and `TextInspectorTool`, plus one managed agent. The worker is `text_webbrowser_agent`, a `ToolCallingAgent` named `search_agent` (`max_steps=20`, `planning_interval=4`, `provide_run_summary=True`) holding the browsing toolset. `run_gaia.py::create_agent_team` builds a near-identical team for benchmark runs: it takes `(model, token_counts)` rather than constructing the model itself, and it additionally passes `final_answer_checks=[increment_web_agent_token_counts]` to the search agent, a token-accounting hook that has no counterpart in `run.py`. Model kwargs also diverge: `run.py` sets `max_completion_tokens=8192` unconditionally, while `run_gaia.py` applies `reasoning_effort="high"` plus `max_completion_tokens=8192` only when `model_id == "o1"` and otherwise falls back to `max_tokens=4096`.

Clarification of the user request never happens. `run.py` passes the raw CLI question straight to `agent.run()`. `run_gaia.py` instead prepends a fixed motivational preamble ("It is paramount that you provide a correct answer... Failure or 'I cannot answer' or 'None found' will not be tolerated") and, for GAIA questions with attachments, pre-captions each file via `scripts/run_agents.py::get_single_file_description` and `get_zip_description`.

Planning is generic framework behavior, not custom code. `MultiStepAgent._run_stream` in `src/smolagents/agents.py` runs a plan at step 1 and every `planning_interval` steps thereafter by calling `_generate_planning_step`. The initial-plan prompt lives in `src/smolagents/prompts/code_agent.yaml` under `planning.initial_plan` and forces a facts survey with headings 1.1 facts given, 1.2 facts to look up, 1.3 facts to derive, then a high-level step plan terminated by `<end_plan>`. Re-planning uses `update_plan_pre_messages` and `update_plan_post_messages`, which run in summary mode (system prompt and prior plans stripped so the old plan does not anchor the new one) and are told how many `remaining_steps` are left. That is the depth-and-breadth control: a step budget the model is periodically reminded of, plus hard `max_steps` caps.

Query generation, search and reading all happen inside the worker's ReAct loop. `ToolCallingAgent._step_stream` emits a tool call, `execute_tool_call` runs it, and the observation goes into memory. Search is `GoogleSearchTool(provider="serper")` from `src/smolagents/default_tools.py`, returning ranked title/link/date/snippet markdown with an optional `filter_year` argument. Page reading uses `scripts/text_web_browser.py::SimpleTextBrowser`, a Lynx-style text browser with a 5,120-character viewport, cookie jar from `scripts/cookies.py`, and a fetch path that converts anything text-like through `scripts/mdconvert.py::MarkdownConverter` and downloads everything else to disk before re-rendering it. Its tools mirror a human browser: `visit_page`, `page_up`, `page_down`, `find_on_page_ctrl_f`, `find_next`, and `find_archived_url` (Wayback Machine). Non-HTML artifacts go to `inspect_file_as_text` (`scripts/text_inspector_tool.py`), which converts PDF, DOCX, XLSX, PPTX, WAV, MP3, ZIP, YouTube transcripts and Wikipedia pages to markdown, then asks the LLM to answer under three fixed headings: short answer, extremely detailed answer, additional context.

Reflection and gap analysis are informal. Beyond re-planning, the worker's task template is patched at build time with an instruction to call `final_answer` with a request for clarification when it needs more context, so a gap is escalated back to the manager rather than resolved silently. Handoff is implemented by `MultiStepAgent.__call__`, which wraps the sub-agent output in the `managed_agent.report` template and, because `provide_run_summary=True`, appends a truncated `<summary_of_work>` transcript so the manager can audit the browsing trail.

Synthesis is where this project diverges most from report-writing deep research tools. The manager's final action is Python code calling `final_answer(...)`, executed by `CodeAgent._step_stream` via `parse_code_blobs` and `self.python_executor`. In `run_gaia.py` only, output is then passed through `scripts/reformulator.py::prepare_response`, which replays the whole memory to the model and demands a `FINAL ANSWER:` line coerced to a number, minimal words, or a comma-separated list. There is no long-form report generator and no citation handling at all: no reference collection, no source attribution, no inline links in the answer. URLs survive only incidentally inside browser observations.

```
question
  |
  v
[CodeAgent  manager]  max_steps=12, planning_interval=4
  |  plan step (facts survey 1.1/1.2/1.3 + step plan, <end_plan>)
  |  writes Python; may call visualizer / inspect_file_as_text
  |  calls search_agent("long natural-language task")
  |        |
  |        v
  |   [ToolCallingAgent  search_agent]  max_steps=20, planning_interval=4
  |     web_search (Serper) -> visit_page -> page_down / ctrl_f / find_next
  |     find_archived_url | inspect_file_as_text
  |     loop until final_answer  (or final_answer = "need clarification")
  |        |
  |        v
  |   report template + <summary_of_work> back to manager
  |
  |  re-plan every 4 steps with remaining_steps budget
  v
final_answer(...)  ->  [run_gaia.py only] reformulator -> "FINAL ANSWER: x"
```

#### Key components

Models go through `LiteLLMModel`. The defaults are set in `run.py::create_agent` (and mirrored in `run_gaia.py::answer_single_question`), not in the tool files: `model_id="o1"` with `reasoning_effort="high"` and `max_completion_tokens=8192`, so any LiteLLM-routable provider works. The framework's `src/smolagents/models.py` also ships `InferenceClientModel`, `LiteLLMRouterModel`, `OpenAIModel`, `AzureOpenAIModel`, `AmazonBedrockModel`, `TransformersModel`, `VLLMModel` and `MLXModel`, and `run_gaia.py` carries a commented-out `InferenceClientModel(model_id="Qwen/Qwen3-32B", provider="novita")` line for open models.

Search: the example is hardwired to Serper via `GoogleSearchTool(provider="serper")`, while `SimpleTextBrowser._serpapi_search` uses SerpApi only for `google:` addresses. These are two separate paths, not alternatives, despite the README's looser "either key" phrasing. The wider framework adds `WebSearchTool` (DuckDuckGo, Bing, Exa engines), `ApiWebSearchTool`, `DuckDuckGoSearchTool` and `WikipediaSearchTool`, none wired in by default.

Scraping stack is requests plus BeautifulSoup, markdownify, pdfminer.six, pypdf, mammoth, openpyxl, python-pptx, SpeechRecognition/pydub and youtube_transcript_api. Vision is a separate `visualizer` tool in `scripts/visual_qa.py`, a `@tool`-decorated function that posts a base64 data URI to `https://api.openai.com/v1/chat/completions` with `"model": "gpt-4o"` and `max_tokens=1000`; the same file also defines an unused `VisualQATool` class backed by `InferenceClient("HuggingFaceM4/idefics2-8b-chatty")`, which `run.py` never imports. Memory is the in-process `agent.memory.steps` list serialized by `write_memory_to_messages`; nothing is persisted between runs. Structured output exists in the framework (`structured_code_agent.yaml`, `CODEAGENT_RESPONSE_FORMAT`) but is off here. Human-in-the-loop is absent from the pipeline; `UserInputTool` and `examples/plan_customization` exist in the repo but are not part of this example. Surfaces: a CLI (`run.py`), a batch harness (`run_gaia.py --concurrency N` over a ThreadPoolExecutor), and a Gradio chat via `app.py` (`GradioUI(agent)`, with optional `file_upload_folder`). A public Space, `m-ric/open_Deep-Research` (672 likes, 43 community discussions), exists but is currently paused and not serving as of 2026-09-09 - the page shows the paused state and asks visitors to request a restart from the author - so trying the UI means running `python app.py` locally. Extensibility comes from the framework: `MCPClient` in `src/smolagents/mcp_client.py` supports stdio, streamable-http and sse MCP servers, and sandboxed execution is available through `E2BExecutor`, `DockerExecutor`, `ModalExecutor` and `BlaxelExecutor`.

#### Getting started

```bash
git clone https://github.com/huggingface/smolagents.git
cd smolagents/examples/open_deep_research
pip install -r requirements.txt
pip install -e ../../.[dev]
```

Keys: `SERPER_API_KEY` is mandatory. Both `run.py` and `run_gaia.py` instantiate `GoogleSearchTool(provider="serper")`, and `GoogleSearchTool.__init__` in `src/smolagents/default_tools.py` raises `ValueError("Missing API key. Make sure you have 'SERPER_API_KEY' in your env variables.")` for any provider other than `serpapi`, so agent construction fails outright without it. `SERPAPI_API_KEY` is optional and is consumed only by `BROWSER_CONFIG["serpapi_key"]`, feeding `SimpleTextBrowser._serpapi_search` for `google:` addresses; the README's "either key" wording is out of date relative to the code. You also need `OPENAI_API_KEY` for the default `o1` model and the `visualizer` tool, and `HF_TOKEN` (both `run.py` and `run_gaia.py` call `login(os.getenv("HF_TOKEN"))` at import). The README warns that default `o1` needs OpenAI tier-3 access.

```bash
python run.py --model-id "o1" "Your question here!"
python app.py                 # Gradio UI
python run_gaia.py --concurrency 32 --run-name my-run --model-id gpt-4o
```

Deployment is whatever you build yourself: a local process, the Gradio app, or a Hugging Face Space. There is no Dockerfile, server, or API in this directory.

#### Evaluation and benchmarks

The only benchmark is GAIA. The README states 55% pass@1 on the GAIA validation set against 67% for OpenAI Deep Research; the blog post gives the precise 55.15% validation figure, cites roughly 46% for Magentic-One as the prior open-framework state of the art, and reports that the same setup emitting JSON tool calls instead of code collapses to 33% average. The blog notes OpenAI Deep Research reached about 67% overall and 47.6% on level 3. Reproduction used a manually augmented dataset, `smolagents/GAIA-annotated`, where single-page PDF and XLS files were screenshotted to PNG so the vision path could read them, and `scripts/gaia_scorer.py` plus `analysis.ipynb` handle scoring. No BrowseComp, HLE, DeepResearch Bench, or xbench-DeepSearch numbers exist for this example.

A third-party number does exist, and it is lower than the published one. MiroFlow's Table 1 ("Comparison of agent frameworks") lists smolagents with an OpenAI o1 backbone at 49.7 on GAIA validation - the Open Deep Research configuration exactly - roughly 5.5 points below the 55.15% announced in the launch blog. MiroFlow's own caption warns that "some open-source frameworks are difficult to reproduce, and some reported performance remains ambiguous," which cuts in the same direction as the reproducibility caveats below.

Those caveats are concrete in the committed code. `run_gaia.py::get_examples_to_answer` returns `[line for line in eval_ds.to_list() if line["question"] not in done_questions and line["file_name"]]`; the trailing `and line["file_name"]` silently restricts the run to GAIA questions with an attached file and skips every text-only question, so an out-of-the-box run does not evaluate the full validation set the 55.15% figure refers to unless you edit that filter. The script also exposes `--use-raw-dataset`, which pulls `gaia-benchmark/GAIA` instead of the gated `smolagents/GAIA-annotated`, so the gated dataset is not strictly required to run - only to match the published score.

#### Strengths

Radical simplicity, though the "roughly 500 lines" framing sometimes attached to this project undercounts it by about 7x. The example directory holds about 3,340 lines of Python: the agent wiring is roughly 450 lines (`run.py` 125, `run_gaia.py` 312, `app.py` 11), and the rest is the browser and converter toolset - `scripts/mdconvert.py` 1,002 lines, `scripts/cookies.py` 715 lines of cookie data, `scripts/text_web_browser.py` 567, plus `cookies`-free odds and ends. Excluding `cookies.py` and `mdconvert.py`, hand-written logic is around 1,600 lines. That is still small enough to read in an afternoon, which makes it the best teaching artifact in this space and a very good starting skeleton. The code-action design is empirically validated: 55.15% versus 33% for the JSON variant in the same harness is one of the few published ablations isolating that choice. Model portability through LiteLLM is real, and the text browser plus text inspector combination is unusually strong on non-HTML artifacts (PDF, spreadsheets, slides, audio, ZIP, YouTube transcripts). Apache-2.0, an active parent project, a (currently paused) public Space, and framework-level MCP and sandbox support round it out.

#### Weaknesses and limitations

It is a GAIA answer machine, not a report writer. There is no clarification turn, no outline, no long-form synthesis, and crucially no citation handling, so it cannot produce a sourced research document without you writing that layer. The reformulator that forces short answers only runs in `run_gaia.py`, so `run.py` and `app.py` output whatever the manager passes to `final_answer`. Search is a single Google reseller with a paid, mandatory key. Breadth is shallow: one worker agent, no parallel fan-out of researchers, and depth control is only step caps plus a `remaining_steps` hint. The default configuration is unsafe by design, with `additional_authorized_imports=["*"]` and the local Python executor, which means the manager can run arbitrary imports on your machine unless you swap in a remote executor. The example is effectively frozen since late 2025 while the surrounding library keeps moving, and the blog's stated limitation stands: text-only browsing cannot match vision or GUI-driven browsing. Reproducing the published score requires the manually screenshot-augmented gated dataset and an edit to the `file_name` filter in `get_examples_to_answer`, since the committed harness runs only the file-attached subset of validation.

#### Best fit

Best for engineers who want to understand or fork a minimal deep research agent, for GAIA-style multi-hop factoid and file-heavy question answering, and for teams that need a small, auditable, Apache-2.0 base they will extend themselves. It is the wrong choice if you need a polished cited report out of the box.

Against LangChain's Open Deep Research, smolagents is far smaller and simpler but gives up the supervisor plus parallel-researcher fan-out, configurable report structure, and citation assembly that report-oriented systems provide. Against Microsoft's Magentic-One, from which its browser and inspector tools are adapted, it is leaner and scored higher on GAIA validation per the blog (55.15% versus roughly 46%), though MiroFlow's independent 49.7 for the same configuration narrows that gap considerably. If you want a working research report generator, look elsewhere; if you want the clearest reference implementation of a code-writing browsing agent, this is it.

#### Sources

- https://github.com/huggingface/smolagents
- https://api.github.com/repos/huggingface/smolagents
- https://github.com/huggingface/smolagents/tree/main/examples/open_deep_research
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/README.md
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/run.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/run_gaia.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/app.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/requirements.txt
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/scripts/text_web_browser.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/scripts/text_inspector_tool.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/scripts/reformulator.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/scripts/run_agents.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/scripts/visual_qa.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/scripts/mdconvert.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/examples/open_deep_research/scripts/cookies.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/src/smolagents/agents.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/src/smolagents/models.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/src/smolagents/default_tools.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/src/smolagents/prompts/code_agent.yaml
- https://raw.githubusercontent.com/huggingface/smolagents/main/src/smolagents/mcp_client.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/src/smolagents/remote_executors.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/src/smolagents/gradio_ui.py
- https://raw.githubusercontent.com/huggingface/smolagents/main/src/smolagents/cli.py
- https://huggingface.co/blog/open-deep-research
- https://github.com/huggingface/smolagents/pull/317
- https://github.com/huggingface/smolagents/commits/main/examples/open_deep_research
- https://pypi.org/pypi/smolagents/json
- https://huggingface.co/spaces/m-ric/open_Deep-Research
- https://arxiv.org/abs/2602.22808
- https://arxiv.org/pdf/2602.22808


### 6. deepagents

Repository: https://github.com/langchain-ai/deepagents
License: MIT | Stars: 29,226 (as of 2026-09-09) | Language: Python (with a separate TypeScript port, deepagentsjs) | Pattern: Middleware-wrapped single ReAct loop acting as a supervisor that delegates to isolated-context subagents via a `task` tool
Fact-check: minor-issues, 3 corrections applied

#### Overview

`deepagents` is LangChain's "batteries-included agent harness": a Python SDK that wraps LangChain's `create_agent()` with an opinionated default stack of middleware for a virtual filesystem, subagent delegation, context compaction, skills, memory, permissions and human approval. It is maintained by LangChain (the `langchain-ai` GitHub org), licensed MIT, and written primarily in Python; a separate TypeScript port lives at `langchain-ai/deepagentsjs`. The GitHub API reports 29,226 stars, 4,098 forks and 188 open issues as of 2026-09-09, with the repository created on 2025-07-27 and last pushed on 2026-09-09. PyPI shows the first release, `deepagents` 0.0.1, on 2025-07-29; the in-repo changelog records the current SDK at 0.7.13, released 2026-09-02.

Maturity is best described as actively maintained but fast-moving and pre-1.0. `pyproject.toml` still classifies the package as "Development Status :: 4 - Beta", and the changelog shows breaking changes as recently as 0.7.0 (2026-07-29), which removed `TodoListMiddleware` from the defaults. The repository is now a monorepo: `libs/deepagents` (the SDK), `libs/code` (`dcode`, a terminal coding agent), `libs/acp` (an Agent Client Protocol server), `libs/talon`, `libs/evals`, and sandbox partner packages under `libs/partners/` (daytona, modal, runloop, vercel, quickjs). Deep research is not the product; it is one example under `examples/deep_research`, and the harness is the substrate for NVIDIA's AI-Q blueprint.

#### Workflow architecture

The orchestration pattern is not a hand-written graph or state machine. `create_deep_agent()` in `libs/deepagents/deepagents/graph.py` assembles a middleware list and then calls LangChain's `create_agent(...)`, returning the compiled graph with `.with_config({"recursion_limit": 9_999, ...})`. The result is a single ReAct-style tool-calling loop whose behavior is shaped by middleware, plus a supervisor pattern layered on top: the main loop can call a `task` tool to spawn subagents with isolated context windows.

The main-agent stack, in assembly order in `graph.py`, is `SkillsMiddleware` (optional), `FilesystemMiddleware`, `SubAgentMiddleware`, `create_summarization_middleware(model, backend)`, `PatchToolCallsMiddleware`, then optional `AsyncSubAgentMiddleware`, profile middleware, `append_prompt_caching_middleware`, `MemoryMiddleware`, `HumanInTheLoopMiddleware`, and finally `_ToolExclusionMiddleware`. State is `DeepAgentState`, which puts a `DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)` on `messages` to keep checkpoint growth linear.

Research-specific behavior lives entirely in prompts and tools in the example. `examples/deep_research/agent.py` builds one agent with `create_deep_agent(model=..., tools=[tavily_search, think_tool], system_prompt=INSTRUCTIONS, subagents=[research_sub_agent])`, with `max_concurrent_research_units = 3` and `max_researcher_iterations = 3`. `research_agent/prompts.py` defines the six-step workflow: plan with `write_todos`, save the question to `/research_request.md`, delegate to subagents (never research directly), synthesize and consolidate citations, write `/final_report.md`, then re-read `/research_request.md` to verify. `SUBAGENT_DELEGATION_INSTRUCTIONS` sets breadth control: default one subagent, one per element for explicit comparisons, at most three parallel, stop after three delegation rounds. `RESEARCHER_INSTRUCTIONS` sets depth control per researcher: 2-3 searches for simple queries, 5 maximum, stop when three or more relevant sources are found or the last two searches repeat. Reflection is an explicit tool, `think_tool` in `research_agent/tools.py`, which the prompt requires after every search. Citations are handled by prompt convention only: each unique URL gets one number across all subagent findings, inline `[1]` markers, and a trailing `### Sources` list.

There is no clarification step. The 0.7 SDK ships no authored base prompt (`BASE_AGENT_PROMPT` is deprecated in `graph.py`), so the agent begins researching from the first message unless the caller adds a clarifier.

```
user query
  |
  v
create_deep_agent loop  (supervisor, LangChain create_agent)
  |-- write_file  /research_request.md
  |-- write_todos (only if TodoListMiddleware is passed in; not default since 0.7.0)
  |-- task(subagent_type="research-agent")  x1..3 in parallel
  |        |
  |        +-> researcher ReAct loop (isolated context)
  |              tavily_search -> think_tool -> tavily_search ... (<=5 searches)
  |              returns ONE final message with findings + numbered sources
  |
  |-- [repeat delegation round, max 3]
  |-- synthesize + renumber citations
  |-- write_file /final_report.md
  +-- read_file  /research_request.md   (verify coverage)
```

Context offload is a first-class mechanism rather than a research trick: subagent intermediate work never enters the parent transcript (`DEFAULT_SUBAGENT_PROMPT` warns the subagent that only its final message is seen), oversized tool results are evicted to backend files by `FilesystemMiddleware`, and `summarization.py` compacts history on a model-dependent trigger. `compute_summarization_defaults()` returns `("fraction", 0.85)` of the context window (keeping `("fraction", 0.10)`) only when the model exposes a profile with an integer `max_input_tokens`; for any model without that profile metadata — a common case for self-hosted or newly added providers — it falls back to a fixed `("tokens", 170000)` trigger keeping the last `("messages", 6)`. Either way the pre-compaction history is offloaded rather than discarded: evicted messages are appended to `/conversation_history/{session_id}.md` on the configured backend, and that path is embedded in the summary so the agent can read back what was compacted.

#### Key components

Models: any LangChain chat model that supports tool calling. The deprecated default is `ChatAnthropic(model_name="claude-sonnet-4-6")` in `graph.py`; harness profiles exist for Anthropic Opus/Sonnet/Haiku, OpenAI Codex and NVIDIA Nemotron Ultra under `profiles/harness/`, and provider profiles for NVIDIA, OpenAI and OpenRouter. Because summarization defaults key off profile metadata, the choice of model also decides which compaction trigger you get.

Search and scraping: none in the SDK. There is no built-in `web_search` or `fetch_url` tool in `libs/deepagents/deepagents/`. The research example supplies its own: Tavily as a URL-discovery engine via `TavilyClient.search`, then `httpx.get` with a browser User-Agent, converted to markdown by `markdownify`, returned unsummarized. Default `max_results` is 1.

Tools and state: built-in tools are `ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep`, `execute` (sandbox backends only) and `task`. Backends are pluggable: `StateBackend` (thread-scoped default), `StoreBackend`, `FilesystemBackend`, `LocalShellBackend`, `CompositeBackend`, `ContextHubBackend`, a LangSmith backend, and `BaseSandbox` implementations from the partner packages. Memory is `AGENTS.md`-style injected files via `MemoryMiddleware`; skills are on-demand `SKILL.md` files via `SkillsMiddleware`.

Structured output, HITL, extensibility: `response_format` is forwarded to `create_agent`. Human-in-the-loop comes from `HumanInTheLoopMiddleware` plus `FilesystemPermission` rules converted by `middleware/_fs_interrupt.py`. MCP is supported through LangChain's tool interface; the docs state Deep Agents "fully support the Model Context Protocol". Surfaces include LangGraph Server and Studio (`langgraph dev`), the separate `deep-agents-ui` chat front end, the `dcode` terminal agent, an ACP server, and a GitHub Action (`action.yml`).

#### Getting started

```bash
uv add deepagents
```

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="openai:gpt-5.5",
    tools=[my_custom_tool],
    system_prompt="You are a research assistant.",
)
result = agent.invoke({"messages": "Research LangGraph and write a summary"})
```

For the research example:

```bash
cd examples/deep_research
uv sync
export ANTHROPIC_API_KEY=...   # model
export TAVILY_API_KEY=...      # web search
export LANGSMITH_API_KEY=...   # required for the local LangGraph server
langgraph dev                  # or: uv run jupyter notebook research_agent.ipynb
```

Deployment options: LangGraph Server locally or on LangSmith deployments (`langgraph.json` maps `research` to `./agent.py:agent`), the `deep-agents-ui` front end pointed at that server, remote sandboxes through the partner backends, and `dcode` for terminal use.

#### Evaluation and benchmarks

There are no GAIA, BrowseComp, HLE, DeepResearch Bench or xbench-DeepSearch numbers in this repository. What exists is `libs/evals`, a unified eval workflow (`.github/workflows/unified_evals.yml`) that scores models as deep agents on four axes: autonomous (`harbor-index`, Harbor/Terminal-Bench family), conversation (a curated 30-task `tau3-subset` of τ³-bench), context (a 30-task subset of Letta's Context-Bench), and research (`drbench-evals`, ServiceNow DRBench in app mode, arXiv 2510.00172), scored as a harmonic mean of insights recall, factuality, report quality and 1 minus distractor recall.

`libs/evals/UNIFIED_SCORECARD.md` publishes results, but they measure models, not the research pipeline, and the research axis has no published rows. Example figures: on the frozen lite profile, micro avg@k ranks "sol 0.528 > opus 0.407 > terra 0.398 > luna 0.370 > Sonnet 5 0.278 > GLM-5.2 0.241". For GPT-5.6 terra on the full profile, autonomous is pass@k 0.268 / avg@k 0.183 over 82 tasks, conversation 0.467 / 0.389 over 30, context 0.967 / 0.811 over 30, macro 0.567 / 0.461. Context-Bench calibration reports gpt-5.6-terra at 510/600 (85.0%) and gpt-5.6-luna at 552/600 (92.0%).

Downstream, LangChain's NVIDIA announcement claims the AI-Q blueprint built on Deep Agents "ranks #1 on deep research benchmarks" without naming a benchmark or score, and NVIDIA's own post says only that the architecture was "tuned to perform well on both Deep Research Bench and Deep Research Bench II leaderboards". Neither figure is verifiable from a published number, so treat both as unverified marketing claims about a downstream product rather than about `deepagents` itself.

#### Strengths

The harness abstraction is the real asset: filesystem offload, subagent context isolation, summarization with recoverable history, prompt caching, permissions and approvals all arrive configured, and each is replaceable without forking because they are ordinary `AgentMiddleware`. Backends make the same agent run against thread state, a store, local disk or a remote sandbox by swapping one argument. Being LangGraph-native brings streaming, checkpointing, interrupts, LangSmith tracing and a hosted deployment path for free. The engineering discipline is visible: a `DeltaChannel` reducer to keep checkpoints linear, a documented `ARCHITECTURE.md` and `THREAT_MODEL.md`, an eval suite with per-run CI links, and a changelog that names breaking changes. MIT licensing, Python and TypeScript parity, and a genuinely large community (29k stars, 4k forks) lower adoption risk.

#### Weaknesses and limitations

It is a harness, not a deep-research system. There is no search tool, no crawler, no dedup or reranking, no clarification turn, no citation verification, and no structured report schema in the SDK; the example supplies all of that in prose prompts, and its `tavily_search` fetches one result by default with a plain `httpx.get` that will fail on JavaScript-rendered or bot-protected pages. Citation integrity depends entirely on the model following renumbering instructions.

The example has also drifted from the SDK. Its prompts instruct the agent to call `write_todos`, but 0.7.0 removed `TodoListMiddleware` from the defaults, and `examples/deep_research/pyproject.toml` pins only `deepagents>=0.6.12`, so a fresh install gets a 0.7.x harness where that tool does not exist unless the caller passes the middleware explicitly. Defaults can also surprise you in the other direction: point the harness at a model whose profile lacks `max_input_tokens` and compaction fires at a fixed 170k tokens rather than at 85% of that model's real context window. More broadly, the pre-1.0 release cadence means upgrade risk; the independent Wavect review — Kevin Riedl / Wavect GmbH, "LangChain Deep Agents Review: Is the Agent Harness Ready for Production?", published 2026-08-23 and last reviewed 2026-09-02 — makes the same point and adds that auth, tenant isolation, budgets and incident recovery remain the adopter's problem. The project states a "trust the LLM" security model, so boundaries must be enforced at the tool and sandbox level. Finally, published evals score models on someone else's benchmarks; there is no reported number for the research example's own quality.

#### Best fit

Choose `deepagents` when you are building a long-horizon agent and want planning, delegation and context management as configured infrastructure rather than as code you write, and when you already accept the LangChain/LangGraph/LangSmith stack. It suits teams that need to plug in their own retrieval, MCP servers or sandboxes, and that will invest in prompts and evals themselves. It is a poor fit if you want a research pipeline that produces cited reports out of the box.

Against LangChain's now-archived `open_deep_research`, which shipped a purpose-built research graph with search integrations and report structure, `deepagents` is the lower layer and the more general one. That comparison is now historical rather than a live choice: the GitHub API reports `langchain-ai/open_deep_research` as archived and read-only, last pushed 2026-08-10, so it is no longer maintained and `deepagents` is the supported substrate going forward. Against LangChain's plain `create_agent`, it is the same runtime with the harness middleware bundled, and the README's own guidance is to drop to `create_agent` when you want a lighter surface or to LangGraph when the loop is the wrong shape. Against `nanoeval`-style or RL-trained end-to-end research models, `deepagents` is prompt-and-scaffold driven, which makes it far easier to audit and modify but leaves quality entirely dependent on the model you point at it.

#### Sources

- https://github.com/langchain-ai/deepagents
- https://api.github.com/repos/langchain-ai/deepagents
- https://raw.githubusercontent.com/langchain-ai/deepagents/main/README.md
- https://github.com/langchain-ai/deepagents/blob/main/libs/ARCHITECTURE.md
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/graph.py
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/middleware/subagents.py
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/middleware/summarization.py
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/middleware/filesystem.py
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/pyproject.toml
- https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/CHANGELOG.md
- https://github.com/langchain-ai/deepagents/blob/main/examples/deep_research/README.md
- https://github.com/langchain-ai/deepagents/blob/main/examples/deep_research/agent.py
- https://github.com/langchain-ai/deepagents/blob/main/examples/deep_research/research_agent/prompts.py
- https://github.com/langchain-ai/deepagents/blob/main/examples/deep_research/research_agent/tools.py
- https://github.com/langchain-ai/deepagents/blob/main/examples/nvidia_deep_agent/README.md
- https://github.com/langchain-ai/deepagents/blob/main/libs/evals/UNIFIED_EVALS.md
- https://github.com/langchain-ai/deepagents/blob/main/libs/evals/UNIFIED_SCORECARD.md
- https://github.com/langchain-ai/deepagents/blob/main/libs/evals/datasets/drbench-evals/README.md
- https://github.com/langchain-ai/deepagents/blob/main/openwiki/concepts/middleware-catalog.md
- https://github.com/langchain-ai/deepagents/blob/main/openwiki/concepts/context-management.md
- https://api.github.com/repos/langchain-ai/open_deep_research
- https://pypi.org/pypi/deepagents/json
- https://docs.langchain.com/oss/python/deepagents/overview
- https://www.langchain.com/deep-agents
- https://www.langchain.com/blog/nvidia-enterprise
- https://developer.nvidia.com/blog/how-to-build-deep-agents-for-enterprise-search-with-nvidia-ai-q-and-langchain
- https://wavect.io/blog/langchain-deep-agents-review/
- https://arxiv.org/abs/2510.00172


### 7. Dexter

Repository: https://github.com/virattt/dexter
License: MIT (README and repo page); no LICENSE file at root and GitHub API license field is null | Stars: 27,590 as of 2026-09-09 | Language: TypeScript | Pattern: Single ReAct-style tool-calling loop with one-level parallel subagent delegation
Fact-check: minor-issues, 3 corrections applied

#### Overview

Dexter is a terminal-first autonomous agent for financial research, written in TypeScript and run under the Bun runtime. The GitHub description is "An autonomous agent for deep financial research," and the README frames it as "Claude Code, but built specifically for financial research." It is maintained by Virat Singh (GitHub user `virattt`), the same author as `ai-hedge-fund`; the repo has no organization owner, so it is effectively a single-maintainer project with community PRs.

License is ambiguous in a way worth flagging. The README's final section says "This project is licensed under the MIT License," and the GitHub repo page shows MIT, but `https://api.github.com/repos/virattt/dexter` returns `"license": null`, and both `LICENSE` and `LICENSE.md` return 404 on the default branch. So MIT is the declared intent, not a machine-detectable license file.

Primary language per the API is TypeScript. Stars stood at 27,590 with 3,410 forks, 166 subscribers and 101 open issues as of 2026-09-09. The repo was created 2025-10-14, matching the author's launch post on X the same week ("An open source financial agent in ~200 lines of code"). The oldest visible tagged release is `v2026.2.5` (Feb 6), and the newest is `v1.0.5` (Aug 4); `pushed_at` is 2026-08-04T15:20:42Z. `package.json` still reads version 1.0.4, so release tagging is loose.

Maturity: well past prototype, still moving fast and single-maintainer. It has CI (`bun run typecheck` and `bun test` per AGENTS.md), colocated `*.test.ts` files, a permissions engine, a SQLite-backed memory layer, and a rubric eval harness. The README's own disclaimer says it is for "educational, entertainment, and informational purposes only" and not for real trading. The in-repo `AGENTS.md` is noticeably stale relative to the code (it names a default model of `gpt-5.5` and tools `financial_search` / `financial_metrics` that no longer exist in `src/tools/registry.ts`), which is a fair signal of the churn rate.

#### Workflow architecture

The orchestration pattern is a single ReAct-style tool-calling loop with one level of parallel subagent delegation. There is no graph, no state machine, and no separate planner node. Planning is prompt-driven and, for structured tasks, delegated to Markdown skill files.

The loop lives in `Agent.run()` in `src/agent/agent.ts`, an async generator that yields typed events. `Agent.create()` assembles the tool set from `getTools(model)` and builds the system prompt via `buildSystemPrompt()` in `src/agent/prompts.ts`, which injects compact tool descriptions, a skills section, a memory section, optional user `RULES.md`, optional `SOUL.md` identity text, and a channel formatting profile from `src/agent/channels.ts`. `DEFAULT_MAX_ITERATIONS` is 10.

Step by step, as implemented:

- Clarification is optional and model-initiated, not a fixed first stage. The `ask_user_question` tool (`src/tools/ask-user-question/ask-user-question.ts`) lets the agent pause mid-turn for 1 to 4 multiple-choice questions. It is CLI-only: `CLI_ONLY_TOOLS` in `agent.ts` strips it (and `bash`) on the WhatsApp/gateway channel and in headless runs.
- Planning/outline is prompt-level. Skills supply the explicit plans: `src/skills/write-memo/SKILL.md` carries an eight-step workflow checklist (frame the trade, gather data in parallel, build bear/base/bull, optional DCF anchor, draft, self-critique, render HTML, report), and `src/skills/dcf/SKILL.md` does the same for valuation. The prompt's skill policy says to invoke a relevant skill immediately as the first action, at most once per query.
- Query generation and search happen inside the loop as tool calls. `web_search` is built in `src/tools/registry.ts` as a fallback chain over whichever providers have keys; `searchWithProviders()` in `src/tools/search/web-search.ts` tries each in order and only errors when all fail.
- Page reading is two-tier. `web_fetch` (`src/tools/fetch/web-fetch.ts`) fetches a URL, converts HTML to Markdown via a lazily-loaded Turndown service in `src/tools/fetch/utils.ts`, then runs the caller's prompt over that Markdown with the provider's fast model. Cross-host redirects are returned as an instruction to re-fetch rather than followed. For JavaScript-heavy or interactive pages, the `browser` tool launches headless Chromium via Playwright (`src/tools/browser/browser.ts`).
- Reflection and gap analysis are not a separate node. Three mechanisms substitute: the scratchpad's soft limits, compaction summaries that include a "Pending Data Needs" and "Recommended Next Steps" section, and subagent self-contained answers. `src/agent/scratchpad.ts` implements `canCallTool()` with `maxCallsPerTool: 3` and a `similarityThreshold` of 0.7; it never blocks, it injects warnings, and `formatToolUsageForPrompt()` pushes those warnings back into the message array as a `HumanMessage`.
- Breadth is controlled by `spawn_subagent` (`src/tools/subagent/spawn-subagent.ts`). The leader emits multiple calls in one turn to fan out in parallel. `src/tools/subagent/types.ts` defines three types (`general-purpose`, `research`, `analysis`), each a bundle of worker system prompt, tool allow-list, and `maxIterations: 8`. `SUBAGENT_DISALLOWED_TOOLS` strips `spawn_subagent`, `ask_user_question` and `bash`, so delegation is exactly one level deep and subagents are read-only. Subagents run with `memoryEnabled: false` and a `systemPromptOverride`, and only their final answer plus a token count returns to the leader.
- Depth is bounded by `maxIterations` on both tiers, plus context management: `microcompactMessages()` per turn, `stripOldThinking(messages, 2)`, threshold-triggered LLM summarization in `src/agent/compact.ts`, `persistLargeResult()` spilling oversized tool results to disk with a preview injected, `enforceResultBudget()` per turn, and `truncateMessages()` with up to `MAX_OVERFLOW_RETRIES` of 2 on context-overflow errors.
- Synthesis is just the loop terminating: when the model returns no tool calls, `handleDirectResponse()` emits the final answer. The heavier deliverable path is the `write-memo` skill, which renders a self-contained HTML memo into `.dexter/memos/` using `src/skills/write-memo/memo-template.html`.
- Citation handling is light. `web_fetch` wraps its output with `formatToolResult(output, [url])`, so source URLs travel with the result, and the `research` subagent prompt asks for a "clear, sourced summary." I found no numbered-citation renderer or citation-verification pass.

Text diagram:

```
user query
   |
   v
Agent.create()  -> tools + system prompt (SOUL.md, RULES.md, skills, memory)
   |
   v
+-- Agent.run() loop (<= 10 iterations) -------------------+
|  microcompact -> strip old thinking -> stream LLM call   |
|      |                                                   |
|      +-- no tool calls --> final answer --> done          |
|      |                                                   |
|      +-- tool calls --> concurrent execute               |
|            get_financials / get_market_data /            |
|            read_filings / stock_screener /               |
|            web_search (Exa->Perplexity->Tavily->Lang) /  |
|            web_fetch / browser / memory_* / skill /      |
|            write_file|edit_file|bash (needs approval)    |
|            spawn_subagent  --> [subagent loop <= 8] xN   |
|                                (parallel, read-only,     |
|                                 cannot re-delegate)      |
|            |                                             |
|      cap+persist large results -> budget -> compact      |
|      -> inject tool-usage warnings -> drain user queue   |
+----------------------------------------------------------+
   |
   v
answer (CLI/WhatsApp) + JSONL trace in .dexter/scratchpad/
```

#### Key components

LLM providers are declared once in `src/providers.ts`: OpenAI (default), Anthropic, Google, xAI, Moonshot, DeepSeek, OpenRouter, Ollama and Ollama Cloud, with prefix-based routing (`claude-`, `gemini-`, `grok-`, `kimi-`, `deepseek-`, `openrouter:`, `ollama:`) and a per-provider `fastModel` plus `contextWindow` used for compaction thresholds. `src/model/llm.ts` sets `DEFAULT_MODEL = 'gpt-5.6-sol'` and wires LangChain chat classes (`@langchain/openai`, `@langchain/anthropic`, `@langchain/google-genai`, `@langchain/ollama`) with exponential-backoff retries.

Search providers: Exa, Perplexity, Tavily and LangSearch, tried in the user's preferred order (`/search` setting) then as fallbacks; plus `x_search` for X/Twitter when `X_BEARER_TOKEN` is set. Financial data comes from the Financial Datasets API through `get_financials`, `get_market_data`, `read_filings`, `stock_screener`, insider trades and institutional holdings modules under `src/tools/finance/`.

Scraping stack: Turndown for HTML-to-Markdown, Playwright Chromium for rendered pages, with `@mozilla/readability` and `linkedom` in dependencies.

Memory and state: `src/memory/` keeps Markdown files in `.dexter/memory/` indexed into `index.sqlite` via `better-sqlite3`, with hybrid retrieval (vector weight 0.7, text weight 0.3), temporal decay at a 30-day half-life, and MMR diversification at lambda 0.7. Embeddings reuse existing OpenAI, Gemini or Ollama keys. Per-query state is the JSONL scratchpad in `.dexter/scratchpad/`. Structured output is Zod throughout, including the eval judge schema.

Human in the loop: `ask_user_question`, plus an approval overlay. `AgentRunnerController` in `src/controllers/agent-runner.ts` surfaces `PendingApproval` objects backed by `src/permissions/` (engine, rules, command parser) for `write_file`, `edit_file` and every `bash` command.

Surfaces: an interactive CLI (`src/index.tsx`, `src/cli.ts`, `@mariozechner/pi-tui` components), a WhatsApp gateway built on `@whiskeysockets/baileys` with access control, and scheduling via the `cron` and `heartbeat` tools. Extensibility is via `SKILL.md` files with YAML frontmatter (`dcf`, `write-memo`, `x-research` ship in-tree), plus user-editable `SOUL.md` and `RULES.md`. I found no MCP client in the tool registry or dependencies; MCP support appears absent.

#### Getting started

```bash
curl -fsSL https://bun.com/install | bash
git clone https://github.com/virattt/dexter.git
cd dexter
bun install
cp env.example .env
```

Required keys: `OPENAI_API_KEY` (or another provider key) and `FINANCIAL_DATASETS_API_KEY`. Optional: `EXASEARCH_API_KEY`, `PERPLEXITY_API_KEY`, `TAVILY_API_KEY`, `LANGSEARCH_API_KEY`, `X_BEARER_TOKEN`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`, `MOONSHOT_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`, and the `LANGSMITH_*` tracing variables.

```bash
bun start          # interactive CLI
bun dev            # watch mode
bun run gateway:login && bun run gateway   # WhatsApp channel
```

Deployment is local-first: a CLI process or the long-running WhatsApp gateway. No Docker file, hosted service, or HTTP API is documented in the README or AGENTS.md. Note `postinstall` runs `playwright install chromium`, and the `bash` tool is skipped on Windows.

#### Evaluation and benchmarks

No published benchmark scores exist. Dexter has no reported GAIA, BrowseComp, HLE, DeepResearch Bench or xbench-DeepSearch numbers, and I found none in the README, AGENTS.md, or the independent reviews I checked.

What it ships is a harness rather than results: `src/evals/run.ts` runs the agent (`maxIterations: 10`, memory disabled, `channel: 'eval'`) over `src/evals/dataset/finance_agent.csv` (50 question rows across nine question-type categories) and grades with a rubric LLM judge in `src/evals/evaluator.ts`. The row count is easy to get wrong: the file is 237 physical lines and about 50 KB, but the Answer and Rubric columns contain newlines inside quoted fields, so parsing it as real CSV yields exactly 50 data rows. The repo's own parser agrees — `parseRow()` and `parseCSVRows()` in `src/evals/dataset.ts` advance the character index across line boundaries while inside a quoted field, precisely because rows span multiple lines. The question-type distribution sums to those 50 rows: Qualitative Retrieval 9, Quantitative Retrieval 9, Numerical Reasoning 8, Beat or Miss 7, Financial Modeling 4, Adjustments 4, Market Analysis 3, Trends 3, Complex Retrieval 3. That matters for how much coverage to read into the harness: 50 rows is a small in-tree sample of the Finance Agent benchmark, not a near-complete copy of it.

The rubric has two operators, `correctness` and `contradiction`, graded per atomic criterion, with results logged to LangSmith. The CSV schema (Question, Answer, Question Type, Expert time (mins), Rubric) matches the Vals AI Finance Agent benchmark format, and sample rows carry expert-time annotations ranging from 2 to 60 minutes (the distinct values present are 2, 3, 5, 10, 15, 20, 25, 30, 35 and 60), though the repo itself does not attribute the source. For external context, the original Finance Agent paper (arXiv 2508.00828, Aug 2025, built on 537 questions) reported OpenAI o3 best at 46.8 percent accuracy and $3.79 average cost per query; the live Vals AI Finance Agent v2 leaderboard (927 expert-reviewed questions, page updated 2026-09-05) now reports Muse Spark 1.2 leading at 60.60 percent, Claude Opus 5 at 58.63 percent and Gemini 3.5 Flash at 57.86 percent. Those are model scores, not Dexter scores, and no Dexter score is published on either.

#### Strengths

Domain depth is the real differentiator. Structured financial primitives (statements, segments, KPI guidance, insider trades, institutional holdings, SEC section extraction, screener) beat generic web-search-only deep research agents on finance questions. The context engineering is unusually careful for a single-maintainer project: microcompaction, LLM summarization that explicitly preserves every number, disk spillover for oversized results, per-turn result budgets, and overflow retries. Auditability is good, with a full JSONL trace per query. Provider breadth is wide and cleanly centralized in one registry. Subagent fan-out is correctly constrained: read-only, non-recursive, isolated. The permissions engine and approval overlay are real, not decorative. Skills give a clean extension point without code changes, and the WhatsApp gateway plus cron/heartbeat make it usable as an always-on assistant rather than a one-shot CLI.

#### Weaknesses and limitations

No published evaluation numbers, so quality claims are unverified. The in-tree eval set is also thin — 50 questions with a multi-line CSV format that is easy to miscount — so even a self-run score would carry wide error bars. The license is declared only in prose. There is no explicit planning or reflection stage, so plan quality is entirely model-dependent, and the anti-loop machinery is advisory warnings rather than enforcement. Citation handling is weak: source URLs ride along in tool results but nothing enforces or verifies attribution in the final answer, which matters for financial work. A hard `maxIterations` of 10 with a 3-calls-per-tool soft cap bounds genuinely deep multi-hour research. Delegation is one level only. Documentation is thin and partly stale, with no `docs/`, no ARCHITECTURE file, and an AGENTS.md that describes tools the code no longer has. Dependence on the Financial Datasets API adds a paid key and, per one independent review, US-equities-heavy coverage. Bun plus Playwright Chromium is a heavier install than a plain Python package, and `bash` is Unix-only. Bus factor is one.

#### Best fit

Best fit is an individual analyst, quant hobbyist, or small investment team that wants an auditable, locally-run research assistant over real fundamentals and filings, and is comfortable running a TypeScript CLI and paying for a market-data key. It is also a good reference implementation for anyone building a Claude-Code-style agent loop with context compaction and bounded subagent fan-out.

Closest alternatives: the author's own `ai-hedge-fund`, which simulates a panel of investor personas producing trading signals rather than open-ended research, so Dexter is the better pick when you want sourced analysis instead of a mock portfolio decision; and general-purpose open deep research agents such as GPT-Researcher or LangChain's open_deep_research, which have stronger report-writing and citation pipelines and broader web coverage but no structured financial data layer. Choose Dexter when the questions are about company financials and filings; choose a general deep research agent when the questions are not.

#### Sources

- https://github.com/virattt/dexter
- https://api.github.com/repos/virattt/dexter
- https://raw.githubusercontent.com/virattt/dexter/main/README.md
- https://raw.githubusercontent.com/virattt/dexter/main/AGENTS.md
- https://raw.githubusercontent.com/virattt/dexter/main/package.json
- https://raw.githubusercontent.com/virattt/dexter/main/env.example
- https://raw.githubusercontent.com/virattt/dexter/main/SOUL.md
- https://raw.githubusercontent.com/virattt/dexter/main/src/agent/agent.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/agent/prompts.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/agent/compact.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/agent/scratchpad.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/agent/channels.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/providers.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/model/llm.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/registry.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/subagent/spawn-subagent.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/subagent/types.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/search/index.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/search/web-search.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/fetch/web-fetch.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/fetch/utils.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/browser/browser.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/tools/ask-user-question/ask-user-question.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/controllers/agent-runner.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/memory/index.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/evals/run.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/evals/dataset.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/evals/evaluator.ts
- https://raw.githubusercontent.com/virattt/dexter/main/src/evals/dataset/finance_agent.csv
- https://raw.githubusercontent.com/virattt/dexter/main/src/skills/write-memo/SKILL.md
- https://raw.githubusercontent.com/virattt/dexter/main/src/skills/dcf/SKILL.md
- https://github.com/virattt/dexter/tree/main/src/skills
- https://github.com/virattt/dexter/releases
- https://github.com/virattt/dexter/releases?page=4
- https://x.com/virattt/status/1978224884464357579
- https://andrew.ooo/posts/dexter-autonomous-financial-research-agent-review/
- https://yuv.ai/blog/dexter
- https://www.vals.ai/benchmarks/fabv2
- https://huggingface.co/datasets/vals-ai/finance_agent_benchmark
- https://arxiv.org/pdf/2508.00828


### 8. Tongyi DeepResearch (WebAgent family)

Repository: https://github.com/Alibaba-NLP/DeepResearch
License: Apache-2.0 | Stars: 19,923 (as of 2026-09-09) | Language: Python | Pattern: Single-agent multi-turn ReAct loop over an RL-trained end-to-end model (parallelism via independent question rollouts, not sub-agents)
Fact-check: minor-issues, 4 corrections applied

#### Overview

Tongyi DeepResearch is Alibaba Tongyi Lab's open-weight deep research agent: a 30B-A3B mixture-of-experts model plus a thin reference harness that drives it. The repository `Alibaba-NLP/DeepResearch` describes itself as "Tongyi Deep Research, the Leading Open-source Deep Research Agent" and doubles as the umbrella home for the WebAgent research line (WebWalker, WebDancer, WebSailor, WebShaper, WebWatcher, WebResearcher, ReSum/WebResummer, WebWeaver, AgentFold, WebLeaper, ParallelMuse, NestBrowse).

License is Apache-2.0 and the primary language is Python. As of 2026-09-09 the GitHub API reports 19,923 stars, 1,531 forks, 92 open issues and 133 watchers. The repo was created 2025-01-09 (it began life as the WebWalker code drop) and its last recorded push is 2026-02-27. The README news section lists the model release on 2025-09-17 and OpenRouter availability on 2025-09-20; the newest dated entry anywhere in the tree is 2025.12.24 for WebLeaper-30B-A3B. Contact for the project is Yong Jiang at Alibaba. The model itself is Tongyi-DeepResearch-30B-A3B: 30.5B total parameters, 3.3B activated per token, built on Qwen3-30B-A3B-Base, 128K context, per the technical report (arXiv 2510.24701).

Maturity is best read as "strong weights, research-grade scaffold." The model is production-hosted (Alibaba Bailian, OpenRouter, HF Spaces), but the code in `inference/` is a benchmark harness with hardcoded ports and no packaging, tests, server or UI. Anything you build on it, you build yourself.

#### Workflow architecture

The orchestration pattern is a single-agent multi-turn ReAct loop over an end-to-end RL-trained model. There is no graph, no state machine, no planner-executor split, and no supervisor with researcher sub-agents in the released inference path. The intelligence that other frameworks put into orchestration code was moved into the weights.

Control flow runs `inference/run_react_infer.sh` -> `inference/run_multi_react.py` -> `MultiTurnReactAgent._run` in `inference/react_agent.py`.

Step by step, against the checklist:

- **Clarification:** none. `_run` reads `data['item']['question']` straight from a JSONL/JSON row and never asks the user anything.
- **Planning / outline:** implicit only. The system prompt (`SYSTEM_PROMPT` in `inference/prompt.py`) says "You are a deep research assistant" and inlines five tool schemas as JSON inside `<tools>` tags. Planning happens inside the model's `<think>` block; no plan object or outline exists in the ReAct path.
- **Query generation and search:** the model emits `<tool_call>{"name": "search", ...}</tool_call>`; `search` takes an *array* of queries so one turn can fan out several complementary searches. `Search.google_search_with_serp` in `inference/tool_search.py` POSTs to `google.serper.dev/search` and formats the `organic` results as a numbered markdown list with title, link, date, source and snippet; it loops over the query array sequentially, and switches locale to `gl=cn, hl=zh-cn` when a query contains CJK characters. The scholar tool is a different endpoint on the same host: `Scholar.google_scholar_with_serp` in `inference/tool_scholar.py` POSTs to `google.serper.dev/scholar` (line 41), has no CJK locale branch, and fans its query array out through a `ThreadPoolExecutor`. Both are keyed by `SERPER_KEY_ID`.
- **Page reading and extraction:** `Visit.readpage_jina` in `inference/tool_visit.py` fetches `https://r.jina.ai/{url}`, truncates to 95,000 `cl100k_base` tokens, then sends `EXTRACTOR_PROMPT` to a *separate* summariser model (`SUMMARY_MODEL_NAME` at `API_BASE`). The prompt asks for JSON with `rational`, `evidence` and `summary` fields, but the code consumes only `raw["evidence"]` and `raw["summary"]`; `rational` is discarded. The observation handed back to the agent is a goal-conditioned digest, never raw HTML. Two distinct retry loops guard the summariser: an empty or near-empty response (`len(raw) < 10`) triggers up to three retries with progressive truncation, cutting content to `int(0.7 * len(content))` each attempt and falling back to 25,000 characters on the last; separately, a `json.loads` failure triggers up to three re-asks against the *same* unchanged `messages` with no further truncation, after which a canned "could not be processed" observation is returned.
- **Reflection and gap analysis:** no separate critic or reflection node. It is emergent behaviour inside `<think>`. A `sanity_check_output` method is defined on `MultiTurnReactAgent` (line 56 of `inference/react_agent.py`) but is never invoked anywhere in the released inference path — not in `_run`, not in `call_server`, not in `run_multi_react.py` — so the think block is not actually validated at runtime, and a response missing `<think>` is appended to `messages` unchanged. The only real output check is the string test for `<answer>`/`</answer>`.
- **Depth and breadth control:** three hard budgets, all in `_run`. `MAX_LLM_CALL_PER_RUN` (env, default 100) caps turns; a 150-minute wall clock aborts with `termination = 'No answer found after 2h30mins'`; and `count_tokens` is called every round against `max_tokens = 110 * 1024`. On token overflow the last message is *overwritten* with an instruction to stop calling tools and answer now, and one final call is made.
- **Synthesis:** the same model writes the final text inside `<answer></answer>`, extracted by string split. The result dict carries `question, answer, messages, prediction, termination`.
- **Citation handling:** none in the ReAct path. Evidence banks with `url2id` mappings and per-section cited retrieval exist only in the `WebAgent/WebWeaver` sub-project (see its README's documented output fields).

Parallelism is at the wrong level to call it multi-agent: `run_multi_react.py` uses a `ThreadPoolExecutor` (default 20 workers) over independent questions, does `roll_out_count` repeated rollouts per question (default 3), and round-robins sticky per-question assignment across vLLM ports 6001-6008. The "Heavy" IterResearch mode, which reconstructs a lean workspace each round and fans out parallel Research Agents into a Synthesis Agent, is described in the blog and tech report but `FAQ.md` states plainly that it "is not fully open-sourced yet."

```
dataset.jsonl
   |
run_multi_react.py  (ThreadPool: N questions x roll_out_count rollouts)
   |  sticky round-robin -> vLLM :6001..:6008
   v
MultiTurnReactAgent._run
   |
   +-> [system: SYSTEM_PROMPT + date] [user: question]
   |
   +--> loop (<=100 calls, <=150 min, <=110K tokens) ------+
   |     call_server -> OpenAI-compatible vLLM             |
   |     stop=["<tool_response>"]                           |
   |     content = <think>...</think> + <tool_call>|<answer>|
   |        |                                               |
   |        +-- search  -> serper.dev/search -> snippets ---+
   |        +-- visit   -> Jina    -> summariser LLM -------+
   |        |               (only evidence + summary used)   |
   |        +-- google_scholar -> serper.dev/scholar         |
   |        +-- PythonInterpreter / parse_file --------------+
   |        (observation appended as user msg in <tool_response>)
   |
   +-- <answer> found, or budget hit -> forced final answer
   v
prediction + full message trace -> iter{k}.jsonl
```

#### Key components

**LLM providers.** `call_server` hardcodes `http://127.0.0.1:{planning_port}/v1` with `api_key="EMPTY"`, i.e. a local OpenAI-compatible vLLM server; `run_react_infer.sh` launches eight `vllm serve` processes, one per GPU. `requirements.txt` pins `vllm==0.10.1`, `qwen-agent==0.0.26`, `transformers==4.56.1`, `openai==1.99.5`. The README documents a GPU-free path: edit `call_server` to point at OpenRouter and set the model to `alibaba/tongyi-deepresearch-30b-a3b`, uncommenting lines 88-90 so the `reasoning` field is re-wrapped in `<think>` tags. A second, separate model handles page summarisation, and Dashscope handles file and video parsing.

**Search.** Serper only (`SERPER_KEY_ID`), used for both web search (`inference/tool_search.py`, hitting `google.serper.dev/search`) and Google Scholar (`inference/tool_scholar.py`, hitting `google.serper.dev/scholar`). No Tavily, Brave, Exa or SearXNG support.

**Reading stack.** Jina Reader (`JINA_API_KEYS`) plus an LLM extractor. No headless browser, no Playwright, no Crawl4AI in `inference/`. The `WebAgent/NestBrowse` sub-project adds `toolkit/browser.py` and an MCP SSE client (`toolkit/mcp_client.py`, using `mcp.client.sse`); MCP-using code in the repo is scoped to that sub-project, spanning `toolkit/mcp_client.py`, `toolkit/browser.py` and `infer_async_nestbrowse.py`. MCP is also pulled in as a declared dependency outside NestBrowse, via the `qwen-agent[gui,rag,code_interpreter,mcp]` extra in both `WebAgent/WebDancer/requirements.txt` and `WebAgent/WebSailor/requirements.txt`. The released `inference/` harness has no MCP at all.

**Other tools.** `PythonInterpreter` (`inference/tool_python.py`) executes code against ByteDance SandboxFusion endpoints; `parse_file` handles PDF/DOCX/PPTX/XLSX/ZIP/MP4/MP3 via `inference/file_tools/`, with optional Alibaba IDP.

**Memory and state.** The `messages` list, nothing more. No vector store, no scratchpad file, no cross-run memory. Resumability is crude but real: on restart, questions already present in `iter{k}.jsonl` are skipped.

**Structured output.** Tag-based, parsed with string splits, plus `json5` for tool arguments. The extractor is the only JSON-schema-ish contract, and even that is loosely enforced — two of its three requested fields are read, the third ignored.

**Human in the loop.** None.

**Surfaces.** A batch CLI over a dataset file. No API server, no chat interface. Interactive demos exist only in older sub-projects: Streamlit in `WebAgent/WebWalker/src/app.py`, a Gradio `WebUI` class in `WebAgent/WebDancer/demos/gui/web_ui.py`. Hosted demos run on ModelScope Studios, HF Spaces and Bailian.

**Extensibility.** Tools are `qwen_agent` `BaseTool` subclasses decorated with `@register_tool` and listed in `TOOL_CLASS`/`TOOL_MAP` in `react_agent.py`. Adding one means editing both that list and the `<tools>` block in `SYSTEM_PROMPT`, since tool schemas are prompt text rather than API-level tool definitions.

#### Evaluation and benchmarks

The technical report (arXiv 2510.24701) gives ReAct-mode scores with baselines:

| Benchmark | Tongyi DR | OpenAI o3 | DeepSeek-V3.1 |
|---|---|---|---|
| Humanity's Last Exam | 32.9 | 24.9 | 29.8 |
| BrowseComp | 43.4 | 49.7 | 30.0 |
| BrowseComp-ZH | 46.7 | 58.1 | 49.2 |
| GAIA | 70.9 | - | 63.1 |
| xbench-DeepSearch | 75.0 | 67.0 | 71.0 |
| WebWalkerQA | 72.2 | 71.7 | 61.2 |
| FRAMES | 90.6 | 84.0 | 83.7 |

Heavy mode raises HLE to 38.3, BrowseComp to 58.3 and BrowseComp-ZH to 58.1, per the same report. The launch blog reports 32.9 / 43.4 / 46.7 / 75. Evaluation code ships in `evaluation/evaluate_deepsearch_official.py` and `evaluation/evaluate_hle_official.py`.

For DeepResearch Bench, the `WebAgent/WebWeaver` README claims state of the art on DeepResearch Bench, DeepConsult and DeepResearchGym, but the numbers live in images rather than text, so specific values are unverified. An independent harness exists at `texttron/BrowseComp-Plus` (`docs/tongyi.md`), though the page I fetched contained only setup instructions; a reported BrowseComp-Plus figure near 24.9% surfaced in search results but I could not verify it against the source, so treat it as unverified. `FAQ.md` also concedes reproduction difficulty: results hold only with the exact released prompts and tools.

#### Strengths

Best-in-class open weights for long-horizon search, with an Apache-2.0 license on both model and code and no vendor lock-in at inference time. The harness is small enough to read in an afternoon, which makes it an excellent reference for how a trained agent model actually behaves. Batch-search and batch-visit signatures cut round trips. The goal-conditioned extractor is a genuinely good design: context stays clean because pages are compressed by a second model before entering history, and the summariser path is defended by two independent retry loops (progressive truncation for empty responses, plain re-asks for malformed JSON). Budget handling is honest, including the forced-answer path on context overflow rather than a silent crash. Rollout resumability and per-question sticky routing make large evaluations practical. The surrounding WebAgent family is an unusually rich body of published method work.

#### Weaknesses and limitations

The released code is an evaluation harness, not a product: hardcoded `127.0.0.1` ports, hardcoded `./eval_data/file_corpus`, a hardcoded 150-minute limit, no packaging, no tests, no CLI for a single ad hoc question, no server, no UI. Single-vendor tool coupling means Serper plus Jina or nothing. There is no citation machinery at all in the ReAct path, which is a real gap for a "deep research" tool where sourced reports are the deliverable. Output validation is thinner than it looks: `sanity_check_output` exists but is dead code, so nothing checks the reasoning block, and there is dead prompt surface too — the extractor asks for a `rational` field the code never reads. Heavy mode, the configuration behind the headline numbers, is unreleased. Self-hosting the model wants eight GPUs as scripted. `AutoTokenizer.from_pretrained` is called inside `count_tokens` on every round, which reloads the tokenizer per turn. Several bare `except:` clauses swallow tool errors into generic strings. No MCP support in the main inference path. And the repo has been quiet since February 2026, with 92 open issues.

#### Best fit

Right for teams who want strong open weights for hard multi-hop search and are willing to write their own orchestration, and for researchers benchmarking agentic search or studying RL-trained agent behaviour. Wrong for anyone who wants a turnkey report generator with inline citations.

Versus its closest alternatives: against open-source *frameworks* such as LangChain's open_deep_research or GPT Researcher, Tongyi inverts the trade. Those give you a supervisor with parallel sub-agents, pluggable search backends, citations and a UI, but depend on a frontier API model. Tongyi gives you the model and almost no framework. Against Jina AI's node-DeepResearch, another lean loop, Tongyi's differentiator is the purpose-trained weights rather than the scaffold. A practical combination is Tongyi weights served via vLLM behind a framework that supplies the planning, citation and UI layers this repo omits.

#### Sources

- https://github.com/Alibaba-NLP/DeepResearch
- https://api.github.com/repos/Alibaba-NLP/DeepResearch
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/README.md
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/FAQ.md
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/.env.example
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/requirements.txt
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/inference/react_agent.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/inference/run_multi_react.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/inference/run_react_infer.sh
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/inference/prompt.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/inference/tool_search.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/inference/tool_scholar.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/inference/tool_visit.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/evaluation/README.md
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/WebAgent/README.md
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/WebAgent/WebResearcher/README.md
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/WebAgent/WebWeaver/README.md
- https://github.com/Alibaba-NLP/DeepResearch/blob/main/WebAgent/NestBrowse/toolkit/mcp_client.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/WebAgent/AgentFold/infer.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/WebAgent/WebWalker/src/app.py
- https://raw.githubusercontent.com/Alibaba-NLP/DeepResearch/main/WebAgent/WebDancer/demos/gui/web_ui.py
- https://tongyi-agent.github.io/blog/introducing-tongyi-deep-research/
- https://arxiv.org/html/2510.24701v2
- https://huggingface.co/Alibaba-NLP/Tongyi-DeepResearch-30B-A3B
- https://github.com/texttron/BrowseComp-Plus/blob/main/docs/tongyi.md
- https://openrouter.ai/alibaba/tongyi-deepresearch-30b-a3b


### 9. deep-research (dzhng)

Repository: https://github.com/dzhng/deep-research
License: MIT (LICENSE file, "Copyright (c) 2025 David Zhang"); note package.json declares "license": "ISC", an internal inconsistency | Stars: 19.7k (19,654 via GitHub API) as of 2026-09-09 | Language: TypeScript | Pattern: Recursive breadth/depth research tree with parallel fan-out; no ReAct tool loop, no supervisor/sub-agents, no graph runtime
Fact-check: minor-issues, 5 corrections applied

#### Overview

`dzhng/deep-research`, published as "Open Deep Research," is a deliberately minimal deep research agent written in TypeScript. It is maintained by David Zhang (GitHub `dzhng`), who states in the README that the project is created by [Duet](https://duet.so); an April 2026 commit changed that attribution from Aomni to Duet. The stated design constraint is explicit: "provide the simplest implementation of a deep research agent" and "keep the repo size at <500 LoC so it is easy to understand and build on top of."

License is MIT per the `LICENSE` file ("Copyright (c) 2025 David Zhang"). Worth flagging: `package.json` declares `"license": "ISC"`, so the two disagree; the LICENSE file is the operative one. Primary language is TypeScript. As of 2026-09-09 the repo page shows 19.7k stars (API: 19,654), about 2.0k forks, 73 open issues and 21 open pull requests (the API's `open_issues_count` of 94 conflates the two).

Created 2025-02-04, days after OpenAI announced its own Deep Research. There are no published releases or tags at all, so "first release" does not apply; `package.json` is still pinned at version `0.0.1`. The newest commit is 2026-04-11, but it only edits the README. The last functional change was 2025-05-27 ("feat: added API to generate report"), merged 2025-06-07. Maturity: a widely copied reference implementation, effectively feature-frozen. It is not a maintained framework, and 73 open issues against a near-static codebase confirm that.

The real source tree is small but larger than 500 lines: `src/deep-research.ts` (294), `src/ai/text-splitter.ts` (143), `src/run.ts` (120), `src/api.ts` (102), `src/ai/providers.ts` (98), `src/feedback.ts` (28), `src/prompt.ts` (15). The seven source files total 800 lines. Excluding the API server and the text splitter still leaves 555. The "<500 LoC" target is met only by counting the research core alone — `deep-research.ts`, `providers.ts`, `feedback.ts` and `prompt.ts`, 435 lines — and dropping the CLI as well.

#### Workflow architecture

The orchestration pattern is a **recursive breadth/depth research tree with parallel fan-out**. There is no ReAct tool-calling loop, no supervisor with researcher sub-agents, no graph or state-machine runtime, and no RL training. Every LLM call is a single-shot `generateObject` from the Vercel AI SDK against a Zod schema. The agent never chooses a tool; the control flow is hard-coded in one self-recursive async function.

1. **Clarification.** `generateFeedback()` in `src/feedback.ts` asks the model for up to 3 follow-up questions. `src/run.ts` prompts the user via `readline` and concatenates the Q/A pairs into `combinedQuery`. This happens only on the report path; the "answer" path and the HTTP API skip it.
2. **Query generation.** `generateSerpQueries()` in `src/deep-research.ts` returns up to `numQueries` objects, each `{query, researchGoal}`. The `researchGoal` field is the planning artifact: its schema description instructs the model to state the goal, then "go deeper into how to advance the research once the results are found, mention additional research directions." Prior `learnings` are injected so deeper levels produce more specific queries. There is no separate outline or plan step.
3. **Search and reading.** `firecrawl.search(serpQuery.query, {timeout: 15000, limit: 5, scrapeOptions: {formats: ['markdown']}})`. Firecrawl performs SERP retrieval and page-to-markdown scraping in one call, so there is no independent fetcher, browser, or parser in this repo.
4. **Extraction.** `processSerpResult()` truncates each page to 25,000 tokens via `trimPrompt`, concatenates them into `<content>` blocks, and extracts `{learnings[], followUpQuestions[]}` under a 60-second `AbortSignal.timeout`. The prompt demands entities, "exact metrics, numbers, or dates."
5. **Reflection / gap analysis.** There is no dedicated reflection or sufficiency-check step. Gap analysis is folded into that same call: `followUpQuestions` *is* the gap list.
6. **Depth and breadth control.** Purely budgetary, not adaptive. `newBreadth = Math.ceil(breadth / 2)`, `newDepth = depth - 1`. If `newDepth > 0`, the function calls `deepResearch()` on itself with `nextQuery` composed of the prior `researchGoal` plus the follow-up questions. Fan-out is throttled by `pLimit(ConcurrencyLimit)`, where `const ConcurrencyLimit = Number(process.env.FIRECRAWL_CONCURRENCY) || 2` — default 2, overridable only with `FIRECRAWL_CONCURRENCY`, not with the `CONCURRENCY_LIMIT` the README names. The loop cannot stop early on sufficiency and cannot extend on difficulty.
7. **Synthesis.** `writeFinalReport()` wraps every learning in `<learning>` tags and asks for a report "as detailed as possible, aim for 3 or more pages, include ALL the learnings." `writeFinalAnswer()` is the alternate terse mode, returning `exactAnswer` for benchmark-style questions.
8. **Citations.** Weak by construction. Learnings carry no URL provenance, so the report writer cannot attribute claims. `writeFinalReport` simply appends `\n\n## Sources\n\n` plus every `visitedUrl` as a bullet list. Results are deduplicated only at the end via `[...new Set(...)]`.

```
user query + breadth B + depth D
  -> generateFeedback (<=3 questions, CLI answers)  [report mode only]
  -> combinedQuery
  -> deepResearch(query, B, D):
       generateSerpQueries -> [{query, researchGoal}] x B
       pLimit(2) parallel, for each:
            firecrawl.search (limit 5, markdown)
            trimPrompt(25k tok) -> processSerpResult
                 -> learnings[], followUpQuestions[]
            if D-1 > 0:
                 nextQuery = researchGoal + followUpQuestions
                 recurse deepResearch(nextQuery, ceil(B/2), D-1)
            else return {learnings, visitedUrls}
       return dedup(union of subtree results)
  -> writeFinalReport | writeFinalAnswer
  -> append "## Sources" url list -> report.md | answer.md
```

State is nothing but two growing string arrays, `learnings` and `visitedUrls`, threaded down the recursion as function arguments. No vector store, no database, no file-system memory, no resumability.

#### Key components

**LLM providers.** `src/ai/providers.ts` resolves in a fixed precedence: `CUSTOM_MODEL` via any OpenAI-compatible `OPENAI_ENDPOINT`, then Fireworks `accounts/fireworks/models/deepseek-r1` (wrapped in `extractReasoningMiddleware({tagName: 'think'})`), then OpenAI `o3-mini` with `reasoningEffort: 'medium'`. The custom-endpoint path is not an independent third option, though: the client is built as `process.env.OPENAI_KEY ? createOpenAI({...}) : undefined`, and `customModel = process.env.CUSTOM_MODEL ? openai?.(...) : undefined`. With `OPENAI_KEY` unset, `openai` is undefined, `customModel` is undefined no matter what `OPENAI_ENDPOINT` and `CUSTOM_MODEL` say, and `getModel()` falls through to Fireworks or throws "No model found." A dummy `OPENAI_KEY` suffices, but it must be set. The custom-endpoint path otherwise covers OpenRouter, Ollama, LM Studio, and Gemini's compatibility layer. No native Anthropic or Google provider.

**Search and scraping.** Firecrawl only, via `@mendable/firecrawl-js`. `FIRECRAWL_BASE_URL` allows a self-hosted Firecrawl. No Tavily, Serper, Exa, Brave, or DuckDuckGo backend exists in the code, and no headless browser.

**Structured output.** Zod schemas on every call through the AI SDK's `generateObject`, with `structuredOutputs: true` on OpenAI models.

**Context management.** `trimPrompt()` counts tokens with `js-tiktoken` (`o200k_base`) and recursively shortens using a vendored `RecursiveCharacterTextSplitter` in `src/ai/text-splitter.ts`, honoring `CONTEXT_SIZE` (default 128,000).

**Surfaces.** A CLI (`src/run.ts`) and a small Express server (`src/api.ts`) exposing `POST /api/research` and `POST /api/generate-report` on port 3051. No web UI. A `ResearchProgress` type and `onProgress` callback exist for host integrations. No MCP support and no tool-plugin interface; extension means editing the source.

#### Getting started

```bash
git clone https://github.com/dzhng/deep-research.git
cd deep-research
npm install
```

Create `.env.local`:

```bash
FIRECRAWL_KEY="your_firecrawl_key"
OPENAI_KEY="your_openai_key"   # required even for a local model; a dummy value works
CONTEXT_SIZE="128000"
# optional
# FIRECRAWL_BASE_URL="http://localhost:3002"
# FIRECRAWL_CONCURRENCY="2"
# OPENAI_ENDPOINT="http://localhost:11434/v1"
# CUSTOM_MODEL="llama3.1"
# FIREWORKS_KEY="YOUR_KEY"
```

Required keys: Firecrawl, plus either OpenAI or Fireworks. The `CUSTOM_MODEL` / `OPENAI_ENDPOINT` path is not a third independent option — it reuses the same `createOpenAI` client and so still requires `OPENAI_KEY` to be set, which contradicts the README's instruction to comment `OPENAI_KEY` out when using a local LLM. Node 22.x per `engines`.

```bash
npm start          # interactive CLI, writes report.md or answer.md
npm run api        # Express server on port 3051
```

Docker:

```bash
docker compose up -d
docker exec -it deep-research npm run docker
```

Deployment options are just those two. The `Dockerfile` uses `node:18-alpine`, which contradicts the `engines: node 22.x` in `package.json`.

#### Evaluation and benchmarks

There are no official benchmark results. The repo publishes no GAIA, BrowseComp, HLE, DeepResearch Bench, or xbench-DeepSearch numbers, and has no eval harness, though `writeFinalAnswer()` clearly exists to make benchmark-style short answers possible.

One caution about a commonly mis-cited number: the arXiv paper "Improving and Evaluating Open Deep Research Agents" (2508.10152) reports 0% for baseline ODR and 10% for its improved ODR+ on BrowseComp-Small (60 questions), but its ODR baseline is Nick Scamara's `nickscamara/open-deep-research`, cited as "Camara 2025", not this repository. Those figures do not describe dzhng's implementation.

The only independent measurement I found is Langfuse's February 2025 comparison, a single-query run: about 3 minutes 34 seconds, roughly $0.71 in model cost, and a report of about 12,000 characters; Langfuse reports no source count for dzhng's run. By comparison OpenAI Deep Research took about 6 minutes, used about 27 sources, and produced about 87,000 characters. So dzhng's implementation was faster and cheaper in that test but produced far less text.

#### Strengths

The codebase is genuinely readable end to end in one sitting, which is why it became the canonical starting point for forks and ports. Parallel fan-out with a configurable concurrency limit gives real speedups. Depth and breadth are honest, legible knobs rather than opaque "effort" settings. Provider flexibility is decent for a repo this size: any OpenAI-compatible endpoint plus self-hosted Firecrawl means the whole pipeline can run locally, provided you leave a placeholder `OPENAI_KEY` in place so the custom-model branch initializes. Zod-schema outputs make the pipeline reliable and easy to modify. Two output modes, long report and terse answer, cover both use cases. MIT, no telemetry, no framework lock-in, a 74 KB repo.

#### Weaknesses and limitations

Citation quality is the biggest defect: no claim-level attribution, only a flat URL dump, because learnings lose their source when appended to a string array. There is no verification, deduplication of contradictory findings, or source-quality weighting. Budgets are fixed rather than adaptive, so easy questions cost as much as hard ones and hard ones cannot get more effort. Coverage per query is shallow: `limit: 5` results, 25k-token truncation per page, at most 3 learnings extracted. Failures are swallowed by a `catch` that returns empty arrays, so a whole subtree can silently vanish. State is ephemeral, with no checkpointing or resumability on a long run. Human-in-the-loop is one round of up to three questions, CLI-only. No MCP, no tool extensibility, no web UI, no tests (`npm test` exits 1). The `/api/generate-report` handler `return report` instead of sending a response, so that endpoint hangs.

Maintenance is effectively stalled since mid-2025, and the documentation has drifted from the code in at least four places: `package.json` says ISC while `LICENSE` says MIT; the `Dockerfile` pins `node:18-alpine` against `engines: node 22.x`; the README documents `CONCURRENCY_LIMIT` and `OPENAI_MODEL` while the code reads `FIRECRAWL_CONCURRENCY` and `CUSTOM_MODEL`, so both README-documented variables are ignored at runtime; and the README tells local-LLM users to comment out `OPENAI_KEY`, which silently disables the custom-model path entirely. The "<500 LoC" claim is inconsistent with the 800-line source tree on any straightforward reading.

#### Best fit

This is the right choice for engineers who want to understand or fork the deep research loop rather than operate one: teaching, prototyping, embedding a cheap research step in a product, or as a control baseline. It is a poor fit for anyone needing auditable per-claim citations, long-horizon reports, or a maintained platform.

Against its closest alternatives: LangChain's `open_deep_research` offers a supervisor plus parallel researcher sub-agents on LangGraph with checkpointing, multiple search backends, and MCP, at much higher conceptual cost. Nick Scamara's `open-deep-research` is the Next.js/Firecrawl sibling with a real web UI, and is the implementation actually benchmarked in the literature. dzhng's repo wins only on comprehensibility, and it wins there decisively.

#### Sources

- https://github.com/dzhng/deep-research
- https://raw.githubusercontent.com/dzhng/deep-research/main/README.md
- https://raw.githubusercontent.com/dzhng/deep-research/main/LICENSE
- https://raw.githubusercontent.com/dzhng/deep-research/main/package.json
- https://raw.githubusercontent.com/dzhng/deep-research/main/.env.example
- https://raw.githubusercontent.com/dzhng/deep-research/main/Dockerfile
- https://raw.githubusercontent.com/dzhng/deep-research/main/docker-compose.yml
- https://raw.githubusercontent.com/dzhng/deep-research/main/src/deep-research.ts
- https://raw.githubusercontent.com/dzhng/deep-research/main/src/run.ts
- https://raw.githubusercontent.com/dzhng/deep-research/main/src/api.ts
- https://raw.githubusercontent.com/dzhng/deep-research/main/src/prompt.ts
- https://raw.githubusercontent.com/dzhng/deep-research/main/src/feedback.ts
- https://raw.githubusercontent.com/dzhng/deep-research/main/src/ai/providers.ts
- https://raw.githubusercontent.com/dzhng/deep-research/main/src/ai/text-splitter.ts
- https://github.com/dzhng/deep-research/tree/main/src
- https://github.com/dzhng/deep-research/commits/main
- https://github.com/dzhng/deep-research/releases
- https://api.github.com/repos/dzhng/deep-research
- https://langfuse.com/blog/2025-02-20-the-agent-deep-dive-open-deep-research
- https://arxiv.org/abs/2508.10152
- https://arxiv.org/pdf/2508.10152
- https://github.com/nickscamara/open-deep-research
- https://github.com/Finance-LLMs/deep-research-python
- https://rywalker.com/research/deep-research


### 10. Gemini Fullstack LangGraph Quickstart

Repository: https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart
License: Apache-2.0 | Stars: 18,321 (as of 2026-09-09) | Language: Python (backend) with TypeScript/React frontend | Pattern: LangGraph state machine with Send-based parallel search fan-out and a reflection-gated loop (4 nodes, no sub-agents)
Fact-check: minor-issues, 4 corrections applied

#### Overview

Gemini Fullstack LangGraph Quickstart is a reference template published by Google under the `google-gemini` GitHub organization. Its GitHub description reads "Get started with building Fullstack Agents using Gemini 2.5 and LangGraph." It pairs a React/Vite chat UI with a LangGraph agent that generates search queries, runs them through Gemini's built-in Google Search grounding tool, reflects on what it found, loops to close knowledge gaps, and writes a cited answer.

The repository was created on 2025-05-22 and is licensed Apache-2.0 per the root `LICENSE` file and the GitHub API. There is an internal inconsistency worth flagging: `backend/pyproject.toml` declares `license = { text = "MIT" }`. The package author field in that file names Philipp Schmid, who is also the dominant committer (26 of roughly 45 commits across 15 contributors), so in practice this is one Google DevRel engineer's template rather than a staffed product team.

Stars stood at 18,321 with 3,066 forks on 2026-09-09 (GitHub API). There has never been a tagged release; the releases page states "There aren't any releases here." The last commit on `main` is dated 2025-06-18. The `pushed_at` timestamp of 2026-06-14 comes entirely from Dependabot npm branches, not from maintainer work. Meanwhile 77 issues and pull requests are open, with recent ones (for example #221, opened 2026-06-26) unanswered. Maturity level: a polished but frozen demo. The repository contains 51 files in total (git tree for `main`, untruncated), and the agent package is 8 Python files under `backend/src/agent/`: `__init__.py`, `app.py`, `configuration.py`, `graph.py`, `prompts.py`, `state.py`, `tools_and_schemas.py`, and `utils.py`.

#### Workflow architecture

The orchestration pattern is a compiled LangGraph state machine with exactly four nodes and one reflection-gated cycle. There is no supervisor, no sub-agent hierarchy, and no ReAct scratchpad. All of it lives in `backend/src/agent/graph.py`, which builds `StateGraph(OverallState, config_schema=Configuration)` and compiles it as `graph = builder.compile(name="pro-search-agent")`.

Step by step, as implemented:

1. No clarification. The graph's entry edge goes straight from `START` to `generate_query`. There is no interrupt, no clarifying question, no human gate anywhere in the file.
2. No separate planning or outline stage. Query generation is the plan. `generate_query()` builds `ChatGoogleGenerativeAI(model=configurable.query_generator_model, temperature=1.0)`, wraps it with `.with_structured_output(SearchQueryList)`, and fills `query_writer_instructions` from `prompts.py` with the current date, the research topic, and `number_queries`.
3. Fan-out. `continue_to_web_research()` is a conditional edge that returns a list of `Send("web_research", {...})` objects, one per generated query. This is the breadth control: the queries run as parallel branches in the same superstep.
4. Search and reading are one step. `web_research()` bypasses LangChain and calls the raw `google.genai` client: `genai_client.models.generate_content(..., config={"tools": [{"google_search": {}}], "temperature": 0})`. The comment in the code explains why: "the langchain client doesn't return grounding metadata." There is no crawler, no HTML parser, no chunker. Gemini's grounding service does the fetching and summarizing server-side, and the node receives text plus `grounding_metadata`.
5. Citation plumbing. `utils.resolve_urls()` rewrites long `vertexaisearch.cloud.google.com` redirect URLs into short `id/{branch}-{idx}` handles to save tokens; `get_citations()` walks `grounding_metadata.grounding_supports` to recover character spans and chunk titles; `insert_citation_markers()` splices markdown links into the text, sorting by descending end index so earlier offsets stay valid.
6. Reflection and gap analysis. `web_research` fans back in to a single `reflection()` node. It joins all `web_research_result` strings, increments `research_loop_count`, and calls the reflection model with `.with_structured_output(Reflection)`, yielding `is_sufficient`, `knowledge_gap`, and `follow_up_queries`.
7. Depth control. `evaluate_research()` is the second conditional edge and the real loop governor: `if state["is_sufficient"] or state["research_loop_count"] >= max_research_loops: return "finalize_answer"`, otherwise it emits fresh `Send("web_research", ...)` calls for each follow-up query, offsetting each branch id by `number_of_ran_queries` so citation handles stay unique.
8. Synthesis. `finalize_answer()` runs the answer model at `temperature=0` on `answer_instructions`, which demands markdown source links. It then post-processes: for each gathered source whose `short_url` appears in the output, it substitutes the real URL back in and appends that source to `unique_sources`, which both de-duplicates and drops uncited sources.

Text diagram:

```
START
  v
generate_query            (Gemini + SearchQueryList schema)
  v  continue_to_web_research -> Send x N
  +--> web_research #1 --+
  +--> web_research #2 --+     (native google_search grounding tool,
  +--> web_research #N --+      citations spliced in per branch)
                          v
                     reflection   (Reflection schema: is_sufficient,
                          |        knowledge_gap, follow_up_queries)
             evaluate_research
              /                \
   Send -> web_research     finalize_answer -> END
   (loop until is_sufficient or research_loop_count >= max_research_loops)
```

#### Key components

LLM provider: Gemini only. `graph.py` raises `ValueError("GEMINI_API_KEY is not set")` at import time. `configuration.py` sets three role-specific defaults: `query_generator_model="gemini-2.0-flash"`, `reflection_model="gemini-2.5-flash"`, `answer_model="gemini-2.5-pro"`. Note that `web_research()` reuses `query_generator_model` for search, so the UI model picker (which sets `reasoning_model` in state) only changes reflection and final synthesis.

Search provider: exactly one, the `google_search` tool inside Gemini. No Tavily, Brave, SerpAPI or local index. Scraping stack: none, by design; grounding is server-side.

State and memory: `state.py` defines `OverallState` as a TypedDict using `add_messages` for chat and `operator.add` reducers for `search_query`, `web_research_result`, and `sources_gathered`, which is what makes the parallel fan-in work. The `SearchStateOutput` dataclass is defined but never imported by `graph.py`, so it is dead code. There is no long-term memory layer in the repo; persistence comes from the LangGraph platform's Postgres checkpointer in deployment.

Structured output: two Pydantic models in `tools_and_schemas.py`, `SearchQueryList` and `Reflection`. Human-in-the-loop: none. MCP or pluggable tools: none; extending it means editing `graph.py`.

Surfaces: the React UI streams via `useStream` from `@langchain/langgraph-sdk/react` in `frontend/src/App.tsx`, mapping node names to an activity timeline. `InputForm.tsx` exposes an effort selector and a model selector pinned to `gemini-2.0-flash`, `gemini-2.5-flash-preview-04-17`, and `gemini-2.5-pro-preview-05-06`. `App.tsx` translates effort into budgets: low is 1 query and 1 loop, medium 3 and 3, high 5 queries and 10 loops. The API is the standard LangGraph server (`backend/langgraph.json` points at `graph.py:graph`), with `app.py` mounting the built frontend at `/app`. A CLI exists at `backend/examples/cli_research.py`.

#### Getting started

```bash
git clone https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart
cd gemini-fullstack-langgraph-quickstart
# backend: Python 3.11+, only GEMINI_API_KEY is required (backend/.env.example)
cd backend && pip install . && echo 'GEMINI_API_KEY="YOUR_KEY"' > .env
cd ../frontend && npm install
cd .. && make dev        # backend on :2024, UI on http://localhost:5173/app
```

One-off CLI run:

```bash
cd backend
python examples/cli_research.py "What are the latest trends in renewable energy?" \
  --initial-queries 3 --max-loops 2
```

Production uses a multi-stage `Dockerfile` on `langchain/langgraph-api:3.11` plus `docker-compose.yml` with `redis:6` and `postgres:16`. A LangSmith key is required for that path:

```bash
docker build -t gemini-fullstack-langgraph -f Dockerfile .
GEMINI_API_KEY=<key> LANGSMITH_API_KEY=<key> docker-compose up
# app at http://localhost:8123/app/
```

#### Evaluation and benchmarks

None. The repository contains no evaluation harness, no scores, and no benchmark claims, and searches turned up no third-party GAIA, BrowseComp, HLE, DeepResearch Bench, or xbench-DeepSearch result for this codebase. The only nearby number is unrelated: DeepResearch Bench reports Gemini-2.5-Pro Deep Research, Google's hosted product, at 48.88 overall on its RACE framework, which says nothing about this template. Tooling in `backend/pyproject.toml` is thin and lint-only: there is a full `[tool.ruff]` block with `lint.select`, `lint.ignore`, per-file ignores and a pydocstyle convention, but no `[tool.pytest.ini_options]` or any other pytest configuration — `pytest>=8.3.5` appears solely as an entry in the `[dependency-groups]` dev list. The repository has no `tests/` directory either, only `backend/test-agent.ipynb`.

#### Strengths

The graph is small enough to read in one sitting and genuinely teaches the LangGraph fan-out pattern: `Send`-based parallel branches with `operator.add` reducers and a conditional edge as loop governor is the idiom most tutorials get wrong. Citation handling is the standout: rather than trusting the model to cite, it recovers character-level grounding spans from the API and mechanically verifies which sources survived into the final text. Leaning on Gemini's native grounding removes an entire scraping and parsing subsystem, which keeps the graph definition in `graph.py` under 300 lines (293, much of it docstrings); the full agent package is larger but still modest, roughly 730 lines across seven modules, with the citation code in `utils.py` accounting for 166 of them. Setup needs one API key. The streaming activity timeline in the UI makes the loop visible, which is the main thing users want from a research agent. Apache-2.0 and a Google namespace make it safe to fork, and 3,066 forks confirm people do.

#### Weaknesses and limitations

It is unmaintained: no commits to `main` since 2025-06-18, 77 open issues and PRs, no releases. The frontend model IDs are pinned to April and May 2025 preview snapshots, and preview endpoints are retired over time, so new clones can fail on model availability. Architecturally it is a shallow loop, not deep research: no clarification turn, no outline or report plan, no per-source note-taking, no cross-source contradiction handling, and no writer separate from the summarizer. Depth is a raw loop counter with a boolean `is_sufficient` gate. Search is locked to Gemini grounding, so no private corpora, no alternative engines, no control over which pages are read. Provider lock-in is hard-coded at import. There is no human-in-the-loop, no MCP, no tool registry, and no tests. Small defects persist: `SearchStateOutput` is dead code, the UI's model choice never reaches the search node, and `get_citations` derives labels via `chunk.web.title.split(".")[:-1][0]`, which is brittle. `TianhongDai/modular-agent-fullstack` — an independent reimplementation rather than a GitHub fork (the API reports `fork: false` with no parent, created 2025-07-13, 13 stars; its README calls itself an "extended and improved version" of the quickstart) — documents the same structural complaints: heavy LangGraph coupling including for serving frontend components, difficulty adding custom agents, Gemini lock-in, and no clear deployment strategy.

#### Best fit

Best for developers learning LangGraph, for teams already committed to Gemini who want a working cited-answer loop to fork, and for demos where a visible research timeline matters. It is a starting point, not a product: expect to replace the model IDs, add persistence config, and write the planning and report-writing stages yourself. Compared with LangChain's own `open_deep_research`, which is provider-agnostic, has a supervisor with parallel researcher sub-agents and published benchmark results, this template is far simpler and far less capable. Compared with GPT-Researcher, which brings its own scraping and multi-backend search, this one trades that flexibility for a single grounded API call. Pick it for the LangGraph lesson and the citation code; pick one of those two for actual research output.

#### Sources

- https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/README.md
- https://api.github.com/repos/google-gemini/gemini-fullstack-langgraph-quickstart
- https://api.github.com/repos/google-gemini/gemini-fullstack-langgraph-quickstart/languages
- https://api.github.com/repos/google-gemini/gemini-fullstack-langgraph-quickstart/contributors
- https://api.github.com/repos/google-gemini/gemini-fullstack-langgraph-quickstart/commits
- https://api.github.com/repos/google-gemini/gemini-fullstack-langgraph-quickstart/git/trees/main?recursive=1
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/src/agent/graph.py
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/src/agent/state.py
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/src/agent/prompts.py
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/src/agent/configuration.py
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/src/agent/tools_and_schemas.py
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/src/agent/utils.py
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/src/agent/app.py
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/pyproject.toml
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/langgraph.json
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/.env.example
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/backend/examples/cli_research.py
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/frontend/src/App.tsx
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/frontend/src/components/InputForm.tsx
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/LICENSE
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/Dockerfile
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/docker-compose.yml
- https://raw.githubusercontent.com/google-gemini/gemini-fullstack-langgraph-quickstart/main/Makefile
- https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart/commits/main
- https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart/releases
- https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart/issues
- https://huggingface.co/blog/lynn-mikami/google-opensource-deepresearch
- https://github.com/TianhongDai/modular-agent-fullstack
- https://api.github.com/repos/TianhongDai/modular-agent-fullstack
- https://deepresearch-bench.github.io/


### 11. Open Deep Research (LangChain)

Repository: https://github.com/langchain-ai/open_deep_research
License: MIT | Stars: 12.7k (GitHub repo page, 2026-09-09) | Language: Python | Pattern: Supervisor plus parallel researcher sub-agents, built as nested LangGraph state machines
Fact-check: minor-issues, 1 correction applied

#### Overview

Open Deep Research is LangChain's reference deep research agent: a LangGraph application that turns a chat request into a cited Markdown report. It is maintained by the LangChain organization on GitHub, with Lance Martin named as the author in `pyproject.toml` and on PyPI. The license is MIT (`LICENSE` reads "MIT License, Copyright (c) 2025 LangChain"). The primary language is Python, requiring Python 3.10 or newer.

The repository shows 12.7k stars and 1.8k forks on its GitHub page as of 2026-09-09; an independent review published 2026-08-04 quoted 12,520. PyPI shows a first release, `open-deep-research` 0.0.1, on 2025-02-19, and a last release, 0.0.16, on 2025-07-16, which matches the version still pinned in `pyproject.toml`.

The important maturity signal is negative: GitHub displays "This repository was archived by the owner on Aug 21, 2026. It is now read-only." The final commits, dated 2026-08-05 through 2026-08-10, are Dependabot dependency bumps rather than feature work. So the code is mature and battle-tested but frozen. I found no statement in the repository naming a successor project. LangChain's `deepagents` repository is active and much larger, but nothing on its page describes it as replacing Open Deep Research, so treating it as the migration target would be unverified.

#### Workflow architecture

The orchestration pattern is a supervisor with parallel researcher sub-agents, implemented as three nested LangGraph state machines in `src/open_deep_research/deep_researcher.py`. There is no monolithic ReAct loop and no upfront section-by-section outline; the ReAct loops sit inside the leaf agents.

The outer graph, `deep_researcher_builder` (a `StateGraph` over `AgentState`), has four nodes wired as a straight line: `clarify_with_user`, `write_research_brief`, `research_supervisor`, `final_report_generation`.

1. Clarification. `clarify_with_user` runs the research model with `.with_structured_output(ClarifyWithUser)`. If `need_clarification` is true it returns `Command(goto=END)` with the question as an AI message, so the run halts and the user replies in the next turn. Setting `allow_clarification=False` skips the node entirely.
2. Planning. `write_research_brief` collapses the whole message history into a single `ResearchQuestion.research_brief` string. This is the only planning artifact. Notably there is no outline or section plan; the current design deliberately dropped that. Martin's "bitter lesson" post confirms the intent, saying the system will "write the report in one-shot based on the collected context" once the multi-agent research phase has gathered it.
3. Supervision. `supervisor_subgraph` alternates two nodes, `supervisor` and `supervisor_tools`. The supervisor model is bound to exactly three tools: `ConductResearch`, `ResearchComplete`, and `think_tool`. `think_tool` (in `utils.py`) is a no-op that echoes the reflection back, so gap analysis is forced into the transcript rather than a separate node.
4. Query generation and search. There is no query-generation node. Each researcher's `tavily_search` tool takes a `queries: List[str]` argument, so the leaf agent writes its own batch of queries per call.
5. Parallel research. `supervisor_tools` slices `conduct_research_calls[:max_concurrent_research_units]` and fans them out with `asyncio.gather` over `researcher_subgraph.ainvoke`. Overflow calls get an error ToolMessage telling the supervisor to retry with fewer units.
6. Reading and extraction. Inside `tavily_search`, results are fetched with `include_raw_content=True`, deduplicated by URL, truncated to `max_content_length` characters (default 50,000), then each page is summarized in parallel by `summarize_webpage` into a `Summary(summary, key_excerpts)` structured object. The current implementation ships no independent crawler; `beautifulsoup4`, `markdownify`, and `pymupdf` appear in `pyproject.toml` but are not imported by `src/open_deep_research/utils.py`.
7. Depth and breadth control. Three integer budgets in `configuration.py`: `max_concurrent_research_units` (default 5, max 20) for breadth, `max_researcher_iterations` (default 6) for supervisor rounds, and `max_react_tool_calls` (default 10) for each leaf agent's loop. The prompts add softer caps, telling researchers to stop after 5 searches and to "bias towards single agent".
8. Compression. `compress_research` distills one researcher's whole transcript into `compressed_research`, keeping the untouched transcript in `raw_notes`. On a token-limit error it calls `remove_up_to_last_ai_message` and retries, up to three times.
9. Report writing. `final_report_generation` makes a single LLM call over the brief plus all compressed notes. On token overflow it estimates a character budget as `model_token_limit * 4`, then shrinks it 10 percent per retry.
10. Citations. Handled purely by prompt. The Citation Rules block in `prompts.py` instructs the writer to assign each unique URL one number and to end with a `### Sources` section. There is no programmatic verification that a cited URL was actually retrieved.

```
messages
  -> clarify_with_user ---(needs clarification)--> END (asks user)
  -> write_research_brief  [ResearchQuestion.research_brief]
  -> research_supervisor (subgraph)
       supervisor  <-->  supervisor_tools
         think_tool (reflect)      ResearchComplete / iteration cap -> END
         ConductResearch xN -> asyncio.gather over researcher_subgraph
              researcher <--> researcher_tools   (tavily/native search, MCP, think_tool)
                       -> compress_research -> compressed_research + raw_notes
  -> final_report_generation (one call, notes -> report + ### Sources)
  -> END
```

#### Key components

Models come through `init_chat_model` with `configurable_fields`, so any LangChain chat provider supporting tool calling and structured output works. Four roles are configured separately: summarization (`openai:gpt-4.1-mini`), research (`openai:gpt-4.1`), compression (`openai:gpt-4.1`), and final report (`openai:gpt-4.1`). Provider extras installed include OpenAI, Anthropic, Google GenAI and Vertex, AWS, Groq, and DeepSeek.

Search in the current implementation is narrow: the `SearchAPI` enum offers only `tavily`, `openai` (`web_search_preview`), `anthropic` (`web_search_20250305`, `max_uses` 5), and `none`. The legacy `src/legacy/configuration.py` enum is much wider (Perplexity, Exa, arXiv, PubMed, Linkup, DuckDuckGo, Google Search), but those code paths are explicitly described as less performant.

Extensibility runs through MCP. `utils.py` builds tools with `MultiServerMCPClient` from `langchain_mcp_adapters`, configured by `MCPConfig(url, tools, auth_required)`, with a Supabase-backed OAuth token path (`get_mcp_access_token`, `fetch_tokens`) for authenticated servers.

State is LangGraph-native: `AgentState`, `SupervisorState`, and `ResearcherState` in `state.py`, using a custom `override_reducer` so a node can replace rather than append to a list. There is no vector store or cross-session memory. Structured output is Pydantic-based (`ClarifyWithUser`, `ResearchQuestion`, `ConductResearch`, `ResearchComplete`, `Summary`).

Human-in-the-loop is limited to the clarification turn; the current graph uses no LangGraph `interrupt`. The legacy workflow implementation is the one described as offering plan approval and feedback.

Surfaces: LangGraph Studio and the local LangGraph server (`langgraph.json` exposes one graph, "Deep Researcher", plus auth at `src/security/auth.py`), hosted LangGraph Platform, and Open Agent Platform at oap.langchain.com for non-technical configuration. `pyproject.toml` defines no console script, so there is no first-party CLI.

#### Getting started

```bash
git clone https://github.com/langchain-ai/open_deep_research.git
cd open_deep_research
uv venv
source .venv/bin/activate
uv sync
cp .env.example .env
```

`.env.example` asks for `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `TAVILY_API_KEY`, LangSmith keys, and Supabase values needed only for Open Agent Platform. With defaults you need at minimum an OpenAI key and a Tavily key.

```bash
uvx --refresh --from "langgraph-cli[inmem]" --with-editable . --python 3.11 langgraph dev --allow-blocking
```

That serves the API on `http://127.0.0.1:2024` and opens Studio. Deployment options are LangGraph Platform or a self-hosted Open Agent Platform instance.

#### Evaluation and benchmarks

Only Deep Research Bench (100 expert-written tasks, 50 English and 50 Chinese, across 22 fields), scored by the RACE LLM-as-judge metric. The README table reports RACE 0.4943 with GPT-5 as the research model, 0.4401 with Claude Sonnet 4 at $187.09, 0.4309 for the gpt-4.1 defaults at $45.98 and 58M tokens, and 0.4344 for the official submission at $87.83 and 207M tokens. That submission placed 6th on 2025-08-02. Note the project brief's claim that it "tops the DR Bench open leaderboard" is not supported. Lance Martin's own post is more modest: the system "scores a 43.5 on deep research bench (top 10), which is not bad for a small open source effort" — that "(top 10)" is a position on the overall leaderboard, not first place and not a ranking restricted to open-source projects. A Hugging Face blog reports NVIDIA AI-Q later reaching first place. No GAIA, BrowseComp, HLE, or xbench numbers are reported.

#### Strengths

Genuinely readable orchestration: roughly 720 lines in one file, with every budget and prompt exposed. Per-role model selection makes cost tuning easy, and the published cost and token figures per configuration are unusually honest. Context isolation per sub-agent plus compression keeps the writer's prompt manageable, and MCP support means enterprise data sources plug in without touching the graph. The archived-but-documented pairing with a free LangChain course and a from-scratch companion repo makes it excellent teaching material.

#### Weaknesses and limitations

The repository is archived and read-only as of 2026-08-21, so no upstream fixes. Search is effectively Tavily or a provider's native web search; the broader backend list lives only in the legacy code. Citation correctness is prompt-enforced, never verified. Token accounting is brutal: 207M tokens for a 100-task run. `supervisor_tools` swallows every exception in its research fan-out with `if is_token_limit_exceeded(...) or True`, ending the research phase silently on any error. The token-limit recovery paths truncate findings by raw character count, which can drop late sources. There is no persistent memory, no PDF or non-HTML reading in the current path, and no CLI.

#### Best fit

Best for teams that want to read and own an orchestration layer rather than consume a product: a fork-and-modify baseline for a domain research assistant, especially where MCP access to internal systems matters, and for engineers learning multi-agent context engineering. It is a poor pick for anyone needing supported software or many search backends out of the box. Against GPT-Researcher, Open Deep Research is more configurable per role but less batteries-included and now unmaintained; against STORM, it skips the outline-first stage in favor of writing the report in one shot from the collected context, which the maintainers argue produces less disjointed reports. Anyone starting fresh in the LangChain ecosystem today should compare against the actively maintained `deepagents` harness before building on an archived repository.

#### Sources

- https://github.com/langchain-ai/open_deep_research
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/README.md
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/LICENSE
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/pyproject.toml
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/langgraph.json
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/.env.example
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/src/open_deep_research/deep_researcher.py
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/src/open_deep_research/configuration.py
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/src/open_deep_research/state.py
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/src/open_deep_research/prompts.py
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/src/open_deep_research/utils.py
- https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/src/legacy/configuration.py
- https://github.com/langchain-ai/open_deep_research/commits/main
- https://github.com/langchain-ai/open_deep_research/tree/main/tests
- https://github.com/langchain-ai/open_deep_research/tree/main/examples
- https://pypi.org/pypi/open-deep-research/json
- https://www.langchain.com/blog/open-deep-research
- https://rlancemartin.github.io/2025/07/30/bitter_lesson/
- https://www.digitalapplied.com/blog/open-source-deep-research-agents-2026-guide
- https://huggingface.co/blog/nvidia/how-nvidia-won-deepresearch-bench
- https://github.com/Ayanami0730/deep_research_bench
- https://github.com/langchain-ai/deepagents


### 12. PaperQA2

Repository: https://github.com/Future-House/paper-qa
License: Apache-2.0 | Stars: 9,182 (as of 2026-09-09) | Language: Python | Pattern: Single ReAct-style tool-selection loop over an aviary Gym-like Environment (ToolSelector agent), plus optional deterministic "fake" path and RL-trainable ldp agents
Fact-check: major-issues, 5 corrections applied

#### Overview

PaperQA2 is a Python package for high-accuracy retrieval augmented generation over scientific documents: PDFs, text files, Microsoft Office documents and source code files. It is maintained by FutureHouse (the `Future-House/paper-qa` GitHub org; the LICENSE file carries "Copyright 2024 FutureHouse"), and the project's documentation site now resolves to `docs.edisonscientific.com`. License is Apache-2.0. Primary language is Python, requiring Python 3.11+.

GitHub stars: 9,182 as of 2026-09-09, with 917 forks. The first PyPI release, `0.0.1`, was uploaded 2023-02-05; 169 releases exist. Version 5, the release the authors brand "PaperQA2," first appeared as `5.0.0a1` on 2024-08-29. In December 2025 the project switched from SemVer to calendar versioning; the README explains this was to decouple git tags from publication terminology and explicitly removes backwards-compatibility guarantees across releases. The most recent release is `v2026.08.12` (2026-08-12), and the newest commit on `main` is dated 2026-08-12.

Maturity is high for a research-lab artifact: a stable CLI, bundled tuned configurations, four separately versioned PDF-reader subpackages under `packages/` (`paper-qa-pypdf`, `paper-qa-pymupdf`, `paper-qa-docling`, `paper-qa-nemotron`), and two peer-reviewed-style publications behind it. The caveat is the deliberate ZeroVer stance: pinning is on the user.

#### Workflow architecture

The orchestration pattern is a single ReAct-style tool-selection loop, not a plan-and-execute graph and not a supervisor with parallel sub-agents. Concretely, PaperQA2 wraps its state in a Gym-like environment from FutureHouse's `aviary` library and hands an LLM a flat tool list; the LLM picks tools until it calls a terminator.

The environment is `PaperQAEnvironment(Environment[EnvironmentState])` in `src/paperqa/agents/env.py`. `reset()` builds `EnvironmentState` (holding a `Docs` object and a `PQASession`) plus the tool list from `settings_to_tools()`, and returns one seed message rendered from `env_reset_prompt` in `src/paperqa/prompts.py`: "Use the tools to answer the question: {question} ... you can terminate by calling the {complete_tool_name} tool ... The current status of evidence/papers/cost is {status}". `step()` executes the requested tool calls with `concurrency=True` and marks `done` when a `complete` tool response appears, or when `answer.max_answer_attempts` is exceeded.

The loop itself is `run_aviary_agent()` in `src/paperqa/agents/main.py`: a `while not done` loop that appends observations to a `ToolSelectorLedger`, asks the `aviary` `ToolSelector` for an action (retried up to 5 times on `MalformedMessageError`), steps the environment, and increments a timestep counter against `agent.max_timesteps`. `agent_type` defaults to `"ToolSelector"` (`src/paperqa/settings.py`). Two alternatives exist: `run_fake_agent()`, a deterministic path, and `run_ldp_agent()`, which runs an `ldp` `Agent` through a `RolloutManager` with callbacks, the hook for RL training.

Tools are defined in `src/paperqa/agents/tools.py`. `DEFAULT_TOOL_NAMES` is `paper_search`, `gather_evidence`, `gen_answer`, `reset`, `complete`. There is also an optional `ClinicalTrialsSearch` tool with a full ClinicalTrials.gov query DSL in its docstring.

Mapping to the requested pipeline stages:

- Clarification: none. There is no user-facing clarification turn.
- Planning/outline: no explicit plan artifact. Planning is implicit in tool choice, steered by tool docstrings ("invoke this tool when just beginning or when unsatisfied with the current evidence"; "Aim for at least five pieces of evidence from multiple sources before invoking this tool").
- Query generation: the agent LLM writes `paper_search(query, min_year, max_year)` calls. In the `fake` agent, `litellm_get_search_query(question, llm, count=3)` seeds exactly three queries.
- Search: `PaperSearch.paper_search` queries a **local** tantivy full-text index, not a web search engine (`src/paperqa/agents/search.py`, `SearchIndex` wrapping `tantivy.Index`). `agent.search_count` defaults to 8. Repeated identical queries are treated as pagination via a `previous_searches` offset dict. External network calls are for metadata enrichment, not discovery: `DEFAULT_CLIENTS` in `src/paperqa/clients/__init__.py` is Crossref, Semantic Scholar and a journal-quality post-processor, with OpenAlex, Unpaywall and a retraction post-processor in `ALL_CLIENTS`.
- Reading/extraction: `src/paperqa/readers.py` (`read_doc`, `chunk_pdf`, `chunk_text`, `chunk_code_text`, `parse_office_doc`, `html2text` for HTML). Chunks are embedded and added by `state.docs.aadd_texts`.
- Evidence extraction and re-ranking: `GatherEvidence.gather_evidence(question, state)` temporarily swaps the session question, calls `Docs.aget_evidence` (`src/paperqa/docs.py`), which retrieves `answer.evidence_k` chunks (default 10) and runs `map_fxn_summary` concurrently to produce a contextual summary plus a relevance score per chunk. Under the default JSON summary path (`prompts.use_json=True`) that score is 0-10; the 1-10 range applies only to the legacy non-JSON `summary_prompt`. `answer.evidence_relevance_score_cutoff` defaults to 1, so score-0 contexts are dropped. This is the "RCS" (LLM-based re-ranking and contextual summarization) the README advertises. Only `agent.agent_evidence_n` contexts (default 1) are shown back to the agent, keeping the loop's context small.
- Reflection/gap analysis: emergent, driven by the status string `make_status()` returns after every tool: `Paper Count=… | Relevant Papers=… | Current Evidence=… | Current Cost=$…`. The agent reads those counters and decides whether to search more, gather more, or answer. `Reset` clears all contexts when the agent keeps failing.
- Depth and breadth control: budgets rather than a planner. `agent.timeout` (default 500s), `agent.max_timesteps`, `answer.evidence_k`, `answer.answer_max_sources` (default 5), `answer.max_concurrent_requests` (default 4), plus per-model rate limits.
- Synthesis: `GenerateAnswer.gen_answer` calls `Docs.aquery`, which renders `qa_prompt`. The tool returns `f"{answer} | {status}"`, and may fail, "indicating that better or different evidence should be found."
- Citation handling: contexts are keyed (`pqac-`-prefixed IDs). `qa_prompt` requires citation keys at sentence ends, and `CITATION_KEY_CONSTRAINTS` in `prompts.py` lists valid and invalid formats explicitly, forbidding "Author et al. (2023)". A `CANNOT_ANSWER_PHRASE` sentinel ("I cannot answer") propagates to `complete(has_successful_answer=False)`.

Text diagram:

```
question
   |
[PaperQAEnvironment.reset] -> EnvironmentState{Docs, PQASession} + tools + reset prompt
   |
   v
 +--------------- ToolSelector loop (run_aviary_agent) ---------------+
 |  agent_llm sees messages + status counters, emits ToolRequestMessage
 |     |
 |     +-> paper_search  -> tantivy local index -> metadata clients -> chunk+embed -> Docs
 |     +-> gather_evidence -> retrieve evidence_k -> per-chunk LLM summary+score (RCS)
 |     +-> gen_answer     -> Docs.aquery -> qa_prompt -> cited answer
 |     +-> reset          -> clear contexts
 |     +-> complete(has_successful_answer) -> done
 |  env.step() runs calls concurrently; loop breaks on complete / max_timesteps / timeout
 +--------------------------------------------------------------------+
   |
   v
AnswerResponse (session + status) -> indexed into the "answers" tantivy index
```

#### Key components

LLM providers: everything LiteLLM supports. Defaults are `gpt-4o-2024-11-20` for `llm`, `summary_llm`, `agent.agent_llm` and `parsing.enrichment_llm`, with `text-embedding-3-small` for embeddings. Local serving via llamafile or Ollama is documented, as are `SentenceTransformerEmbeddingModel`, a `SparseEmbeddingModel`, and hybrid embeddings.

Search providers: a local tantivy full-text index is the retrieval substrate; metadata comes from Crossref, Semantic Scholar, OpenAlex, Unpaywall, journal-quality and retraction post-processors. Optional ClinicalTrials.gov search. There is no built-in general web search.

Reading stack: pluggable `parsing.parse_pdf`, whose default is resolved at runtime by `get_default_pdf_parser()`, which prefers `paperqa_pymupdf.parse_pdf_to_pages` and falls back to `paperqa_pypdf.parse_pdf_to_pages` (an ImportError if neither is installed); Docling and Nvidia nemotron-parse are opt-in via `parsing.parse_pdf`. Alongside that: `unstructured`-based Office parsing; `html2text`; code chunking. Multimodal is on by default (`parsing.multimodal=True`), including LLM enrichment of figures, tables and equations.

Memory and state: `EnvironmentState` plus a `Docs` vector store (NumPy by default, `QdrantVectorStore` optionally), and a persistent `~/.pqa/` home containing the paper index and an `answers` index queryable via `pqa search`.

Structured output: Pydantic throughout; `prompts.use_json=True` by default for evidence summaries, with retry on invalid JSON.

Human-in-the-loop: none in the loop. Extensibility comes from `agent.callbacks` keyed on tool lifecycle events, `on_env_reset_callback` / `on_agent_action_callback` / `on_env_step_callback`, custom `tool_names`, and a swappable `env_class`.

Surfaces: the `pqa` CLI (`ask`, `search`, `index`, `view`, `save`), the Python API (`ask`, `agent_query`, `Docs.aquery`), and bundled configs (`high_quality`, `fast`, `wikicrow`, `contracrow`, `debug`, `tier1_limits`). No MCP server and no HTTP server ship in this repo; `ldp`'s `HTTPAgentClient` is supported as an agent type.

#### Getting started

```bash
pip install paper-qa>=5
export OPENAI_API_KEY=sk-...
# recommended for 100+ papers, to dodge public rate limits
export CROSSREF_API_KEY=...
export SEMANTIC_SCHOLAR_API_KEY=...
```

Put PDFs in a directory, then from that directory:

```bash
pqa ask 'What is PaperQA2?'
pqa --settings high_quality ask 'Are there nm scale features in thermoelectric materials?'
pqa -i nanomaterials index          # named, reusable index
pqa -i 'answers' search 'contextual summarization'
```

Library form:

```python
from paperqa import Settings, ask

answer_response = ask(
    "What is PaperQA2?",
    settings=Settings(agent={"index": {"paper_directory": "my_papers"}}),
)
```

Deployment is library or CLI on your own machine; state lives in `PQA_HOME` (default `~/.pqa/`). No container or hosted service is documented in the repo.

#### Evaluation and benchmarks

None of the general deep-research benchmarks (GAIA, BrowseComp, HLE, DeepResearch Bench, xbench-DeepSearch) are reported. The evaluations are literature-specific:

- LitQA2, the multiple-choice benchmark introduced in the paper (248 questions in arXiv:2409.13740; the publicly released LAB-Bench split used by third parties is 199 questions, per AstaBench Table 23): PaperQA2 reached 85.2% +/- 1.1% precision and 66.0% +/- 1.2% accuracy (n=3), versus human experts at 64.3% +/- 15.2% precision and 63.1% +/- 16.0% accuracy (n=8), a statistically significant precision win (t(7.2)=3.86, p=0.0029). Sources: arXiv:2409.13740, arXiv:2510.21652.
- Contradiction detection: 2.34 +/- 1.99 contradictions per paper on a random subset of biology papers, 70% validated by human experts (arXiv:2409.13740 abstract).
- Summarization: WikiCrow, built on PaperQA2, had 13.5% "cited and unsupported" statements versus 24.9% for paired Wikipedia articles, and fewer reasoning errors (12 vs 26), at $4.48 +/- $1.02 per article.
- RAG-QA Arena science split (1,404 questions over 1.7M documents): FutureHouse reports PaperQA2 scoring 12.4% higher than the closest competing system, announced 2025-03-05. The absolute score is not given on that page.

Those four are first-party. Independent numbers do exist, however. AstaBench (arXiv:2510.21652) benchmarks PaperQA2 indirectly: it evaluates FutureHouse Crow, an agent built on PaperQA2, and Table 23 gives independent LitQA2 retrieval scores for PaperQA2 (recall 69.9, recall@30 62.8), essentially matching Ai2's own PaperFinder (70.3 / 64.3). AstaBench also notes that PaperQA2 ships without a retrieval corpus, so the authors had to use FutureHouse's hosted API. The independent figures are broadly consistent with the first-party accuracy claim (66.0 for PaperQA2 versus 72.0 for Crow on a LitQA2 subset).

#### Strengths

Citation discipline is the standout: every answer sentence must carry context keys, the prompt enumerates invalid citation styles, and unsupported answers route to an explicit "unsure" terminal state rather than a confident guess. The two-stage retrieval (embedding recall, then per-chunk LLM summarization and 0-10 relevance scoring, with score-0 contexts dropped by the default cutoff of 1) is a genuine accuracy mechanism, not framing. Cost is visible to the agent in-loop via the status string, which is unusually honest engineering. The codebase is small, framework-light (Pydantic plus LiteLLM, explicitly no LangChain), and heavily configurable through one `Settings` tree. Bundled configs encode the exact hyperparameters used in the publications. The `ldp` integration means the loop is trainable, not just promptable. And the retrieval quality holds up outside the lab: Ai2's AstaBench measures PaperQA2's LitQA2 recall at parity with their own PaperFinder.

#### Weaknesses and limitations

It does not find papers for you. `paper_search` hits a local tantivy index; the README's own answer to "Where do I get papers?" is "it's probably best to just download PDFs of papers you think will help." That is a very different product from a web-browsing deep-research agent. AstaBench makes the same observation from the outside: PaperQA2 ships no retrieval corpus, so evaluating it required FutureHouse's hosted API. There is no clarification step, no explicit plan or outline artifact, and no dedicated report-length synthesis stage; the default `answer_length` is "about 200 words, but can be longer," so long-form output is permitted but not orchestrated. Parallelism is limited: `gather_evidence` carries a TODO noting the question swap "prevents us from supporting parallel calls," and `complete` has a documented race condition if called twice concurrently. Reflection is a counter string rather than a critique step. CalVer plus removed compatibility guarantees means upgrades can break configs. Cost is real at $1-$3 per query by the authors' own accounting. Benchmarks remain mostly self-reported and centered on biology, with AstaBench the main independent cross-check.

#### Best fit

Right for researchers, librarians and R&D teams who already hold a corpus (a Zotero library, an internal PDF archive, a downloaded arXiv slice) and need answers with auditable per-sentence citations. It is also a good base for domain agents: WikiCrow and ContraCrow are shipped as configs, and the callback plus custom-tool surface is clean.

Wrong for open-web research questions. Compared with GPT Researcher or open-source Deep Research clones, which start from a web search API and produce long reports, PaperQA2 inverts the tradeoff: much stronger grounding and citation verification, far weaker discovery and no long-form outline. Compared with LlamaIndex or LangChain, whose comparison the README addresses directly, PaperQA2 is not a framework but an opinionated, tuned pipeline with scientific-metadata plumbing (journal quality, retraction checks, DOI resolution) that a generic RAG stack would have to build. A pragmatic combination is a web or Semantic Scholar harvester upstream feeding PDFs into PaperQA2's index.

#### Sources

- https://github.com/Future-House/paper-qa
- https://raw.githubusercontent.com/Future-House/paper-qa/main/README.md
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/agents/main.py
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/agents/env.py
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/agents/tools.py
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/agents/search.py
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/settings.py
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/prompts.py
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/docs.py
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/readers.py
- https://raw.githubusercontent.com/Future-House/paper-qa/main/src/paperqa/clients/__init__.py
- https://github.com/Future-House/paper-qa/releases
- https://github.com/Future-House/paper-qa/tree/main/packages
- https://github.com/Future-House/paper-qa/commits/main.atom
- https://pypi.org/pypi/paper-qa/json
- https://arxiv.org/abs/2409.13740
- https://arxiv.org/html/2409.13740v1
- https://arxiv.org/pdf/2510.21652
- https://www.futurehouse.org/research-announcements/paperqa2-achieves-sota-performance-on-rag-qa-arena-science-benchmark
- https://docs.edisonscientific.com/paperqa


### 13. Local Deep Research

Repository: https://github.com/LearningCircuit/local-deep-research
License: MIT | Stars: 9,061 (2026-09-09) | Language: Python | Pattern: Pluggable strategies: default LangGraph/LangChain tool-calling lead agent with parallel researcher subagents, plus alternative fixed iterative search pipelines
Fact-check: minor-issues, 5 corrections applied

#### Overview

Local Deep Research (LDR) is a self-hosted, privacy-first deep research application: you ask a question, it runs iterative multi-engine search across the web, academic databases and your own documents, and returns a cited summary or a full structured report. It is maintained by the GitHub user LearningCircuit, with HashedViking and djpetti listed as co-authors in `pyproject.toml`, plus a large contributor pool and community channels on Discord and r/LocalDeepResearch. License is MIT (copyright 2025 LearningCircuit). Primary language is Python (requires-python `>=3.12,<3.15`), with a Jinja2 + Socket.IO web frontend.

The repository was created 2025-02-09 and had 9,061 stars, 811 forks and 841 open issues when I checked the GitHub API on 2026-09-09; the last push to `main` was the same day, so it is actively developed. First PyPI release was 0.1.0 on 2025-03-18; the latest of 161 releases is 1.10.7 (2026-08-28). Maturity is high for a community project: 30+ search engine integrations, Alembic migrations, an unusually deep CI security posture (CodeQL, Semgrep, OSV-Scanner, Trivy, Cosign-signed images with SLSA provenance and SPDX SBOMs), and a documented release gate. The large open-issue count and an explicitly "experimental" chat mode temper that.

#### Workflow architecture

There is no single pipeline. `create_strategy()` in `src/local_deep_research/search_system_factory.py` dispatches on a strategy name to one of several implementations in `advanced_search_system/strategies/`; `AdvancedSearchSystem.analyze_topic()` in `search_system.py` is the entry point that all surfaces (FastAPI web worker, programmatic API, news scheduler) call. The two architectures that matter:

**1. Default: `langgraph-agent` (supervisor + parallel researcher subagents).** `LangGraphAgentStrategy.analyze_topic()` in `strategies/langgraph_agent_strategy.py` builds a tool list via `_build_tools()`, composes a system prompt, and calls LangChain's `create_agent(model, tools, system_prompt)` to get a tool-calling agent, then consumes `agent.stream(..., stream_mode="updates")` under a `recursion_limit` of `max_iterations * 2 + 1` (default `max_iterations` 50, floor 10). There is no clarification turn: the prompt explicitly says "Do NOT ask clarifying questions". Planning, query generation, engine selection and the decision to stop are all left to the model inside the loop, which is why the file's own comment says the agent "needs many more cycles than pipeline strategies". Tools are `web_search` (the user's primary engine), `search_<engine>` specialized tools loaded by `_load_specialized_engine_tools()`, `fetch_content` for page reading, and `research_subtopic`. Depth and breadth come from `research_subtopic` (`_make_research_subtopic_tool`): the lead passes 2 to 5 subtopics (hard limit 10, surplus queued), each is researched by a fresh `create_agent()` subagent with its own tool set in a `ThreadPoolExecutor`, with a 1800-second per-task deadline. The pool size is not fixed: `MAX_SUBAGENT_WORKERS = 4` is only the fallback default when the user has not set `langgraph_agent.max_subagent_workers`, and `_coerce_max_subagent_workers` clamps whatever the user sets to the range 1–32 (values above 32 are clamped down with a warning, values below 1 are raised to 1). Subagents cannot recurse (`research_subtopic` is excluded from `sub_tools`). All results funnel into a lock-protected `SearchResultsCollector` that assigns stable `[N]` indices and de-duplicates by canonical URL and snippet. `_finalize()` then runs the citation pass; `_synthesize_from_collector()` is a fallback synthesis if the agent was cut short.

**2. Pipeline: `focused-iteration` (fixed plan-and-execute loop).** `FocusedIterationStrategy.analyze_topic()` runs a bounded `for iteration in range(1, self.max_iterations + 1)` loop (defaults: 8 iterations, 5 questions per iteration). Each pass calls `self.question_generator.generate_questions(...)` with the current knowledge summary and prior questions, executes them in parallel via `ProgressiveExplorer.explore()` or `_execute_parallel_searches()`, accumulates results with no filtering, and after iteration 3 adds verification searches from `explorer.suggest_next_searches()`. Reflection here is implicit in the question generator seeing `_get_current_knowledge_summary()`, not a separate critic node. Final synthesis is `self.citation_handler.analyze_followup(query, results, previous_knowledge, nr_of_links)`.

Citations are handled by `citation_handler.py`, which delegates to one of three implementations in `citation_handlers/`: `StandardCitationHandler`, `ForcedAnswerCitationHandler` (benchmark mode) or `PrecisionExtractionHandler`. Both strategies pass a citation offset so numbering stays continuous across multiple calls. Long reports go through `IntegratedReportGenerator.generate_report()` in `report_generator.py`, which is genuinely plan-and-execute: `_determine_report_structure()` prompts the LLM for a `STRUCTURE ... END_STRUCTURE` table of contents, `_research_and_generate_sections()` runs fresh research per section, and `_format_final_report()` assembles the document.

Text diagram of the default flow:

```
query
  |
AdvancedSearchSystem.analyze_topic()
  |
create_strategy("langgraph-agent")
  |
LangGraphAgentStrategy.analyze_topic()
  |
create_agent(model, tools, system_prompt)   <-- LangChain/LangGraph tool-calling loop
  |
  +-> web_search(query)            -> SearchResultsCollector [N]
  +-> search_arxiv / search_pubmed -> SearchResultsCollector
  +-> fetch_content(url, focus)    -> ContentFetcher -> extracted text
  +-> research_subtopic([t1..t5])
  |        |
  |        +-- ThreadPoolExecutor (default 4 workers, user-settable 1-32; 30 min/task)
  |            subagent(t1) ... subagent(t5)   (own create_agent, no recursion)
  |                    |
  |                    +-> shared SearchResultsCollector
  |
  (agent decides: search more / delegate / answer)
  |
_finalize() -> CitationHandler -> cited answer + ## Sources
  |
[report mode] IntegratedReportGenerator: TOC -> per-section research -> final report
```

#### Key components

LLM providers: Ollama (native API), LM Studio and llama.cpp `llama-server` (OpenAI-compatible), any OpenAI-compatible endpoint including vLLM, an Anthropic-Messages-compatible endpoint, plus OpenAI, Anthropic, Google Gemini, OpenRouter and Requesty. Dependencies confirm `langchain-ollama`, `langchain-openai`, `langchain-anthropic` on `langchain~=1.2`.

Search providers: arXiv, PubMed, Semantic Scholar, Wikipedia, SearXNG, DuckDuckGo, GitHub, Elasticsearch, Wayback Machine, The Guardian, Wikinews for free tiers; Tavily, Brave, Google via SerpAPI or Programmable Search for paid; plus local document collections, a personal Library, and any LangChain retriever (FAISS, Chroma, Pinecone, Weaviate, Elasticsearch). The `auto` and `parallel` meta engines were removed because the langgraph-agent picks engines per query.

Reading stack: `ContentFetcher` behind `build_fetch_tool()` in `advanced_search_system/tools/fetch/`, with three modes (`full`, `summary_focus`, `summary_focus_query`, or disabled). Extraction libraries pinned in `pyproject.toml`: trafilatura, justext, readabilipy, extruct, newspaper4k, beautifulsoup4, crawl4ai and playwright for JS rendering, pdfplumber/pypdf/unstructured for documents. Robots.txt is respected and no anti-detection is used.

State and memory: per-user SQLCipher AES-256 databases keyed from the user's password (login works by attempting decryption), 20+ SQLAlchemy models, Alembic migrations, sentence-transformers plus faiss-cpu for the indexed Library, and a `settings_snapshot` threaded through strategies. Egress is governed by an `EgressScope` enum with six members, not three: the default is ADAPTIVE, which simply follows the primary engine and resolves to PRIVATE_ONLY, PUBLIC_ONLY or BOTH; STRICT narrows the run to the single primary engine; PUBLIC_ONLY and PRIVATE_ONLY are the explicit one-sided modes; and UNPROTECTED is an operator-gated escape hatch (`LDR_POLICY_ALLOW_UNPROTECTED_EGRESS=true`) that turns scope filtering off entirely, though hard SSRF and cloud-metadata blocking still applies underneath it. Whatever scope resolves, it filters which tools exist for that run and is mirrored into the prompt, so the model is told what it may reach.

Structured output is mostly prompt-parsed rather than schema-enforced (the report TOC is parsed from a delimited text block). Human-in-the-loop is limited: no clarification turn, but there is a `followup_research/` service, an experimental multi-turn Chat mode, and a Stop control checked at named termination points. Surfaces: FastAPI + Socket.IO web UI on port 5000 (`ldr-web`), authenticated REST API, `LDRClient`/`quick_summary()` Python API, an `ldr-mcp` MCP server exposing `search`, `quick_research`, `detailed_research`, `generate_report`, `analyze_documents` and config tools, and Apprise notifications. Note the standalone `ldr` CLI was removed; the benchmark CLI is invoked as a module.

#### Getting started

Docker Compose is the recommended path:

```bash
curl -O https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/docker-compose.yml && docker compose up -d
```

Docker run on native Linux, bringing your own Ollama and SearXNG:

```bash
docker run -d -p 11434:11434 --name ollama ollama/ollama
docker exec ollama ollama pull gpt-oss:20b
docker run -d -p 8080:8080 --name searxng searxng/searxng
docker run -d --network host --name local-deep-research \
  --volume "deep-research:/data" -e LDR_DATA_DIR=/data \
  -e LDR_SEARCH_ENGINE_WEB_SEARXNG_DEFAULT_PARAMS_INSTANCE_URL=http://localhost:8080 \
  localdeepresearch/local-deep-research
```

pip:

```bash
pip install local-deep-research
python -m local_deep_research.web.app   # web UI on http://localhost:5000
pip install "local-deep-research[mcp]"  # adds the ldr-mcp server
```

No API key is required for a fully local stack (Ollama plus SearXNG). Cloud providers need their own keys, set per user in the encrypted DB or as `LDR_*` env vars such as `LDR_LLM_PROVIDER` and `LDR_LLM_OPENAI_API_KEY`. `llm.model` has no default since 1.6.3, so you must pick a model. Requires an AVX-capable x86-64 CPU or ARM64; deployment options include Docker, Compose with an NVIDIA GPU override, pip, and Unraid.

#### Evaluation and benchmarks

LDR ships its own harness (`src/local_deep_research/benchmarks/`, `docs/BENCHMARKING.md`) with dataset modules for SimpleQA, BrowseComp and xbench-DeepSearch, plus a custom-dataset template; there is no top-level `benchmarks/` directory in the repo root (the root has `community_benchmark_results/`). Results are collected in a community dataset on Hugging Face. The README headline table, using `langgraph-agent` with Serper and local Ollama models, reports Qwen3.6-27B at 95.7% SimpleQA (287/300) and 77.0% xbench-DeepSearch (77/100); Qwen3.5-9B at 182/200 and 59.0%; gpt-oss-20B at 295/346. Two of those percentages do not match their own counts: 182/200 is 91.0% but is printed as 91.2%, and 295/346 is 85.3% but is printed as 85.4% — the `accuracy_pct` column of the leaderboard CSV disagrees with the `correct`/`total` columns in the same row, and the README table inherits the error. The README's headline prose also claims "~95% SimpleQA (n=500)" while the 95.7% row is n=300; the actual n=500 run is a separate, lower row at 94.8%. The Hugging Face leaderboard shows SimpleQA runs spanning 73.1% to 95.7% at n=30 to 500, two xbench-DeepSearch runs (59% and 77%, n=100), and no populated BrowseComp results. `focused_iteration_strategy.py`'s docstring claims 96.51% SimpleQA with 8 iterations, 5 questions per iteration and GPT-4.1 Mini.

The caveats are stronger than "self-reported with grader noise". On the leaderboard CSV, the two headline runs quoted above were graded by the model under test: the 95.7% (287/300) SimpleQA row and the 77.0% (77/100) xbench row both carry `evaluator_model=qwen3.6:latest, evaluator_provider=ollama`, and the 91.0% qwen3.5:9b and 85.3% gpt-oss:20b rows are likewise self-graded. That is self-evaluation, and it departs from the project's own documented default grader — `docs/BENCHMARKING.md` specifies Claude 3.7 Sonnet via OpenRouter, with a stated mis-grade rate around 1%. Independence is also thinner than "community-submitted" suggests: every headline row carries `contributor=LearningCircuit`, and only two of the ten SimpleQA rows come from non-maintainer contributors. Samples are small, SimpleQA contamination risk is real, and none of this is independent evaluation. No GAIA, HLE, DeepResearch Bench or independently audited scores exist. Third-party coverage (Medium, Korben, YouTube reviews, a BSAIL Lab academic write-up by contributor djpetti) is qualitative, not benchmarked.

#### Strengths

Genuine local-first operation: the whole loop can run on Ollama plus SearXNG with nothing leaving the machine, and the project states it has no telemetry. Breadth of search backends is unmatched among self-hosted research tools, especially the academic set plus a journal-quality scoring system over OpenAlex, DOAJ and predatory-journal lists. Security engineering is far above hobby-project norms: per-user SQLCipher encryption, egress scopes that actually filter the agent's tool list, signed images with SBOMs, and a dozen scanners in CI. Strategy pluggability lets you trade cost for depth, and the compounding Library plus LangChain retriever support turns it into a personal RAG system. Many delivery surfaces (web, REST, Python, MCP, scheduled news digests) and detailed self-reported local-model benchmarks that, taken with the grading caveats above, still help narrow the field before downloading weights.

#### Weaknesses and limitations

No clarification step at all, by design, so an ambiguous query is answered rather than negotiated. Depth control in the default strategy is a recursion limit and a subagent pool size rather than an explicit budget; that pool defaults to 4 workers and is user-configurable up to 32 via `langgraph_agent.max_subagent_workers`, against a preferred batch of 5 subtopics, so the default is conservative but not a ceiling. Reflection and gap analysis are implicit in prompts, not separate verification nodes, and the code contains candid comments about known failure modes (a citation pass skipped when a subsection call collects no new sources; Runnable transforms escaping the `<think>`-stripping wrapper). Structured output relies on text parsing of LLM responses. 841 open issues and a very fast release cadence suggest churn: the `mcp` and `agentic` strategies were removed, meta engines were removed, the `ldr` CLI was removed, and `docs/features.md` still lists strategies the factory no longer implements. The dependency list is enormous, which is a real operational and supply-chain surface despite the scanning. Benchmarks are self-reported, maintainer-submitted and in the headline cases self-graded, with internal inconsistencies between counts and printed percentages. Chat mode is experimental and quick-mode only. Docker `--network host` quick start silently breaks on Docker Desktop.

#### Best fit

Best for privacy-constrained researchers who must keep queries and documents off third-party servers: academics and clinicians leaning on arXiv, PubMed, Semantic Scholar and journal-quality filtering; journalists and lawyers with sensitive subjects; and homelab or self-hosting users who already run Ollama or LM Studio and want an agentic layer plus an encrypted personal library on top. It is also a reasonable local research backend for Claude Desktop or Claude Code via its MCP server. It is a poor fit if you want a hosted service, a hardened API-first product with schema-guaranteed output, or state-of-the-art performance on hard browsing benchmarks.

Closest alternatives: LangChain's own `open_deep_research`, which is a much smaller and cleaner LangGraph supervisor implementation that is easier to read and embed but ships no UI, no encrypted multi-user storage and no academic search breadth; and GPT Researcher, which produces comparable cited reports with a simpler planner-and-executor design and better cloud-provider polish, but weaker local-first guarantees and no per-user encryption or private-document library. Pick LDR when privacy, academic sources and owning your own indexed corpus matter more than architectural minimalism.

#### Sources

- https://github.com/LearningCircuit/local-deep-research
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/README.md
- https://api.github.com/repos/LearningCircuit/local-deep-research
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/pyproject.toml
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/src/local_deep_research/advanced_search_system/strategies/langgraph_agent_strategy.py
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/src/local_deep_research/advanced_search_system/strategies/focused_iteration_strategy.py
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/src/local_deep_research/search_system_factory.py
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/src/local_deep_research/search_system.py
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/src/local_deep_research/citation_handler.py
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/src/local_deep_research/report_generator.py
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/src/local_deep_research/advanced_search_system/tools/fetch/__init__.py
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/src/local_deep_research/security/egress/policy.py
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/docs/egress-modes.md
- https://github.com/LearningCircuit/local-deep-research/tree/main/src/local_deep_research/advanced_search_system/strategies
- https://github.com/LearningCircuit/local-deep-research/tree/main/src/local_deep_research/benchmarks/datasets
- https://github.com/LearningCircuit/local-deep-research/tree/main/src/local_deep_research/followup_research
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/docs/architecture.md
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/docs/architecture/OVERVIEW.md
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/docs/features.md
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/docs/search-engines.md
- https://raw.githubusercontent.com/LearningCircuit/local-deep-research/main/docs/BENCHMARKING.md
- https://huggingface.co/datasets/local-deep-research/ldr-benchmarks
- https://huggingface.co/datasets/local-deep-research/ldr-benchmarks/raw/main/leaderboards/simpleqa.csv
- https://github.com/LearningCircuit/ldr-benchmarks
- https://pypi.org/pypi/local-deep-research/json
- https://www.reddit.com/r/LocalLLaMA/comments/1t1n6o8/we_are_finally_there_qwen3627b_agentic_search_957/
- https://news.ycombinator.com/item?id=43330164


### 14. MiroThinker

Repository: https://github.com/MiroMindAI/MiroThinker
License: Apache-2.0 | Stars: 8,371 (GitHub API, 2026-09-09; repo page rounds to 8.4k) | Language: Python | Pattern: RL/mid-trained end-to-end model driving a single ReAct tool loop (optional supervisor + browsing sub-agent), with recency-based context compression and episode-level retry
Fact-check: minor-issues, 3 corrections applied

#### Overview

MiroThinker is an open-weight deep research agent family plus the harness needed to run it, published by the MiroMind team (GitHub org `MiroMindAI`). The GitHub description calls it "a deep research agent optimized for complex research and prediction tasks." The repository is Apache-2.0, Python, and as of 2026-09-09 the GitHub API reports 8,371 stars, 643 forks, 91 watchers and 2 open issues. It was created 2025-08-07; the newest commit on `main` is dated 2026-03-23 (the API's `pushed_at` is 2026-07-06). There are no GitHub releases and only one branch (`main`) — versioning happens through Hugging Face model collections instead. The release train is v0.1 (2025-08-08), v0.2 (2025-09-08), v1.0 (2025-11-13), v1.5 (2026-01-05) and 1.7 (2026-03-11). Two technical reports back it: arXiv 2511.11793 for v1.0 and arXiv 2603.15726 for 1.7 and the proprietary H1. A companion framework repo, MiroFlow (Apache-2.0, ~3.1k stars), and a hosted product at dr.miromind.ai round out the family. Maturity is high for a research artifact: 14 benchmark harnesses under `apps/miroflow-agent/conf/benchmark/` (aime2025, browsecomp, browsecomp_zh, deepsearchqa, frames, futurex, gaia-validation, gaia-validation-text-103, hle, hle-text-500, hle-text-2158, seal-0, webwalkerqa, xbench_deepsearch) with 15 `run_evaluate_multiple_runs_*.sh` runner scripts in `scripts/`, one of which is a debug runner, plus a Gradio demo, a trace visualizer, LobeHub tool-parser glue, and a Discord community. FutureX is the odd one out: it has a config and a runner but no `benchmarks/check_progress/` module, and is scored via `benchmarks/evaluators/extract_futurex_results.py`. It is not a packaged product; there is no PyPI package, no Docker compose, no semantic-version tags.

#### Workflow architecture

The important thing to understand is that MiroThinker puts almost nothing in the scaffold. The pipeline is a **single ReAct loop driven by a model that was RL/mid-trained to do the planning itself**. There is no clarification turn, no outline stage, no separate query-generation or reflection module, no explicit breadth/depth controller. Those behaviors are supposed to be learned weights, not framework code. The 1.7 paper describes it as "a dual-loop structure: an outer episode loop that handles trajectory-level restarts, and an inner step loop that drives reasoning, tool invocation, and observation."

The outer loop is a clean-slate restart under 1.7. `benchmarks/common_benchmark.py:296` sets `max_format_retries = self.context_compress_limit`, and each retry re-initializes the agent with the original query alone — the paper's §3.1 puts it as "C_0^(e) = {q}, e>1 ... effectively discarding all information from the preceding trajectory. This clean-slate restart avoids any bias from a potentially degraded context." The code does contain a failure-experience mechanism that would prepend a structured "=== Previous Attempts Analysis ===" block (`FAILURE_EXPERIENCE_HEADER` at `src/utils/prompt_utils.py:27`), and `retry_with_summary` defaults to True, but both shipped 1.7 configs (`mirothinker_1.7_keep5_max200.yaml:23` and `..._max300.yaml:23`) set it to False. That flag gates the only two call sites that produce a failure summary (`answer_generator.py:517` and `:580`), so under the 1.7 setup the summary is always None and the header is never appended. Treat that mechanism as belonging to the v1.0/v1.5-era configs.

The inner loop is `Orchestrator.run_main_agent` in `apps/miroflow-agent/src/core/orchestrator.py` (~1200 lines, the loop starts at line 736). Per turn it calls `AnswerGenerator.handle_llm_call`, parses XML-style `<use_mcp_tool>` blocks, executes them through `ToolManager.execute_tool_call`, appends observations via `llm_client.update_message_history`, and then calls `ensure_summary_context` to check whether there is still room for a final summary. Three guard mechanisms are worth naming because they are the real engineering: `_handle_response_format_issues` rolls back a turn when the model emits malformed MCP tags or refusal phrases; `_check_duplicate_query` / `ToolExecutor.is_duplicate_query` roll back repeated searches; and `ToolExecutor.should_rollback_result` rolls back on empty search results. All three are capped by `MAX_CONSECUTIVE_ROLLBACKS = 5`.

Context management is the distinctive part. `keep_tool_result: 5` (see `conf/agent/mirothinker_1.7_keep5_max200.yaml` and `src/llm/base_client.py`) keeps only the K most recent tool observations while preserving the complete thought/action trace. The README calls this "recency-based context retention" and argues it frees context for longer trajectories without hurting accuracy.

Synthesis is a single forced summarization turn, not an iterative writer. `AnswerGenerator.generate_and_finalize_answer` appends the prompt from `generate_agent_summarize_prompt(agent_type="main")`, which demands a `\boxed{}` answer of "as few words as possible" — this is a benchmark-answer harness, not a report writer. Citations appear only in the demo surface: `apps/gradio-demo/prompt_patch.py` monkey-patches the summarizer to produce Markdown with `[ID]` in-text citations and a References section.

Multi-agent mode exists but is legacy. `conf/agent/multi_agent.yaml` defines an `agent-browsing` sub-agent, `expose_sub_agents_as_tools` in `src/config/settings.py` publishes it to the main agent as a tool named `search_and_browse` taking a single `subtask` string, and `Orchestrator.run_sub_agent` runs its own bounded loop then summarizes with the `agent-browsing` prompt. The README marks this configuration as for v0.1/v0.2 only; 1.7 configs set `sub_agents:` empty.

```
task (fixed in main.py / passed by benchmark runner)
   |
   v
[episode loop]  benchmarks/common_benchmark.py
   |   retries up to context_compress_limit times; under 1.7 each
   |   retry is a clean-slate restart from the original query alone
   |   (retry_with_summary: False, so no "Previous Attempts Analysis")
   v
[step loop]  Orchestrator.run_main_agent  (max_turns 200-300)
   |
   +-> LLM turn (thought + one <use_mcp_tool> call)
   |      |
   |      +-> google_search (Serper) | scrape_and_extract_info (Jina + summary LLM)
   |      |   | run_python_code (E2B) | vqa / transcribe / reasoning / reader
   |      |
   |      +-> rollback if: malformed tags | duplicate query | empty results
   |
   +-> observation appended; only last K=5 kept
   +-> context-budget check (ensure_summary_context)
   |
   v
final summarization turn -> \boxed{answer}  (or Markdown + [n] citations in demo)
   |
   v
LLM-as-a-Judge scoring (benchmarks/evaluators)
```

#### Key components

**LLM providers**: `src/llm/factory.py` hard-codes `SUPPORTED_PROVIDERS = {"anthropic", "openai", "qwen"}`, mapped to two clients (`AnthropicClient`, `OpenAIClient`). Shipped configs are `claude-3-7`, `gpt-5`, `qwen-3`. The intended path is self-hosting a MiroThinker checkpoint behind SGLang or vLLM and pointing `llm=qwen-3 llm.base_url=...` at it. Open weights: MiroThinker-1.7-mini (30B) and MiroThinker-1.7 (235B), 256K context, 300 tool calls; earlier v1.0 came in 8B/30B/72B on Qwen3 and Qwen2.5 bases.

**Search**: Serper (Google) via `google_search` in `dev_mcp_servers/search_and_scrape_webpage.py`, plus `sogou_search` through the Tencent Cloud SDK for Chinese queries (blacklisted in the 1.7 config). Legacy `searching_google_mcp_server.py` and `searching_sogou_mcp_server.py` also exist.

**Reading stack**: `dev_mcp_servers/jina_scrape_llm_summary.py` scrapes via Jina Reader (`r.jina.ai`), falls back to direct Python scraping, then runs a cheap "summary LLM" to answer the caller's `info_to_extract` question — so the agent never sees raw HTML. Optional `tool-reading` uses MarkItDown; `browser_session.py` exists in `mcp_servers/`.

**Everything else**: code execution and file handling in an E2B sandbox (`python_mcp_server.py`); VQA, transcription and heavy-reasoning tools in both commercial (Claude, OpenAI) and open-source (Qwen2.5-VL-72B, Whisper-large-v3-turbo, Qwen3-235B-Thinking) variants; a `task_planner` dev MCP server offering `add_todo` / `list_todos` / `complete_todo` / `delete_todo`, though no shipped 1.7 config enables it.

**State**: no vector store or persistent memory. State is the message history plus `TaskLog` JSON traces, which double as SFT/DPO training data (`apps/collect-trace`). **Structured output**: `\boxed{}` extraction. **Human-in-the-loop**: none in the agent loop. **Surfaces**: Hydra CLI (`apps/miroflow-agent/main.py`), Gradio demo, a Flask trace viewer (`apps/visualize-trace`), and a LobeHub tool parser. Extensibility is entirely MCP: add a server entry in `settings.py` and list it in a YAML config.

#### Getting started

```bash
git clone https://github.com/MiroMindAI/MiroThinker
cd MiroThinker/apps/miroflow-agent
uv sync
cp .env.example .env
```

Minimal keys: `SERPER_API_KEY`, `JINA_API_KEY`, `E2B_API_KEY`, plus `SUMMARY_LLM_BASE_URL` / `SUMMARY_LLM_MODEL_NAME` / `SUMMARY_LLM_API_KEY`. `OPENAI_API_KEY` is additionally required for LLM-as-a-Judge scoring and for pre-processing GAIA's image/audio files.

Serve the weights, then run:

```bash
python3 -m sglang.launch_server --model-path miromind-ai/MiroThinker-1.7-mini \
  --tp 4 --dp 1 --host 0.0.0.0 --port 61002 --trust-remote-code

cd apps/miroflow-agent
uv run python main.py llm=qwen-3 agent=mirothinker_1.7_keep5_max200 \
  llm.base_url=http://localhost:61002/v1
```

The question is hard-coded at `main.py` line 32. Deployment options include SGLang (recommended), vLLM, llama.cpp/Ollama with community GGUF quants (Q4 runs the 30B MoE in ~16GB VRAM per the Gradio README), or the hosted dr.miromind.ai.

#### Evaluation and benchmarks

From the 1.7 paper's Table 1 (arXiv 2603.15726): MiroThinker-1.7-mini scores 67.9 BrowseComp / 72.3 BrowseComp-ZH / 80.3 GAIA / 36.4 HLE / 57.2 xbench-DeepSearch; MiroThinker-1.7 scores 74.0 / 75.3 / 82.7 / 42.9 / 62.0. The proprietary MiroThinker-H1 reaches 88.2 / 84.4 / 88.5 / 47.7 / 72.0, plus 73.9 on FinSearchComp (T2/T3). Read the README headline carefully: the "88.2 on BrowseComp" it opens with is H1, which has no released weights. Earlier releases: v1.5-235B at 39.2 HLE-Text, 69.8 BrowseComp, 71.5 BrowseComp-ZH, 80.8 GAIA-Val-165; v1.0-72B at 37.7 / 47.1 / 55.6 and 81.9 GAIA-Text-103; v0.2 at 17.8 HLE, 17.2 BrowseComp-EN, 29.4 BrowseComp-ZH, 56.0 xbench-DeepSearch, 74.8 Frames. MiroThinker-72B-Preview placed 4th on FutureX for the week of 2025-09-11. Every number is self-reported; I found no independent third-party reproduction. To their credit, the team documents contamination controls: Hugging Face datasets/spaces are blocked at the tool layer (`_is_banned_url`, `_is_huggingface_dataset_or_space_url`) and v1.5 trajectories were canary-string tested. DeepResearch Bench itself is not reported, but §7.4 / Table 3 of the 1.7 paper evaluates long-form report generation on 50 DeepResearchEval-derived queries, where MiroThinker-H1 scores 78.0 overall — the highest among the 11 agents compared, ahead of ChatGPT-5.4 Deep Research and Gemini-3.1-Pro Deep Research — with MiroThinker-1.7 at 77.5 and MiroThinker-1.7-mini at 76.9, scored on a separate factual-grounding axis as well.

#### Strengths

Genuinely open weights under Apache-2.0 at 30B and 235B, with published training data (MiroVerse), traces, and evaluation harnesses — reproducibility is unusually good. The 30B MoE (3B active) is small enough to self-host, and the reported scores are competitive with commercial deep research products. Recency-based context retention is a clean, well-argued idea. The rollback machinery (format errors, duplicate queries, empty results) is the kind of thing you only write after watching many real failures. Fourteen benchmark harnesses with LLM-as-a-Judge and progress monitors (13 of the 14 have a `check_progress` module) make it a serious evaluation platform.

#### Weaknesses and limitations

The scaffold gives you very little if you do not run their weights: no clarification, no outline, no reflection loop, no citation handling outside the Gradio patch. Report generation is not a gap in the models — the paper's own long-report evaluation puts H1 first among the agents it compares — but it is a gap in this repository: the open-source harness only ever emits a `\boxed{}` short answer, and long-form report generation is exercised through dr.miromind.ai rather than through `apps/miroflow-agent`. Only three LLM provider paths exist, and the models are text-only — multimodal inputs require GPT-4o pre-processing. Search is effectively Serper-only, scraping Jina-only, code E2B-only; all three are paid third-party services, and swapping them means editing `settings.py`. The task is hard-coded in `main.py`; there is no server API. `main` has not moved since 2026-03-23, and the README still carries stale cross-references (a "v1.5" section that recommends 1.7 configs). The best-performing system, H1, is closed.

#### Best fit

Best for researchers and engineers who want a SOTA-class browsing agent running on their own GPUs, and for anyone benchmarking search agents on GAIA/BrowseComp/HLE. It is a poor fit for teams who want a hosted API, or who want a citation-rich narrative report generator out of this repository specifically — the models are evidently capable of long-form reports, but the open harness does not produce them; for that you are pointed at dr.miromind.ai. Against its closest alternatives: MiroFlow (same org) is the framework-first sibling with more orchestration and less model, so pick MiroFlow if you want to drive GPT-5 or Claude and MiroThinker if you want open weights; Alibaba's WebSailor/WebDancer line is the nearest open-weight competitor, and MiroThinker's own tables show it well ahead on GAIA and BrowseComp. Against LangChain-style open-deep-research scaffolds, MiroThinker trades workflow flexibility and out-of-the-box report plumbing for raw browsing accuracy.

#### Sources

- https://github.com/MiroMindAI/MiroThinker
- https://raw.githubusercontent.com/MiroMindAI/MiroThinker/main/README.md
- https://api.github.com/repos/MiroMindAI/MiroThinker
- https://api.github.com/repos/MiroMindAI/MiroThinker/commits
- https://api.github.com/repos/MiroMindAI/MiroThinker/releases
- https://github.com/MiroMindAI/MiroThinker/tree/main/apps/miroflow-agent/conf/benchmark
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/miroflow-agent/src/core/orchestrator.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/miroflow-agent/src/core/pipeline.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/miroflow-agent/src/core/answer_generator.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/miroflow-agent/src/utils/prompt_utils.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/miroflow-agent/src/config/settings.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/miroflow-agent/src/llm/factory.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/miroflow-agent/conf/agent/mirothinker_1.7_keep5_max200.yaml
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/miroflow-agent/conf/agent/multi_agent.yaml
- https://github.com/MiroMindAI/MiroThinker/blob/main/libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/task_planner.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/gradio-demo/prompt_patch.py
- https://github.com/MiroMindAI/MiroThinker/blob/main/apps/gradio-demo/README.md
- https://arxiv.org/abs/2511.11793
- https://arxiv.org/abs/2603.15726
- https://arxiv.org/html/2603.15726v1
- https://github.com/MiroMindAI/MiroFlow
- https://dr.miromind.ai/
- https://huggingface.co/collections/miromind-ai/mirothinker-17
- https://www.prnewswire.com/news-releases/miromind-team-unveils-mirothinker-1-7--mirothinker-h1-a-new-era-of-verification-centric-heavy-duty-research-agents-302714500.html (launch press release, located via search; benchmark figures above are cited from the arXiv paper instead)


### 15. WebThinker

Repository: https://github.com/RUC-NLPIR/WebThinker
License: MIT | Stars: 1,467 (as of 2026-09-09) | Language: Python | Pattern: Single-generation interleaved reasoning loop with special-token tool interception, an auxiliary-LLM tool layer, a nested Deep Web Explorer sub-loop, and optional online-DPO-trained weights
Fact-check: minor-issues, 5 corrections applied

#### Overview

WebThinker is a research codebase from RUC-NLPIR, the Gaoling/NLP-IR group at Renmin University of China, published alongside the NeurIPS 2025 paper "WebThinker: Empowering Large Reasoning Models with Deep Research Capability" (arXiv 2504.21776, first authors Xiaoxi Li, Jiajie Jin, Guanting Dong; contact xiaoxi_li@ruc.edu.cn). It is released under the MIT License and written in Python (repo `language: Python`). The GitHub API reports 1,467 stars and 139 forks as of 2026-09-09, with 9 open issues and 2 open pull requests (the API's `open_issues_count` of 11 lumps them together). The repository was created 2025-03-28 and the README dates the full code release to 2025-03-31. There are no git tags and no GitHub releases, so there is no versioned first release; the latest commit is db387eb, 2025-12-08, a README edit. The repo homepage is a Notion project page, and four fine-tuned checkpoints are published on Hugging Face under `lixiaoxi45` (WebThinker-QwQ-32B, WebThinker-R1-7B/14B/32B).

Maturity is best described as a research artifact rather than a product. It is a set of standalone scripts plus a Streamlit demo, with `requirements.txt` pinning `torch==2.5.1`, `transformers==4.46.1`, `vllm==0.6.4`. There is no package, no automated test suite or test runner configuration, no CI, and no Dockerfile; the only test-named files are a manual web-parser smoke script (`scripts/utils/test_webparser.py`) and vendored LiveCodeBench code (`scripts/lcb_runner/benchmarks/test_output_prediction.py`, `scripts/lcb_runner/pyext/pyext-0.7/test/test_pyext.py`, plus a `setup.py` inside that vendored `pyext` package). Thirty-two compiled `.pyc` files are committed under `__pycache__` directories. Activity has been quiet since late 2025.

#### Workflow architecture

The orchestration pattern is deliberately not a graph or a supervisor-with-subagents design. It is a single-generation interleaved loop: one reasoning model produces a continuous chain of thought, and the harness intercepts special tokens it emits, executes the corresponding tool, splices the result back into the same prompt, and resumes generation in completion mode. The paper calls this the Autonomous Think-Search-and-Draft strategy. A second "auxiliary" instruct model implements every tool that requires language work. An optional third layer is model-side: the released checkpoints were trained with iterative online DPO on tool-use trajectories.

Report mode lives in `scripts/run_web_thinker_report.py`. `process_single_sequence` (line 433) is the driver. Step by step:

1. There is no clarification turn. The question goes straight to planning: `get_search_plan_instruction` (in `scripts/prompts/prompts_report.py`) asks the auxiliary model for a numbered plan of at most 8 steps.
2. `get_report_webthinker_instruction(question, plan)` builds the system prompt, declaring four tools as token pairs: `<|begin_search_query|>`, `<|begin_write_section|>`, `<|begin_check_article|>`, `<|begin_edit_article|>`.
3. The reasoning model is called with `stop=[END_SEARCH_QUERY, END_WRITE_SECTION, END_EDIT_ARTICLE, BEGIN_CHECK_ARTICLE]`, so generation halts exactly at a tool call. The `while not seq['finished']` loop dispatches on which stop token was hit.
4. Query generation is entirely the model's; the harness only dedupes (`seq['executed_search_queries']`) and rejects queries under 6 characters or placeholders like `"your query here"`.
5. On a search, the auxiliary model first writes a "detailed search intent" (`get_search_intent_instruction`), then `bing_web_search_async` or `google_serper_search_async` runs, top-k results (default 10) are fetched in parallel by `fetch_page_content_async`, and `extract_snippet_with_context` windows each page around the search snippet. The window size is set at lines ~733-741: the top 5 results get 10,000 characters when the page was deep-read (the `read_web_page` flag) and 4,000 characters otherwise, while results ranked 6 and below always get 2,000 characters — so only the 2,000-char tier is rank-driven.
6. Depth comes from `generate_deep_web_explorer` (line 227), a nested sub-loop over the same or auxiliary model that can issue further `<|begin_search_query|>` calls and `<|begin_click_link|>` calls on any URL it saw. Clicked pages are summarized by the auxiliary model via `get_click_web_page_reader_instruction`. The sub-loop is capped at `MAX_INTERACTIONS = 10` and `MAX_TOKENS = 20000`, and returns only the text after `**Final Information**`, cut out by `extract_answer_fn(analysis, mode='research')`.
7. Reflection and gap analysis are not separate stages; they happen as ordinary chain-of-thought between tool calls, which is the paper's central claim.
8. Writing is incremental. On `<|begin_write_section|>` the harness parses "section name\ntask", retrieves the top 3 relevant pages from `document_memory` using a BM25Okapi index rebuilt after each search, and has the auxiliary model draft the section (`get_write_section_instruction`). `<|begin_check_article|>` returns only the markdown header outline (`re.findall(r'^#{1,4}\s+.*$', ...)`) and folds the previous check block to save context; a title is generated if missing. `<|begin_edit_article|>` sends the whole article to the auxiliary model for rewriting. After the loop, `get_final_report_instruction` does one structure-only pass.
9. Citation handling: there is effectively none. `get_write_section_instruction`, `get_search_plan_instruction` and the RAG baseline prompt all say "No need to mention citations or references" / "Do not add citations or references", and the 30 shipped WebThinker sample reports in `outputs/glaive.qwq.webthinker/` contain no URLs or reference lists. The "cited report" framing is not supported by the code.

Problem-solving mode (`scripts/run_web_thinker.py`) is the same machinery minus the writing tools, with `--max_search_limit` (default 20) and no planning step; it uses `get_multiqa_search_o1_instruction`.

```
question
  -> aux LLM: search plan (<=8 steps)
  -> reasoning LLM (single continuous generation)
       |-- <|begin_search_query|> -> aux: intent -> Bing/Serper -> parallel fetch
       |        -> Deep Web Explorer sub-loop (<=10 searches+clicks, 20k tok)
       |             search / <|begin_click_link|> -> aux: page reader
       |        -> "**Final Information**" spliced back as <|begin_search_result|>
       |-- <|begin_write_section|> -> BM25 top-3 docs -> aux: draft -> article
       |-- <|begin_check_article|> -> header outline injected back
       |-- <|begin_edit_article|> -> aux: full-article rewrite
       (loop until EOS, 80 interactions, or 50k tokens)
  -> aux: final structure pass -> markdown report
```

#### Key components

Models: any OpenAI-compatible endpoint via `AsyncOpenAI`, configured as two separate base URLs (`--api_base_url`, `--aux_api_base_url`). Defaults are QwQ-32B as reasoner and Qwen2.5-32B-Instruct as auxiliary, served with vLLM; the scripts also load local tokenizers with `AutoTokenizer`, so a tokenizer path is mandatory. vLLM LoRA adapters can be hot-loaded (`load_lora_adapter`/`unload_lora_adapter`). Search: Bing Web Search v7 or Google Serper, selected by `--search_engine` (`scripts/search/bing_search.py`). Reading stack: `aiohttp` plus BeautifulSoup with lxml, `pdfplumber` for PDFs, optional Jina Reader (`--use_jina`, `r.jina.ai`), and a fallback `WebParserClient` that POSTs URLs to a local `/parse_urls` service the README suggests backing with Crawl4AI; `WebParserClient_url` is `None` by default so that fallback is off until edited. A manual smoke script for that parser service ships as `scripts/utils/test_webparser.py`. Memory and state: per-run in-process dicts (`search_cache`, `url_cache`), the growing prompt string itself, `document_memory` plus a rebuilt BM25 index, and a `RateLimiter`. Structured output is regex extraction between literal markers (`extract_between`, `extract_markdown_content`), not JSON schemas or function calling. Human-in-the-loop: none beyond typing the question. Surfaces: CLI scripts and a Streamlit demo (`demo/run_demo.py`, configured in `demo/settings.py`); no HTTP API, no MCP, no plugin interface. Evaluation helpers ship in `scripts/evaluate/evaluate.py` and `evaluate_report.py` (listwise LLM judging).

#### Getting started

```bash
conda create -n webthinker python=3.9 && conda activate webthinker
pip install -r requirements.txt
```

You need a Serper or Bing key, plus two served models (vLLM is assumed) and local tokenizer paths. Report mode:

```bash
python scripts/run_web_thinker_report.py \
    --single_question "What are the models of OpenAI and what are the differences?" \
    --search_engine "serper" --serper_api_key "YOUR_KEY" \
    --api_base_url "YOUR_API_BASE_URL" --model_name "QwQ-32B" \
    --aux_api_base_url "YOUR_AUX_API_BASE_URL" --aux_model_name "Qwen2.5-32B-Instruct" \
    --tokenizer_path "PATH" --aux_tokenizer_path "PATH"
```

The demo:

```bash
cd demo && streamlit run run_demo.py
```

Note that the README's own snippet for this step reads `streamlit run_demo.py`, which is missing the `run` subcommand and will fail; Streamlit's CLI requires `streamlit run <script>`.

Optional extras: `--use_jina --jina_api_key`, `--concurrent_limit 32`, `--lora_name/--lora_path`. Deployment is self-host only.

#### Evaluation and benchmarks

From the paper (arXiv 2504.21776v1 HTML), WebThinker-32B-RL versus Search-o1-32B: GPQA 70.7 vs 67.2, GAIA 48.5 vs 39.8, WebWalkerQA 46.5 vs 34.1, HLE 15.8 vs 10.8 (HLE table also lists o3-mini Medium at 11.1). The relative-gain percentages come from the paper's results discussion (Section 4.4, arXiv:2504.21776 HTML), not from the repository: it reports "22.9% and 20.4% improvement on WebWalkerQA and HLE, respectively" for the Base variant over prior methods, and for the RL variant over Base "8.5% and 21.5% improvement on GAIA and HLE, respectively." The README itself carries no numbers at all — its only performance material is the `figures/performance.png` image plus a one-line qualitative claim. For report generation on 30 Glaive Reasoning-v1-20m questions, the paper reports WebThinker-32B-RL at 8.3/8.4/7.7/7.9 (Comprehensiveness/Thoroughness/Factuality/Coherence, average 8.1) versus Gemini 2.0 Deep Research 7.9 average and Grok3 DeeperSearch 6.5. The committed `outputs/glaive.qwq.webthinker/markdown.test/evaluation_scores.json` gives 8.53/8.53/7.75/7.93 for WebThinker against Gemini 8.25/8.22/7.60/8.03 and naive RAG 5.23/4.83/5.93/6.10. No BrowseComp, DeepResearch Bench or xbench-DeepSearch numbers exist, and all figures are author-reported; I found no independent reproduction.

#### Strengths

The single-generation design is genuinely different from workflow-graph agents and is the cleanest open implementation of "tool calls inside the chain of thought" for deep research. The Deep Web Explorer gives real link-following depth rather than snippet-only retrieval. Section-level drafting interleaved with search means the report is grounded in what was just read, and the check/edit tools give the model a way to revise. Released 7B/14B/32B checkpoints plus the DPO recipe make the RL claim reproducible in principle. Committed sample reports for WebThinker, Gemini Deep Research and Grok3 make qualitative comparison easy. MIT licensing and OpenAI-compatible endpoints keep it portable.

#### Weaknesses and limitations

No citations in generated reports, which disqualifies it for verifiable research output without modification. Heavy operational burden: two served models, local tokenizer files, and an optional separate parser service. Hard-coded defaults are researcher-specific (`--tokenizer_path` defaults to `/share/project/llm/QwQ-32B`). Budgets are constants inside functions (`MAX_TOKENS = 50000`, `MAX_INTERACTIONS = 80`, explorer caps of 10 and 20000), not configuration. Token accounting uses `len(text.split())`, a rough approximation. Model routing checks `'qwq' in args.model_name.lower()`, so behaviour silently changes with a renamed model. State is in-memory only, so there is no resume, no persistence, and no observability beyond print statements. Bing support is a liability given the API's August 2025 retirement noted in the README. Documentation quality is uneven — the quick-start Streamlit command as written does not run. Also: Chinese-language comments, dead commented-out code, 32 committed `.pyc` files, no automated tests, no CI, and no commits since December 2025.

#### Best fit

WebThinker suits researchers studying agentic reasoning, anyone fine-tuning or RL-training an open reasoning model for tool use, and teams who want to benchmark an end-to-end LRM agent on GAIA/WebWalkerQA/HLE with their own GPUs. It is a poor fit for production deep research or for anyone who needs footnoted output, hosted deployment, or a stable API. Its closest sibling is Search-o1 from the same group, which is the ablation baseline here: same token-interception idea, but snippet-level retrieval and no report drafting or link clicking. Against LangChain-style open deep research stacks that use a supervisor plus parallel researcher subagents and emit inline citations, WebThinker trades orchestration control, provider breadth and citation discipline for a simpler, more autonomous single-model loop and for trainable weights. If you want a citing report generator today, look elsewhere; if you want to study or train the agent itself, this is one of the better-documented starting points.

#### Sources

- https://github.com/RUC-NLPIR/WebThinker
- https://raw.githubusercontent.com/RUC-NLPIR/WebThinker/main/README.md
- https://api.github.com/repos/RUC-NLPIR/WebThinker
- https://github.com/RUC-NLPIR/WebThinker/blob/main/scripts/run_web_thinker_report.py
- https://github.com/RUC-NLPIR/WebThinker/blob/main/scripts/run_web_thinker.py
- https://github.com/RUC-NLPIR/WebThinker/blob/main/scripts/prompts/prompts_report.py
- https://github.com/RUC-NLPIR/WebThinker/blob/main/scripts/prompts/prompts.py
- https://github.com/RUC-NLPIR/WebThinker/blob/main/scripts/search/bing_search.py
- https://github.com/RUC-NLPIR/WebThinker/blob/main/scripts/evaluate/evaluate.py
- https://github.com/RUC-NLPIR/WebThinker/tree/main/scripts/utils
- https://github.com/RUC-NLPIR/WebThinker/blob/main/demo/run_demo.py
- https://github.com/RUC-NLPIR/WebThinker/blob/main/demo/settings.py
- https://github.com/RUC-NLPIR/WebThinker/blob/main/requirements.txt
- https://github.com/RUC-NLPIR/WebThinker/blob/main/outputs/glaive.qwq.webthinker/markdown.test/evaluation_scores.json
- https://arxiv.org/abs/2504.21776
- https://arxiv.org/html/2504.21776v1
- https://huggingface.co/lixiaoxi45/WebThinker-QwQ-32B
- https://www.marktechpost.com/2025/05/06/this-ai-paper-introduce-webthinker-a-deep-research-agent-that-empowers-large-reasoning-models-lrms-for-autonomous-search-and-report-generation/
- https://foremost-beechnut-8ed.notion.site/WebThinker-Empowering-Large-Reasoning-Models-with-Deep-Research-Capability-d13158a27d924a4b9df7f9ab94066b64


### 16. DR Tulu

Repository: https://github.com/rlresearch/dr-tulu
License: Apache-2.0 | Stars: 707 (as of 2026-09-09) | Language: Python | Pattern: Single RL-trained ReAct-style tool loop (think / call_tool / answer) over MCP tools, with a forced-synthesis fallback agent
Fact-check: minor-issues, 4 corrections applied

#### Overview

DR Tulu is the code, data and weights release behind "DR Tulu: Reinforcement Learning with Evolving Rubrics for Deep Research" (arXiv 2511.19399). Unlike most projects in this space it is not a prompt-orchestration framework wrapped around a frontier API; it is an 8B model trained end to end to do deep research, shipped with the agent library it was trained against. The repository is maintained by the Allen Institute for AI (Ai2), with the README crediting student researchers at the University of Washington, Carnegie Mellon University and MIT; the first authors are Rulin Shao, Akari Asai, Shannon Zejiang Shen and Hamish Ivison. License is Apache-2.0 (`LICENSE`, confirmed by the GitHub API). Primary language is Python (the `app/` demo frontend is TypeScript/Next.js). GitHub metadata read on 2026-09-09: 707 stars, 77 forks, 5 open issues, created 2025-11-18, 105 commits on `main`. There are no GitHub releases or tags. The published PyPI package `dr-agent` is at 0.1.2 — the API lists exactly three releases, 0.1.0, 0.1.1 and 0.1.2 — while `agent/pyproject.toml` in the repo carries an unpublished 0.1.2.post1, so do not take the in-tree number for a shipped one. The repo has three branches: `main` (last commit 9d7b037, 2026-03-30, "import fix"), `rubric-rl` (20f78df, 2026-04-06) and `vk-auto-launch` (5e142c0, committer date 2026-09-09, "autolaunch things"), the last being the most recently touched. The API reports `pushed_at` 2026-06-17T02:47:32Z, which matches no branch tip we could identify; which push it refers to is unverified. The README release notes run 2025-11-19 (initial code release), 2025-11-25 (CLI demo, eval docs, new RL checkpoints) and 2026-02-09 (free interactive demo at dr-tulu.org). Maturity: a research artifact of high quality, actively used but not a hardened product. `agent/pyproject.toml` self-classifies as "Development Status :: 3 - Alpha", and the CLI chat is labeled "[experimental]". The paper is an ICML 2026 oral.

#### Workflow architecture

The orchestration pattern is a single ReAct-style tool loop driven by an RL-trained policy, not a plan-and-execute graph or a supervisor with parallel researcher sub-agents. There is no clarification turn, no outline stage, no explicit reflection or gap-analysis node. All of that behavior is expected to live inside the model's own `<think>` blocks, which is the central design bet of the project.

The concrete pieces:

- `agent/workflows/auto_search_sft.py` defines `AutoReasonSearchWorkflow(BaseWorkflow)` plus three `BaseAgent` subclasses: `SearchAgent` (the DR Tulu policy, holding the tools), `AnswerAgent` (synthesis fallback) and `WebPageReaderAgentV2` (optional page cleaner).
- `setup_components()` in the same file instantiates MCP-backed tools by config name: `SerperSearchTool` registered twice under the tool names `snippet_search` and `google_search`, or `SemanticScholarSnippetSearchTool`; then one of `SerperBrowseTool`, `Crawl4AIBrowseTool`, `JinaBrowseTool` or `NoBrowseTool` as `browse_webpage`. When `use_browse_agent=true` it wraps the browse tool and the reader agent in a `ChainedTool` (`agent/dr_agent/tool_interface/chained_tool.py`) with `output_formatting="last"`, so scraped HTML is summarized by a second model before entering context.
- The loop itself is `LLMToolClient._generate_with_tools_vllm()` in `agent/dr_agent/client.py` (parallel implementations `_generate_with_tools_commercial_api` and `_generate_with_tools_native`). It is a `while True` over: compute a dynamic token budget, generate until a tool stop sequence, append to `current_context`, find the first tool call with `_find_first_tool_call()`, execute, append the observation, repeat. It exits on no tool call, on `tool_call_count >= max_tool_calls`, or on hitting the token budget.
- Query generation, search, reading and depth/breadth control are all emitted by the model as text. Governance is purely budgetary: `search_agent_max_tool_calls` (default 10), `number_documents_to_search` (10), `browse_max_pages_to_fetch`, `browse_context_char_length` (6000) in `agent/workflows/auto_search_sft.yaml`.
- The protocol lives in `agent/dr_agent/shared_prompts/unified_tool_calling_v20250907.yaml`: `<think>`, `<call_tool name="...">query</call_tool>`, tool results returned as `<tool_output><snippet id=UNIQUE_ID>...</snippet></tool_output>`, and a final `<answer>` containing `<cite id="S17">claim</cite>` spans plus optional `\boxed{}`. Citations are therefore token-level attributions to returned snippet IDs, and the prompt explicitly forbids inventing IDs. Three `additional_instructions` variants (`exact_answer`, `short_form`, `long_form`) are selected per dataset; the `long_form` variant is what produces multi-section cited reports.
- Synthesis: if the loop terminates without `<answer>`, `AutoReasonSearchWorkflow.__call__` runs `AnswerAgent` with the whole trajectory as an assistant turn and the instruction "Now please generate an answer based on the search results by far" and a `generation_prefix="<answer>"`. The workflow also returns `searched_links`, `browsed_links` and tool-failure counts.
- Training, not orchestration, is where the intelligence was added: `rl/open-instruct/` (GRPO via Ai2 Open-Instruct, including `open_instruct/grpo_fast_rubric.py` and `open_instruct/search_rewards/longform_rubric_rewards.py` with `compute_weighted_rubric_reward_with_citation_and_format_reward`) and `sft/llama-factory/`.

```
user query
   |
   v
SearchAgent (DR-Tulu-8B, vLLM)  <-- system prompt: think/call_tool/answer/cite
   |
   +--> <think> ... </think>                      (reasoning, gap analysis, in-model)
   +--> <call_tool name="google_search">      --\
   +--> <call_tool name="snippet_search">      --+--> MCP server (FastMCP, port 8000)
   +--> <call_tool name="browse_webpage">     --/       Serper / Semantic Scholar / Jina / Crawl4AI
   |          |
   |          +-- optional ChainedTool: WebPageReaderAgentV2 (Qwen3-8B) cleans page text
   |          v
   +<-- <tool_output><snippet id=Sx>...</snippet></tool_output>
   |
   loop while tool_call_count < max_tool_calls (10) and token budget remains
   |
   v
<answer> ... <cite id="Sx,Sy">claim</cite> ... </answer>
   |  (if loop ended with no <answer>)
   +--> AnswerAgent forced synthesis with generation_prefix="<answer>"
```

#### Key components

Models: the intended policy is `rl-research/DR-Tulu-8B`, the RL checkpoint trained on top of `rl-research/DR-Tulu-SFT-8B`, which was itself SFT'd from `Qwen/Qwen3-8B` — the instruct/hybrid-reasoning model, not the `Qwen3-8B-Base` pretrained variant; the repo agrees, with `search_agent_tokenizer_name: "Qwen/Qwen3-8B"` in `agent/workflows/auto_search_sft.yaml`. It is served locally with vLLM on port 30001 (`--max-model-len 40960`), and its model card warns that "running it out of the box with HuggingFace or vLLM will not work well!" without the `dr-agent` library. The optional browse/reader agent defaults to `Qwen/Qwen3-8B` on port 30002. Commercial APIs are supported through litellm and a separate `workflows/auto_search_sft-oai.yaml` config for GPU-free debugging with OpenAI models. Sibling checkpoints `DR-Tulu-SFT-8B` and `DR-Tulu-No-RLER-8B` and the datasets `dr-tulu-sft-data` and `dr-tulu-rl-data` are on Hugging Face.

Search and reading: the MCP backend `agent/dr_agent/mcp_backend/main.py` is a FastMCP server exposing `serper_google_webpage_search`, `serper_google_scholar_search`, `semantic_scholar_search`, `semantic_scholar_snippet_search`, `pubmed_search`, `massive_serve_search`, `local_search`, `local_browse`, `vllm_hosted_reranker`, plus browsers `serper_fetch_webpage_content`, `jina_fetch_webpage_content`, `crawl4ai_fetch_webpage_content`, `crawl4ai_docker_fetch_webpage_content` and `webthinker_fetch_webpage_content`. Local retrieval includes BM25 and FAISS backends (`mcp_backend/local/search/`).

Memory and state: none beyond the growing trajectory string, plus a global tool cache (`mcp_backend/cache.py`, diskcache/tinydb) built for rate-limit-aware high-concurrency RL rollouts. Multi-turn chat history is threaded in via the `messages` argument.

Structured output: text tags parsed by `tool_interface/tool_parsers.py` (versioned, e.g. `v20250824`), not JSON schemas or native function calling by default, though a `_generate_with_tools_native` path exists.

Surfaces: an interactive CLI (`agent/scripts/launch_chat.py`, which offers to auto-launch the MCP and vLLM servers), a FastAPI service via `workflows/auto_search_sft.py serve` exposing `/chat`, `/chat/stream` (SSE), `/health` and optional password auth (`agent/dr_agent/web_api/api.py`), a Next.js chat UI in `app/` declared in `app/package.json` as `@dr-tulu/chat-ui` version 0.1.0 — a workspace app, with no evidence it is published to npm under that or any other name — a batch `generate-dataset` mode with concurrency and sharding, and the hosted demo at dr-tulu.org. Human-in-the-loop is limited to conversational follow-ups.

Extensibility: tools are MCP tools, so swapping backends is a config change; `tool_interface/agent_as_tool.py` (`BaseAgent.as_tool`) and `ChainedTool` let you expose a sub-agent as a tool.

#### Evaluation and benchmarks

From Table 1 of the paper, DR Tulu-8B (RL) scores SQAv2 (AstaBench ScholarQA-CSv2) 88.3, HealthBench 52.8, ResearchQA 75.7, DeepResearch Bench 45.4, average 65.6. Comparators in the same table: OpenAI Deep Research 79.6 / 53.8 / 79.2 / 46.9, average 64.9; GPT-5 + Search 65.8 average; Gemini 3 Pro + Search 57.0; Ai2 ScholarQA (Claude Sonnet) 57.7; Tongyi DeepResearch-30B-A3B 50.0; WebExplorer-8B 44.4; WebThinker-32B-DPO 28.9; the SFT-only ablation 53.9. Table 2 short-form: SimpleQA 75.9, 2Wiki 68.9, WebWalker 39.0, average 61.3. The abstract claims +15.6 points over Tongyi DR and +0.7 over OpenAI DR on the long-form average. Cost claims: $0.00008/query for tool APIs, $0.0018/query including LM inference at OpenRouter Qwen3-8B pricing, versus $1.80/query for OpenAI Deep Research and $1.30 for Ai2 ScholarQA on SQAv2. The paper also introduces GeneticDiseasesQA, 47 expert-curated questions over 24 pathogenic gene variants. Training scale: 16K SFT trajectories distilled from GPT-5, roughly 5K long-form RL prompts from SearchArena and OpenScholar plus 4K from RaR. No GAIA, BrowseComp or HLE scores appear in the main tables, although `agent/evaluation/browse_comp_eval/browsecomp_eval.py` and an `hle` dataset branch exist in the code, and the blog's earlier table reports lower numbers (SQAv2 86.7, HealthBench 43.7, ResearchQA 71.1, DRB 41.8) than the current model card, so quote the source you rely on.

#### Strengths

Full-stack openness is the real differentiator: weights, SFT and RL data, the RL trainer with rubric reward code, the agent library and the eval harness are all public under Apache-2.0, which almost no other deep research release matches. Citation handling is first class and trained in, with snippet-ID grounding rather than post-hoc URL stapling, and cited claim spans that evaluation actually scores. The cost profile is extreme: an 8B local model plus mostly free paper search. Tool plumbing is genuinely reusable, with MCP tools, global caching and async concurrency designed for thousands of parallel rollouts. Adaptive tool choice, mixing Semantic Scholar snippets with Google and browsing, is learned rather than hardcoded. The eval directory is unusually complete, with runnable harnesses for DRB, ScholarQA, ResearchQA, HealthBench and short-form QA.

#### Weaknesses and limitations

You need GPUs. One or two of them, and everything interesting assumes local vLLM; the OpenAI-config path exists mainly for debugging and does not give you DR Tulu. The model card is blunt that the weights alone are not enough — without the `dr-agent` library, running them out of the box on HuggingFace or vLLM "will not work well". The orchestration layer is deliberately thin, so there is no clarification step, no outline, no parallel researchers, no report-length control and no retry policy beyond a tool-call cap of 10, which bounds how deep a report can go. The code carries visible research debt: a comment in `setup_components` concedes the `snippet_search` tool name is set "in a hacky way", `__call__` sets `browse_tool.bm25_query` and the reader agent's question by mutation with a TODO calling it "a bit hectic and hacky", the answer fallback prompt contains the typo "generate an based on the search results", and `agent/pyproject.toml` declares Apache-2.0 while its PyPI classifiers say MIT. `AnswerAgent.prompt` raises on any dataset name outside a fixed allowlist. `main` has not moved since 2026-03-30 and there are no tagged releases or newer PyPI publishes than 0.1.2, so pinning means pinning a commit; active work appears to sit on side branches such as `vk-auto-launch`. Context is a single 40K-token string with no compaction, so long investigations hit the token budget rather than reasoning about it. Finally, evaluation is largely self-reported, with several baseline numbers copied from other leaderboards rather than rerun, and third-party replications of the headline comparison against OpenAI Deep Research are unverified.

#### Best fit

DR Tulu suits researchers and teams who want to study or extend RL training for research agents, and organizations that need cited long-form research over scientific literature at near-zero marginal cost with no data leaving their infrastructure. Clinical, scholarly and other domains where every claim must trace to a retrievable snippet are its sweet spot. It is a poor fit for someone who wants a turnkey product, a web UI for non-technical users, or a framework for orchestrating GPT-5 or Claude across many tools. Compared with Ai2's own ScholarQA, a fixed-pipeline system that scores 87.7 on SQAv2 but only 36.1 on DRB, DR Tulu generalizes far better outside scholarly search. Compared with Tongyi DeepResearch-30B-A3B, it is nearly four times smaller, scores 15.6 points higher on the long-form average, and unlike that model emits citations at all. Against orchestration frameworks such as LangChain's open_deep_research or GPT-Researcher, DR Tulu is not really the same kind of object: those give you a configurable graph over any API model, while DR Tulu gives you a small model that has already internalized the graph.

#### Sources

- https://github.com/rlresearch/dr-tulu
- https://raw.githubusercontent.com/rlresearch/dr-tulu/main/README.md
- https://api.github.com/repos/rlresearch/dr-tulu
- https://api.github.com/repos/rlresearch/dr-tulu/branches
- https://github.com/rlresearch/dr-tulu/blob/main/app/package.json
- https://pypi.org/pypi/dr-agent/json
- Repository source read via shallow clone: `agent/README.md`, `agent/workflows/auto_search_sft.py`, `agent/workflows/auto_search_sft.yaml`, `agent/dr_agent/client.py`, `agent/dr_agent/agent_interface.py`, `agent/dr_agent/mcp_backend/main.py`, `agent/dr_agent/shared_prompts/unified_tool_calling_v20250907.yaml`, `agent/dr_agent/tool_interface/`, `agent/dr_agent/web_api/api.py`, `agent/evaluation/README.md`, `agent/pyproject.toml`, `agent/.env.example`, `app/package.json`, `rl/open-instruct/open_instruct/search_rewards/longform_rubric_rewards.py`, `LICENSE`
- https://allenai.org/blog/dr-tulu
- https://arxiv.org/abs/2511.19399
- https://arxiv.org/pdf/2511.19399
- https://huggingface.co/rl-research/DR-Tulu-8B
- https://huggingface.co/rl-research/DR-Tulu-SFT-8B/raw/main/README.md
- https://huggingface.co/collections/rl-research/dr-tulu
- https://icml.cc/virtual/2026/oral/71088


## Appendix: other open-source projects found

- **Local Deep Researcher** - https://github.com/langchain-ai/local-deep-researcher - Notable local loop, but overlaps the selected LearningCircuit local-deep-research for the private-first slot.
- **DeepSearcher** - https://github.com/zilliztech/deep-searcher - Notable but no commits since Nov 2025; private-corpus vector-RAG focus over end-to-end web research.
- **open-deep-research (nickscamara)** - https://github.com/nickscamara/open-deep-research - Firecrawl-based DR clone; lower adoption and overlaps selected full-stack apps.
- **node-DeepResearch (Jina DeepSearch)** - https://github.com/jina-ai/node-DeepResearch - Notable budget-bounded search-read-reason loop, but the single-agent loop archetype is covered by dzhng/deep-research.
- **u14app deep-research** - https://github.com/u14app/deep-research - Notable but lower adoption; UI wrapper around the dzhng-style loop.
- **MS-Agent** - https://github.com/modelscope/ms-agent - General agent framework where deep research is one pipeline; overlaps AgentScope, lower adoption.
- **OpenDeepSearch** - https://github.com/sentient-agi/OpenDeepSearch - Search tool + ReAct agent for multi-hop QA rather than an iterative cited-report workflow.
- **DeepResearchAgent (Skywork)** - https://github.com/SkyworkAI/DeepResearchAgent - Hierarchical planner/worker design already represented by higher-adoption supervisor systems.
- **MiroFlow** - https://github.com/MiroMindAI/MiroFlow - Companion orchestration repo of the selected MiroThinker (same org and stack); profiled together with it.
- **Automated-AI-Web-Researcher-Ollama** - https://github.com/TheBlewish/Automated-AI-Web-Researcher-Ollama - Early local-Ollama researcher, largely superseded by the selected LearningCircuit tool.
- **OpenDeepResearcher** - https://github.com/mshumer/OpenDeepResearcher - Historically influential notebook prototype, now unmaintained.
- **deep-research-web-ui** - https://github.com/AnotiaWang/deep-research-web-ui - Web-UI port of dzhng/deep-research; merged conceptually into that entry.
- **open-deep-research (btahir)** - https://github.com/btahir/open-deep-research - Notable but lower-adoption Gemini-DR clone; no distinct architecture.
- **HyperResearch** - https://github.com/jordan-gibbs/hyperresearch - Lower adoption; knowledge-base accumulation rather than a distinct research loop.
- **Auto-Deep-Research** - https://github.com/HKUDS/AutoAgent - Deep-research mode of HKUDS/AutoAgent; merged into that repo, which is itself a general agent framework.
- **OpenResearcher (TIGER-AI-Lab)** - https://github.com/TIGER-AI-Lab/OpenResearcher - Trajectory-synthesis and training pipeline for research models rather than a deployable workflow; lower adoption.
- **Enterprise Deep Research** - https://github.com/SalesforceAIResearch/enterprise-deep-research - Notable vendor LangGraph multi-agent system, but lower adoption and architecturally redundant with LangChain ODR.
- **PokeeResearch** - https://github.com/Pokee-AI/PokeeResearchOSS - RLAIF-trained 7B research agent; lower adoption than the selected open-weight models.
- **SurveyX** - https://github.com/IAAR-Shanghai/SurveyX - Narrow survey-paper generator; literature synthesis covered by PaperQA2/STORM.
- **DeepGit** - https://github.com/zamalali/DeepGit - Narrow scope — deep research over GitHub repositories only.
- **open-deep-research (fdarkaou)** - https://github.com/fdarkaou/open-deep-research - Lower-adoption Next.js DR clone.
- **DeepResearcher (GAIR)** - https://github.com/GAIR-NLP/DeepResearcher - RL training framework for live-web search agents; training axis covered by Tongyi and DR Tulu.
- **agents-deep-research (QX Labs)** - https://github.com/qx-labs/agents-deep-research - Solid OpenAI-Agents-SDK implementation but lower adoption; design duplicates LangChain ODR.
- **deep_research_from_scratch** - https://github.com/langchain-ai/deep_research_from_scratch - Teaching companion to the selected LangChain open_deep_research.
- **OpenSeeker** - https://github.com/PolarSeeker/OpenSeeker - Search-model training project with benchmark-oriented outputs; lower adoption.
- **Vision-DeepResearch** - https://github.com/Osilly/Vision-DeepResearch - Multimodal research model plus benchmark; niche and lower adoption.
- **Open Researcher (Firecrawl)** - https://github.com/firecrawl/open-researcher - Vendor demo app for Firecrawl; lower adoption.
- **Step-DeepResearch** - https://github.com/stepfun-ai/StepDeepResearch - Promising Apache-2.0 32B model + framework but very recent and low adoption to date.
- **CognitiveKernel-Pro** - https://github.com/Tencent/CognitiveKernel-Pro - Notable multi-module agent with training recipes, but lower adoption; overlaps other supervisor systems.
- **MedResearcher-R1** - https://github.com/AQ-MedAI/MedResearcher-R1 - Domain-specific (medical) trained agent; lower adoption.
- **OpenResearcher (GAIR)** - https://github.com/GAIR-NLP/OpenResearcher - arXiv+web scientific QA assistant; lower adoption and overlaps PaperQA2.
- **II-Researcher** - https://github.com/Intelligent-Internet/ii-researcher - Lower adoption; pluggable search/report framework without a distinct architecture.
- **Universal Deep Research** - https://github.com/NVlabs/UniversalDeepResearch - Interesting user-specified-strategy paper prototype, but low adoption and not a maintained product.
- **Open Deep Research (Nutlope)** - https://github.com/Nutlope/open-deep-research - Lower-adoption demo app on the Together/Llama stack.
- **Deeper Seeker** - https://github.com/HarshJ23/Deeper-Seeker - Minimal early prototype, effectively unmaintained.
- **deep-research-py** - https://github.com/epuerta9/deep-research-py - Python port of dzhng/deep-research.
- **Together Open Deep Research** - https://github.com/togethercomputer/open_deep_research - Vendor reference implementation; lower adoption, no distinct architecture.
- **gptr-mcp** - https://github.com/assafelovic/gptr-mcp - MCP wrapper around the selected GPT Researcher, not a separate workflow.
- **Marco-DeepResearch (ATH-MaaS)** - https://github.com/ATH-MaaS/Marco-DeepResearch - Duplicate of AIDC-AI/Marco-DeepResearch (same Alibaba International project under a second org).
- **A-RAG** - https://github.com/Ayanami0730/arag - Retrieval backend/library for research agents, not an end-to-end workflow.
- **Open-Deep-Research-workflow-on-Dify** - https://github.com/AdamPlatin123/Open-Deep-Research-workflow-on-Dify - Dify workflow export; low adoption and platform-locked.
- **DeepWideResearch** - https://github.com/puppyone-ai/DeepWideResearch - Low adoption; agentic-RAG report engine without distinguishing design.
- **DeepEar** - https://github.com/HKUSTDial/DeepEar - Low adoption; financial signal-tracking niche.
- **FinSight** - https://github.com/RUC-NLPIR/FinSight - Financial vertical with low adoption; Dexter covers the finance axis at far higher scale.
- **open-gemini-deep-research** - https://github.com/eRuaro/open-gemini-deep-research - Low-adoption Gemini DR recreation.
- **tarun7r deep-research-agent** - https://github.com/tarun7r/deep-research-agent - Low adoption hobby LangGraph implementation.
- **PanelWise** - https://github.com/inclusionAI/PanelWise - Low adoption; parallel multi-model fusion is a variant of the supervisor pattern already covered.
- **Fathom-DeepResearch** - https://github.com/FractalAIResearchLabs/Fathom-DeepResearch - Strong published results but only ~64 stars; minimal adoption.
- **iFlytek DeepResearch** - https://github.com/iflytek/DeepResearch - Low adoption vendor framework.
- **open-deep-research-with-web-ui** - https://github.com/extracurricular-ai/open-deep-research-with-web-ui - Low-adoption UI wrapper around the smolagents example.
- **ResearStudio** - https://github.com/ResearAI/ResearStudio - Human-in-the-loop DR framework with lower adoption; HITL steering overlaps Co-STORM and Open Research ANA.
- **WebAgent (WebDancer / WebSailor / WebWalker / WebShaper)** - https://github.com/Alibaba-NLP/WebAgent - Same Tongyi WebAgent family as the selected Alibaba-NLP/DeepResearch; merged into that canonical entry.
- **OWL** - https://github.com/camel-ai/owl - General multi-agent collaboration framework benchmarked on GAIA; deep research is an application, not the product.
- **SimpleDeepSearcher** - https://github.com/RUCAIBox/SimpleDeepSearcher - SFT data-synthesis/training study for search agents, not an end-to-end report workflow.
- **Search-R1** - https://github.com/PeterGriffinJin/Search-R1 - RL training framework for search-interleaved reasoning (short-answer QA), not a cited-report workflow.
- **ReSearch / ReCall** - https://github.com/Agent-RL/ReSearch - Duplicate of Agent-RL/ReCall (same project, two repos); RL training stack rather than a workflow.
- **Search-o1 (sunnynexus)** - https://github.com/sunnynexus/Search-o1 - Duplicate of RUC-NLPIR/Search-o1 (author mirror).
- **Agentic Reasoning** - https://github.com/theworldofagents/Agentic-Reasoning - Lower adoption; mind-map memory variant of the reasoning-with-search pattern.
- **deep_research_agent (grapeot)** - https://github.com/grapeot/deep_research_agent - Minimal demo, low adoption.
- **Librarium** - https://github.com/jkudish/librarium - Low adoption; fan-out to search APIs with light iteration.
- **Cerno Agentic Local Deep Research** - https://github.com/Cerno-AI/Cerno-Agentic-Local-Deep-Research - Very low adoption (~88 stars).
- **deep-research (shibing624)** - https://github.com/shibing624/deep-research - Very low adoption (~50 stars).
- **FlowSearch** - https://github.com/Alpha-Innovator/FlowSearch - Notable knowledge-flow design but lower adoption; overlaps other multi-agent DR frameworks.
- **OpenScholar** - https://github.com/AkariAsai/OpenScholar - Well-cited literature-synthesis pipeline, but overlaps the selected PaperQA2 and has lower adoption.
- **Search-o1** - https://github.com/RUC-NLPIR/Search-o1 - Retrieval-augmented reasoning method (reason-in-documents), not a plan->iterate->report workflow; superseded by WebThinker from the same lab.
- **R1-Searcher** - https://github.com/RUCAIBox/R1-Searcher - RL training method and checkpoints for search invocation; not an end-to-end research workflow.
- **R1-Searcher++** - https://github.com/RUCAIBox/R1-Searcher-plus - Follow-up training method with minimal adoption (~82 stars).
- **ReSearch / ReCall** - https://github.com/Agent-RL/ReCall - RL tool-use training framework (canonical of the ReSearch/ReCall pair), not a research workflow.
- **MindSearch** - https://github.com/InternLM/MindSearch - Notable (6.9k) sub-question graph search framework, but answer-engine oriented and largely dormant.
- **ASearcher** - https://github.com/inclusionAI/ASearcher - Asynchronous RL training infrastructure for search agents, not a workflow.
- **OmniThink** - https://github.com/zjunlp/OmniThink - Long-form machine-writing method; lower adoption and overlaps STORM's niche.
- **OAgents** - https://github.com/OPPO-PersonalAI/OAgents - General agent-design empirical study/framework, not a dedicated DR workflow.
- **O-Researcher** - https://github.com/OPPO-PersonalAI/O-Researcher - Minimal adoption (~27 stars).
- **WebExplorer** - https://github.com/hkust-nlp/WebExplorer - Data-synthesis plus training pipeline; low adoption, not a workflow.
- **ZeroSearch** - https://github.com/Alibaba-NLP/ZeroSearch - RL training trick using a simulated search engine; training method, not a research workflow.
- **MaskSearch** - https://github.com/Alibaba-NLP/MaskSearch - Pre-training framework for agentic search ability; not a workflow.
- **Dr. Zero** - https://github.com/facebookresearch/drzero - Self-evolving training research (proposer/solver co-evolution), not an end-to-end research system.
- **QUEST** - https://github.com/OSU-NLP-Group/QUEST - Synthetic-task training recipe for research agents; not a deployable workflow.
- **DeepAgent** - https://github.com/RUC-NLPIR/DeepAgent - General tool-discovery reasoning agent over 16k APIs; web research is one capability, not the product.
- **s3** - https://github.com/pat-jj/s3 - Searcher-training method for RAG; not an end-to-end cited-report workflow.
- **DR-Venus** - https://github.com/inclusionAI/DR-Venus - Edge-scale 4B trained agent with low adoption (~95 stars).
- **Atom-Searcher / Research-Venus** - https://github.com/antgroup/Research-Venus - Reward-shaping training method plus model; low adoption.
- **Agents-A1** - https://github.com/InternScience/Agents-A1 - Agentic foundation model release; general-purpose rather than a deep research workflow.
- **LiteResearcher** - https://github.com/simplexai-labs/LiteResearcher - Agentic-RL training framework; low adoption, not a workflow.
- **DeepScholar** - https://github.com/guestrin-lab/deepscholar - Primarily a benchmark/build harness for research synthesis; low adoption.
- **MMSearch-R1** - https://github.com/EvolvingLMMs-Lab/multimodal-search-r1 - Multimodal RL training framework for on-demand search, not a report-writing workflow.
- **WriteHERE** - https://github.com/principia-ai/WriteHERE - Recursive long-form writing framework; writing-centric rather than a full research loop.
- **AI-Researcher** - https://github.com/HKUDS/AI-Researcher - Autonomous-science pipeline (idea -> code -> paper), a different category from web deep research.
- **Agent Laboratory** - https://github.com/SamuelSchmidgall/AgentLaboratory - Autonomous experimentation/paper-writing workflow, not web deep research.
- **The AI Scientist** - https://github.com/SakanaAI/AI-Scientist - Automated scientific discovery (runs experiments), out of scope for search-and-synthesize DR.
- **AgentCPM (AgentCPM-Report)** - https://github.com/OpenBMB/AgentCPM - Agent training/eval infrastructure; the report agent is one component, lower adoption.
- **InfoAgent** - https://github.com/microsoft/InfoAgent - Research code for trajectory compression; very low adoption (~81 stars).
- **SmartSearch** - https://github.com/RUC-NLPIR/SmartSearch - Query-refinement method; very low adoption.
- **Yunque DeepResearch Agent** - https://github.com/Tencent-BAC/YunqueAgent - Low adoption (~101 stars) vendor multi-agent release.
- **RAG-Gym** - https://github.com/RAG-Gym/RAG-Gym - Agent-optimization framework for multi-hop RAG; not an end-to-end DR workflow.
- **MrlX** - https://github.com/AQ-MedAI/MrlX - Multi-agent RL training framework, not a workflow.
- **WebSeer** - https://github.com/99hgz/WebSeer - Minimal adoption (13 stars) training paper code.
- **VideoDeepResearch** - https://github.com/RUC-NLPIR/VideoDeepResearch - Long-video QA agent; out of scope for text/web report synthesis.
- **LMM-Searcher** - https://github.com/RUCAIBox/LMM-Searcher - Multimodal search research code with minimal adoption (~30 stars).
- **Awesome Deep Research (survey companion)** - https://github.com/scienceaix/deepresearch - Index/survey companion list, not an agent or workflow.
- **deep-agents-from-scratch** - https://github.com/langchain-ai/deep-agents-from-scratch - Teaching companion to the selected deepagents.
- **Hugging Face open_deep_research (smolagents example)** - https://github.com/huggingface/smolagents - Duplicate of the selected smolagents open_deep_research entry (same repo).
- **Google ADK deep-search agent** - https://github.com/google/adk-samples - Sample inside a large samples monorepo; overlaps the selected Gemini fullstack quickstart.
- **OpenAI Agents SDK research_bot** - https://github.com/openai/openai-agents-python - Small example inside an SDK repo; a demo, not a maintained DR project.
- **OpenAI Cookbook deep_research_api examples** - https://github.com/openai/openai-cookbook - Notebooks driving OpenAI's closed Deep Research API; the research engine itself is not open source.
- **Magentic-One (AutoGen)** - https://github.com/microsoft/autogen - General multi-agent team inside AutoGen; task-completion oriented, not a cited-report DR pipeline.
- **Magentic-UI** - https://github.com/microsoft/Magentic-UI - Human-in-the-loop browsing agent; web-task automation rather than cited report synthesis.
- **Azure-Samples deepresearch** - https://github.com/Azure-Samples/deepresearch - Vendor sample with ~64 stars.
- **CrewAI deep_research_paper_chat** - https://github.com/crewAIInc/deep_research_paper_chat - 20-star vendor demo.
- **crewAI-examples** - https://github.com/crewAIInc/crewAI-examples - Example collection, not a deep research project.
- **create-llama deep_research use case** - https://github.com/run-llama/create-llama - Template inside a scaffolding CLI; not a standalone DR system.
- **Agno research/deep-research agent cookbook** - https://github.com/agno-agi/agno - General agent framework; deep research is a cookbook example.
- **Firesearch** - https://github.com/firecrawl/firesearch - Vendor tool with lower adoption; overlaps Firecrawl's open-researcher.
- **NVIDIA AI-Q Research Assistant blueprint** - https://github.com/NVIDIA-AI-Blueprints/aiq - Notable enterprise blueprint but lower adoption; built on the selected deepagents, which is profiled instead.
- **Biomedical AI-Q Research Agent** - https://github.com/NVIDIA-AI-Blueprints/biomedical-aiq-research-agent - Domain variant of the AI-Q blueprint; low adoption.
- **Anthropic claude-cookbooks multi-agent research pattern** - https://github.com/anthropics/claude-cookbooks - Notebooks and prompts illustrating a pattern; the production Research feature is closed source.
- **AdvancedResearch** - https://github.com/The-Swarm-Corporation/AdvancedResearch - 36-star reproduction of the orchestrator-worker pattern.
- **deep-research-n8n** - https://github.com/dair-ai/deep-research-n8n - 22-star n8n workflow export.
- **ROMA (Recursive Open Meta-Agent)** - https://github.com/sentient-agi/ROMA - General recursive meta-agent framework; deep research is one downstream application.
- **Onyx (formerly Danswer)** - https://github.com/onyx-dot-app/onyx - Enterprise search/chat platform where Deep Research is one mode; overlaps khoj for the self-hosted-app slot.
- **SurfSense** - https://github.com/MODSetter/SurfSense - Notable self-hosted connector-based research app, but overlaps khoj and Onyx in the same niche.
- **Jan-nano** - https://huggingface.co/Menlo/Jan-nano - Open-weight tool-use model on HF only; no research workflow repo of its own.
- **Alita** - https://github.com/CharlesQ9/Alita - Self-evolving generalist agent that writes MCP tools; not a deep research workflow.
- **Marco-DeepResearch** - https://github.com/AIDC-AI/Marco-DeepResearch - Canonical of the two Marco-DeepResearch entries; low adoption (~337 stars).
- **S1-DeepResearch** - https://github.com/ScienceOne-AI/S1-DeepResearch - Minimal adoption (~27 stars).
- **MM-DeepResearch** - https://github.com/HJYao00/MM-DeepResearch - Minimal adoption (~21 stars) multimodal RL baseline.
- **openPangu-Embedded-7B-DeepDiver** - https://huggingface.co/FreedomIntelligence/openPangu-Embedded-7B-DeepDiver - Model weights on HF; no accompanying open workflow implementation.
- **GLM-Z1-Rumination-32B-0414** - https://huggingface.co/zai-org/GLM-Z1-Rumination-32B-0414 - Open weights only; the rumination/search harness is not released as a workflow.
- **nanoDeepResearch** - https://github.com/liyuan24/nanoDeepResearch - Teaching mini-implementation with low adoption.
- **MiroMind Open-Source Deep Research (HF Space)** - https://huggingface.co/spaces/miromind-ai/MiroMind-Open-Source-Deep-Research - Hosted demo Space for the selected MiroThinker/MiroFlow stack.
- **Perplexica** - https://github.com/ItzCrazyKns/Perplexica - Answer engine with focus modes; single-pass search-and-answer, not plan -> iterate -> cited long report.
- **Scira (formerly MiniPerplx)** - https://github.com/zaidmukaddam/scira - Search/answer UI rather than an end-to-end deep research workflow.
- **Morphic** - https://github.com/miurla/morphic - Generative-UI answer engine; no research plan or report synthesis stage.
- **FreeAskInternet** - https://github.com/nashsu/FreeAskInternet - Multi-engine search aggregator plus answer; not an iterative research loop.
- **Search with Lepton** - https://github.com/leptonai/search_with_lepton - Minimal 'build your own Perplexity' demo; single search-and-answer turn.
- **Farfalle** - https://github.com/rashadphz/farfalle - Self-hosted answer engine; no plan/iterate/report pipeline.
- **TurboSeek** - https://github.com/Nutlope/turboseek - Answer engine demo, not a deep research workflow.
- **Open Notebook** - https://github.com/lfnovo/open-notebook - NotebookLM-style workspace over user sources; research is an ask-mode, not an autonomous iterative loop.
- **AnythingLLM** - https://github.com/Mintplex-Labs/anything-llm - General local LLM workspace with web-search skills; not a deep research workflow.
- **RAGFlow** - https://github.com/infiniflow/ragflow - RAG infrastructure with a deep-research mode; primarily document parsing/retrieval, not a research agent.
- **Feynman** - https://github.com/advaitpaliwal/feynman - Notable 2026 app (9.3k) but young and architecturally overlapping the selected full-stack apps.
- **AIPOCH Open-Science** - https://github.com/aipoch/open-science - Desktop scientific workbench with agents; not an end-to-end DR loop.
- **OpenManus** - https://github.com/FoundationAgents/OpenManus - General Manus-style agent harness; DeepResearch is one flow among many.
- **AutoAgent** - https://github.com/HKUDS/AutoAgent - Zero-code general multi-agent framework (parent of Auto-Deep-Research); DR is one mode.
- **AgenticSeek** - https://github.com/Fosowl/agenticSeek - Fully local general assistant (browse/code/plan); no cited-report research pipeline.
- **Suna / Kortix** - https://github.com/kortix-ai/suna - General agent platform used for research; not a purpose-built DR workflow.
- **JoyAgent-JDGenie** - https://github.com/jd-opensource/joyagent-jdgenie - Notable industrial multi-agent system but general-purpose; supervisor pattern already covered.
- **Youtu-Agent** - https://github.com/TencentCloudADP/youtu-agent - General agent framework with a DeepSearch example; not a dedicated DR system.
- **AWorld** - https://github.com/inclusionAI/AWorld - Multi-agent training/runtime framework; infrastructure rather than a workflow.
- **AgentScope** - https://github.com/agentscope-ai/agentscope - General multi-agent framework where DeepResearch is an official example.
- **Anemoi** - https://github.com/Coral-Protocol/Anemoi - Low adoption (~370 stars) multi-agent topology experiment on GAIA.
- **X-Master (SciMaster)** - https://github.com/sjtu-sai-agents/X-Master - HLE-focused tool-augmented reasoning agent; low adoption and QA-oriented.
- **Open Research ANA (CopilotKit)** - https://github.com/CopilotKit/open-research-ANA - Interesting HITL research canvas but low adoption (~401 stars).
- **PaSa** - https://github.com/bytedance/pasa - Narrow academic paper-search agent (crawler/selector), not a report-writing workflow.
- **DeepDive** - https://github.com/THUDM/DeepDive - RL-trained deep search model with lower adoption than the selected open-weight models.
- **Chain-of-Agents / Agent Foundation Models (AFM)** - https://github.com/OPPO-PersonalAI/Agent_Foundation_Models - Model/training release backing O-Researcher; not a workflow.
- **Open-AgentRL (DemyAgent / RLAnything)** - https://github.com/Gen-Verse/Open-AgentRL - Agentic-RL training stack; training axis already covered by selected models.
- **OpenSearch-VL** - https://github.com/shawn0728/OpenSearch-VL - Multimodal training recipe; low adoption and out of the text-report scope.
- **HiRA** - https://github.com/RUC-NLPIR/HiRA - Low adoption (~65 stars) planner/executor decoupling method.
- **ManuSearch** - https://github.com/RUCAIBox/ManuSearch - Minimal adoption (~36 stars).
- **SearchClaw** - https://github.com/RUC-NLPIR/SearchClaw - Very new, low-adoption harness (~110 stars).
- **AutoSurvey** - https://github.com/AutoSurveys/AutoSurvey - Narrow survey-writing pipeline; lower adoption than STORM in the same niche.
- **LLMxMapReduce-V2 / SurveyGO** - https://github.com/thunlp/LLMxMapReduce - Long-input survey generation method; retrieval/iteration is secondary to long-context writing.
- **SurveyForge** - https://github.com/Alpha-Innovator/SurveyForge - Survey writer plus benchmark; narrow and lower adoption.
- **Ai2 ScholarQA** - https://github.com/allenai/ai2-scholarqa-lib - Literature synthesis library with low adoption; overlaps the selected PaperQA2.
- **The AI Scientist-v2** - https://github.com/SakanaAI/AI-Scientist-v2 - Autonomous experimental science via tree search, not web deep research.
- **InternAgent (NovelSeek)** - https://github.com/InternScience/InternAgent - Autonomous scientific discovery framework (idea -> experiment), different category.
- **RD-Agent** - https://github.com/microsoft/RD-Agent - R&D automation that runs experiments; not a search-read-synthesize research workflow.
- **Robin (FutureHouse)** - https://github.com/Future-House/robin - Hypothesis-generation and data-analysis system for lab science; out of scope.
- **autoresearch (karpathy)** - https://github.com/karpathy/autoresearch - Agents running ML training experiments (automated science); no search/read/cite research loop despite huge star count.
- **last30days-skill** - https://github.com/mvanhorn/last30days-skill - Packaged agent skill/prompt for a host agent, not a standalone end-to-end research system.
- **DeepResearch Bench** - https://github.com/Ayanami0730/deep_research_bench - Benchmark and evaluation harness only.
- **Mind2Web 2** - https://github.com/OSU-NLP-Group/Mind2Web-2 - Benchmark with an Agent-as-a-Judge harness; not an agent.
- **AstaBench** - https://github.com/allenai/asta-bench - Benchmark suite and eval harness only.
- **DeepResearchEval** - https://github.com/Infinity-AILab/DeepResearchEval - Benchmark/evaluation framework only.
- **openai/simple-evals (BrowseComp)** - https://github.com/openai/simple-evals - Benchmark scoring implementation only.
- **Awesome Deep Research (DavidZWZ)** - https://github.com/DavidZWZ/Awesome-Deep-Research - Curated index/survey companion, not a workflow.

## Methodology

- Discovery: 6 parallel agents, each searching through a different lens (GitHub, curated lists, academic releases, vendor reference implementations, community comparisons, Hugging Face Hub), plus a completeness critic. 193 unique candidates after merging.
- Curation: one agent merged duplicates and selected up to 16 projects for depth, ordered by notability; everything else is in the appendix.
- Profiling: one agent per project read the README, repository metadata, and the core workflow source files, then wrote the report.
- Verification: an independent adversarial agent per project tried to refute the key claims against the live repository; an editor agent applied corrections where issues were found.
- Synthesis: one agent wrote the executive summary, taxonomy, comparison table, and recommendations from the verified profiles.
- All agents ran on Claude Opus 5 at high reasoning effort.