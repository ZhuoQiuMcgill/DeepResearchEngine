"""Bounded discovery metadata; unknown values remain unknown, never inferred."""
from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser

from .common import ToolFault, prefix_utf8, url


def object_schema(properties):
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties)}


def coverage_schema():
    count = {"type": "integer", "minimum": 0}
    return object_schema({
        "scope": {"const": "first_page"},
        "requested_max_results": {"type": "integer", "minimum": 1, "maximum": 10},
        "returned_results": count, "available_on_page": count,
        "omitted_by_max_results": count,
        "provider_total_results": {"type": ["integer", "null"], "minimum": 0},
        "more_results_available": {"type": ["boolean", "null"]},
    })


def coverage(requested, returned, available, total=None):
    omitted = max(0, available - returned)
    return {"scope": "first_page", "requested_max_results": requested,
            "returned_results": returned, "available_on_page": available,
            "omitted_by_max_results": omitted, "provider_total_results": total,
            "more_results_available": True if omitted else total > returned if total is not None else None}


def validate_coverage(result, arguments, *, scholarly=False):
    """Parent-side check of facts that the JSON schema cannot relate."""
    returned = len(result["results"])
    total = result["provider_total_results"] if scholarly else None
    if scholarly:
        available = returned
    else:
        attempts = result["backend_attempts"]
        if not attempts or attempts[-1]["outcome"] != "returned" or attempts[-1]["kept_count"] != returned:
            raise ToolFault("WORKER_PROTOCOL_ERROR", "Search coverage lacks its successful backend observation")
        available = attempts[-1]["returned_count"]
    if (returned > arguments["max_results"] or available < returned or
            result["coverage"] != coverage(arguments["max_results"], returned, available, total)):
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Search coverage differs from the recorded request/results")


def extend_scholarly_schema(definitions):
    """Add new closed revisions without changing any released v1 definitions."""
    text = lambda size: {"type": ["string", "null"], "maxLength": size}
    author = object_schema({"name": text(512), "given": text(256), "family": text(256),
                            "orcid": text(8192), "author_id": text(8192)})
    flags = {"type": "array", "maxItems": 256, "uniqueItems": True,
             "items": {"type": "string", "maxLength": 128}}
    bibliography = object_schema({
        "authors": {"type": ["array", "null"], "maxItems": 32, "items": author},
        "authors_total": {"type": ["integer", "null"], "minimum": 0},
        "abstract": text(16384),
        "abstract_source": {"enum": ["crossref.abstract", "openalex.abstract_inverted_index"]},
        "abstract_normalization": {"enum": ["jats-text/1", "inverted-index/1"]},
        "container_titles": {"type": ["array", "null"], "maxItems": 8,
                             "items": {"type": "string", "maxLength": 1024}},
        "cited_by_count": {"type": ["integer", "null"], "minimum": 0},
        "missing_fields": flags, "invalid_fields": flags, "truncated_fields": flags,
    })
    for provider in ("crossref", "openalex"):
        candidate = deepcopy(definitions[provider + "_candidate"])
        candidate["properties"]["bibliography"] = bibliography
        candidate["required"].append("bibliography")
        definitions[provider + "_candidate_v2"] = candidate
        result = deepcopy(definitions[provider + "_result"])
        result["properties"]["results"]["items"] = {"$ref": f"#/$defs/{provider}_candidate_v2"}
        result["properties"]["coverage"] = coverage_schema()
        result["required"].append("coverage")
        definitions[provider + "_result_v2"] = result


class _AbstractText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag.split(":")[-1] in {"p", "br", "title", "sec", "list-item"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        self.handle_starttag(tag, [])


def _abstract(provider, value):
    if provider == "crossref":
        if not isinstance(value, str):
            raise ValueError("abstract is not text")
        parser = _AbstractText()
        parser.feed(value)
        parser.close()
        return " ".join("".join(parser.parts).split())
    if not isinstance(value, dict):
        raise ValueError("abstract is not an inverted index")
    positions = {}
    for word, offsets in value.items():
        if not isinstance(word, str) or not word or not isinstance(offsets, list) or not offsets:
            raise ValueError("invalid inverted-index token")
        for offset in offsets:
            if type(offset) is not int or offset < 0 or offset in positions:
                raise ValueError("invalid or overlapping inverted-index position")
            positions[offset] = word
    if not positions:
        return ""
    if max(positions) + 1 != len(positions):
        raise ValueError("inverted index has gaps")
    # Repeated long tokens can expand a small index into an enormous string.
    # Materialize at most the cap plus one UTF-8 codepoint, enough for the
    # common field limiter to report truncation without allocating the tail.
    parts, used = [], 0
    for index in range(len(positions)):
        if index:
            parts.append(" ")
            used += 1
        token = prefix_utf8(positions[index], max(0, 16388 - used))
        parts.append(token)
        used += len(token.encode("utf-8"))
        if used > 16384:
            break
    return "".join(parts)


def bibliography(provider, row):
    """Preserve optional provider fields and explicitly flag loss or absence."""
    missing, invalid, truncated = [], [], []

    def string(value, field, limit, *, link=False):
        if value is None or value == "":
            missing.append(field)
            return None
        if not isinstance(value, str):
            invalid.append(field)
            return None
        if link:
            try:
                return url(value)
            except ToolFault:
                invalid.append(field)
                return None
        shortened = prefix_utf8(value, limit)
        if shortened != value:
            truncated.append(field)
        return shortened

    raw_authors = row.get("author" if provider == "crossref" else "authorships")
    authors, authors_total = None, None
    if raw_authors is None:
        missing.append("authors")
    elif not isinstance(raw_authors, list):
        invalid.append("authors")
    else:
        authors, authors_total = [], len(raw_authors)
        if len(raw_authors) > 32:
            truncated.append("authors")
        for index, raw in enumerate(raw_authors[:32]):
            field = f"authors[{index}]"
            if not isinstance(raw, dict):
                invalid.append(field)
                continue
            if provider == "openalex":
                raw = raw.get("author")
                if not isinstance(raw, dict):
                    invalid.append(field)
                    continue
                name, given, family = raw.get("display_name"), None, None
                orcid, identity = raw.get("orcid"), raw.get("id")
            else:
                given, family = raw.get("given"), raw.get("family")
                name = raw.get("name") or " ".join(v for v in (given, family) if isinstance(v, str))
                orcid, identity = raw.get("ORCID"), None
            # Unknown name components and identifiers are represented by null;
            # only supplied malformed values are optional-field errors.
            values = {"name": (name, 512), "given": (given, 256), "family": (family, 256),
                      "orcid": (orcid, 8192), "author_id": (identity, 8192)}
            authors.append({key: string(value, field + "." + key, size, link=key in {"orcid", "author_id"})
                            if value is not None else None for key, (value, size) in values.items()})
    abstract = None
    raw_abstract = row.get("abstract" if provider == "crossref" else "abstract_inverted_index")
    if raw_abstract is None:
        missing.append("abstract")
    else:
        try:
            abstract = string(_abstract(provider, raw_abstract), "abstract", 16384)
        except (ValueError, TypeError):
            invalid.append("abstract")
    containers = row.get("container-title") if provider == "crossref" else None
    if provider == "openalex":
        primary = row.get("primary_location")
        source = primary.get("source") if isinstance(primary, dict) else None
        name = source.get("display_name") if isinstance(source, dict) else None
        containers = [name] if name is not None else None
    if containers is None:
        missing.append("container_titles")
    elif not isinstance(containers, list) or any(not isinstance(v, str) for v in containers):
        invalid.append("container_titles")
        containers = None
    else:
        if len(containers) > 8:
            truncated.append("container_titles")
        containers = [string(value, f"container_titles[{i}]", 1024) or "" for i, value in enumerate(containers[:8])]
    cited = row.get("is-referenced-by-count" if provider == "crossref" else "cited_by_count")
    if cited is None:
        missing.append("cited_by_count")
    elif type(cited) is not int or not 0 <= cited <= 2**53 - 1:
        invalid.append("cited_by_count")
        cited = None
    return {"authors": authors, "authors_total": authors_total, "abstract": abstract,
            "abstract_source": "crossref.abstract" if provider == "crossref" else "openalex.abstract_inverted_index",
            "abstract_normalization": "jats-text/1" if provider == "crossref" else "inverted-index/1",
            "container_titles": containers, "cited_by_count": cited,
            "missing_fields": sorted(set(missing)), "invalid_fields": sorted(set(invalid)),
            "truncated_fields": sorted(set(truncated))}
