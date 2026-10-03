"""Parallel source digestion with quotes bound to recorded immutable reads."""
from __future__ import annotations

import re

from deepresearch.engine.contracts import EngineError, canonical_json, digest_bytes
from deepresearch.workflows.components.parallel import bounded_map
from deepresearch.workflows.components.quotations import locate_quote
from ..evidence_contracts import SourceDistillation
from .roles import decision, retain


def content_hint(access):
    if access.get("classification") == "article_abstract":
        return "abstract"
    if access.get("classification") == "article_metadata":
        return "bibliography"
    text = "\n".join(segment["text"] for segment in access["segments"])
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    reference_lines = sum(bool(re.match(r"^[|\s]*[\[［]\d+[\]］]", line)) for line in lines)
    if lines and reference_lines / len(lines) >= .45:
        return "bibliography"
    if len(text.encode("utf-8")) < 2048:
        return "abstract"
    return "substantive"


def chunk_source(access, *, max_chunk_bytes=262144):
    chunks, current, size = [], [], 0
    for segment in access["segments"]:
        if not segment["text"]:
            continue
        length = len(canonical_json(segment))
        if current and size + length > max_chunk_bytes:
            chunks.append(current)
            current, size = [], 0
        if length > max_chunk_bytes:
            raise EngineError("LIMIT_EXCEEDED", "A recorded source segment exceeds the distillation input allowance")
        current.append(segment)
        size += length
    if current:
        chunks.append(current)
    return chunks


def matched_quote(quote, text):
    """Return saved bytes, allowing only whitespace/PDF soft word wraps."""
    return locate_quote(quote, text)


def validate_distillation(value, job, plan):
    if value.source_id != job["source"].item_id or value.chunk_id != job["chunk_id"]:
        raise EngineError("INVALID_EVIDENCE_REFERENCE", "Distillation changed its host-pinned source/chunk identity")
    segments = {segment["segment_id"]: segment for segment in job["segments"]}
    changes, invalid = [], []
    for index, finding in enumerate(value.findings):
        if finding.question not in plan.questions or finding.segment_id not in segments:
            raise EngineError("INVALID_EVIDENCE_REFERENCE", "Distillation cites an unknown question or unread source segment")
        original_segment, original_quote = finding.segment_id, finding.quote
        exact = matched_quote(finding.quote, segments[finding.segment_id]["text"])
        if exact is None:
            alternatives = [(sid, matched_quote(finding.quote, segment["text"]))
                for sid, segment in segments.items() if sid != finding.segment_id]
            matches = [(sid, quote) for sid, quote in alternatives if quote is not None]
            if len(matches) == 1:
                finding.segment_id, exact = matches[0]
        if exact is None or len(exact) > 2048:
            invalid.append({"finding_index": index, "segment_id": original_segment, "quote": original_quote[:512]})
            continue
        finding.quote = exact
        if original_segment != finding.segment_id or original_quote != exact:
            changes.append({"finding_index": index, "from_segment_id": original_segment,
                "to_segment_id": finding.segment_id, "quote_normalized": original_quote != exact})
    if invalid:
        raise EngineError("INVALID_EVIDENCE_REFERENCE", "Distillation quotation is absent from its recorded source segment",
            {"invalid_quotes": invalid[:7]})
    job["validation_changes"] = changes
    hint = content_hint({"segments": job["segments"],
        "classification": job["source"].provenance.get("classification")})
    if hint in {"abstract", "bibliography"} and value.content_kind == "substantive":
        value.content_kind = hint
    return value


async def distill_sources(context, accesses, sources, question, plan, *, records=None,
                          concurrency=4, max_calls=20, call_counter=None, node_prefix=""):
    """Only new, identified chunks run; repeated rounds reuse retained digests."""
    records = list(records or [])
    call_counter = call_counter if call_counter is not None else {"used": 0}
    done = {(record["source_id"], record["chunk_id"], record["input_sha256"]) for record in records}
    jobs, skipped = [], []
    by_id = {source.item_id: source for source in sources.items}
    for access in accesses.values():
        for index, segments in enumerate(chunk_source(access)):
            chunk_id = f"{access['source_id']}.chunk-{index + 1:03d}"
            sha = digest_bytes(canonical_json(segments))
            if (access["source_id"], chunk_id, sha) in done:
                continue
            job = {"source": by_id[access["source_id"]], "chunk_id": chunk_id,
                "segments": segments, "input_sha256": sha, "access": access}
            # Reserve finite map work before spawning; retries consume the same
            # shared counter, never a new model or descendant allowance.
            if len(jobs) + call_counter["used"] >= max_calls:
                skipped.append({"source_id": access["source_id"], "chunk_id": chunk_id,
                    "reason": "distillation_call_limit"})
            else:
                jobs.append(job)

    async def worker(job):
        source, access = job["source"], job["access"]
        feedback = []
        for attempt in range(1, 3):
            if call_counter["used"] >= max_calls:
                return {"source_id": source.item_id, "chunk_id": job["chunk_id"],
                    "skipped": True, "reason": "distillation_call_limit"}
            call_counter["used"] += 1
            node = f"{node_prefix}distill.{job['chunk_id']}.{attempt}"
            task_input = {
                "question": question, "plan": plan.to_dict(),
                "source": {"source_id": source.item_id, "url": source.url,
                    "snapshot_ref": source.snapshot_ref.to_dict(), "document_bytes": source.text_bytes,
                    "read_bytes": access["read_bytes"], "complete_read": access["complete"],
                    "content_hint": content_hint(access)},
                "chunk_id": job["chunk_id"], "segments": job["segments"], "feedback": feedback,
            }
            input_ref = await retain(context, task_input, node + ".input.json")
            value, outcome = await decision(context, "baseline.distiller", task_input,
                SourceDistillation, node_id=node, input_ref=input_ref)
            try:
                value = validate_distillation(value, job, plan)
            except EngineError as error:
                if attempt == 2:
                    raise
                feedback = [error.message + ". Return four to six short verified findings. Remove any finding whose quote cannot be copied exactly; do not add more findings during repair."]
                feedback += [f"Finding {item['finding_index']} in {item['segment_id']} has an unmatched quote: {item['quote']!r}. Remove it or copy a shorter exact passage from a supplied segment."[:1024]
                    for item in error.details.get("invalid_quotes", [])[:7]]
                continue
            record = {"schema_version": 1, "source_id": source.item_id, "chunk_id": job["chunk_id"],
                "input_sha256": job["input_sha256"], "segment_ids": [s["segment_id"] for s in job["segments"]],
                "access_ref": access["access_ref"], "output_ref": outcome["output_ref"],
                "input_ref": input_ref,
                "validation_changes": job.get("validation_changes", []),
                "content_kind": value.content_kind, "distillation": value.to_dict()}
            record["validation_ref"] = await retain(context, record, node + ".validated.json")
            await context.port.emit("workflow.evidence.distilled", {
                "source_id": source.item_id, "chunk_id": job["chunk_id"],
                "content_kind": value.content_kind, "output_ref": outcome["output_ref"],
                "input_ref": input_ref,
                "validation_ref": record["validation_ref"], "access_ref": access["access_ref"]})
            return record

    completed = await bounded_map(jobs, worker, concurrency=concurrency)
    for record in completed:
        if record.get("skipped"):
            skipped.append(record)
        else:
            records.append(record)
    return records, skipped
