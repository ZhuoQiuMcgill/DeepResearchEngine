# INSE 691 frontend

The existing editable React Flow UI is ported from WHYKEYSAY/INSE-691-Project (abf3e09) into the formal DeepResearchEngine repository. This directory uses the public RunService API; it does not copy the previous model launcher or snippet-only search backend.

## Start
From the repository root, run the Python service in one terminal:

```powershell
uv sync --locked
uv run --locked deepresearch --store local/ui-store serve --port 8765 --origin http://127.0.0.1:5180
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5180. For another local backend, copy `.env.example` to `.env.local` and set `ENGINE_BASE_URL` to its `/api/v1` URL. The UI server only accepts a loopback Engine URL. Python owns the store and credentials; JavaScript does not open the database or call providers directly.

## Models
Choose an Engine profile in the header. Catalog availability does not mean credentials are present. DeepSeek/OpenAI need the corresponding key in ignored `local/.env` at the repository root. Custom models must be registered by trusted Python host configuration.

For a running local NInfer service, set these host settings in ignored `local/.env` before starting `deepresearch serve`:

```dotenv
NINFER_BASE_URL=http://127.0.0.1:18086/v1
NINFER_MODEL=qwen38-ninfer-256k
```

The service registers a distinct loopback-only `ninfer` Chat Completions profile. The UI selects it by default when present. Thinking is disabled, temperature is 0.2 and output is bounded to 4096 tokens per model call. Start the model server separately; the Engine does not change its context/cache/MTP settings. The live local endpoint reported 262144 context tokens. No secrets are committed.

UI NInfer agents explicitly use a 258048 context allowance (262144 minus 4096 output tokens) and a 180-second per-call timeout, rather than the Runtime's 32768 / 45-second defaults. This allowance still uses the Engine's UTF-8 byte-size/4 token estimate (rounded up), not a tokenizer measurement. Tool attempts match the selected tool-call budget. Accumulated input that exceeds an allowance returns `CONTEXT_LIMIT_EXCEEDED` with safe numeric details.

UI agents opt into `finalize_on_limit`. Near the tool/model allowance, Runtime switches to a final answer with `tool_choice=none`. An oversized tool batch is declined in full and returned as not executed; a saved final answer may explicitly state insufficient source material. Tool limits, recording failures, cancellation, unauthorized calls and malformed arguments remain enforced. An answer being saved does not establish that every research question was answered. Search instructions request focused queries and reserve calls for reading.

## Features and mapping
- Existing canvas, draggable node library, node/edge editing, resize handles, dark mode, import/export, timeline and final Markdown report.
- Inspector tabs: Configuration, Performance, Output. Node metrics stay with the workflow history. The formal API reports token usage; context size, tokens/s and first-token timing stay unknown because this API does not expose them.
- Plan with AI registers a tool-free planner agent and reads its saved JSON output through the same RunService API.
- Each node registers an agent with a pinned Engine profile and tool revisions, then starts one Engine run. Searcher/Reader/Analyst may use the registered discovery, fetch and document-read tools; Request/Organizer/Writer work from supplied upstream output. The tool-call limit is bounded to 1–32.
- Tool/model/activity events are polled using committed sequence cursors, deduplicated by event ID and streamed into the timeline. Stop sends cooperative cancellation. Pause finishes the active node before pausing graph scheduling.
- A node completes only when execution succeeded, recording is complete and its saved output is committed. UTF-8 artifact chunks are joined before decoding. Truncated/disconnected responses are errors, not successful reports.
- History contains local workflow snapshots. Its Engine history button also reads persisted runs and reports from the backend, including after a service restart.

## Boundaries
The browser coordinates an acyclic graph sequentially. Independent nodes are separate Engine runs, not native child-agent invocations. Upstream text and public URLs are supplied as input; cross-run snapshot authority is not fabricated. Closing/reloading the tab does not resume the remaining graph automatically. Use Engine history to inspect an already admitted run before starting another.

Inputs are bounded to 200 KiB, report retrieval to 8 MiB. The Engine history view currently lists the latest 50 runs. Local workflow histories and Engine histories are distinct. A static file server alone cannot run this UI: use Vite dev/preview or port the small API bridge to your deployment server.

## Checks
`npm test` and `npm run build`. Adapter tests cover saved artifact chunks, event deduplication, incomplete recording, and premature stream termination. Root Python service tests exercise the actual Runtime and Storage with controlled model responses. A live model run still requires an Engine-supported configured profile; do not treat fixture tests as live model results.

## Upstream integration (October 2, 2026)

The UI branch includes upstream `c30ecb8`, canonical `deepresearch.*` modules and the server-side `baseline@3` method. The editable canvas still runs individual agents through the public Agent API; it does not implicitly start the formal Baseline workflow. Local NInfer and the opt-in final-answer policy remain supported. The OpenAPI snapshot includes that optional registration flag.

Live checks exercised Qwen planning, a tool-free Writer and a Reader with successful web.fetch/document.read calls through the UI bridge, with saved report retrieval and reported usage. Backend tests: 837 passed; frontend tests: 23 passed; frontend production build passed. The upstream model-free ResearchRun example also exercised HTTP/SSE, idempotency and report reads after restart. These checks do not measure a full 256K request or complete a live Baseline research run.
