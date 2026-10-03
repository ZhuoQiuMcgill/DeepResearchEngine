"""Method registration without imports of concrete research strategies."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from deepresearch.engine.contracts import EngineError, canonical_json, digest_json


class Method(Protocol):
    async def run(self, context, task_input: dict[str, Any], parameters: dict[str, Any]): ...


@dataclass(frozen=True)
class MethodDefinition:
    method_id: str
    revision: int
    description: str
    input_schema: dict[str, Any]
    parameters_schema: dict[str, Any]
    agent_roles: tuple[tuple[str, int], ...] = ()
    resource_digests: dict[str, str] = field(default_factory=dict)
    tool_revisions: dict[str, int] = field(default_factory=dict)

    def to_dict(self):
        value = {"schema_version": 1, "method_id": self.method_id, "revision": self.revision,
                "description": self.description, "input_schema": copy.deepcopy(self.input_schema),
                "parameters_schema": copy.deepcopy(self.parameters_schema),
                "agent_roles": [{"role_id": r, "revision": v} for r, v in self.agent_roles],
                "resource_digests": copy.deepcopy(self.resource_digests)}
        if self.tool_revisions:
            value["tool_revisions"] = copy.deepcopy(self.tool_revisions)
        return {**value, "sha256": digest_json(value)}


class MethodRegistry:
    def __init__(self):
        self._methods = {}

    def register(self, definition: MethodDefinition, method: Method):
        if not definition.method_id or type(definition.revision) is not int or definition.revision < 1:
            raise EngineError("INVALID_DATA", "Method identity and positive revision are required")
        if not isinstance(definition.tool_revisions, dict) or any(not isinstance(name, str) or not name or
                type(revision) is not int or revision < 1 for name, revision in definition.tool_revisions.items()):
            raise EngineError("INVALID_DATA", "Method tool pins require names and positive integer revisions")
        for schema in (definition.input_schema, definition.parameters_schema):
            Draft202012Validator.check_schema(schema)
        fingerprint = digest_json(definition.to_dict())
        key = (definition.method_id, definition.revision)
        if key in self._methods:
            if self._methods[key][2] != fingerprint or self._methods[key][1] is not method:
                raise EngineError("REGISTRATION_CONFLICT", "Method revision is already pinned")
            return
        self._methods[key] = (copy.deepcopy(definition), method, fingerprint)

    def resolve(self, method_id: str, revision: int):
        entry = self._methods.get((method_id, revision))
        if entry is None:
            raise EngineError("METHOD_NOT_FOUND", "Exact registered method revision is required")
        return copy.deepcopy(entry[0]), entry[1]

    def validate(self, definition, task_input, parameters):
        canonical_json({"input": task_input, "parameters": parameters}, 131072)
        for schema, value in ((definition.input_schema, task_input), (definition.parameters_schema, parameters)):
            if next(Draft202012Validator(schema).iter_errors(value), None) is not None:
                raise EngineError("INVALID_DATA", "Method input or parameters failed its pinned schema")

    def list(self):
        return [entry[0].to_dict() for _, entry in sorted(self._methods.items())]
