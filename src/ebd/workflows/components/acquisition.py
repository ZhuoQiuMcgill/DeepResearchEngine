"""Model-free URL-manifest execution through the recorded platform tools."""
from __future__ import annotations

import asyncio
from ebd.engine.contracts import EngineError
from ebd.workflows.contracts import SourceManifest, SourceRecord, TokenMeasurement


async def acquire(context, manifest):
    records = [SourceRecord(item_id=item.item_id, url=item.url, discovery_ref=item.discovery_ref,
        status="pending") for item in manifest.items]
    sources = SourceManifest(items=records)
    await context.port.update(sources=sources.to_dict())
    seen = {}
    for index, item in enumerate(manifest.items):
        async with context.node(f"acquisition.{item.item_id}", "acquisition", {"item_id": item.item_id, "url": item.url}) as node:
            if item.url in seen:
                record = seen[item.url].model_copy(deep=True, update={"item_id": item.item_id, "discovery_ref": item.discovery_ref})
            else:
                try:
                    result = await context.port.run_tool("web.fetch", {"url": item.url, "mode": "static"})
                except (EngineError, asyncio.CancelledError) as error:
                    cancelled = isinstance(error, asyncio.CancelledError) or error.code == "CANCELLED"
                    unknown = isinstance(error, EngineError) and (
                        error.commit_state == "unknown" or error.observed_effect_state == "unknown")
                    records[index] = records[index].model_copy(update={
                        "status": "unknown" if unknown else "cancelled" if cancelled else "failed",
                        "error": error.to_dict() if isinstance(error, EngineError) else EngineError("CANCELLED", "Fetch cancelled").to_dict(),
                        "recording_status": "incomplete", "persistence_state": "unknown" if unknown else "not_applicable"})
                    await context.port.update(cleanup=True, sources=SourceManifest(items=records).to_dict())
                    raise
                persistence, recording = result.get("persistence", {}), result.get("recording", {})
                if recording.get("status") != "complete":
                    raise EngineError("RECORDING_INCOMPLETE", "Fetch outcome was not durably acknowledged")
                if persistence.get("commit_state") == "unknown":
                    records[index] = records[index].model_copy(update={"status": "unknown", "error": result.get("error"), "recording_status": "complete", "persistence_state": "unknown"})
                    await context.port.update(sources=SourceManifest(items=records).to_dict())
                    raise EngineError("ACQUISITION_UNKNOWN", "Fetch commitment is unresolved; no automatic refetch is permitted",
                        observed_effect_state="unknown", commit_state="unknown")
                if result["status"] == "succeeded":
                    value = result["result"]
                    provenance = value["provenance"]
                    record = SourceRecord(item_id=item.item_id, url=item.url, discovery_ref=item.discovery_ref,
                        status="succeeded", snapshot_ref=value["snapshot_ref"], source_run_id=context.run_id,
                        line_count=value["line_count"], page_count=value["page_count"],
                        text_bytes=provenance["text_bytes"], text_sha256=provenance["text_sha256"],
                        provenance=provenance, recording_status="complete", persistence_state=persistence.get("commit_state", "unknown"))
                    measurement = context.tokens.estimate_document(record.text_bytes, record.text_sha256, context.model_ref)
                    record.measurements.append(TokenMeasurement.model_validate(measurement.to_dict()))
                    await context.port.emit("workflow.source.ready", {"item_id": item.item_id,
                        "snapshot_ref": record.snapshot_ref.to_dict(), "text_bytes": record.text_bytes})
                else:
                    receipt = persistence.get("receipt") or {}
                    record = SourceRecord(item_id=item.item_id, url=item.url, discovery_ref=item.discovery_ref,
                        status="cancelled" if result["status"] == "cancelled" else "failed",
                        error=result.get("error"), recording_status="complete",
                        persistence_state=persistence.get("commit_state", "not_applicable"),
                        snapshot_ref=receipt.get("snapshot_ref"), source_run_id=context.run_id,
                        line_count=receipt.get("line_count", 0), page_count=receipt.get("physical_page_count"))
                    if result["status"] in {"cancelled", "timed_out", "limit_exhausted"}:
                        records[index] = record
                        await context.port.update(sources=SourceManifest(items=records).to_dict())
                        raise EngineError((record.error or {}).get("code", "ACQUISITION_FAILED"), "Acquisition reached a shared execution limit")
                seen[item.url] = record
            records[index] = record
            node["detail"]["source_status"] = record.status
            await context.port.update(sources=SourceManifest(items=records).to_dict())
    return SourceManifest(items=records)
