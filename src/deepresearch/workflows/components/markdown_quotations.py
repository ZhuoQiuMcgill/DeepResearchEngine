"""Source-mapped CommonMark formatting, without flattening structural relations."""
from __future__ import annotations

import re
from itertools import product

from markdown_it import MarkdownIt
from markdown_it.common.normalize_url import normalizeLink
from markdown_it.helpers import parseLinkDestination, parseLinkTitle
from markdown_it.tree import SyntaxTreeNode

_SOFT_BREAK = re.compile(r'[ \t]*\n')
_INLINE_POLICIES = tuple(product((False, True), repeat=4))
_ESCAPABLE = frozenset('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~')


def _text_end(text, cursor, value):
    """Account for parser escapes while retaining every original character."""
    for character in value:
        if (text.startswith('\\', cursor) and cursor + 1 < len(text)
                and text[cursor + 1] in _ESCAPABLE):
            cursor += 1
        if cursor >= len(text) or text[cursor] != character:
            return None
        cursor += 1
    return cursor


def _link_end(text, cursor, child):
    """Validate the entire inline HTTP(S) suffix using the pinned parser.

    Destination/title escapes and entity decoding are deliberately unsupported.
    Normalized hrefs only identify the parsed link; no normalized characters
    enter the projection. Bounds limit optional syntax as well as the label.
    """
    if not text.startswith('](', cursor):
        return None
    maximum = min(len(text), cursor + 8192)
    pos = cursor + 2
    while pos < maximum and text[pos] in ' \t\n':
        pos += 1
    destination = parseLinkDestination(text, pos, maximum)
    if not destination.ok:
        return None
    raw = text[pos:destination.pos]
    if raw.startswith('<') and raw.endswith('>'):
        raw = raw[1:-1]
    if (not 0 < len(raw) <= 4096 or '\\' in raw or raw != destination.str
            or re.fullmatch(r'https?://[^\s]+', raw) is None
            or normalizeLink(raw) != child.attrGet('href')):
        return None
    pos = destination.pos
    gap = pos
    while pos < maximum and text[pos] in ' \t\n':
        pos += 1
    title = ''
    if pos < maximum and text[pos] != ')':
        parsed = parseLinkTitle(text, pos, maximum)
        if (gap == pos or not parsed.ok or parsed.pos - pos > 4096
                or '\\' in text[pos:parsed.pos]
                or text[pos + 1:parsed.pos - 1] != parsed.str):
            return None
        title = parsed.str
        pos = parsed.pos
        while pos < maximum and text[pos] in ' \t\n':
            pos += 1
    if pos >= maximum or text[pos] != ')' or title != (child.attrGet('title') or ''):
        return None
    return pos + 1


def recorded_prefix(segments, target):
    """Recover only a byte-verified contiguous document prefix for a read.

    A gap, conflicting overlap, missing offsets or excessive context leaves the
    Markdown context unknown. This uses already delivered reads, never a fetch.
    """
    start = target.get("start_byte")
    if type(start) is not int or not 0 <= start <= 2097152:
        return None
    if start == 0:
        return ""
    covered = bytearray()
    ordered = sorted((s for s in segments if type(s.get("start_byte")) is int), key=lambda s: s["start_byte"])
    for segment in ordered:
        offset = segment["start_byte"]
        if offset < 0 or offset > len(covered):
            return None
        data = segment["text"].encode("utf-8")
        if segment.get("end_byte") != offset + len(data):
            return None
        overlap = min(len(data), len(covered) - offset)
        if covered[offset:offset + overlap] != data[:overlap]:
            return None
        covered.extend(data[overlap:max(overlap, start - offset)])
        if len(covered) >= start:
            try:
                return covered[:start].decode("utf-8")
            except UnicodeError:
                return None
    return None


def _inline_omissions(token, *, code_ranges=None):
    """Account for every original character before marking presentation syntax.

    Escaped punctuation is accounted for but stays byte-for-byte literal.
    Unsupported transformations (entities, reference links) keep the original
    inline source. Code bodies must equal their parsed content;
    otherwise even padding/newline normalization keeps their delimiters literal.
    Balanced bare sup/sub markup is accounted for but never omitted.
    Four independent groups preserve retained emphasis, links, standalone code
    and code within link labels without enumerating subsets of individual spans.
    """
    text, cursor = token.content, 0
    omitted = [set() for _ in range(4)]
    link = None
    html_stack = []

    def literal():
        return [set() for _ in range(4)]

    for child in token.children or []:
        if child.type in {"strong_open", "strong_close", "em_open", "em_close"}:
            if not text.startswith(child.markup, cursor):
                return literal()
            omitted[0].update(range(cursor, cursor + len(child.markup)))
            cursor += len(child.markup)
            continue
        if child.type == 'link_open':
            if link is not None or not text.startswith('[', cursor):
                return literal()
            link = child, cursor + 1
            omitted[3].add(cursor)
            cursor += 1
            continue
        if child.type == 'link_close':
            if link is None or not 0 < cursor - link[1] <= 1024:
                return literal()
            end = _link_end(text, cursor, link[0])
            if end is None:
                return literal()
            omitted[3].update(range(cursor, end))
            cursor, link = end, None
            continue
        if child.type == "text":
            end = _text_end(text, cursor, child.content)
            if end is None:
                return literal()
            cursor = end
            continue
        elif child.type == "softbreak":
            # The inline parser consumes spaces before a soft newline. Keep
            # those original bytes in the projection and account for them.
            gap = _SOFT_BREAK.match(text, cursor)
            if gap is None:
                return literal()
            value = gap.group()
        elif child.type == 'html_inline' and child.content in {'<sup>', '</sup>', '<sub>', '</sub>'}:
            value = child.content
            if value.startswith('</'):
                if not html_stack or html_stack.pop() != value[2:-1]:
                    return literal()
            else:
                html_stack.append(value[1:-1])
        elif child.type == "code_inline":
            marker = child.markup
            end = re.search(r"(?<!`)" + re.escape(marker) + r"(?!`)", text[cursor + len(marker):])
            if not text.startswith(marker, cursor) or end is None:
                return literal()
            value = text[cursor:cursor + len(marker) + end.end()]
            body_start, body_end = cursor + len(marker), cursor + len(value) - len(marker)
            if text[body_start:body_end] == child.content:
                if code_ranges is not None:
                    code_ranges.append((body_start, body_end))
                group = omitted[2 if link is not None else 1]
                group.update(range(cursor, body_start))
                group.update(range(body_end, cursor + len(value)))
        else:
            return literal()
        if not text.startswith(value, cursor):
            return literal()
        cursor += len(value)
    return omitted if cursor == len(text) and link is None and not html_stack else literal()


def _inline_positions(token, *, policy=(True, True, True, True), omissions=None):
    """Keep exact source indices, with at most sixteen formatting policies."""
    groups = _inline_omissions(token) if omissions is None else omissions
    omitted = set().union(*(group for group, omit in zip(groups, policy) if omit))
    return [i for i in range(len(token.content)) if i not in omitted]


def _inline_policies(groups):
    """Deduplicate omission sets before allocating full source index maps."""
    seen = set()
    for policy in _INLINE_POLICIES:
        omitted = frozenset().union(*(g for g, omit in zip(groups, policy) if omit))
        if omitted not in seen:
            seen.add(omitted)
            yield policy, omitted


def _table_inline_omissions(node, text, starts):
    """Map parsed cell syntax back to physical cells, retaining every pipe.

    The parser may unescape cells, pad short rows or drop excess cells. Never
    use those normalized values as source text. Only exact cell mappings can
    omit formatting; unsupported cells and ragged rows stay literal.
    """
    omitted = [set() for _ in range(4)]
    for group in node.children:
        for row in group.children:
            if row.type != "tr" or row.map is None or row.map[1] != row.map[0] + 1:
                continue
            left, right = (starts[i] for i in row.map)
            raw = text[left:right].rstrip('\r\n')
            pipes = []
            for match in re.finditer(r'\|', raw):
                index = match.start()
                back = index - 1
                while back >= 0 and raw[back] == '\\':
                    back -= 1
                if (index - back - 1) % 2 == 0:
                    pipes.append(index)
            bounds = list(zip([0, *(i + 1 for i in pipes)], [*pipes, len(raw)]))
            if bounds and not raw[slice(*bounds[0])].strip():
                bounds.pop(0)
            if bounds and not raw[slice(*bounds[-1])].strip():
                bounds.pop()
            if len(bounds) != len(row.children):
                continue
            for cell, (begin, end) in zip(row.children, bounds):
                if len(cell.children) != 1 or cell.children[0].type != 'inline':
                    continue
                token = cell.children[0].token
                original = raw[begin:end]
                if not token.content or original.strip() != token.content:
                    continue
                offset = left + begin + len(original) - len(original.lstrip())
                for group, indices in zip(omitted, _inline_omissions(token)):
                    group.update(offset + i for i in indices)
    return omitted


def _list_item_omissions(node, text, starts):
    """Map a flat item's exact lines while retaining its marker/indentation.

    Multiline items cannot use the contiguous inline-content mapping. Admit
    only a literal bullet prefix and its exact space width on continuations;
    never flatten those lines or join independently projected items.
    """
    token = node.children[0].token
    first, last = token.map
    lines = token.content.split('\n')
    if len(lines) != last - first:
        return None
    positions = []
    width = None
    for line, value in zip(range(first, last), lines):
        raw = text[starts[line]:starts[line + 1]].removesuffix('\n')
        if width is None:
            marker = re.match(r' {0,3}[-+*][ ]+', raw)
            if marker is None:
                return None
            width = marker.end()
        if raw != (raw[:width] if line == first else ' ' * width) + value:
            return None
        positions.extend(range(starts[line] + width, starts[line] + len(raw)))
        if line + 1 < last:
            positions.append(starts[line + 1] - 1)
    groups = _inline_omissions(token)
    return [{positions[i] for i in group} for group in groups]


def mixed_markdown_query(text):
    """One shared format policy for a complete paragraph retaining code syntax.

    Parse the original query once. Never reinterpret a code body as Markdown
    after removing its delimiters. Escapes and entities are never decoded.
    """
    try:
        tokens = MarkdownIt('commonmark').parse(text)
    except (IndexError, RecursionError):
        return None
    if [t.type for t in tokens] != ['paragraph_open', 'inline', 'paragraph_close']:
        return None
    token = tokens[1]
    if token.content != text.strip():
        return None
    groups = _inline_omissions(token)
    if not (groups[1] or groups[2]):
        return None
    # Query destinations and other syntax remain literal. In particular, an
    # explicitly quoted URL cannot disappear and conceal a changed destination.
    return ''.join(token.content[i] for i in _inline_positions(token,
        policy=(False, True, True, False), omissions=groups))


def markdown_projections(text, *, mixed_views=None):
    """Yield independent original-index projections of safe Markdown blocks.

    A paragraph's emphasis, exact inline-code delimiters and inline HTTP(S) link
    syntax can be omitted. A flat unordered list can omit bullet
    markers while preserving all item contents/order. A parsed table can omit
    its delimiter line and parsed cell formatting, retaining every header/data row
    and literal pipe.
    Ordered/nested lists, quotes, HTML and code blocks are never flattened. The caller must
    supply a source with known document-start context, not a fragment of code.
    """
    parser = MarkdownIt("commonmark").enable("table")
    try:
        root = SyntaxTreeNode(parser.parse(text))
    except (IndexError, RecursionError):
        # Malformed nested markup can trip the parser. Disable this optional
        # projection; exact archived-text matching remains available.
        return
    starts = [0, *(m.end() for m in re.finditer("\n", text))]
    starts.append(len(text))

    def inline(node):
        if len(node.children) != 1 or node.children[0].type != "inline":
            return None
        token = node.children[0].token
        start, end = (starts[i] for i in token.map)
        raw = text[start:end]
        if not token.content or raw.count(token.content) != 1:
            return None
        begin = start + raw.index(token.content)
        return token, begin, end

    for node in root.children:
        if node.type == "table":
            # MarkdownIt establishes that this is a table, not a code block,
            # thematic break or prose containing hyphens. Omit only the second
            # physical line and exactly mapped cell syntax; never substitute
            # its normalized/padded cell contents.
            left, right = (starts[i] for i in node.map)
            delimiter_start = starts[node.map[0] + 1]
            delimiter_end = starts[node.map[0] + 2]
            delimiter = text[delimiter_start:delimiter_end].strip()
            if re.fullmatch(r"\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?", delimiter):
                positions = [*range(left, delimiter_start), *range(delimiter_end, right)]
                yield "".join(text[i] for i in positions), positions
                groups = _table_inline_omissions(node, text, starts)
                for _, omitted in _inline_policies(groups):
                    if not omitted:
                        continue
                    # Also retain a projection with the separator, so a quote
                    # may preserve that line while omitting inline syntax.
                    for original in (range(left, right), positions):
                        mapped = [i for i in original if i not in omitted]
                        yield "".join(text[i] for i in mapped), mapped
        elif node.type in {"paragraph", "heading"}:
            found = inline(node)
            if found is None:
                continue
            token, begin, _ = found
            bodies = []
            groups = _inline_omissions(token, code_ranges=bodies)
            if mixed_views is not None and node.type == 'paragraph' and (groups[1] or groups[2]):
                seen = set()
                for emphasis, links in product((False, True), repeat=2):
                    policy = (emphasis, True, True, links)
                    removed = frozenset().union(*(g for g, omit in zip(groups, policy) if omit))
                    if removed in seen:
                        continue
                    seen.add(removed)
                    positions = _inline_positions(token, policy=policy, omissions=groups)
                    mixed_views.append((''.join(token.content[i] for i in positions),
                        [begin + i for i in positions], [(begin + a, begin + b) for a, b in bodies]))
            for policy, omitted in _inline_policies(groups):
                if not omitted:
                    continue
                positions = _inline_positions(token, policy=policy, omissions=groups)
                yield "".join(token.content[i] for i in positions), [begin + i for i in positions]
        elif node.type == "bullet_list":
            if all(len(item.children) == 1 and item.children[0].type == 'paragraph'
                   and len(item.children[0].children) == 1
                   and item.children[0].children[0].type == 'inline' for item in node.children):
                for item in node.children:
                    paragraph = item.children[0]
                    token = paragraph.children[0].token
                    if token.map[1] == token.map[0] + 1:
                        continue
                    groups = _list_item_omissions(paragraph, text, starts)
                    if groups is None:
                        continue
                    left, right = (starts[i] for i in token.map)
                    for _, omitted in _inline_policies(groups):
                        if omitted:
                            mapped = [i for i in range(left, right) if i not in omitted]
                            yield ''.join(text[i] for i in mapped), mapped
            items = []
            for item in node.children:
                if len(item.children) != 1 or item.children[0].type != "paragraph":
                    break
                found = inline(item.children[0])
                if found is None:
                    break
                token, begin, _ = found
                # Multiline/nested items need their own structural handling.
                if token.map[1] != token.map[0] + 1:
                    break
                prefix = text[starts[token.map[0]]:begin]
                if re.fullmatch(r" {0,3}[-+*][ \t]+", prefix) is None:
                    break
                items.append((token, begin, _inline_omissions(token)))
            else:
                if not items:
                    continue
                left, right = (starts[i] for i in node.map)
                kept = bytearray(b"\1" * (right - left))
                all_groups = [set() for _ in range(4)]
                for token, begin, groups in items:
                    line_start = starts[token.map[0]]
                    kept[line_start - left:begin - left] = b"\0" * (begin - line_start)
                    for group, indices in zip(all_groups, groups):
                        group.update(begin + i for i in indices)
                original = [left + i for i, keep in enumerate(kept) if keep]
                for _, omitted in _inline_policies(all_groups):
                    positions = [i for i in original if i not in omitted]
                    yield "".join(text[i] for i in positions), positions
