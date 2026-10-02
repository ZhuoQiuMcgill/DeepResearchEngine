# Run Baseline revision 2

`baseline@2` answers an arbitrary research question through planning, bounded
search/fetch rounds, selected-evidence analysis, writing and review. It uses real
network tools, Storage and model calls. The four roles are tool-free; Workflow
components acquire and select evidence. See the [architecture](../architecture/baseline.md)
for publication, stopping and review semantics.

## Select the version and environment

From the repository root, use Python 3.11+ and the locked uv environment:

```shell
uv sync --locked
uv run --locked deepresearch methods
```

Bootstrap exposes `baseline@1`, `baseline@2` and `example.echo@1`. The request
still defaults to `method_revision: 1`; **send revision 2 explicitly** for the
formal method. Wire `schema_version` stays 1. Revision 2 pins Planner 1, Analyst 1,
Writer 2 and Reviewer 1. V1 remains available with its own parameter schema.
The historical `deepresearch baseline` command runs a separate single-Agent
workflow; use `deepresearch research` for registered methods.

Choose a configured profile/model pair from `GET /api/v1/profiles`; the example
uses `deepseek` / `deepseek-flash`. Put the selected provider credential in the
ignored `local/.env` using [.env.example](../../.env.example). Preserve an existing
file; environment values take precedence. Credentials and endpoints stay on the
host. Model calls consume provider usage; `example.echo@1` is the separate
credential-free integration method over real Storage.

Use a separate ignored store for each developer. One Engine process owns a store;
stop the HTTP host before opening that same directory with a CLI reader.

## Request and parameter limits

The [input schema](../../src/deepresearch/methods/baseline/resources/2/input.schema.json)
and [parameter schema](../../src/deepresearch/methods/baseline/resources/2/parameters.schema.json)
are authoritative. `input` is a closed object with one required nonblank
`question` (1–8,192 characters). `parameters` is also closed: misspelled or unknown
keys are rejected. The same JSON request is used by Python, CLI and HTTP.

```json
{
  "schema_version": 1,
  "client_request_id": "urban-heat-v2-001",
  "method_id": "baseline",
  "method_revision": 2,
  "input": {"question": "What evidence supports urban tree planting to reduce heat, and what are its limitations?"},
  "parameters": {
    "max_rounds": 2,
    "max_queries": 2,
    "max_sources": 4,
    "max_report_attempts": 2,
    "context_tokens": 6000
  },
  "profile_ref": "deepseek",
  "model_ref": "deepseek-flash",
  "timeout_seconds": 600.0
}
```

| Parameter | Allowed values | Effective default | Meaning |
| --- | --- | --- | --- |
| `max_rounds` | Integer 1–3 | 2 | Research-round cap |
| `max_queries` | Integer 1–4 | 2 | Literal search queries per round |
| `max_results` | Integer 1–10 | 5 | Results requested per discovery tool call |
| `max_sources` | Integer 1–8 | 4 | Attempted unique source URLs across the whole method, including failures |
| `max_report_attempts` | Integer 1–2 | 2 | Maximum Writer/Reviewer draft pairs |
| `context_tokens` | Integer 512–12,000 | 6,000 | Selected assembled evidence token policy |
| `max_context_bytes` | Integer 1,024–32,768 | 32,768 | Assembled evidence UTF-8 byte cap |
| `max_scan_bytes` | Integer 1,024–262,144 | 131,072 | Saved-text scan allowance per source, per round |
| `strict_tokens` | Boolean | `false` | Require verified model-specific evidence measurements |
| `queries` | Up to 4 unique strings, 1–4,096 characters each | `[]` | Override Planner search queries; length must also be at most `max_queries` |
| `search_tools` | 1–3 unique registered names | `["web.search", "scholar.crossref.search"]` | Ordered discovery fallback tools |
| `source_urls` | Up to 8 unique HTTP(S) URLs, 1–8,192 characters each | `[]` | First-round candidates, subject to selection and remaining source allowance |

Allowed `search_tools` are `web.search`, `scholar.crossref.search` and
`scholar.openalex.search`. OpenAlex also needs the host's explicit budget admission
(`--admit-openalex`); a method parameter does not grant it. Executed queries must
be nonblank and fit 4,096 UTF-8 bytes; URLs must fit 8,192 UTF-8 bytes and have no
embedded credentials. `queries`, `search_tools` and `source_urls` defaults above
come from method execution. Planner still runs with supplied queries or URLs.

Top-level `timeout_seconds` must be greater than 0 and at most 1,800 (default
600). All rounds, tools and child roles share the root's deadline, cancellation
and lineage budgets. These method parameters do not replenish those budgets.
Default shared `storage_writes=1024` accommodates formal-flow recording, including
child records and node projections. Deployments may explicitly narrow the
allowance; other limits remain unchanged. The entire tree shares it, so the host
does not guarantee every maximum parameter can be consumed simultaneously.

`context_tokens` covers evidence blocks including provenance headers. It does
not cap every role's complete prompt, model output or provider spend. Estimated
measurements are labelled; `unknown` counts are null. Strict mode requires a
registered tokenizer for the target model, and is not a promise of exact provider
token accounting. Observed provider usage is a separate run aggregate.

The four formal role resources explicitly set `max_context_tokens=131072` and
`max_task_input_bytes=131072`. The current provider preflight conservatively
counts each rendered UTF-8 byte as an estimated token; the complete request
includes instructions, plan, analysis and, for Reviewer, the draft. This is
separate from the evidence estimator and accommodates their combined inputs.
It does not describe the model's native context size. A vLLM deployment's
declared ceiling can narrow the effective capacity, and host limits remain
independent. Oversized combined inputs fail before model dispatch.

## CLI

This PowerShell example generates a fresh intent ID and invokes v2 directly:

```powershell
$request = @{
    schema_version = 1
    client_request_id = "baseline-v2-" + [guid]::NewGuid().ToString("N")
    method_id = "baseline"
    method_revision = 2
    input = @{ question = "What evidence supports urban tree planting to reduce heat, and what are its limitations?" }
    parameters = @{ max_rounds = 2; max_queries = 2; max_sources = 4; max_report_attempts = 2; context_tokens = 6000 }
    profile_ref = "deepseek"
    model_ref = "deepseek-flash"
    timeout_seconds = 600.0
} | ConvertTo-Json -Depth 8
$run = $request | uv run --locked deepresearch --store local/my-baseline-v2 research | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Research failed; inspect the returned error." }
uv run --locked deepresearch --store local/my-baseline-v2 research --show $run.run_id
uv run --locked deepresearch --store local/my-baseline-v2 research --sources $run.run_id
uv run --locked deepresearch --store local/my-baseline-v2 research --report $run.run_id --output local/report.md
```

The start command waits for owned execution to settle, prints the run view, and
exits 0 for success or 2 for failure. Check the exit code before relying on later
reads. Rejected drafts can be retained even when no final report is available.

For a POSIX shell, stdin redirection also works:

```shell
uv run --locked deepresearch --store local/my-baseline-v2 research < examples/baseline-request.json
```

Inspect the example's `method_revision` and use a new `client_request_id` for new
intent. Repeating the same full request and identity returns the original run,
including after restart; changing any field under that identity is a conflict.

To check the CLI with no model or network consumption:

```powershell
'{"schema_version":1,"client_request_id":"echo-cli-001","method_id":"example.echo","method_revision":1,"input":{"message":"Hello research team"}}' | uv run --locked deepresearch --store local/my-echo research
```

## HTTP, SSE and retained reads

Start the host in another terminal:

```shell
uv run --locked deepresearch --store local/my-http-baseline serve --port 8000 --origin http://localhost:5173
```

Open `http://127.0.0.1:8000/docs` for the current OpenAPI contract. Run the following
PowerShell commands against the loopback host. This launches real Baseline model
and network work; to exercise admission/SSE/report/artifact reads without those
calls, substitute `example.echo`, revision 1 and `input = @{ message = "Hello" }`.
Echo has no acquired sources.

```powershell
$base = "http://127.0.0.1:8000/api/v1"
Invoke-RestMethod "$base/methods"
$request = @{
    schema_version = 1
    client_request_id = "baseline-http-" + [guid]::NewGuid().ToString("N")
    method_id = "baseline"
    method_revision = 2
    input = @{ question = "What evidence supports urban tree planting to reduce heat, and what are its limitations?" }
    parameters = @{ max_rounds = 2; max_queries = 2; max_sources = 4; max_report_attempts = 2 }
    profile_ref = "deepseek"
    model_ref = "deepseek-flash"
    timeout_seconds = 600.0
} | ConvertTo-Json -Depth 8
$run = Invoke-RestMethod -Method Post -Uri "$base/research-runs" -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($request))
$runId = $run.run_id
curl.exe --fail -N "$base/research-runs/$runId/events/stream?after_seq=0&limit=100"
do {
    $view = Invoke-RestMethod "$base/research-runs/$runId"
    if ($view.active) { Start-Sleep -Milliseconds 200 }
} while ($view.active)
$view | Select-Object status, recording_status, terminal_event_receipt, report_ref, error
Invoke-RestMethod "$base/research-runs/$runId/usage"
```

POST returns 202 for admitted work, not a completed report. Consume until
`active=false`; success needs `status="succeeded"`, `recording_status="complete"`
and committed terminal/completion evidence. SSE contains saved events, including
child-role activity, rather than streamed model tokens. A large `workflow.finished`
event can omit `nodes` and contain `node_count`/`nodes_sha256`; use the persisted
run view and node events for complete nodes. Its `id` is the committed
sequence. Reconnect with `Last-Event-ID` set to a sequence actually received;
with both it and `after_seq`, replay starts after their maximum. Disconnecting
SSE leaves the run executing. `POST /research-runs/{run_id}/cancel` requests
cancellation; keep inspecting until the view settles.

Read a source selected for the final context from the saved snapshot:

```powershell
$sources = Invoke-RestMethod "$base/research-runs/$runId/sources"
$selected = @($view.context_plan.selections | Where-Object { $null -ne $_ })
if ($selected.Count -gt 0) {
    $itemId = $selected[0].item_id
    $source = $sources.items | Where-Object { $_.item_id -eq $itemId } | Select-Object -First 1
    if ($null -ne $source.page_count) { $kind = "pages"; $count = $source.page_count; $window = 10 }
    else { $kind = "lines"; $count = $source.line_count; $window = 20 }
    if ($count -gt 0) {
        $read = @{ range = @{ kind = $kind; start = 1; end_exclusive = [Math]::Min($count + 1, $window + 1) }; max_text_bytes = 16384; continuation = $null } | ConvertTo-Json -Depth 6
        Invoke-RestMethod -Method Post -Uri "$base/research-runs/$runId/sources/$itemId/read" -ContentType "application/json" -Body $read
    }
}
```

Ranges are one-based and end-exclusive, limited to 200 lines or 10 physical
pages; each read returns at most 65,536 bytes. If
`has_more_in_requested_range=true`, reuse the returned `continuation` with the
same source/range/allowance. After a host reopen, begin a fresh range read.
Reading another saved passage does not change the evidence originally delivered
to Analyst/Writer. These reads never refetch the source.

Download the accepted report and inspect the result artifact:

```powershell
if ($view.status -eq "succeeded" -and $view.recording_status -eq "complete" -and $view.report_ref) {
    $bytes = [IO.MemoryStream]::new()
    try {
        $offset = 0
        do {
            $chunk = Invoke-RestMethod "$base/research-runs/$runId/report?start=$offset&max_bytes=65536"
            $part = [Convert]::FromBase64String($chunk.data)
            $bytes.Write($part, 0, $part.Length)
            $offset = $chunk.next_offset
        } while (-not $chunk.eof)
        [IO.File]::WriteAllBytes((Join-Path (Get-Location) "baseline-report.md"), $bytes.ToArray())
    } finally { $bytes.Dispose() }
}
Invoke-RestMethod "$base/research-runs/$runId/objects?limit=100"
if ($view.result_manifest_ref) {
    $artifactId = $view.result_manifest_ref.artifact_id
    Invoke-RestMethod "$base/research-runs/$runId/artifacts/$($artifactId)?start=0&max_bytes=65536"
}
```

Report and artifact responses contain base64 `data`, zero-based byte `start`,
`next_offset`, `eof`, chunk `byte_length`, `total_bytes`, media type and full-object
SHA-256. Follow `next_offset` until `eof`, concatenate decoded bytes, then decode
UTF-8 or verify the full digest. Individual chunks can split a Unicode code point.
Use `/objects` and its cursor to discover owned artifact/snapshot/checkpoint
references. Generic artifact reads accept artifact IDs, not snapshot/checkpoint
IDs. The full canonical request is retained as `research-request.json`; find
its `request_ref` in the method manifest or `workflow.accepted` event, not a new
RunView field. Input, plan, analyses, drafts, reviews and validation/result
artifacts are inspection material; a retained draft is not automatically an
accepted report. If Runtime output validation fails, its raw artifact is only
diagnostic evidence: `output_ref` remains null and there is no valid export.

## Interpret a result

The result manifest's `stop_reason` is `evidence_sufficient`, `source_limit`,
`no_new_queries` or `round_limit`. They explain why acquisition/analysis stopped,
not a proof of complete knowledge. Inspect round analysis artifacts for `gaps`,
source failures, selected ranges and truncation. Reports must preserve material
limitations and cite exact `[source-id]` labels from the final selected context.
A fetched but unselected source cannot support a report citation. Reviewer uses
model judgment plus deterministic structure/label checks; acceptance does not
verify external factual truth.

The run's `/usage` aggregates observed attempts from all four roles and every
executed round/draft. `known_subtotals`, `per_attempt_usage_refs`,
`unknown_attempt_ids` and completeness retain what providers actually reported;
missing counts stay unknown. Evidence estimates are not billed usage.

Errors, cancellation, unknown commits and incomplete cleanup stop the method.
Recorded ordinary source failures can leave a successful subset, and saved
sources/artifacts remain readable after a failed run. Exhausted draft review
produces `REPORT_REVIEW_FAILED` and no accepted final report. Reopen reads durable
facts; interrupted runs have `automatic_resume=false`. A checkpoint is not
permission to repeat external effects.

Optional [Hooks](extensions.md) observe node lifecycle or subset/reorder known
candidate/context IDs. A complete baseline requires no installed extensions.
See [ResearchRun API](research-service.md) for generic contracts and
[research acceptance](../research-acceptance.md) for the checks actually performed.
