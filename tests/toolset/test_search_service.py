"""SearXNG adapter contract checks using only an in-memory HTTP transport."""
from __future__ import annotations

import copy
import json
import socket

import httpx
import pytest
from jsonschema import Draft202012Validator

from deepresearch.engine.toolset import ToolCatalog
from deepresearch.engine.toolset import search_service as service
from deepresearch.engine.toolset.common import ToolFault, digest, validate_arguments
from deepresearch.engine.toolset.discovery_metadata import validate_coverage

QUERY = 'How do I flight from GuangZhou to Montreal? + 中文 %26'
TARGET = 'https://example.org/a%2Fb?x=a%26b&plus=%2B&literal=+#part'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Search adapter tests must not use the network")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def row(target=TARGET, **fields):
    return {"title": "Literal title", "url": target, "content": "Full provider snippet",
            "engines": ["yahoo", "duckduckgo"], **fields}


def respond(monkeypatch, payload=None, *, content=None, status=200, error=None):
    requests, settings = [], []
    body = content if content is not None else json.dumps(payload, ensure_ascii=False).encode()
    original_client = httpx.Client

    def handle(request):
        requests.append(request)
        if error:
            raise error
        return httpx.Response(status, content=body, headers={"content-type": "application/json"})

    def client(**kwargs):
        settings.append(kwargs)
        return original_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(service.httpx, "Client", client)
    return requests, settings, body


def search(maximum=5):
    return service.search({"query": QUERY, "max_results": maximum}, service.plan(), 30)


def validate(payload, maximum=5):
    schema = ToolCatalog().resolve("web.search", 4).unwrap().output_schema
    Draft202012Validator(schema).validate(payload)
    validate_coverage(payload, {"query": QUERY, "max_results": maximum})


def test_literal_query_raw_destinations_engine_identity_and_local_http_counts(monkeypatch):
    requests, settings, body = respond(monkeypatch, {"query": QUERY, "results": [row()]})
    result, observations, usage, fault = search()
    assert fault is None
    assert result["query"] == requests[0].url.params["q"] == QUERY
    assert str(requests[0].url).startswith("http://127.0.0.1:18888/search?")
    assert dict(requests[0].url.params) == {"q": QUERY, "format": "json", "language": "en",
        "engines": "yahoo,duckduckgo", "safesearch": "0", "pageno": "1"}
    assert settings[0]["trust_env"] is False and settings[0]["follow_redirects"] is False
    candidate = result["results"][0]
    assert candidate["url"] == candidate["raw_url"] == TARGET
    assert candidate["engines"] == ["yahoo", "duckduckgo"] and candidate["discovery_only"]
    assert candidate["snippet"] == "Full provider snippet" and candidate["source_date"] is None
    attempt = observations["backend_attempts"][0]
    assert attempt == result["backend_attempts"][0]
    assert attempt["response_bytes"] == len(body) and attempt["response_sha256"] == digest(body)
    assert attempt["upstream_http_request_count"] is None
    assert usage["http_request_count"] == usage["http_response_count"] == 1
    assert usage["monetary_cost"] is None
    validate(result)


def test_partial_engine_failure_keeps_successful_discoveries_and_diagnostics(monkeypatch):
    respond(monkeypatch, {"query": QUERY, "results": [row(engines=["duckduckgo"])],
        "unresponsive_engines": [["yahoo", "timeout"], ["google", "not selected"]]})
    result, observations, _, fault = search()
    assert fault is None and result["results"][0]["engines"] == ["duckduckgo"]
    assert observations["backend_attempts"][0]["engine_errors"] == [{"engine": "yahoo", "reason": "timeout"}]
    assert result["coverage"]["provider_total_results"] is None
    assert result["coverage"]["more_results_available"] is None
    validate(result)


def test_unique_eligible_coverage_preserves_provider_rank_and_caps_returned_rows(monkeypatch):
    rows = [row("javascript:bad"), row(), row(), row("https://example.org/b"), row("https://example.org/c")]
    respond(monkeypatch, {"query": QUERY, "results": rows, "number_of_results": 999999})
    result, observations, _, fault = search(2)
    assert fault is None
    assert [r["provider_rank"] for r in result["results"]] == [2, 4]
    assert [r["rank"] for r in result["results"]] == [1, 2]
    assert result["coverage"] == {"scope": "first_page", "requested_max_results": 2,
        "returned_results": 2, "available_on_page": 3, "omitted_by_max_results": 1,
        "provider_total_results": None, "more_results_available": True}
    attempt = observations["backend_attempts"][0]
    assert (attempt["extracted_count"], attempt["rejected_url_count"], attempt["returned_count"], attempt["kept_count"]) == (5, 1, 3, 2)
    validate(result, 2)
    altered = copy.deepcopy(result)
    altered["coverage"]["available_on_page"] += 1
    with pytest.raises(ToolFault, match="coverage"):
        validate_coverage(altered, {"max_results": 2})


def test_utf8_field_limits_and_missing_fields_are_explicit(monkeypatch):
    respond(monkeypatch, {"query": QUERY, "results": [
        row(title="中" * 2000, content="é" * 9000, engines=["yahoo", "yahoo"], publishedDate="2026-10-03"),
        row("https://example.org/empty", content=None)]})
    result, _, _, fault = search()
    assert fault is None
    first, second = result["results"]
    assert first["title"] == "中" * (4096 // 3) and first["snippet"] == "é" * 8192
    assert first["truncated_fields"] == ["title", "snippet"]
    assert first["engines"] == ["yahoo"] and first["source_date"] == "2026-10-03"
    assert second["missing_fields"] == ["snippet", "source_date"] and second["snippet"] == ""
    validate(result)


@pytest.mark.parametrize("payload", [[], {"query": "rewritten", "results": [row()]},
    {"query": QUERY}, {"query": QUERY, "results": {}}, {"query": QUERY, "results": [None]},
    {"query": QUERY, "results": [row()] * 501}])
def test_malformed_service_payload_is_a_recorded_protocol_failure(monkeypatch, payload):
    respond(monkeypatch, payload)
    result, observations, usage, fault = search()
    assert result is None and fault.code == "SEARCH_PROTOCOL_ERROR"
    attempt = observations["backend_attempts"][0]
    assert attempt["failure_reason"] == "search_protocol_error" and attempt["http_status"] == 200
    assert usage["http_request_count"] == usage["http_response_count"] == 1


@pytest.mark.parametrize("content", [b'{', b'{"query":"a","query":"b"}', b'{"value":NaN}', b'\xff'])
def test_invalid_json_stays_a_typed_failure(monkeypatch, content):
    respond(monkeypatch, content=content)
    result, observations, _, fault = search()
    assert result is None and fault.code == "INVALID_JSON"
    assert observations["backend_attempts"][0]["response_sha256"] == digest(content)


@pytest.mark.parametrize("status", [302, 403, 429, 503])
def test_non_200_service_response_is_not_followed_or_reported_as_empty_success(monkeypatch, status):
    requests, _, _ = respond(monkeypatch, {}, status=status)
    result, observations, usage, fault = search()
    assert result is None and fault.code == "SEARCH_UNAVAILABLE" and len(requests) == 1
    assert observations["backend_attempts"][0]["http_status"] == status
    assert usage["http_response_count"] == 1


def test_transport_failure_counts_dispatch_without_inventing_response(monkeypatch):
    respond(monkeypatch, error=httpx.ConnectError("controlled unavailable service"))
    result, observations, usage, fault = search()
    assert result is None and fault.code == "SEARCH_UNAVAILABLE"
    assert usage["http_request_count"] == 1 and usage["http_response_count"] == 0
    assert observations["backend_attempts"][0]["http_status"] is None


def test_stream_response_byte_cap_is_enforced(monkeypatch):
    respond(monkeypatch, content=b" " * ((1 << 20) + 1))
    result, observations, usage, fault = search()
    assert result is None and fault.code == "SEARCH_RESPONSE_LIMIT"
    assert observations["backend_attempts"][0]["failure_reason"] == "search_response_limit"
    assert usage["http_request_count"] == usage["http_response_count"] == 1


def test_no_usable_rows_keeps_engine_failure_diagnostics(monkeypatch):
    respond(monkeypatch, {"query": QUERY, "results": [row(engines=["unselected"])],
        "unresponsive_engines": [["yahoo", "timeout"], ["duckduckgo", "blocked"]]})
    result, observations, _, fault = search()
    assert result is None and fault.code == "SEARCH_UNAVAILABLE"
    attempt = observations["backend_attempts"][0]
    assert attempt["rejected_url_count"] == 1 and len(attempt["engine_errors"]) == 2


def test_duplicate_engine_diagnostics_cannot_break_closed_success_schema(monkeypatch):
    respond(monkeypatch, {"query": QUERY, "results": [row()], "unresponsive_engines": [
        ["yahoo", "timeout"], ["yahoo", "timeout"], ["duckduckgo", "blocked"]]})
    result, observations, _, fault = search()
    # Reject malformed diagnostic collections or keep one bounded entry per engine.
    if fault is not None:
        assert result is None and fault.code == "SEARCH_PROTOCOL_ERROR"
    else:
        validate(result)
        assert {r["engine"] for r in observations["backend_attempts"][0]["engine_errors"]} == {"yahoo", "duckduckgo"}


def test_registered_schema_is_closed_at_every_result_object(monkeypatch):
    respond(monkeypatch, {"query": QUERY, "results": [row()]})
    result, _, _, _ = search()
    validator = Draft202012Validator(ToolCatalog().resolve("web.search", 4).unwrap().output_schema)
    for path in [(), ("results", 0), ("coverage",), ("backend_policy",), ("backend_attempts", 0)]:
        changed = copy.deepcopy(result)
        target = changed
        for key in path:
            target = target[key]
        target["unexpected"] = True
        assert list(validator.iter_errors(changed)), path


def test_trusted_plan_and_input_limits_are_checked_before_transport(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("Invalid plan must not create HTTP client")
    monkeypatch.setattr(service.httpx, "Client", forbidden)
    altered = service.plan() | {"engines": ["google"]}
    with pytest.raises(ToolFault):
        service.search({"query": QUERY, "max_results": 5}, altered, 30)
    for arguments in ({"query": QUERY, "max_results": 11}, {"query": "中" * 1366}, {"query": QUERY, "extra": True}):
        with pytest.raises(ToolFault):
            validate_arguments("web.search", arguments, 4)
