"""Load exact resource revisions; compile without allocating execution authority."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from string import Template
from typing import Any, Iterable, Mapping

from deepresearch.engine.contracts import AgentDefinition, ToolRef, canonical_json, digest_bytes, digest_json, strict_json_loads

from ._validation import (
    CatalogError, checked_schema, checked_template, execution_limits, fail,
    identifier, json_data, matches_schema, narrow_limits, object_fields, revision_number,
)

RESOURCE_NAMES = ("definition.json", "instructions.md", "task.md", "input.schema.json", "output.schema.json")
RESOURCE_MAX_BYTES = 65536


@dataclass(frozen=True)
class AgentSpec:
    """Immutable validated resource snapshot. JSON properties return fresh copies."""

    role_id: str
    revision: int
    instructions: str
    task_template: str
    _definition: bytes
    _input_schema: bytes
    _output_schema: bytes
    _ref: bytes

    @property
    def ref(self) -> dict[str, Any]:
        """Role/revision, aggregate sha256 and hashes of all five original files."""
        return strict_json_loads(self._ref)

    @property
    def resource_digests(self) -> dict[str, str]:
        return self.ref["resource_digests"]

    @property
    def input_schema(self) -> dict[str, Any]:
        return strict_json_loads(self._input_schema)

    @property
    def output_schema(self) -> dict[str, Any]:
        return strict_json_loads(self._output_schema)

    @property
    def tool_requests(self) -> tuple[ToolRef, ...]:
        return tuple(ToolRef(**tool) for tool in strict_json_loads(self._definition)["tool_requests"])

    def render_task(self, input: dict[str, Any]) -> str:
        """Validate structured JSON, then substitute literal top-level values once."""
        declaration = strict_json_loads(self._definition)
        limits = narrow_limits(declaration["limits"], {})
        data = json_data(input, limits["max_task_input_bytes"])
        matches_schema(self.input_schema, data, "INVALID_INPUT")
        values = {key: value if type(value) is str else canonical_json(value).decode("utf-8")
                  for key, value in data.items()}
        rendered = Template(self.task_template).substitute(values)
        json_data(rendered, limits["max_task_input_bytes"])
        return rendered

    def validate_output(self, output: Any) -> None:
        """Pure validation for consumers; Runtime still validates actual results."""
        declaration = strict_json_loads(self._definition)
        limits = narrow_limits(declaration["limits"], {})
        value = json_data(output, min(limits["max_final_output_bytes"], declaration["output"].get(
            "max_bytes", limits["max_final_output_bytes"])))
        matches_schema(self.output_schema, value, "INVALID_OUTPUT")

    def compile_definition(
        self, *, profile_ref: str, model_ref: str,
        tools: Iterable[ToolRef] = (),
        limits: Mapping[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> AgentDefinition:
        """Intersect exact tool requests with host approval and narrow run limits.

        Profile/model are trusted names resolved by Engine, never credentials.
        The host can select an agent ID for distinct bindings of the same role.
        """
        for name in (profile_ref, model_ref):
            if type(name) is not str or not name.strip() or len(name.encode("utf-8")) > 256:
                fail("INVALID_BINDING", "Profile and model require bounded nonblank names")
        selected_id = self.role_id if agent_id is None else agent_id
        identifier(selected_id)
        approved = set()
        for tool in tools:
            if not isinstance(tool, ToolRef) or type(tool.name) is not str or not tool.name or len(tool.name) > 128:
                fail("INVALID_BINDING", "Host tool approval requires exact ToolRef records")
            revision_number(tool.revision)
            if tool in approved:
                fail("INVALID_BINDING", "Host tool approvals must be unique")
            approved.add(tool)
        if limits is not None and not isinstance(limits, Mapping):
            fail("INVALID_LIMIT", "Host execution limits must be a mapping")
        declaration = strict_json_loads(self._definition)
        effective_limits = narrow_limits(declaration["limits"], json_data(dict(limits or {}), 16384))
        output = declaration["output"]
        # AgentDefinition has no metadata field. A standard inert annotation is
        # included in its hash without introducing provider settings or grants.
        rendered_schema = {"type": "string", "minLength": 1,
                           "$comment": "Agent catalog pin " + canonical_json(self.ref).decode("utf-8")}
        definition = AgentDefinition(
            agent_id=selected_id, revision=self.revision, instructions=self.instructions,
            profile_ref=profile_ref, model_ref=model_ref,
            allowed_tools=[tool for tool in self.tool_requests if tool in approved],
            input_schema=rendered_schema, output_schema=self.output_schema,
            output_mode=output["mode"], output_media_type=output["media_type"],
            output_contract={key: value for key, value in output.items() if key not in {"mode", "media_type"}},
            limits=effective_limits,
        )
        try:
            canonical_json(definition, 131072)
        except (ValueError, TypeError):
            fail("INVALID_RESOURCE", "Compiled definition exceeds Runtime serialization bounds")
        return definition


class AgentCatalog:
    """Resource-backed catalog with no latest aliases, dispatch or registration.

    root is a trusted local bundle directory; omit it for packaged resources.
    A catalog rejects changed bytes under any previously loaded role/revision.
    """

    def __init__(self, root: str | Path | None = None):
        self._root = Path(root).resolve() if root is not None else resources.files(__package__).joinpath("resources")
        self._pins: dict[tuple[str, int], str] = {}

    def load(self, role_id: str, revision: int, *, expected_digest: str | None = None) -> AgentSpec:
        identifier(role_id)
        revision_number(revision)
        if expected_digest is not None:
            import re
            if type(expected_digest) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest):
                fail("INVALID_IDENTITY", "Expected digest must be a SHA-256 pin")
        bundle = self._root.joinpath(role_id, str(revision))
        if isinstance(self._root, Path):
            try:
                bundle.resolve().relative_to(self._root)
            except (ValueError, OSError):
                fail("INVALID_RESOURCE", "Bundle escapes the trusted catalog root")
        raw = {}
        for name in RESOURCE_NAMES:
            resource = bundle.joinpath(name)
            try:
                if isinstance(self._root, Path):
                    resource.resolve().relative_to(bundle.resolve())
                with resource.open("rb") as stream:
                    raw[name] = stream.read(RESOURCE_MAX_BYTES + 1)
            except FileNotFoundError:
                fail("RESOURCE_NOT_FOUND", "Exact role revision is missing a required resource")
            except (OSError, ValueError):
                fail("INVALID_RESOURCE", "Resource cannot be read within the bundle")
            if len(raw[name]) > RESOURCE_MAX_BYTES:
                fail("INVALID_RESOURCE", "Resource exceeds the bundle byte allowance")
        parsed = {}
        for name in ("definition.json", "input.schema.json", "output.schema.json"):
            try:
                parsed[name] = strict_json_loads(raw[name], max_bytes=RESOURCE_MAX_BYTES)
            except (ValueError, TypeError, RecursionError):
                fail("INVALID_RESOURCE", "Resource must contain bounded finite JSON with unique keys")
        definition = parsed["definition.json"]
        fields = {"schema_version", "role_id", "revision", "description", "tool_requests", "limits", "output"}
        object_fields(definition, fields, fields - {"description"})
        if type(definition["schema_version"]) is not int or definition["schema_version"] != 1:
            fail("INVALID_RESOURCE", "Unsupported bundle schema version")
        if definition["role_id"] != role_id or type(definition["revision"]) is not int or definition["revision"] != revision:
            fail("INVALID_IDENTITY", "Bundle identity differs from the requested role/revision")
        if "description" in definition and type(definition["description"]) is not str:
            fail("INVALID_RESOURCE", "Role description must be text")
        tools = definition["tool_requests"]
        if type(tools) is not list or len(tools) > 64:
            fail("INVALID_RESOURCE", "Tool requests must be a bounded array")
        seen = set()
        for tool in tools:
            object_fields(tool, {"name", "revision"}, {"name", "revision"})
            if type(tool["name"]) is not str or not tool["name"] or len(tool["name"]) > 128:
                fail("INVALID_RESOURCE", "Tool request requires a bounded name")
            revision_number(tool["revision"])
            key = (tool["name"], tool["revision"])
            if key in seen:
                fail("INVALID_RESOURCE", "Duplicate tool request")
            seen.add(key)
        execution_limits(definition["limits"])
        output = definition["output"]
        object_fields(output, {"mode", "media_type", "delivery", "native_enforcement", "max_bytes"}, {"mode", "media_type"})
        if output["mode"] not in ("text", "json") or output["media_type"] not in (
            ("application/json",) if output["mode"] == "json" else ("text/plain", "text/markdown")):
            fail("INVALID_RESOURCE", "Output mode and media type must match Runtime")
        if output.get("delivery", "inline_or_artifact") not in ("inline_or_artifact", "artifact") or output.get(
            "native_enforcement", "optional") not in ("disabled", "optional", "required"):
            fail("INVALID_RESOURCE", "Unsupported output delivery or enforcement")
        if "max_bytes" in output and (type(output["max_bytes"]) is not int or output["max_bytes"] <= 0):
            fail("INVALID_RESOURCE", "Output byte limit must be a positive integer")
        input_schema = checked_schema(parsed["input.schema.json"])
        output_schema = checked_schema(parsed["output.schema.json"])
        if type(input_schema) is not dict or type(output_schema) is not dict:
            fail("INVALID_SCHEMA", "Input/output resources must be schema objects")
        if output["mode"] == "text" and output_schema.get("type") != "string":
            fail("INVALID_SCHEMA", "Text output requires a string schema")
        try:
            instructions = raw["instructions.md"].decode("utf-8")
            task = raw["task.md"].decode("utf-8")
        except UnicodeError:
            fail("INVALID_RESOURCE", "Instructions and task template require UTF-8")
        if not instructions.strip() or len(raw["instructions.md"]) > 32768 or not task.strip():
            fail("INVALID_RESOURCE", "Instructions/task must be nonblank and within Runtime bounds")
        checked_template(task, input_schema)
        descriptor = {"schema_version": 1, "role_id": role_id, "revision": revision,
                      "resource_digests": {name: digest_bytes(raw[name]) for name in RESOURCE_NAMES}}
        descriptor["sha256"] = digest_json(descriptor)
        digest = descriptor["sha256"]
        if expected_digest is not None and expected_digest != digest:
            fail("REVISION_CONFLICT", "Resources differ from the expected digest pin")
        previous = self._pins.get((role_id, revision))
        if previous is not None and previous != digest:
            fail("REVISION_CONFLICT", "Resource bytes changed under a previously loaded revision")
        self._pins[(role_id, revision)] = digest
        return AgentSpec(role_id, revision, instructions, task, canonical_json(definition),
                         canonical_json(input_schema), canonical_json(output_schema), canonical_json(descriptor))
