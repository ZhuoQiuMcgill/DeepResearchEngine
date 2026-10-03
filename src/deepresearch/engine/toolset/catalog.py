"""Immutable registered schemas and fixed worker argv."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from deepresearch.engine.contracts import EngineError, Err, Ok, ToolDefinition

from .common import LIMITS, ToolFault, validate_arguments
from .scholarly import SCHEMA
from .discovery_metadata import coverage_schema


def _object(properties, required=None):
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": list(properties) if required is None else required}


def _inputs(name):
    query = _object({"query": {"type": "string", "minLength": 1, "maxLength": 4096},
                     "max_results": {"type": "integer", "minimum": 1, "maximum": 10}}, ["query"])
    if "search" in name: return query
    if name == "web.fetch": return _object({"url": {"type": "string", "minLength": 1, "maxLength": 8192}, "mode": {"const": "static"}}, ["url"])
    reference = _object({"schema_version": {"const": 1}, "store_id": {"type": "string", "minLength": 1}, "snapshot_id": {"type": "string", "minLength": 1}})
    interval = _object({"kind": {"enum": ["lines", "pages"]}, "start": {"type": "integer", "minimum": 1}, "end_exclusive": {"type": "integer", "minimum": 1}})
    return _object({"snapshot_ref": reference, "range": interval, "max_text_bytes": {"type": "integer", "minimum": 1, "maximum": 65536},
                    "continuation": {"type": ["string", "null"], "maxLength": 8192}}, ["snapshot_ref", "range"])


def _outputs(name, revision=1):
    string = {"type": "string"}
    nullable = {"type": ["string", "null"]}
    integer = {"type": "integer", "minimum": 0}
    reference = _inputs("document.read")["properties"]["snapshot_ref"]
    interval = _inputs("document.read")["properties"]["range"]
    if name.startswith("scholar."):
        provider = name.split(".")[1]
        suffix = "_result_v2" if revision == 2 else "_result"
        # Preserve the released v1 schema and its identity byte-for-byte.
        definitions = {key: value for key, value in SCHEMA["$defs"].items() if revision == 2 or not key.endswith("_v2")}
        return {"$ref": f"#/$defs/{provider}{suffix}", "$defs": copy.deepcopy(definitions)}
    if name == "document.read":
        span = _object({"line": {"type": ["integer", "null"], "minimum": 1}, "page": {"type": ["integer", "null"], "minimum": 1}, "start_byte": integer, "end_byte": integer})
        return _object({"schema_version": {"const": 1}, "snapshot_ref": reference, "extraction_version": string,
            "normalization_version": string, "requested_range": interval, "returned_range": interval,
            "text": {"type": "string", "maxLength": 65536}, "byte_length": integer,
            "truncated": {"type": "boolean"}, "has_more_in_requested_range": {"type": "boolean"},
            "has_more_in_document": {"type": "boolean"}, "next_position": {"anyOf": [{"type": "null"}, _object({"unit": {"type": "integer", "minimum": 1}, "offset": {"type": ["integer", "null"], "minimum": 0}})]}, "continuation": nullable,
            "spans": {"type": "array", "maxItems": 200, "items": span}})
    if name == "web.fetch":
        redirect = _object({"from_url": string, "to_url": string, "http_status": integer})
        provenance = _object({"requested_url": string, "final_url": string,
            "redirects": {"type": "array", "maxItems": 5, "items": redirect}, "retrieved_at": string, "http_status": integer,
            "content_type": string, "content_encoding": nullable, "declared_content_length": nullable,
            "http_request_count": integer, "http_response_count": integer,
            "response_transfer_bytes": integer, "response_decoded_bytes": integer,
            "etag": nullable, "last_modified": nullable, "representation": {"const": "content_decoded"}, "media_type": string,
            "chosen_charset": nullable, "charset_source": nullable,
            "original_bytes": integer, "original_sha256": string, "text_bytes": integer, "text_sha256": string,
            "index_bytes": integer, "index_sha256": string, "extraction_version": string,
            "normalization_version": string, "classification": string, "physical_page_count": {"type": ["integer", "null"], "minimum": 0},
            "parser_warning_count": integer})
        return _object({"snapshot_ref": reference, "extraction_version": string, "normalization_version": string,
            "line_count": integer, "page_count": {"type": ["integer", "null"], "minimum": 0},
            "provenance": provenance, "preview": {"type": "string", "maxLength": 65536}})
    disabled = _object({"backend": {"const": "google"}, "reason": {"const": "URL_FIDELITY_GATE_PENDING"}})
    failure = {"anyOf": [{"type": "null"}, _object({"code": string, "message": string,
        "details": _object({}), "observed_effect_state": string})]}
    backends = ["yahoo", "google"] if revision == 1 else ["yahoo", "duckduckgo", "google"]
    attempt = _object({"backend_attempt_index": {"type": "integer", "minimum": 1, "maximum": 2},
        "backend": {"enum": backends}, "declared_provider": {"enum": ["bing", "google"]},
        "outcome": {"enum": ["returned", "unavailable", "failed"]}, "elapsed_ms": integer,
        "returned_count": integer, "kept_count": integer, "error": failure})
    candidate = _object({"rank": {"type": "integer", "minimum": 1, "maximum": 10},
        "title": {"type": "string", "maxLength": 4096}, "url": {"type": "string", "maxLength": 8192},
        "snippet": {"type": "string", "maxLength": 16384}, "source_date": nullable,
        "backend": {"enum": backends}, "declared_provider": {"enum": ["bing", "google"]},
        "discovery_only": {"const": True}, "truncated_fields": {"type": "array", "maxItems": 2, "uniqueItems": True, "items": {"enum": ["title", "snippet"]}}})
    if revision >= 2:
        candidate["properties"]["raw_url"] = {"type":"string","maxLength":8192}
        candidate["required"].append("raw_url")
        attempt["properties"].update({"http_status":{"type":["integer","null"],"minimum":100,"maximum":599},
            "http_request_count":integer,"http_response_count":integer,"response_bytes":{"type":["integer","null"],"minimum":0},
            "response_sha256":nullable,"extracted_count":integer,"rejected_url_count":integer,
            "advertisement_count":integer,"failure_reason":nullable,
            "redirects":{"type":"array","maxItems":2,"items":_object({"from_url":string,"to_url":string,"http_status":integer})}})
        attempt["required"] = list(attempt["properties"])
    if revision == 3:
        candidate["properties"].update(provider_rank={"type": "integer", "minimum": 1},
            domain={"type": "string", "minLength": 1, "maxLength": 8192},
            missing_fields={"type": "array", "uniqueItems": True, "maxItems": 2,
                            "items": {"enum": ["snippet", "source_date"]}})
        candidate["required"] = list(candidate["properties"])
    result = _object({"query": string, "searched_at": string,
        "backend_policy": _object({"configured_order": {"const": backends if revision == 1 else ["yahoo","duckduckgo","google"]},
            "active_order": {"const": ["yahoo"] if revision == 1 else ["yahoo","duckduckgo"]},
            "disabled_backends": {"type": "array", "maxItems": 1, "items": disabled}}),
        "backend_attempts": {"type": "array", "maxItems": 2, "items": attempt},
        "results": {"type": "array", "maxItems": 10, "items": candidate}})
    if revision == 3:
        result["properties"]["coverage"] = coverage_schema()
        result["required"].append("coverage")
    return result


class ToolCatalog:
    def __init__(self):
        entries = {
            "web.search": ("Discover web sources using explicit Yahoo search. Discoveries require web.fetch and document.read before citation.", ("network.search",), {}),
            "scholar.crossref.search": ("Discover scholarly Crossref bibliographic metadata for a literal query. Follow DOI/publisher links with web.fetch and read saved evidence; metadata is discovery only.", ("network.search",), {}),
            "scholar.openalex.search": ("Discover OpenAlex scholarly work and open-access locations for a literal query. Quoted phrases are supported. Metadata is discovery only; fetch accessible source URLs then read saved evidence.", ("network.search",), {}),
            "web.fetch": ("Fetch one public static HTML, plain-text or text-PDF source and commit immutable original/text/index. Returns snapshot reference and counts for document.read. Interactive or inaccessible sources fail explicitly.", ("network.fetch", "snapshot.commit"), {"operation": "snapshot.commit"}),
            "document.read": ("Read saved immutable snapshot lines or physical PDF pages. Range is one-based and end-exclusive; pass the opaque continuation unchanged with the same snapshot_ref and original range when truncated. next_position describes the byte position. Reading never fetches the source again.", ("snapshot.read",), {"operation": "snapshot.read"}),
        }
        self._entries = {}
        for name, (description, capabilities, storage_needs) in entries.items():
            output = _outputs(name)
            self._entries[(name, 1)] = ToolDefinition(name=name, revision=1, description=description,
                input_schema=_inputs(name), output_schema=output, capabilities=capabilities,
                limits=dict(LIMITS), argv=(sys.executable, "-m", "deepresearch.engine.toolset.worker", name, "1"),
                config={"profile": "selected-discovery/1", "google_enabled": False}, storage_needs=storage_needs)
        first = self._entries[("web.search", 1)]
        self._entries[("web.search", 2)] = ToolDefinition(name="web.search", revision=2,
            description="Discover web sources using bounded Yahoo then DuckDuckGo fallback. Returns literal query, ranked URLs/snippets and HTTP/parser observations; discoveries require saved source reads before citation.",
            input_schema=_inputs("web.search"), output_schema=_outputs("web.search", 2), capabilities=first.capabilities,
            limits=dict(LIMITS), argv=(sys.executable,"-m","deepresearch.engine.toolset.worker","web.search","2"),
            config={"profile":"selected-discovery/2","google_enabled":False}, storage_needs={})
        for name, revision in (("web.search", 3), ("scholar.crossref.search", 2), ("scholar.openalex.search", 2)):
            base = self._entries[(name, 2 if name == "web.search" else 1)]
            self._entries[(name, revision)] = ToolDefinition(name=name, revision=revision,
                description=base.description + " Returns explicit first-page coverage, missing/truncated fields and provider metadata when available.",
                input_schema=_inputs(name), output_schema=_outputs(name, revision), capabilities=base.capabilities,
                limits=dict(LIMITS), argv=(sys.executable, "-m", "deepresearch.engine.toolset.worker", name, str(revision)),
                config={"profile": f"selected-discovery/{revision}", "google_enabled": False}, storage_needs={})

    def resolve(self, name: str, revision: int = 1):
        if type(revision) is not int or (name, revision) not in self._entries:
            return Err(EngineError("UNKNOWN_TOOL", "Tool name/revision is not registered"))
        return Ok(copy.deepcopy(self._entries[(name, revision)]))

    @property
    def definitions(self):
        return tuple(copy.deepcopy(value) for value in self._entries.values())

    def list(self):
        return self.definitions

    def validate_arguments(self, definition, arguments):
        """Pure semantic preflight; no network, reads, reservation or processes."""
        try:
            normalized = validate_arguments(definition.name, arguments)
            if definition.name.startswith("scholar."):
                from .scholarly import request_url
                request_url(definition.name.split(".")[1], normalized)
        except ToolFault as exc:
            raise EngineError("tool.invalid_arguments", exc.message, {"cause": exc.code}) from exc
