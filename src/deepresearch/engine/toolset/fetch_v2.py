"""Adaptive acquisition over bounded open-source transports and shared extraction.

The chosen original is either decoded HTTP bytes or explicitly marked rendered
DOM. Both are immutable and are the exact input used to build text and index.
"""
from __future__ import annotations

import re
import time

from .common import ToolFault, encode
from .retrieval import pack_component, request_body
from .article_extraction import extract_source

_INFO_FIELDS = {"requested_url", "final_url", "redirects", "retrieved_at", "http_status",
    "content_type", "content_encoding", "declared_content_length", "http_request_count",
    "http_response_count", "response_transfer_bytes", "response_decoded_bytes", "etag", "last_modified"}
_RENDERABLE = {"EXTRACTION_EMPTY", "SOURCE_REQUIRES_RENDERING", "SOURCE_CHALLENGE"}


def extend_schema(schema, *, supervised=False):
    """Extend only the new revision's closed provenance contract."""
    from .discovery_metadata import object_schema
    count = {"type": "integer", "minimum": 0}
    nullable = {"type": ["string", "null"]}
    attempts = {"type": "array", "minItems": 1, "maxItems": 3, "items": object_schema({
        "backend": {"enum": ["curl_cffi/0.16.3", "httpx/0.28.1", "playwright/1.63.0/chromium"]},
        "outcome": {"enum": ["returned", "failed"]}, "elapsed_ms": count,
        "http_status": {"type": ["integer", "null"]}, "error_code": nullable,
        "http_request_count": count, "http_response_count": count, "decoded_body_bytes": count})}
    capture = object_schema({"backend": {"const": "playwright/1.63.0/chromium"},
        "captured_at": {"type": "string"}, "relayed_requests": count,
        "blocked_requests": count, "failed_resources": count, "dom_bytes": count,
        "wait_until": {"const": "domcontentloaded"}, "settle_ms": count})
    capture["properties"]["resource_failures"] = {"type": "array", "maxItems": 8,
        "items": object_schema({"url": {"type": "string", "maxLength": 1024},
            "resource_type": {"type": "string"}, "code": {"type": "string"},
            "limit_scope": nullable, "limit_kind": nullable,
            "limit": {"type": ["integer", "null"], "minimum": 0}})}
    provenance = schema["properties"]["provenance"]
    provenance["properties"].update(
        representation={"enum": ["content_decoded", "rendered_dom"]},
        transport={"enum": ["curl_cffi/0.16.3", "httpx/0.28.1"]}, fetch_attempts=attempts,
        capture={"anyOf": [{"type": "null"}, capture]})
    provenance["required"] = list(provenance["properties"])
    # Optional for older archives and non-HTML inputs; never infer from HTTP
    # Last-Modified or retrieval time. All declared conflicting values survive.
    from .document_metadata import dates_schema
    provenance["properties"]["document_dates"] = dates_schema()
    from .html_recovery import diagnostic_schema
    provenance["properties"]["html_extraction"] = diagnostic_schema()
    from .pdf_extraction import diagnostic_schema as pdf_schema
    provenance["properties"]["pdf_extraction"] = pdf_schema()
    from .html_structured_data import diagnostic_schema as structured_schema
    provenance["properties"]["structured_data"] = structured_schema()
    if supervised:
        from .fetch_policy import supervision_schema
        provenance['properties']['fetch_supervision'] = supervision_schema()
        # A terminated optional renderer can leave its network counts unknown while
        # an independently validated static capture remains available. Null is not 0.
        for key in ('http_request_count', 'http_response_count'):
            provenance['properties'][key] = {'type': ['integer', 'null'], 'minimum': 0}
        for key in ('http_request_count', 'http_response_count', 'decoded_body_bytes'):
            attempts['items']['properties'][key] = {'type': ['integer', 'null'], 'minimum': 0}
    return schema


def _extract(body, info, limits):
    status = info["http_status"]
    if status == 206:
        raise ToolFault("PARTIAL_RESPONSE", "Partial HTTP responses are not complete documents")
    if not 200 <= status < 300:
        raise ToolFault("FETCH_HTTP_ERROR", "Source returned a non-success HTTP status", details={"http_status": status})
    proposal = extract_source(body, {key: info[key] for key in _INFO_FIELDS}, limits)
    base_bytes = (proposal['provenance'].get('structured_data') or {}).get('base_text_bytes', len(proposal['text']))
    text = proposal["text"][:base_bytes].decode("utf-8")
    # Reject app-shell instructions rather than publishing them as source text.
    if len(text.strip()) < 500 and re.search(
            r"(?:enable|requires?|need|turn on).{0,60}javascript|javascript.{0,60}(?:enable|required)", text, re.I | re.S):
        raise ToolFault("SOURCE_REQUIRES_RENDERING", "Source contains a JavaScript shell rather than document text")
    return proposal


def fetch(arguments, plan, limits, timeout):
    from .fetch_transport import CurlTransport
    from .browser_capture import capture

    deadline = time.monotonic() + timeout
    attempts, info, proposal = [], {}, None
    representation = "content_decoded"
    with CurlTransport(deadline) as transport:
        phased = plan.get('extraction_config_ref') == 'adaptive/2'
        backends = ("curl_cffi/0.16.3", "httpx/0.28.1", "playwright/1.63.0/chromium")
        if phased:
            grant = plan['network_grant']
            transport.max_requests = min(transport.max_requests, grant['requests'])
            transport.total_bytes = min(transport.total_bytes, grant['decoded_bytes'])
            backends = backends[:2] if plan['stage'] == 'static' else backends[2:]
        try:
            for backend in backends:
                started = time.monotonic()
                before = (transport.http_request_count, transport.http_response_count, transport.decoded_bytes)
                error = None
                info = {}
                try:
                    if backend.startswith("curl_cffi"):
                        body, info, _ = transport.request(arguments["url"], cap=limits["raw_bytes"])
                    elif backend.startswith("httpx"):
                        if transport.max_requests - transport.http_request_count < 1 or transport.total_bytes - transport.decoded_bytes < 1:
                            raise ToolFault('RESPONSE_LIMIT', 'Fetch network grant exhausted', status='limit_exhausted',
                                details={'limit_scope': 'fetch'})
                        legacy_info = {}
                        def received_headers(value, _):
                            nonlocal legacy_info
                            legacy_info = value
                        try:
                            body, info, _ = request_body(arguments["url"],
                                cap=min(limits["raw_bytes"], transport.total_bytes - transport.decoded_bytes),
                                timeout=max(.001, deadline - time.monotonic()),
                                redirects=min(5, transport.max_requests - transport.http_request_count - 1),
                                on_headers=received_headers)
                            info["final_url"] = info["final_url"].split("#", 1)[0]
                            for hop in info["redirects"]:
                                hop["from_url"] = hop["from_url"].split("#", 1)[0]
                        except ToolFault as legacy_error:
                            legacy_info.update({key: value for key, value in legacy_error.details.items()
                                                if key in {"http_request_count", "http_response_count"}})
                            raise
                        finally:
                            if legacy_info:
                                info = legacy_info
                            transport.http_request_count += legacy_info.get("http_request_count", 0)
                            transport.http_response_count += legacy_info.get("http_response_count", 0)
                            transport.decoded_bytes += legacy_info.get("response_decoded_bytes", 0)
                    else:
                        browser_limits = {**limits, 'browser_script_bytes': 8 << 20} if phased else limits
                        body, info = capture(arguments["url"], transport, browser_limits, max(.001, deadline - time.monotonic()))
                        representation = "rendered_dom"
                    proposal = _extract(body, info, limits)
                except ToolFault as fault:
                    error = fault
                    # Failed capture/transport still carries observed HTTP facts.
                    details = getattr(fault, "observations", {})
                    info.update({key: value for key, value in details.items() if value is not None})
                attempts.append({"backend": backend, "outcome": "failed" if error else "returned",
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                    "http_status": info.get("http_status"), "error_code": error.code if error else None,
                    "http_request_count": transport.http_request_count - before[0],
                    "http_response_count": transport.http_response_count - before[1],
                    "decoded_body_bytes": transport.decoded_bytes - before[2]})
                if error is None:
                    break
                if (backend == backends[-1]
                        or backend.startswith("httpx") and arguments.get("mode", "auto") == "static"
                        or error.status in {"limit_exhausted", "timed_out"}
                        or error.code not in _RENDERABLE | ({"FETCH_HTTP_ERROR", "FETCH_UNAVAILABLE"} if backend.startswith("httpx") else set())):
                    raise error
            provenance = proposal["provenance"]
            provenance.update(representation=representation,
                transport="httpx/0.28.1" if backend.startswith("httpx") else "curl_cffi/0.16.3",
                fetch_attempts=attempts, capture=None,
                http_request_count=transport.http_request_count,
                http_response_count=transport.http_response_count)
            if representation == "rendered_dom":
                provenance.update(chosen_charset="utf-8", charset_source="browser")
                provenance["capture"] = {"backend": info["capture_backend"], "captured_at": info["captured_at"], **info["capture"]}
            encode(provenance, limits["provenance_bytes"])
        except ToolFault as fault:
            fault.observations = {"http_status": info.get("http_status"), "redirects": info.get("redirects", []),
                "final_url": info.get("final_url", arguments["url"]), "extraction_version": None,
                "representation": None, "fetch_attempts": attempts}
            fault.usage = {"http_request_count": transport.http_request_count,
                "http_response_count": transport.http_response_count, "decoded_body_bytes": transport.decoded_bytes,
                "text_utf8_bytes": None, "monetary_cost": None}
            # These failures settled inside one fetch worker. Parent admission,
            # cancellation, storage and cleanup failures do not pass this path.
            safe = {key: value for key, value in fault.details.items() if key in {
                "limit_scope", "limit_kind", "limit", "resource_url", "resource_type", "is_main_document",
                "http_request_count", "http_response_count", "decoded_body_bytes", "response_decoded_bytes",
                "transport_error_code"}}
            fault.details = {**safe, "http_status": info.get("http_status"), "failure_scope": "fetch"}
            raise
        observations = {"http_status": info["http_status"], "redirects": info["redirects"],
            "final_url": info["final_url"], "extraction_version": proposal["extraction_version"],
            "representation": representation, "fetch_attempts": attempts}
        usage = {"http_request_count": transport.http_request_count,
            "http_response_count": transport.http_response_count, "decoded_body_bytes": transport.decoded_bytes,
            "text_utf8_bytes": len(proposal["text"]), "monetary_cost": None}
    return {"operation_id": plan["operation_id"], "proposal": {**proposal,
        **{key: pack_component(proposal[key]) for key in ("original", "text", "index")}}}, observations, usage
