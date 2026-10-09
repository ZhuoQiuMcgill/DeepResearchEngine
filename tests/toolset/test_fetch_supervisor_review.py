"""Offline regressions for the final fetch-supervisor review.

Selection uses extracted, packed captures. Controller fallback runs the real
worker/fetch_v2 code with mocked acquisition. Publication rejection uses SQLite.
Existing recorded integration tests own missing/mismatched counter regressions.
"""
from __future__ import annotations

import asyncio
import copy
import socket

import pytest

from deepresearch.engine.toolset import browser_capture, fetch_transport, worker
from deepresearch.engine.toolset.common import LIMITS, ToolFault, encode, strict_json
from deepresearch.engine.toolset.process import ProcessOutcome
from tests.toolset.test_fetch_supervisor import (
    BODY, COUNTS, FACT, Scenario, Stage, assert_selected, components, html_body,
)
from tests.toolset.test_fetch_v2 import ARTICLE, SHELL, URL, acquisition
from tests.toolset.test_recorded_fetch_supervision import (
    assert_lifecycle, assert_stage_records, fetch, integration,
)


@pytest.fixture(autouse=True)
def prohibit_acquisition(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Review regressions must not acquire network resources or launch a browser")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(fetch_transport.httpx, "Client", forbidden)
    monkeypatch.setattr(fetch_transport, "Session", forbidden)
    monkeypatch.setattr(browser_capture, "sync_playwright", forbidden)


@pytest.mark.parametrize("changed", [True, False], ids=["changed-indentation", "preserved-indentation"])
def test_code_indentation_must_survive_render_selection(monkeypatch, changed):
    original = "if approved:\n    authorize()\n    publish()"
    candidate = "if approved:\n    authorize()\npublish()" if changed else original
    before = BODY.replace("rate = count / minutes", original)
    after = BODY.replace("rate = count / minutes", candidate) + "<p>" + FACT + "</p>"
    scenario = Scenario(monkeypatch, [Stage(body=html_body(before)),
        Stage(body=html_body(after, scripts=False))])
    response, selected = assert_selected(scenario, scenario.run(), "static" if changed else "render")
    static_text = components(scenario.sent[0])["text"].decode()
    rendered_text = components(scenario.sent[1])["text"].decode()
    assert original in static_text and candidate in rendered_text
    assert len(scenario.calls) == 2
    assert original in selected["text"].decode()
    assert response["observations"]["fetch_supervision"]["decision"] == (
        "static_body_not_preserved" if changed else "rendered_with_preservation")
    if changed:
        assert original not in rendered_text
        assert FACT.encode() not in selected["text"]
    else:
        assert FACT.encode() in selected["text"]


def dated_html(body, dates, *, scripts):
    tags = "".join(f'<meta property="{field}" content="{value}">' for field, value in dates)
    return html_body(body, scripts=scripts).replace(b"</head>", tags.encode() + b"</head>")


@pytest.mark.parametrize("kind", ["published", "modified"])
@pytest.mark.parametrize("change", ["removed", "changed", "preserved", "additional"])
def test_document_declared_dates_must_survive_render_selection(monkeypatch, kind, change):
    fields = {"published": "article:published_time", "modified": "article:modified_time"}
    original = [(fields["published"], "2020-01-01"), (fields["modified"], "2021-02-03")]
    altered = list(original)
    target = 0 if kind == "published" else 1
    if change == "removed":
        altered.pop(target)
    elif change == "changed":
        altered[target] = (fields[kind], "2026-10-04")
    elif change == "additional":
        altered.append((fields[kind], "2022-04-05"))
    scenario = Scenario(monkeypatch, [Stage(body=dated_html(BODY, original, scripts=True)),
        Stage(body=dated_html(BODY + "<p>" + FACT + "</p>", altered, scripts=False))])
    retains_static = change in {"removed", "changed"}
    response, selected = assert_selected(scenario, scenario.run(), "static" if retains_static else "render")
    assert len(scenario.calls) == 2
    for sent, pairs in zip(scenario.sent, (original, altered)):
        dates = sent["prepared"]["proposal"]["provenance"]["document_dates"]
        assert dates["origin"] == "document_declared_not_verified" and dates["omitted_count"] == 0
        for group, field in fields.items():
            assert dates[group] == [{"field": f, "value": v} for f, v in pairs if f == field]
    assert response["prepared"]["proposal"]["provenance"]["document_dates"] == (
        scenario.sent[0 if retains_static else 1]["prepared"]["proposal"]["provenance"]["document_dates"])
    assert response["observations"]["fetch_supervision"]["decision"] == (
        "document_dates_not_preserved" if retains_static else "rendered_with_preservation")
    assert (FACT.encode() in selected["text"]) is (not retains_static)


@pytest.mark.parametrize("failure", ["http-503", "fetch-unavailable"])
def test_real_worker_static_shell_then_httpx_failure_still_reaches_renderer(monkeypatch, failure):
    unavailable = ToolFault("FETCH_UNAVAILABLE", "Controlled HTTPX transport failure")
    instances, captures, requests = acquisition(monkeypatch, SHELL, rendered=ARTICLE,
        legacy_body=b"unavailable" if failure == "http-503" else b"",
        legacy_status=503 if failure == "http-503" else None,
        legacy_fault=unavailable if failure == "fetch-unavailable" else None)
    scenario = Scenario(monkeypatch, [Stage(body=SHELL), Stage(body=ARTICLE)])

    async def dispatch(bound, payload, seconds, stdout_cap, stderr_cap):
        assert len(scenario.calls) < 2, "Unexpected worker replay"
        assert strict_json(payload, LIMITS["stdin_bytes"]) == bound
        phase = "static" if not scenario.calls else "render"
        assert bound["plan"]["stage"] == phase
        assert captures == [], "Rendering must wait for the parent's separate dispatch"
        response, exit_code = worker.run(bound, "web.fetch", 3)
        output = encode(response, stdout_cap)
        process = ProcessOutcome(exit_code=exit_code, stdout=output, stdin_bytes=len(payload),
            stdout_bytes=len(output), stderr_bytes=0, cleanup_complete=True, pid=123,
            duration_ms=1)
        scenario.calls.append({"request": copy.deepcopy(bound), "payload": payload,
            "seconds": seconds, "stdout_cap": stdout_cap, "stderr_cap": stderr_cap,
            "process": process})
        scenario.sent.append(copy.deepcopy(response))
        if phase == "static":
            assert response["phase"] == "failed" and response["prepared"] is None
            assert captures == []
        else:
            assert response["phase"] == "prepared" and len(captures) == 1
        return process

    scenario.dispatch = dispatch
    response, data = assert_selected(scenario, scenario.run(), "render")
    static, rendered = scenario.sent
    assert static["error"]["code"] == ("FETCH_HTTP_ERROR" if failure == "http-503" else "FETCH_UNAVAILABLE")
    assert static["error"]["details"]["failure_scope"] == "fetch"
    history = static["observations"]["fetch_attempts"]
    assert [entry["backend"] for entry in history] == ["curl_cffi/0.16.3", "httpx/0.28.1"]
    assert history[0]["error_code"] == "SOURCE_REQUIRES_RENDERING"
    assert history[1]["error_code"] == static["error"]["code"]
    assert history[1]["http_status"] == (503 if failure == "http-503" else None)
    assert all(entry["outcome"] == "failed" for entry in history)
    assert len(instances) == 2 and all(instance.closed for instance in instances)
    assert len(captures) == 1 and len(requests) == 2
    assert requests[0][0] == URL and requests[1][0] == "httpx:" + URL
    assert captures[0]["transport"] is instances[1]
    first, second = [call["request"] for call in scenario.calls]
    assert first["invocation"] == second["invocation"]
    assert first["plan"]["operation_id"] == second["plan"]["operation_id"]
    assert first["request_id"] != second["request_id"]
    assert second["plan"]["network_grant"] == {
        "requests": 40 - static["usage"]["http_request_count"],
        "decoded_bytes": (32 << 20) - static["usage"]["decoded_body_bytes"]}
    assert response["observations"]["fetch_supervision"]["decision"] == "rendered_after_static_failure"
    assert response["observations"]["fetch_supervision"]["network_usage_complete"] is True
    assert data["original"] == ARTICLE
    assert response["observations"]["fetch_attempts"] == history + rendered["observations"]["fetch_attempts"]
    for key in COUNTS:
        assert response["usage"][key] == static["usage"][key] + rendered["usage"][key]


def test_failed_renderer_unknown_backend_rejects_before_snapshot_commit(tmp_path):
    def corrupt(response, request):
        response["observations"]["fetch_attempts"][0]["backend"] = "unplanned-backend"

    async def check():
        stages = [Stage(), Stage(error="FETCH_UNAVAILABLE", counts=(3, 2, 10000), mutate=corrupt)]
        async with integration(tmp_path / "store", stages) as env:
            result = await fetch(env)
            assert result.status == "failed" and result.error.code == "WORKER_PROTOCOL_ERROR"
            assert result.result is None and result.persistence["commit_state"] == "not_committed"
            assert result.persistence["receipt"] is None
            assert_lifecycle(env, result, 0)
            assert_stage_records(env, result)
            assert env.probe.lookups == []
    asyncio.run(check())


@pytest.mark.parametrize("scope", ["fetch", "resource"])
def test_settled_response_byte_overshoot_is_counted_without_clamping(monkeypatch, scope):
    static_bytes = 150000
    residual = (32 << 20) - static_bytes
    observed = residual + 4096

    def limit_details(response, request):
        assert request["plan"]["network_grant"]["decoded_bytes"] == residual
        response["error"]["details"].update(limit_kind="decoded_bytes", limit_scope=scope,
            limit=residual if scope == "fetch" else 2 << 20,
            resource_url="https://example.org/large.js", resource_type="script")

    scenario = Scenario(monkeypatch, [Stage(counts=(2, 2, static_bytes)),
        Stage(error="RESPONSE_LIMIT", counts=(3, 2, observed), mutate=limit_details)])
    response, _ = assert_selected(scenario, scenario.run(), "static")
    diagnostic = response["observations"]["fetch_supervision"]
    assert diagnostic["decision"] == "static_retained_after_render_failure"
    assert diagnostic["render_error_code"] == "RESPONSE_LIMIT"
    assert diagnostic["network_usage_complete"] is True
    assert diagnostic["render_decoded_byte_grant"] == residual
    assert diagnostic["render_decoded_body_bytes"] == observed > residual
    assert diagnostic["known_decoded_body_bytes"] == response["usage"]["decoded_body_bytes"] == (32 << 20) + 4096
    assert response["usage"]["http_request_count"] == 5 and response["usage"]["http_response_count"] == 4
    assert scenario.rows[-1]["decoded_body_bytes"] == observed
    assert response["observations"]["fetch_attempts"][-1]["decoded_body_bytes"] == observed
    assert response["prepared"]["proposal"]["provenance"]["fetch_attempts"][-1]["decoded_body_bytes"] == observed
