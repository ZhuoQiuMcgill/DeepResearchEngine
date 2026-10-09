"""Parallel source digestion with quotes bound to recorded immutable reads."""
from __future__ import annotations

import re

from deepresearch.engine.contracts import EngineError, canonical_json, digest_bytes
from deepresearch.workflows.components.parallel import bounded_map
from deepresearch.workflows.components.quotations import PreparedQuoteSource, locate_quote
from deepresearch.workflows.components.quote_bindings import AdjacentQuoteSource
from deepresearch.workflows.components.pdf_quotations import layout_window
from deepresearch.workflows.components.markdown_quotations import recorded_prefix
from deepresearch.workflows.components.source_access import source_extraction_feedback
from ..evidence_contracts import SourceDistillation
from .roles import decision, retain


def content_hint(access, *, provenance=None):
    provenance = provenance or {}
    classification = provenance.get('classification', access.get('classification'))
    if classification == "article_abstract":
        return "abstract"
    if classification == "article_metadata":
        return "bibliography"
    base_bytes = (provenance.get('structured_data') or {}).get('base_text_bytes')
    pieces = []
    for segment in access['segments']:
        text = segment['text']
        if base_bytes is not None:
            # Metadata cannot upgrade short/abstract-only body text merely by
            # increasing archive length. Offsets refer to immutable UTF-8 bytes.
            start = segment.get('start_byte')
            if type(start) is not int:
                continue
            text = text.encode('utf-8')[:max(0, base_bytes - start)].decode('utf-8')
        pieces.append(text)
    text = "\n".join(pieces)
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


def validate_distillation(value, job, plan, *, markdown_links=False, html_cells=False, markdown_formatting=False, adjacent_reads=False, pdf_layout=False):
    if value.source_id != job["source"].item_id or value.chunk_id != job["chunk_id"]:
        raise EngineError("INVALID_EVIDENCE_REFERENCE", "Distillation changed its host-pinned source/chunk identity")
    segments = {segment["segment_id"]: segment for segment in job["segments"]}
    media_type = job["source"].provenance.get("media_type")
    html_source = isinstance(media_type, str) and media_type.split(";", 1)[0].strip().lower() in {"text/html", "application/xhtml+xml"}
    html_cells = bool(html_cells and html_source)
    prefix_reads = job.get("access", {}).get("segments", job["segments"])
    prefixes = {sid: recorded_prefix(prefix_reads, segment) for sid, segment in segments.items()} if (markdown_formatting or html_cells) and html_source else {}
    locators = {}
    def prepare_window(window):
        prefix = recorded_prefix(prefix_reads, window) if (markdown_formatting or html_cells) and html_source else None
        margins, breaks = layout_window(job["source"].provenance, window) if pdf_layout else ((), ())
        return PreparedQuoteSource(window["text"], markdown_links=markdown_links,
            html_cells=html_cells and prefix is not None,
            markdown_formatting=markdown_formatting and prefix is not None, markdown_prefix=prefix or "",
            pdf_margins=margins, pdf_page_breaks=breaks)
    adjacent = AdjacentQuoteSource(job["segments"], prepare_window) if adjacent_reads else None
    def match(quote, segment):
        # A fragment may begin inside fenced code; never infer a fresh document
        # from a follow-up range. Exact/HTML comparison remains available.
        sid = segment["segment_id"]
        if sid not in locators:
            prefix = prefixes.get(sid)
            margins, breaks = layout_window(job["source"].provenance, segment) if pdf_layout else ((), ())
            locators[sid] = PreparedQuoteSource(segment["text"], markdown_links=markdown_links,
                html_cells=html_cells and prefix is not None,
                markdown_formatting=markdown_formatting and prefix is not None, markdown_prefix=prefix or "",
                pdf_margins=margins, pdf_page_breaks=breaks)
        return locators[sid].locate(quote)
    changes, invalid, bindings = [], [], []
    for index, finding in enumerate(value.findings):
        if finding.question not in plan.questions or finding.segment_id not in segments:
            raise EngineError("INVALID_EVIDENCE_REFERENCE", "Distillation cites an unknown question or unread source segment")
        original_segment, original_quote = finding.segment_id, finding.quote
        exact = match(finding.quote, segments[finding.segment_id])
        matches = []
        if exact is None:
            alternatives = [(sid, match(finding.quote, segment))
                for sid, segment in segments.items() if sid != finding.segment_id]
            matches = [(sid, quote) for sid, quote in alternatives if quote is not None]
            if len(matches) == 1:
                finding.segment_id, exact = matches[0]
        if exact is None and not matches and adjacent is not None:
            cross_read = adjacent.locate(finding.quote)
            if cross_read is not None:
                exact, binding = cross_read
                finding.segment_id = binding["parts"][0]["segment_id"]
                bindings.append({"finding_index": index, **binding})
        if exact is None or len(exact) > 2048:
            invalid.append({"finding_index": index, "segment_id": original_segment, "quote": original_quote[:512]})
            continue
        finding.quote = exact
        if original_segment != finding.segment_id or original_quote != exact:
            changes.append({"finding_index": index, "from_segment_id": original_segment,
                "to_segment_id": finding.segment_id, "quote_normalized": original_quote != exact})
    job["validation_changes"] = changes
    job["quote_bindings"] = bindings
    if invalid:
        raise EngineError("INVALID_EVIDENCE_REFERENCE", "Distillation quotation is absent from its recorded source segment",
            {"invalid_quotes": invalid})
    hint = content_hint({"segments": job["segments"]}, provenance=job["source"].provenance)
    if hint in {"abstract", "bibliography"} and value.content_kind == "substantive":
        value.content_kind = hint
    return value


async def distill_sources(context, accesses, sources, question, plan, *, records=None,
                          concurrency=4, max_calls=20, call_counter=None, node_prefix="", isolate_errors=False):
    """Only new, identified chunks run; repeated rounds reuse retained digests."""
    records = list(records or [])
    call_counter = call_counter if call_counter is not None else {"used": 0}
    quarantined = call_counter.setdefault("quarantined", {})
    done = {(record["source_id"], record["chunk_id"], record["input_sha256"]) for record in records}
    jobs, skipped = [], []
    by_id = {source.item_id: source for source in sources.items}
    for access in accesses.values():
        for index, segments in enumerate(chunk_source(access)):
            chunk_id = f"{access['source_id']}.chunk-{index + 1:03d}"
            sha = digest_bytes(canonical_json(segments))
            identity = (access["source_id"], chunk_id, sha)
            if identity in quarantined:
                skipped.append(quarantined[identity])
                continue
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
        source_feedback = source_extraction_feedback(source) if isolate_errors else []
        feedback, repair = list(source_feedback), {}
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
                    "content_hint": content_hint(access, provenance=source.provenance)},
                "chunk_id": job["chunk_id"], "segments": job["segments"], "feedback": feedback,
            }
            if isolate_errors:
                task_input.update(getattr(context, "agent_input_defaults", {}))
                task_input["repair"] = repair
            input_ref = await retain(context, task_input, node + ".input.json")
            try:
                value, outcome = await decision(context, "baseline.distiller", task_input,
                    SourceDistillation, node_id=node, input_ref=input_ref, max_attempts=1)
                try:
                    value = validate_distillation(value, job, plan, markdown_links=isolate_errors,
                        html_cells=isolate_errors, markdown_formatting=isolate_errors, adjacent_reads=isolate_errors, pdf_layout=isolate_errors)
                except EngineError as quote_error:
                    if not isolate_errors or not quote_error.details.get("invalid_quotes"):
                        raise
                    # Exact verified findings survive. Exclude only unverified
                    # quotations; never ask a second model to regenerate them.
                    removed = {item["finding_index"] for item in quote_error.details["invalid_quotes"]}
                    value.findings = [finding for i, finding in enumerate(value.findings) if i not in removed]
                    value.summary = (" ".join(f.claim for f in value.findings) or "No verifiable finding in this chunk.")[:4096]
                    value.limitations = (value.limitations[:5] + [f"Host excluded {len(removed)} findings whose quotations could not be verified."])
                    prior_changes = list(job.get("validation_changes", []))
                    value = validate_distillation(value, job, plan, markdown_links=True, html_cells=True, markdown_formatting=True, adjacent_reads=True, pdf_layout=True)
                    job["validation_changes"] = prior_changes + [{"finding_index": i, "action": "excluded_unverified_quote"} for i in sorted(removed)]
            except EngineError as error:
                if not isolate_errors and error.code == "INVALID_ROLE_OUTPUT":
                    raise
                recoverable = error.code in {"INVALID_ROLE_OUTPUT", "INVALID_EVIDENCE_REFERENCE"}
                if not recoverable:
                    raise
                if attempt == 2:
                    if not isolate_errors:
                        raise
                    failure = {"source_id": source.item_id, "chunk_id": job["chunk_id"],
                        "skipped": True, "reason": "invalid_distillation", "error": error.to_dict()}
                    failure["failure_ref"] = await retain(context, failure, node + ".quarantined.json")
                    quarantined[(source.item_id, job["chunk_id"], job["input_sha256"])] = failure
                    await context.port.emit("workflow.evidence.quarantined", {"source_id": source.item_id,
                        "chunk_id": job["chunk_id"], "failure_ref": failure["failure_ref"]})
                    return failure
                if isolate_errors:
                    output_ref = error.details.get("output_ref") or (outcome["output_ref"] if "outcome" in locals() else None)
                    previous = (await context.port.read_artifact(output_ref, max_bytes=65536)).decode("utf-8", errors="replace") if output_ref else None
                    repair = {"attempt": attempt + 1, "previous_output": previous, "errors": [error.to_dict()]}
                feedback = [error.message + ". Correct only the identified contract errors. Preserve verified findings; do not add new findings or meet a target count during repair."]
                if not isolate_errors:
                    feedback = [error.message + ". Return four to six short verified findings. Remove any finding whose quote cannot be copied exactly; do not add more findings during repair."]
                feedback = source_feedback + feedback
                feedback += [f"Finding {item['finding_index']} in {item['segment_id']} has an unmatched quote: {item['quote']!r}. Remove it or copy a shorter exact passage from a supplied segment."[:1024]
                    for item in error.details.get("invalid_quotes", [])[:max(0, 8 - len(feedback))]]
                continue
            record = {"schema_version": 1, "source_id": source.item_id, "chunk_id": job["chunk_id"],
                "input_sha256": job["input_sha256"], "segment_ids": [s["segment_id"] for s in job["segments"]],
                "access_ref": access["access_ref"], "output_ref": outcome["output_ref"],
                "input_ref": input_ref,
                "validation_changes": job.get("validation_changes", []),
                "content_kind": value.content_kind, "distillation": value.to_dict()}
            if job.get("quote_bindings"):
                record["quote_bindings"] = job["quote_bindings"]
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
