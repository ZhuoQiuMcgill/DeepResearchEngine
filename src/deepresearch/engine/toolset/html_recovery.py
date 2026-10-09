"""Conservative recovery when a layout heuristic selects only a document section.

This is a text-coverage diagnostic, not a claim that a page was fully captured
or that every DOM paragraph belongs to the article. Original bytes stay intact.
"""
from __future__ import annotations

from copy import deepcopy


def diagnostic_schema():
    from .discovery_metadata import object_schema
    count = {"type": "integer", "minimum": 0}
    flag = {"type": "boolean"}
    result = object_schema({"method": {"enum": ["dom-prose-overlap/1", "dom-prose-overlap/2"]},
        "semantic_verification": {"const": False}, "eligible_blocks": count, "eligible_characters": count,
        "primary_matched_blocks": count, "primary_matched_characters": count,
        "matched_blocks": count, "matched_characters": count,
        "recovery_attempted": flag, "recovery_applied": flag, "substantial_omission": flag})
    from .html_structure import diagnostic_schema as structure_schema
    result["properties"]["structure"] = structure_schema()
    from .html_graphics import diagnostic_schema as graphics_schema
    result['properties']['graphics'] = graphics_schema()
    result["properties"].update(intermediate_matched_blocks=count,
        intermediate_matched_characters=count,
        prose_render_recovery_attempted=flag, prose_render_recovery_applied=flag,
        verification_stage={"const": "rendered_markdown"})
    return result


def _compact(text):
    return "".join(text.split())


def _visible_body(tree):
    """Drop explicitly non-content/hidden nodes, not topic-bearing ID substrings."""
    from lxml import html

    body = tree.find("body")
    if body is None:
        return None
    # Respect explicit document boundaries. A news article plus recommendations
    # is not one long article; omitted prose outside its article/main landmark
    # must not trigger recovery or be fed back as supposed missing evidence.
    articles = body.xpath('.//article[not(ancestor::article)]')
    mains = body.xpath('.//main[not(ancestor::main)]|.//*[@role="main"]')
    scope = articles[0] if len(articles) == 1 else mains[0] if len(mains) == 1 else body
    selected = deepcopy(scope)
    if selected.tag == "body":
        body = selected
    else:
        body = html.Element("body")
        body.append(selected)
    for node in body.xpath('.//nav|.//aside|.//footer|.//script|.//style|.//template|.//form|'
                           './/*[@hidden or @role="navigation" or @role="banner"]'):
        if node.getparent() is not None:
            node.drop_tree()
    return body


def finalize_diagnostic(tree, text, diagnostic):
    """Measure the delivered Markdown after every recovery/rendering stage.

    The intermediate extractor tree cannot establish what the final renderer
    retained. Parse the actual Markdown with its table and literal-HTML support;
    compare exact paragraph characters, ignoring whitespace as before. This is
    an overlap diagnostic, never a quotation or semantic correctness check.
    No rendered HTML is executed and the parser has no network access.
    """
    from lxml import html
    from markdown_it import MarkdownIt

    body = _visible_body(tree)
    paragraphs = [] if body is None else [_compact(''.join(p.itertext())) for p in body.iter('p')]
    paragraphs = list(dict.fromkeys(p for p in paragraphs if len(p) >= 80))
    rendered = MarkdownIt('commonmark').enable('table').render(text)
    selected = html.fragment_fromstring(rendered, create_parent='div', parser=html.HTMLParser(no_network=True))
    delivered = _compact(''.join(selected.itertext()))
    matched = [p for p in paragraphs if p in delivered]
    total, chars = sum(map(len, paragraphs)), sum(map(len, matched))
    return {**diagnostic, 'method': 'dom-prose-overlap/2', 'verification_stage': 'rendered_markdown',
        'eligible_blocks': len(paragraphs), 'eligible_characters': total,
        'intermediate_matched_blocks': diagnostic.get('intermediate_matched_blocks', diagnostic['matched_blocks']),
        'intermediate_matched_characters': diagnostic.get('intermediate_matched_characters', diagnostic['matched_characters']),
        'matched_blocks': len(matched), 'matched_characters': chars,
        'substantial_omission': (len(paragraphs) - len(matched) >= 2 and total - chars >= 1024
                                 and chars < total * .8)}


def recover_rendered_prose(tree, text, diagnostic):
    """Recover omitted original paragraphs without importing whole-page cards.

    Only an explicit article/main authorizes new prose. Project original DOM
    paragraphs and their headings around already delivered content; check that
    final rendering preserves prior text, links, code and matched paragraphs.
    """
    from lxml import html
    from markdown_it import MarkdownIt
    from .html_selection import select_prose
    from .html_structure import _render, _retains_text

    if not diagnostic['substantial_omission']:
        return text, diagnostic
    diagnostic = {**diagnostic, 'prose_render_recovery_attempted': True,
                  'prose_render_recovery_applied': False}
    body = _visible_body(tree)
    scopes = [] if body is None else body.xpath('./article|./main|./*[@role="main"]')
    if len(scopes) != 1:
        return text, diagnostic
    scope = scopes[0]
    parser = MarkdownIt('commonmark').enable('table')
    def rendered(value):
        return html.fragment_fromstring(parser.render(value), create_parent='div', parser=html.HTMLParser(no_network=True))
    selected = rendered(text)
    delivered = _compact(''.join(selected.itertext()))
    paragraphs = [p for p in scope.iter('p') if len(_compact(''.join(p.itertext()))) >= 80]
    matched = {_compact(''.join(p.itertext())) for p in paragraphs
               if _compact(''.join(p.itertext())) in delivered}
    missing = [p for p in paragraphs if _compact(''.join(p.itertext())) not in matched]
    projected, recovered = select_prose(scope, selected, missing)
    if not recovered or projected is None or not _retains_text(selected, projected):
        return text, diagnostic
    graphics = {}
    candidate = _render(projected, graphics=graphics, source_tree=tree)
    result = rendered(candidate)
    def destinations(node):
        return {n.get(key) for n in node.iter() for key in ('href', 'src') if n.get(key)}
    if (not _retains_text(selected, result)
            or not destinations(selected) <= destinations(result)
            or not {''.join(n.itertext()) for n in selected.iter('code')} <= {''.join(n.itertext()) for n in result.iter('code')}):
        return text, diagnostic
    after = _compact(''.join(result.itertext()))
    final_matches = {_compact(''.join(p.itertext())) for p in paragraphs if _compact(''.join(p.itertext())) in after}
    if not matched < final_matches:
        return text, diagnostic
    diagnostic.update(prose_render_recovery_applied=True, recovery_attempted=True, recovery_applied=True)
    # This candidate supersedes the previous renderer's selection provenance.
    diagnostic.pop('graphics', None)
    if graphics:
        diagnostic['graphics'] = graphics
    return candidate, diagnostic


def recover_document(tree, document, options):
    """Try a layout-neutral body only after substantial prose was omitted.

    ID/class words such as ``content`` and ``authority`` are merely presentation
    hints. A second pass neutralizes them in a copy, preserves explicit HTML
    structure, and is eligible only if it retains the primary result's blocks,
    links, images and code. Small peripheral omissions do not expand an article
    into the whole page. Counts are deliberately labelled heuristic evidence.
    """
    from lxml import html
    from trafilatura import bare_extraction

    body = _visible_body(tree)
    paragraphs = [] if body is None else [
        _compact("".join(node.itertext())) for node in body.iter("p")]
    paragraphs = list(dict.fromkeys(p for p in paragraphs if len(p) >= 80))
    primary_text = _compact("".join(document.body.itertext()))

    def coverage(text):
        matched = [p for p in paragraphs if p in text]
        return len(matched), sum(map(len, matched))

    before_count, before_chars = coverage(primary_text)
    total = sum(map(len, paragraphs))
    substantial = (len(paragraphs) - before_count >= 2 and total - before_chars >= 1024
                   and before_chars < total * .8)
    diagnostic = {"method": "dom-prose-overlap/1", "semantic_verification": False,
        "eligible_blocks": len(paragraphs), "eligible_characters": total,
        "primary_matched_blocks": before_count, "primary_matched_characters": before_chars,
        "matched_blocks": before_count, "matched_characters": before_chars,
        "recovery_attempted": substantial, "recovery_applied": False,
        "substantial_omission": substantial}
    if not substantial:
        return document, diagnostic

    wrapper = html.Element("main", itemprop="articleBody")
    wrapper.text, body.text = body.text, None
    for node in list(body):
        wrapper.append(node)
    for node in wrapper.iterdescendants():
        node.attrib.pop("id", None)
        node.attrib.pop("class", None)
        node.attrib.pop("itemprop", None)
    body.append(wrapper)
    root = html.Element("html")
    root.append(body)
    candidate = bare_extraction(html.tostring(root, encoding="unicode"), options=options)
    if candidate is None:
        return document, diagnostic
    text = _compact("".join(candidate.body.itertext()))
    count, chars = coverage(text)
    # Never trade an existing condition/qualifier or source destination for a
    # longer document. In particular a flat short-text rescue is not proof that
    # its first structured candidate contains all the original evidence.
    blocks = [_compact("".join(n.itertext())) for n in document.body]
    links = {(n.tag, n.get("target") or n.get("src")) for n in document.body.iter()
             if n.tag in {"ref", "graphic"}}
    candidate_links = {(n.tag, n.get("target") or n.get("src")) for n in candidate.body.iter()
                       if n.tag in {"ref", "graphic"}}
    codes = ["".join(n.itertext()) for n in document.body.iter("code")]
    candidate_codes = ["".join(n.itertext()) for n in candidate.body.iter("code")]
    if (chars > before_chars and all(block in text for block in blocks)
            and links <= candidate_links and all(code in candidate_codes for code in codes)):
        document = candidate
        diagnostic.update(matched_blocks=count, matched_characters=chars, recovery_applied=True,
            substantial_omission=(len(paragraphs) - count >= 2 and total - chars >= 1024 and chars < total * .8))
    return document, diagnostic
