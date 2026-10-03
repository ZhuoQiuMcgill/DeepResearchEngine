"""Opt-in real Engine/recording/worker/Storage acceptance, never a pytest mock.

Run: uv run --locked python tests/toolset/live_acceptance.py
The generated evidence/store live under ignored local/toolset-acceptance/.
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import os
from pathlib import Path

from deepresearch.engine.connections import Engine, EngineSettings, RunOptions
from deepresearch.engine.contracts import RunRef, SnapshotRef, canonical_json, new_id
from deepresearch.engine.connections.models import (RunAccessRequest, SnapshotReadRequest,
    HistoryReadRequest, RunAccessOptions)


def parent_memory():
    if os.name != "nt": return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(key, ctypes.c_size_t) for key in
            ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    counters = Counters(); counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb): return None
    return {"private_bytes": counters.PrivateUsage, "working_set_bytes": counters.WorkingSetSize,
        "lifetime_peak_commit_bytes": counters.PeakPagefileUsage, "lifetime_peak_working_set_bytes": counters.PeakWorkingSetSize}


async def main():
    target = Path("local/toolset-acceptance") / new_id("acceptance_")
    engine = (await Engine.open(EngineSettings(storage_root=target / "store", openalex_admission=True))).unwrap()
    rows = []
    try:
        requests = [("web.search", {"query": "environment based design Yong Zeng", "max_results": 5}),
                    ("scholar.crossref.search", {"query": '"Environment based design" "Yong Zeng"', "max_results": 3}),
                    ("scholar.openalex.search", {"query": '"environment-based design"', "max_results": 3}),
                    ("scholar.openalex.search", {"query": '"Environment Based Design" contradiction requirements', "max_results": 5}),
                    ("web.fetch", {"url": "https://www.rfc-editor.org/rfc/rfc9110.txt"}),
                    ("web.fetch", {"url": "https://www.rfc-editor.org/rfc/rfc9110.html"}),
                    ("web.fetch", {"url": "https://www.rfc-editor.org/rfc/rfc9110.pdf"})]
        source_added = False
        for name, arguments in requests:
            before = parent_memory()
            result = await engine.run_tool(name, arguments, RunOptions(timeout_seconds=70))
            row = result.to_dict(); rows.append(row)
            rows.append({"parent_memory": {"tool": name, "before": before, "after": parent_memory(), "scope": "current/lifetime counters, not a per-tool RAM guarantee"}})
            target.mkdir(parents=True, exist_ok=True)
            (target / "evidence.json").write_bytes(canonical_json(rows))
            print(json.dumps({"tool": name, "status": result.status, "recording": result.recording.get("status"),
                "error": result.error.code if result.error else None, "process": result.process,
                "resources": result.observations.get("resources"), "persistence": result.persistence.get("commit_state")}, ensure_ascii=False), flush=True)
            if name == "scholar.openalex.search" and result.status == "succeeded" and not source_added:
                for item in result.result["results"]:
                    location = item.get("best_oa_location")
                    if location and location.get("pdf_url"):
                        requests.append(("web.fetch", {"url": location["pdf_url"]}))
                        source_added = True
                        break
            if name == "web.fetch" and result.status == "succeeded":
                ref = SnapshotRef(**result.result["snapshot_ref"])
                request = RunAccessRequest(read_objects=(SnapshotReadRequest(ref, {"kind": "lines", "start": 1, "end_exclusive": 10}),), history=HistoryReadRequest())
                session = (await engine.open_run_access(RunRef(engine.storage.store_id, result.invocation["run_id"]), request, RunAccessOptions())).unwrap()
                end = min(10, result.result["line_count"] + 1)
                value = (await session.storage.snapshots.read(session.context, ref, {"kind": "lines", "start": 1, "end_exclusive": end})).unwrap()
                rows.append({"saved_source_read": value.to_dict()})
                print(json.dumps({"saved_source_read_bytes": value.byte_length, "snapshot_ref": ref.to_dict()}), flush=True)
                await session.close()
                # The public standalone CLI/Engine route reauthorizes the old
                # snapshot explicitly and runs the real document.read worker.
                from deepresearch.engine.connections import ToolRunOptions
                read = await engine.run_tool("document.read", {"snapshot_ref": ref.to_dict(), "range": {"kind": "lines", "start": 1, "end_exclusive": 10}},
                    ToolRunOptions(source_run_ref=RunRef(engine.storage.store_id, result.invocation["run_id"]),
                        read_objects=(SnapshotReadRequest(ref, {"kind": "lines", "start": 1, "end_exclusive": 10}),)))
                rows.append(read.to_dict())
                print(json.dumps({"tool": "document.read", "status": read.status, "recording": read.recording.get("status"),
                    "error": read.error.code if read.error else None, "text_bytes": read.result["byte_length"] if read.result else None}), flush=True)
        # Concurrency two is measured only after successful single plain/HTML/PDF
        # observations; normal Engine configuration remains concurrency one.
        if any(row.get("tool", {}).get("name") == "web.fetch" and row.get("status") == "succeeded" and row.get("result", {}).get("page_count") for row in rows):
            from deepresearch.engine.toolset import ToolExecutor
            previous = engine.executor
            state, sink = previous.export_quota_checkpoint(), previous._quota_sink
            await previous.close()
            engine.executor = ToolExecutor(engine.catalog, fetch_concurrency=2, quota_checkpoint=state, quota_checkpoint_sink=sink)
            baseline_memory = parent_memory()
            samples = []
            done = asyncio.Event()
            async def sample():
                while not done.is_set():
                    samples.append(parent_memory()); await asyncio.sleep(.01)
            sampling = asyncio.create_task(sample())
            concurrent = await asyncio.gather(*[engine.run_tool("web.fetch", {"url": source}, RunOptions(timeout_seconds=70)) for source in
                ("https://www.rfc-editor.org/rfc/rfc9110.html", "https://www.rfc-editor.org/rfc/rfc9110.pdf")])
            done.set(); await sampling
            measured = {"baseline": baseline_memory, "after": parent_memory(), "sampled_peak_private_bytes": max((s["private_bytes"] for s in samples if s), default=None),
                "sample_count": len(samples), "scope": "sampled parent private bytes plus cumulative process peaks, no general RAM guarantee"}
            rows.extend(result.to_dict() for result in concurrent)
            rows.append({"concurrency_two_memory": measured})
            print(json.dumps({"concurrency_two_statuses": [result.status for result in concurrent], "parent_memory": measured,
                "worker_peaks": [result.observations.get("resources") for result in concurrent]}), flush=True)
        target.mkdir(parents=True, exist_ok=True)
        (target / "evidence.json").write_bytes(canonical_json(rows))
        print("Evidence:", (target / "evidence.json").as_posix(), flush=True)
    finally:
        print("Engine cleanup:", (await engine.close()).to_dict(), flush=True)


if __name__ == "__main__": asyncio.run(main())
