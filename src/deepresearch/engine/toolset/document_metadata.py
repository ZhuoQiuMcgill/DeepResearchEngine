"""Bounded, explicitly declared HTML dates; no inferred publication chronology."""
from __future__ import annotations

_PUBLISHED = {"article:published_time", "parsely-pub-date", "citation_publication_date",
              "citation_date", "dc.date", "dc.date.issued", "dcterms.issued",
              "prism.publicationdate", "datepublished"}
_MODIFIED = {"article:modified_time", "dcterms.modified", "dc.date.modified", "datemodified"}


def declared_dates(tree):
    result = {"origin": "document_declared_not_verified", "published": [], "modified": [], "omitted_count": 0}
    seen = set()
    # Broad <time> or body-date heuristics can select a newer related article.
    # Preserve only recognized explicit document metadata, including conflicts.
    for element in tree.xpath("//head/meta[@content]"):
        field = (element.get("property") or element.get("name") or "").strip().lower()
        group = "published" if field in _PUBLISHED else "modified" if field in _MODIFIED else None
        value = (element.get("content") or "").strip()
        if group is None or not value or (field, value) in seen:
            continue
        seen.add((field, value))
        if len(value) > 160 or len(result[group]) >= 8:
            result["omitted_count"] += 1
            continue
        result[group].append({"field": field, "value": value})
    return result


def dates_schema():
    from .discovery_metadata import object_schema
    values = {"type": "array", "maxItems": 8, "items": object_schema({
        "field": {"type": "string", "maxLength": 64},
        "value": {"type": "string", "minLength": 1, "maxLength": 160}})}
    return object_schema({"origin": {"const": "document_declared_not_verified"},
        "published": values, "modified": values,
        "omitted_count": {"type": "integer", "minimum": 0}})
