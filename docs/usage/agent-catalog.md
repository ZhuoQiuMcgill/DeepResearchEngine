# Versioned Agent role catalog

`deepresearch.agent_catalog` loads resource bundles and compiles ordinary
`deepresearch.engine.contracts.AgentDefinition` objects. Register and execute those definitions
through the existing `Engine`. Engine, Runtime, provider profiles, tool bindings
and Storage retain execution authority, validation, recording and budgets.

The catalog does not open model connections, fetch evidence, register invocation
edges or issue grants. Importing and loading roles needs no credentials.
`baseline@4` pins `baseline.writer@4` and `baseline.reviewer@3`: the Writer's
final report and the Reviewer's issue strings use English. Earlier role bundles
remain available with their original instructions. The Workflow's separate
publication check rejects CJK narrative even if the model reviewer accepts it.

## Public interfaces

```python
from deepresearch.agent_catalog import AgentCatalog, AgentSpec, CatalogError

catalog = AgentCatalog()  # Packaged resources; independent of the current directory.
# AgentCatalog(root="path/to/trusted/roles") loads a host-owned resource directory.
spec = catalog.load("baseline.writer", 1)
# load(role_id: str, revision: int, *, expected_digest: str | None = None) -> AgentSpec

task = spec.render_task({"question": "What does the evidence support?",
                         "evidence": "[source-1] Host-selected retained source text."})
# render_task(input: dict[str, Any]) -> str

definition = spec.compile_definition(
    profile_ref="deepseek",
    model_ref="deepseek-flash",
    tools=(),
    limits={"max_model_calls": 1, "max_run_seconds": 60},
)
# compile_definition(*, profile_ref: str, model_ref: str,
#                    tools: Iterable[ToolRef] = (),
#                    limits: Mapping[str, Any] | None = None,
#                    agent_id: str | None = None) -> AgentDefinition

spec.validate_output("# Answer\n\nA supported finding. [source-1]")
# validate_output(output: Any) -> None; Runtime still validates actual outputs.
```

`AgentSpec` exposes `role_id`, `revision`, `instructions`, `task_template`,
`input_schema`, `output_schema`, `tool_requests`, `resource_digests` and `ref`.
The spec is an immutable snapshot; schema and reference properties return fresh
JSON dictionaries. Each compilation returns an independent mutable
`AgentDefinition` for the host to register.

`CatalogError` extends `ValueError` and exposes a stable `code`: `INVALID_IDENTITY`,
`RESOURCE_NOT_FOUND`, `INVALID_RESOURCE`, `INVALID_SCHEMA`, `INVALID_TEMPLATE`,
`INVALID_DATA`, `INVALID_INPUT`, `INVALID_OUTPUT`, `INVALID_LIMIT`,
`INVALID_BINDING` or `REVISION_CONFLICT`. Diagnostics omit resource contents and
input values. Catch it at the host's configuration/input boundary; the catalog
does not replace Engine's `Ok`/`Err` or execution result contracts.

## Baseline writer and researcher

`baseline.writer`, revision **1**, requires a closed input object with
`question: string` and `evidence: string`. The question must be nonempty.
Empty evidence is permitted so the writer can report insufficient support.
Output is a nonempty Markdown string delivered as a saved artifact. This role
requests **no tools**, including when the host offers tools to compilation.
The host selects saved evidence and supplies its text and provenance labels.
Writer prompt instructions preserve those labels and forbid invented research
actions and citations; citation correctness still needs host verification.

`baseline.researcher`, revision **1**, requires a closed input object with
`question: string`. It requests `web.search@1`, `web.fetch@1` and
`document.read@1`. Its instructions require fetched and actually read evidence
before citation. To approve tools explicitly:

```python
from deepresearch.engine.contracts import ToolRef

researcher = catalog.load("baseline.researcher", 1)
definition = researcher.compile_definition(
    profile_ref="deepseek", model_ref="deepseek-flash",
    tools=(ToolRef("web.search", 1), ToolRef("web.fetch", 1),
           ToolRef("document.read", 1)),
)
```

Compilation includes only exact requested tools that the host approves.
Missing approval removes a tool; a different revision does not match. Approval
cannot add an unrequested tool. Engine must still resolve approved revisions and
bind their live permissions. The researcher is an optional role; loading it
does not add model calls or change a workflow's budgets.

Profile/model names are mandatory host arguments and are resolved by Engine's
existing profile registry. The catalog never reads credential files or embeds
provider configuration. If the host registers different bindings of one role
in the same Engine, use distinct `agent_id` values. Changed content or bindings
under one registered agent ID/revision cause Engine's existing registration
conflict.

## Rendering and Runtime compatibility

The role's structured input schema validates **before** rendering. Task templates
use `$question` or `${question}` style substitution and `$$` for a literal dollar.
Every template variable must name a required top-level input property.
Expressions, indexing, attribute access, missing names and malformed dollar
syntax reject the bundle. Input strings are inserted literally once: dollar
syntax or braces inside evidence are never evaluated. Non-string JSON values
are inserted as canonical JSON. Objects reject unknown properties according to
their declared schema. Inputs, rendered tasks and outputs have finite JSON,
depth and byte bounds.

`render_task` returns the actual string passed to `Engine.run_agent`. The compiled
definition therefore has a **string** input schema. The structured role schema
remains on `spec.input_schema`; passing the original dictionary to that compiled
definition is invalid. Hosts using this catalog must render structured input
before calling Engine. Direct Engine callers can still supply strings under the
existing AgentDefinition contract.

Role limits use the existing Runtime limit names and defaults. `limits=` applies
host ceilings by taking the minimum of each numeric bound and the role's
effective limits. It cannot increase a role's allowance. Count/byte limits must
be positive integers; durations must be positive finite numbers. Advisory token
budgets may be narrowed; `None` cannot remove an existing budget. Strict token
enforcement is rejected because the current Runtime does not support it.
Engine deadlines, grants and lineage budgets continue to apply independently.
If compilation narrows task/output bounds further, Runtime enforces those
effective bounds at admission/execution.

## Resources, revisions and digest pins

Each role revision contains these five required resource names:

```text
resources/baseline.writer/1/
    definition.json
    instructions.md
    task.md
    input.schema.json
    output.schema.json
```

`definition.json` has `schema_version: 1`, `role_id`, integer `revision`,
`tool_requests` (exact `name`/`revision` objects), `limits` and `output`; an optional
`description` is text. Unknown definition, tool, limit and output properties
reject loading. `output` accepts `mode`, `media_type`, `delivery`,
`native_enforcement` and `max_bytes`, using Runtime's existing values. The schema
comes from `output.schema.json`. Resources cannot declare credentials, profiles,
provider settings, context grants or delegation authority.

JSON resources require unique keys and finite values. Individual files are
limited to 64 KiB, instructions to 32 KiB, and JSON nesting to 32 levels. JSON
schemas use a deliberately closed Draft 2020-12 subset: primitive types,
enum/const, declared object properties, arrays, numeric/string length bounds,
composition, annotations, `$defs` and local JSON Pointer `$ref`. Object schemas
must explicitly constrain additional properties. Unknown keywords, regexes,
formats, external references, schema IDs, dynamic/recursive references and
unresolved pointers reject loading. Schemas are bounded to 512 nodes and 32
levels after reference expansion. Literal JSON in `const`, `enum`, `default`
and `examples` is data, not a schema to resolve. Nothing fetches schema URLs.

There are no `latest` aliases or automatic fallbacks. A role/revision request
must match the bundle's own identity. `spec.ref` contains:

```text
schema_version: 1
role_id: string
revision: integer
resource_digests: {filename: "sha256:<hex>", ...}
sha256: "sha256:<hex>"
```

Each file digest covers its original bytes, including whitespace and line
endings. The aggregate digest covers the canonical reference descriptor before
adding its `sha256` field. A catalog rejects changed bytes under a revision it
already loaded. For pins that survive processes or deployments, save `spec.ref`
in workflow metadata and load with `expected_digest=ref["sha256"]`.

The compiled string input schema includes the complete reference in its standard
`$comment` annotation. This inert annotation includes resource pins in the
existing `AgentDefinition.definition_ref` hash, which Engine and Runtime already
record. It creates no provider settings or execution permissions. A changed
template or structured input schema therefore changes the definition digest
even when rendered output has the same string shape.

Resources ship under the existing Hatch wheel package target `src/deepresearch` and are
loaded through `importlib.resources`; no dependency/manifest change is required.

## Verification

```powershell
uv --cache-dir .uv-cache run --locked --offline python -B -m pytest tests/agent_catalog -q -p no:cacheprovider
```

Tests cover packaged loads, exact revision/digest pins, content drift, malformed
resources, closed schemas, unsafe templates, literal substitution, host tool and
budget control, independent snapshots, and compatibility with real
Engine/Runtime/SQLite Storage. Provider IO in the compatibility test uses a
controlled HTTP transport; it is not live model or research acceptance.
