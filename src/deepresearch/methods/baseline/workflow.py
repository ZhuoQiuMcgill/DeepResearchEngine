"""Formal baseline: plan, bounded research rounds, synthesis and review."""
from __future__ import annotations

from importlib.resources import files

from deepresearch.engine.contracts import EngineError, digest_bytes, strict_json_loads
from deepresearch.workflows import FetchItem, FetchManifest, MethodDefinition, SourceManifest
from deepresearch.workflows.components.acquisition import acquire
from deepresearch.workflows.components.context_selection import assemble_context
from deepresearch.workflows.components.discovery import discover
from deepresearch.workflows.components.search_policy import SearchPolicy, infer_topic
from .contracts import EvidenceAnalysis, ResearchPlan
from .stages.roles import decision, retain, validate_findings
from .stages.reporting import write_and_review


def resource(name, revision=2):
    return strict_json_loads(files(__package__).joinpath("resources", str(revision), name).read_bytes())


def definition(revision=2):
    spec = resource("method.json", revision)
    assets = {name: digest_bytes(files(__package__).joinpath("resources", str(revision), name).read_bytes())
              for name in ("method.json", "input.schema.json", "parameters.schema.json")}
    for name in ("workflow.py", "contracts.py", "stages/roles.py", "stages/reporting.py"):
        assets[name] = digest_bytes(files(__package__).joinpath(name).read_bytes())
    for name in ("discovery.py", "acquisition.py", "context_selection.py", "agents.py", "search_policy.py"):
        assets["component:" + name] = digest_bytes(files("deepresearch.workflows.components").joinpath(name).read_bytes())
    return MethodDefinition("baseline", revision, spec["description"], resource("input.schema.json", revision),
        resource("parameters.schema.json", revision), tuple((role["role_id"], role["revision"]) for role in spec["agent_roles"]), assets,
        tool_revisions=spec.get("tool_revisions", {}))


class BaselineMethod:
    revision = 2
    defaults = {"max_results": 5, "max_sources": 4, "max_rounds": 2, "max_queries": 2,
        "context_tokens": 6000, "max_context_bytes": 32768, "max_scan_bytes": 131072,
        "strict_tokens": False, "max_report_attempts": 2, "queries": [],
        "search_tools": ["web.search", "scholar.crossref.search"], "source_urls": []}
    max_source_text_bytes = 16384

    async def run(self, context, task_input, parameters):
        question = task_input["question"].strip()
        options = {**self.defaults, **parameters}
        if "search_topic" in options and not options["search_topic"].strip():
            raise EngineError("INVALID_DATA", "Search topic must be nonblank")
        search_policy = SearchPolicy(options.get("search_topic") or infer_topic(question)) if self.revision >= 3 else None
        if not question:
            raise EngineError("INVALID_DATA", "Research question must be nonblank")
        if len(options["queries"]) > options["max_queries"]:
            raise EngineError("INVALID_DATA", "Supplied queries exceed the selected per-round query budget")
        if options["strict_tokens"]:
            context.tokens.measure("", context.model_ref, require_verified=True)
        supplied = [FetchItem(item_id=f"requested-{index + 1:03d}", url=url, reason="User-selected source")
                    for index, url in enumerate(options["source_urls"])]
        plan, planner = await decision(context, "baseline.planner", {
            "question": question, "user_queries": options["queries"], "max_queries": options["max_queries"],
        }, ResearchPlan, node_id="plan.research")
        if len(plan.queries) > options["max_queries"]:
            raise EngineError("INVALID_ROLE_OUTPUT", "Planner exceeded the selected query budget")
        plan_ref = planner["output_ref"]
        await context.checkpoint({"kind": f"baseline-plan/{self.revision}", "plan_ref": plan_ref})
        queries = options["queries"] or plan.queries
        sources, discovery_sets, rounds, fetched, searched = SourceManifest(), [], [], set(), set()
        analysis = evidence = context_plan = None
        stop_reason = "round_limit"
        for round_index in range(1, options["max_rounds"] + 1):
            prefix = f"r{round_index}."
            fresh_queries = [query for query in queries if query not in searched][:options["max_queries"]]
            for query in fresh_queries:
                if not query.strip() or len(query.encode("utf-8")) > 4096:
                    raise EngineError("INVALID_DATA", "Each literal search query must fit 4,096 UTF-8 bytes")
            discovered, sets = await discover(context, fresh_queries, options["search_tools"],
                options["max_results"], node_prefix=prefix, policy=search_policy,
                source_ids=[source.item_id for source in sources.items],
                rewrite_queries=not (round_index == 1 and options["queries"]))
            searched.update(fresh_queries)
            discovery_sets.extend(sets)
            candidates, seen = [], set(fetched)
            for item in (supplied if round_index == 1 else []) + discovered:
                if item.url not in seen:
                    candidates.append(item)
                    seen.add(item.url)
            remaining = options["max_sources"] - len(fetched)
            async with context.node(prefix + "discovery.select", "source_selection", {"candidate_count": len(candidates)}):
                ids = await context.select(prefix + "discovery.select", "discovery.select", [item.item_id for item in candidates])
                by_id = {item.item_id: item for item in candidates}
                manifest = FetchManifest(items=[by_id[item_id] for item_id in ids[:remaining]])
                fetch_ref = await retain(context, manifest.to_dict(), prefix + "fetch-manifest.json")
            if manifest.items:
                sources = await acquire(context, manifest, previous=sources)
                fetched.update(item.url for item in manifest.items)
            if not any(source.status == "succeeded" for source in sources.items):
                raise EngineError("NO_EVIDENCE", "No selected source was successfully retained")
            source_ref = await retain(context, sources.to_dict(), prefix + "source-manifest.json")
            evidence, context_plan = await assemble_context(context, sources, question + "\n" + "\n".join(plan.questions),
                token_budget=options["context_tokens"], max_text_bytes=options["max_context_bytes"],
                max_scan_bytes=options["max_scan_bytes"], strict_tokens=options["strict_tokens"],
                recipient_role="baseline.analyst", node_prefix=prefix,
                max_source_text_bytes=self.max_source_text_bytes)
            selected_ids = [selection.item_id for selection in context_plan.selections]
            analysis, analyst = await decision(context, "baseline.analyst", {
                "question": question, "plan": plan.to_dict(), "evidence": evidence,
                "available_source_ids": selected_ids, "round": round_index,
            }, EvidenceAnalysis, node_id=prefix + "analyze.evidence")
            async with context.node(prefix + "analyze.bindings", "evidence_validation"):
                validate_findings(analysis, selected_ids, plan)
            round_record = {"round": round_index, "queries": fresh_queries, "fetch_manifest_ref": fetch_ref,
                "source_manifest_ref": source_ref, "analysis_ref": analyst["output_ref"],
                "context_plan": context_plan.to_dict(), "sufficient": analysis.sufficient}
            rounds.append(round_record)
            await context.checkpoint({"kind": f"baseline-research/{self.revision}", "plan_ref": plan_ref, "rounds": rounds})
            if analysis.sufficient:
                stop_reason = "evidence_sufficient"
                break
            if len(fetched) >= options["max_sources"]:
                stop_reason = "source_limit"
                break
            queries = [query for query in analysis.follow_up_queries if query not in searched]
            if not queries:
                stop_reason = "no_new_queries"
                break
        writer_plan = context_plan.model_copy(deep=True, update={"recipient_role": "baseline.writer"})
        async with context.node("context.deliver", "context_delivery", {"source_count": len(writer_plan.selections)}):
            await retain(context, writer_plan.to_dict(), "writer-context-plan.json")
            await context.port.update(context_plan=writer_plan.to_dict())
        report_ref, drafts = await write_and_review(context, question, plan, analysis, evidence,
            writer_plan, max_attempts=options["max_report_attempts"], revision=self.revision)
        result = {"schema_version": 1, "method_id": "baseline", "method_revision": self.revision,
            "plan_ref": plan_ref, "rounds": rounds, "stop_reason": stop_reason,
            "discovery_sets": discovery_sets, "sources": sources.to_dict(),
            "context_plan": writer_plan.to_dict(), "drafts": drafts, "report_ref": report_ref}
        async with context.node("publish.result", "publication"):
            result_ref = await retain(context, result, "research-result.json")
            await context.checkpoint({"kind": f"baseline-result/{self.revision}", "result_manifest_ref": result_ref, "report_ref": report_ref})
            await context.port.update(report_ref=report_ref, result_manifest_ref=result_ref,
                                      context_plan=writer_plan.to_dict(), sources=sources.to_dict())
        return {**result, "result_manifest_ref": result_ref}


class ExpandedBaselineMethod(BaselineMethod):
    """Same research method with a 20-source allowance and 256k Agent roles."""

    revision = 3
    defaults = {**BaselineMethod.defaults, "max_sources": 20,
        "context_tokens": 131072, "max_context_bytes": 524288, "max_scan_bytes": 262144,
        "max_report_attempts": 4}
    max_source_text_bytes = 65536


class EnglishBaselineMethod(ExpandedBaselineMethod):
    """Expanded research with English Writer/Reviewer roles and publication checks."""

    revision = 4
