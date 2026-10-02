"""Saved-source scanning and explicit, bounded evidence delivery."""
from __future__ import annotations

import re

from deepresearch.engine.contracts import EngineError, digest_bytes
from deepresearch.workflows.contracts import ContextPlan, ContextSelection, SourceRange, TokenMeasurement


def relevance(text, question):
    words = {word.lower() for word in re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}", question)}
    words -= {"what", "which", "with", "that", "this", "from", "have", "does", "the", "and", "how", "are", "for"}
    lower = text.lower()
    return sum(min(lower.count(word), 20) for word in words)


async def scan_source(context, source, question, max_scan_bytes, *, node_prefix=""):
    kind = "pages" if source.page_count is not None else "lines"
    count = source.page_count if kind == "pages" else source.line_count
    step = 10 if kind == "pages" else 200
    used, serial, best = 0, 0, None
    for start in range(1, (count or 0) + 1, step):
        interval = SourceRange(kind=kind, start=start, end_exclusive=min(start + step, count + 1))
        cursor = None
        while used < max_scan_bytes:
            node_id = f"{node_prefix}read.{source.item_id}.{serial}"
            serial += 1
            async with context.node(node_id, "source_read", {"item_id": source.item_id, "range": interval.tool_range()}):
                result = await context.port.run_tool("document.read", {"snapshot_ref": source.snapshot_ref.to_dict(),
                    "range": interval.tool_range(), "max_text_bytes": min(65536, max_scan_bytes - used), "continuation": cursor})
                if result["status"] != "succeeded" or result.get("recording", {}).get("status") != "complete":
                    raise EngineError("SOURCE_READ_FAILED", "Selected retained source could not be read completely recorded")
                value = result["result"]
                text = value["text"]
                used += len(text.encode("utf-8"))
                candidate = (relevance(text, question), interval, value, result["invocation"].get("action_id"))
                if text.strip() and (best is None or candidate[0] > best[0]):
                    best = candidate
                if not value.get("has_more_in_requested_range"):
                    break
                next_cursor = value.get("continuation")
                if not next_cursor or next_cursor == cursor:
                    raise EngineError("SOURCE_READ_FAILED", "Saved-source continuation made no progress")
                cursor = next_cursor
        if used >= max_scan_bytes:
            break
    return best


async def assemble_context(context, sources, question, *, token_budget, max_text_bytes, max_scan_bytes,
                           strict_tokens=False, recipient_role="baseline.writer", node_prefix=""):
    usable = [source for source in sources.items if source.status == "succeeded"]
    async with context.node(node_prefix + "context.select", "context_selection"):
        ids = await context.select(node_prefix + "context.select", "context.select", [source.item_id for source in usable])
    by_id = {source.item_id: source for source in usable}
    selections, blocks = [], []
    for item_id in ids:
        source = by_id[item_id]
        candidate = await scan_source(context, source, question, max_scan_bytes, node_prefix=node_prefix)
        if candidate is None:
            continue
        _, interval, value, action_id = candidate
        async with context.node(f"{node_prefix}context.{item_id}", "context_selection", {"item_id": item_id}):
            spans = value.get("spans") or []
            offset = spans[0]["start_byte"] if spans else None
            def render_block(selected, shortened):
                size = len(selected.encode("utf-8"))
                bounds = f"[{offset},{offset + size})" if offset is not None else "not reported"
                partial = shortened or value.get("truncated", False)
                header = (f"[{item_id}]\nURL: {source.url}\nSnapshot: {source.snapshot_ref.snapshot_id}\n"
                    f"Requested range: {interval.kind} [{interval.start},{interval.end_exclusive})\n"
                    f"Delivered UTF-8 bytes: {bounds}; partial selection: {str(partial).lower()}\n"
                    "Only the text below was supplied; the requested range is not a claim of full coverage.\nContent:\n")
                return header + selected
            allocation = max(1, token_budget // max(1, len(ids)) - 128)
            selected, measured, shortened = context.tokens.fit(value["text"], context.model_ref,
                allocation, min(16384, max_text_bytes), require_verified=strict_tokens)
            while selected:
                trial = "\n\n".join(blocks + [render_block(selected, shortened)])
                total = context.tokens.measure(trial, context.model_ref, scope="assembled",
                    rendering_revision="evidence-blocks/1", require_verified=strict_tokens)
                if len(trial.encode("utf-8")) <= max_text_bytes and total.count is not None and total.count <= token_budget:
                    break
                selected = selected[:len(selected) // 2]
                shortened = True
            if not selected:
                continue
            measured = context.tokens.measure(selected, context.model_ref, require_verified=strict_tokens)
            text_bytes = len(selected.encode("utf-8"))
            selection = ContextSelection(item_id=item_id, snapshot_ref=source.snapshot_ref, range=interval,
                max_text_bytes=text_bytes, text_sha256=digest_bytes(selected.encode("utf-8")),
                measurement=TokenMeasurement.model_validate(measured.to_dict()),
                truncated=shortened or value.get("truncated", False),
                start_byte=offset, end_byte=offset + text_bytes if offset is not None else None,
                source_read_action_id=action_id)
            selections.append(selection)
            blocks.append(render_block(selected, shortened))
            source.measurements.append(selection.measurement)
            await context.port.emit("workflow.measurement", {"item_id": item_id, "measurement": selection.measurement.to_dict()})
    if not selections:
        raise EngineError("NO_EVIDENCE", "No retained evidence fits the selected context policy")
    rendered = "\n\n".join(blocks)
    measurement = context.tokens.measure(rendered, context.model_ref, scope="assembled", rendering_revision="evidence-blocks/1",
        require_verified=strict_tokens)
    ref = await context.port.publish(rendered.encode("utf-8"), "text/plain", node_prefix + "selected-context.txt")
    plan = ContextPlan(recipient_role=recipient_role, model_ref=context.model_ref, token_budget=token_budget,
        max_text_bytes=max_text_bytes, selections=selections, context_ref=ref,
        measurement=TokenMeasurement.model_validate(measurement.to_dict()), strict_tokens=strict_tokens)
    await context.port.emit("workflow.context.selected", {"context_ref": ref, "source_ids": [s.item_id for s in selections],
        "measurement": plan.measurement.to_dict()})
    await context.port.update(context_plan=plan.to_dict(), sources=sources.to_dict())
    return rendered, plan
