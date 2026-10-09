"""Agent candidate selection, with bounded metadata and host-enforced identities.

The selector sees discovery metadata and prior acquisition outcomes, never an
implicitly fetched document. Its complete input, output and URL bindings are
retained so a frontend or Hook can explain every admitted fetch.
"""
from __future__ import annotations

from copy import deepcopy

from deepresearch.engine.contracts import EngineError, canonical_json
from ..selection_contracts import SelectionDecision
from .roles import decision, retain

MAX_CANDIDATES = 128
MAX_CANDIDATE_BYTES = 262144


def _text(value, limit, field, notes):
    value = value if isinstance(value, str) else ""
    raw = value.encode("utf-8")
    if len(raw) > limit:
        notes.append("truncated:" + field)
        return raw[:limit].decode("utf-8", errors="ignore")
    return value


def candidate_cards(candidates, discoveries, work_ids, node_prefix):
    """Keep input order; the byte/count cap is explicit, not a relevance filter."""
    metadata = {}
    for entry in discoveries:
        for candidate in entry.get("candidates", []):
            metadata.setdefault(candidate["url"], []).append((candidate, entry))
    cards, bindings, omitted, used = [], {}, [], 2  # JSON array brackets.
    for index, item in enumerate(candidates, 1):
        found = metadata.get(item.url, [])
        # Prefer metadata containing an abstract, without dropping alternative
        # discovery identities. This chooses a description of the SAME URL.
        candidate, entry = max(found, key=lambda pair: bool(
            (pair[0].get("metadata", {}).get("bibliography") or {}).get("abstract")), default=({}, {}))
        raw = candidate.get("metadata", {})
        notes = []
        bibliography = deepcopy(raw.get("bibliography") or {})
        if bibliography.get("abstract") is not None:
            bibliography["abstract"] = _text(bibliography["abstract"], 4096, "abstract", notes)
        authors = bibliography.get("authors")
        if isinstance(authors, list):
            if len(authors) > 8:
                notes.append("truncated:authors")
            bibliography["authors"] = [{"name": _text(author.get("name") or " ".join(filter(None,
                [author.get("given"), author.get("family")])), 256, "author_name", notes)} for author in authors[:8]]
        containers = bibliography.get("container_titles")
        if isinstance(containers, list):
            if len(containers) > 3:
                notes.append("truncated:container_titles")
            bibliography["container_titles"] = [_text(title, 512, "container_title", notes) for title in containers[:3]]
        for key in ("year", "publication_year", "published", "publication_date", "source_date", "publisher", "doi"):
            if key in raw:
                bibliography[key] = (_text(raw[key], 1024, key, notes) if isinstance(raw[key], str) else raw[key])
        identity = f"{node_prefix}candidate-{index:03d}"
        card = {"candidate_id": identity, "url": item.url, "work_id": work_ids[item.url],
            "title": _text(candidate.get("title"), 2048, "title", notes),
            "snippet": _text(raw.get("snippet"), 2048, "snippet", notes),
            "bibliography": bibliography,
            "discovery": {"tool": entry.get("tool"), "query": entry.get("query"),
                "rank": candidate.get("rank"), "location": candidate.get("location"),
                "source": "requested" if item.reason == "User-selected source" else "search" if found else "archived_link",
                "ref": item.discovery_ref, "raw_ref": entry.get("artifact_ref"),
                "reason": item.reason if not found else None},
            "metadata_notes": notes}
        size = len(canonical_json(card)) + bool(cards)  # Include each comma.
        if len(cards) >= MAX_CANDIDATES or used + size > MAX_CANDIDATE_BYTES:
            omitted.append(item)
            continue
        cards.append(card)
        bindings[identity] = item.model_copy(update={"item_id": identity})
        used += size
    coverage = {"total_candidates": len(candidates), "delivered_candidates": len(cards),
        "omitted_candidates": len(omitted), "truncated_candidates": sum(bool(c["metadata_notes"]) for c in cards)}
    return cards, bindings, omitted, coverage


def acquisition_history(sources, accesses, digests):
    history = []
    for source in sources.items:
        records = [record for record in digests if record["source_id"] == source.item_id]
        history.append({"source_id": source.item_id, "url": source.url, "status": source.status,
            "work_id": accesses.get(source.item_id, {}).get("work_id"),
            "complete_read": accesses.get(source.item_id, {}).get("complete", False),
            "content_kinds": list(dict.fromkeys(record["content_kind"] for record in records)),
            "summaries": [record["distillation"]["summary"][:2048] for record in records[:2]],
            "error_code": (source.error or {}).get("code")})
    return history


def validate_selection(value, delivered_ids, budget):
    named = [choice.candidate_id for group in (value.selections, value.deferred, value.rejected) for choice in group]
    if len(named) != len(set(named)) or set(named) != set(delivered_ids):
        raise EngineError("INVALID_SELECTION", "Selector must classify every supplied candidate exactly once; unknown IDs are forbidden",
            {"missing_ids": sorted(set(delivered_ids) - set(named))[:32],
             "unknown_ids": sorted(set(named) - set(delivered_ids))[:32]})
    if len(value.selections) > min(budget["remaining_fetches"], budget["batch_fetch_limit"]):
        raise EngineError("INVALID_SELECTION", "Selector exceeded the current fetch allowance")


async def select_sources(context, candidates, discoveries, work_ids, *, question, plan,
                         sources, accesses, digests, gaps, budget, node_prefix):
    cards, bindings, omitted, coverage = candidate_cards(candidates, discoveries, work_ids, node_prefix)
    inventory = {"schema_version": 1, "items": [item.to_dict() for item in candidates],
        "coverage": coverage, "omitted_ids": [item.item_id for item in omitted]}
    inventory_ref = await retain(context, inventory, node_prefix + "selection-inventory.json")
    if not cards or not budget["batch_fetch_limit"]:
        return [], list(candidates), {"inventory_ref": inventory_ref, "coverage": coverage, "invoked": False}
    task_input = {"question": question, "plan": plan.to_dict(), "candidates": cards,
        "history": acquisition_history(sources, accesses, digests), "gaps": list(gaps),
        "budget": budget, "coverage": coverage}
    input_ref = await retain(context, task_input, node_prefix + "selection-input.json")
    value, outcome = await decision(context, "baseline.selector", task_input, SelectionDecision,
        node_id=node_prefix + "select.sources", input_ref=input_ref,
        validator=lambda value: validate_selection(value, bindings, budget))
    initial_input_ref, input_ref = input_ref, outcome["input_ref"]
    async with context.node(node_prefix + "select.bindings", "selection_validation", {"input_ref": input_ref}) as node:
        validate_selection(value, bindings, budget)
        record = {"schema_version": 1, "invoked": True, "inventory_ref": inventory_ref,
            "initial_input_ref": initial_input_ref,
            "input_ref": input_ref, "output_ref": outcome["output_ref"], "coverage": coverage,
            "decision": value.to_dict(), "bindings": {key: item.to_dict() for key, item in bindings.items()}}
        record["validation_ref"] = await retain(context, record, node_prefix + "selection-validated.json")
        node["detail"].update(output_ref=outcome["output_ref"], validation_ref=record["validation_ref"],
            selected_count=len(value.selections), deferred_count=len(value.deferred), rejected_count=len(value.rejected))
    # Keep large decisions/bindings in their artifact, not repeated in every
    # round checkpoint. The reference remains sufficient for frontend/audit.
    summary = {key: value for key, value in record.items() if key not in {"decision", "bindings"}}
    return ([bindings[choice.candidate_id] for choice in value.selections],
        [bindings[choice.candidate_id] for choice in value.deferred] + omitted, summary)
