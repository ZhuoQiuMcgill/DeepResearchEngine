"""Small real model/tool conversations; no provider SDK bypasses the Engine."""
from __future__ import annotations

import asyncio
import argparse
from pathlib import Path

from ebd.connections import Engine, EngineSettings, RunOptions, RunAccessRequest, RunAccessOptions, HistoryReadRequest
from ebd.contracts import AgentDefinition, RunRef, ToolRef, canonical_json
from ebd.baseline import history


async def main(selected=None):
    workspace = Path.cwd()
    engine = (await Engine.open(EngineSettings(workspace=workspace, storage_root=workspace / "local" / "provider-acceptance"))).unwrap()
    try:
        async def check(provider, model):
            definition = AgentDefinition("check-" + provider,
                "Verify the real tool integration. You must call the registered scholar.crossref.search once with query 'Environment Based Design' and max_results 1. Then return one short sentence identifying the returned work title or explicitly describing the tool error. Do not search by any internal or provider search. Do not invent a tool result.",
                model_ref=model, profile_ref=provider, allowed_tools=[ToolRef("scholar.crossref.search")],
                limits={"max_run_seconds": 180, "max_model_seconds": 75, "max_model_calls": 3, "max_tool_calls": 2})
            registered = engine.register_agent(definition).unwrap()
            result = await engine.run_agent(registered.ref, "Check the platform function tool now.", RunOptions(timeout_seconds=180))
            if not result.execution:
                raise RuntimeError(provider + " failed preflight: " + result.error.code)
            run_ref = RunRef(engine.storage.store_id, result.execution["run_id"])
            access = (await engine.open_run_access(run_ref, RunAccessRequest(history=HistoryReadRequest()), RunAccessOptions())).unwrap()
            async with access:
                trace = await history(access)
            target = workspace / "local" / "provider-acceptance" / (provider + "-" + run_ref.run_id)
            target.mkdir(parents=True, exist_ok=True)
            (target / "result.json").write_bytes(canonical_json(result))
            (target / "trace.json").write_bytes(canonical_json(trace))
            successful_tools = [r for r in trace if r["event"]["kind"] == "tool.outcome" and r["event"]["payload"].get("status") == "succeeded"]
            outcome = {"provider": provider, "model": model, "status": result.status,
                "recording": result.recording_status, "tool_successes": len(successful_tools),
                "model_calls": result.counters.get("model_calls"), "evidence": str(target),
                "error_code": result.error.code if result.error else None}
            print(canonical_json(outcome).decode(), flush=True)
            if result.status != "succeeded" or result.recording_status != "complete" or not successful_tools:
                raise RuntimeError(provider + " real tool conversation did not pass")
        profiles = {"deepseek": "deepseek-flash", "openai": "gpt-6-luna"}
        results = await asyncio.gather(*(check(p, profiles[p]) for p in (selected or profiles)), return_exceptions=True)
        if any(isinstance(r, BaseException) for r in results):
            raise RuntimeError("One or more provider checks failed; saved evidence identifies the outcome")
    finally:
        await engine.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("deepseek", "openai"), action="append")
    asyncio.run(main(parser.parse_args().provider))
