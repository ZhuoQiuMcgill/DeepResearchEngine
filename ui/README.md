# INSE 691 Project

Independent frontend for authoring and observing research workflows.

Run `npm ci`, then `npm run dev`. Open http://127.0.0.1:5178.
The port is fixed in `vite.config.ts`; do not append a port argument. If the port is already occupied, Vite reports an error instead of switching addresses.

`npm run build` creates the production build; `npm test` checks workflow integrity.

The app runs public web searches and sends model requests to the selected local or API model. Integration and usage: [docs/guide.md](docs/guide.md).

### Pick a model

Use **Model** beside **Run workflow** to select **Local Qwen** or **API model**. The selection applies to **Plan with AI** and every node in the next run. The selector marks profiles without server settings as unavailable.

- To use **Local Qwen**, connect a running local endpoint with `PLANNER_BASE_URL` and `PLANNER_MODEL` and run `npm run dev:ui`. Use `npm run dev` if you want the launcher to start a configured NInfer or llama.cpp installation.
- To use an **API model**, add `PLANNER_REMOTE_BASE_URL` (the base URL ending in `/v1`), `PLANNER_REMOTE_MODEL`, and, if required, `PLANNER_REMOTE_API_KEY` to the ignored `.env.local` file. Use `npm run dev:ui` to start the UI and its model adapter without starting a local model. Restart the server after changing settings.
- To use **both**, configure the API profile and run `npm run dev`. Switch in the **Model** menu without restarting. API keys belong in `.env.local` and must never have a `VITE_` prefix.

If you previously put an API endpoint in `PLANNER_BASE_URL`, move its URL, model, and key to the three `PLANNER_REMOTE_*` fields before starting the local model. The local launcher writes `PLANNER_BASE_URL` and `PLANNER_MODEL` for Qwen. Clear `PLANNER_API_KEY` if it held the remote key.

The API provider receives the question and the inputs needed for each model call, which can include search snippets and output from earlier tasks. The local profile sends its inference requests to your local model service. Search tasks still send their queries to DuckDuckGo in both profiles.

### AI request to nodes
Enter the research request and choose **Plan with AI**. The app sends the exact request to a configured OpenAI-compatible model through its local server. The model chooses task labels, instructions, roles and dependencies. The canvas changes only after a usable plan arrives; errors or cancellation preserve it. Explicit numeric requests such as `use 7 subagent for search` require exactly seven Searcher nodes. The UI no longer uses the fixed template as a fallback.

Use the provider's actual model ID. `npm run preview` also serves the adapter. An offline HTML preview can inspect and review run records. Live planning and execution require the server. Plans are limited to 64 tasks and 6,000 request characters, with a ten-minute request timeout. AI planning creates tasks. **Run workflow** executes them in dependency order.

### Timeline and appearance
Use the header Dark/Light button to save an appearance preference on this device. Run timeline shows one row per node with elapsed-time bars, status and log count. Click a row to expand its timestamped activity, output, input snapshot, instructions, model identifier and upstream node IDs. Replay limits the timeline to the selected event. Events export and recent run history retain these log snapshots; older runs still show their original messages. Times are wall-clock durations and include pauses. New runs contain actual model outputs. Older saved runs retain their original simulation labels.

### Resize the workspace
Drag the dividers beside the node library and inspector, above the timeline, or beside the research question to resize those panels. Double-click a divider to restore its default size. Focused dividers also support arrow keys and Home. Panel sizes are saved on this device and constrained to the available window size. Select a canvas node to reveal corner and edge resize handles; drag its body to move it. Node dimensions survive save, import and export. Node editing is disabled during a run.

Drag any node type from the left library onto the canvas to place a new node at the drop position, including after panning or zooming. The new node opens in the inspector. Clicking a library item still adds a node; adding nodes is disabled during a run.


### Live model performance
Select a node and open **Performance**, between Configuration and Output in the inspector. The app polls telemetry every 750 ms and shows provider-reported generation/prefill rates, input/output token counts, first-content latency, elapsed time, active context size and request configuration. Planning requests now consume provider SSE streams; final plan handling is unchanged. Missing provider fields remain blank. Token counts are never inferred from chunk or character counts. During input processing the provider may not send progress. Session usage is in memory and resets when the app server restarts; it covers planning and node requests from this app, not other clients. Current context comes from the running service metadata.

The NInfer preset uses a 262144-token context and one concurrent generation. llama.cpp Q4 is a selectable backup. Set `PLANNER_CUDA_VISIBLE_DEVICES` in `.env.local` to select a GPU for NInfer.



### Default local model: NInfer MTP3 / 256K
`npm run dev` starts or reuses the configured local model. For a new NInfer launch, set `PLANNER_NINFER_BIN` and `PLANNER_NINFER_MODEL_PATH` in `.env.local`. Set `PLANNER_NINFER_LIBRARY_PATH` if the installation requires extra shared libraries. For llama.cpp, use `PLANNER_LLAMA_BIN` and `PLANNER_LLAMA_MODEL_PATH`. On Windows these paths refer to files inside WSL.

- `npm run model:ninfer`: switch this project's owned model to NInfer on port 18086.
- `npm run model:q4`: switch it to llama.cpp Q4_K_M, Q4 KV, MTP2, 256K on port 8002.
- `npm run model:start`: start or reuse the selected engine.

A successful switch writes the endpoint, alias, engine and 256K minimum into ignored `.env.local`. Restart the UI server to reload them. Switching stops only a matching PID recorded by this project. Runtime logs are in ignored `.local-runtime/model.log`. Install model files, engines and CUDA dependencies locally.

Context is read from the active engine: `/v1/models` for NInfer, `/props` for llama.cpp. Planning refuses an active window below 262144. The response adapter uses streaming text and provider usage/timing fields; absent live counters remain blank rather than being guessed. Configuration status does not itself mean successful inference. Node execution and search use `/api/node` and share the same single-request model gate and telemetry.


### Actual execution and final report
Searchers request public DuckDuckGo HTML results, with up to ten distinct result snippets per task (or fewer if the page budget is lower). The query includes the subject and node title. No API key is needed. This first backend reads search snippets, not full pages, PDFs, or JavaScript-rendered statistics. Search outages, throttling and empty results stop the run with an explicit error rather than inventing sources. Research questions and node titles are sent to the search provider; model processing stays on the configured model endpoint.

Other roles process their instructions and upstream output through the selected model. Execution is sequential, even when the graph contains independent branches. Pause finishes the active node before pausing. Stop aborts its request. Failures retain completed node logs. Completion opens **Final report** with terminal node outputs and a Markdown download. Inputs, outputs and timestamps remain available in the timeline and run history.

An explicit second-stage count such as `8 for review` requires eight Reader nodes; the synthesis/writing path must receive all branches. If the model ignores counts or leaves a branch without a Writer, the existing canvas is preserved with an error. Old plans can be regenerated using **Plan with AI**. Search snippets may be incomplete or stale: the model is instructed to disclose missing dates and statistics rather than invent a definitive ranking.

Node metrics are correlated by request ID and saved with completed node events. Selecting a different node or replaying history never displays another request's metrics. Historical runs without recorded metrics show empty values. The header shows model activity and total tokens for the current app server session.
