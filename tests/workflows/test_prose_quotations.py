"""Prose delimiter compatibility returns exact original evidence only."""
from types import SimpleNamespace

import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.methods.baseline.contracts import ResearchPlan
from deepresearch.methods.baseline.evidence_contracts import SourceDistillation
from deepresearch.methods.baseline.stages.distillation import validate_distillation
from deepresearch.workflows.components.quotations import PreparedQuoteSource, locate_quote
from tests.methods.test_parallel_baseline import PLAN

OPTIONS = dict(markdown_links=True, html_cells=True, markdown_formatting=True)


@pytest.mark.parametrize('curly_source', [True, False])
@pytest.mark.parametrize('body', [
    'Keep 12 records, only if ready.',
    'Keep **12 records**, only if ready.',
    'Keep [12 records](https://example.test/records), only if ready.',
    'Keep [12 records](https://example.test/records "Archive title"), only if ready.',
    'Keep `12 records`, only if ready.',
    'Keep 12 records,\nonly if ready.',
    'Keep 12 records,\r\nonly if ready.',
], ids=['plain', 'emphasis', 'link', 'titled-link', 'code', 'lf', 'crlf'])
def test_paired_delimiters_return_original_characters_and_utf8_offsets(curly_source, body):
    original = ('“' + body + '”') if curly_source else ('"' + body + '"')
    query = ('"' + body + '"') if curly_source else ('“' + body + '”')
    text = '😀 Préface.\n\nAn editor says ' + original + ' today.\n\nOther prose.'
    source = PreparedQuoteSource(text, **OPTIONS)
    assert source.locate(query) == original
    start = text.index(original)
    assert source.locate_spans(query) == [(start, start + len(original))]
    byte_start = len(text[:start].encode('utf-8'))
    assert text.encode('utf-8')[byte_start:byte_start + len(original.encode('utf-8'))] == original.encode('utf-8')
    assert source.locate(query) == original  # Reused parsing retains the map.


def test_delimiters_combine_with_existing_visible_link_and_emphasis_views():
    text = 'An editor says “Keep **12 [records](https://example.test/r)** only if ready.” today.'
    assert locate_quote('"Keep 12 records only if ready."', text, **OPTIONS) == '“Keep **12 [records](https://example.test/r)** only if ready.”'


@pytest.mark.parametrize('changed', [
    '"keep 12 records, only if ready."',
    '"Keep 13 records, only if ready."',
    '"Keep 12 records, if ready."',
    '"Keep 12 records, only if not ready."',
    '"Keep records 12, only if ready."',
    '"Keep 12 records; only if ready."',
    '"Keep 12 records, only if ready!"',
    '"Keep 12 records, only if ready.\' ',
    '“Keep 12 records, only if ready.“',
    '”Keep 12 records, only if ready.”',
    '«Keep 12 records, only if ready.»',
    '“Keep 12 records, only if ready."',
    'Keep 12 records, only if ready."',
    '"Keep 12 records, only if ready.',
])
def test_words_values_negation_order_other_punctuation_and_unpaired_quotes_stay_exact(changed):
    assert locate_quote(changed, 'An editor says “Keep 12 records, only if ready.” today.', **OPTIONS) is None


@pytest.mark.parametrize('wrapper', [
    '`{}`', '``{}``', '```text\n{}\n```', '~~~\n{}\n~~~', '    {}',
    '<pre>{}</pre>', '<code>{}</code>', '<script>{}</script>',
    '<math>{}</math>', '<svg><text>{}</text></svg>', '<!-- {} -->',
    '<p title="{}">Exact attribute.</p>',
    '<a href="https://example.test/{}">Exact destination.</a>',
    '> {}', '- {}', '1. {}', '# {}',
    '| Label |\n| --- |\n| {} |',
])
def test_literal_and_unsupported_contexts_never_acquire_prose_equivalence(wrapper):
    original = '“Keep 12 records.”'
    text = wrapper.format(original)
    assert locate_quote(original, text, **OPTIONS) == original
    assert locate_quote('"Keep 12 records."', text, **OPTIONS) is None


@pytest.mark.parametrize('text,query', [
    ('The formula is “velocity” = 12.', '"velocity" = 12'),
    ('The formula is x = “velocity”.', 'x = "velocity"'),
    ('Use $“velocity”$ here.', '$"velocity"$'),
    ('The symbol is “velocity”^2.', '“velocity"^2'),
    ('The value is “x + y”.', '"x + y"'),
    ('The value is “12”.', '"12"'),
    ('The value is 12″ and 14″.', '12" and 14"'),
    ('The value is 12” and 14”.', '12" and 14"'),
    ('The derivative is f′ and f″.', 'f\' and f"'),
    ('The symbol is “velocity”′.', '"velocity"′'),
    ('The variable is word“velocity”word.', 'word"velocity"word'),
    ('Use https://example.test/“record” now.', 'https://example.test/"record"'),
    ('Use www.example.test/“record” now.', 'www.example.test/"record"'),
    ('Use [records](https://example.test/“record”) now.', '[records](https://example.test/"record")'),
    ('Use [records](https://example.test/r "“record”") now.', '[records](https://example.test/r "\"record\"")'),
    ('The editor says “A &amp; B”.', '"A &amp; B"'),
    ('The editor says “A <span>B</span>”.', '"A <span>B</span>"'),
    ('The editor says “Keep\n\n12 records.”', '"Keep 12 records."'),
])
def test_math_primes_urls_attributes_entities_and_block_boundaries_stay_literal(text, query):
    assert locate_quote(query, text, **OPTIONS) is None


def test_inline_code_keeps_literal_curly_and_ascii_bodies_in_mixed_prose():
    text = 'An editor says “Use `“literal code”` and `"other code"` only if ready.”'
    query = '"Use `“literal code”` and `"other code"` only if ready."'
    assert locate_quote(query, text, **OPTIONS) == text[text.index('“Use'):]
    assert locate_quote(query.replace('“literal code”', '"literal code"'), text, **OPTIONS) is None
    assert locate_quote('"literal code"', text, **OPTIONS) is None
    assert locate_quote('“other code”', text, **OPTIONS) is None


@pytest.mark.parametrize('options', [{}, {'markdown_links': True}, {'html_cells': True}, {'markdown_formatting': True}])
def test_both_admitted_format_flags_are_required(options):
    assert locate_quote('"Keep records."', '“Keep records.”', **options) is None


def test_recorded_prefix_protects_fenced_code_and_never_supplies_evidence():
    body = '“Keep records.”\n```'
    assert locate_quote('"Keep records."', body, markdown_prefix='```text\n', **OPTIONS) is None
    prefix = 'An editor says “Keep '
    body = 'records.” today.'
    assert locate_quote('"Keep records."', body, markdown_prefix=prefix, **OPTIONS) is None
    assert locate_quote('"Keep records."', '“Keep records.” today.', markdown_prefix='An editor says ', **OPTIONS) == '“Keep records.”'


def test_earliest_original_match_and_duplicate_spans_remain_deterministic():
    text = '“Keep records.” first.\n\n"Keep records." second.'
    source = PreparedQuoteSource(text, **OPTIONS)
    assert source.locate('"Keep records."') == '“Keep records.”'
    later = text.index('"Keep')
    assert source.locate_spans('"Keep records."') == [(0, 15), (later, later + 15)]


@pytest.mark.parametrize('error', [IndexError, RecursionError])
def test_optional_parser_failure_preserves_literal_matching(monkeypatch, error):
    from markdown_it import MarkdownIt
    def fail(*args, **kwargs):
        raise error('unsupported parsing')
    monkeypatch.setattr(MarkdownIt, 'parse', fail)
    assert locate_quote('"Keep records."', '“Keep records.”', **OPTIONS) is None
    assert locate_quote('“Keep records.”', '“Keep records.”', **OPTIONS) == '“Keep records.”'


@pytest.mark.parametrize('text,quote', [
    ('“' + 'a' * 2047 + '”', '"' + 'a' * 2047 + '"'),
    ('“Keep records.”' + 'a' * 65536, '"Keep records."'),
    ('“Keep records.”' + '😀' * 17000, '"Keep records."'),
    ('“Keep records.”', '\ud800Keep records.\ud801'),
    ('\ud800Keep records.\ud801', '"Keep records."'),
], ids=['long-quote', 'long-source', 'utf8-source', 'invalid-query', 'invalid-source'])
def test_original_input_bounds_and_invalid_utf8_are_preserved(text, quote):
    assert locate_quote(quote, text, **OPTIONS) is None


@pytest.mark.parametrize('media_type,offset,accepted', [
    ('text/html', 0, True), ('application/xhtml+xml', 0, True),
    ('text/html; charset=utf-8', 0, True),
    ('text/plain', 0, False), ('application/pdf', 0, False),
    ('text/html', 1, False), ('text/html', None, False),
])
def test_distillation_requires_html_provenance_and_known_start(media_type, offset, accepted):
    text = 'An editor says “Keep 12 records.” today.'
    job = {'source': SimpleNamespace(item_id='source', provenance={'media_type': media_type}),
           'chunk_id': 'chunk', 'segments': [{'segment_id': 'one', 'text': text, 'start_byte': offset}]}
    value = SourceDistillation.model_validate({'source_id': 'source', 'chunk_id': 'chunk',
        'content_kind': 'substantive', 'summary': 'Record guidance.', 'limitations': [], 'reference_queries': [],
        'findings': [{'question': PLAN['questions'][0], 'claim': 'Keep 12 records.',
                      'segment_id': 'one', 'quote': '"Keep 12 records."'}]})
    if accepted:
        result = validate_distillation(value, job, ResearchPlan.model_validate(PLAN), **OPTIONS)
        assert result.findings[0].quote == '“Keep 12 records.”'
        assert job['validation_changes'][0]['quote_normalized'] is True
    else:
        with pytest.raises(EngineError, match='quotation is absent'):
            validate_distillation(value, job, ResearchPlan.model_validate(PLAN), **OPTIONS)
