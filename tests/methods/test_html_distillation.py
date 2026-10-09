"""The hardened method opts in only for HTML and retains archived quotes."""
from types import SimpleNamespace

import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.methods.baseline.contracts import ResearchPlan
from deepresearch.methods.baseline.evidence_contracts import SourceDistillation
from deepresearch.methods.baseline.stages.distillation import validate_distillation
from tests.methods.test_parallel_baseline import PLAN


def example(media_type, *, segment_id="one"):
    source = '<table><tr><td>RAM</td><td>16 GB</td></tr></table>'
    job = {"source": SimpleNamespace(item_id="source", provenance={"media_type": media_type}),
           "chunk_id": "chunk", "segments": [{"segment_id": "one", "text": source, "start_byte": 0}]}
    value = SourceDistillation.model_validate({"source_id": "source", "chunk_id": "chunk",
        "content_kind": "substantive", "summary": "Specification", "limitations": [], "reference_queries": [],
        "findings": [{"question": PLAN["questions"][0], "claim": "RAM is 16 GB.",
                      "segment_id": segment_id, "quote": 'RAM\t</td><td>16 GB</td>'}]})
    return value, job, ResearchPlan.model_validate(PLAN)


@pytest.mark.parametrize("media_type,enabled,accepted", [
    ("text/html", True, True), ("text/html; charset=utf-8", True, True),
    ("application/xhtml+xml", True, True),
    ("application/pdf", True, False), ("text/plain", True, False),
    ("", True, False), (None, True, False), ("text/html", False, False),
])
def test_source_format_and_explicit_opt_in_control_adaptation(media_type, enabled, accepted):
    value, job, plan = example(media_type)
    if accepted:
        result = validate_distillation(value, job, plan, html_cells=enabled)
        assert result.findings[0].quote == 'RAM</td><td>16 GB</td>'
        assert job["validation_changes"] == [{"finding_index": 0, "from_segment_id": "one",
            "to_segment_id": "one", "quote_normalized": True}]
    else:
        with pytest.raises(EngineError, match="quotation is absent"):
            validate_distillation(value, job, plan, html_cells=enabled)


@pytest.mark.parametrize("ambiguous", [False, True])
def test_alternative_segment_must_still_have_unique_match(ambiguous):
    value, job, plan = example("text/html", segment_id="other")
    job["segments"].append({"segment_id": "other", "text": "Unrelated source passage."})
    if ambiguous:
        job["segments"].append({**job["segments"][0], "segment_id": "duplicate"})
        with pytest.raises(EngineError):
            validate_distillation(value, job, plan, html_cells=True)
    else:
        result = validate_distillation(value, job, plan, html_cells=True)
        assert result.findings[0].segment_id == "one"
        assert job["validation_changes"][0]["from_segment_id"] == "other"


@pytest.mark.parametrize("offset,media_type,accepted", [
    (0, "text/html", True), (1, "text/html", False), (None, "text/html", False),
    (0, "text/plain", False), (0, "application/pdf", False),
    (0, "application/xhtml+xml", True),
])
def test_markdown_requires_known_source_start_and_html_provenance(offset, media_type, accepted):
    value, job, plan = example(media_type)
    job["segments"][0].update(text="- First 2\n- Second 3", start_byte=offset)
    value.findings[0].quote = "First 2 Second 3"
    if accepted:
        result = validate_distillation(value, job, plan, markdown_formatting=True)
        assert result.findings[0].quote == "First 2\n- Second 3"
    else:
        with pytest.raises(EngineError):
            validate_distillation(value, job, plan, markdown_formatting=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["html", "markdown", "inline", "markdown_table", "table_emphasis",
    "html_prose", "highlighted_code", "table_link", "markdown_code", "prose_quotes", "nested_break", "table_gap", "prose_hyphen"])
async def test_html_quote_survives_real_archive_to_analyst_without_model_rewrite(tmp_path, monkeypatch, format):
    from tests.methods.test_parallel_baseline import (
        ALPHA, Document, _configured, _distillation, _request, _settle, _events, _json)
    from tests.methods.test_selection_baseline import _decision
    from tests.methods.test_systemic_baseline import valid_report
    source, quote, expected = {
        "html": ('<table><tr><td>RAM</td><td>16 GB</td></tr></table>',
                 'RAM\t</td><td>16 GB</td>', 'RAM</td><td>16 GB</td>'),
        "markdown": ('- RAM 16 GB\n- Storage 256 GB',
                     'RAM 16 GB Storage 256 GB', 'RAM 16 GB\n- Storage 256 GB'),
        "inline": ('<table><tr><td><span>RAM <span>16 GB</span></span></td></tr></table>',
                   'RAM 16 GB', 'RAM <span>16 GB'),
        "markdown_table": ('| RAM | 16 GB |\n| --- | --- |\n| Storage | 256 GB |',
                           'RAM | 16 GB |\n| Storage | 256 GB',
                           'RAM | 16 GB |\n| --- | --- |\n| Storage | 256 GB'),
        "table_emphasis": ('| Item | Result |\n| --- | --- |\n| **RAM** | *16 GB* |',
                           'RAM | 16 GB', 'RAM** | *16 GB'),
        "html_prose": ('<dl><dd><p>RAM <code><span>16 GB</span></code></p></dd></dl>',
                       'RAM `16 GB`', 'RAM <code><span>16 GB'),
        "highlighted_code": ('<pre><code>RAM <span>=</span> 16 GB</code></pre>',
                             'RAM = 16 GB', 'RAM <span>=</span> 16 GB'),
        "table_link": ('<table><tr><th>RAM</th><td>16 <a href="https://example.test/u">GB</a></td></tr></table>',
                       'RAM</th><td>16 GB', 'RAM</th><td>16 <a href="https://example.test/u">GB'),
        "markdown_code": ('`RAM` is `16 GB`', 'RAM is 16 GB', 'RAM` is `16 GB'),
        "prose_quotes": ('The listing states “RAM is 16 GB”.',
                         'The listing states "RAM is 16 GB".', 'The listing states “RAM is 16 GB”.'),
        "nested_break": ('<table><tr><td><span>Intro<br/>RAM is <a href="https://example.test/u">16 GB</a> total.</span></td></tr></table>',
                         'RAM is 16 GB total.', 'RAM is <a href="https://example.test/u">16 GB</a> total.'),
        "table_gap": ('<table><tr><td>RAM</td><td>16 GB</td>\n</tr></table>',
                      '<td>RAM</td><td>16 GB</td></tr>', '<td>RAM</td><td>16 GB</td>\n</tr>'),
        "prose_hyphen": ('- An 8‑core unit has 16 GB of RAM.',
                         'An 8-core unit has 16 GB of RAM.', 'An 8‑core unit has 16 GB of RAM.'),
    }[format]
    text = "The retained specification describes the recorded device configuration.\n" * 40 + '\n' + source

    def respond(role, value, ordinal):
        if role == "baseline.selector":
            return _decision(value)
        if role == "baseline.distiller":
            result = _distillation(value)
            for finding in result["findings"]:
                finding.update(quote=quote, claim="The recorded RAM is 16 GB.")
            result["findings"].append({**result["findings"][0], "quote": quote.replace('16 GB', '160 GB')})
            return result
        if role == "baseline.writer":
            return valid_report(value)

    async with _configured(tmp_path, monkeypatch, {ALPHA: Document(text, media_type="text/html")}, respond=respond) as h:
        request = _request(max_sources=1, max_rounds=1, min_substantive_sources=1).model_copy(update={"method_revision": 12})
        view = await _settle(h.service, (await h.service.start_run(request)).run_id)
        assert view.status == "succeeded", view.error
        assert len(h.role_calls("distiller")) == 1
        evidence = h.role_calls("analyst")[0]["input"]["evidence"]
        assert expected in evidence
        assert "160 GB" not in evidence and "Host excluded 1 findings" in evidence
        event = next(e for e in await _events(h.service, view.run_id) if e["kind"] == "workflow.evidence.distilled")
        validated = await _json(h.service, view.run_id, event["payload"]["validation_ref"])
        assert len(validated["distillation"]["findings"]) == 2
        assert all(f["quote"] == expected for f in validated["distillation"]["findings"])
        assert sum(c.get("quote_normalized", False) for c in validated["validation_changes"]) == 2
