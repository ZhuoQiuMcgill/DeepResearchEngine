"""Source structure must survive extraction independently of research topic."""
from __future__ import annotations

import pytest

from deepresearch.engine.toolset.article_extraction import extract_source
from deepresearch.engine.toolset.common import LIMITS, digest
from tests.toolset.test_fetch_v2 import info


def extract(body, *, tag="main", noise=False, base=""):
    navigation = '<nav>' + '<a href="/login">Member login</a> ' * 40 + '</nav>' if noise else ''
    markup = (f'<html><head><title>Reference</title>{base}</head><body>{navigation}'
              f'<{tag}>{body}</{tag}><footer>Copyright</footer></body></html>').encode()
    result = extract_source(markup, info(markup, final_url="https://example.test/manual/page.html"), LIMITS)
    assert result["original"] == markup
    assert result["provenance"]["original_sha256"] == digest(markup)
    assert result["provenance"]["text_sha256"] == digest(result["text"])
    return result["text"].decode()


@pytest.mark.parametrize("tag", ["article", "main", "div"])
@pytest.mark.parametrize("noise", [False, True])
def test_short_link_retains_destination_and_surrounding_condition(tag, noise):
    text = extract('<p>Read the <a href="details.html#method">original methods</a> '
                   'before using this result.</p>', tag=tag, noise=noise)
    assert '[original methods](https://example.test/manual/details.html#method)' in text
    assert 'before using this result.' in text


@pytest.mark.parametrize("tag", ["article", "main", "div"])
def test_short_code_preserves_indentation_and_occurs_once(tag):
    code = 'if ready:\n    begin()\n    if failed:\n        rollback()\nfinish()'
    text = extract('<p>Example:</p><pre><code>' + code + '</code></pre>', tag=tag)
    assert '\n' + code + '\n' in text
    assert text.count('rollback()') == 1


def test_short_table_retains_column_association_and_signs():
    text = extract('<h1>Measurements</h1><table><tr><th>Condition</th><th>Group A</th><th>Group B</th></tr>'
                   '<tr><td>Duration (min)</td><td>12</td><td>24</td></tr>'
                   '<tr><td>Uncertainty</td><td>±2</td><td>±3</td></tr></table>')
    assert '| Condition | Group A | Group B |' in text
    assert '| Duration (min) | 12 | 24 |' in text
    assert '| Uncertainty | ±2 | ±3 |' in text


def test_short_ordered_list_preserves_step_order():
    text = extract('<h1>Order matters</h1><ol><li>Disconnect power.</li><li>Remove cover.</li>'
                   '<li>Replace fuse.</li></ol>')
    assert '1. Disconnect power.\n2. Remove cover.\n3. Replace fuse.' in text


def test_short_scientific_units_preserve_exponents_and_subscripts():
    text = extract('<p>Do not exceed 10<sup>−3</sup> mol L<sup>−1</sup>; keep CO<sub>2</sub> below 1%.</p>')
    assert '10<sup>−3</sup> mol L<sup>−1</sup>' in text
    assert 'CO<sub>2</sub> below 1%' in text


@pytest.mark.parametrize("padding", ["", '<p>' + 'This manual retains its original supporting evidence. ' * 8 + '</p>'])
def test_linked_image_keeps_source_link_and_document_relative_image(padding):
    text = extract(padding + '<p>Results: <a href="data.csv"><img src="figures/plot.png" '
                   'alt="Measured series"></a></p>', base='<base href="../archive/">')
    assert '(https://example.test/archive/data.csv)' in text
    assert '![Measured series](https://example.test/archive/figures/plot.png)' in text


def test_short_plain_text_is_preserved():
    assert 'Closed for maintenance until 18:00 UTC.' in extract('<p>Closed for maintenance until 18:00 UTC.</p>')


def test_structured_candidate_cannot_discard_an_existing_condition(monkeypatch):
    from types import SimpleNamespace
    from lxml import etree
    import trafilatura

    flat = etree.fromstring(b'<body><p>Measured value: 12.</p><p>Not valid below 0 degrees.</p></body>')
    shortened = etree.fromstring(b'<body><head>Measured value: 12.</head></body>')
    outputs = iter([flat, shortened])
    monkeypatch.setattr(trafilatura, 'bare_extraction',
                        lambda *args, **kwargs: SimpleNamespace(body=next(outputs), commentsbody=None))
    text = extract('<p>Measured value: 12.</p><p>Not valid below 0 degrees.</p><a href="details">Details</a>')
    assert 'Measured value: 12.' in text and 'Not valid below 0 degrees.' in text


def test_reused_image_retains_each_declared_destination():
    image = '<img src="icon.png" alt="Data file">'
    text = extract('<p>Separate results: <a href="first.csv">' + image + '</a>'
                   ' and <a href="second.csv">' + image + '</a>.</p>')
    assert '(https://example.test/manual/first.csv)' in text
    assert '(https://example.test/manual/second.csv)' in text


@pytest.mark.parametrize("selection", ['id="content"', 'class="article-content"', 'role="article"'])
def test_one_named_section_cannot_hide_the_rest_of_a_manual(selection):
    sections = []
    for index, name in enumerate(["Preparation", "Measurements", "Authority", "Limitations"]):
        attr = selection if index == 1 else f'id="{name.lower()}"'
        paragraphs = ''.join(f'<p>{name} paragraph {n}: ' +
            'These independently recorded observations apply only under the stated conditions. ' * 3 +
            '</p>' for n in range(40))
        sections.append(f'<div {attr}><section><h2>{name}</h2>{paragraphs}</section></div>')
    body = ''.join(sections) + '<ol><li>Disconnect power.</li><li>Wait for cooling.</li></ol>'
    body += '<pre>if ready:\n    begin()\nelse:\n    stop()</pre>'
    body += '<p>Read <a href="limits.html#conditions">the original conditions</a> before use.</p>'
    text = extract(body, tag="div", noise=True)
    for name in ["Preparation", "Measurements", "Authority", "Limitations"]:
        assert f'## {name}' in text
        for n in range(40):
            assert f'{name} paragraph {n}:' in text
    assert '1. Disconnect power.\n2. Wait for cooling.' in text
    assert 'if ready:\n    begin()\nelse:\n    stop()' in text
    assert '[the original conditions](https://example.test/manual/limits.html#conditions)' in text
    assert 'Member login' not in text


def test_related_cards_outside_article_do_not_trigger_body_expansion():
    prose = ''.join(f'<p>Observation {n}: measured observations apply only under the documented conditions. '
                    + 'Independent evidence. ' * 20 + '</p>' for n in range(20))
    related = ''.join(f'<div><h2>Related article {n}</h2><p>Unrelated recommendation {n}: '
                      + 'Other article description. ' * 20 + '</p></div>' for n in range(12))
    text = extract('<article><h1>Original observations</h1>' + prose + '</article>' + related)
    assert 'measured observations apply only under the documented conditions.' in text
    assert 'Unrelated recommendation' not in text


@pytest.mark.parametrize("omitted", ["qualifier", "link", "code"])
def test_long_recovery_cannot_trade_existing_evidence_for_more_prose(monkeypatch, omitted):
    from types import SimpleNamespace
    from lxml import etree, html
    import trafilatura
    from trafilatura.settings import Extractor
    from deepresearch.engine.toolset.html_recovery import recover_document

    prose = ''.join(f'<p>Independent measurement {i}: ' + 'Recorded observations. ' * 20 + '</p>' for i in range(4))
    retained = {'qualifier': '<p>Only valid above zero degrees.</p>',
                'link': '<p><ref target="https://example.test/conditions">Original conditions</ref></p>',
                'code': '<code>if ready:\n    begin()</code>'}[omitted]
    primary = SimpleNamespace(body=etree.fromstring(('<body>'+retained+'</body>').encode()))
    # Matching visible words alone is insufficient when a URL/indentation was lost.
    flattened = {'qualifier': '', 'link': '<p>Original conditions</p>',
                 'code': '<code>if ready: begin()</code>'}[omitted]
    candidate = SimpleNamespace(body=etree.fromstring(('<body>'+prose+flattened+'</body>').encode()))
    monkeypatch.setattr(trafilatura, 'bare_extraction', lambda *a, **kw: candidate)
    tree = html.document_fromstring('<html><body>'+prose+'</body></html>')
    document, diagnostic = recover_document(tree, primary, Extractor())
    assert document is primary and diagnostic['recovery_attempted']
    assert not diagnostic['recovery_applied'] and diagnostic['substantial_omission']
