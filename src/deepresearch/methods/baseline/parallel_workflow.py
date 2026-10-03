"""Baseline 5: bounded discovery, archived reads, parallel digestion and synthesis."""
from __future__ import annotations

import math
import re

from deepresearch.engine.contracts import EngineError, digest_bytes, strict_json_loads
from deepresearch.workflows import FetchItem, FetchManifest, ResearchQuality, SourceManifest
from deepresearch.workflows.components.acquisition import acquire
from deepresearch.workflows.components.retrieval import retrieve_candidates
from deepresearch.workflows.components.search_policy import infer_topic
from deepresearch.workflows.components.source_access import read_retained_source
from .contracts import ResearchPlan
from .evidence_contracts import DistilledAnalysis
from .stages.distillation import content_hint, distill_sources
from .stages.evidence_delivery import deliver_evidence, discovered_access_urls, reference_queries
from .stages.reporting import write_and_review
from .stages.roles import decision, retain, validate_findings
from .workflow import EnglishBaselineMethod


def substantive_work_count(sources, accesses, digests):
    substantive = {record["source_id"] for record in digests if record["content_kind"] == "substantive"}
    # Equivalent work locations and byte-identical copies count as one work.
    groups = []
    for source in sources.items:
        if source.item_id not in substantive:
            continue
        identities = {"sha256:" + source.text_sha256,
            "work:" + accesses[source.item_id].get("work_id", source.url)}
        overlapping = [group for group in groups if group & identities]
        for group in overlapping:
            identities.update(group)
            groups.remove(group)
        groups.append(identities)
    return len(groups)


def research_quality(sources, accesses, digests, analysis, plan, notes=()):
    substantive = {record["source_id"] for record in digests if record["content_kind"] == "substantive"}
    gaps = list(analysis.gaps)
    covered = {finding.question for finding in analysis.findings}
    gaps += ["Missing answer to planned question: " + question for question in plan.questions if question not in covered]
    gaps += list(notes)
    reasons = []
    if any(not accesses[sid]["complete"] for sid in substantive):
        reasons.append("At least one substantive source has an incomplete archived-text read.")
    if analysis.follow_up_reads:
        reasons.append("The Analyst still requests source ranges that need further evidence delivery.")
    enough = analysis.sufficient and not gaps and not reasons
    return ResearchQuality(status="sufficient" if enough else "partial" if substantive else "insufficient",
        evidence_sufficient=enough, attempted_sources=len(sources.items),
        substantive_sources=substantive_work_count(sources, accesses, digests),
        fully_read_sources=sum(access["complete"] for access in accesses.values()),
        distilled_sources=len({record["source_id"] for record in digests}),
        gaps=list(dict.fromkeys(gaps))[:16], reasons=reasons[:16])


def _work_key(item, entries):
    if item.reason.startswith("retrieval/1 "):
        return strict_json_loads(item.reason[len("retrieval/1 "):].encode("utf-8"))["work_id"]
    for entry in entries:
        for metadata in entry.get("candidates", []):
            if metadata.get("url") == item.url and metadata.get("work_id"):
                return metadata["work_id"]
    match = re.search(r"(?:work|identity)=([^\s;]+)", item.reason)
    if match:
        return match.group(1)
    doi = re.search(r"10\.\d{4,9}/[^\s?#]+", item.url)
    return doi.group(0).lower() if doi else item.url


class ParallelBaselineMethod(EnglishBaselineMethod):
    revision = 5

    def __init__(self, revision=5):
        self.revision = revision

    defaults = {**EnglishBaselineMethod.defaults, "max_scan_bytes": 1048576,
        "search_tools": ["web.search", "scholar.crossref.search", "scholar.openalex.search"],
        "parallel_agents": 4, "max_distillation_calls": 20, "recovery_queries": 4,
        "min_substantive_sources": 2}

    async def run(self, context, task_input, parameters):
        question = task_input["question"]
        if not question.strip():
            raise EngineError("INVALID_DATA", "Research question must be nonblank")
        options = {**self.defaults, **parameters}
        if len(options["queries"]) > options["max_queries"]:
            raise EngineError("INVALID_DATA", "Supplied queries exceed the selected query budget")
        topic = options.get("search_topic") or infer_topic(question)
        if options["strict_tokens"]:
            context.tokens.measure("", context.model_ref, require_verified=True)
        plan, planner = await decision(context, "baseline.planner", {
            "question": question, "user_queries": options["queries"], "max_queries": options["max_queries"],
        }, ResearchPlan, node_id="plan.research")
        if len(plan.queries) > options["max_queries"]:
            raise EngineError("INVALID_ROLE_OUTPUT", "Planner exceeded the selected query budget")
        plan_ref = planner["output_ref"]
        await context.checkpoint({"kind": f"baseline-plan/{self.revision}", "plan_ref": plan_ref})
        sources, accesses, digests, rounds, discovery_sets = SourceManifest(), {}, [], [], []
        fetched, full_works, searched = set(), set(), set()
        backlog = []
        attempted_items = []
        call_counter = {"used": 0}
        pending_reads, supplemental = [], []
        queries = options["queries"] or plan.queries
        stop_reason = "round_limit"

        async def fetch_candidates(candidates, prefix, *, ceiling):
            nonlocal sources, backlog
            candidates = list(candidates) + backlog
            backlog = []
            candidates = list({item.url: item for item in reversed(candidates)}.values())[::-1]
            async with context.node(prefix + "discovery.select", "source_selection", {"candidate_count": len(candidates)}):
                ids = await context.select(prefix + "discovery.select", "discovery.select", [item.item_id for item in candidates])
                by_id = {item.item_id: item for item in candidates}
                queue = [by_id[item_id] for item_id in ids]
                await retain(context, {"schema_version": 1, "items": [item.to_dict() for item in queue[:options['max_sources'] - len(fetched)]]},
                    prefix + "fetch-candidates.json")
            attempted = []
            read_works = set(full_works)
            while queue and len(fetched) < ceiling:
                candidate = queue.pop(0)
                work = _work_key(candidate, discovery_sets)
                if candidate.url in fetched or work in full_works:
                    continue
                if work in read_works:
                    backlog.append(candidate)
                    continue
                item = candidate.model_copy(update={"item_id": f"{prefix}source-{len(fetched) + 1:03d}"})
                fetched.add(item.url)
                attempted.append(item)
                attempted_items.append(item)
                # Every submitted URL counts, even a denied/partial retrieval.
                sources = await acquire(context, FetchManifest(items=[item]), previous=sources)
                source = sources.items[-1]
                if source.status != "succeeded":
                    continue
                access = await read_retained_source(context, source,
                    max_read_bytes=options["max_scan_bytes"], node_prefix=prefix + "access.")
                access["classification"] = source.provenance.get("classification", "static_text")
                access["work_id"] = work
                accesses[source.item_id] = access
                if content_hint(access) == "substantive" and access["complete"]:
                    # Defer alternatives until the Distiller confirms useful
                    # full text; a long paywall page must not suppress them.
                    read_works.add(work)
                else:
                    # Referrals are taken only from bytes fetched and archived,
                    # never constructed from publisher URL conventions.
                    for number, url in enumerate(discovered_access_urls(access), 1):
                        if url not in fetched:
                            queue.insert(0, FetchItem(item_id=f"{source.item_id}.referral-{number}", url=url,
                                discovery_ref=source.item_id, reason=f"Archived access link from {source.item_id}"))
            backlog.extend(queue)
            return await retain(context, FetchManifest(items=attempted).to_dict(), prefix + "fetch-manifest.json")

        def confirm_full_works():
            full_works.update(accesses[record["source_id"]]["work_id"] for record in digests
                if record["content_kind"] == "substantive" and accesses[record["source_id"]]["complete"])

        for round_index in range(1, options["max_rounds"] + 1):
            prefix = f"r{round_index}."
            round_attempt_start = len(attempted_items)
            fresh = list(dict.fromkeys(q for q in queries if q not in searched))[:options["max_queries"]]
            searched.update(fresh)
            candidates, entries = await retrieve_candidates(context, fresh, options["search_tools"],
                options["max_results"], topic=topic, node_prefix=prefix,
                source_ids=list(accesses), recovery_limit=options["recovery_queries"],
                rewrite_queries=not (round_index == 1 and options["queries"]))
            recovery_remaining = options["recovery_queries"] - max((entry.get("recovery_index", 0) for entry in entries), default=0)
            discovery_sets.extend(entries)
            if round_index == 1:
                supplied = [FetchItem(item_id=f"requested-{i + 1:03d}", url=url, reason="User-selected source")
                    for i, url in enumerate(options["source_urls"])]
                candidates = supplied + [item for item in candidates if item.url not in {s.url for s in supplied}]
            # Leave acquisition capacity for later gaps. Digest early enough
            # that actual cited works can improve the next acquisition batch.
            round_ceiling = math.ceil(options["max_sources"] * round_index / options["max_rounds"])
            first_ceiling = len(fetched) + max(1, math.ceil((round_ceiling - len(fetched)) / 2))
            fetch_ref = await fetch_candidates(candidates, prefix, ceiling=min(first_ceiling, round_ceiling))
            if not accesses and backlog:
                await fetch_candidates([], prefix + "fallback.", ceiling=round_ceiling)
            if pending_reads:
                supplemental = await self._fulfill_reads(context, pending_reads, sources, accesses, prefix,
                    max_read_bytes=options["max_scan_bytes"])
            digests, skipped = await distill_sources(context, accesses, sources, question, plan,
                records=digests, concurrency=options["parallel_agents"], max_calls=options["max_distillation_calls"],
                call_counter=call_counter, node_prefix=prefix)
            confirm_full_works()
            # Poor snippets and bibliography-only responses trigger alternate
            # discovery inside the same round; they do not consume a third round.
            extra = []
            if substantive_work_count(sources, accesses, digests) < options["min_substantive_sources"] and len(fetched) < round_ceiling and recovery_remaining:
                rescue_cap = min(options["max_queries"], recovery_remaining)
                rescue = [q for q in reference_queries(digests) if q not in searched][:rescue_cap]
                if not rescue and topic:
                    rescue = [f'"{topic}" methodology', f'"{topic}" filetype:pdf']
                    rescue = [q for q in rescue if q not in searched][:rescue_cap]
                if rescue:
                    searched.update(rescue)
                    extra, entries = await retrieve_candidates(context, rescue, options["search_tools"],
                        options["max_results"], topic=topic, node_prefix=prefix + "recovery.",
                        source_ids=list(accesses), recovery_limit=recovery_remaining - len(rescue))
                    discovery_sets.extend(entries)
            if (extra or backlog) and len(fetched) < round_ceiling:
                await fetch_candidates(extra, prefix + "recovery.", ceiling=round_ceiling)
                digests, more_skipped = await distill_sources(context, accesses, sources, question, plan,
                    records=digests, concurrency=options["parallel_agents"], max_calls=options["max_distillation_calls"],
                    call_counter=call_counter, node_prefix=prefix + "recovery.")
                skipped.extend(more_skipped)
                confirm_full_works()
            fetch_ref = await retain(context, FetchManifest(items=attempted_items[round_attempt_start:]).to_dict(),
                prefix + "round-fetch-manifest.json")
            if not accesses:
                raise EngineError("NO_EVIDENCE", "No discovered source produced a recorded readable snapshot")
            evidence, context_plan, notes = await deliver_evidence(context, sources, accesses, digests,
                token_budget=options["context_tokens"], max_text_bytes=options["max_context_bytes"],
                strict_tokens=options["strict_tokens"], node_prefix=prefix, priority_segments=supplemental)
            selected_ids = list(dict.fromkeys(s.item_id for s in context_plan.selections))
            analysis, analyst = await decision(context, "baseline.analyst", {
                "question": question, "plan": plan.to_dict(), "evidence": evidence,
                "available_source_ids": selected_ids, "round": round_index,
            }, DistilledAnalysis, node_id=prefix + "analyze.evidence")
            async with context.node(prefix + "analyze.bindings", "evidence_validation"):
                validate_findings(analysis, selected_ids, plan)
                if any(read.source_id not in accesses for read in analysis.follow_up_reads):
                    raise EngineError("INVALID_EVIDENCE_REFERENCE", "Analyst requested an unknown saved source")
            analysis_ref = await retain(context, analysis.to_dict(), prefix + "validated-analysis.json")
            analysis_adjustments = ([{"kind": "contradictory_sufficiency", "reported_sufficient": True,
                "validated_sufficient": False}] if analysis._reported_sufficient and not analysis.sufficient else [])
            await retain(context, {"schema_version": 1, "analyst_output_ref": analyst["output_ref"],
                "analysis_ref": analysis_ref, "adjustments": analysis_adjustments}, prefix + "analysis-validation.json")
            notes += [f"Chunk {item['chunk_id']} could not be distilled within the shared call allowance." for item in skipped]
            quality = research_quality(sources, accesses, digests, analysis, plan, notes)
            if quality.substantive_sources < options["min_substantive_sources"]:
                quality = quality.model_copy(update={"status": "partial" if quality.substantive_sources else "insufficient",
                    "evidence_sufficient": False,
                    "reasons": quality.reasons + ["Too few distinct substantive source documents for the selected coverage policy."]})
            await context.port.update(quality=quality.to_dict())
            access_ref = await retain(context, {"schema_version": 1, "sources": [
                {k: v for k, v in access.items() if k != "segments"} for access in accesses.values()],
                "supplemental_reads": [{"source_id": sid, **{k: v for k, v in segment.items() if k != "text"}}
                    for sid, segment in supplemental]}, prefix + "source-access.json")
            digest_ref = await retain(context, {"schema_version": 1, "records": digests,
                "skipped": skipped, "model_calls": call_counter["used"]}, prefix + "distillations.json")
            source_ref = await retain(context, sources.to_dict(), prefix + "source-manifest.json")
            record = {"round": round_index, "queries": fresh, "fetch_manifest_ref": fetch_ref,
                "source_manifest_ref": source_ref, "source_access_ref": access_ref,
                "distillations_ref": digest_ref, "analysis_ref": analysis_ref,
                "analyst_output_ref": analyst["output_ref"], "analysis_adjustments": analysis_adjustments,
                "context_plan": context_plan.to_dict(), "sufficient": quality.evidence_sufficient,
                "quality": quality.to_dict()}
            rounds.append(record)
            await context.checkpoint({"kind": f"baseline-research/{self.revision}", "plan_ref": plan_ref, "rounds": rounds})
            if quality.evidence_sufficient:
                stop_reason = "evidence_sufficient"
                break
            pending_reads = analysis.follow_up_reads
            queries = list(dict.fromkeys(analysis.follow_up_queries + reference_queries(digests)))
            queries = [q for q in queries if q not in searched]
            if not queries and topic and round_index < options["max_rounds"]:
                queries = [f'"{topic}" core method', f'"{topic}" applications']
            if not queries and not pending_reads and not backlog:
                stop_reason = "source_limit" if len(fetched) >= options["max_sources"] else "no_new_queries"
                break
        writer_plan = context_plan.model_copy(deep=True, update={"recipient_role": "baseline.writer"})
        async with context.node("context.deliver", "context_delivery", {"source_count": len(set(s.item_id for s in writer_plan.selections))}):
            await retain(context, writer_plan.to_dict(), "writer-context-plan.json")
            await context.port.update(context_plan=writer_plan.to_dict())
        report_ref, drafts = await write_and_review(context, question, plan, analysis, evidence, writer_plan,
            max_attempts=options["max_report_attempts"], revision=self.revision, quality=quality)
        quality = quality.model_copy(update={"report_accepted": True})
        result = {"schema_version": 1, "method_id": "baseline", "method_revision": self.revision,
            "plan_ref": plan_ref, "rounds": rounds, "stop_reason": stop_reason,
            "discovery_sets": discovery_sets, "sources": sources.to_dict(),
            "source_access_ref": access_ref, "distillations_ref": digest_ref,
            "context_plan": writer_plan.to_dict(), "quality": quality.to_dict(),
            "drafts": drafts, "report_ref": report_ref}
        async with context.node("publish.result", "publication"):
            result_ref = await retain(context, result, "research-result.json")
            await context.checkpoint({"kind": f"baseline-result/{self.revision}", "result_manifest_ref": result_ref,
                "report_ref": report_ref, "quality": quality.to_dict()})
            await context.port.update(report_ref=report_ref, result_manifest_ref=result_ref,
                sources=sources.to_dict(), context_plan=writer_plan.to_dict(), quality=quality.to_dict())
        return {**result, "result_manifest_ref": result_ref}

    @staticmethod
    async def _fulfill_reads(context, requests, sources, accesses, prefix, *, max_read_bytes):
        by_id = {source.item_id: source for source in sources.items}
        extra = []
        for index, request in enumerate(requests):
            source = by_id[request.source_id]
            # A requested range already read can be promoted directly into
            # synthesis, including tail pages omitted by quote-only delivery.
            cached = [segment for segment in accesses[source.item_id]["segments"]
                if segment["range"]["kind"] == request.range.kind
                and segment["range"]["start"] < request.range.end_exclusive
                and segment["range"]["end_exclusive"] > request.range.start]
            if accesses[source.item_id]["complete"] and cached:
                extra.extend((source.item_id, segment) for segment in cached)
                continue
            cursor, used = None, 0
            serial = 0
            while used < max_read_bytes:
                node = f"{prefix}gap-read.{index}.{serial}"
                async with context.node(node, "source_read", {"source_id": source.item_id, "range": request.range.tool_range()}):
                    result = await context.port.run_tool("document.read", {"snapshot_ref": source.snapshot_ref.to_dict(),
                        "range": request.range.tool_range(), "max_text_bytes": min(65536, max_read_bytes - used),
                        "continuation": cursor})
                    if result["status"] != "succeeded" or result.get("recording", {}).get("status") != "complete":
                        raise EngineError("SOURCE_READ_FAILED", "Requested evidence could not be read with complete recording")
                    value = result["result"]
                    text = value["text"]
                    used += len(text.encode("utf-8"))
                    spans = value.get("spans") or []
                    if text:
                        start = spans[0]["start_byte"]
                        segment = {"segment_id": node, "range": request.range.to_dict(), "start_byte": start,
                            "end_byte": start + len(text.encode("utf-8")), "text": text,
                            "text_sha256": digest_bytes(text.encode("utf-8")),
                            "read_action_id": result["invocation"]["action_id"]}
                        extra.append((source.item_id, segment))
                    if not value.get("has_more_in_requested_range"):
                        break
                    next_cursor = value.get("continuation")
                    if not next_cursor or next_cursor == cursor:
                        raise EngineError("SOURCE_READ_FAILED", "Requested source continuation made no progress")
                    cursor, serial = next_cursor, serial + 1
        return extra
