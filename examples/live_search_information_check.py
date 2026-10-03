"""Check enriched search results through real workers, Storage and restart reads.

No model/fetch calls. Provider failures remain recorded availability findings.
Run: uv run --locked python examples/live_search_information_check.py
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys

from deepresearch.bootstrap import create_research_service
from deepresearch.engine import Engine, EngineSettings
from deepresearch.engine.contracts import canonical_json, digest_bytes, new_id
from deepresearch.engine.toolset.discovery_metadata import validate_coverage
from deepresearch.workflows import MethodDefinition, MethodRegistry, ResearchRunRequest

QUESTION = "What is EBD (Environment Based Design)?"
PINS = {"web.search": 3, "scholar.crossref.search": 2, "scholar.openalex.search": 2}


class SearchInformationCheck:
    async def run(self, context, task_input, parameters):
        probes = [("web.search", task_input["question"]),
                  ("web.search", '"Environment Based Design"'),
                  ("scholar.crossref.search", task_input["question"]),
                  ("scholar.crossref.search", '"Environment-based formulation of design problem"'),
                  ("scholar.openalex.search", '"Environment Based Design"')]
        records = []
        for index, (name, query) in enumerate(probes):
            async with context.node(f"probe.{index}", "discovery", {"tool": name, "query": query}):
                result = await context.port.run_tool(name, {"query": query, "max_results": 10})
                assert result["recording"]["status"] == "complete"
                if result["status"] == "succeeded":
                    assert result["result"]["query"] == query
                    validate_coverage(result["result"], {"query": query, "max_results": 10}, scholarly=name.startswith("scholar."))
                ref = await context.port.publish(canonical_json(result), "application/json", f"probe-{index}.json")
                records.append({"tool": name, "revision": PINS[name], "query": query,
                                "status": result["status"], "artifact_ref": ref})
        ref = await context.port.publish(canonical_json({"question": task_input["question"], "probes": records}),
                                         "application/json", "search-information-result.json")
        report = await context.port.publish(b"Search information diagnostic; inspect per-provider availability and metadata.\n",
                                            "text/plain", "diagnostic.txt")
        return {"report_ref": report, "result_manifest_ref": ref}


def registry():
    value = MethodRegistry()
    value.register(MethodDefinition("acceptance.search-information", 1, "Search metadata diagnostic",
        {"type": "object", "additionalProperties": False, "required": ["question"],
         "properties": {"question": {"const": QUESTION}}},
        {"type": "object", "additionalProperties": False}, tool_revisions=PINS), SearchInformationCheck())
    return value


async def read(service, run_id, ref):
    chunks, offset = [], 0
    while True:
        page = await service.read_artifact(run_id, ref["artifact_id"], start=offset)
        chunk = base64.b64decode(page["data"], validate=True)
        chunks.append(chunk)
        offset += len(chunk)
        if page["eof"]:
            data = b"".join(chunks)
            assert digest_bytes(data) == page["sha256"]
            return data
        assert chunk and page["next_offset"] == offset


async def main(args):
    target = Path(args.output)
    target.mkdir(parents=True, exist_ok=True)
    settings = EngineSettings(storage_root=args.store, openalex_admission=args.admit_openalex)
    engine = (await Engine.open(settings)).unwrap()
    service = create_research_service(engine, registry=registry())
    originals, summaries = [], []
    try:
        request = ResearchRunRequest(client_request_id=new_id("search-information-"),
            method_id="acceptance.search-information", method_revision=1,
            input={"question": QUESTION}, timeout_seconds=180)
        run_id = (await service.start_run(request)).run_id
        for _ in range(2000):
            view = await service.get_run(run_id)
            if not view.active:
                break
            await asyncio.sleep(.1)
        assert not view.active and view.status == "succeeded", view.error
        assert view.usage is None
        result = json.loads(await read(service, run_id, view.result_manifest_ref.to_dict()))
        for index, probe in enumerate(result["probes"]):
            data = await read(service, run_id, probe["artifact_ref"])
            originals.append((probe["artifact_ref"], data))
            (target / f"probe-{index}.json").write_bytes(data)
            raw = json.loads(data)
            payload = raw.get("result") or {}
            rows = payload.get("results", [])
            summary = {**probe, "coverage": payload.get("coverage"),
                "rows_with_authors": sum(bool(row.get("bibliography", {}).get("authors")) for row in rows),
                "rows_with_abstract": sum(bool(row.get("bibliography", {}).get("abstract")) for row in rows),
                "titles": [row.get("title") or row.get("titles") for row in rows],
                "error": (raw.get("error") or {}).get("code")}
            summaries.append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
        (target / "run.json").write_bytes(canonical_json(view.to_dict()))
    finally:
        assert (await service.close()).complete
        assert (await engine.close()).complete
    reopened = (await Engine.open(settings)).unwrap()
    reader = create_research_service(reopened, registry=registry())
    try:
        for ref, data in originals:
            assert await read(reader, run_id, ref) == data
        view = await reader.get_run(run_id)
        assert view.status == "succeeded" and not view.active
    finally:
        assert (await reader.close()).complete
        assert (await reopened.close()).complete
    (target / "acceptance.json").write_bytes(canonical_json({"question": QUESTION, "run_id": run_id,
        "contract_checks_passed": True, "restart_reads_identical": True, "model_calls": 0,
        "probes": summaries, "unavailable_probes": [p for p in summaries if p["status"] != "succeeded"]}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default="local/search-information-live/store")
    parser.add_argument("--output", default="local/search-information-live/evidence")
    parser.add_argument("--admit-openalex", action="store_true")
    asyncio.run(main(parser.parse_args()))
