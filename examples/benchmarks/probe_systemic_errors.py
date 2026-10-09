"""Offline baseline@10 diagnostic probes; observations are NOT acceptance tests.

No credentials or model calls. Uses controlled port responses and, when supplied,
immutable exports from the 2026-10-03 experiment. Does not modify those exports.
Run with the repository's Python environment. --browser additionally exercises
real Chromium through a controlled in-memory HTTP relay (no public requests).
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from deepresearch.engine.contracts import EngineError, digest_bytes
from deepresearch.methods.baseline.contracts import ResearchPlan
from deepresearch.methods.baseline.evidence_contracts import EvidenceReadRequest
from deepresearch.methods.baseline.parallel_workflow import ParallelBaselineMethod
from deepresearch.methods.baseline.selection_contracts import SelectionDecision
from deepresearch.methods.baseline.stages import distillation, roles
from deepresearch.methods.baseline.stages.evidence_delivery import _block
from deepresearch.methods.baseline.stages.reporting import citation_issues
from deepresearch.workflows.components.acquisition import acquire
from deepresearch.workflows.components.parallel import bounded_map
from deepresearch.workflows.components.quotations import locate_quote
from deepresearch.workflows.components.retrieval import _prepare
from deepresearch.workflows.components.source_access import _outcome, _slice
from deepresearch.workflows.contracts import FetchManifest, SourceManifest, SourceRecord


class Port:
    def __init__(self, response=None):
        self.response = response
        self.calls = []
        self.updates = []

    async def run_tool(self, name, arguments):
        self.calls.append({"name": name, "arguments": arguments})
        return self.response

    async def update(self, **value):
        self.updates.append(value)

    async def publish(self, *args):
        return {"schema_version": 1, "store_id": "probe", "artifact_id": "probe"}

    async def emit(self, *args):
        pass


class Context:
    def __init__(self, response=None):
        self.port = Port(response)
        self.run_id = "offline-probe"

    @asynccontextmanager
    async def node(self, *args):
        yield {"detail": {}}


def fixture():
    text = "Recorded source text."
    source = SourceRecord(item_id="source-001", url="https://example.test/article.pdf",
        status="succeeded", snapshot_ref={"store_id": "probe", "snapshot_id": "original"},
        recording_status="complete", persistence_state="committed", line_count=147,
        page_count=None, text_bytes=len(text), text_sha256=digest_bytes(text.encode()),
        provenance={"retrieved_at": "2026-10-03T12:34:56Z", "classification": "abstract",
                    "final_url": "https://example.test/actual-html", "media_type": "text/html"})
    segment = {"segment_id": "seg-001", "text": text, "text_sha256": digest_bytes(text.encode()),
        "range": {"schema_version": 1, "kind": "lines", "start": 1, "end_exclusive": 2},
        "start_byte": 0, "end_byte": len(text), "read_action_id": "read-001"}
    access = {"source_id": source.item_id, "segments": [segment], "read_bytes": len(text),
        "complete": False, "document_bytes": len(text),
        "access_ref": {"schema_version": 1, "store_id": "probe", "artifact_id": "access"}}
    plan = ResearchPlan(objective="Audit evidence", questions=["What is known?"],
                        queries=["evidence"], outline=["Findings"])
    return source, access, plan


async def controlled_probes():
    observations = {}
    source, access, plan = fixture()
    rendered = _block(source, access, [], access["segments"])
    observations["delivery_metadata"] = {
        "input": {"line_count": source.line_count, "page_count": source.page_count,
                  "provenance": source.provenance}, "rendered": rendered,
        "missing_explicit_fields": [key for key in ("line_count", "page_count", "supported_ranges",
            "retrieved_at", "final_url", "media_type") if key not in rendered],
        "note": "A delivered line interval is present; complete bounds and capability declarations are absent."}

    queries = ["site:apple.com Vision Pro after:2025-10-15 -rumor",
               '"Apple Vision Pro" battery specifications',
               "Guangzhou to Montreal flight visa -cargo",
               "C++ memory safety"]
    observations["query_rewrite"] = [{"original": q,
        "rewritten": _prepare(q, None, (), True).prepared,
        "literal_control": _prepare(q, None, (), False).prepared} for q in queries]

    report_cases = {
        "valid_minimal": "A supported fact [source-001].\n\n## References\n[source-001] https://example.test/article.pdf",
        "missing_references": "A supported fact [source-001].",
        "references_only_citation": "An unsupported assertion.\n\n## References\n[source-001] https://example.test/article.pdf",
        "wrong_reference_url": "A supported fact [source-001].\n\n## References\n[source-001] https://unrelated.test/fiction",
        "unknown_id_control": "An assertion [invented-source]."}
    observations["citation_gate"] = {key: citation_issues(value, [source.item_id])
                                     for key, value in report_cases.items()}

    started, cancelled = asyncio.Event(), []
    async def worker(item):
        if item == "bad":
            await started.wait()
            raise EngineError("INVALID_EVIDENCE_REFERENCE", "Controlled chunk failure")
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.append(item)
            raise
    try:
        await bounded_map(["bad", "independent"], worker, concurrency=2)
    except EngineError as error:
        observations["distillation_sibling_cancellation"] = {
            "error_code": error.code, "cancelled_independent_jobs": cancelled}

    failure = {"status": "limit_exhausted", "recording": {"status": "complete"},
        "persistence": {"commit_state": "not_committed"},
        "error": {"code": "RESPONSE_LIMIT", "message": "Single URL body exceeds limit"}}
    context = Context(failure)
    manifest = FetchManifest.model_validate({"items": [
        {"item_id": "new-001", "url": "https://example.test/large"},
        {"item_id": "new-002", "url": "https://example.test/next"}]})
    try:
        await acquire(context, manifest, previous=SourceManifest(items=[source]))
    except EngineError as error:
        observations["local_fetch_limit"] = {"error": error.to_dict(),
            "requested_urls": [call["arguments"]["url"] for call in context.port.calls],
            "retained_source_statuses": [s["status"] for s in context.port.updates[-1]["sources"]["items"]]}

    request = EvidenceReadRequest(source_id=source.item_id,
        range={"kind": "lines", "start": 1, "end_exclusive": 2}, reason="Audit follow-up read")
    requested = request.range.tool_range()
    correct = {"schema_version": 1, "snapshot_ref": source.snapshot_ref.to_dict(),
        "requested_range": requested, "returned_range": requested,
        "text": "ok", "byte_length": 2, "truncated": False,
        "has_more_in_requested_range": False, "has_more_in_document": False,
        "spans": [{"line": 1, "start_byte": 0, "end_byte": 2}],
        "next_position": None, "continuation": None}
    mutations = {
        "valid_control": {},
        "wrong_snapshot": {"snapshot_ref": {"schema_version": 1, "store_id": "probe", "snapshot_id": "foreign"}},
        "wrong_requested_range": {"requested_range": {"kind": "pages", "start": 1, "end_exclusive": 2}},
        "false_byte_length": {"byte_length": 999},
        "outside_requested_span": {"spans": [{"line": 99, "start_byte": 0, "end_byte": 2}]},
        "payload_over_cap": {"text": "x" * 101, "byte_length": 101,
            "spans": [{"line": 1, "start_byte": 0, "end_byte": 101}]}}
    reads = {}
    for name, change in mutations.items():
        value = correct | change
        outcome = {"status": "succeeded", "recording": {"status": "complete"},
            "persistence": {"commit_state": "not_applicable"},
            "process": {"cleanup": {"complete": True}},
            "invocation": {"action_id": "controlled-read"}, "result": value}
        try:
            _slice(_outcome(outcome), source.snapshot_ref.to_dict(), requested, 100, None)
            primary = "accepted"
        except EngineError as error:
            primary = error.code
        try:
            extras = await ParallelBaselineMethod._fulfill_reads(Context(outcome), [request],
                SourceManifest(items=[source]), {source.item_id: access}, "probe.", max_read_bytes=100)
            follow_up = {"status": "accepted", "bytes": sum(len(s[1]["text"].encode()) for s in extras)}
        except EngineError as error:
            follow_up = {"status": error.code}
        reads[name] = {"primary_validator": primary, "follow_up_path": follow_up}
    observations["read_validation_disparity"] = reads

    unsupported = failure | {"status": "failed", "error": {"code": "UNSUPPORTED_RANGE",
        "message": "This immutable snapshot has no physical page map"}}
    try:
        await ParallelBaselineMethod._fulfill_reads(Context(unsupported), [request],
            SourceManifest(items=[source]), {source.item_id: access}, "probe.", max_read_bytes=100)
    except EngineError as error:
        observations["read_error_propagation"] = {"tool_error": unsupported["error"],
                                                  "workflow_error": error.to_dict()}

    calls = []
    async def malformed_role(*args, **kwargs):
        calls.append(kwargs["node_id"])
        return b'{"invalid_json":', {"output_ref": {"artifact_id": "raw"}}
    with patch.object(roles, "invoke_role", malformed_role):
        try:
            await distillation.distill_sources(Context(), {source.item_id: access},
                SourceManifest(items=[source]), "Audit", plan, max_calls=4)
        except EngineError as error:
            observations["distiller_schema_repair"] = {"attempts": len(calls), "error": error.to_dict(),
                "note": "Semantic quotation validation allows two attempts; JSON/contract errors bypass that loop."}
    return observations


def retained_probes(root):
    def read(path):
        return json.loads((root / path).read_text(encoding="utf-8"))
    observed = {}
    raw_selector = read("flights-deepseek-diagnostics/selector.03.output.json")
    try:
        SelectionDecision.model_validate(raw_selector)
        observed["retained_selector"] = {"accepted": True}
    except ValueError as error:
        observed["retained_selector"] = {"accepted": False, "validation_error": str(error)}
    distiller = read("sleep-deepseek-diagnostics/distiller.10.output.json")
    source_input = read("sleep-deepseek-diagnostics/r1.recovery.distill.r1.recovery.source-007.chunk-001.2.input.json")
    quotes = []
    for finding in distiller["findings"]:
        if "One such amino acid" not in finding["quote"]:
            continue
        segment = next(s for s in source_input["segments"] if "One such amino acid" in s["text"])
        exact = next(line.strip() for line in segment["text"].splitlines() if "One such amino acid" in line)
        quotes.append({"model_quote": finding["quote"], "saved_passage": exact,
            "model_quote_matches": locate_quote(finding["quote"], segment["text"]) is not None,
            "saved_passage_matches_control": locate_quote(exact, segment["text"]) is not None,
            "changed_fact_matches_control": locate_quote(exact.replace("melatonin", "fabricated-hormone"), segment["text"]) is not None})
    observed["retained_markdown_quote"] = quotes
    first = read("sleep-deepseek-diagnostics/distiller.09.output.json")
    def matched_findings(output):
        return sum(any(locate_quote(finding["quote"], segment["text"]) is not None
                       for segment in source_input["segments"]) for finding in output["findings"])
    observed["retained_repair_regression"] = {
        "first_findings": len(first["findings"]), "first_matching_quotes": matched_findings(first),
        "retry_findings": len(distiller["findings"]), "retry_matching_quotes": matched_findings(distiller),
        "repair_input_keys": list(source_input), "repair_feedback": source_input["feedback"],
        "note": "Quote matching alone does not certify the semantic correctness of a finding."}
    changes = []
    for file in sorted(root.glob("*-diagnostics/*retrieval.query.*.json")):
        value = json.loads(file.read_text(encoding="utf-8"))
        if value.get("original_query") != value.get("executed_query"):
            changes.append({"file": str(file.relative_to(root)), "original": value.get("original_query"),
                            "executed": value.get("executed_query")})
    observed["actual_query_changes"] = changes
    source_ids = [s["source_id"] for s in read("writer-pairs/headsets-sources.json")]
    draft = (root / "writer-pairs/headsets-deepseek-draft.md").read_text(encoding="utf-8")
    observed["writer_reference_gate"] = {"original_issues": citation_issues(draft, source_ids),
        "issues_after_removing_only_unknown_quality_label": citation_issues(draft.replace("[quality]", "quality"), source_ids),
        "note": "Only an in-memory copy changed; this draft is not an accepted full-run report."}
    observed["retained_failure_metadata"] = read("failure-audit.json")
    return observed


def browser_probe():
    from deepresearch.engine.toolset import browser_capture
    from deepresearch.engine.toolset.common import ToolFault
    from tests.toolset.test_fetch_backends import RelayTransport, html_reply
    observations = {}
    for name, fault in [("ordinary_failure_control", ToolFault("FETCH_UNAVAILABLE", "Auxiliary script unavailable")),
                        ("oversized_auxiliary_script", ToolFault("RESPONSE_LIMIT", "Auxiliary script exceeds per-resource cap", status="limit_exhausted"))]:
        client = RelayTransport({"https://example.test/page": html_reply(
            b'<html><title>Public document</title><body><p>Usable primary article already present.</p><script src="/optional.js"></script></body></html>'),
            "https://example.test/optional.js": fault})
        try:
            dom, info = browser_capture.capture("https://example.test/page", client, {"raw_bytes": 10000}, 15)
            observations[name] = {"status": "succeeded", "article_present": b"Usable primary article" in dom}
        except ToolFault as error:
            observations[name] = {"status": error.status, "code": error.code, "details": error.details,
                                  "observations": error.observations}
        observations[name]["requested_urls"] = [call[0] for call in client.calls]
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    results = {"purpose": "Observe current failures, not prove system acceptance or model capability",
               "controlled": asyncio.run(controlled_probes())}
    if args.experiment:
        results["retained"] = retained_probes(args.experiment)
    if args.browser:
        results["browser"] = browser_probe()
    root = Path(__file__).resolve().parents[2]
    results["source_sha256"] = {str(path.relative_to(root)).replace("\\", "/"):
        hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((root / "src/deepresearch").rglob("*.py"))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "controlled_groups": len(results["controlled"]),
                      "retained_groups": len(results.get("retained", {})), "browser_groups": len(results.get("browser", {}))}))


if __name__ == "__main__":
    main()
