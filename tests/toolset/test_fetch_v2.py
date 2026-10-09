"""Adaptive fetch checks with mocked acquisition and real extraction/schema validation."""
from __future__ import annotations

import copy
import asyncio
import json
import socket

import pytest
from jsonschema import Draft202012Validator

from deepresearch.engine.connections import Engine, EngineSettings
from deepresearch.engine.connections.models import ArtifactReadRequest, RunAccessRequest
from deepresearch.engine.contracts import ArtifactRef, RunRef, ToolRef
from deepresearch.engine.toolset import ToolCatalog, browser_capture, fetch_transport, fetch_v2
from deepresearch.engine.toolset.article_extraction import extract_source
from deepresearch.engine.toolset.common import LIMITS, ToolFault, digest, encode, strict_json, validate_arguments
from deepresearch.engine.toolset.process import ProcessOutcome
from deepresearch.engine.toolset.retrieval import unpack_component

URL = "https://example.org/source?literal=+&encoded=%2B"
SHELL = b"<html><body><p>Please enable JavaScript to view this page.</p></body></html>"
ARTICLE = b"<article><h1>Measured observations</h1><p>" + (
    b"The experiment records actual measurements, controls and stated limitations. " * 20
) + b"</p></article>"
COOKIE_CHALLENGE = b"<html><body><p>Cookies must be enabled to view this page. Please reload after enabling cookies.</p></body></html>"


@pytest.fixture(autouse=True)
def no_network_or_browser(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Fetch tests must use mocked transport/capture only")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    # Windows asyncio uses a loopback socketpair for its own wakeup pipe.
    # Block acquisition clients and DNS without breaking the event loop.
    monkeypatch.setattr(fetch_transport.httpx, "Client", forbidden)
    monkeypatch.setattr(fetch_transport, "Session", forbidden)
    monkeypatch.setattr(browser_capture, "sync_playwright", forbidden)


def info(body, status=200, **fields):
    return {"requested_url": URL, "final_url": URL, "redirects": [],
        "retrieved_at": "2026-10-03T00:00:00Z", "http_status": status,
        "content_type": "text/html; charset=utf-8", "content_encoding": None,
        "declared_content_length": str(len(body)), "http_request_count": 1,
        "http_response_count": 1, "response_transfer_bytes": len(body),
        "response_decoded_bytes": len(body), "etag": None, "last_modified": None, **fields}


def acquisition(monkeypatch, body=ARTICLE, *, static_status=200, static_fault=None,
                rendered=ARTICLE, rendered_status=201, render_fault=None, render_counts=(3, 2, 400),
                legacy_body=SHELL, legacy_status=200, legacy_fault=None):
    instances, captures, requests = [], [], []

    class Transport:
        def __init__(self, deadline):
            self.deadline = deadline
            self.total_bytes, self.max_requests = 32 << 20, 40
            self.http_request_count = self.http_response_count = self.decoded_bytes = 0
            self.closed = False
            instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.closed = True

        def request(self, source, *, cap):
            requests.append((source, cap))
            self.http_request_count += 1
            if static_status is not None:
                self.http_response_count += 1
                self.decoded_bytes += len(body)
            if static_fault:
                static_fault.observations = {"http_status": static_status, "final_url": URL, "redirects": []}
                raise static_fault
            return body, info(body, static_status), []

    def capture(source, transport, limits, timeout):
        captures.append({"url": source, "timeout": timeout, "transport": transport})
        transport.http_request_count += render_counts[0]
        transport.http_response_count += render_counts[1]
        transport.decoded_bytes += render_counts[2]
        if render_fault:
            render_fault.observations = {"http_status": rendered_status, "final_url": URL, "redirects": []}
            raise render_fault
        metadata = info(rendered, rendered_status, content_type="text/html; charset=utf-8")
        metadata.update(capture_backend="playwright/1.63.0/chromium", captured_at="2026-10-03T00:00:01Z",
            capture={"relayed_requests": 2, "blocked_requests": 1, "failed_resources": 1,
                     "dom_bytes": len(rendered), "wait_until": "domcontentloaded", "settle_ms": 1000})
        return rendered, metadata

    def legacy(source, *, cap, timeout, redirects, on_headers=None):
        requests.append(("httpx:" + source, cap))
        assert cap <= LIMITS["raw_bytes"] and timeout > 0 and 0 <= redirects <= 5
        metadata = info(legacy_body, legacy_status,
            http_response_count=int(legacy_status is not None),
            response_decoded_bytes=len(legacy_body) if legacy_status is not None else 0)
        if on_headers and legacy_status is not None:
            on_headers(metadata, [])
        if legacy_fault:
            legacy_fault.details = {**metadata, **legacy_fault.details}
            raise legacy_fault
        return legacy_body, metadata, []

    monkeypatch.setattr(fetch_transport, "CurlTransport", Transport)
    monkeypatch.setattr(browser_capture, "capture", capture)
    monkeypatch.setattr(fetch_v2, "request_body", legacy)
    return instances, captures, requests


def fetch(mode=None, limits=None):
    arguments = validate_arguments("web.fetch", {"url": URL, **({"mode": mode} if mode else {})}, 2)
    return fetch_v2.fetch(arguments, {"operation_id": "controlled-operation"}, LIMITS | (limits or {}), 30)


def test_settled_fetch_failure_preserves_limit_scope_and_resource_identity(monkeypatch):
    acquisition(monkeypatch, SHELL, render_fault=ToolFault("RESPONSE_LIMIT", "Limit reached",
        status="limit_exhausted", details={"resource_url": "https://example.org/large.js",
            "resource_type": "script", "limit_scope": "resource", "limit_kind": "decoded_bytes", "limit": 2 << 20}))
    with pytest.raises(ToolFault) as caught:
        fetch("auto")
    details = caught.value.details
    assert details["failure_scope"] == "fetch" and details["limit_scope"] == "resource"
    assert details["resource_url"] == "https://example.org/large.js" and details["limit"] == 2 << 20
    assert caught.value.usage["http_response_count"] > 0


def assembled(prepared):
    proposal = prepared["proposal"]
    components = {key: unpack_component(proposal[key], LIMITS[cap]) for key, cap in
                  [("original", "raw_bytes"), ("text", "text_bytes"), ("index", "index_bytes")]}
    index = json.loads(components["index"])
    result = {"snapshot_ref": {"store_id": "fixture-store", "snapshot_id": "fixture-snapshot", "schema_version": 1},
        "extraction_version": proposal["extraction_version"], "normalization_version": proposal["normalization_version"],
        "line_count": len(index["lines"]), "page_count": None, "provenance": proposal["provenance"],
        "preview": components["text"][:LIMITS["preview_bytes"]].decode("utf-8", errors="ignore")}
    return result, components


def assert_hashes(result, components):
    for role, data in components.items():
        assert result["provenance"][role + "_bytes"] == len(data)
        assert result["provenance"][role + "_sha256"] == digest(data)
    assert json.loads(components["index"])["text_sha256"] == digest(components["text"])


@pytest.mark.parametrize("mode", [None, "auto", "static"])
def test_static_document_never_starts_renderer_and_preserves_original(mode, monkeypatch):
    instances, captures, requests = acquisition(monkeypatch)
    prepared, observations, usage = fetch(mode)
    result, components = assembled(prepared)
    assert prepared["operation_id"] == "controlled-operation"
    assert requests == [(URL, LIMITS["raw_bytes"])] and captures == [] and instances[0].closed
    assert components["original"] == ARTICLE and b"actual measurements" in components["text"]
    provenance = result["provenance"]
    assert provenance["representation"] == observations["representation"] == "content_decoded"
    assert provenance["capture"] is None and provenance["transport"] == "curl_cffi/0.16.3"
    assert len(provenance["fetch_attempts"]) == 1
    assert usage["http_request_count"] == usage["http_response_count"] == 1
    assert usage["decoded_body_bytes"] == len(ARTICLE)
    assert_hashes(result, components)
    Draft202012Validator(ToolCatalog().resolve("web.fetch", 2).unwrap().output_schema).validate(result)


def test_publication_metadata_survives_fetch_without_guessing_a_date(monkeypatch):
    body = (b'<html><head><meta property="article:published_time" content="2024-02-23T13:00:00-05:00">'
            b'<meta name="parsely-pub-date" content="2024-02-23T13:00:08Z">'
            b'<meta property="article:modified_time" content="2024-10-15T21:48:03Z"></head><body>'
            + ARTICLE + b'<aside><time datetime="2026-10-03">Related article</time></aside></body></html>')
    acquisition(monkeypatch, body)
    prepared, _, _ = fetch()
    result, components = assembled(prepared)
    dates = result["provenance"]["document_dates"]
    assert dates["origin"] == "document_declared_not_verified"
    assert dates["published"] == [
        {"field": "article:published_time", "value": "2024-02-23T13:00:00-05:00"},
        {"field": "parsely-pub-date", "value": "2024-02-23T13:00:08Z"}]
    assert dates["modified"] == [{"field": "article:modified_time", "value": "2024-10-15T21:48:03Z"}]
    assert "2026-10-03" not in json.dumps(dates)
    assert components["original"] == body
    assert_hashes(result, components)
    Draft202012Validator(ToolCatalog().resolve("web.fetch", 2).unwrap().output_schema).validate(result)


def test_metadata_bounds_and_unknown_dates_are_explicit(monkeypatch):
    acquisition(monkeypatch, ARTICLE)
    prepared, _, _ = fetch()
    empty = prepared["proposal"]["provenance"]["document_dates"]
    assert empty["published"] == empty["modified"] == []
    head = b"".join(f'<meta property="article:published_time" content="2020-01-{i:02d}">'.encode() for i in range(1, 11))
    body = b"<html><head>" + head + b'</head><body>' + ARTICLE + b"</body></html>"
    acquisition(monkeypatch, body)
    prepared, _, _ = fetch()
    dates = prepared["proposal"]["provenance"]["document_dates"]
    assert len(dates["published"]) == 8 and dates["omitted_count"] == 2


def test_static_shell_fails_without_renderer(monkeypatch):
    instances, captures, _ = acquisition(monkeypatch, SHELL)
    with pytest.raises(ToolFault) as caught:
        fetch("static")
    fault = caught.value
    assert fault.code == "SOURCE_REQUIRES_RENDERING" and captures == [] and instances[0].closed
    assert fault.observations["fetch_attempts"][0]["error_code"] == fault.code
    assert fault.usage["http_request_count"] == fault.usage["http_response_count"] == 2
    assert [a["backend"] for a in fault.observations["fetch_attempts"]] == ["curl_cffi/0.16.3", "httpx/0.28.1"]
    assert fault.usage["text_utf8_bytes"] is None


@pytest.mark.parametrize("mode", [None, "auto"])
def test_auto_shell_fallback_marks_dom_actual_status_counters_and_hashes(monkeypatch, mode):
    instances, captures, _ = acquisition(monkeypatch, SHELL)
    prepared, observations, usage = fetch(mode)
    result, components = assembled(prepared)
    provenance = result["provenance"]
    assert len(captures) == 1 and captures[0]["transport"] is instances[0] and instances[0].closed
    assert 0 < captures[0]["timeout"] <= 30
    assert components["original"] == ARTICLE and components["original"] != SHELL
    assert provenance["representation"] == observations["representation"] == "rendered_dom"
    assert provenance["http_status"] == observations["http_status"] == 201
    assert provenance["chosen_charset"] == "utf-8" and provenance["charset_source"] == "browser"
    assert provenance["capture"]["failed_resources"] == 1 and provenance["capture"]["blocked_requests"] == 1
    assert provenance["capture"]["dom_bytes"] == len(ARTICLE)
    first, legacy, second = provenance["fetch_attempts"]
    assert legacy["backend"] == "httpx/0.28.1" and legacy["outcome"] == "failed"
    assert first["outcome"] == "failed" and first["error_code"] == "SOURCE_REQUIRES_RENDERING"
    assert first["http_status"] == 200 and second["http_status"] == 201
    assert second["outcome"] == "returned" and second["error_code"] is None
    assert (second["http_request_count"], second["http_response_count"], second["decoded_body_bytes"]) == (3, 2, 400)
    assert usage["http_request_count"] == provenance["http_request_count"] == 5
    assert usage["http_response_count"] == provenance["http_response_count"] == 4
    assert usage["decoded_body_bytes"] == 2 * len(SHELL) + 400
    assert_hashes(result, components)
    Draft202012Validator(ToolCatalog().resolve("web.fetch", 2).unwrap().output_schema).validate(result)


@pytest.mark.parametrize("body", [b"<html><body></body></html>", b"<html><body>Verify you are human</body></html>"])
def test_renderable_extraction_faults_get_one_bounded_fallback(monkeypatch, body):
    _, captures, _ = acquisition(monkeypatch, body)
    prepared, _, _ = fetch()
    assert len(captures) == 1
    assert prepared["proposal"]["provenance"]["fetch_attempts"][0]["error_code"] in {"EXTRACTION_EMPTY", "SOURCE_CHALLENGE"}


@pytest.mark.parametrize("status,code", [(206, "PARTIAL_RESPONSE"), (403, "FETCH_HTTP_ERROR"), (429, "FETCH_HTTP_ERROR"), (503, "FETCH_HTTP_ERROR")])
def test_http_failure_does_not_escalate_to_rendering(monkeypatch, status, code):
    instances, captures, _ = acquisition(monkeypatch, static_status=status)
    with pytest.raises(ToolFault) as caught:
        fetch()
    assert caught.value.code == code and not captures and instances[0].closed
    assert caught.value.observations["http_status"] == status
    assert len(caught.value.observations["fetch_attempts"]) == 1
    assert caught.value.usage["http_request_count"] == 1


def test_transport_failure_preserves_zero_response_count(monkeypatch):
    _, captures, _ = acquisition(monkeypatch, static_status=None, static_fault=ToolFault("FETCH_UNAVAILABLE", "controlled"))
    with pytest.raises(ToolFault) as caught:
        fetch()
    assert not captures and caught.value.observations["http_status"] is None
    assert caught.value.usage["http_request_count"] == 1 and caught.value.usage["http_response_count"] == 0


@pytest.mark.parametrize("status,code", [(403, "SOURCE_DENIED"), (429, "SOURCE_DENIED"), (200, "SOURCE_CHALLENGE")])
def test_renderer_failure_retains_both_attempts_and_actual_response_status(monkeypatch, status, code):
    instances, captures, _ = acquisition(monkeypatch, SHELL, rendered_status=status, render_fault=ToolFault(code, "controlled capture failure"))
    with pytest.raises(ToolFault) as caught:
        fetch()
    fault = caught.value
    assert fault.code == code and instances[0].closed and len(captures) == 1
    assert fault.observations["http_status"] == status
    assert [a["outcome"] for a in fault.observations["fetch_attempts"]] == ["failed", "failed", "failed"]
    assert fault.observations["fetch_attempts"][-1]["http_status"] == status
    assert fault.usage["http_request_count"] == 5 and fault.usage["http_response_count"] == 4
    assert fault.usage["decoded_body_bytes"] == 2 * len(SHELL) + 400 and fault.usage["text_utf8_bytes"] is None


def test_renderer_without_response_must_not_inherit_static_http_200(monkeypatch):
    acquisition(monkeypatch, SHELL, rendered_status=None,
        render_fault=ToolFault("BROWSER_UNAVAILABLE", "browser failed before navigation"), render_counts=(0, 0, 0))
    with pytest.raises(ToolFault) as caught:
        fetch()
    attempts = caught.value.observations["fetch_attempts"]
    assert attempts[0]["http_status"] == 200
    assert attempts[-1]["http_status"] is None
    assert attempts[-1]["http_request_count"] == attempts[-1]["http_response_count"] == 0
    assert caught.value.usage["http_request_count"] == caught.value.usage["http_response_count"] == 2


def test_renderer_cannot_turn_non_success_status_into_success(monkeypatch):
    acquisition(monkeypatch, SHELL, rendered_status=500)
    with pytest.raises(ToolFault) as caught:
        fetch()
    assert caught.value.code == "FETCH_HTTP_ERROR"
    assert caught.value.observations["fetch_attempts"][-1]["http_status"] == 500


@pytest.mark.parametrize("render", [False, True])
def test_assembled_v2_output_schema_remains_closed_and_v1_is_unchanged(monkeypatch, render):
    acquisition(monkeypatch, SHELL if render else ARTICLE)
    result, _ = assembled(fetch()[0])
    catalog = ToolCatalog()
    validator = Draft202012Validator(catalog.resolve("web.fetch", 2).unwrap().output_schema)
    validator.validate(result)
    paths = [(), ("provenance",), ("provenance", "fetch_attempts", 0)]
    if render:
        paths.append(("provenance", "capture"))
    for path in paths:
        changed, target = copy.deepcopy(result), None
        target = changed
        for key in path:
            target = target[key]
        target["unexpected"] = True
        assert list(validator.iter_errors(changed)), path
    old = catalog.resolve("web.fetch", 1).unwrap().output_schema["properties"]["provenance"]
    assert "transport" not in old["properties"] and "capture" not in old["properties"]
    assert old["properties"]["representation"] == {"const": "content_decoded"}


def test_mode_defaults_and_closed_input_are_revision_specific():
    assert validate_arguments("web.fetch", {"url": URL}, 1)["mode"] == "static"
    assert validate_arguments("web.fetch", {"url": URL}, 2)["mode"] == "auto"
    for args, revision in [({"url": URL, "mode": "auto"}, 1),
        ({"url": URL, "mode": "browser"}, 2), ({"url": URL, "secret": "not allowed"}, 2)]:
        with pytest.raises(ToolFault):
            validate_arguments("web.fetch", args, revision)


def test_augmented_provenance_still_obeys_size_cap(monkeypatch):
    acquisition(monkeypatch, SHELL)
    with pytest.raises(ToolFault) as caught:
        fetch(limits={"provenance_bytes": 100})
    assert caught.value.code == "LIMIT_EXCEEDED"
    assert caught.value.usage["http_request_count"] >= 1


@pytest.mark.parametrize("mode", ["static", "auto"])
def test_httpx_recovers_empty_curl_203_before_browser(monkeypatch, mode):
    instances, captures, requests = acquisition(monkeypatch, b"<html><body></body></html>",
        static_status=203, legacy_body=ARTICLE)
    prepared, observations, usage = fetch(mode)
    result, components = assembled(prepared)
    provenance = result["provenance"]
    assert not captures and instances[0].closed and len(requests) == 2
    assert [a["backend"] for a in provenance["fetch_attempts"]] == ["curl_cffi/0.16.3", "httpx/0.28.1"]
    assert provenance["fetch_attempts"][0]["http_status"] == 203
    assert provenance["transport"] == "httpx/0.28.1" and provenance["capture"] is None
    assert provenance["representation"] == "content_decoded" and observations["http_status"] == 200
    assert usage["http_request_count"] == usage["http_response_count"] == 2
    assert components["original"] == ARTICLE
    assert_hashes(result, components)
    Draft202012Validator(ToolCatalog().resolve("web.fetch", 2).unwrap().output_schema).validate(result)


@pytest.mark.parametrize("received_response", [False, True])
def test_httpx_failure_counts_are_retained_without_rendering_in_static_mode(monkeypatch, received_response):
    body = b"partial decoded bytes" if received_response else b""
    status = 200 if received_response else None
    instances, captures, _ = acquisition(monkeypatch, SHELL, legacy_body=body, legacy_status=status,
        legacy_fault=ToolFault("FETCH_UNAVAILABLE", "controlled HTTPX failure"))
    with pytest.raises(ToolFault) as caught:
        fetch("static")
    fault = caught.value
    assert fault.code == "FETCH_UNAVAILABLE" and instances[0].closed and not captures
    attempts = fault.observations["fetch_attempts"]
    assert len(attempts) == 2 and attempts[-1]["backend"] == "httpx/0.28.1"
    assert attempts[-1]["http_status"] == status
    assert attempts[-1]["http_request_count"] == 1
    assert attempts[-1]["http_response_count"] == int(received_response)
    assert attempts[-1]["decoded_body_bytes"] == len(body)
    assert fault.usage["http_request_count"] == 2
    assert fault.usage["http_response_count"] == 1 + int(received_response)
    assert fault.usage["decoded_body_bytes"] == len(SHELL) + len(body)


@pytest.mark.parametrize("code,status", [("RESPONSE_LIMIT", "limit_exhausted"), ("DEADLINE_EXCEEDED", "timed_out")])
def test_httpx_budget_or_deadline_failure_never_starts_browser(monkeypatch, code, status):
    _, captures, _ = acquisition(monkeypatch, SHELL,
        legacy_fault=ToolFault(code, "controlled exhausted HTTPX attempt", status=status))
    with pytest.raises(ToolFault) as caught:
        fetch("auto")
    assert caught.value.code == code and caught.value.status == status and not captures
    assert len(caught.value.observations["fetch_attempts"]) == 2
    assert caught.value.usage["http_request_count"] == 2


def test_httpx_non_success_status_is_retained_when_auto_uses_browser(monkeypatch):
    _, captures, _ = acquisition(monkeypatch, SHELL, legacy_body=b"unavailable", legacy_status=503)
    prepared, _, usage = fetch("auto")
    attempts = prepared["proposal"]["provenance"]["fetch_attempts"]
    assert len(captures) == 1 and len(attempts) == 3
    assert attempts[1]["backend"] == "httpx/0.28.1"
    assert attempts[1]["http_status"] == 503 and attempts[1]["error_code"] == "FETCH_HTTP_ERROR"
    assert attempts[2]["http_status"] == 201 and attempts[2]["outcome"] == "returned"
    assert usage["http_request_count"] == 5 and usage["http_response_count"] == 4


@pytest.mark.parametrize("attribute", ['aria-hidden="true"', 'class="article-body content-wrapper"'])
def test_generic_article_wrapper_does_not_prune_body_to_skip_link(attribute):
    paragraphs = [
        "The food diary recorded the timing of evening meals and the participants' later sleep observations. Each entry included the meal description and the time recorded on the following morning.",
        "Researchers compared these observations with a separate control period. The report describes differences between groups and explains why the observations alone cannot establish causation.",
        "The participants also reported bedtime, activity and caffeine intake. Missing diary entries were retained as missing observations rather than replaced with estimated sleep scores.",
    ]
    markup = ('<html><head><title>Food diary observations</title></head><body>'
        '<a href="#main">Skip to content</a><nav>Home About Subscribe</nav>'
        f'<div {attribute}><article id="main"><h1>Food diary observations</h1>'
        '<h2>Methods and results</h2>' + ''.join(f'<p>{p}</p>' for p in paragraphs) +
        '</article></div><footer>Subscribe to our newsletter</footer></body></html>').encode()
    proposal = extract_source(markup, info(markup), LIMITS)
    text = proposal["text"].decode()
    assert all(p in text for p in paragraphs)
    assert len(text) > 500 and text.strip() != "Skip to content"
    assert proposal["original"] == markup
    assert proposal["provenance"]["classification"] == "web_text_unverified"
    assert proposal["extraction_version"] == "trafilatura_markdown/17+trafilatura/2.2.0+markdownify/1.2.3"
    assert proposal["provenance"]["text_sha256"] == digest(proposal["text"])


def test_image_bearing_table_headers_preserve_product_names_and_column_identity():
    # Names occur only in the linked image-bearing headers. Losing them leaves
    # plausible measurements whose product association can no longer be read.
    markup = b"""<html><head><title>Device comparison</title></head><body><main>
        <h1>Device comparison</h1>
        <p>This table compares two devices using recorded specifications. The column headers
        identify the device associated with each measurement.</p>
        <table><thead><tr><th>Specification</th>
        <th><a href="/headset/product-a"><div><img src="/images/a.png" alt="Product A">Product A</div></a></th>
        <th><a href="/headset/product-b"><div><img src="/images/b.png" alt="Product B">Product B</div></a></th>
        </tr></thead><tbody>
        <tr><td>Display width</td><td>2064 pixels</td><td>3660 pixels</td></tr>
        <tr><td>Weight</td><td>515 grams</td><td>600 grams</td></tr>
        <tr><td>Refresh rate</td><td>120 Hz</td><td>100 Hz</td></tr>
        </tbody></table></main></body></html>"""
    final_url = "https://publisher.example/compare/devices"
    proposal = extract_source(markup, info(markup, final_url=final_url), LIMITS)
    text = proposal["text"].decode()
    header = next(line for line in text.splitlines() if line.startswith("| Specification |"))
    cells = header.split("|")
    assert "Product A" in cells[2] and "Product B" in cells[3]
    assert "Product B" not in cells[2] and "Product A" not in cells[3]
    assert "![Product A](https://publisher.example/images/a.png)" in cells[2]
    assert "![Product B](https://publisher.example/images/b.png)" in cells[3]
    for row in ("| Display width | 2064 pixels | 3660 pixels |",
                "| Weight | 515 grams | 600 grams |", "| Refresh rate | 120 Hz | 100 Hz |"):
        assert row in text
    # Autouse guards forbid HTTP clients, browser launch and DNS; these image
    # links are derived solely from archived HTML and the final response URL.
    assert proposal["original"] == markup
    assert proposal["provenance"]["final_url"] == final_url
    assert proposal["provenance"]["text_sha256"] == digest(proposal["text"])


def test_scholarly_abstract_keeps_labelled_sections_instead_of_claiming_fulltext():
    abstract = "This synthetic abstract describes measured observations and the limitations of the available sample."
    markup = ('<html><head><meta name="citation_title" content="Synthetic study">'
        '<meta name="citation_doi" content="10.1234/fixture"></head><body><article>'
        f'<section class="article-abstract"><h2>Abstract</h2><p>{abstract}</p></section>'
        '<div id="FullText"></div></article></body></html>').encode()
    proposal = extract_source(markup, info(markup), LIMITS)
    assert abstract in proposal["text"].decode()
    assert "[Same-body abstract; not full text]" in proposal["text"].decode()
    assert "Title: Synthetic study" in proposal["text"].decode()
    assert proposal["provenance"]["classification"] == "article_abstract"


def test_pdf_and_plain_text_preserve_original_bytes_and_report_extractor():
    from tests.toolset.test_protocol import pdf_fixture
    from deepresearch.engine.toolset.pdf_extraction import VERSION
    for body, media, version in [(b"first\r\nsecond\n", "text/plain", "plain_text/1"),
        (pdf_fixture(["first", "last"]), "application/pdf", VERSION)]:
        proposal = extract_source(body, info(body, content_type=media), LIMITS)
        assert proposal["original"] == body and proposal["extraction_version"] == version
        assert b"first\n" in proposal["text"]
        assert proposal["provenance"]["original_sha256"] == digest(body)


@pytest.mark.parametrize("message", ["Cookies must be enabled to view this page.",
    "Please enable cookies in your browser, then reload this page."])
@pytest.mark.parametrize("status", [200, 203])
def test_short_cookie_challenge_is_not_published_as_article_text(message, status):
    body = f"<html><body><p>{message}</p></body></html>".encode()
    with pytest.raises(ToolFault) as caught:
        extract_source(body, info(body, status), LIMITS)
    assert caught.value.code == "SOURCE_CHALLENGE"


def test_substantive_article_can_quote_cookie_challenge_without_being_rejected():
    body = ARTICLE.replace(b"</article>", b"<p>The browser displayed the message: Cookies must be enabled.</p></article>")
    proposal = extract_source(body, info(body), LIMITS)
    assert b"actual measurements" in proposal["text"]
    assert b"Cookies must be enabled" in proposal["text"]
    assert len(proposal["text"]) > 1000


def test_cookie_challenge_on_both_static_transports_remains_failure(monkeypatch):
    _, captures, _ = acquisition(monkeypatch, COOKIE_CHALLENGE, static_status=203, legacy_body=COOKIE_CHALLENGE)
    with pytest.raises(ToolFault) as caught:
        fetch("static")
    fault = caught.value
    assert fault.code == "SOURCE_CHALLENGE" and not captures
    assert [a["error_code"] for a in fault.observations["fetch_attempts"]] == ["SOURCE_CHALLENGE", "SOURCE_CHALLENGE"]
    assert [a["http_status"] for a in fault.observations["fetch_attempts"]] == [203, 200]
    assert fault.usage["text_utf8_bytes"] is None


@pytest.mark.parametrize("mode", ["auto", "static"])
def test_cookie_challenge_httpx_recovery_archives_exact_components_after_reopen(monkeypatch, tmp_path, mode):
    """Mock only acquisition/worker envelope; commit, close, reopen and reads are real."""
    _, captures, _ = acquisition(monkeypatch, COOKIE_CHALLENGE, static_status=203, legacy_body=ARTICLE)
    expected = extract_source(ARTICLE, info(ARTICLE), LIMITS)

    class Worker:
        memory_bytes = 512 << 20

        async def run(self, argv, payload, **kwargs):
            request = strict_json(payload, LIMITS["stdin_bytes"])
            assert request["tool"] == {"name": "web.fetch", "revision": 2}
            prepared, observations, usage = fetch_v2.fetch(request["arguments"], request["plan"], LIMITS, 30)
            response = {key: request[key] for key in ("schema_version", "request_id", "tool", "invocation")}
            response.update(message_type="worker_response", phase="prepared", prepared=prepared,
                            error=None, observations=observations, usage=usage)
            data = encode(response)
            return ProcessOutcome(exit_code=0, stdout=data, stdin_bytes=len(payload), stdout_bytes=len(data), cleanup_complete=True)

        async def close(self, deadline=None):
            return {"complete": True}

    async def check():
        settings = EngineSettings(storage_root=tmp_path / "store")
        engine = (await Engine.open(settings)).unwrap()
        engine.executor.runner = Worker()
        try:
            result = await engine.run_tool(ToolRef("web.fetch", 2), {"url": URL, "mode": mode})
            assert result.status == "succeeded", result.to_dict()
            assert result.recording["status"] == "complete" and result.persistence["commit_state"] == "committed"
            provenance = result.result["provenance"]
            assert provenance["transport"] == "httpx/0.28.1" and provenance["capture"] is None
            assert not captures and provenance["representation"] == "content_decoded"
            assert [a["http_status"] for a in provenance["fetch_attempts"]] == [203, 200]
            assert provenance["fetch_attempts"][0]["error_code"] == "SOURCE_CHALLENGE"
            assert provenance["fetch_attempts"][1]["outcome"] == "returned"
            Draft202012Validator(engine.catalog.resolve("web.fetch", 2).unwrap().output_schema).validate(result.result)
            receipt = result.persistence["receipt"]
            run_ref = RunRef(engine.storage.store_id, result.invocation["run_id"])
        finally:
            assert (await engine.close()).complete

        reopened = (await Engine.open(settings)).unwrap()
        try:
            refs = {role: ArtifactRef(**receipt[role + "_ref"]) for role in ("original", "text", "index")}
            session = (await reopened.open_run_access(run_ref, RunAccessRequest(
                read_objects=tuple(ArtifactReadRequest(ref) for ref in refs.values())))).unwrap()
            async with session:
                for role, ref in refs.items():
                    handle = (await session.storage.artifacts.open(session.context, ref)).unwrap()
                    data = bytearray()
                    try:
                        while True:
                            chunk = (await handle.read(session.context)).unwrap()
                            data.extend(chunk.bytes)
                            if chunk.eof:
                                break
                            assert chunk.bytes
                    finally:
                        (await handle.aclose(session.context)).unwrap()
                    assert bytes(data) == expected[role]
                    assert digest(data) == receipt["component_digests"][role] == provenance[role + "_sha256"]
                    assert len(data) == provenance[role + "_bytes"]
        finally:
            assert (await reopened.close()).complete

    asyncio.run(check())


@pytest.mark.parametrize('href,base_href,expected', [
    ('#details', '', 'https://example.test/guide/current.html#details'),
    ('other.html', '', 'https://example.test/guide/other.html'),
    ('papers/trial.pdf', '', 'https://example.test/guide/papers/trial.pdf'),
    ('../trial.pdf', '', 'https://example.test/trial.pdf'),
    ('?lang=en', '', 'https://example.test/guide/current.html?lang=en'),
    ('//other.test/paper', '', 'https://other.test/paper'),
    ('https://other.test/paper', '', 'https://other.test/paper'),
    ('paper.pdf', '<base href="/archive/">', 'https://example.test/archive/paper.pdf'),
])
def test_generic_extraction_resolves_links_against_final_document_path(href, base_href, expected):
    markup = (f'<html><head><title>Source references</title>{base_href}</head><body><article>'
        f'<h1>Document references<!-- retained HTML comment --></h1><p>The original methods and result are documented in the '
        f'<a href="{href}">linked evidence</a>. Read that source to check the experiment population '
        'and measurements before drawing a conclusion. The document should preserve exact destinations '
        'because following a reference on a different page can retrieve unrelated content and invalidate '
        'the evidence chain even when the words in this paragraph have been read correctly.</p></article></body></html>').encode()
    proposal = extract_source(markup, info(markup, final_url='https://example.test/guide/current.html'), LIMITS)
    assert f'[linked evidence]({expected})' in proposal['text'].decode()
    assert proposal['original'] == markup
    assert proposal['provenance']['original_sha256'] == digest(markup)
