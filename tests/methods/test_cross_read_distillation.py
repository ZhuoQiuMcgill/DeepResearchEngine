"""Preserve exact quotations and each independent read through synthesis."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from deepresearch.engine.contracts import EngineError, digest_bytes
from deepresearch.methods.baseline.contracts import ResearchPlan
from deepresearch.methods.baseline.evidence_contracts import SourceDistillation
from deepresearch.methods.baseline.stages.distillation import validate_distillation
from deepresearch.methods.baseline.stages.evidence_delivery import _quote_units
from deepresearch.workflows.components.quote_bindings import bound_quote_units
from tests.methods.test_parallel_baseline import PLAN


def example(parts=("Prefix 😀 A recorded ", "finding continues ", "across reads. Suffix"), start=0):
    segments = []
    for index, text in enumerate(parts):
        end = start + len(text.encode())
        segments.append({"segment_id": f"s{index}", "text": text, "start_byte": start,
            "end_byte": end, "text_sha256": digest_bytes(text.encode()), "read_action_id": f"action{index}",
            "range": {"kind": "pages", "start": 1, "end_exclusive": 4}})
        start = end
    value = SourceDistillation.model_validate({"source_id": "source", "chunk_id": "chunk",
        "content_kind": "substantive", "summary": "A supported finding.", "limitations": [], "reference_queries": [],
        "findings": [{"question": PLAN["questions"][0], "claim": "A supported finding.",
            "segment_id": "s1", "quote": "A recorded finding continues across reads."}]})
    job = {"source": SimpleNamespace(item_id="source", provenance={"media_type": "application/pdf"}),
           "chunk_id": "chunk", "segments": segments}
    return value, job, ResearchPlan.model_validate(PLAN)


def test_cross_read_quote_preserves_exact_bytes_and_separate_actions():
    value, job, plan = example()
    value = validate_distillation(value, job, plan, adjacent_reads=True)
    finding = value.findings[0].model_dump()
    assert finding["segment_id"] == "s0"
    binding, = job["quote_bindings"]
    units = bound_quote_units(finding, binding, {s["segment_id"]: s for s in job["segments"]})
    assert "".join(u["text"] for u in units) == finding["quote"]
    assert [u["read_action_id"] for u in units] == ["action0", "action1", "action2"]
    assert units[0]["start_byte"] == len("Prefix 😀 ".encode())
    record = {"segment_ids": [s["segment_id"] for s in job["segments"]],
              "distillation": value.to_dict(), "quote_bindings": job["quote_bindings"]}
    assert _quote_units([record], {"segments": job["segments"]}) == units


@pytest.mark.parametrize("case", ["disabled", "gap", "unseen", "changed_word", "ambiguous", "overlap"])
def test_absent_or_ambiguous_evidence_stays_rejected(case):
    value, job, plan = example()
    if case == "gap":
        for s in job["segments"][1:]:
            s["start_byte"] += 1
            s["end_byte"] += 1
    if case == "overlap":
        job["segments"][1]["start_byte"] -= 1
        job["segments"][1]["end_byte"] -= 1
    if case == "unseen":
        job["access"] = {"segments": list(job["segments"])}
        job["segments"] = job["segments"][:2]
    if case == "changed_word":
        value.findings[0].quote = value.findings[0].quote.replace("continues", "ends")
    if case == "ambiguous":
        copies = deepcopy(job["segments"])
        for s in copies:
            s["start_byte"] += 1000
            s["end_byte"] += 1000
            s["segment_id"] += "copy"
        job["segments"] += copies
    with pytest.raises(EngineError, match="quotation is absent"):
        validate_distillation(value, job, plan, adjacent_reads=case != "disabled")


@pytest.mark.parametrize("case", ["action", "hash", "gap", "anchor", "quote", "unseen", "byte", "range"])
def test_persisted_bindings_cannot_forge_read_authority(case):
    value, job, plan = example()
    value = validate_distillation(value, job, plan, adjacent_reads=True)
    finding, binding = value.findings[0].model_dump(), job["quote_bindings"][0]
    segments = {s["segment_id"]: s for s in job["segments"]}
    part = binding["parts"][1]
    if case == "action": part["read_action_id"] = "unseen-action"
    if case == "hash": part["text_sha256"] = "sha256:wrong"
    if case == "gap": part["start_byte"] += 1
    if case == "anchor": finding["segment_id"] = "s1"
    if case == "quote": finding["quote"] += "!"
    if case == "unseen": del segments["s2"]
    if case == "byte": segments["s1"]["text"] = "invented"
    if case == "range": part["end_byte"] += 1
    with pytest.raises(EngineError, match="byte authority"):
        bound_quote_units(finding, binding, segments)


def test_quote_spanning_many_small_reads_and_utf8_characters():
    quote = "😀 " + "A long quoted sentence with ﬂowers. " * 20
    value, job, plan = example(tuple(quote[i:i + 13] for i in range(0, len(quote), 13)))
    value.findings[0].quote = quote.strip()
    result = validate_distillation(value, job, plan, adjacent_reads=True)
    assert result.findings[0].quote == quote.strip()
    assert len(job["quote_bindings"][0]["parts"]) > 20


def test_two_full_size_reads_use_bounded_windows_and_keep_original_offsets():
    value, job, plan = example(("x " * 32750 + "A recorded ", "finding continues across reads." + " y" * 32750))
    result = validate_distillation(value, job, plan, adjacent_reads=True)
    assert result.findings[0].quote == "A recorded finding continues across reads."
    assert job["quote_bindings"][0]["parts"][0]["start_byte"] == 65500


def test_cross_read_html_keeps_document_context_and_table_relationships():
    value, job, plan = example(("<table><tr><td>RAM</td><td><b>16 ", "GB</b></td></tr></table>"))
    job["source"].provenance["media_type"] = "text/html"
    value.findings[0].quote = "16 GB"
    result = validate_distillation(value, job, plan, adjacent_reads=True, html_cells=True)
    assert result.findings[0].quote == "16 GB"
    assert len(job["quote_bindings"]) == 1


def test_bindings_survive_filtering_and_revalidation_with_new_indices():
    value, job, plan = example()
    invalid = value.findings[0].model_copy(update={"quote": "Absent claim"})
    value.findings.insert(0, invalid)
    with pytest.raises(EngineError):
        validate_distillation(value, job, plan, adjacent_reads=True)
    assert job["quote_bindings"][0]["finding_index"] == 1
    value.findings = value.findings[1:]
    validate_distillation(value, job, plan, adjacent_reads=True)
    assert job["quote_bindings"][0]["finding_index"] == 0


def test_different_whitespace_repeated_across_boundaries_is_ambiguous():
    value, job, plan = example(("A recorded ", "finding continues across reads.\nA recorded\n", "finding continues across reads."))
    value.findings[0].segment_id = "s0"
    with pytest.raises(EngineError):
        validate_distillation(value, job, plan, adjacent_reads=True)


@pytest.mark.asyncio
async def test_real_archive_read_to_compressed_synthesis_preserves_both_actions(tmp_path, monkeypatch):
    from deepresearch.workflows.components import source_access
    from tests.methods.test_parallel_baseline import (
        ALPHA, Document, _configured, _distillation, _request, _settle, _events, _json)
    from tests.methods.test_selection_baseline import _decision
    from tests.methods.test_systemic_baseline import valid_report
    from examples.benchmarks.audit_research_store import audit

    monkeypatch.setattr(source_access, "_CHUNK_BYTES", 4096)
    quote = "A recorded finding continues across reads."
    text = "X" * 4080 + quote + "\n" + "Unrelated background text.\n" * 1000

    def respond(role, value, ordinal):
        if role == "baseline.selector": return _decision(value)
        if role == "baseline.writer": return valid_report(value)
        if role == "baseline.distiller":
            result = _distillation(value)
            assert len(value["segments"]) > 2
            for finding in result["findings"]:
                finding.update(segment_id=value["segments"][0]["segment_id"], quote=quote)
            result["findings"].insert(0, {**result["findings"][0], "quote": "Unseen model addition"})
            return result

    async with _configured(tmp_path, monkeypatch, {ALPHA: Document(text, media_type="application/pdf")}, respond=respond) as h:
        request = _request(max_sources=1, max_rounds=1, min_substantive_sources=1,
            max_context_bytes=12000).model_copy(update={"method_revision": 12})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        assert len(h.role_calls("distiller")) == 1
        evidence = h.role_calls("analyst")[0]["input"]["evidence"]
        assert "Unrelated background text" not in evidence and "Unseen model addition" not in evidence
        event = next(e for e in await _events(h.service, view.run_id) if e["kind"] == "workflow.evidence.distilled")
        record = await _json(h.service, view.run_id, event["payload"]["validation_ref"])
        assert len(record["distillation"]["findings"]) == len(record["quote_bindings"]) == 2
        assert [b["finding_index"] for b in record["quote_bindings"]] == [0, 1]
        selections = view.context_plan.selections
        assert len(selections) == 2
        binding = record["quote_bindings"][0]
        for selection, part in zip(selections, binding["parts"]):
            assert selection.source_read_action_id == part["read_action_id"]
            assert (selection.start_byte, selection.end_byte) == (part["start_byte"], part["end_byte"])
            assert selection.text_sha256 == part["text_sha256"]
        assert len({s.source_read_action_id for s in selections}) == 2
    checked = audit(tmp_path / "store")
    assert checked["integrity"] == "ok" and checked["findings"] == []
    assert checked["verified_findings"] == 2 and checked["excluded_quotes"] == 1
