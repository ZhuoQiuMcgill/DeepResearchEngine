"""Baseline strategy over shared acquisition and controlled-context components."""
from __future__ import annotations

from importlib.resources import files

from ebd.engine.contracts import EngineError, canonical_json, strict_json_loads, digest_bytes
from ebd.workflows import FetchItem, FetchManifest, MethodDefinition
from ebd.workflows.components.acquisition import acquire
from ebd.workflows.components.context_selection import assemble_context
from ebd.workflows.components.discovery import discover


def resource(name):
    return strict_json_loads(files(__package__).joinpath(name).read_bytes())


def definition():
    spec = resource("method.json")
    return MethodDefinition(spec["method_id"], spec["revision"], spec["description"],
        resource("input.schema.json"), resource("parameters.schema.json"), (("baseline.writer", 1),),
        {**{name: digest_bytes(files(__package__).joinpath(name).read_bytes())
         for name in ("method.json", "input.schema.json", "parameters.schema.json", "workflow.py")},
         **{f"component:{name}": digest_bytes(files("ebd.workflows.components").joinpath(name).read_bytes())
            for name in ("discovery.py", "acquisition.py", "context_selection.py")}})


class BaselineMethod:
    async def run(self, context, task_input, parameters):
        question = task_input["question"]
        defaults = {"max_results": 5, "max_sources": 3, "context_tokens": 6000,
            "max_context_bytes": 65536, "max_scan_bytes": 262144, "strict_tokens": False,
            "queries": [question], "search_tools": ["web.search", "scholar.crossref.search"], "source_urls": []}
        options = {**defaults, **parameters}
        queries = options["queries"] or [question]
        if any(not query.strip() or len(query.encode("utf-8")) > 4096 for query in queries):
            raise EngineError("INVALID_DATA", "Each literal search query must fit 4,096 UTF-8 bytes")
        supplied = [FetchItem(item_id=f"requested-{i + 1:03d}", url=url, reason="User-selected source")
            for i, url in enumerate(options["source_urls"])]
        if options["strict_tokens"]:
            context.tokens.measure("", context.model_ref, require_verified=True)
        discovered, discovery_sets = await discover(context, queries, options["search_tools"], options["max_results"])
        urls, candidates = set(), []
        raw = supplied + discovered
        for item in raw:
            if item.url not in urls:
                urls.add(item.url)
                candidates.append(item)
        async with context.node("discovery.select", "source_selection", {"candidate_count": len(candidates)}):
            selected = await context.select("discovery.select", "discovery.select", [item.item_id for item in candidates])
            lookup = {item.item_id: item for item in candidates}
            manifest = FetchManifest(items=[lookup[item] for item in selected[:options["max_sources"]]])
            if not manifest.items:
                raise EngineError("NO_SOURCES", "No approved discovery or supplied URL is available")
            fetch_ref = await context.port.publish(canonical_json(manifest.to_dict()), "application/json", "fetch-manifest.json")
        sources = await acquire(context, manifest)
        source_ref = await context.port.publish(canonical_json(sources.to_dict()), "application/json", "source-manifest.json")
        await context.checkpoint({"kind": "baseline-acquired/1", "fetch_manifest_ref": fetch_ref,
            "source_manifest_ref": source_ref, "discovery_sets": discovery_sets})
        evidence, plan = await assemble_context(context, sources, question,
            token_budget=options["context_tokens"], max_text_bytes=options["max_context_bytes"],
            max_scan_bytes=options["max_scan_bytes"], strict_tokens=options["strict_tokens"])
        async with context.node("write.report", "agent", {"role_id": "baseline.writer", "role_revision": 1}):
            outcome = await context.port.invoke_agent("baseline.writer", {"question": question, "evidence": evidence})
            if outcome.get("status") != "succeeded" or outcome.get("recording_status") != "complete" or not outcome.get("output_ref"):
                raise EngineError("REPORT_FAILED", "Writer did not publish an acknowledged report")
        result = {"schema_version": 1, "method_id": "baseline", "method_revision": 1,
            "discovery_sets": discovery_sets, "fetch_manifest_ref": fetch_ref,
            "sources": sources.to_dict(), "context_plan": plan.to_dict(), "report_ref": outcome["output_ref"],
            "writer_run_id": (outcome.get("child_run") or {}).get("run_id"), "usage": outcome.get("usage")}
        manifest_ref = await context.port.publish(canonical_json(result), "application/json", "research-result.json")
        await context.checkpoint({"kind": "baseline-result/1", "result_manifest_ref": manifest_ref, "report_ref": outcome["output_ref"]})
        await context.port.update(report_ref=outcome["output_ref"], result_manifest_ref=manifest_ref,
            context_plan=plan.to_dict(), sources=sources.to_dict(), usage=outcome.get("usage"))
        return result
