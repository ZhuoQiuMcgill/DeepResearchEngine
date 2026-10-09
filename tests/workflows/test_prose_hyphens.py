"""Neutral format-equivalence positives and protected-context negatives."""
from types import SimpleNamespace
import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.methods.baseline.contracts import ResearchPlan
from deepresearch.methods.baseline.evidence_contracts import SourceDistillation
from deepresearch.methods.baseline.stages.distillation import validate_distillation
from deepresearch.workflows.components.quotations import PreparedQuoteSource, locate_quote
from tests.methods.test_parallel_baseline import PLAN

OPTIONS = dict(markdown_links=True, html_cells=True, markdown_formatting=True)


@pytest.mark.parametrize('nonbreaking_source', [True, False])
@pytest.mark.parametrize('body', [
    'Use a long-term plan for 12 records.',
    'Use an 8-core unit with 4 fast cores and 4 efficient cores.',
    'Use a **long-term** plan for 12 records.',
    'Use a [long-term](https://example.test/long-term "long-term title") plan.',
    'Use a long-term plan and keep `literal-code` exact.',
    'Use a long-term plan,\nonly when ready.',
    'Use a long-term plan,\r\nonly when ready.',
    '- Use a long-term plan.\n- Keep 12 records.',
    '* Use a long-term plan.\n\n* Keep 12 records.',
    '+ Use a long-term plan,\n  only when ready.',
    '- Use a long-term plan,\r\n  only when ready.',
])
def test_bidirectional_original_chars_spans_and_utf8(nonbreaking_source, body):
    # Change only the visible compound, retaining destinations/code/title.
    alternate = body.replace('a long-term', 'a long‑term').replace('an 8-core', 'an 8‑core')
    alternate = alternate.replace('**long-term**', '**long‑term**').replace('[long-term]', '[long‑term]')
    original, query = (alternate, body) if nonbreaking_source else (body, alternate)
    text = '😀 Préface.\n\n' + original + '\n\nOther prose.'
    source = PreparedQuoteSource(text, **OPTIONS)
    assert source.locate(query) == original
    start = text.index(original)
    assert source.locate_spans(query) == [(start, start + len(original))]
    byte_start = len(text[:start].encode('utf-8'))
    data = original.encode('utf-8')
    assert text.encode('utf-8')[byte_start:byte_start + len(data)] == data
    assert source.locate(query) == original


@pytest.mark.parametrize('text,query', [
    ('Use a **long‑term** plan.', 'Use a long-term plan.'),
    ('- Use an **8‑core** unit.\n- Keep 12 records.', 'Use an 8-core unit. Keep 12 records.'),
    ('Use a [long‑term](https://example.test/r) plan.', 'Use a long-term plan.'),
    ('An editor says “Use a long‑term plan.”', '"Use a long-term plan."'),
    ('Use a long‑term plan and `“literal‑code”` exactly.', 'Use a long-term plan and `“literal‑code”` exactly.'),
])
def test_composes_with_existing_views(text, query):
    assert locate_quote(query, text, **OPTIONS) == text.removeprefix('- ').removeprefix('An editor says ')


@pytest.mark.parametrize('wrapper', [
    '`{}`', '``{}``', '```text\n{}\n```', '~~~\n{}\n~~~', '    {}',
    '<pre>{}</pre>', '<code>{}</code>', '<p>{}</p>', '<em>{}</em>',
    '<p title="{}">Exact attribute.</p>', '<!-- {} -->', '<script>{}</script>',
    '<math>{}</math>', '<svg><text>{}</text></svg>',
    '> {}', '1. {}', '# {}', '| Label |\n| --- |\n| {} |',
    '- Parent\n  - {}', '- {}\n\n  Another paragraph.',
    '- {}\n  ```text\n  literal\n  ```',
])
def test_unsupported_block_contexts_remain_literal(wrapper):
    original = 'Use a long‑term plan.'
    text = wrapper.format(original)
    assert locate_quote(original, text, **OPTIONS) == original
    assert locate_quote(original.replace('‑', '-'), text, **OPTIONS) is None


@pytest.mark.parametrize('text', [
    'Use https://example.test/long‑term now.', 'Use www.example.test/long‑term now.',
    'Use example.test/long‑term now.', 'Use mailto:long‑term@example.test now.',
    'Use urn:long‑term now.', 'Use long‑term@example.test now.',
    'Use [a plan](https://example.test/long‑term) now.',
    'Use [a plan](https://example.test/r "long‑term") now.',
    'Use `<em>long‑term</em>` now.', 'Use `long‑term` now.',
    'Use &quot;long‑term&quot; now.', 'Use a long&#x2011;term plan.',
    'Use a long‑term &amp; ready plan.', 'Use a long\\‑term plan.',
    'Use \\*long‑term now.', 'Use $long‑term$ now.', 'Use \\(long‑term\\) now.',
    'Use long‑term^2 now.', 'Use long‑term = 12 now.',
    'Use long‑term + 12 now.', 'Use long‑term × 12 now.',
    'Keep 12‑24 records.', 'Keep 1.2‑3.4 units.', 'Keep ‑12 records.',
    'Keep 12 ‑ 4 records.', 'Keep −12 records.', 'Keep 12–24 records.',
    'Use Model‑Unit now.', 'Use model_id‑token now.', 'Use item8‑token now.',
    'Use long‑term.identifier now.', 'Use object.long‑term now.',
    'Use long‑term/path now.', 'Use variable‑x now.', 'Use x‑variable now.',
    'Use alpha‑beta‑gamma now.', 'Use 1234‑unit now.',
])
def test_code_urls_entities_escapes_math_numbers_and_identifier_shapes(text):
    assert locate_quote(text, text, **OPTIONS) == text
    query = text.replace('‑', '-').replace('−', '-').replace('–', '-').replace('&#x2011;', '-')
    assert query != text
    assert locate_quote(query, text, **OPTIONS) is None


@pytest.mark.parametrize('query', [
    'Use a long–term plan.', 'Use a long‐term plan.', 'Use a long−term plan.',
    'Use a longterm plan.', 'Use a Long-term plan.', 'Use a long-term plans.',
    'Use a long-term plan!', 'Use a long-term 12 plan.', 'Use a short-term plan.',
])
def test_all_other_changes_remain_exact(query):
    assert locate_quote(query, 'Use a long‑term plan.', **OPTIONS) is None


@pytest.mark.parametrize('options', [{}, {'markdown_links': True}, {'html_cells': True}, {'markdown_formatting': True}])
def test_both_format_admissions_required(options):
    assert locate_quote('Use a long-term plan.', 'Use a long‑term plan.', **options) is None


def test_code_and_url_positions_in_mixed_paragraph_stay_literal():
    text = 'Use a long‑term plan with `long‑term` and [records](https://example.test/long‑term).'
    query = text.replace('a long‑term', 'a long-term')
    assert locate_quote(query, text, **OPTIONS) == text
    assert locate_quote(query.replace('`long‑term`', '`long-term`'), text, **OPTIONS) is None
    assert locate_quote(query.replace('/long‑term', '/long-term'), text, **OPTIONS) is None
    assert locate_quote('long-term', '`long‑term` only.', **OPTIONS) is None


def test_curly_quotes_do_not_gain_list_admission():
    assert locate_quote('"Use a long-term plan."', '- “Use a long‑term plan.”', **OPTIONS) is None
    assert locate_quote('“Use a long-term plan.”', '- “Use a long‑term plan.”', **OPTIONS) == '“Use a long‑term plan.”'


def test_prior_valid_match_has_priority_and_new_spans_are_enumerated():
    text = 'Use a long‑term plan.\n\nUse a long-term plan.'
    query = 'Use a long-term plan.'
    source = PreparedQuoteSource(text, **OPTIONS)
    assert source.locate(query) == query
    later = text.index(query)
    assert source.locate_spans(query) == [(0, len(text.split('\n')[0])), (later, later + len(query))]


@pytest.mark.parametrize('text,query', [
    ('Use an 18‑core unit.', '8-core'), ('Use an 18‑core unit.', '8-core unit.'),
    ('Use a along‑term plan.', 'long-term'), ('Use a long‑term plan.', 'long-ter'),
    ('Use a long‑term plan.', 'ong-term'), ('Use an 18-core unit.', '8‑core'),
    ('Use a **long**‑term plan.', 'ong-term'),
])
def test_new_equivalence_cannot_match_partial_compounds_or_numeric_suffixes(text, query):
    assert locate_quote(query, text, **OPTIONS) is None


def test_entire_compound_may_use_inline_emphasis_on_either_side():
    text = 'Use a **long**‑term plan.'
    assert locate_quote('long-term', text, **OPTIONS) == 'long**‑term'


def test_compound_spanning_prefix_never_enters_returned_evidence():
    assert locate_quote('8-core', '8‑core unit.', markdown_prefix='Use an 1', **OPTIONS) is None


def test_prefix_supplies_only_context_and_protects_other_blocks():
    assert locate_quote('Use a long-term plan.', 'Use a long‑term plan.\n```', markdown_prefix='```text\n', **OPTIONS) is None
    assert locate_quote('Use a long-term plan.', 'long‑term plan.', markdown_prefix='Use a ', **OPTIONS) is None
    assert locate_quote('long-term plan.', 'long‑term plan.', markdown_prefix='Use a ', **OPTIONS) == 'long‑term plan.'
    assert locate_quote('term plan.', 'term plan.', markdown_prefix='Use a long‑', **OPTIONS) == 'term plan.'
    assert locate_quote('long-term', 'term', markdown_prefix='Use a long‑', **OPTIONS) is None


@pytest.mark.parametrize('error', [IndexError, RecursionError])
def test_parser_failure_preserves_exact(monkeypatch, error):
    from markdown_it import MarkdownIt
    def fail(*args, **kwargs):
        raise error('unsupported parsing')
    monkeypatch.setattr(MarkdownIt, 'parse', fail)
    assert locate_quote('Use a long-term plan.', 'Use a long‑term plan.', **OPTIONS) is None
    assert locate_quote('Use a long‑term plan.', 'Use a long‑term plan.', **OPTIONS) == 'Use a long‑term plan.'


@pytest.mark.parametrize('text,query,prefix', [
    ('Use a long‑term plan.' + 'x' * 65536, 'Use a long-term plan.', ''),
    ('Use a long‑term plan.' + '😀' * 17000, 'Use a long-term plan.', ''),
    ('Use a long‑term plan.', 'Use a long-term plan.' + 'x' * 2048, ''),
    ('Use a long‑term plan.', '\ud800long-term', ''),
    ('\ud800long‑term', 'long-term', ''),
    ('Use a long‑term plan.', 'Use a long-term plan.', 'x' * 2097153),
    ('Use a long‑term plan.', 'Use a long-term plan.', '\ud800'),
], ids=['long-source', 'utf8-source', 'long-query', 'invalid-query', 'invalid-source', 'long-prefix', 'invalid-prefix'])
def test_existing_bounds_and_utf8_validation(text, query, prefix):
    assert locate_quote(query, text, markdown_prefix=prefix, **OPTIONS) is None


@pytest.mark.parametrize('media_type,offset,accepted', [
    ('text/html', 0, True), ('application/xhtml+xml', 0, True),
    ('text/html; charset=utf-8', 0, True), ('text/plain', 0, False),
    ('application/pdf', 0, False), ('text/html', 1, False), ('text/html', None, False),
])
def test_distillation_provenance_and_known_context(media_type, offset, accepted):
    text = '- Use an 8‑core unit with 4 fast cores.'
    job = {'source': SimpleNamespace(item_id='source', provenance={'media_type': media_type}),
           'chunk_id': 'chunk', 'segments': [{'segment_id': 'one', 'text': text, 'start_byte': offset}]}
    value = SourceDistillation.model_validate({'source_id': 'source', 'chunk_id': 'chunk',
        'content_kind': 'substantive', 'summary': 'Unit guidance.', 'limitations': [], 'reference_queries': [],
        'findings': [{'question': PLAN['questions'][0], 'claim': 'Use the unit.',
                      'segment_id': 'one', 'quote': 'Use an 8-core unit with 4 fast cores.'}]})
    if accepted:
        result = validate_distillation(value, job, ResearchPlan.model_validate(PLAN), **OPTIONS)
        assert result.findings[0].quote == text[2:]
        assert job['validation_changes'][0]['quote_normalized'] is True
    else:
        with pytest.raises(EngineError, match='quotation is absent'):
            validate_distillation(value, job, ResearchPlan.model_validate(PLAN), **OPTIONS)
