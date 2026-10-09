"""Versioned, bounded adapter to an explicitly configured self-hosted SearXNG.

SearXNG owns engine parsing and aggregation. This adapter preserves its returned
destinations, identifies upstream engines, and does not claim their HTTP counts.
"""
from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx

from .common import ToolFault, closed, digest, prefix_utf8, strict_json, url, utc_now
from .discovery_metadata import coverage, coverage_schema, object_schema

DEFAULT_ENDPOINT = "http://127.0.0.1:18888"
ENGINES = ["yahoo", "duckduckgo"]


def service_endpoint(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("SearXNG endpoint must be a trusted HTTP(S) base URL without credentials/query/fragment")
    return value.rstrip("/")


def plan(endpoint=DEFAULT_ENDPOINT):
    return {"kind": "search", "adapter": "searxng/1", "endpoint": service_endpoint(endpoint),
            "engines": list(ENGINES), "language": "en", "timeout_seconds": 15,
            "response_bytes": 1 << 20}


def schema():
    string = {"type": "string"}
    nullable = {"type": ["string", "null"]}
    count = {"type": "integer", "minimum": 0}
    engine_list = {"type": "array", "maxItems": 2, "uniqueItems": True,
                   "items": {"enum": ENGINES}}
    candidate = object_schema({
        "rank": {"type": "integer", "minimum": 1, "maximum": 10},
        "provider_rank": {"type": "integer", "minimum": 1},
        "title": {"type": "string", "maxLength": 4096},
        "url": {"type": "string", "maxLength": 8192},
        "raw_url": {"type": "string", "maxLength": 8192},
        "snippet": {"type": "string", "maxLength": 16384},
        "domain": {"type": "string", "minLength": 1, "maxLength": 8192},
        "source_date": nullable, "backend": {"const": "searxng"},
        "declared_provider": {"const": "searxng"}, "engines": engine_list,
        "discovery_only": {"const": True},
        "truncated_fields": {"type": "array", "maxItems": 2, "uniqueItems": True,
                             "items": {"enum": ["title", "snippet"]}},
        "missing_fields": {"type": "array", "maxItems": 2, "uniqueItems": True,
                           "items": {"enum": ["snippet", "source_date"]}},
    })
    failure = object_schema({"engine": {"enum": ENGINES}, "reason": string})
    attempt = object_schema({
        "backend_attempt_index": {"const": 1}, "backend": {"const": "searxng"},
        "declared_provider": {"const": "searxng"},
        "outcome": {"enum": ["returned", "unavailable", "failed"]},
        "elapsed_ms": count, "returned_count": count, "kept_count": count,
        "http_status": {"type": ["integer", "null"], "minimum": 100, "maximum": 599},
        "http_request_count": count, "http_response_count": count,
        "upstream_http_request_count": {"type": "null"},
        "response_bytes": {"type": ["integer", "null"], "minimum": 0},
        "response_sha256": nullable, "extracted_count": count, "rejected_url_count": count,
        "failure_reason": nullable,
        "engine_errors": {"type": "array", "maxItems": 2, "items": failure},
    })
    return object_schema({"query": string, "searched_at": string,
        "backend_policy": object_schema({"configured_order": {"const": ["searxng"]},
            "active_order": {"const": ["searxng"]}, "engines": {"const": ENGINES},
            "disabled_backends": {"type": "array", "maxItems": 0},
            "aggregation": {"const": "searxng_native_rank"}}),
        "backend_attempts": {"type": "array", "minItems": 1, "maxItems": 1, "items": attempt},
        "results": {"type": "array", "maxItems": 10, "items": candidate},
        "coverage": coverage_schema()})


def project(payload, maximum):
    rows = payload.get("results")
    if not isinstance(rows, list) or len(rows) > 500:
        raise ToolFault("SEARCH_PROTOCOL_ERROR", "Search service returned an invalid result collection")
    results, seen, rejected = [], set(), 0
    for rank, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ToolFault("SEARCH_PROTOCOL_ERROR", "Search service returned an invalid result row")
        raw = row.get("url")
        try:
            if not isinstance(raw, str) or len(raw.encode()) > 8192:
                raise ValueError()
            destination = url(raw)
        except (ToolFault, ValueError, UnicodeError):
            rejected += 1
            continue
        title, snippet = row.get("title"), row.get("content") or ""
        engines = row.get("engines")
        if (not isinstance(title, str) or not title.strip() or not isinstance(snippet, str)
                or not isinstance(engines, list) or not engines or any(e not in ENGINES for e in engines)):
            rejected += 1
            continue
        if destination in seen:
            continue
        seen.add(destination)
        short_title, short_snippet = prefix_utf8(title, 4096), prefix_utf8(snippet, 16384)
        date = row.get("publishedDate")
        date = prefix_utf8(date, 256) if isinstance(date, str) and date else None
        results.append({"rank": len(results) + 1, "provider_rank": rank,
            "title": short_title, "url": destination, "raw_url": raw, "snippet": short_snippet,
            "domain": urlsplit(destination).hostname, "source_date": date,
            "backend": "searxng", "declared_provider": "searxng", "engines": list(dict.fromkeys(engines)),
            "discovery_only": True,
            "truncated_fields": [name for name, original, shortened in
                [("title", title, short_title), ("snippet", snippet, short_snippet)] if original != shortened],
            "missing_fields": (["snippet"] if not snippet else []) + (["source_date"] if date is None else [])})
    return results[:maximum], len(results), rejected


def search(arguments, selected_plan, timeout):
    closed(selected_plan, set(plan()))
    try:
        expected = plan(selected_plan["endpoint"])
    except (TypeError, ValueError):
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Invalid trusted search service endpoint") from None
    if selected_plan != expected:
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Search service plan differs from registered policy")
    started = time.monotonic()
    deadline = started + min(timeout, selected_plan["timeout_seconds"])
    attempt = {"backend_attempt_index": 1, "backend": "searxng", "declared_provider": "searxng",
        "outcome": "unavailable", "elapsed_ms": 0, "returned_count": 0, "kept_count": 0,
        "http_status": None, "http_request_count": 0, "http_response_count": 0,
        "upstream_http_request_count": None, "response_bytes": None, "response_sha256": None,
        "extracted_count": 0, "rejected_url_count": 0, "failure_reason": None, "engine_errors": []}
    results, available, fault = [], 0, None
    try:
        with httpx.Client(trust_env=False, follow_redirects=False,
                          timeout=max(.01, deadline - time.monotonic())) as client:
            attempt["http_request_count"] = 1
            with client.stream("GET", selected_plan["endpoint"] + "/search", params={
                    "q": arguments["query"], "format": "json", "language": "en",
                    "engines": ",".join(ENGINES), "safesearch": 0, "pageno": 1}) as response:
                attempt["http_response_count"] = 1
                attempt["http_status"] = response.status_code
                if response.status_code != 200:
                    raise ToolFault("SEARCH_UNAVAILABLE", "SearXNG did not return HTTP 200")
                body = bytearray()
                for chunk in response.iter_bytes(16384):
                    if time.monotonic() >= deadline:
                        raise ToolFault("SEARCH_UNAVAILABLE", "Search service response deadline expired")
                    body.extend(chunk)
                    if len(body) > selected_plan["response_bytes"]:
                        raise ToolFault("SEARCH_RESPONSE_LIMIT", "Search service response exceeds the byte limit")
        attempt["response_bytes"], attempt["response_sha256"] = len(body), digest(bytes(body))
        payload = strict_json(bytes(body), selected_plan["response_bytes"])
        if not isinstance(payload, dict) or payload.get("query") != arguments["query"]:
            raise ToolFault("SEARCH_PROTOCOL_ERROR", "Search service changed the literal query")
        errors = payload.get("unresponsive_engines", [])
        seen_errors = set()
        if isinstance(errors, list):
            for entry in errors:
                if isinstance(entry, list) and len(entry) == 2 and entry[0] in ENGINES and entry[0] not in seen_errors:
                    attempt["engine_errors"].append({"engine": entry[0], "reason": prefix_utf8(str(entry[1]), 512)})
                    seen_errors.add(entry[0])
        results, available, rejected = project(payload, arguments["max_results"])
        attempt.update(extracted_count=len(payload["results"]), rejected_url_count=rejected,
                       returned_count=available, kept_count=len(results))
        if not results:
            raise ToolFault("SEARCH_UNAVAILABLE", "SearXNG returned no usable discoveries; inspect engine_errors")
        attempt["outcome"] = "returned"
    except httpx.HTTPError:
        fault = ToolFault("SEARCH_UNAVAILABLE", "Self-hosted SearXNG is unavailable; check the configured service")
        attempt["failure_reason"] = "service_transport"
    except ToolFault as error:
        fault = error
        attempt["failure_reason"] = error.code.lower()
    attempt["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    observations = {"backend_attempts": [attempt], "disabled_backends": []}
    usage = {"search_backend_attempts": 1, "http_request_count": attempt["http_request_count"],
             "http_response_count": attempt["http_response_count"], "monetary_cost": None}
    if fault:
        return None, observations, usage, fault
    return {"query": arguments["query"], "searched_at": utc_now(), "backend_policy": {
        "configured_order": ["searxng"], "active_order": ["searxng"], "engines": list(ENGINES),
        "disabled_backends": [], "aggregation": "searxng_native_rank"},
        "backend_attempts": [attempt], "results": results,
        "coverage": coverage(arguments["max_results"], len(results), available)}, observations, usage, None
