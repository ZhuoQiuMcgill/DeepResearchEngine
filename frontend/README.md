# INSE 691 frontend

The existing editable React Flow UI is ported from WHYKEYSAY/INSE-691-Project (abf3e09) into the formal DeepResearchEngine repository. This directory uses the public RunService API; it does not copy the previous model launcher or snippet-only search backend.

## Start
From the repository root, run the Python service in one terminal:

```powershell
uv sync --locked
uv run --locked ebd --store local/ui-store serve --port 8765 --origin http://127.0.0.1:5180
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5180. For another local backend, copy `.env.example` to `.env.local` and set `ENGINE_BASE_URL` to its `/api/v1` URL. The UI server only accepts a loopback Engine URL. Python owns the store and credentials; JavaScript does not open the database or call providers directly.

## Models
Choose an Engine profile in the header. Catalog availability does not mean credentials are present. DeepSeek/OpenAI need the corresponding key in ignored `local/.env` at the repository root. Custom models must be registered by trusted Python host configuration. The old NInfer service is not a vLLM deployment and is deliberately not represented as one. No local model configuration or secrets were copied.

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
