"""Retain provider results and project candidates without confusing schemas."""
from __future__ import annotations

from deepresearch.engine.contracts import EngineError, canonical_json
from deepresearch.workflows.contracts import FetchItem, public_url


def candidates(name, payload, discovery_ref):
    rows = payload.get("results", [])
    projected = []
    for row in rows:
        if name == "web.search":
            urls = [row.get("url")]
        elif name == "scholar.crossref.search":
            links = row.get("links", [])
            urls = [link.get("url") for link in links if link.get("content_type") == "application/pdf"]
            urls += [row.get("doi_url")]
        elif name == "scholar.openalex.search":
            locations = [row.get("best_oa_location"), row.get("primary_location")]
            urls = [(row.get("open_access") or {}).get("oa_url")]
            urls += [(location or {}).get("pdf_url") for location in locations]
            urls += [(location or {}).get("landing_page_url") for location in locations]
            urls += [row.get("doi_url")]
        else:
            raise EngineError("INVALID_DATA", "Unregistered discovery projection")
        for candidate in urls:
            if not isinstance(candidate, str):
                continue
            try:
                public_url(candidate)
            except ValueError:
                continue
            projected.append({"url": candidate, "discovery_ref": discovery_ref,
                "reason": f"{name} candidate {row.get('rank', len(projected) + 1)}"})
            break
    return projected


async def discover(context, queries, search_tools, max_results, *, node_prefix=""):
    found, retained = [], []
    for query_index, query in enumerate(queries):
        for tool_index, name in enumerate(search_tools):
            node_id = f"{node_prefix}discovery.{query_index}.{tool_index}"
            async with context.node(node_id, "discovery", {"tool": name, "query": query}):
                result = await context.port.run_tool(name, {"query": query, "max_results": max_results})
                if result.get("recording", {}).get("status") != "complete":
                    raise EngineError("RECORDING_INCOMPLETE", "Discovery outcome was not durably acknowledged")
                ref = await context.port.publish(canonical_json(result), "application/json", node_id + ".json")
                retained.append({"discovery_id": node_id, "tool": name, "query": query,
                    "status": result["status"], "artifact_ref": ref})
                if result["status"] == "succeeded":
                    projected = candidates(name, result["result"], node_id)
                    found.extend(projected)
                    if projected:
                        break
                error = result.get("error") or {}
                if result["status"] in {"cancelled", "timed_out", "limit_exhausted"} or error.get("commit_state") == "unknown":
                    raise EngineError(error.get("code", "DISCOVERY_FAILED"), "Discovery could not safely continue")
    seen, items = set(), []
    for candidate in found:
        if candidate["url"] not in seen:
            seen.add(candidate["url"])
            items.append(FetchItem(item_id=f"{node_prefix}source-{len(items) + 1:03d}", **candidate))
    return items, retained
