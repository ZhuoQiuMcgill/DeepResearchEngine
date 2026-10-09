"""Compare limited cell formatting without flattening HTML relationships."""
from __future__ import annotations

from html.parser import HTMLParser
from bisect import bisect_left
import re

_SPACE = " \t\r\n\f"
_OPTIONAL_P_END = re.compile(r"</p>(?=</(?:div|td|th|li|dd)>)")
_STRUCTURAL = {"table", "thead", "tbody", "tfoot", "tr", "td", "th"}
_CHILDREN = {"table": {"thead", "tbody", "tfoot", "tr", "caption", "colgroup"},
             "thead": {"tr"}, "tbody": {"tr"}, "tfoot": {"tr"},
             "tr": {"td", "th"}, "colgroup": {"col"}}
_PARENTS = {"thead": {"table"}, "tbody": {"table"}, "tfoot": {"table"},
            "tr": {"table", "thead", "tbody", "tfoot"}, "td": {"tr"}, "th": {"tr"}}
_LITERAL = {"pre", "code", "script", "style", "textarea", "math", "svg", "noscript", "template"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def _without_markdown_code(value):
    """Mask code for parsing only; never use the masked text as evidence.

    Conservatively protect unmatched backticks/fences through the end of a
    bounded segment. Source tables beginning in indented code are checked below.
    """
    protected = bytearray(len(value))
    cursor = 0
    for match in re.finditer(r"`+|~{3,}", value):
        if match.start() < cursor:
            continue
        marker = match.group()
        closer = re.search(re.escape(marker[0]) + "{" + str(len(marker)) + r",}", value[match.end():])
        cursor = match.end() + closer.end() if closer else len(value)
        protected[match.start():cursor] = b"\1" * (cursor - match.start())
    return "".join(" " if protected[i] and c not in "\r\n" else c for i, c in enumerate(value))


def _cell_projection(value, *, fragment=False):
    """Project cell edges, optional paragraph ends and structural table gaps.

    Source tables must be complete, explicitly nested and code-free. Query
    fragments can infer missing ancestors, but never repair malformed nesting.
    Only ASCII gaps between consecutive structural events outside cell contents
    may disappear. Tags, attributes, entities and original indexes stay literal.
    """
    starts = [0, *(m.end() for m in re.finditer("\n", value))]
    omitted = bytearray(len(value))
    masked = _without_markdown_code(value)
    # A table on a continuation line of an indented Markdown block is still
    # literal code, even when its own line has fewer than four leading spaces.
    from markdown_it import MarkdownIt
    try:
        tokens = MarkdownIt("commonmark").parse(value)
    except (IndexError, RecursionError):
        return value, list(range(len(value))), []
    protected = bytearray(len(value))
    for token in tokens:
        if token.type in {"fence", "code_block"} and token.map is not None:
            left, right = token.map
            a = starts[left]
            b = starts[right] if right < len(starts) else len(value)
            protected[a:b] = b"\1" * (b - a)
    masked = "".join(" " if protected[i] and c not in "\r\n" else c for i, c in enumerate(masked))
    tables = []

    class LimitReached(Exception):
        pass

    class Cells(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.stack = []
            self.table_start = None
            self.table_depth = 0
            self.safe = True
            self.query_safe = True
            self.pending = []
            self.previous = None
            self.events = 0

        def position(self):
            line, column = self.getpos()
            return starts[line - 1] + column

        def reject(self):
            self.safe = False
            self.query_safe = False

        def infer(self, tag, closing=False):
            if not fragment or self.stack or tag not in _STRUCTURAL:
                return
            parents = {"table": [], "thead": ["table"], "tbody": ["table"],
                       "tfoot": ["table"], "tr": ["table"],
                       "td": ["table", "tr"], "th": ["table", "tr"]}[tag]
            self.stack.extend((parent, False) for parent in parents)
            if closing:
                self.stack.append((tag, False))

        def event(self, tag, start, end, *, structural_gap=False):
            self.events += 1
            if self.events > 32768 or len(self.stack) >= 128:
                raise LimitReached
            if (fragment or self.table_start is not None) and structural_gap and self.previous:
                previous_tag, previous_end = self.previous
                gap = value[previous_end:start]
                if (previous_tag in _STRUCTURAL and tag in _STRUCTURAL
                        and gap and all(c in _SPACE for c in gap)):
                    self.pending.append((previous_end, start))
            self.previous = (tag, end)

        def boundary(self, forward):
            position = self.position()
            if forward:
                position += len(self.get_starttag_text())
            else:
                position -= 1
            edge = position
            while 0 <= position < len(value) and value[position] in _SPACE:
                position += 1 if forward else -1
            if position != edge:
                self.pending.append((edge, position) if forward else (position + 1, edge + 1))

        def handle_starttag(self, tag, attrs):
            start = self.position()
            self.infer(tag)
            parent = self.stack[-1][0] if self.stack else None
            blocked = tag in _LITERAL or any(a in {"hidden", "style", "aria-hidden"} for a, _ in attrs)
            if tag == "table" and self.table_start is None:
                self.table_start = start
                self.table_depth = len(self.stack) + 1
                if not fragment:
                    self.pending = []
                self.safe = not any(unsafe or t in _STRUCTURAL for t, unsafe in self.stack)
                # Escaped raw HTML in Markdown is a literal example.
                backslashes = 0
                while start > backslashes and value[start - backslashes - 1] == "\\":
                    backslashes += 1
                self.safe = self.safe and backslashes % 2 == 0
            elif tag == "table":
                self.reject()  # Nested tables do not supply a flat context.
            if fragment or self.table_start is not None:
                if (blocked or (parent in _CHILDREN and tag not in _CHILDREN[parent])
                        or (tag in _PARENTS and parent not in _PARENTS[tag])):
                    self.reject()
            self.event(tag, start, start + len(self.get_starttag_text()), structural_gap=parent in _CHILDREN)
            if tag in {"td", "th"} and (self.table_start is not None or fragment):
                self.boundary(True)
            if tag not in _VOID:
                self.stack.append((tag, blocked or any(unsafe for _, unsafe in self.stack)))

        def handle_endtag(self, tag):
            start = self.position()
            end = value.find(">", start) + 1
            self.infer(tag, closing=True)
            # Preserve the pre-existing, bounded HTML optional-p rule.
            if (self.stack and self.stack[-1][0] == "p" and tag in {"div", "td", "th", "li", "dd"}
                    and len(self.stack) > 1 and self.stack[-2][0] == tag):
                self.stack.pop()
            balanced = bool(self.stack and self.stack[-1][0] == tag)
            if fragment or self.table_start is not None:
                if not balanced or not re.fullmatch(r"</[\w:-]+[ \t\r\n\f]*>", value[start:end], flags=re.ASCII):
                    self.reject()
            if tag in {"td", "th"} and (self.table_start is not None or fragment):
                self.boundary(False)
            if tag == "p" and (self.table_start is not None or fragment) and _OPTIONAL_P_END.match(value, start):
                # https://html.spec.whatwg.org/multipage/grouping-content.html#the-p-element
                self.pending.append((start, start + 4))
            # Closing a cell is a content edge; closing a row/section/table is
            # a structural gap. Never erase spacing between inline children.
            self.event(tag, start, end, structural_gap=tag in _CHILDREN)
            closes_table = tag == "table" and self.table_start is not None and len(self.stack) == self.table_depth
            if balanced:
                self.stack.pop()
            else:
                # Recover only to find a later independent table, never to
                # authorize a projection of this malformed one.
                for i in range(len(self.stack) - 1, -1, -1):
                    if self.stack[i][0] == tag:
                        closes_table = tag == "table" and self.table_start is not None and i + 1 == self.table_depth
                        del self.stack[i:]
                        break
            if closes_table:
                if self.safe and masked[self.table_start:end] == value[self.table_start:end]:
                    tables.append((self.table_start, end))
                    if not fragment:
                        for left, right in self.pending:
                            omitted[left:right] = b"\1" * (right - left)
                self.table_start = None
                if not fragment:
                    self.pending = []

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if tag not in _VOID:
                self.reject()
                closes_table = tag == "table" and len(self.stack) == self.table_depth
                self.stack.pop()
                if closes_table:
                    self.table_start = None
                    if not fragment:
                        self.pending = []

        def handle_data(self, data):
            if ((fragment or self.table_start is not None) and self.stack
                    and self.stack[-1][0] in _CHILDREN
                    and any(c not in _SPACE for c in data)):
                self.reject()

        def handle_entityref(self, name):
            self.handle_data("&" + name + ";")

        def handle_charref(self, name):
            self.handle_data("&#" + name + ";")

        def handle_comment(self, data):
            if fragment or self.table_start is not None:
                self.reject()

        def handle_decl(self, decl):
            self.handle_comment(decl)

        def unknown_decl(self, data):
            self.handle_comment(data)

    parser = Cells()
    try:
        parser.feed(masked)
        parser.close()
    except LimitReached:
        return value, list(range(len(value))), []
    if fragment and parser.query_safe:
        for left, right in parser.pending:
            omitted[left:right] = b"\1" * (right - left)
    positions = [i for i in range(len(value)) if not omitted[i]]
    return "".join(value[i] for i in positions), positions, tables


def cell_whitespace_projection(quote):
    projected, positions, _ = _cell_projection(quote, fragment=True)
    return projected, positions


def table_projections(text):
    """Only complete, code-free source tables admit a formatting comparison."""
    projected, positions, tables = _cell_projection(text)
    for start, end in tables:
        left, right = bisect_left(positions, start), bisect_left(positions, end)
        yield projected[left:right], positions[left:right]


def _inline_cell_positions(value):
    """Balanced, attribute-free presentation tags inside one explicit cell.

    No structural tags, links, hidden/style attributes, mathematical annotations
    or edit marks are omitted. An unsupported/malformed child keeps its entire
    cell literal, rather than guessing the intended DOM.
    """
    starts = [0, *(m.end() for m in re.finditer("\n", value))]
    cells = []

    class InlineCells(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.cell = None

        def position(self):
            line, column = self.getpos()
            return starts[line - 1] + column

        def handle_starttag(self, tag, attrs):
            start = self.position()
            end = start + len(self.get_starttag_text())
            if tag in {"td", "th"}:
                if self.cell is not None:
                    self.cell["depth"] += 1
                    self.cell["safe"] = False
                else:
                    self.cell = {"tag": tag, "start": end, "depth": 1,
                                 "safe": True, "stack": [], "omitted": []}
            elif self.cell is not None:
                if tag in {"span", "b", "strong", "i", "em"} and not attrs:
                    self.cell["stack"].append(tag)
                    self.cell["omitted"].append((start, end))
                else:
                    self.cell["safe"] = False

        def handle_endtag(self, tag):
            cell = self.cell
            if cell is None:
                return
            start = self.position()
            if tag in {"td", "th"}:
                cell["depth"] -= 1
                if cell["depth"] == 0:
                    if cell["safe"] and tag == cell["tag"] and not cell["stack"] and cell["omitted"]:
                        kept = bytearray(b"\1" * (start - cell["start"]))
                        for left, right in cell["omitted"]:
                            kept[left - cell["start"]:right - cell["start"]] = b"\0" * (right - left)
                        cells.append([cell["start"] + i for i, keep in enumerate(kept) if keep])
                    self.cell = None
            elif cell["stack"] and tag == cell["stack"][-1]:
                cell["stack"].pop()
                cell["omitted"].append((start, value.find(">", start) + 1))
            else:
                cell["safe"] = False

        def handle_startendtag(self, tag, attrs):
            if self.cell is not None:
                self.cell["safe"] = False

        def handle_comment(self, data):
            if self.cell is not None:
                self.cell["safe"] = False

    parser = InlineCells()
    parser.feed(value)
    parser.close()
    return cells


def inline_cell_projections(text):
    """Each projection is one cell in a complete code-free source table."""
    for table, original_positions in table_projections(text):
        for positions in _inline_cell_positions(table):
            yield "".join(table[i] for i in positions), [original_positions[i] for i in positions]
