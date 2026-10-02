"""Closed resource contracts and a bounded, local JSON Schema vocabulary."""
from __future__ import annotations

import math
import re
from string import Template
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from ebd.engine.agent.runtime import DEFAULT_LIMITS
from ebd.engine.contracts import canonical_json, strict_json_loads


class CatalogError(ValueError):
    """Safe catalog diagnostic; messages never contain resource/input values."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def fail(code: str, message: str):
    raise CatalogError(code, message) from None


def object_fields(value, allowed, required=()):
    if type(value) is not dict or set(value) - set(allowed) or set(required) - set(value):
        fail("INVALID_RESOURCE", "Resource has unknown or missing properties")


def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", value) or len(value) > 96:
        fail("INVALID_IDENTITY", "Role/agent ID must be a bounded lowercase identifier")


def revision_number(value):
    if type(value) is not int or not 1 <= value <= 2147483647:
        fail("INVALID_IDENTITY", "Revision must be an explicit positive integer")


def json_data(value: Any, max_bytes: int) -> Any:
    def walk(item, depth=0):
        if depth > 32:
            raise ValueError()
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError()
                walk(child, depth + 1)
        elif type(item) is list:
            for child in item:
                walk(child, depth + 1)
        elif type(item) not in {str, int, float, bool, type(None)}:
            raise ValueError()
    try:
        walk(value)
        return strict_json_loads(canonical_json(value, max_bytes), max_bytes=max_bytes)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        fail("INVALID_DATA", "Data must be bounded finite JSON")


def execution_limits(value):
    object_fields(value, DEFAULT_LIMITS)
    for key, limit in value.items():
        if key == "token_budget":
            if limit is None:
                continue
            object_fields(limit, {"max_total_tokens", "enforcement"}, {"max_total_tokens", "enforcement"})
            if type(limit["max_total_tokens"]) is not int or limit["max_total_tokens"] <= 0 or limit["enforcement"] != "advisory":
                fail("INVALID_LIMIT", "Only a positive advisory token budget is supported")
        elif key.endswith("seconds"):
            try:
                finite = type(limit) in {int, float} and math.isfinite(limit)
            except OverflowError:
                finite = False
            if not finite or limit <= 0:
                fail("INVALID_LIMIT", "Duration limits must be positive finite numbers")
        elif type(limit) is not int or limit <= 0:
            fail("INVALID_LIMIT", "Count and byte limits must be positive integers")


def narrow_limits(requested, host):
    execution_limits(requested)
    execution_limits(host)
    result = json_data({**DEFAULT_LIMITS, **requested}, 16384)
    for key, cap in host.items():
        if key == "token_budget":
            if cap is not None:
                prior = result[key]
                result[key] = {"enforcement": "advisory", "max_total_tokens": min(
                    cap["max_total_tokens"], prior["max_total_tokens"] if prior else cap["max_total_tokens"])}
        else:
            result[key] = min(result[key], cap)
    return result


# Deliberately omit regexes, formats, dynamic references and schema IDs. Unknown
# keywords fail rather than silently becoming annotations or remote resolution.
KEYWORDS = frozenset({
    "$schema", "$ref", "$defs", "$comment", "title", "description", "default", "examples",
    "type", "enum", "const", "properties", "required", "additionalProperties",
    "minProperties", "maxProperties", "items", "prefixItems", "minItems", "maxItems",
    "uniqueItems", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "multipleOf", "allOf", "anyOf", "oneOf", "not",
})
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"


def checked_schema(schema):
    nodes, edges, references = {}, {}, {}

    def visit(node, path=()):
        if len(nodes) >= 512:
            fail("INVALID_SCHEMA", "Schema exceeds the supported node allowance")
        nodes[path] = node
        edges[path] = []
        if type(node) is bool:
            return
        object_fields(node, KEYWORDS)
        if "$schema" in node and node["$schema"] != SCHEMA_URI:
            fail("INVALID_SCHEMA", "Only Draft 2020-12 schemas are supported")
        declared_type = node.get("type")
        if declared_type == "object" or (type(declared_type) is list and "object" in declared_type) or "properties" in node:
            if "additionalProperties" not in node or node["additionalProperties"] is True:
                fail("INVALID_SCHEMA", "Object schemas must explicitly constrain additional properties")
        if "$ref" in node:
            ref = node["$ref"]
            if type(ref) is not str or not (ref == "#" or ref.startswith("#/")) or "%" in ref:
                fail("INVALID_SCHEMA", "Only local JSON Pointer schema references are supported")
            parts = []
            for part in ref[2:].split("/") if ref != "#" else []:
                if re.search(r"~(?![01])", part):
                    fail("INVALID_SCHEMA", "Schema reference contains an invalid JSON Pointer")
                parts.append(part.replace("~1", "/").replace("~0", "~"))
            references[path] = tuple(parts)
        children = []
        for keyword in ("properties", "$defs"):
            if keyword in node:
                if type(node[keyword]) is not dict:
                    fail("INVALID_SCHEMA", "Schema member map must be an object")
                children.extend((node[keyword][name], path + (keyword, name)) for name in node[keyword])
        for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
            if keyword in node:
                if type(node[keyword]) is not list:
                    fail("INVALID_SCHEMA", "Schema branches must be an array")
                children.extend((child, path + (keyword, str(index))) for index, child in enumerate(node[keyword]))
        for keyword in ("items", "additionalProperties", "not"):
            if keyword in node:
                children.append((node[keyword], path + (keyword,)))
        for child, child_path in children:
            edges[path].append(child_path)
            visit(child, child_path)

    visit(schema)
    for path, target in references.items():
        if target not in nodes:
            fail("INVALID_SCHEMA", "Schema reference does not resolve to a schema")
        edges[path].append(target)
    heights, active = {}, set()

    def acyclic(path):
        if path in active:
            fail("INVALID_SCHEMA", "Recursive schema references are unsupported")
        if path in heights:
            return heights[path]
        active.add(path)
        height = 1 + max((acyclic(child) for child in edges[path]), default=0)
        if height > 32:
            fail("INVALID_SCHEMA", "Schema reference expansion exceeds the depth allowance")
        active.remove(path)
        heights[path] = height
        return height

    acyclic(())
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        fail("INVALID_SCHEMA", "Resource is not a valid Draft 2020-12 schema")
    return schema


def matches_schema(schema, value, code):
    if not Draft202012Validator(schema).is_valid(value):
        fail(code, "Data does not satisfy the pinned schema")


def checked_template(text, schema):
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        fail("INVALID_SCHEMA", "Task input requires a closed object schema")
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    for match in Template.pattern.finditer(text):
        if match.group("invalid") is not None:
            fail("INVALID_TEMPLATE", "Task template contains invalid dollar syntax")
        variable = match.group("named") or match.group("braced")
        if variable and (variable not in properties or variable not in required):
            fail("INVALID_TEMPLATE", "Template variables must name required top-level input properties")
    return text
