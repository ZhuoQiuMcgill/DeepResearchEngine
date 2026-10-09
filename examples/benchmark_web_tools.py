"""Model-free, fixed-corpus web benchmark using Engine workers and real Storage.

Run explicitly (makes network requests):
    uv run --locked python examples/benchmark_web_tools.py --phase all
Use --search-revision 4 --fetch-revision 2 once registered. Defaults retain 3/1.
--output is a new evidence directory; report.json is checkpointed after each URL.
For staged fetches use --case, --fetch-offset and --max-fetch with separate outputs.
No dotenv loading, providers, query rewriting or model relevance grading.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time

from deepresearch.engine.connections import Engine, EngineSettings, RunOptions
from deepresearch.engine.connections.models import (
    ArtifactReadRequest, EvidenceBinding, RunAccessOptions, RunAccessRequest, SnapshotReadRequest,
)
from deepresearch.engine.contracts import ArtifactRef, RunRef, SnapshotRef, ToolRef, digest_bytes

FIXTURE = Path(__file__).with_name("benchmarks") / "web-tools.json"
COMPONENT_CAPS = {"original": 8 << 20, "text": 4 << 20, "index": 1 << 20}
MAX_READ_PAGES = 1024  # Bounds both 200-line windows and byte continuations.


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def error_record(error):
    return error.to_dict() if hasattr(error, "to_dict") else {
        "code": type(error).__name__, "message": str(error),
    }


def select_corpus(fixture, case_ids=None):
    """Exact-URL deduplication, retaining every association and prior failure."""
    selected = set(case_ids or [case["id"] for case in fixture["cases"]])
    rows = {}
    for source in fixture["fetch_corpus"]:
        associations = [a for a in source["prior_attempts"] if a["case_id"] in selected]
        if associations:
            row = rows.setdefault(source["url"], {
                "id": source["id"], "url": source["url"], "prior_attempts": [],
            })
            row["prior_attempts"].extend(associations)
    return list(rows.values())


async def invoke(engine, name, revision, arguments, options, session=None):
    started = datetime.now(timezone.utc).isoformat()
    before = time.perf_counter()
    try:
        if session is None:
            result = await engine.run_tool(ToolRef(name, revision), arguments, options)
        else:
            result = await engine.run_workflow_tool(session, ToolRef(name, revision), arguments)
        raw = result.to_dict()
    except Exception as error:
        raw = {"status": "failed", "error": error_record(error), "result": None,
               "recording": {"status": "unavailable"}}
    return {"tool": name, "revision": revision, "arguments": arguments,
            "started_at": started, "elapsed_seconds": time.perf_counter() - before,
            "raw": raw}


async def read_artifact(engine, run_ref, ref, cap):
    request = RunAccessRequest(read_objects=(ArtifactReadRequest(ref, max_bytes=cap),))
    options = RunAccessOptions(max_total_read_bytes=cap + 65536, max_operations=256)
    session = (await engine.open_run_access(run_ref, request, options)).unwrap()
    async with session:
        handle = (await session.storage.artifacts.open(session.context, ref, max_bytes=cap)).unwrap()
        content = bytearray()
        try:
            for _ in range(cap // 65536 + 2):
                chunk = (await handle.read(session.context, 65536)).unwrap()
                content.extend(chunk.bytes)
                if len(content) > cap:
                    raise ValueError("Archived component exceeds its cap")
                if chunk.eof:
                    return bytes(content)
                if not chunk.bytes:
                    raise ValueError("Archived artifact read made no progress")
            raise ValueError("Archived artifact read page limit reached")
        finally:
            (await handle.aclose(session.context)).unwrap()


class Headings(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.parts, self.tag = [], [], None

    def handle_starttag(self, tag, attrs):
        if re.fullmatch(r"h[1-6]", tag):
            self.tag, self.parts = tag, []

    def handle_data(self, data):
        if self.tag:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.tag:
            text = " ".join("".join(self.parts).split())
            if text:
                self.rows.append({"level": int(tag[1]), "text": text})
            self.tag = None


def describe_text(text, original, provenance):
    headings = []
    if provenance.get("media_type") in {"text/html", "application/xhtml+xml"}:
        parser = Headings()
        parser.feed(original.decode(provenance.get("chosen_charset") or "utf-8", errors="replace"))
        headings = parser.rows
    flags = []
    lowered = text.lower()
    for marker in ("verify you are human", "just a moment", "access denied", "enable javascript"):
        if marker in lowered:
            flags.append("challenge_marker:" + marker)
    if len(text.strip()) < 500:
        flags.append("short_text_under_500_characters")
    return {"classification": provenance.get("classification"), "text_characters": len(text),
            "text_bytes": len(text.encode("utf-8")), "word_count": len(text.split()),
            "raw_html_headings": headings, "raw_html_heading_count": len(headings),
            "extracted_text_heading_lines": [line for line in text.splitlines()
                                             if re.match(r"^#{1,6}\s+", line)],
            "review_flags": flags, "usable_evidence": None, "human_review_required": True,
            "note": "Headings describe original HTML or explicit Markdown markers; flags and size do not establish relevance or evidence quality."}


async def verify_fetch(engine, raw, directory, timeout=90, page_bytes=65536):
    """Verify all three archived components and the entire document.read stream."""
    directory.mkdir(parents=True, exist_ok=True)
    report = {"components": {}, "reads": [], "errors": [], "archive_verified": False,
              "full_text_read": False, "ready_for_human_review": False}
    payload = raw.get("result") or {}
    receipt = (raw.get("persistence") or {}).get("receipt") or {}
    try:
        run_ref = RunRef(engine.storage.store_id, raw["invocation"]["run_id"])
        snapshot = SnapshotRef(**payload["snapshot_ref"])
        if receipt["snapshot_ref"] != payload["snapshot_ref"]:
            raise ValueError("Fetch result and commit receipt snapshot identities differ")
    except Exception as error:
        report["errors"].append(error_record(error))
        return report
    provenance = payload.get("provenance") or {}
    components = {}
    for role, cap in COMPONENT_CAPS.items():
        try:
            ref = ArtifactRef(**receipt[role + "_ref"])
            data = await read_artifact(engine, run_ref, ref, cap)
            components[role] = data
            filename = role + {"original": ".bin", "text": ".txt", "index": ".json"}[role]
            (directory / filename).write_bytes(data)
            observed = digest_bytes(data)
            verified = (observed == receipt["component_digests"][role]
                        == provenance.get(role + "_sha256")
                        and len(data) == provenance.get(role + "_bytes"))
            report["components"][role] = {"ref": ref.to_dict(), "sha256": observed,
                "byte_length": len(data), "verified": verified, "file": filename}
            if not verified:
                raise ValueError(role + " archive hash/length mismatch")
        except Exception as error:
            report["errors"].append({"component": role, **error_record(error)})
    report["archive_verified"] = all(report["components"].get(role, {}).get("verified")
                                      for role in COMPONENT_CAPS)
    assembled, seen = bytearray(), set()
    line_count = payload["line_count"]
    interval = {"kind": "lines", "start": 1, "end_exclusive": min(201, line_count + 1)}
    continuation = None
    session = None
    try:
        # Standalone calls create fresh grants, invalidating authority-bound
        # cursors. One model-free Engine session preserves read authority.
        session = (await engine.open_workflow_session(tools=(ToolRef("document.read", 1),),
            options=RunOptions(timeout_seconds=timeout))).unwrap()
        full_range = {"kind": "lines", "start": 1, "end_exclusive": line_count + 1}
        (await engine.bind_evidence(session, run_ref, EvidenceBinding(read_objects=(
            SnapshotReadRequest(snapshot, full_range, max_text_bytes=page_bytes),)))).unwrap()
        report["read_run_id"] = session.context.run_id
        for index in range(MAX_READ_PAGES):
            arguments = {"snapshot_ref": snapshot.to_dict(), "range": interval, "max_text_bytes": page_bytes}
            if continuation:
                arguments["continuation"] = continuation
            call = await invoke(engine, "document.read", 1, arguments, None, session)
            filename = f"read-{index + 1:04}.json"
            write_json(directory / filename, call)
            outcome = call["raw"]
            report["reads"].append({"file": filename, "elapsed_seconds": call["elapsed_seconds"],
                "status": outcome["status"], "error": outcome.get("error"),
                "invocation": outcome.get("invocation"), "recording": outcome.get("recording")})
            if outcome["status"] != "succeeded" or outcome.get("recording", {}).get("status") != "complete":
                raise ValueError("document.read failed or recording incomplete; see retained call")
            page = outcome["result"]
            chunk = page["text"].encode("utf-8")
            if len(chunk) != page["byte_length"] or page["snapshot_ref"] != snapshot.to_dict():
                raise ValueError("document.read byte length or snapshot identity mismatch")
            # A line range excludes its final delimiter. Overlap its last line
            # in the next window, using authoritative byte spans to verify and
            # remove duplicates without inventing the missing newline.
            offset = 0
            for span in page["spans"]:
                start, end = span["start_byte"], span["end_byte"]
                if not 0 <= start <= end or start > len(assembled):
                    raise ValueError("document.read has a byte gap or invalid span")
                segment = chunk[offset:offset + end - start]
                overlap = min(len(assembled), end) - start
                if len(segment) != end - start or assembled[start:start + overlap] != segment[:overlap]:
                    raise ValueError("document.read overlap differs from earlier bytes")
                assembled.extend(segment[overlap:])
                offset += len(segment)
            if offset != len(chunk):
                raise ValueError("document.read spans do not cover the returned text")
            if len(assembled) > COMPONENT_CAPS["text"]:
                raise ValueError("document.read exceeds text cap")
            continuation = page.get("continuation")
            if not continuation:
                if page["has_more_in_requested_range"] or page["truncated"]:
                    raise ValueError("document.read ended before its requested range was delivered")
                if interval["end_exclusive"] <= line_count:
                    start = interval["end_exclusive"] - 1
                    interval = {"kind": "lines", "start": start, "end_exclusive": min(start + 200, line_count + 1)}
                    continue
                if page["has_more_in_document"]:
                    raise ValueError("document.read ended before full archive was delivered")
                text_bytes = bytes(assembled)
                report["read_sha256"] = digest_bytes(text_bytes)
                report["read_bytes"] = len(text_bytes)
                report["full_text_read"] = (text_bytes == components.get("text")
                    and report["read_sha256"] == provenance.get("text_sha256"))
                if not report["full_text_read"]:
                    raise ValueError("Full document.read text differs from archived text")
                break
            if not chunk or continuation in seen:
                raise ValueError("document.read continuation made no progress")
            seen.add(continuation)
        else:
            raise ValueError("document.read page limit reached")
    except Exception as error:
        report["errors"].append(error_record(error))
    finally:
        if session is not None:
            await session.close()
    if "text" in components:
        try:
            report["content"] = describe_text(components["text"].decode("utf-8"),
                                               components.get("original", b""), provenance)
        except Exception as error:
            report["errors"].append(error_record(error))
    report["ready_for_human_review"] = bool(report["archive_verified"] and report["full_text_read"]
        and raw.get("recording", {}).get("status") == "complete"
        and raw.get("persistence", {}).get("commit_state") == "committed" and not report["errors"])
    return report


async def benchmark(engine, args, fixture, output):
    cases = [case for case in fixture["cases"] if not args.case or case["id"] in args.case]
    corpus = select_corpus(fixture, [case["id"] for case in cases])
    batch = corpus[args.fetch_offset:]
    if args.max_fetch is not None:
        batch = batch[:args.max_fetch]
    report = {"schema_version": 1, "model_calls": 0, "started_at": datetime.now(timezone.utc).isoformat(),
        "fixture_sha256": digest_bytes(FIXTURE.read_bytes()), "corpus_id": fixture["corpus_id"],
        "configuration": vars(args), "cases": cases, "searches": [], "fetches": [],
        "selected_unique_urls": len(corpus), "selected_historical_attempts": sum(len(r["prior_attempts"]) for r in corpus),
        "planned_fetch_ids": [r["id"] for r in batch] if args.phase != "search" else [],
        "unattempted_fetch_ids": [r["id"] for r in corpus], "status": "running",
        "quality_note": "Transport success and read readiness do not establish usable evidence; review content using the case cues."}

    def checkpoint():
        write_json(output / "report.json", report)

    checkpoint()
    try:
        if args.phase in {"search", "all"}:
            for case in cases:
                call = await invoke(engine, "web.search", args.search_revision,
                    {"query": case["question"], "max_results": args.max_results}, RunOptions(timeout_seconds=args.timeout))
                payload = call["raw"].get("result") or {}
                report["searches"].append({"case_id": case["id"], **call,
                    "searched_at": payload.get("searched_at"), "result_count": len(payload.get("results", [])) if payload else None,
                    "query_matches": payload.get("query") == case["question"] if payload else None})
                checkpoint()  # Raw results retain complete links, snippets, coverage and backend diagnostics.
        if args.phase in {"fetch", "all"}:
            for source in batch:
                call = await invoke(engine, "web.fetch", args.fetch_revision,
                    {"url": source["url"]}, RunOptions(timeout_seconds=args.timeout))
                row = {**source, **call, "verification": None}
                report["fetches"].append(row)
                report["unattempted_fetch_ids"].remove(source["id"])
                checkpoint()  # A verification failure must never erase the fetch result.
                if call["raw"]["status"] == "succeeded":
                    try:
                        row["verification"] = await verify_fetch(engine, call["raw"], output / source["id"], args.timeout)
                    except Exception as error:
                        row["verification"] = {"ready_for_human_review": False, "errors": [error_record(error)]}
                checkpoint()
        report["status"] = "completed"
    finally:
        report["fetch_status_counts"] = dict(Counter(r["raw"]["status"] for r in report["fetches"]))
        report["ready_for_human_review_count"] = sum(bool((r["verification"] or {}).get("ready_for_human_review"))
                                                    for r in report["fetches"])
        checkpoint()
    return report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-revision", type=int, default=3)
    parser.add_argument("--fetch-revision", type=int, default=1)
    parser.add_argument("--phase", choices=("search", "fetch", "all"), default="all")
    parser.add_argument("--case", action="append", choices=("headsets", "flights", "sleep"))
    parser.add_argument("--max-fetch", type=int)
    parser.add_argument("--fetch-offset", type=int, default=0)
    parser.add_argument("--max-results", type=int, choices=range(1, 11), default=10)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--store", default="local/web-tool-benchmark/store")
    parser.add_argument("--output", default="local/web-tool-benchmark/evidence")
    args = parser.parse_args(argv)
    if min(args.search_revision, args.fetch_revision, args.timeout) < 1 or args.timeout > 1800:
        parser.error("revisions must be positive and timeout must be 1..1800 seconds")
    if args.fetch_offset < 0 or (args.max_fetch is not None and args.max_fetch < 0):
        parser.error("fetch offset and maximum must be nonnegative")
    return args


async def main(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use a new/empty --output directory to preserve previous evidence")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    engine = (await Engine.open(EngineSettings(storage_root=args.store))).unwrap()
    try:
        report = await benchmark(engine, args, fixture, output)
        print(json.dumps({"report": str(output / "report.json"), "status": report["status"],
            "fetch_status_counts": report["fetch_status_counts"],
            "ready_for_human_review_count": report["ready_for_human_review_count"]}))
    finally:
        write_json(output / "cleanup.json", (await engine.close()).to_dict())


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
