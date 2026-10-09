"""Deliver verified reads and source digests with explicit coverage to synthesis."""
from __future__ import annotations

import re

from deepresearch.engine.contracts import EngineError, canonical_json, digest_bytes
from deepresearch.workflows.contracts import ContextPlan, ContextSelection, TokenMeasurement
from deepresearch.workflows.components.source_access import source_descriptor, source_span_origin
from deepresearch.workflows.components.quote_bindings import bound_quote_units, indexed_quote_bindings
from .roles import retain


def _quote_units(records, access):
    segments = {s["segment_id"]: s for s in access["segments"]}
    units, seen = [], set()
    for record in records:
        bindings = indexed_quote_bindings(record)
        supplied = {sid: segments[sid] for sid in record["segment_ids"]}
        for index, finding in enumerate(record["distillation"]["findings"]):
            if index in bindings:
                for unit in bound_quote_units(finding, bindings[index], supplied):
                    key = (unit["start_byte"], unit["text"])
                    if key not in seen:
                        seen.add(key)
                        units.append(unit)
                continue
            segment = segments[finding["segment_id"]]
            quote = finding["quote"]
            start = segment["text"].find(quote)
            if start < 0:
                raise EngineError("INTEGRITY_ERROR", "Validated source quotation no longer matches its saved read")
            offset = segment["start_byte"] + len(segment["text"][:start].encode("utf-8"))
            key = (offset, quote)
            if key in seen:
                continue
            seen.add(key)
            units.append({**segment, "text": quote, "start_byte": offset,
                "end_byte": offset + len(quote.encode("utf-8")),
                "text_sha256": digest_bytes(quote.encode("utf-8"))})
    return units


def _block(source, access, records, units):
    digests = []
    segments = {s["segment_id"]: s for s in access["segments"]}
    for record in records:
        bindings, findings = indexed_quote_bindings(record), []
        supplied = {sid: segments[sid] for sid in record["segment_ids"]}
        for index, finding in enumerate(record["distillation"]["findings"]):
            summary = {key: finding[key] for key in ("question", "claim", "segment_id")}
            if index in bindings:
                parts = bound_quote_units(finding, bindings[index], supplied)
                summary["segment_ids"] = [p["segment_id"] for p in parts]
            findings.append(summary)
        digests.append({"chunk_id": record["chunk_id"], "content_kind": record["content_kind"],
            "summary": record["distillation"]["summary"], "limitations": record["distillation"]["limitations"],
            "findings": findings})
    lines = [f"[{source.item_id}]", f"URL: {source.url}",
        f"Snapshot: {source.snapshot_ref.snapshot_id}",
        "Source metadata (null means unknown; retrieved_at is not publication date):",
        canonical_json(source_descriptor(source, discovery_metadata=access.get("discovery_metadata"))).decode("utf-8"),
        f"Source read: {access['read_bytes']}/{source.text_bytes} UTF-8 bytes; complete={str(access['complete']).lower()}",
        "Source-worker digests are derived analysis, not independent corroboration:",
        canonical_json(digests).decode("utf-8"), "Verified verbatim source text:"]
    for unit in units:
        origin = source_span_origin(source, unit['start_byte'], unit['end_byte'])
        if origin is not None:
            lines += ['Archive representation (host annotation, not a source quotation): ' +
                      canonical_json(origin).decode('utf-8')]
        lines += [f"Segment {unit['segment_id']}; requested {unit['range']['kind']} "
            f"[{unit['range']['start']},{unit['range']['end_exclusive']}); "
            f"delivered UTF-8 bytes [{unit['start_byte']},{unit['end_byte']})", unit["text"]]
    return "\n".join(lines)


async def deliver_evidence(context, sources, accesses, records, *, token_budget,
                           max_text_bytes, strict_tokens=False, node_prefix="", priority_segments=()):
    by_source = {}
    for record in records:
        if record["content_kind"] != "irrelevant":
            by_source.setdefault(record["source_id"], []).append(record)
    usable = [s for s in sources.items if s.item_id in by_source and s.status == "succeeded"]
    async with context.node(node_prefix + "context.select", "context_selection"):
        ids = await context.select(node_prefix + "context.select", "context.select", [s.item_id for s in usable])
    source_map = {s.item_id: s for s in usable}
    choices, notes = [], []
    promoted = {}
    for source_id, segment in priority_segments:
        promoted.setdefault(source_id, []).append(segment)
    for item_id in ids:
        source, access, digests = source_map[item_id], accesses[item_id], by_source[item_id]
        failed_resources = (source.provenance.get("capture") or {}).get("failed_resources", 0)
        if failed_resources:
            notes.append(f"Rendered source {item_id} had {failed_resources} failed auxiliary resources; dynamic content may be incomplete.")
        if (source.provenance.get("html_extraction") or {}).get("substantial_omission"):
            notes.append(f"Source {item_id} has substantial unmatched HTML prose in a heuristic extraction check; "
                         "a complete archived-text read does not establish complete page extraction.")
        if (source.provenance.get("html_extraction") or {}).get("structure", {}).get("unresolved"):
            notes.append(f"Source {item_id} has unresolved HTML list/table/code structure differences; "
                         "the archived extraction may omit conditions or relationships.")
        digested = {sid for r in digests for sid in r["segment_ids"]}
        units = [s for s in access["segments"] if s["segment_id"] in digested and s["text"]]
        existing = {(s["start_byte"], s["end_byte"]) for s in units}
        units += [s for s in promoted.get(item_id, []) if (s["start_byte"], s["end_byte"]) not in existing]
        choices.append((source, access, digests, units))

    def render(values):
        return "\n\n".join(_block(*value) for value in values)

    def fits(text):
        measurement = context.tokens.measure(text, context.model_ref, scope="assembled",
            rendering_revision="distilled-evidence/1", require_verified=strict_tokens)
        return len(text.encode("utf-8")) <= max_text_bytes and measurement.count is not None and measurement.count <= token_budget

    evidence = render(choices)
    if not fits(evidence):
        choices = [(s, a, d, promoted.get(s.item_id, []) + (_quote_units(d, a) or units[:1])) for s, a, d, units in choices]
        evidence = render(choices)
    # Narrow contexts retain whole source units, never silently clip a quote.
    while choices and not fits(evidence):
        removed = choices.pop()
        notes.append(f"Source {removed[0].item_id} could not fit the synthesis evidence allowance.")
        evidence = render(choices)
    if not choices or not evidence.strip():
        raise EngineError("NO_EVIDENCE", "No validated source digest and recorded text fit the synthesis allowance")
    selections = []
    for source, access, digests, units in choices:
        for unit in units:
            size = len(unit["text"].encode("utf-8"))
            if not size:
                continue
            measurement = context.tokens.measure(unit["text"], context.model_ref,
                require_verified=strict_tokens, rendering_revision="source-text/1")
            selections.append(ContextSelection(item_id=source.item_id, snapshot_ref=source.snapshot_ref,
                range=unit["range"], max_text_bytes=size, text_sha256=unit["text_sha256"],
                measurement=TokenMeasurement.model_validate(measurement.to_dict()),
                start_byte=unit["start_byte"], end_byte=unit["end_byte"],
                truncated=(size != access["document_bytes"]), source_read_action_id=unit["read_action_id"]))
    measurement = context.tokens.measure(evidence, context.model_ref, scope="assembled",
        rendering_revision="distilled-evidence/1", require_verified=strict_tokens)
    ref = await context.port.publish(evidence.encode("utf-8"), "text/plain", node_prefix + "selected-context.txt")
    plan = ContextPlan(recipient_role="baseline.analyst", model_ref=context.model_ref,
        token_budget=token_budget, max_text_bytes=max_text_bytes, selections=selections,
        context_ref=ref, measurement=TokenMeasurement.model_validate(measurement.to_dict()), strict_tokens=strict_tokens)
    await context.port.emit("workflow.context.selected", {"context_ref": ref,
        "source_ids": [s.item_id for s, _, _, _ in choices], "measurement": plan.measurement.to_dict()})
    await context.port.update(context_plan=plan.to_dict())
    return evidence, plan, notes


def reference_queries(records):
    # These are publication titles extracted from saved source text. Preserve
    # their identity as quoted title cues through generic query preparation.
    return list(dict.fromkeys('"' + " ".join(title.replace('"', '').split()) + '"'
        for record in records for title in record["distillation"]["reference_queries"] if title.strip()))


def discovered_access_urls(access):
    """Only URLs actually present in archived source text become referrals."""
    from deepresearch.workflows.contracts import public_url
    urls = []
    for segment in access["segments"]:
        for url in re.findall(r"https?://[^\s<>\"\]]+", segment["text"]):
            url = url.rstrip(".,;)")
            if not (re.search(r"\.pdf(?:$|[?#])", url, re.I) or "/article/" in url):
                continue
            try:
                public_url(url)
            except ValueError:
                continue
            urls.append(url)
    return list(dict.fromkeys(urls))[:4]
