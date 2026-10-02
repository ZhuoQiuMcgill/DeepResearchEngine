# Optional Workflow hooks

`ebd.extensions` supplies optional hooks independently of Workflow, method,
runner and application implementations. Its only platform dependency is the
shared `EngineError`/`Err` contract. Registration is explicit: this package
performs no method imports, plugin discovery, Storage access, network requests
or model calls. The host chooses the points and supplies a trusted recording
callback. An empty registry makes `observe` a no-op and `select` return a fresh
list containing the host's original IDs in their original order, including an
empty list. A complete base method must implement its own mandatory execution,
retention, usage, publication and lifecycle recording.

## Public API

```python
from ebd.extensions import (
    ExtensionRegistry, ExtensionSpec, HookDecision, HookDispatcher, HookEvent,
    ObserverHandler, ControlHandler, RecordCallback,
)

HookEvent(run_id, node_id, point, payload={})
ExtensionSpec(extension_id, revision, points,
              mode="observe", timeout_seconds=1.0, config={})
HookDecision(keep_ids=("candidate-a",))
registry = ExtensionRegistry()
registry.register(spec, handler)  # returns the pinned ExtensionSpec
registry.specs                  # immutable tuple ordered by extension_id

dispatcher = HookDispatcher(registry, record_async_callback)
await dispatcher.observe(event)                       # returns None
selected = await dispatcher.select(event, candidate_ids)  # returns list[str]
```

The observer signature is `async handler(event: HookEvent)`. Its return value
is ignored. The control signature is
`async handler(event: HookEvent, candidate_ids: tuple[str, ...]) -> HookDecision`.
Both accept async functions or objects with async `__call__`; synchronous
handlers and signatures incompatible with these positional arguments reject
registration. Configuration is an immutable snapshot on the spec. A trusted
host can capture that spec in the handler's closure; no live context or client
is injected. The handler code and any captured objects remain host-trusted.

`HookEvent`, `ExtensionSpec` and `HookDecision` are frozen values. Nested
metadata dictionaries become copied read-only mappings and lists/tuples become
copied tuples. Changing the original data after construction cannot change the
snapshot. Each value's `to_dict()` exports fresh JSON data. `HookEvent` exposes
`payload_digest`; `ExtensionSpec` exposes `config_digest`, both canonical
UTF-8 JSON SHA-256 strings with the `sha256:` prefix. Dictionary insertion order
and list-versus-tuple input do not change the digest. The digests describe the
metadata/configuration, not the executable handler code.

Each registry pins one exact revision per `extension_id`. Registering the same
spec and the identical handler object again is idempotent. Changed revision,
configuration, mode, points, timeout or handler rejects with
`EngineError("extension.registration_conflict", ...)`. Use a new registry to
activate a different revision; there is no implicit latest-version resolution
or replacement. `HookDispatcher` snapshots registrations at construction.
Finish registration before constructing it; later registrations affect only
new dispatchers. Within each dispatch, matching handlers run sequentially in
lexicographic `extension_id` order. Hosts serialize calls when a global ordering
of concurrently emitted events is required.

## Points and host responsibilities

The initial host conventions are:

| Point | Host boundary |
| --- | --- |
| `node.before` | Safe node metadata before its work starts |
| `node.after` | Safe result references/counts after work completes |
| `node.failed` | Safe failure category and references |
| `discovery.select` | Select/reorder admitted discovery candidate IDs |
| `context.select` | Select/reorder admitted saved context IDs |

Points are validated stable lowercase dotted names, such as
`acquisition.fetch.before` or `custom_2.rank.select`. Every segment begins with
a letter and contains lowercase letters, digits or underscores; the full name
has at least two segments and at most 128 characters. No central enum or method
import is required to add a point. The host defines and versions its semantics.
`node_id=None` permits a workflow-wide event. Observation and control dispatch
are separate: `observe` invokes only observers, and `select` invokes only
controls. To disable extensions, supply an empty registry or leave them
unregistered. A registration subscribed to another point has no effect.

The host must project safe metadata before constructing an event: opaque IDs,
counts, categories, digests and bounded reference descriptors. Do not put raw
source text, queries, prompts, responses, credentials or live Storage/network/
model clients in events or configuration. Native finite JSON values are the
only accepted metadata; arbitrary Python objects are never introspected or
serialized. Common private/content keys (including `text`, `content`, `body`,
`query`, `prompt`, `instructions`, `snippet`, `title`, `api_key`, `secret`,
`password`, `authorization`, `headers` and `cookies`) reject recursively.
These checks cannot identify a secret disguised as an ordinary metadata value;
the trusted host is responsible for semantic filtering. Hooks receive no
live authority, budget ledger, Storage binding or execution context through
this API.

Before `select`, the host builds its original candidate list from objects that
are currently permitted, with its normal acquisition/context constraints.
Every decision must be an exact `HookDecision`; dictionaries, subclasses,
arbitrary lists and extra action/settings fields are rejected. `keep_ids` must
be a tuple of unique IDs from the current list. A control hook may remove all
IDs or return a permutation. A later hook cannot reintroduce an ID removed by
an earlier one. Validation never accepts foreign IDs, enlarges the list,
modifies candidate objects or grants any new operation. The host must recheck
current grants, cancellation, deadlines and budgets, enforce final context/
resource limits, then freeze and record the actual request intent before
execution. Reordering alone does not prove that resource costs fit a budget.
The parent framework owns these checks and its complete base-method behavior.

## Recording and failures

The required signature is `async record_async_callback(kind, payload)`. The
callback must return only after durable platform recording is acknowledged;
it may return a receipt or `None`, and must raise on failure or return the
shared `Err(error)`. The dispatcher propagates raised exceptions and returned
`Err.error` unchanged. It does not interpret `None` as independent evidence of
commitment: the trusted callback owns that promise and its normal Storage
identity/reconciliation rules. Provide an adapter bound to the proper scoped
producer and event-kind grants. Payloads contain plain JSON and no live clients.

Each invoked hook produces exactly one attempted diagnostic:

| Kind | Outcome |
| --- | --- |
| `workflow.hook.observed` | Observer completed; its response has no authority |
| `workflow.hook.decision` | Control returned a validated selection |
| `workflow.hook.failed` | Timeout, handler error/cancellation, invalid control response or capacity rejection |

All include `schema_version: 1`, `run_id`, `node_id`, `point`, `payload_digest`,
`extension_id`, exact `revision`, `mode`, `config_digest` and `timeout_seconds`.
Control records also include `original_candidate_ids` and the current input
`candidate_ids`; successful decisions include validated `keep_ids`. Failures
include only a fixed `failure` category, never exception text, arbitrary error
details, rejected response values, event payloads or raw configuration.
Recording is awaited before the next handler and before returning a selection.
A recording failure stops dispatch; optional hooks cannot silently suppress a
mandatory diagnostic failure. There is no diagnostic retry or execution replay.

Observer errors/timeouts are isolated only after their failure diagnostic is
successfully recorded, allowing later observers to run. Invalid/failing controls
record a failure and raise `EngineError`; they never silently fall back to the
broader host list. Codes are `extension.invalid_decision`, `extension.failed`,
`extension.timeout` or `extension.capacity`. Invalid construction/registration
uses `extension.invalid_event`, `extension.invalid_spec`,
`extension.invalid_registration` or `extension.invalid_dispatcher`; invalid host
lists use `extension.invalid_candidates`. Caller task cancellation cancels the
active hook, attempts a `caller_cancelled` failure record and is re-raised.
A further cancellation or failed recording can prevent that record; the host's
mandatory lifecycle recording still owns execution completion.

For replay, retain the exact spec/handler revision and non-secret config in the
host's versioned catalog, plus the host's admitted candidate identities. Saved
hook records identify the pinned extension/configuration and validated input/
output ID order. Apply recorded decisions to the matching host inputs; do not
rerun hooks, reacquire authority or infer current permissions from a digest.
This package emits replay facts; it does not implement workflow resume/replay.

## Bounds and real timeout limits

The fixed profile bounds payloads to 16 KiB canonical JSON and configurations
to 8 KiB, at most eight levels below the root and 1,024 values including
containers. Strings have at most 512 UTF-8 bytes; metadata keys are ASCII names
of 1–64 characters beginning with a letter. Integers have at most 64 significant
bits and floats must be finite. Cycles and invalid Unicode are rejected.
Identities are opaque ASCII strings of 1–128 characters beginning with a letter
or digit and otherwise using letters, digits, `.`, `_`, `:`, `/` or `-`.
Candidate lists contain at most 128 unique IDs. Registries have at most 32
extensions, each with 1–32 unique points. Timeouts are positive finite seconds,
default 1, capped at 30. Count/byte/depth bounds are checked during copying.

The dispatcher runs at most 32 active handler tasks, including timed-out tasks
that have not settled. Timeouts request task cancellation and stop awaiting the
handler; a late result is discarded and never creates another decision record.
A handler that suppresses cancellation continues consuming capacity until it
settles. Further observer admission failures are diagnosed and isolated;
control admission failures are diagnosed and raise `EngineError`.

These are cooperative asyncio limits in the host process, not an OS sandbox.
A handler that blocks the event loop, uses native blocking code, allocates
unbounded memory or captures external capabilities cannot be forcibly stopped
by this package. Cancellation-resistant tasks can outlive dispatch and delay
host/event-loop shutdown. Only register trusted, yielding async callbacks;
untrusted execution would require a separate process boundary owned by the
host. Recording is outside the optional handler timeout. The host must bound
its Storage callback and overall hook-call/node/workflow deadlines under the
existing execution and recording budgets.

## Example

```python
from ebd.extensions import (
    ExtensionRegistry, ExtensionSpec, HookDecision, HookDispatcher, HookEvent,
)

async def build_and_select(record_async_callback):
    registry = ExtensionRegistry()
    spec = ExtensionSpec(
        "prefer-ranked", "r1", ("discovery.select",), mode="control",
        timeout_seconds=0.25, config={"keep_limit": 2},
    )

    async def prefer_ranked(event, candidate_ids):
        return HookDecision(candidate_ids[:spec.config["keep_limit"]])

    registry.register(spec, prefer_ranked)
    dispatcher = HookDispatcher(registry, record_async_callback)
    event = HookEvent("research-1", "discovery-1", "discovery.select", {
        "candidate_count": 3, "manifest_id": "manifest-1",
    })
    return await dispatcher.select(event, ["source-a", "source-b", "source-c"])
```

The injected callback commits the diagnostic through the host's existing
recorder. The host subsequently resolves the returned IDs and performs its
normal budget/authority validation before freezing the request intent.
Workflow/application integration is described in the
[method guide](workflows.md) and [Research API](research-service.md).

`await dispatcher.close(timeout_seconds=5)` cancels/drains owned handler tasks
and returns `CleanupReport`. A resistant callback produces incomplete cleanup
with retained resource identities; it is not silently abandoned. ResearchRunService
owns this call and merges Hook/session cleanup before confirming completion.

## Verification

```powershell
uv --cache-dir .uv-cache run --locked --offline pytest tests/extensions -q
```

Tests cover copied recursive immutability, bounds/private fields, no-extension
base behavior, exact revision conflicts, deterministic cumulative selections,
foreign/duplicate/invalid decisions, observer/control errors and timeouts,
cancellation, resistant-task capacity, mandatory recording failure and real
scoped SQLite Storage close/reopen of replay diagnostics. These tests require
no credentials, network or model calls. Method integration and real research
checks are recorded in [Stage 1/2 acceptance](../research-acceptance.md).
