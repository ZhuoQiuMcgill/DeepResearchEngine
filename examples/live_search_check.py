"""Model-free live search acceptance over real workers, events and Storage.

Run: uv run --locked python examples/live_search_check.py
Records three topics in an isolated store and preserves raw discoveries and
screening decisions. It makes no fetch or model calls and does not resume runs.
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
from deepresearch.workflows import MethodDefinition, MethodRegistry, ResearchRunRequest
from deepresearch.workflows.components.discovery import discover
from deepresearch.workflows.components.search_policy import SearchPolicy


class SearchCheck:
    async def run(self, context, task_input, parameters):
        items, retained = await discover(context, task_input["queries"],
            ["web.search","scholar.crossref.search"],5,policy=SearchPolicy(task_input["topic"]))
        payload = {"schema_version":1,"topic":task_input["topic"],
            "items":[item.to_dict() for item in items],"discoveries":retained}
        result = await context.port.publish(canonical_json(payload),"application/json","search-result.json")
        report = await context.port.publish(f"Search-only diagnostic: {len(items)} candidates.\n".encode(),
            "text/plain","search-check.txt")
        return {"report_ref":report,"result_manifest_ref":result}


async def read_json(service, run_id, ref):
    data, offset = [], 0
    while True:
        part = await service.read_artifact(run_id,ref["artifact_id"],start=offset)
        raw = base64.b64decode(part["data"],validate=True)
        data.append(raw)
        offset += len(raw)
        if part["eof"]:
            result = b"".join(data)
            assert digest_bytes(result) == part["sha256"]
            return json.loads(result)
        assert raw and part["next_offset"] == offset


async def main(args):
    output = Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    registry = MethodRegistry()
    registry.register(MethodDefinition("acceptance.search",1,"Recorded search-only diagnostic",
        {"type":"object","additionalProperties":False,"required":["topic","queries"],"properties":{
            "topic":{"type":"string","minLength":1,"maxLength":256},
            "queries":{"type":"array","minItems":1,"maxItems":2,"items":{"type":"string","minLength":1,"maxLength":4096}}}},
        {"type":"object","additionalProperties":False}, tool_revisions={"web.search":2}),SearchCheck())
    engine = (await Engine.open(EngineSettings(storage_root=args.store))).unwrap()
    service = create_research_service(engine,registry=registry)
    records = []
    try:
        cases = [
            ("ebd-definition","Environment-Based Design",["what is Environment-Based Design EBD definition principles process"]),
            ("ebd-foundation","Environment-Based Design",['retrieve full text of Zeng\'s "Environment-based formulation of design problem" to obtain the primary definition']),
            ("rag-survey","retrieval augmented generation",['"retrieval augmented generation" survey']),
        ]
        for label,topic,queries in cases:
            admitted = await service.start_run(ResearchRunRequest(client_request_id=new_id("search-check-"),
                method_id="acceptance.search",method_revision=1,input={"topic":topic,"queries":queries},timeout_seconds=180))
            for _ in range(1800):
                view = await service.get_run(admitted.run_id)
                if not view.active:
                    break
                await asyncio.sleep(.1)
            assert not view.active and view.status == "succeeded", view.error
            payload = await read_json(service,view.run_id,view.result_manifest_ref.to_dict())
            raw_results, selections = [], []
            for discovery in payload["discoveries"]:
                value = await read_json(service,view.run_id,discovery["artifact_ref"])
                raw_results.append(value)
                assert value["recording"]["status"] == "complete"
                if discovery.get("selection_ref"):
                    selection = await read_json(service,view.run_id,discovery["selection_ref"])
                    selections.append(selection)
                    assert selection["accepted_count"] == sum(row["accepted"] for row in selection["decisions"])
            assert payload["items"], f"No useful discoveries for {label}"
            assert view.usage is None, "Search acceptance must make no model calls"
            if label == "ebd-foundation":
                assert any("10.3233/jid-2004-8404" in item["url"].lower() for item in payload["items"]), "Foundational paper was not discovered"
            record = {"label":label,"run":view.to_dict(),"result":payload,"raw_discoveries":raw_results,"selections":selections}
            records.append(record)
            (output / (label + ".json")).write_bytes(canonical_json(record))
            print(json.dumps({"label":label,"run_id":view.run_id,"candidates":len(payload["items"]),
                "calls":[{"tool":result["tool"],"status":result["status"],"backend_attempts":result["observations"].get("backend_attempts")} for result in raw_results],
                "accepted_titles":[row["title"] for selection in selections for row in selection["decisions"] if row["accepted"]]},ensure_ascii=False),flush=True)
    finally:
        service_cleanup = (await service.close()).to_dict()
        engine_cleanup = (await engine.close()).to_dict()
        (output / "cleanup.json").write_bytes(canonical_json({"service":service_cleanup,"engine":engine_cleanup}))
        assert service_cleanup["complete"] and engine_cleanup["complete"]
    (output / "acceptance.json").write_bytes(canonical_json({"schema_version":1,"passed":True,
        "cases":[{"label":record["label"],"run_id":record["run"]["run_id"],"candidates":len(record["result"]["items"])} for record in records]}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--store",default="local/search-fix-live/store")
    parser.add_argument("--output",default="local/search-fix-live/evidence")
    asyncio.run(main(parser.parse_args()))
