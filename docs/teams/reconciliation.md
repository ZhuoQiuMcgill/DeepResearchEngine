# Joint design reconciliation queue

Status: DRAFT integration review. All four team proposals are delivered.
The private Git repository and shared contribution rules are established;
runtime implementation remains unauthorized. PM owns this document and
reconciles changes with the affected owners before a shared contract revision.

## Delivered inputs

- `designs/agent-container-design.md`
- `designs/cli-toolset-design.md`
- `designs/storage-design.md`
- `designs/connections-design.md`
- `../research/free-search-fetch.md`

PM saved-file QA read all nine design/status/research files as UTF-8,
checked paired code fences, and parsed all five JSON example blocks.
These checks passed. They verify document integrity, not the proposed
runtime behavior or agreement among the APIs.

## Questions that must become one shared contract

| Topic | Current difference / required resolution | Owners |
| --- | --- | --- |
| Retry identity | Container proposes fresh action IDs; Storage groups attempts under logical actions. Define action/attempt/event IDs and uncertain-append deduplication once. | Container, Storage, Connections |
| Compatibility fields | `schema_major` and `schema_version` differ. Choose one wire compatibility field and separate definition/extraction revisions. | All |
| Lifecycle names | `run.accepted` and `agent.started` differ. Define distinct semantic phases only where needed and one canonical producer for each. | Container, Storage |
| Storage causality | Connections allocates commit action IDs while Storage reuses causal action/attempt plus operation ID. Define dispatch versus persistence operation identity and lookup after uncertain commit. | Storage, Connections, Toolset |
| CLI bridge | Three teams prefer bounded launcher-mediated preparation/commit/read injection for the initial three tools. Finalize internal/public schemas and authority; no final transport chosen yet. | Toolset, Storage, Connections |
| Standalone recording | Specify the shared trusted standalone entry point and exactly one lifecycle producer, without duplicating Container hooks or adding an unrecorded bypass. | Container, Toolset, Connections, Storage |
| Snapshot locators | Align one-based physical PDF pages, end-exclusive ranges, empty pages/unit counts, byte caps and continuation input. | Storage, Toolset |
| Resource limits | Proposed JSON/raw/text/index caps and fetch concurrency are untested. Define enforcement and validate peak memory; small input bytes do not bound PDF expansion. | Toolset, Container, Connections |
| Durability profile | Storage proposes DELETE journal plus synchronous=EXTRA baseline and opt-in WAL with a patched SQLite check. Reconcile acknowledgment/recovery and verify the actual linked runtime, preserving the shared environment. | Storage, Container |
| Child execution | Align permission attenuation, child scope/export, shared lineage limits, admission, cancellation, leases/revocation, and terminal ownership. | Connections, Container, Storage |
| Provider profiles | DeepSeek model/thinking and Qwen deployment manifest remain configurable open choices; gpt-6-luna is fixed. Do not block common interfaces on missing local deployment or claim live validation. | Container, Connections, PM |

The launcher-mediated bridge is the converging proposal, not a reason to
install a broker or implement IPC now. Public fetch success must follow a
durable complete snapshot receipt, even when its worker exited zero earlier.
Filesystem artifact publication and SQLite metadata are separate durability
boundaries requiring recovery, not a joint atomic transaction.

## Decisions already recorded

Use `decisions.md` for the selected free search/fetch design stack and its
search availability/URL-fidelity gate. Use root `CONTRIBUTING.md` for the
single uv/lockfile environment, account-linked noreply author, path ownership,
and PM-only serialized Git operations. Teams do not solve interface
differences through competing branches or edits to shared files.

PM coordinates narrow owner revisions after these drafts are committed.
The resulting shared interface design must be concrete and reviewable before
the user is asked to approve implementation.
