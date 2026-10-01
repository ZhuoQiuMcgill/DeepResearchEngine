"""Local schema validation never follows network references."""
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, SchemaError


def validate_schema(schema: dict[str, Any]) -> None:
    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value and not str(value["$ref"]).startswith("#"):
                raise ValueError("External schema references are not permitted")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise ValueError("Schema is not valid Draft 2020-12") from None


def validation_errors(schema: dict[str, Any], value: Any) -> list[dict[str, Any]]:
    validate_schema(schema)
    errors = []
    for error in Draft202012Validator(schema).iter_errors(value):
        # Do not echo untrusted values, task secrets, or entire validation messages.
        errors.append({"path": [part if type(part) is int else str(part)[:128] for part in list(error.absolute_path)[:16]], "validator": str(error.validator)[:64]})
        if len(errors) == 16:
            break
    return errors
