"""Small real model/tool conversations; no provider SDK bypasses the Engine."""
from __future__ import annotations

import asyncio
import argparse
from pathlib import Path

from ebd.connections import Engine, EngineSettings, RunOptions, RunAccessRequest, RunAccessOptions, HistoryReadRequest
from ebd.contracts import AgentDefinition, RunRef, ToolRef, canonical_json
from ebd.baseline import history


TOKEN_COUNTERS = (
    "input_tokens", "output_tokens", "total_tokens", "cached_input_tokens",
    "uncached_input_tokens", "reasoning_output_tokens",
)


def response_usage_records(trace):
    records = []
    for row in trace:
        event = row["event"]
        if event["kind"] != "model.outcome":
            continue
        usage = event["payload"].get("usage")
        if not isinstance(usage, dict) or not all(name in usage for name in TOKEN_COUNTERS):
            raise RuntimeError("Model response has no explicit token usage record")
        if any(value is not None and (type(value) is not int or value < 0)
               for name in TOKEN_COUNTERS for value in (usage[name],)):
            raise RuntimeError("Token counts are invalid")
        records.append({"event_id": event["event_id"],
                        "action_id": event["context"]["action_id"],
                        "attempt_id": event["context"]["attempt_id"], "usage": usage,
                        "provider_usage": event["payload"].get("provider_usage")})
    return records


async def main(selected=None):
    workspace = Path.cwd()
    settings = EngineSettings(workspace=workspace, storage_root=workspace / "local" / "provider-acceptance")
    engine = (await Engine.open(settings)).unwrap()
    completed = {}
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
            usage_records = response_usage_records(trace)
            outcome = {"provider": provider, "model": model, "status": result.status,
                "recording": result.recording_status, "tool_successes": len(successful_tools),
                "model_calls": result.counters.get("model_calls"), "evidence": str(target),
                "error_code": result.error.code if result.error else None,
                "usage": result.usage}
            print(canonical_json(outcome).decode(), flush=True)
            if result.status != "succeeded" or result.recording_status != "complete" or not successful_tools:
                raise RuntimeError(provider + " real tool conversation did not pass")
            if len(usage_records) != result.counters["model_calls"] or any(
                row["usage"]["completeness"] != "complete" or row["usage"]["source"] != "provider"
                for row in usage_records
            ):
                raise RuntimeError(provider + " did not report complete per-response token usage")
            completed[provider] = (run_ref, usage_records, result.usage, target)
        profiles = {"deepseek": "deepseek-flash", "openai": "gpt-6-luna"}
        results = await asyncio.gather(*(check(p, profiles[p]) for p in (selected or profiles)), return_exceptions=True)
        if any(isinstance(r, BaseException) for r in results):
            raise RuntimeError("One or more provider checks failed; saved evidence identifies the outcome")
    finally:
        if not (await engine.close()).complete:
            raise RuntimeError("Provider check cleanup did not complete")
    reopened = (await Engine.open(settings)).unwrap()
    try:
        for provider, (run_ref, expected, aggregate, target) in completed.items():
            access = (await reopened.open_run_access(
                run_ref, RunAccessRequest(history=HistoryReadRequest()), RunAccessOptions()
            )).unwrap()
            async with access:
                restored_trace = await history(access)
            actual = response_usage_records(restored_trace)
            if actual != expected:
                raise RuntimeError(provider + " per-response token usage changed after reopen")
            terminals = [row["event"] for row in restored_trace if row["event"]["kind"] == "agent.finished"]
            if len(terminals) != 1 or terminals[0]["payload"]["usage"] != aggregate:
                raise RuntimeError(provider + " persisted terminal token aggregate differs")
            restored_aggregate = terminals[0]["payload"]["usage"]
            usage_refs = [{"store_id": run_ref.store_id, "event_id": row["event_id"],
                           "action_id": row["action_id"], "attempt_id": row["attempt_id"]}
                          for row in actual]
            if restored_aggregate["per_attempt_usage_refs"] != usage_refs:
                raise RuntimeError(provider + " persisted per-response usage references differ")
            for name in TOKEN_COUNTERS:
                counts = [row["usage"][name] for row in actual if row["usage"][name] is not None]
                if restored_aggregate["known_subtotals"][name] != (sum(counts) if counts else None):
                    raise RuntimeError(provider + " run token aggregate differs from committed responses")
            proof = {"provider": provider, "run_id": run_ref.run_id,
                     "per_response_records": actual, "aggregate": restored_aggregate,
                     "close_reopen_identical": True}
            (target / "token-usage-acceptance.json").write_bytes(canonical_json(proof))
            print(canonical_json({"provider": provider, "token_usage_reopen": "passed",
                                  "response_count": len(actual)}).decode(), flush=True)
    finally:
        if not (await reopened.close()).complete:
            raise RuntimeError("Reopened provider check cleanup did not complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("deepseek", "openai"), action="append")
    asyncio.run(main(parser.parse_args().provider))
