"""Bounded query recovery and discovery alternatives, entirely through the port.

``recovery_limit`` counts extra distinct queries across this invocation, not
backend calls. Explicit host queries can use ``rewrite_queries=False``. Raw
outcomes and screening/preparation decisions remain artifacts; they are never
source evidence. Topic screening requires the complete normalized topic phrase
in a title or snippet. A foundation exception requires a cited title in the
returned title; an author cue alone is insufficient. Fetch limits and content
classification belong to the caller.

Candidate metadata contains ``work_id`` (normalized actual DOI, otherwise a
normalized-title SHA-256), ``title_key``, location, rank, preference and item ID.
``FetchItem.reason`` is ``retrieval/1 `` followed by canonical JSON containing
work_id, title_sha256, location, rank and preference. ``candidates_ref`` retains
the final identities/order, including unique title-to-DOI reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from deepresearch.engine.contracts import EngineError, canonical_json, digest_bytes
from deepresearch.workflows.contracts import FetchItem, public_url

_TOOLS = {"web.search", "scholar.crossref.search", "scholar.openalex.search"}
_METADATA_HOSTS = ("scribd.com", "researchgate.net", "scispace.com", "typeset.io")
_FILLER = set("a an the of for to from in on and or with what is are how which obtain retrieve fetch read download full complete text primary core originating publication paper sections discussion conclusion please about that this its define explain search find".split())
_FOCUS = ("definition", "principles", "process", "methodology", "modeling", "requirements", "contradictions")


def _key(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold().replace("_", " ")))


def _quote(text):
    return '"' + " ".join(text.replace('"', "").split()) + '"'


def _short(text, words=12):
    return " ".join(text.split()[:words])[:240].strip()


@dataclass(frozen=True)
class _Query:
    original: str
    prepared: str | None
    preparation: str
    titles: tuple[str, ...]
    authors: tuple[str, ...]
    year: str | None
    variants: tuple[str, ...]


def _prepare(query, topic, source_ids, rewrite):
    if any(re.search(r"(?<![\w.-])" + re.escape(identity) + r"(?![\w.-])", query) for identity in source_ids):
        return _Query(query, None, "references_retained_source", (), (), None, ())
    subject = _short(topic or "", 16)
    quoted = tuple(dict.fromkeys(phrase.strip() for phrase in re.findall(r'["“]([^"”\n]{3,512})["”]', query)
                                if _key(phrase) != _key(subject)))
    name_words = {"design", "theory", "modeling", "formulation", "problem", "analysis", "axiomatic", "environment", "based"}
    quoted_authors = tuple(phrase for phrase in quoted
        if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}", phrase)
        and not set(_key(phrase).split()) & name_words)
    titles = tuple(phrase for phrase in quoted if phrase not in quoted_authors)
    authors = list(quoted_authors)
    authors.extend(re.findall(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})['’]s\b", query))
    byline = re.search(r"\b(?:by|author:)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})", query)
    if byline:
        authors.append(byline.group(1))
    leading = re.match(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+", query)
    if subject and leading and _key(query[leading.end():]).startswith(_key(subject)):
        authors.append(leading.group(1))
    authors = tuple(dict.fromkeys(" ".join(word for word in author.split() if word.casefold() not in _FILLER)
                                  for author in authors))
    authors = tuple(author for author in authors if author)
    years = re.findall(r"\b(?:19|20)\d{2}\b", query)
    year = years[0] if years else None
    cue = " ".join((*authors[:1], *([year] if year else [])))
    focus = [word for word in _FOCUS if word in _key(query).split()][:2]
    keywords = [word for word in _key(query).split() if word not in _FILLER and word not in _key(subject).split()]
    if titles:
        prepared = " ".join(filter(None, (_quote(subject) if subject else "", _quote(titles[0]), cue)))
        reason = "subject_and_cited_title"
    elif subject:
        # Definition vocabulary stays attached to the actual subject; no
        # speculative ecological vocabulary or synonyms are introduced.
        prepared = " ".join(filter(None, (_quote(subject), cue, " ".join(focus))))
        reason = "subject_core_vocabulary"
    else:
        prepared = _short(" ".join(dict.fromkeys(keywords))) or query.strip()
        reason = "short_keywords"
    if not rewrite:
        prepared, reason = query, "host_literal_query"
    variants = []
    for title in titles:
        variants += [_quote(title), " ".join(filter(None, (_quote(title), cue)))]
    if subject:
        variants += [_quote(subject), " ".join(filter(None, (_quote(subject), " ".join(authors[:1])))),
                     subject, " ".join(filter(None, (subject, " ".join(focus[:1]))))]
    else:
        variants += [_short(" ".join(keywords), 5), _short(" ".join(keywords), 3)]
    distinct = tuple(dict.fromkeys(value for value in variants if value.strip() and value != prepared))
    return _Query(query, prepared, reason, titles, authors, year, distinct)


def _title(row):
    return row.get("title") or " ".join(row.get("titles") or [])


def _contains_phrase(text, phrase):
    # Preserve every subject word and its order, including modifiers such as
    # "based". Space padding avoids partial-word matches after normalization.
    return bool(phrase) and " " + phrase + " " in " " + text + " "


def _screen(row, topic, query):
    titles = [row["title"]] if row.get("title") else row.get("titles") or []
    title_keys = [_key(title) for title in titles]
    topic_key = _key(topic or "")
    if not topic_key:
        return True, "no_explicit_topic"
    # Check fields independently: a title ending in one subject word and an
    # unrelated snippet starting in the next must not invent a topic phrase.
    if any(_contains_phrase(text, topic_key) for text in [*title_keys, _key(row.get("snippet") or "")]):
        return True, "topic_phrase"
    if any(_contains_phrase(title, _key(cue)) for title in title_keys for cue in query.titles):
        return True, "cited_title_cue"
    return False, "topic_or_cited_title_missing"


def _doi(row):
    value = row.get("doi")
    if not value:
        url = row.get("doi_url") or row.get("url") or ""
        parsed = urlsplit(url)
        if parsed.hostname and parsed.hostname.casefold() in {"doi.org", "dx.doi.org"}:
            value = unquote(parsed.path.lstrip("/"))
        else:
            # Publishers can return a DOI explicitly in an actual landing/PDF
            # path. This identity joins alternatives; it never creates a URL.
            match = re.search(r"/doi/(?:(?:abs|full|pdf|epdf)/)?(10\.\d{4,9}/\S+)$",
                              unquote(parsed.path), re.I)
            if match:
                value = match.group(1)
    if isinstance(value, str) and re.fullmatch(r"10\.\d{4,9}/\S+", value.strip(), re.I):
        return value.strip().casefold()
    return None


def _locations(name, row):
    if name == "web.search":
        yield row.get("url"), "web.url", False, False
    elif name == "scholar.crossref.search":
        for index, link in enumerate(row.get("links") or []):
            pdf = (link.get("content_type") or "").casefold().split(";")[0] == "application/pdf"
            yield link.get("url"), f"crossref.links.{index}", pdf, False
        yield row.get("doi_url"), "crossref.doi_url", False, False
    else:
        access = row.get("open_access") or {}
        yield access.get("oa_url"), "openalex.open_access.oa_url", False, bool(access.get("is_oa"))
        for label, location in [("best_oa_location", row.get("best_oa_location")),
                                ("primary_location", row.get("primary_location")),
                                *((f"locations.{i}", location) for i, location in enumerate(row.get("locations") or []))]:
            if location:
                yield location.get("pdf_url"), f"openalex.{label}.pdf_url", True, bool(location.get("is_oa"))
                yield location.get("landing_page_url"), f"openalex.{label}.landing_page_url", False, bool(location.get("is_oa"))
        yield row.get("doi_url"), "openalex.doi_url", False, False


def _preference(url, pdf, oa):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if any(host == domain or host.endswith("." + domain) for domain in _METADATA_HOSTS):
        return 90
    pdf = pdf or parsed.path.casefold().endswith(".pdf")
    academic = bool(re.search(r"(?:\.edu(?:\.[a-z]+)?$|\.ac\.[a-z]+$|universit)", host))
    author = bool(re.search(r"/(?:~|people/|faculty/|staff/|personal/|users/)", parsed.path))
    if academic or author:
        return 0 if pdf else 10
    if pdf:
        return 20 if oa else 30
    if oa:
        return 35
    if host in {"doi.org", "dx.doi.org"}:
        return 60
    return 40


def _project(name, rows, discovery_id, topic, query):
    projected, decisions = [], []
    for index, row in enumerate(rows, 1):
        keep, reason = _screen(row, topic, query)
        title = _title(row)
        title_key = _key(title)
        doi = _doi(row)
        decision = {"rank": row.get("rank", index), "title": title, "accepted": keep, "reason": reason}
        decisions.append(decision)
        if not keep:
            continue
        for url, location, pdf, oa in _locations(name, row):
            if not isinstance(url, str):
                continue
            try:
                public_url(url)
            except ValueError:
                continue
            title_sha256 = digest_bytes(title_key.encode()) if title_key else None
            work_id = "doi:" + doi if doi else "title:" + title_sha256 if title_sha256 else "url:" + digest_bytes(url.encode())
            projected.append({"url": url, "work_id": work_id, "doi": doi,
                "title": title, "title_key": title_key, "title_sha256": title_sha256,
                "location": location, "rank": row.get("rank", index),
                "preference": _preference(url, pdf, oa), "discovery_ref": discovery_id})
    return projected, decisions


def _optional_admission_denial(result, name):
    error, process = result.get("error") or {}, result.get("process") or {}
    return (name == "scholar.openalex.search" and result.get("status") == "limit_exhausted"
        and error.get("code") == "SCHOLAR_QUOTA_EXHAUSTED"
        and result.get("recording", {}).get("status") == "complete"
        and process.get("dispatched") is False
        and process.get("cleanup", {}).get("complete") is True
        and error.get("commit_state") == "not_applicable"
        and (result.get("persistence") or {}).get("commit_state") == "not_applicable")


def _settled_search_unavailable(result, name):
    error, process = result.get("error") or {}, result.get("process") or {}
    cleanup, persistence = process.get("cleanup") or {}, result.get("persistence") or {}
    recording, tool = result.get("recording") or {}, result.get("tool") or {}
    # This exact native terminal describes a read-only search with no usable
    # discoveries. The worker's generic unknown-effect label is retained; it
    # cannot turn this no-mutation outcome into an unresolved business commit.
    return (name == "web.search" and tool.get("name") == name
        and type(tool.get("revision")) is int and tool["revision"] in {1, 2}
        and result.get("status") == "failed" and result.get("result") is None
        and error.get("code") == "SEARCH_UNAVAILABLE"
        and error.get("commit_state") == "not_applicable"
        and error.get("retryable_delivery") is False
        and recording.get("status") == "complete" and recording.get("error") is None
        and process.get("dispatched") is True and process.get("exit_code") == 3
        and process.get("termination_reason") is None
        and cleanup.get("complete") is True and cleanup.get("errors") == []
        and cleanup.get("unconfirmed_resources") == []
        and persistence.get("required") is False
        and persistence.get("commit_state") == "not_applicable"
        and persistence.get("operation_id") is None and persistence.get("receipt") is None)


def _must_stop(result, name):
    error = result.get("error") or {}
    persistence = result.get("persistence") or {}
    quota_denial = _optional_admission_denial(result, name)
    # Generic ToolFault labels also cover settled read-only unavailability.
    # Exempt only that exact terminal or the proven no-dispatch admission
    # denial. Unknown status/commitment and shared execution limits still stop.
    known_read_failure = _settled_search_unavailable(result, name)
    if (result.get("status") == "unknown" or error.get("commit_state") == "unknown"
            or (error.get("observed_effect_state") == "unknown" and not (quota_denial or known_read_failure))
            or persistence.get("commit_state") == "unknown"):
        raise EngineError(error.get("code", "DISCOVERY_UNKNOWN"), "Discovery effect or commitment is unresolved",
                          observed_effect_state="unknown", commit_state="unknown")
    if result.get("status") in {"cancelled", "timed_out", "limit_exhausted"} and not quota_denial:
        raise EngineError(error.get("code", "DISCOVERY_FAILED"), "Discovery reached a shared execution limit")
    if result.get("process", {}).get("cleanup", {}).get("complete") is False:
        raise EngineError("CLEANUP_INCOMPLETE", "Discovery resources did not settle")


async def retrieve_candidates(context, queries, search_tools, max_results, *, topic,
                              node_prefix="", source_ids=(), recovery_limit=4,
                              rewrite_queries=True):
    """Return FetchItems and recorded discovery entries, without fetching.

    Recovery queries are globally unique within the call and carry a one-based
    ``recovery_index``; initial queries use zero. Pass the caller's remaining
    per-round allowance as ``recovery_limit`` and a distinct node prefix for
    another invocation. Previously retained source IDs are reserved, never reused.
    A recorded, known no-dispatch OpenAlex admission denial disables that backend
    for this call. A settled, recorded SEARCH_UNAVAILABLE from read-only
    web.search preserves earlier candidates and permits bounded distinct-query
    recovery. Unknown status/commitment, other unknown effects, incomplete
    recording/cleanup and cancellation propagate without another external action.
    """
    queries, tools, reserved = tuple(queries), tuple(search_tools), set(source_ids)
    if (type(max_results) is not int or not 1 <= max_results <= 10
            or type(recovery_limit) is not int or not 0 <= recovery_limit <= 4
            or type(rewrite_queries) is not bool or not tools or len(set(tools)) != len(tools)
            or set(tools) - _TOOLS or not re.fullmatch(r"[A-Za-z0-9_.-]*", node_prefix)
            or len(node_prefix) > 100 or (topic is not None and (not isinstance(topic, str) or len(topic.encode()) > 1024))
            or any(not isinstance(query, str) or not query.strip() or len(query.encode()) > 4096 for query in queries)):
        raise EngineError("INVALID_DATA", "Retrieval inputs exceed the bounded query/tool contract")
    prepared = [_prepare(query, topic, reserved, rewrite_queries) for query in queries]
    retained, found, disabled, dispatched = [], [], set(), set()
    ids, serial, recovery_used = {}, 0, 0

    async def execute(query, original, preparation_ref, recovery_index, query_index, attempt_index):
        nonlocal serial
        usable_web = False
        for tool_index, name in enumerate(tools):
            if name in disabled:
                continue
            node_id = f"{node_prefix}discovery.{query_index}.{attempt_index}.{tool_index}"
            async with context.node(node_id, "discovery", {"tool": name, "query": query, "recovery_index": recovery_index}) as node:
                result = await context.port.run_tool(name, {"query": query, "max_results": max_results})
                if result.get("recording", {}).get("status") != "complete":
                    raise EngineError("RECORDING_INCOMPLETE", "Discovery outcome was not durably acknowledged")
                raw_ref = await context.port.publish(canonical_json(result), "application/json", node_id + ".json")
                node["detail"]["artifact_ref"] = raw_ref
                _must_stop(result, name)
                candidates, decisions = [], []
                if result.get("status") == "succeeded":
                    candidates, decisions = _project(name, result["result"].get("results", []), node_id, topic, original)
                for candidate in candidates:
                    if candidate["url"] not in ids:
                        serial += 1
                        while f"{node_prefix}source-{serial:03d}" in reserved:
                            serial += 1
                        ids[candidate["url"]] = f"{node_prefix}source-{serial:03d}"
                    candidate["item_id"] = ids[candidate["url"]]
                found.extend(candidates)
                usable_web |= name == "web.search" and any(candidate["preference"] < 60 for candidate in candidates)
                selection = {"schema_version": 1, "tool": name, "original_query": original.original,
                    "executed_query": query, "topic": topic, "preparation": original.preparation,
                    "recovery_index": recovery_index, "received_count": len(decisions),
                    "accepted_count": sum(decision["accepted"] for decision in decisions),
                    "decisions": decisions, "candidates": candidates}
                selection_ref = await context.port.publish(canonical_json(selection), "application/json", node_id + ".selection.json")
                retained.append({"discovery_id": node_id, "tool": name, "query": query,
                    "status": result["status"], "artifact_ref": raw_ref, "original_query": original.original,
                    "preparation_ref": preparation_ref, "selection_ref": selection_ref,
                    "recovery_index": recovery_index, "candidates": candidates})
                node["detail"].update(artifact_ref=raw_ref, selection_ref=selection_ref, candidate_count=len(candidates))
                if _optional_admission_denial(result, name):
                    disabled.add(name)
        return usable_web

    for query_index, original in enumerate(prepared):
        prep_id = f"{node_prefix}retrieval.query.{query_index}"
        async with context.node(prep_id, "query_preparation", {"preparation": original.preparation}) as node:
            prep = {"schema_version": 1, "original_query": original.original, "executed_query": original.prepared,
                "topic": topic, "preparation": original.preparation, "rewrite_queries": rewrite_queries,
                "cited_titles": list(original.titles), "author_cues": list(original.authors),
                "year": original.year, "recovery_variants": list(original.variants), "recovery_limit": recovery_limit}
            preparation_ref = await context.port.publish(canonical_json(prep), "application/json", prep_id + ".json")
            node["detail"]["preparation_ref"] = preparation_ref
        if original.prepared is None:
            continue
        if original.prepared in dispatched:
            continue
        dispatched.add(original.prepared)
        usable = await execute(original.prepared, original, preparation_ref, 0, query_index, 0)
        if "web.search" not in tools or usable:
            continue
        for attempt_index, variant in enumerate(original.variants, 1):
            if recovery_used >= recovery_limit:
                break
            if variant in dispatched or any(other.prepared == variant for other in prepared):
                continue
            dispatched.add(variant)
            recovery_used += 1
            if await execute(variant, original, preparation_ref, recovery_used, query_index, attempt_index):
                break

    # Prefer an actual DOI when an otherwise identical normalized title has one
    # unambiguous DOI in the returned payloads. No URL is derived from that DOI.
    title_dois = {}
    for candidate in found:
        if candidate["title_key"] and candidate["doi"]:
            title_dois.setdefault(candidate["title_key"], set()).add(candidate["doi"])
    for candidate in found:
        alternatives = title_dois.get(candidate["title_key"], set())
        if not candidate["doi"] and len(alternatives) == 1:
            candidate["work_id"] = "doi:" + next(iter(alternatives))
    unique = {}
    for candidate in found:
        current = unique.get(candidate["url"])
        if current is None or (candidate["preference"], candidate["rank"]) < (current["preference"], current["rank"]):
            unique[candidate["url"]] = candidate
    ordered = sorted(unique.values(), key=lambda candidate: (candidate["preference"], candidate["rank"], int(candidate["item_id"].rsplit("-", 1)[1])))
    items, works = [], {}
    for candidate in ordered:
        reason = {key: candidate[key] for key in ("work_id", "title_sha256", "location", "rank", "preference")}
        items.append(FetchItem(item_id=candidate["item_id"], url=candidate["url"], discovery_ref=candidate["discovery_ref"],
                               reason="retrieval/1 " + canonical_json(reason).decode()))
        works.setdefault(candidate["work_id"], []).append(candidate["item_id"])
    async with context.node(f"{node_prefix}retrieval.candidates", "discovery_selection",
                            {"candidate_count": len(items), "recovery_used": recovery_used}) as node:
        summary = {"schema_version": 1, "topic": topic, "recovery_used": recovery_used,
            "candidates": ordered, "works": works,
            "discoveries": [{"discovery_id": entry["discovery_id"], "candidates": entry["candidates"]} for entry in retained]}
        candidates_ref = await context.port.publish(canonical_json(summary), "application/json", f"{node_prefix}retrieval.candidates.json")
        node["detail"]["candidates_ref"] = candidates_ref
        for entry in retained:
            entry["candidates_ref"] = candidates_ref
            entry["recovery_used"] = recovery_used
    return items, retained
