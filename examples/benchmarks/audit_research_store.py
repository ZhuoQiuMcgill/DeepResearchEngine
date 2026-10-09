"""Read-only integrity/lineage audit of a settled research store; no model calls.

Use the same OS/Python environment that owns the store (especially on Windows).
The JSON records structural findings, not a judgment of factual report quality.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

from deepresearch.methods.baseline.stages.reporting import citation_issues
from deepresearch.workflows.components.quotations import locate_quote
from deepresearch.workflows.components.quote_bindings import bound_quote_units
from deepresearch.engine.contracts import EngineError


def audit(root):
    root = Path(root).resolve()
    with sqlite3.connect((root / "store.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(list(db.execute("PRAGMA foreign_key_check")))
        pending = Counter(row[0] for row in db.execute(
            "SELECT phase FROM operations WHERE phase NOT IN ('ready','aborted','interrupted')"))
        rows = {r["object_id"]: dict(r) for r in db.execute("SELECT * FROM artifacts WHERE phase='ready'")}
        findings, contents, values = [], {}, {}
        def check(ok, kind, identity):
            if not ok:
                findings.append({"kind": kind, "identity": identity})
        for identity, row in rows.items():
            data = (root / row["relative_key"]).read_bytes()
            check(len(data) == row["byte_length"] and
                  "sha256:" + hashlib.sha256(data).hexdigest() == row["sha256"], "artifact_hash", identity)
            contents[identity] = data
            if row["media_type"] == "application/json":
                try:
                    value = json.loads(data)
                except ValueError:
                    continue  # Raw rejected model output can intentionally be invalid JSON.
                if isinstance(value, dict):
                    values[identity] = value
        def parsed(ref):
            return json.loads(contents[ref["artifact_id"]])
        events = [json.loads(r[0]) for r in db.execute("SELECT envelope FROM events ORDER BY seq")]
        kinds = Counter(e["kind"] for e in events)
        requests = {e["context"]["run_id"]: parsed(e["payload"]["request_ref"])
                    for e in events if e["kind"] == "workflow.accepted"}
        hardened = any(r.get("method_revision", 0) >= 11 for r in requests.values())
        snapshots = {r["object_id"]: json.loads(r["descriptor"]) for r in db.execute("SELECT * FROM snapshots")}
        tools = {e["context"]["action_id"]: e["payload"] for e in events if e["kind"] == "tool.outcome"}
        # Distillation owns its bounded contract-repair loop and does not emit
        # decision()'s generic repair event. Count actual logical Agent nodes
        # carrying repair inputs, rather than treating that event as exhaustive.
        # API restarts stay inside one node and cannot inflate this count.
        repaired_nodes, unavailable_repair_inputs = set(), set()
        for event in events:
            node = event["payload"]
            if event["kind"] != "workflow.node.started" or node.get("kind") != "agent":
                continue
            key = event["context"]["run_id"], node["node_id"]
            ref = node.get("detail", {}).get("input_ref")
            task = values.get(ref["artifact_id"]) if ref else None
            if task is None:
                unavailable_repair_inputs.add(key)
                continue
            repair = task.get("repair")
            if isinstance(repair, dict) and type(repair.get("attempt")) is int and repair["attempt"] > 1:
                repaired_nodes.add(key)
        verified_segments, verified_findings, excluded_quotes, selector_inputs = 0, 0, 0, 0
        times = set()
        for identity, value in values.items():
            if "research_context" in value and "question" in value:
                times.add(value["research_context"]["as_of"])
            if "snapshot_ref" in value and "segments" in value and "read_bytes" in value:
                snapshot = snapshots[value["snapshot_ref"]["snapshot_id"]]
                raw = contents[snapshot["refs"]["text"]["artifact_id"]]
                total = 0
                for segment in value["segments"]:
                    part = raw[segment["start_byte"]:segment["end_byte"]]
                    check("sha256:" + hashlib.sha256(part).hexdigest() == segment["text_sha256"],
                          "read_segment_hash", segment["segment_id"])
                    outcome = tools.get(segment["read_action_id"], {})
                    check(outcome.get("status") == "succeeded" and outcome.get("tool", {}).get("name") == "document.read",
                          "read_action_link", segment["segment_id"])
                    total += len(part)
                    verified_segments += 1
                check(total == value["read_bytes"], "read_byte_accounting", identity)
            if {"distillation", "input_ref", "chunk_id", "validation_changes"} <= value.keys():
                task = parsed(value["input_ref"])
                segments = {s["segment_id"]: s for s in task["segments"]}
                access = parsed(value["access_ref"])
                reads = {s["segment_id"]: s for s in access["segments"]}
                snapshot = snapshots[access["snapshot_ref"]["snapshot_id"]]
                raw = contents[snapshot["refs"]["text"]["artifact_id"]]
                for segment in segments.values():
                    check(segment["text"].encode() == raw[segment["start_byte"]:segment["end_byte"]],
                          "agent_segment_bytes", segment["segment_id"])
                    read = reads.get(segment["segment_id"], {})
                    check(all(segment.get(k) == read.get(k) for k in
                              ("start_byte", "end_byte", "text_sha256", "read_action_id", "range")),
                          "agent_segment_authority", segment["segment_id"])
                bindings = {b["finding_index"]: b for b in value.get("quote_bindings", [])}
                check(len(bindings) == len(value.get("quote_bindings", [])) and
                      all(type(i) is int and 0 <= i < len(value["distillation"]["findings"]) for i in bindings),
                      "quote_binding_indices", identity)
                for index, finding in enumerate(value["distillation"]["findings"]):
                    if index in bindings:
                        try:
                            units = bound_quote_units(finding, bindings[index], segments)
                            saved = b"".join(raw[u["start_byte"]:u["end_byte"]] for u in units)
                            check(saved == finding["quote"].encode("utf-8"), "retained_cross_read_quote", identity)
                        except (EngineError, KeyError, TypeError, ValueError):
                            check(False, "retained_cross_read_quote", identity)
                        verified_findings += 1
                        continue
                    segment = segments.get(finding["segment_id"])
                    check(segment is not None and locate_quote(finding["quote"], segment["text"]) is not None,
                          "retained_quote", identity)
                    verified_findings += 1
                excluded_quotes += sum(c.get("action") == "excluded_unverified_quote" for c in value["validation_changes"])
            if {"decision", "bindings", "input_ref", "output_ref", "inventory_ref"} <= value.keys():
                task = parsed(value["input_ref"])
                selector_inputs += 1
                if hardened:
                    check("research_context" in task and "repair" in task, "selector_input_missing_defaults", identity)
                # Match this accepted selection output to its actual agent node input.
                output_hash = rows[value["output_ref"]["artifact_id"]]["sha256"]
                candidate_inputs = []
                active_input = None
                for event in events:
                    if event["kind"] == "workflow.node.started" and event["payload"].get("kind") == "agent":
                        active_input = event["payload"].get("detail", {}).get("input_ref")
                    if event["kind"] == "invocation.outcome":
                        ref = (event["payload"].get("export_receipt") or {}).get("artifact_ref")
                        if ref and rows[ref["artifact_id"]]["sha256"] == output_hash and active_input:
                            candidate_inputs.append(parsed(active_input))
                check(task in candidate_inputs, "selector_input_provenance", identity)
        results = []
        for row in db.execute("SELECT value FROM state_heads WHERE value IS NOT NULL"):
            value = json.loads(row[0])
            if not isinstance(value, dict): continue
            view = value.get("view", {})
            if view.get("method_id") != "baseline": continue
            if view.get("active"):
                raise RuntimeError("Audit only settled runs")
            sources = view.get("sources", {}).get("items", [])
            request = requests[view["run_id"]]
            result = parsed(view["result_manifest_ref"]) if view.get("result_manifest_ref") else None
            literal_queries = 0
            if result:
                check(len(sources) <= request["parameters"].get("max_sources", 20), "source_budget", view["run_id"])
                check(len(result["rounds"]) <= request["parameters"].get("max_rounds", 2), "round_budget", view["run_id"])
                if view["method_revision"] >= 11:
                    for entry in result["discovery_sets"]:
                        if entry.get("recovery_index", 0) == 0:
                            check(entry["query"] == entry["original_query"], "rewritten_primary_query", entry["discovery_id"])
                            literal_queries += 1
            citation_errors = []
            if view.get("report_ref"):
                report = contents[view["report_ref"]["artifact_id"]].decode()
                urls = {s["item_id"]: {u for u in (s["url"], s.get("provenance", {}).get("final_url")) if u} for s in sources}
                citation_errors = citation_issues(report, urls, source_urls=urls, strict=view["method_revision"] >= 11)
            results.append({"run_id": view["run_id"], "status": view["status"], "error": view.get("error"),
                "question": request["input"]["question"], "method_revision": view["method_revision"],
                "literal_primary_queries": literal_queries,
                "recording_status": view["recording_status"], "quality": view.get("quality"),
                "sources": len(sources), "successful_fetches": sum(s["status"] == "succeeded" for s in sources),
                "citation_errors": citation_errors})
        return {"store": str(root), "integrity": integrity, "foreign_key_violations": foreign_keys,
                "pending_operations": dict(pending), "verified_artifacts": len(rows), "snapshots": len(snapshots),
                "verified_segments": verified_segments, "verified_findings": verified_findings,
                "excluded_quotes": excluded_quotes, "selector_inputs": selector_inputs,
                "research_times": sorted(times), "role_repairs": len(repaired_nodes),
                "role_repair_events": kinds["workflow.role.repair"],
                "role_repair_inputs_unavailable": len(unavailable_repair_inputs),
                "quarantines": kinds["workflow.evidence.quarantined"], "event_counts": dict(kinds),
                "findings": findings, "runs": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.store)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    raise SystemExit(bool(result["findings"] or result["integrity"] != "ok" or result["foreign_key_violations"]
                         or result["pending_operations"] or any(r["citation_errors"] for r in result["runs"])))
