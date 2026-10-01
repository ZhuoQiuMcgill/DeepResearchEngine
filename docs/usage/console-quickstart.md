# Console integration walkthrough

Start with [team setup](../team-start.md). This walkthrough exercises the actual
local HTTP API from PowerShell. It creates a bounded bibliographic lookup agent,
runs one task, polls activity and saves the exact report bytes. It demonstrates
the console integration lifecycle; bibliographic metadata is not full-text
research evidence. See [service reference](service.md) for all routes and bounds.

## 1. Start the backend

From the repository root, in terminal A:

```powershell
uv run --locked ebd --store local/my-console-store serve --port 8000 --origin http://localhost:5173
```

In terminal B, also at the repository root:

```powershell
$ErrorActionPreference = 'Stop'
$ebdApi = 'http://127.0.0.1:8000/api/v1'
Invoke-RestMethod "$ebdApi/health"
Invoke-RestMethod "$ebdApi/profiles"
Invoke-RestMethod "$ebdApi/tools"
Invoke-RestMethod "$ebdApi/agents"
```

Health should report `ready=true`. A fresh service has no agent definitions.
These calls require no model key. OpenAPI is at
`http://127.0.0.1:8000/openapi.json`, with a checked-in
[offline copy](../api/openapi.json).

## 2. Register an agent

```powershell
$ebdDefinition = @{
    schema_version = 1
    agent_id = 'console-quickstart'
    revision = 1
    instructions = 'Call scholar.crossref.search once with the supplied query and max_results=2. Return Markdown summarizing the returned titles and DOI links. Label this as bibliographic metadata; do not claim to have read full text.'
    profile_ref = 'deepseek'
    model_ref = 'deepseek-flash'
    allowed_tools = @(@{ name = 'scholar.crossref.search'; revision = 1 })
    output_mode = 'text'
    output_media_type = 'text/markdown'
    output_schema = @{ type = 'string' }
    limits = @{
        max_run_seconds = 180
        max_model_seconds = 45
        max_model_calls = 3
        max_tool_calls = 2
        max_tool_attempts = 2
        max_output_tokens_per_call = 512
    }
}
$ebdRegistered = Invoke-RestMethod "$ebdApi/agents" -Method Post `
    -ContentType 'application/json' -Body ($ebdDefinition | ConvertTo-Json -Depth 10)
$ebdRegistered.agent_ref
$ebdReportExtension = 'md'
```

Registration returns HTTP 201 and the agent reference. Registration alone makes
no model call. Repeat the same definition/revision to reuse it; changed content
needs a new revision. Definitions are process-local and must be registered on
each service startup. A frontend can offer registration; an application can
also register its definitions in trusted Python configuration.

The three output fields above explicitly select the defaults: Markdown text,
validated as a string. `output_media_type` labels the saved artifact; the string
schema does not validate Markdown syntax. Changing the output mode, media type
or schema under the same agent ID requires a new `revision`. Inspect the saved
definition through `GET /api/v1/agents`.

### Register structured JSON output instead

After the registration block above, optionally run this alternative. It reuses
the same profile, tools and execution limits under a different agent ID, and
sets `$ebdRegistered` so the remaining walkthrough starts this JSON agent.

```powershell
$ebdJsonDefinition = $ebdDefinition.Clone()
$ebdJsonDefinition.agent_id = 'console-quickstart-json'
$ebdJsonDefinition.instructions = 'Call scholar.crossref.search once with the supplied query and max_results=2. Return only a JSON object, without Markdown fences or commentary, with kind="bibliographic_metadata" and entries containing title (string) and doi (string or null) for each result. Include no other fields and use null for an unavailable DOI. Do not claim to have read full text.'
$ebdJsonDefinition.output_mode = 'json'
$ebdJsonDefinition.output_media_type = 'application/json'
$ebdJsonDefinition.output_schema = @{
    type = 'object'
    properties = @{
        kind = @{ type = 'string'; const = 'bibliographic_metadata' }
        entries = @{
            type = 'array'
            maxItems = 2
            items = @{
                type = 'object'
                properties = @{
                    title = @{ type = 'string' }
                    doi = @{ type = @('string', 'null') }
                }
                required = @('title', 'doi')
                additionalProperties = $false
            }
        }
    }
    required = @('kind', 'entries')
    additionalProperties = $false
}
$ebdRegistered = Invoke-RestMethod "$ebdApi/agents" -Method Post `
    -ContentType 'application/json' -Body ($ebdJsonDefinition | ConvertTo-Json -Depth 10)
$ebdRegistered.agent_ref
$ebdReportExtension = 'json'
```

JSON mode requires `application/json` and a JSON Schema for the parsed value.
The Runtime parses and validates the final response locally before publishing
successful output. Invalid JSON or a schema mismatch produces
`status="validation_failed"` with no successful `output_ref`; these HTTP fields
do not enable provider-native strict schema enforcement. Use the three flat
HTTP fields shown here, not `output_format` or the Python-only
`AgentDefinition.output_contract`. See the
[output contract reference](service.md#agent-output-format) for validation,
artifact and Python differences.

## 3. Start and observe a real run

This step needs `DEEPSEEK_API_KEY` in the backend's `local/.env` or environment.
It makes real DeepSeek and Crossref requests.

```powershell
$ebdRequest = @{
    schema_version = 1
    agent_id = $ebdRegistered.agent_ref.agent_id
    revision = $ebdRegistered.agent_ref.revision
    input = 'Environment Based Design Yong Zeng'
    timeout_seconds = 180
    limits = @{ model_calls = 3; tool_calls = 2 }
}
$ebdHandle = Invoke-RestMethod "$ebdApi/runs" -Method Post `
    -ContentType 'application/json' -Body ($ebdRequest | ConvertTo-Json -Depth 10)
$ebdRunId = $ebdHandle.run_id
$ebdAfter = 0
$ebdPollUntil = [DateTime]::UtcNow.AddSeconds(210)
do {
    $ebdView = Invoke-RestMethod "$ebdApi/runs/$ebdRunId/status"
    do {
        $ebdPage = Invoke-RestMethod "$ebdApi/runs/$ebdRunId/events?after_seq=$ebdAfter&limit=100"
        $ebdPage.events | ForEach-Object { $_.event.kind }
        $ebdAfter = $ebdPage.next_after_seq
    } while ($ebdPage.has_more)
    if ($ebdView.active) {
        if ([DateTime]::UtcNow -gt $ebdPollUntil) {
            throw "Polling stopped; inspect or cancel run $ebdRunId. Do not resubmit it automatically."
        }
        Start-Sleep -Seconds 1
    }
} while ($ebdView.active)
$ebdView | Select-Object run_id,status,active,recording_status
$ebdResult = Invoke-RestMethod "$ebdApi/runs/$ebdRunId/result"
$ebdUsage = Invoke-RestMethod "$ebdApi/runs/$ebdRunId/usage"
$ebdUsage.usage
```

The start response is HTTP 202 with an accepted handle. It is not the completed
report. Retain the run ID in client state. Refreshing or disconnecting the
browser does not cancel the owned execution. If a start response is lost, inspect
the run catalog before retrying: POST start has no client idempotency key.

Use `next_after_seq` exactly; store sequences can have gaps for a selected run.
During execution, token observations are in `model.outcome` events; terminal
`/usage` provides the aggregate. Show nullable counts as unknown.

## 4. Download the saved report

```powershell
if (-not $ebdResult.available -or $ebdResult.status -ne 'succeeded' -or
    $ebdResult.recording_status -ne 'complete' -or
    $ebdResult.persistence_state -ne 'committed' -or -not $ebdResult.output_ref) {
    $ebdResult | ConvertTo-Json -Depth 10
    throw 'Run did not deliver a committed successful report'
}
$ebdArtifactId = $ebdResult.output_ref.artifact_id
$ebdOffset = 0
$ebdBytes = [System.IO.MemoryStream]::new()
try {
    do {
        $ebdChunk = Invoke-RestMethod "$ebdApi/runs/$ebdRunId/artifacts/$ebdArtifactId`?start=$ebdOffset&max_bytes=65536"
        $ebdDecoded = [Convert]::FromBase64String($ebdChunk.data)
        $ebdBytes.Write($ebdDecoded, 0, $ebdDecoded.Length)
        $ebdOffset = $ebdChunk.next_offset
    } until ($ebdChunk.eof)
    New-Item -ItemType Directory -Force local/client-reports | Out-Null
    $ebdReportPath = Join-Path (Get-Location) "local/client-reports/$ebdRunId.$ebdReportExtension"
    [System.IO.File]::WriteAllBytes($ebdReportPath, $ebdBytes.ToArray())
    Get-Item -LiteralPath $ebdReportPath | Select-Object FullName,Length
} finally {
    $ebdBytes.Dispose()
}
```

The report is read through the saved artifact reference, including multiple
chunks if necessary. In a browser, join the decoded byte chunks before UTF-8
decoding so a multibyte character crossing a chunk boundary remains intact.

To cancel an active run from a separate terminal or UI action:

```powershell
Invoke-RestMethod "$ebdApi/runs/$ebdRunId/cancel" -Method Post
```

Cancellation is cooperative; keep polling until `active=false`. After stopping
and restarting the backend with the same store, `/runs`, `/result`, `/usage`
and artifact reads can inspect saved terminals. Register definitions again
before starting new work. An interrupted run is not automatically resumed.

## Common integration failures

| Observation | Next action |
| --- | --- |
| `CREDENTIAL_MISSING` / HTTP 503 | Configure the selected backend profile's key; do not send it in browser requests. |
| `ORIGIN_DENIED` / HTTP 403 | Match the frontend's exact scheme, host and port with `--origin`. |
| `STORAGE_BUSY` | Use another local store or stop its existing Engine owner. |
| `REGISTRATION_CONFLICT` / HTTP 409 | Register changed content with a new revision. |
| `PROFILE_MISMATCH` / HTTP 422 | Select a profile/model pair returned by `/profiles`. |
| `SERVICE_BUSY` / HTTP 409 | Wait for capacity and inspect the existing run list. |
| Run fails after HTTP 202 | Read `/result` and `/events`; acceptance does not guarantee provider quota, source availability or success. |

The frontend can now implement run lists, status, progress, cancellation, report
viewing and token usage. Whole-mission launch/state is a separate application
contract agreed with the orchestrator team, as described in
[team start](../team-start.md#integration-rules-to-agree-before-parallel-work).
