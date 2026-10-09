"""Recover source structure without using link-density cleanup as a renderer.

Selection stays bounded to the visible article/main (or a well-covered body).
Loss detection compares source blocks with the selected extraction tree. A
candidate must retain the previous evidence before it can replace that tree.
"""
from __future__ import annotations

from copy import deepcopy
from html import unescape
import re

from .html_recovery import _compact, _visible_body

KINDS = {"ol", "ul", "dl", "table", "pre"}
TEXT_BLOCKS = {"body", "div", "section", "article", "main", "p", "head", "h1", "h2", "h3", "h4", "h5", "h6",
               "item", "li", "dd", "dt", "cell", "td", "th", "code", "pre", "list", "ol", "ul", "dl", "table", "tr", "row"}


def _text_units(node):
    """Do not concatenate separate list items or paragraphs into a false phrase."""
    parts = []
    def walk(current):
        if current.tag in TEXT_BLOCKS and parts:
            yield ''.join(parts)
            parts.clear()
        if isinstance(current.tag, str) and current.text:
            parts.append(current.text)
        for child in current:
            yield from walk(child)
            if child.tail:
                parts.append(child.tail)
        if current.tag in TEXT_BLOCKS and parts:
            yield ''.join(parts)
            parts.clear()
    yield from walk(node)
    if parts:
        yield ''.join(parts)


def _retains_text(document, scope):
    """Allow original insertions inside a block, never lost/replaced old tokens.

    The initial extractor can delete a date and join its surrounding commas.
    Requiring that damaged sentence as a contiguous substring would forbid
    restoring the date. Compare exact, ordered words/numbers/punctuation within
    source blocks; do not normalize case, values or negation, or combine unrelated
    paragraphs to manufacture a match. This is a preservation guard, not a quote
    matcher: quotation validation still uses exact archived substrings.
    """
    original = _text(scope)
    source = [*_text_units(scope), *(''.join(n.itertext()) for n in scope.iter()
        if n.tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dt", "dd", "td", "th", "pre"})]
    index = {}
    for text in source:
        tokens = tuple(re.findall(r'\w+|[^\w\s]', text))
        for token in set(tokens):
            index.setdefault(token, []).append(tokens)
    slots = None
    for text in _text_units(document):
        if _compact(text) in original:
            continue
        tokens = tuple(re.findall(r'\w+|[^\w\s]', text))
        if not tokens:
            continue
        def contains(candidate):
            remaining = iter(candidate)
            return all(token in remaining for token in tokens)
        if not any(len(value) >= len(tokens) and contains(value) for value in index.get(tokens[0], ())):
            # Flattened fields can merge tokens (e.g. a price and a frequency).
            # Explain that only with whole original DOM slots in one block.
            if slots is None:
                from .html_alignment import DOMSlotMatcher
                slots = DOMSlotMatcher(scope)
            if not slots.retains(text):
                return False
    return True


def _bounded_scope(scope, document, selected):
    """Locate the common source container of already selected prose first."""
    matched = [n for n in scope.iter('p') if len(_text(n)) >= 80 and _text(n) in selected]
    if not matched:
        return scope
    ancestor_sets = [set(n.iterancestors()) for n in matched[1:]]
    candidate = matched[0].getparent()
    while candidate is not None and candidate is not scope:
        if all(candidate in parents for parents in ancestor_sets) and _retains_text(document, candidate):
            return candidate
        candidate = candidate.getparent()
    return scope


def diagnostic_schema():
    from .discovery_metadata import object_schema
    count = {"type": "integer", "minimum": 0}
    result = object_schema({"method": {"const": "dom-structure-check/1"},
        "semantic_verification": {"const": False}, "checked_blocks": count,
        "damaged_blocks": count, "recovery_applied": {"type": "boolean"},
        "unresolved": {"type": "boolean"}, "decision": {"enum": [
            "no_damage_detected", "primary_content_outside_scope", "ambiguous_body_scope",
            "candidate_loses_destinations", "candidate_loses_code", "recovered", "partially_recovered"]}})
    result["properties"].update(recovered_blocks=count, unresolved_blocks=count)
    return result


def _text(node):
    return _compact("".join(node.itertext()))


def _table_needs_html(rows):
    """Markdown requires a full header row followed by rectangular data rows.

    Inventing headers or padding cells changes the source relationships. Keep
    headerless, mixed-header, row-header and ragged tables as original HTML.
    """
    return (not rows or not rows[0] or any(tag != 'th' for tag in rows[0])
            or any(len(row) != len(rows[0]) or any(tag != 'td' for tag in row)
                   for row in rows[1:]))


def _damaged(node, document, selected_text):
    content = _text(node)
    if content not in selected_text:
        return True
    if node.tag == "pre":
        return "".join(node.itertext()) not in ["".join(n.itertext()) for n in document.iter("code")]
    if node.tag == "table":
        if node.xpath('.//svg'):
            # Text equality cannot detect a graphical value that became empty.
            # Recover only after the same selection/preservation checks below.
            return True
        # An intact intermediate table can still render as plain pipe text or
        # mislabel row headers. Check representability before text equality.
        if _table_needs_html([[c.tag for c in row if c.tag in {'td', 'th'}]
                              for row in node.iter('tr')]):
            return True
        # Markdown's rectangular cells cannot express spans or nested tables.
        if node.xpath('.//*[@rowspan or @colspan]|.//table'):
            return True
        expected = [[_text(c) for c in row if c.tag in {"td", "th"}] for row in node.iter("tr")]
        return not any(expected == [[_text(c) for c in row] for row in t.iter("row")]
                       for t in document.iter("table"))
    if node.tag == "dl":
        return True  # Preserve explicit term/definition associations as HTML.
    if node.xpath('.//*[@value]|.//ol[@start or @reversed or @type]') or any(
            name in node.attrib for name in ("start", "reversed", "type")):
        return True
    expected = [(n.tag, len(n.xpath('./li'))) for n in node.iter() if n.tag in {"ol", "ul"}]
    return not any(_text(n) == content and expected == [
        (child.get("rend"), len(child.findall("item"))) for child in n.iter("list")]
        for n in document.iter("list"))


def _render(scope, code_blocks=None, graphics=None, *, source_tree=None):
    from lxml import html
    from bs4 import Comment
    from markdownify import MarkdownConverter
    from .html_graphics import project_selected_graphics, TABLE_MARKER
    scope, graphic_diagnostic = project_selected_graphics(scope, source_tree=source_tree)
    if graphics is not None and graphic_diagnostic is not None:
        graphics.update(graphic_diagnostic)
    emitted_codes = [] if code_blocks is None else code_blocks

    class SourceConverter(MarkdownConverter):
        def literal(self, el):
            # Keep relationships Markdown cannot encode. Never emit executable
            # attributes/elements when this Markdown is rendered by a client.
            copied = deepcopy(el)
            for comment in copied.find_all(string=lambda value: isinstance(value, Comment)):
                comment.extract()
            tags = {"table", "caption", "thead", "tbody", "tfoot", "tr", "td", "th",
                    "colgroup", "col", "ol", "ul", "li", "dl", "dt", "dd", "p", "div",
                    "span", "a", "img", "br", "pre", "code", "sub", "sup", "em", "strong", "b", "i"}
            attrs = {"rowspan", "colspan", "scope", "headers", "id", "start", "reversed", "value",
                     "type", "href", "src", "alt", "title"}
            for tag in [copied, *copied.find_all(True)]:
                if tag.name not in tags:
                    tag.unwrap()
                    continue
                tag.attrs = {k: v for k, v in tag.attrs.items() if k in attrs}
                for key in ("href", "src"):
                    schemes = ("https://", "http://", "mailto:", "tel:") if key == "href" else ("https://", "http://")
                    if key in tag.attrs and not str(tag[key]).lower().startswith(schemes):
                        del tag[key]
            emitted_codes.extend(tag.get_text() for tag in [copied, *copied.find_all(['pre', 'code'])]
                                 if tag.name in {'pre', 'code'})
            return '\n\n' + str(copied) + '\n\n'

        def convert_table(self, el, text, parent_tags):
            rows = [[c.name for c in row.find_all(['td', 'th'], recursive=False)]
                    for row in el.find_all('tr')]
            if (TABLE_MARKER in el.attrs or _table_needs_html(rows) or el.find(attrs={"rowspan": True})
                    or el.find(attrs={"colspan": True}) or el.find(['table', 'pre'])):
                return self.literal(el)
            return super().convert_table(el, text, parent_tags)

        def convert_ul(self, el, text, parent_tags):
            if any(child.name != 'li' for child in el.find_all(recursive=False)):
                return self.literal(el)
            return super().convert_ul(el, text, parent_tags)

        def convert_ol(self, el, text, parent_tags):
            # Some pages use div records inside a list. Flattening their nested
            # lists loses the record boundary; retain the original HTML shape.
            if any(child.name != 'li' for child in el.find_all(recursive=False)):
                return self.literal(el)
            if any(a in el.attrs for a in ("reversed", "type")) or el.find('li', attrs={"value": True}) or (
                    'start' in el.attrs and not str(el['start']).isdigit()):
                return self.literal(el)
            return super().convert_ol(el, text, parent_tags)

        def convert_dl(self, el, text, parent_tags):
            return self.literal(el)

        def convert_code(self, el, text, parent_tags):
            if el.find(['table', 'pre']):
                return self.literal(el)
            if el.find('a', href=True):
                # A Markdown code span cannot carry the source hyperlink. Keep
                # both inline, rather than making the preservation guard reject
                # unrelated table recovery elsewhere in this document.
                return self.literal(el).strip('\n')
            result = super().convert_code(el, text, parent_tags)
            if result:
                # Inline HTML code can start on a new source line; Markdown
                # code spans normalize that formatting whitespace. Track the
                # rendered element's original text separately from block code.
                emitted_codes.append(el.get_text())
            return result

        def convert_pre(self, el, text, parent_tags):
            # Syntax highlighting can contain divs. Their Markdown conversion
            # adds blank lines that were never part of the original program.
            text = el.get_text()
            emitted_codes.append(text)
            if el.find('a', href=True):
                # Fenced Markdown cannot retain hyperlinks within code without
                # changing the code text. HTML pre preserves both relationships.
                return self.literal(el)
            fence = '`' * max(3, 1 + max((len(s) for s in re.findall(r'`+', text)), default=0))
            return '\n\n' + fence + '\n' + text + '\n' + fence + '\n\n'

    return SourceConverter(heading_style="ATX", bullets="-", sub_symbol="<sub>", sup_symbol="<sup>",
        strip_pre=None, autolinks=False, keep_inline_images_in=["td", "th", "h1", "h2", "h3", "h4", "h5", "h6"],
        bs4_options="lxml").convert(html.tostring(scope, encoding="unicode"))


def recover_structure(tree, document, primary):
    scope = _visible_body(tree)
    selected = _text(document.body)
    if scope is not None:
        scope = _bounded_scope(scope, document.body, selected)
    blocks = [] if scope is None else [n for n in scope.iter()
        if n.tag in KINDS and not any(p.tag in KINDS for p in n.iterancestors()) and _text(n)]
    damaged = [n for n in blocks if _damaged(n, document.body, selected)]
    diagnostic = {"method": "dom-structure-check/1", "semantic_verification": False,
        "checked_blocks": len(blocks), "damaged_blocks": len(damaged), "recovery_applied": False,
        "unresolved": bool(damaged), "decision": "no_damage_detected"}
    if not damaged:
        return primary, diagnostic
    scope_text = _text(scope)
    if not _retains_text(document.body, scope):
        diagnostic["decision"] = "primary_content_outside_scope"
        return primary, diagnostic
    # Unmarked whole-page scope needs strong independent paragraph coverage.
    # Do not turn omitted related cards into source evidence to rescue a list.
    semantic_scope = any(n.tag in {'article', 'main'} or n.get('role') == 'main'
                         for n in [scope, *scope.iterancestors()])
    recovered = len(damaged)
    if not semantic_scope and len(selected) < .8 * len(scope_text):
        from .html_selection import select_anchored_structure
        projected, recovered = select_anchored_structure(scope, document.body, damaged)
        if projected is None or not _retains_text(document.body, projected):
            diagnostic["decision"] = "ambiguous_body_scope"
            return primary, diagnostic
        scope = projected
    emitted_codes = []
    graphics = {}
    candidate = _render(scope, emitted_codes, graphics, source_tree=tree)
    decoded = unescape(candidate)
    if any((n.get("target") or n.get("src") or "") not in decoded
           for n in document.body.iter() if n.tag in {"ref", "graphic"}
           and (n.get("target") or n.get("src") or "") in unescape(primary)):
        diagnostic["decision"] = "candidate_loses_destinations"
        return primary, diagnostic
    if any("".join(n.itertext()) not in decoded and "".join(n.itertext()) not in emitted_codes
           for n in document.body.iter("code")):
        diagnostic["decision"] = "candidate_loses_code"
        return primary, diagnostic
    unresolved = len(damaged) - recovered
    diagnostic.update(recovery_applied=True, unresolved=bool(unresolved),
                      recovered_blocks=recovered, unresolved_blocks=unresolved,
                      decision="partially_recovered" if unresolved else "recovered")
    if graphics:
        diagnostic['graphics'] = graphics
    return candidate, diagnostic
