"""Offline harness checks; controlled fetch bytes, real Engine/Storage/read worker."""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deepresearch.engine.connections import Engine, EngineSettings, RunOptions
from deepresearch.engine.contracts import ToolRef
from deepresearch.engine.toolset.common import encode, strict_json
from deepresearch.engine.toolset.process import ProcessOutcome
from deepresearch.engine.toolset.retrieval import extract, pack_component

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("benchmark_web_tools", ROOT / "examples/benchmark_web_tools.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def fixture():
    return json.loads(benchmark.FIXTURE.read_text(encoding="utf-8"))


def test_fixed_questions_and_complete_historical_corpus():
    data = fixture()
    assert [c["question"] for c in data["cases"]] == [
        "compare meta quest 3 and apple vision pro",
        "How do I flight from GuangZhou to Montreal?",
        "What food can help me sleep well?",
    ]
    rows = benchmark.select_corpus(data)
    assert len(rows) == data["unique_url_count"] == 34
    assert sum(len(r["prior_attempts"]) for r in rows) == data["historical_attempt_count"] == 34
    assert [len(benchmark.select_corpus(data, [c])) for c in ("headsets", "flights", "sleep")] == [14, 10, 10]
    assert sum(a["status"] == "failed" for r in rows for a in r["prior_attempts"]) == 16
    # When the ignored source evidence is present, verify exact URL/order/identity/error parity.
    for case in data["cases"]:
        path = ROOT / f"local/cross-topic-diagnostics-20261003/{case['id']}-metrics.json"
        if path.exists():
            original = json.loads(path.read_text(encoding="utf-8"))
            actual = [{"url": r["url"], **{k: a[k] for k in ("source_id", "status", "text_bytes", "error")}}
                      for r in rows for a in r["prior_attempts"] if a["case_id"] == case["id"]]
            assert actual == original["sources"]


def test_dedup_preserves_cross_case_associations_and_exact_urls():
    data = fixture()
    duplicate = copy.deepcopy(data["fetch_corpus"][0])
    duplicate["prior_attempts"][0]["case_id"] = "sleep"
    data["fetch_corpus"].append(duplicate)
    rows = benchmark.select_corpus(data)
    assert len(rows) == 34 and len(rows[0]["prior_attempts"]) == 2
    assert benchmark.select_corpus(data, ["sleep"])[-1]["url"] == duplicate["url"]
    assert len(benchmark.select_corpus(data, ["sleep"])[-1]["prior_attempts"]) == 1
    assert rows[0]["url"] != rows[4]["url"]  # Query parameter order is preserved.


class FetchFixtureWorker:
    """Replace only network acquisition; real document.read subprocesses remain."""
    memory_bytes = 512 << 20

    def __init__(self, delegate, proposal):
        self.delegate, self.proposal = delegate, proposal

    async def run(self, argv, payload, **kwargs):
        request = strict_json(payload, 1 << 20)
        if request["tool"]["name"] == "document.read":
            return await self.delegate.run(argv, payload, **kwargs)
        assert request["tool"]["name"] == "web.fetch", "No other/network tool admitted in this test"
        proposal = self.proposal
        response = {key: request[key] for key in ("schema_version", "request_id", "tool", "invocation")}
        response.update(message_type="worker_response", phase="prepared", error=None,
            prepared={"operation_id": request["plan"]["operation_id"], "proposal": {
                **proposal, **{key: pack_component(proposal[key]) for key in ("original", "text", "index")}}},
            observations={"http_status": 200, "redirects": [], "final_url": "https://example.com/",
                          "extraction_version": proposal["extraction_version"]}, usage={"http_request_count": 1})
        output = encode(response)
        return ProcessOutcome(exit_code=0, stdout=output, stdin_bytes=len(payload), stdout_bytes=len(output), cleanup_complete=True)

    async def close(self, deadline=None):
        return await self.delegate.close(deadline)


async def seeded_engine(tmp_path):
    engine = (await Engine.open(EngineSettings(storage_root=tmp_path / "store"))).unwrap()
    body = ("# Archived source\n" + ("中abc retained full text " * 40 + "\n") * 300).encode()
    info = {"content_type": "text/plain", "requested_url": "https://example.com/",
        "final_url": "https://example.com/", "redirects": [], "retrieved_at": "2026-10-03T00:00:00Z",
        "http_status": 200, "content_encoding": None, "declared_content_length": None,
        "http_request_count": 1, "http_response_count": 1, "response_transfer_bytes": len(body),
        "response_decoded_bytes": len(body), "etag": None, "last_modified": None}
    engine.executor.runner = FetchFixtureWorker(engine.executor.runner, extract(body, info))
    raw = (await engine.run_tool(ToolRef("web.fetch", 1), {"url": "https://example.com/"}, RunOptions())).to_dict()
    assert raw["status"] == "succeeded", raw
    return engine, raw, body


def test_real_storage_hashes_and_full_read_continuations(tmp_path):
    async def check():
        engine, raw, body = await seeded_engine(tmp_path)
        try:
            result = await benchmark.verify_fetch(engine, raw, tmp_path / "evidence")
            assert result["errors"] == []
            assert result["archive_verified"] and result["full_text_read"] and result["ready_for_human_review"]
            assert len(result["reads"]) >= 2
            assert result["read_bytes"] == len(body)
            assert (tmp_path / "evidence/text.txt").read_bytes() == body
            assert result["content"]["usable_evidence"] is None
            assert result["content"]["human_review_required"]
            assert result["content"]["extracted_text_heading_lines"] == ["# Archived source"]
            calls = [json.loads((tmp_path / "evidence" / r["file"]).read_text(encoding="utf-8")) for r in result["reads"]]
            assert "continuation" not in calls[0]["arguments"]
            assert calls[1]["arguments"]["continuation"] == calls[0]["raw"]["result"]["continuation"]
            assert any(c["arguments"]["range"]["start"] == 200 for c in calls)
        finally:
            assert (await engine.close()).complete
    asyncio.run(check())


def test_bad_hash_is_not_ready_even_when_http_and_reads_succeed(tmp_path):
    async def check():
        engine, raw, _ = await seeded_engine(tmp_path)
        try:
            raw["persistence"]["receipt"]["component_digests"]["original"] = "sha256:" + "0" * 64
            result = await benchmark.verify_fetch(engine, raw, tmp_path / "evidence")
            assert not result["archive_verified"] and not result["ready_for_human_review"]
            assert result["full_text_read"] and result["errors"]
            assert result["components"]["text"]["verified"] and result["components"]["index"]["verified"]
        finally:
            assert (await engine.close()).complete
    asyncio.run(check())


def test_document_failure_keeps_raw_error_and_archive_diagnostics(tmp_path, monkeypatch):
    async def check():
        engine, raw, _ = await seeded_engine(tmp_path)
        async def fail(*args, **kwargs):
            raise RuntimeError("controlled read failure")
        monkeypatch.setattr(engine, "run_workflow_tool", fail)
        try:
            result = await benchmark.verify_fetch(engine, raw, tmp_path / "evidence")
            assert result["archive_verified"] and not result["full_text_read"]
            assert not result["ready_for_human_review"]
            assert result["reads"][0]["error"]["message"] == "controlled read failure"
            saved = json.loads((tmp_path / "evidence/read-0001.json").read_text(encoding="utf-8"))
            assert saved["raw"]["error"]["code"] == "RuntimeError"
        finally:
            assert (await engine.close()).complete
    asyncio.run(check())


@pytest.mark.parametrize("phase", ["search", "fetch", "all"])
def test_phases_literal_query_fixed_urls_and_failure_retention(tmp_path, phase):
    class UnavailableEngine:
        async def run_tool(self, ref, arguments, options):
            if ref.name == "web.search":
                raw = {"status": "succeeded", "recording": {"status": "complete"}, "result": {
                    "query": arguments["query"], "searched_at": "2026-10-03T00:00:00Z",
                    "backend_attempts": [{"backend": "controlled"}],
                    "results": [{"url": "https://moving.example/new-result", "snippet": "Full snippet " * 200}]}}
                return SimpleNamespace(to_dict=lambda: raw)
            assert ref.revision == 2
            raise RuntimeError("controlled unavailable fetch")
    args = benchmark.parse_args(["--phase", phase, "--case", "flights", "--max-fetch", "2",
                                 "--fetch-offset", "1", "--search-revision", "4", "--fetch-revision", "2"])
    result = asyncio.run(benchmark.benchmark(UnavailableEngine(), args, fixture(), tmp_path))
    assert len(result["searches"]) == (0 if phase == "fetch" else 1)
    if result["searches"]:
        search = result["searches"][0]
        assert search["arguments"]["query"] == "How do I flight from GuangZhou to Montreal?"
        assert search["raw"]["result"]["results"][0]["snippet"] == "Full snippet " * 200
    assert len(result["fetches"]) == (0 if phase == "search" else 2)
    if result["fetches"]:
        assert [r["url"] for r in result["fetches"]] == [r["url"] for r in benchmark.select_corpus(fixture(), ["flights"])[1:3]]
        assert result["fetch_status_counts"] == {"failed": 2}
        assert all(r["raw"]["error"]["message"] == "controlled unavailable fetch" for r in result["fetches"])
    assert result["ready_for_human_review_count"] == 0
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["status"] == "completed"


def test_content_facts_are_not_relevance_labels():
    summary = benchmark.describe_text("Access denied", b"<h1>Heading <em>one</em></h1><h2>Two</h2>",
        {"media_type": "text/html", "classification": "static_text"})
    assert summary["raw_html_headings"] == [{"level": 1, "text": "Heading one"}, {"level": 2, "text": "Two"}]
    assert "challenge_marker:access denied" in summary["review_flags"]
    assert summary["usable_evidence"] is None


def test_defaults_and_empty_batch():
    args = benchmark.parse_args(["--max-fetch", "0"])
    assert (args.search_revision, args.fetch_revision, args.max_fetch) == (3, 1, 0)
    with pytest.raises(SystemExit):
        benchmark.parse_args(["--max-fetch", "-1"])
