# Local baseline with Langfuse

This optional demo uses the unchanged baseline strategy and verbatim question
`What is EBD (Environment Based Design)?`. Its model runs locally, and its
researchers search/read downloaded papers through LangChain tools. It performs
no live web search. Keep it separate from the Haiku/Luna experiments: the model
and source access differ, so its result is not a fair cross-arm comparison.

The existing cloud profiles and provider-native web tools are unchanged.
Tracing uses the project's LangChain CallbackHandler and OpenTelemetry SDK.
Only loopback Langfuse endpoints are accepted by this demo's tracing connector.

## Prepare

```powershell
npm ci
npm run corpus:prepare -- --library "<downloaded EBD library>"
npm run langfuse:setup
```

Corpus preparation reads the downloaded PDFs and their existing catalog. It
preserves publication URLs and PDF hashes in ignored `local/ebd-corpus.json`.
It skips missing PDFs and PDFs without usable extracted text. It does not
download documents or invent substitutes for unreadable scanned pages.

The local model uses an OpenAI-compatible Chat Completions endpoint. Set these
in the ignored root `.env` if your service differs from the defaults:

```dotenv
LOCAL_MODEL_BASE_URL=http://127.0.0.1:18086/v1
LOCAL_MODEL_NAME=qwen38-local-256k
LOCAL_MODEL_CONTEXT_TOKENS=262144
LOCAL_CORPUS_PATH=local/ebd-corpus.json
```

`LOCAL_MODEL_CONTEXT_TOKENS` records the requested window; configure the actual
model server separately. The optional `scripts/serve-local-model.sh` requests
262144 total tokens, one slot, Q4_K_M weights and Q4 KV on llama.cpp. Choose
GPU UUIDs with `CUDA_VISIBLE_DEVICES`; it reserves a 4096 MiB margin per device
and never stops other GPU processes. An existing local server can be used
instead. Output is capped at 8192 tokens per call, temperature is 0.2, and
`chat_template_kwargs.enable_thinking=false` is passed explicitly.

The local profile sends no cloud model credentials. Its zero API cost excludes
electricity and hardware costs. Requested context capacity does not imply
that a run used the entire window, or establish a token-speed benchmark.

## Start Langfuse

The setup command generates machine-local secrets into ignored env files. It
never prints their values. From `deploy/langfuse`, run:

```shell
docker compose -p inse691-langfuse up -d
```

The UI is at http://localhost:3000. Login values are in the local
`deploy/langfuse/.env`: `LANGFUSE_INIT_USER_EMAIL` and
`LANGFUSE_INIT_USER_PASSWORD`. Do not commit this file or copy it into traces.

On this WSL machine the root disk was nearly full. Direct Windows-drive MinIO
storage also failed readback. The optional machine-specific
`scripts/mount-demo-storage.sh` creates a dedicated 20 GiB ext4 image on D:
only when that image does not exist, mounts it, and makes the mount visible
inside Docker's mount namespace. Run it as WSL root before starting MinIO,
including after WSL restarts. Set `LANGFUSE_MINIO_VOLUME` in the ignored deploy
env to `/mnt/inse691-langfuse-minio`. Other machines can retain the default
named volume. This script does not delete or resize other data.

## Run and inspect

```powershell
npm run langfuse:check
npm run research -- --strategy baseline --model local --task ebd
```

The first command sends a **no-model connectivity check**, distinct from an
actual research run, and confirms ingestion through Langfuse v4's
`/api/public/v2/observations` API. The full run returns its native trace URL in
`summary.json`. The call tree contains `plan`, `research`, `observe`,
`finalize`, `write`, individual generations, `search_local_documents` and
`read_local_document`. Concurrent researchers remain identifiable under their
own graph nodes, even when a one-slot local server queues their model calls.

Each researcher has eight document-tool calls. Excess parallel calls receive
correlated **not executed** results. Final-only generation retains native
tool history with `tool_choice=none`. Unknown tools fail, document IDs must
have appeared in search, and reaching the output limit is recorded as a
diagnostic rather than silently represented as complete text.

Read `report.md`, `summary.json`, `events.jsonl` and individual researcher
records under the run directory. A terminal `ok` means the graph produced
text; inspect diagnostics and citations before treating it as a finished
research report. Failed/interrupted attempts are retained, not hidden.

For a portable local waterfall with expandable inputs/outputs, export the
actual observations from Langfuse, then serve the generated artifact:

```powershell
npx tsx scripts/export-trace.ts "<completed run directory>"
npx tsx scripts/serve-trace.ts "<completed run directory>"
```

Open http://127.0.0.1:5182/. The HTML contains no API keys or external scripts.
Its logs and report remain private research content; exports stay under ignored
`local/`, not in the Git repository. It is a static snapshot; the native
Langfuse UI remains the source for live and later runs.

Reference: [Langfuse's current public API](https://langfuse.com/docs/api-and-data-platform/features/public-api)
and [LangChain integration](https://langfuse.com/integrations/frameworks/langchain).
