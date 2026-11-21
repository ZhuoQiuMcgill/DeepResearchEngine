# INSE 691 Project guide

## Edit and plan
Add or drag nodes from the library. Edit their instructions and titles in the inspector and connect ports to define dependencies. Panels and cards can be resized. Workflows save on this device and can be exported/imported as JSON.

Choose **Local Qwen** or **API model** beside **Run workflow**. The selection applies to AI planning and all nodes in the next run. **Plan with AI** sends the research request to the selected model. Numeric search and reading-stage counts must match the resulting graph. All generated branches must lead to a Writer. A rejected plan leaves the existing canvas intact.

## Run and read
**Run workflow** previews the exact question, model, and task order before execution. Searchers retrieve public search-result snippets and source links. Nodes use the selected model to process their inputs. Search failures stop the run with a visible error. Data that sources do not provide should be listed as missing in the report.

Pause takes effect after the active node finishes. Step runs one node while paused. Stop aborts the active request. Keep this browser tab open while running because the browser coordinates the graph. Graph editing and model selection are locked during execution.

The timeline shows actual start/end times and each node's input, instruction, output and model. Click a row to expand its logs. Completion opens Final report; use Download report for a Markdown file. Recent runs retain the last five workflows and their events on this device. Historical demo records retain their original simulation text.

## Local setup
Use `npm run dev` with Local Qwen, or configure the API profile as described in the [README](../README.md) and use `npm run dev:ui` to skip local model startup. Open http://127.0.0.1:5178. Never place API credentials in browser fields or exported workflows.

## Scope
The current model profile handles one request at a time. Multiple graph branches do not imply simultaneous GPU inference. Each search retrieves up to ten results, bounded by the configured page budget. Search-provider rate limits and source freshness can affect results. Recursive graph loops, authenticated sources, multi-user storage, durable background jobs and full-page extraction are not implemented.

## Development
React, TypeScript, React Flow and Vite. Run npm test and npm run build. The server exposes /api/plan, /api/node, /api/planner and /api/telemetry. src/backend.ts remains an unused proposed adapter for a future standalone orchestration service.
