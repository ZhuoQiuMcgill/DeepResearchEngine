"""Complete retained-source reads use real wire contracts and a controlled port."""
from __future__ import annotations

import asyncio
import copy
import json

import pytest

from deepresearch.engine.contracts import DocumentSlice, EngineError, SnapshotRef, digest_bytes
from deepresearch.extensions import ExtensionRegistry, HookDispatcher
from deepresearch.workflows import SourceRecord, WorkflowContext
from deepresearch.workflows.contracts import SourceRange
from deepresearch.workflows.components.source_access import read_retained_source


def test_failed_read_preserves_actionable_cause_and_limit_details():
    from deepresearch.workflows.components.source_access import _outcome
    message = "Shared tool dispatch allowance is exhausted"
    details = {"limit": 128, "resource": "tool_calls"}
    with pytest.raises(EngineError) as caught:
        _outcome({"status": "failed", "recording": {"status": "complete"},
                  "error": {"code": "LIMIT_EXCEEDED", "message": message, "details": details}})
    assert caught.value.code == "LIMIT_EXCEEDED"
    assert caught.value.message == message and caught.value.details == details


def test_source_metadata_exposes_extraction_diagnostic_without_promising_completeness():
    from deepresearch.workflows.components.source_access import source_descriptor
    port = RetainedPort(text="Archived body.")
    port.source.provenance["html_extraction"] = {
        "method": "dom-prose-overlap/1", "semantic_verification": False, "substantial_omission": True}
    assert source_descriptor(port.source)["html_extraction"] == port.source.provenance["html_extraction"]
    port.source.provenance["pdf_extraction"] = {
        "method": "page-text-preservation/1", "semantic_verification": False, "fallback_pages": 2}
    assert source_descriptor(port.source)["pdf_extraction"] == port.source.provenance["pdf_extraction"]


class RetainedPort:
    """Recorded DocumentSlice responses, including PDF separator/range semantics."""

    def __init__(self, *, pages=None, text="", item_id="source-1"):
        self.kind = "pages" if pages is not None else "lines"
        self.text = ("\n".join(pages) if pages is not None else text).encode("utf-8")
        # Native line_spans excludes LF from each unit, including a final LF.
        lines = self.text.split(b"\n") if self.text else []
        if self.text.endswith(b"\n"):
            lines.pop()
        parts = [page.encode("utf-8") for page in pages] if pages is not None else lines
        self.units, offset = [], 0
        for part in parts:
            self.units.append((offset, offset + len(part)))
            offset += len(part) + 1
        self.source = SourceRecord(
            item_id=item_id, url="https://example.org/retained", status="succeeded",
            snapshot_ref={"store_id": "controlled", "snapshot_id": "snapshot-1"},
            page_count=len(parts) if pages is not None else None,
            line_count=len(lines), text_bytes=len(self.text),
            text_sha256=digest_bytes(self.text), recording_status="complete",
            persistence_state="committed",
        )
        self.reads, self.publications, self.events, self.updates = [], [], [], []
        self.positions = {}
        self.transform = None
        self.read_gate = None
        self.read_entered = asyncio.Event()
        self.publication_error = None
        self.event_error = None
        self.active = True

    def assert_active(self):
        if not self.active:
            raise EngineError("CANCELLED", "Controlled cancellation")

    async def update(self, **fields):
        self.updates.append(copy.deepcopy(fields))

    async def emit(self, kind, payload, **kwargs):
        self.events.append((kind, copy.deepcopy(payload), kwargs))
        if kind == self.event_error:
            raise EngineError("RECORDING_INCOMPLETE", "Controlled node recording failure")

    async def run_tool(self, name, arguments):
        assert name == "document.read"
        assert arguments["snapshot_ref"] == self.source.snapshot_ref.to_dict()
        self.reads.append(copy.deepcopy(arguments))
        self.read_entered.set()
        if self.read_gate is not None:
            await self.read_gate.wait()
        interval, cap = arguments["range"], arguments["max_text_bytes"]
        assert interval["kind"] == self.kind and 1 <= cap <= 65536
        assert interval["end_exclusive"] - interval["start"] <= (10 if self.kind == "pages" else 200)
        cursor = arguments["continuation"]
        if cursor is not None:
            bound_range, position = self.positions[cursor]
            assert bound_range == interval, "Continuation must keep its original range"
            unit, offset = position["unit"], position["offset"]
        else:
            unit = interval["start"]
            offset = self.units[unit - 1][0] if unit < interval["end_exclusive"] else 0
        returned_start = unit
        chunks, spans = [], []
        remaining = cap
        while unit < interval["end_exclusive"]:
            finish = self.units[unit][0] if unit + 1 < interval["end_exclusive"] else self.units[unit - 1][1]
            if self.kind == "lines" and unit == len(self.units):
                finish = len(self.text)
            end = min(finish, offset + remaining)
            while end > offset:
                try:
                    self.text[offset:end].decode("utf-8")
                    break
                except UnicodeError:
                    end -= 1
            if finish > offset and end == offset:
                if spans:
                    break
                minimum = len(self.text[offset:].decode("utf-8")[0].encode("utf-8"))
                raise EngineError(
                    "LIMIT_EXCEEDED", "The next UTF-8 codepoint does not fit",
                    {"minimum_next_codepoint_bytes": minimum},
                )
            chunks.append(self.text[offset:end])
            spans.append({
                "line": unit if self.kind == "lines" else None,
                "page": unit if self.kind == "pages" else None,
                "start_byte": offset, "end_byte": end,
            })
            remaining -= end - offset
            if end < finish:
                offset = end
                break
            unit += 1
            offset = self.units[unit - 1][0] if unit < interval["end_exclusive"] else None
            if remaining == 0 and unit < interval["end_exclusive"] and self.units[unit - 1][0] < self.units[unit - 1][1]:
                break
        more = unit < interval["end_exclusive"]
        next_position = {"unit": unit, "offset": offset} if more else None
        next_cursor = f"opaque-{len(self.reads)}" if more else None
        if more:
            self.positions[next_cursor] = (copy.deepcopy(interval), next_position)
        raw = b"".join(chunks)
        value = DocumentSlice(
            snapshot_ref=SnapshotRef("controlled", "snapshot-1"),
            extraction_version="controlled/1", normalization_version="text/1",
            requested_range=copy.deepcopy(interval),
            returned_range={
                "kind": self.kind, "start": returned_start,
                "end_exclusive": spans[-1]["page" if self.kind == "pages" else "line"] + 1 if spans else returned_start,
            },
            text=raw.decode("utf-8"), byte_length=len(raw),
            truncated=more, has_more_in_requested_range=more,
            has_more_in_document=more or interval["end_exclusive"] <= len(self.units),
            next_position=next_position, continuation=next_cursor, spans=spans,
        ).to_dict()
        result = {
            "status": "succeeded", "recording": {"status": "complete"},
            "persistence": {"commit_state": "not_applicable"},
            "invocation": {"action_id": f"action-{len(self.reads)}"}, "result": value,
        }
        return self.transform(result, len(self.reads)) if self.transform else result

    async def publish(self, content, media_type, filename):
        self.publications.append((content, media_type, filename))
        if self.publication_error:
            raise self.publication_error
        return {"schema_version": 1, "store_id": "controlled", "artifact_id": "source-access"}


def context(port):
    return WorkflowContext(
        "run-source-access", "controlled-model", port,
        HookDispatcher(ExtensionRegistry(), port.emit), None,
    )


def delivered(access):
    return "".join(segment["text"] for segment in access["segments"]).encode("utf-8")


def verify_manifest(port, access):
    assert len(port.publications) == 1
    content, media_type, filename = port.publications[0]
    assert media_type == "application/json" and filename.endswith(".json")
    expected = {key: value for key, value in access.items() if key != "access_ref"}
    expected["segments"] = [
        {key: value for key, value in segment.items() if key != "text"}
        for segment in access["segments"]
    ]
    assert json.loads(content) == expected
    assert access["read_bytes"] == sum(
        len(segment["text"].encode("utf-8")) for segment in access["segments"]
    )
    assert len({segment["segment_id"] for segment in access["segments"]}) == len(access["segments"])
    for segment in access["segments"]:
        raw = segment["text"].encode("utf-8")
        assert len(raw) <= 65536
        assert segment["end_byte"] - segment["start_byte"] == len(raw)
        assert segment["text_sha256"] == digest_bytes(raw)
        SourceRange.model_validate(segment["range"])
        assert segment["read_action_id"].startswith("action-")
    assert not any("sources" in update or "context_plan" in update for update in port.updates)


@pytest.mark.asyncio
async def test_pdf_reads_every_page_including_tail_and_inter_batch_separators():
    pages = [f"physical page {i}: supported observation" for i in range(1, 24)]
    pages[-1] += " LAST-PAGE-EVIDENCE"
    port = RetainedPort(pages=pages)
    ctx = context(port)
    access = await read_retained_source(ctx, port.source, node_prefix="r1.map.")
    assert access["complete"] and delivered(access) == port.text
    assert access["read_bytes"] == access["document_bytes"] == len(port.text)
    assert [read["range"]["start"] for read in port.reads] == [1, 10, 19]
    assert "LAST-PAGE-EVIDENCE" in access["segments"][-1]["text"]
    assert all(node.startswith("r1.map.") and port.source.item_id in node for node in ctx.nodes)
    verify_manifest(port, access)
    assert b"LAST-PAGE-EVIDENCE" not in port.publications[0][0]


@pytest.mark.asyncio
async def test_all_line_batches_and_final_unterminated_line_are_read():
    text = "".join(f"line {i}\n" for i in range(1, 451)) + "FINAL UNTERMINATED TAIL"
    port = RetainedPort(text=text)
    access = await read_retained_source(context(port), port.source)
    assert access["complete"] and delivered(access) == port.text
    assert len(port.reads) == 3
    assert all(read["range"]["end_exclusive"] - read["range"]["start"] <= 200 for read in port.reads)
    assert access["segments"][-1]["text"].endswith("FINAL UNTERMINATED TAIL")
    verify_manifest(port, access)


@pytest.mark.asyncio
async def test_long_line_document_does_not_spend_extra_dispatches_on_bridges():
    text = "".join(f"section line {i}: evidence remains exact.\n" for i in range(6000)) + "UNTERMINATED TAIL"
    port = RetainedPort(text=text)
    access = await read_retained_source(context(port), port.source)
    assert access["complete"] and delivered(access) == port.text
    assert len(port.reads) == 31
    assert access["read_bytes"] == len(port.text)
    verify_manifest(port, access)


@pytest.mark.asyncio
async def test_large_unicode_page_advances_all_continuations_without_splitting_utf8():
    port = RetainedPort(pages=["证据😀" * 14000 + "THE END"])
    access = await read_retained_source(context(port), port.source)
    assert access["complete"] and delivered(access) == port.text
    assert len(port.reads) == 3
    assert port.reads[0]["continuation"] is None
    assert all(read["continuation"] is not None for read in port.reads[1:])
    assert all(read["range"] == port.reads[0]["range"] for read in port.reads)
    assert [segment["start_byte"] for segment in access["segments"]] == [
        0, access["segments"][0]["end_byte"], access["segments"][1]["end_byte"],
    ]
    verify_manifest(port, access)


@pytest.mark.asyncio
async def test_explicit_cap_returns_a_recorded_partial_manifest_without_clipping():
    port = RetainedPort(text="x" * 200000)
    access = await read_retained_source(context(port), port.source, max_read_bytes=70000)
    assert not access["complete"] and access["read_bytes"] == 70000
    assert delivered(access) == port.text[:70000]
    assert [read["max_text_bytes"] for read in port.reads] == [65536, 4464]
    verify_manifest(port, access)


@pytest.mark.asyncio
async def test_utf8_codepoint_that_cannot_fit_remaining_allowance_is_explicitly_partial():
    port = RetainedPort(text="ab😀tail")
    access = await read_retained_source(context(port), port.source, max_read_bytes=3)
    assert not access["complete"] and access["read_bytes"] == 2
    assert delivered(access) == b"ab"
    assert len(port.reads) == 2 and port.reads[-1]["max_text_bytes"] == 1
    verify_manifest(port, access)


@pytest.mark.asyncio
async def test_zero_allowance_does_not_claim_source_coverage():
    port = RetainedPort(text="unread source")
    access = await read_retained_source(context(port), port.source, max_read_bytes=0)
    assert not access["complete"] and access["read_bytes"] == 0 and access["segments"] == []
    assert port.reads == []
    verify_manifest(port, access)


@pytest.mark.asyncio
async def test_exact_byte_allowance_can_complete_a_single_range():
    port = RetainedPort(text="x" * 65536)
    access = await read_retained_source(context(port), port.source, max_read_bytes=len(port.text))
    assert access["complete"] and access["read_bytes"] == len(port.text)
    verify_manifest(port, access)


@pytest.mark.asyncio
async def test_pdf_overlap_is_charged_to_the_explicit_read_allowance():
    port = RetainedPort(pages=["p" * 20 for _ in range(11)])
    access = await read_retained_source(context(port), port.source, max_read_bytes=len(port.text))
    assert not access["complete"] and access["read_bytes"] < len(port.text)
    assert delivered(access) == port.text[:access["read_bytes"]]
    verify_manifest(port, access)


@pytest.mark.asyncio
@pytest.mark.parametrize("pages", [None, [], [""], [""] * 23])
async def test_empty_documents_and_zero_text_pages_are_verified_by_real_read_outcomes(pages):
    port = RetainedPort(pages=pages)
    access = await read_retained_source(context(port), port.source)
    assert port.reads, "Zero-byte declarations alone must not imply a verified complete read"
    assert access["complete"] and delivered(access) == port.text
    verify_manifest(port, access)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("text_sha256", digest_bytes(b"different document")),
    ("text_bytes", 42),
])
async def test_complete_document_hash_and_byte_declarations_must_match(field, value):
    port = RetainedPort(text="saved evidence")
    source = port.source.model_copy(update={field: value})
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), source)
    assert error.value.code == "INTEGRITY_ERROR" and port.publications == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    lambda value: value.update(byte_length=1),
    lambda value: value.update(snapshot_ref={"store_id": "other", "snapshot_id": "snapshot-1"}),
    lambda value: value["requested_range"].update(start=2),
    lambda value: value["returned_range"].update(end_exclusive=999),
    lambda value: value["spans"][0].update(start_byte=1),
    lambda value: value["spans"][0].update(end_byte=999),
    lambda value: value["spans"][0].update(line=2),
    lambda value: value.update(spans=[]),
    lambda value: value.update(text="\ud800"),
    lambda value: value.update(has_more_in_document=True),
])
async def test_corrupted_read_metadata_or_utf8_never_produces_an_access_publication(change):
    port = RetainedPort(text="evidence")
    port.transform = lambda result, call: (change(result["result"]) or result)
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "INTEGRITY_ERROR" and port.publications == []


@pytest.mark.asyncio
async def test_pdf_overlap_content_must_remain_identical():
    port = RetainedPort(pages=["page-content"] * 11)

    def corrupt(result, call):
        if call == 2:
            result["result"]["text"] = "!" + result["result"]["text"][1:]
        return result

    port.transform = corrupt
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "INTEGRITY_ERROR" and port.publications == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    lambda value: value.update(continuation=None),
    lambda value: value.update(next_position={"unit": 1, "offset": 0}),
    lambda value: value.update(has_more_in_document=False),
    lambda value: value.update(truncated=False),
])
async def test_invalid_or_nonadvancing_continuations_fail_instead_of_looping(change):
    port = RetainedPort(text="x" * 140000)
    port.transform = lambda result, call: (change(result["result"]) or result)
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "INTEGRITY_ERROR"
    assert len(port.reads) == 1 and port.publications == []


@pytest.mark.asyncio
async def test_a_changed_cursor_cannot_replay_the_same_byte_position():
    port = RetainedPort(text="x" * 140000)

    def replay(result, call):
        if call == 2:
            value = result["result"]
            for span in value["spans"]:
                span["start_byte"] -= 65536
                span["end_byte"] -= 65536
            value["next_position"]["offset"] -= 65536
        return result

    port.transform = replay
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "INTEGRITY_ERROR"
    assert len(port.reads) == 2 and port.publications == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status,recording,persistence,code", [
    ("unknown", "complete", "not_applicable", "OUTCOME_UNKNOWN"),
    ("succeeded", "incomplete", "not_applicable", "RECORDING_INCOMPLETE"),
    ("succeeded", "complete", "unknown", "OUTCOME_UNKNOWN"),
    ("failed", "complete", "not_applicable", "SOURCE_READ_FAILED"),
    ("cancelled", "complete", "not_applicable", "CANCELLED"),
])
async def test_unknown_failure_cancellation_and_incomplete_recording_stop_safely(status, recording, persistence, code):
    port = RetainedPort(text="source")

    def fail(result, call):
        result.update(status=status, recording={"status": recording}, persistence={"commit_state": persistence})
        return result

    port.transform = fail
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == code
    assert port.publications == [] and len(port.reads) == 1
    if code == "OUTCOME_UNKNOWN":
        assert error.value.commit_state == "unknown"


@pytest.mark.asyncio
async def test_cancellation_during_a_read_propagates_and_records_cleanup_without_publication():
    port = RetainedPort(text="source")
    port.read_gate = asyncio.Event()
    ctx = context(port)
    task = asyncio.create_task(read_retained_source(ctx, port.source, node_prefix="cancel."))
    await port.read_entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert port.publications == []
    assert ctx.nodes["cancel.source.read.source-1.0"]["status"] == "cancelled"
    assert any(update.get("cleanup") for update in port.updates)
    assert all("sources" not in update and "context_plan" not in update for update in port.updates)


@pytest.mark.asyncio
async def test_cancellation_after_tool_return_prevents_manifest_publication():
    port = RetainedPort(text="source")

    def cancel(result, call):
        port.active = False
        return result

    port.transform = cancel
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "CANCELLED" and port.publications == []


@pytest.mark.asyncio
async def test_node_recording_failure_cannot_become_success():
    port = RetainedPort(text="source")
    port.event_error = "workflow.node.completed"
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "RECORDING_INCOMPLETE" and port.publications == []


@pytest.mark.asyncio
async def test_unknown_publication_commit_propagates_its_original_effect_state():
    port = RetainedPort(text="source")
    port.publication_error = EngineError(
        "COMMIT_UNKNOWN", "Controlled publication uncertainty",
        observed_effect_state="unknown", commit_state="unknown",
    )
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value is port.publication_error
    assert error.value.commit_state == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("allowance", [-1, True, 1.5, "100"])
async def test_invalid_read_allowances_reject_before_any_read(allowance):
    port = RetainedPort(text="source")
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source, max_read_bytes=allowance)
    assert error.value.code == "INVALID_DATA" and port.reads == [] and port.publications == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"status": "unknown"}, {"recording_status": "incomplete"}, {"persistence_state": "unknown"},
    {"snapshot_ref": None}, {"text_bytes": None}, {"text_sha256": None},
])
async def test_unusable_or_unverifiable_sources_do_not_dispatch_reads(change):
    port = RetainedPort(text="source")
    with pytest.raises(EngineError):
        await read_retained_source(context(port), port.source.model_copy(update=change))
    assert port.reads == [] and port.publications == []


@pytest.mark.asyncio
async def test_source_and_prefix_provide_distinct_node_and_segment_identities():
    first = RetainedPort(text="first source", item_id="source-1")
    second = RetainedPort(text="second source", item_id="source-2")
    ctx = context(first)
    one = await read_retained_source(ctx, first.source, node_prefix="r1.")
    ctx.port = second
    two = await read_retained_source(ctx, second.source, node_prefix="r1.")
    assert one["segments"][0]["segment_id"] != two["segments"][0]["segment_id"]
    assert len(ctx.nodes) == 4


@pytest.mark.asyncio
async def test_repeated_cursor_is_rejected_even_when_its_reported_offset_advances():
    port = RetainedPort(text="x" * 200000)

    def repeat(result, call):
        if call == 2:
            result["result"]["continuation"] = "opaque-1"
        return result

    port.transform = repeat
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "INTEGRITY_ERROR" and port.publications == []
    assert len(port.reads) == 2


@pytest.mark.asyncio
async def test_repeated_read_action_identity_is_rejected():
    port = RetainedPort(text="x" * 140000)

    def repeat(result, call):
        result["invocation"]["action_id"] = "action-1"
        return result

    port.transform = repeat
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "INTEGRITY_ERROR" and port.publications == []
    assert len(port.reads) == 2


@pytest.mark.asyncio
async def test_unknown_effect_in_a_contradictory_success_outcome_is_not_accepted():
    port = RetainedPort(text="source")

    def uncertain(result, call):
        result["error"] = {"code": "READ_UNKNOWN", "commit_state": "unknown"}
        return result

    port.transform = uncertain
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "OUTCOME_UNKNOWN" and error.value.commit_state == "unknown"
    assert port.publications == []


@pytest.mark.asyncio
async def test_span_boundaries_must_not_split_valid_unicode_text():
    port = RetainedPort(text="😀\ntail")

    def split(result, call):
        result["result"]["spans"][0]["end_byte"] = 1
        result["result"]["spans"][1]["start_byte"] = 1
        return result

    port.transform = split
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source)
    assert error.value.code == "INTEGRITY_ERROR" and port.publications == []


@pytest.mark.asyncio
async def test_unrelated_limit_failure_is_not_mistaken_for_local_utf8_allowance_exhaustion():
    port = RetainedPort(text="ab😀tail")

    def limit(result, call):
        result["status"] = "limit_exhausted"
        result["error"] = {"code": "LIMIT_EXCEEDED", "details": {}}
        return result

    port.transform = limit
    with pytest.raises(EngineError) as error:
        await read_retained_source(context(port), port.source, max_read_bytes=3)
    assert error.value.code == "LIMIT_EXCEEDED" and port.publications == []


class NativeRangePort(RetainedPort):
    """Exercise the native range implementation through the component's port."""

    async def run_tool(self, name, arguments):
        from deepresearch.engine.storage._ranges import line_spans, slice_document

        assert name == "document.read" and self.kind == "lines"
        assert arguments["snapshot_ref"] == self.source.snapshot_ref.to_dict()
        self.reads.append(copy.deepcopy(arguments))
        requested = arguments["range"]
        position = None
        if arguments["continuation"] is not None:
            bound_range, position = self.positions[arguments["continuation"]]
            assert bound_range == requested
        value, next_position = slice_document(
            self.text, {"lines": line_spans(self.text), "pages": None},
            requested, arguments["max_text_bytes"], position,
        )
        cursor = f"native-{len(self.reads)}" if next_position else None
        if cursor:
            self.positions[cursor] = (copy.deepcopy(requested), next_position)
        chunk = DocumentSlice(
            snapshot_ref=SnapshotRef("controlled", "snapshot-1"),
            extraction_version="controlled/1", normalization_version="text/1",
            **value, byte_length=len(value["text"].encode("utf-8")),
            next_position=next_position, continuation=cursor,
        )
        return {
            "status": "succeeded", "recording": {"status": "complete"},
            "persistence": {"commit_state": "not_applicable"},
            "invocation": {"action_id": f"action-{len(self.reads)}"},
            "result": chunk.to_dict(),
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("port_type", [RetainedPort, NativeRangePort], ids=["wire", "native-ranges"])
@pytest.mark.parametrize("text", ["one line\n", "first\n\n", "\n"])
async def test_terminal_lf_is_delivered_and_verified_as_complete(port_type, text):
    port = port_type(text=text)
    access = await read_retained_source(context(port), port.source)
    assert access["complete"] and delivered(access) == port.text
    assert access["read_bytes"] == access["document_bytes"] == len(port.text)
    assert digest_bytes(delivered(access)) == port.source.text_sha256
    verify_manifest(port, access)


@pytest.mark.asyncio
@pytest.mark.parametrize("port_type", [RetainedPort, NativeRangePort], ids=["wire", "native-ranges"])
@pytest.mark.parametrize("allowance", [65536, 65537])
async def test_terminal_lf_continuation_obeys_byte_limit_and_preserves_utf8(port_type, allowance):
    port = port_type(text="界" * 21845 + "x\n")
    assert len(port.text) == 65537
    access = await read_retained_source(context(port), port.source, max_read_bytes=allowance)
    assert access["complete"] is (allowance == len(port.text))
    assert access["read_bytes"] == allowance
    assert delivered(access) == port.text[:allowance]
    assert len(port.reads) == (2 if access["complete"] else 1)
    if access["complete"]:
        assert port.reads[1]["continuation"] is not None
        assert port.reads[1]["range"] == port.reads[0]["range"]
        assert access["segments"][-1]["text"] == "\n"
        assert access["segments"][-1]["start_byte"] == 65536
    verify_manifest(port, access)
