"""Locate an exact saved substring, permitting whitespace and PDF soft wraps."""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right

from .html_quotations import cell_whitespace_projection, inline_cell_projections, table_projections
from .markdown_quotations import markdown_projections, mixed_markdown_query

_LATIN_LETTERS = "A-Za-zﬀﬁﬂﬃﬄﬅﬆ"
_SOFT_WORD = re.compile(r"(?<!\w)[" + _LATIN_LETTERS + r"]+(?:-[ \t]*\r?\n[ \t]*[" + _LATIN_LETTERS + r"]+)+(?!\w)")
_SOFT_SEPARATOR = re.compile(r"-[ \t]*\r?\n[ \t]*")


def _normalized(value, join_words):
    omitted = bytearray(len(value))
    if join_words:
        for word in _SOFT_WORD.finditer(value):
            for separator in _SOFT_SEPARATOR.finditer(value, word.start(), word.end()):
                omitted[separator.start():separator.end()] = b"\1" * (separator.end() - separator.start())
    output, spans = [], []
    for index, character in enumerate(value):
        if omitted[index]:
            continue
        if character.isspace():
            if output and output[-1] == " ":
                spans[-1] = (spans[-1][0], index + 1)
                continue
            character = " "
        output.append(character)
        spans.append((index, index + 1))
    return "".join(output), spans


def _visible_links(text):
    """Conservative inline HTTP link projection with original character offsets.

    Unsupported Markdown stays literal. No case, punctuation or factual text is
    changed; every visible character maps to an actual original character.
    """
    output, positions, cursor = [], [], 0
    for match in re.finditer(r"(?<!!)\[([^\[\]\n]{1,1024})\]\((https?://[^\s()]{1,4096})\)", text):
        indices = [*range(cursor, match.start()), *range(match.start(1), match.end(1))]
        output.extend(text[index] for index in indices)
        positions.extend(indices)
        cursor = match.end()
    output.extend(text[cursor:])
    positions.extend(range(cursor, len(text)))
    return "".join(output), positions


def locate_quote(quote: str, text: str, *, markdown_links=False, html_cells=False,
                 markdown_formatting=False, markdown_prefix="") -> str | None:
    """Return an original contiguous saved substring, or None.

    Case, letters, numbers and order remain exact. Whitespace may
    differ. Latin alphabetic fragments (ASCII and seven presentation ligatures)
    separated by hyphen + LF/CRLF (optional
    horizontal whitespace) may join on BOTH query and source sides. Inline
    hyphens and number/identifier wraps are preserved; no fuzzy or global Unicode
    compatibility matching occurs. The whitespace-only comparison remains
    available for quotations explicitly retaining a wrapped hyphen.

    Optional HTML cell comparison ignores only ASCII whitespace at td/th content
    edges outside code and an optional </p> immediately before a known enclosing
    block end, retaining relationship tags/attributes and original character maps.
    The caller must explicitly admit an HTML-derived source. It never flattens
    tables, decodes entities or changes row/column relationships.
    Balanced inline presentation, code markup and supported link markup can be
    omitted within a complete explicit HTML prose block or cell. Highlighted
    preformatted code retains its literal body. Table-wide views retain every
    relationship tag; no text joins across block/cell boundaries. Unsupported
    attributes, entities, malformed markup and literal Markdown code stay literal.

    Optional CommonMark comparison omits parsed emphasis, exact inline-code
    delimiters and inline HTTP(S) link syntax, or flat unordered-list bullets.
    Table delimiter lines and cell formatting may be omitted while retaining
    rows/pipes. Code bodies, code blocks, ordered/nested lists and blockquotes
    remain literal. Bounded format policies permit retained inline formatting. Callers establish document-start context with an
    optional recorded prefix. Only matches inside the current read can return.
    In admitted HTML context, a single prose paragraph can additionally compare
    mixed retained/omitted code delimiters using one query policy and at most
    four shared source policies. Escapes retain their original bytes; quoted
    link destinations/titles remain exact. Newly matched code bodies must be
    complete, and existing matches retain priority.

    When both HTML and Markdown formatting are admitted, balanced prose double
    quotation delimiters may differ between curly and straight forms. Only
    exactly mapped top-level Markdown paragraphs qualify; code, URLs, raw HTML
    attributes and mathematical/primes remain literal. No other punctuation
    changes. Both paired endpoints must be present in the query.

    The same provenance/context gates independently admit U+2011 versus ASCII
    hyphens in exactly mapped prose paragraphs and flat unordered-list paragraphs.
    Only complete lowercase lexical compounds or small integer-to-word compounds
    qualify; protected syntax and numeric ranges remain literal. No global folding.

    Preserve existing matches before considering the new hyphen comparison.
    Within each group, select the earliest original match, breaking a
    same-start tie by the shorter span. Ambiguity does not imply uniqueness.
    Quote and returned span are bounded to 2048 characters; text to 65536 UTF-8
    bytes. Invalid/empty/oversized input returns None. The index map is used
    only to slice original text: callers compute offsets/digests from that
    original substring, never from normalized comparison text.
    """
    return PreparedQuoteSource(text, markdown_links=markdown_links, html_cells=html_cells,
        markdown_formatting=markdown_formatting, markdown_prefix=markdown_prefix).locate(quote)


class PreparedQuoteSource:
    """Reuse source parsing within one validation call, never model conclusions.

    Each instance owns one immutable read and its admitted document context.
    Position maps use packed unsigned offsets; only the current read's characters
    survive preparation, even when parsing needs a much larger recorded prefix.
    Preparation is lazy so invalid input does not invoke a parser.
    """

    def __init__(self, text, *, markdown_links=False, html_cells=False,
                 markdown_formatting=False, markdown_prefix="", pdf_margins=(), pdf_page_breaks=()):
        self._text = text
        self._options = markdown_links, html_cells, markdown_formatting, markdown_prefix
        self._prepared = None
        self._pdf_margins, self._pdf_breaks = pdf_margins, pdf_page_breaks
        previous = -1
        for start, end in pdf_margins:
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or start < previous:
                self._pdf_margins = ()
                break
            previous = end
        self._valid = type(text) is str and len(text) <= 65536
        if self._valid:
            try:
                self._valid = len(text.encode("utf-8", errors="strict")) <= 65536
                if markdown_formatting or html_cells:
                    self._valid = (self._valid and type(markdown_prefix) is str
                        and len(markdown_prefix.encode("utf-8", errors="strict")) <= 2097152)
            except UnicodeError:
                self._valid = False

    def _prepare(self):
        from array import array

        markdown_links, html_cells, markdown_formatting, prefix = self._options
        projections = [(self._text, None, "literal")]
        if markdown_links:
            visible, positions = _visible_links(self._text)
            projections.append((visible, positions, "literal"))
        # A formatting view is not a new document. In particular, removing a
        # Markdown code delimiter must not turn literal HTML code into a table.
        html_sources = list(projections)
        self._mixed_bodies = []
        if markdown_formatting:
            for projected, positions, _ in list(projections):
                mixed_views = []
                # New query-side formatting requires admitted HTML context and
                # original Markdown. A prior formatting view is not reparsed.
                original_context = html_cells and positions is None
                views = (markdown_projections(prefix + projected, mixed_views=mixed_views)
                         if original_context else markdown_projections(prefix + projected))
                for visible, mapped in views:
                    kept = [(c, i - len(prefix)) for c, i in zip(visible, mapped) if i >= len(prefix)]
                    if kept:
                        indices = [positions[i] if positions is not None else i for _, i in kept]
                        projections.append(("".join(c for c, _ in kept), indices, "literal"))
                for visible, mapped, bodies in mixed_views:
                    kept = [(c, i - len(prefix)) for c, i in zip(visible, mapped) if i >= len(prefix)]
                    if kept:
                        projections.append((''.join(c for c, _ in kept), [i for _, i in kept], 'markdown_mixed'))
                        self._mixed_bodies.extend((a - len(prefix), b - len(prefix))
                            for a, b in bodies if b > len(prefix))
            self._mixed_bodies = sorted(set(self._mixed_bodies))
        if html_cells:
            for projected, positions, _ in html_sources:
                if '<' not in projected:
                    # No in-read HTML edge can change. Avoid reparsing a long
                    # recorded prefix for each plain Markdown format variant.
                    continue
                for factory, cell_query in ((table_projections, "html_cell"), (inline_cell_projections, "literal")):
                    for visible, cells in factory(prefix + projected):
                        kept = [(c, i - len(prefix)) for c, i in zip(visible, cells) if i >= len(prefix)]
                        if kept:
                            mapped = [positions[i] if positions is not None else i for _, i in kept]
                            projections.append(("".join(c for c, _ in kept), mapped, cell_query))
            from .html_inline_quotations import inline_html_projections
            for visible, cells, mode in inline_html_projections(prefix + self._text):
                kept = [(c, i - len(prefix)) for c, i in zip(visible, cells) if i >= len(prefix)]
                if kept:
                    projections.append((''.join(c for c, _ in kept), [i for _, i in kept], mode))
        if self._pdf_margins and self._pdf_breaks:
            from .pdf_quotations import margin_projection
            visible, positions = margin_projection(self._text, self._pdf_margins)
            projections.append((visible, positions, "pdf_body"))
        if html_cells and markdown_formatting:
            from .prose_hyphens import prose_hyphens
            from .prose_quotations import delimiter_projection
            compounds = {}
            hyphens = {i - len(prefix): c for i, c in prose_hyphens(prefix + self._text, compounds=compounds).items()
                       if i >= len(prefix)}
            self._hyphen_words = sorted((i - len(prefix), a - len(prefix), b - len(prefix))
                for i, (a, b) in compounds.items() if i >= len(prefix))
            if hyphens:
                for projected, positions, mode in list(projections):
                    if mode == 'pdf_body':
                        continue
                    visible = delimiter_projection(projected, hyphens, positions)
                    if visible != projected:
                        projections.append((visible, positions, ('prose_hyphens', mode)))
        if html_cells and markdown_formatting:
            from .prose_quotations import delimiter_projection, prose_delimiters
            delimiters = {i - len(prefix): c for i, c in prose_delimiters(prefix + self._text).items()
                          if i >= len(prefix)}
            if delimiters:
                for projected, positions, mode in list(projections):
                    if mode == 'pdf_body':
                        continue
                    visible = delimiter_projection(projected, delimiters, positions)
                    if visible != projected:
                        projections.append((visible, positions, ('prose_quotes', mode)))
        prepared = []
        for projected, positions, cell_query in projections:
            for join_words in (False, True):
                haystack, spans = _normalized(projected, join_words)
                starts = array("I", (positions[a] if positions is not None else a for a, _ in spans))
                ends = array("I", (positions[b - 1] + 1 if positions is not None else b for _, b in spans))
                prepared.append((haystack, starts, ends, join_words, cell_query))
        self._prepared = prepared

    def locate(self, quote):
        matches = self._matches(quote, all_matches=False)
        if not matches:
            return None
        start, end = min(matches)
        return self._text[start:end] if end - start <= 2048 else None

    def locate_spans(self, quote):
        """Enumerate bounded original spans for cross-read ambiguity checks."""
        return sorted({(a, b) for a, b in self._matches(quote, all_matches=True) if b - a <= 2048})

    def _matches(self, quote, *, all_matches):
        if not self._valid or type(quote) is not str or not quote or len(quote) > 2048:
            return []
        try:
            quote.encode("utf-8", errors="strict")
        except UnicodeError:
            return []
        if self._prepared is None:
            self._prepare()
        queries, matches, hyphen_matches, mixed_matches, hyphen_modes = {}, [], [], [], set()
        for haystack, starts, ends, join_words, cell_query in self._prepared:
            key = join_words, cell_query
            query_mode, policies = cell_query, set()
            while isinstance(query_mode, tuple):
                policy, query_mode = query_mode
                policies.add(policy)
            if key not in queries:
                projected_quote = quote
                if policies:
                    from .prose_quotations import delimiter_projection, prose_delimiters
                    markers = {}
                    if 'prose_quotes' in policies:
                        delimiters = prose_delimiters(quote)
                        if not delimiters:
                            queries[key] = set()
                            continue
                        markers.update(delimiters)
                    if 'prose_hyphens' in policies:
                        hyphen_modes.add(key)
                        from .prose_hyphens import prose_hyphens
                        hyphens = prose_hyphens(quote)
                        if not hyphens:
                            queries[key] = set()
                            continue
                        markers.update(hyphens)
                    projected_quote = delimiter_projection(quote, markers)
                if query_mode == 'html_cell':
                    projected_quote = cell_whitespace_projection(projected_quote)[0]
                variants = [projected_quote]
                if query_mode == 'markdown_mixed':
                    mixed = mixed_markdown_query(projected_quote)
                    variants = [] if mixed is None else [mixed]
                if query_mode == 'html_prose' and self._options[2]:
                    # Query formatting may differ only for a single prose block;
                    # literal preformatted code never uses this adaptation.
                    from markdown_it import MarkdownIt
                    try:
                        tokens = MarkdownIt('commonmark').parse(projected_quote)
                    except (IndexError, RecursionError):
                        tokens = []
                    if [t.type for t in tokens] == ['paragraph_open', 'inline', 'paragraph_close']:
                        variants.extend(v for v, _ in markdown_projections(projected_quote))
                queries[key] = {_normalized(v, join_words)[0].strip() for v in variants}
            for needle in queries[key]:
                if not needle:
                    continue
                found = haystack.find(needle)
                while found >= 0:
                    start, end = starts[found], ends[found + len(needle) - 1]
                    allowed = cell_query != "pdf_body" or any(start < point < end for point in self._pdf_breaks)
                    if query_mode == 'markdown_mixed':
                        # A newly stripped code delimiter cannot authorize a
                        # partial literal body, number or identifier match.
                        bodies = self._mixed_bodies
                        left = bisect_right(bodies, (start, len(self._text) + 1)) - 1
                        right = bisect_left(bodies, (end,)) - 1
                        allowed = (allowed
                            and not (left >= 0 and bodies[left][0] < start < bodies[left][1])
                            and not (right >= 0 and bodies[right][0] < end < bodies[right][1])
                            and not (start and re.match(r'\w\w', self._text[start - 1:start + 1]))
                            and not (end < len(self._text) and re.match(r'\w\w', self._text[end - 1:end + 1])))
                    if allowed and key in hyphen_modes:
                        words = self._hyphen_words
                        left, right = bisect_left(words, (start,)), bisect_left(words, (end,))
                        allowed = all(start <= a and b <= end for _, a, b in words[left:right])
                    if allowed:
                        (mixed_matches if query_mode == 'markdown_mixed' else
                         hyphen_matches if key in hyphen_modes else matches).append((start, end))
                    if not all_matches and allowed:
                        break
                    found = haystack.find(needle, found + 1)
        return matches + hyphen_matches + mixed_matches if all_matches else (matches or hyphen_matches or mixed_matches)
