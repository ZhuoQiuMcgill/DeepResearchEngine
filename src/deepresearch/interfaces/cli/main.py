"""Host CLI: registered tools and applications use the same Engine boundary."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

from deepresearch.engine.contracts import EngineError, canonical_json, strict_json_loads


async def run(args):
    from deepresearch.engine.connections import Engine, EngineSettings, RunOptions, ToolRunOptions, SnapshotReadRequest
    from deepresearch.engine.contracts import RunRef, SnapshotRef
    if args.command == "baseline":
        from deepresearch.interfaces.cli.legacy_baseline import run_baseline
        await run_baseline(args.workspace, args.store, args.verify_run)
        return 0
    engine = (await Engine.open(EngineSettings(workspace=args.workspace, storage_root=args.store,
        openalex_admission=args.admit_openalex, searxng_url=args.searxng_url))).unwrap()
    try:
        if args.command in {"methods", "research"}:
            from deepresearch.bootstrap import create_research_service
            from deepresearch.workflows import ResearchRunRequest
            service = create_research_service(engine)
            try:
                if args.command == "methods":
                    value = {"schema_version": 1, "methods": service.registry.list()}
                elif args.show:
                    value = (await service.get_run(args.show)).to_dict()
                elif args.sources:
                    value = (await service.get_run(args.sources)).sources.to_dict()
                elif args.report:
                    chunks, start = [], 0
                    import base64
                    while True:
                        chunk = await service.read_report(args.report, start=start, max_bytes=65536)
                        chunks.append(base64.b64decode(chunk["data"]))
                        if chunk["eof"]:
                            break
                        start += chunk["byte_length"]
                    content = b"".join(chunks)
                    if args.output:
                        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                        Path(args.output).write_bytes(content)
                        value = {"schema_version": 1, "run_id": args.report, "output": str(Path(args.output).resolve()), "bytes": len(content)}
                    else:
                        sys.stdout.buffer.write(content)
                        return 0
                else:
                    raw = args.arguments if args.arguments is not None else sys.stdin.buffer.read(262145)
                    request = ResearchRunRequest.model_validate(strict_json_loads(raw, 262144))
                    view = await service.start_run(request)
                    while view.active:
                        await asyncio.sleep(.1)
                        view = await service.get_run(view.run_id)
                    value = view.to_dict()
                sys.stdout.buffer.write(canonical_json(value) + b"\n")
                return 0 if value.get("status", "succeeded") == "succeeded" else 2
            finally:
                cleanup = await service.close()
                if not cleanup.complete:
                    raise EngineError("CLEANUP_INCOMPLETE", "Research resources remain owned")
        if args.command == "tools":
            sys.stdout.buffer.write(canonical_json([d.to_dict() for d in engine.catalog.definitions]) + b"\n")
            return 0
        data = args.arguments if args.arguments is not None else sys.stdin.buffer.read(1048577)
        arguments = strict_json_loads(data)
        options = RunOptions(timeout_seconds=args.timeout)
        if args.source_run:
            if args.name != "document.read":
                raise ValueError("--source-run applies to document.read")
            options = ToolRunOptions(timeout_seconds=args.timeout,
                source_run_ref=RunRef(engine.storage.store_id, args.source_run),
                read_objects=(SnapshotReadRequest(SnapshotRef(**arguments["snapshot_ref"]), arguments["range"], arguments.get("max_text_bytes", 65536)),))
        from deepresearch.engine.contracts import ToolRef
        result = await engine.run_tool(ToolRef(args.name, args.revision), arguments, options)
        sys.stdout.buffer.write(canonical_json(result) + b"\n")
        return 0 if result.status == "succeeded" and result.recording.get("status") == "complete" else 2
    finally:
        cleanup = await engine.close()
        if not cleanup.complete:
            raise EngineError("CLEANUP_INCOMPLETE", "Engine resources remain owned")


def main():
    parser = argparse.ArgumentParser(prog="deepresearch")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    parser.add_argument("--store", default=None)
    parser.add_argument("--searxng-url", default="http://127.0.0.1:18888", help="Trusted self-hosted SearXNG base URL for web.search@4")
    parser.add_argument("--admit-openalex", action="store_true", help="Authorize the initial persisted anonymous local budget; existing quota state is retained")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tools", help="List registered fixed-argv tool contracts")
    commands.add_parser("methods", help="List pinned research methods and their input/parameter schemas")
    research = commands.add_parser("research", help="Run the registered research workflow or inspect saved results")
    selection = research.add_mutually_exclusive_group()
    selection.add_argument("--show", metavar="RUN_ID")
    selection.add_argument("--sources", metavar="RUN_ID")
    selection.add_argument("--report", metavar="RUN_ID")
    selection.add_argument("--arguments", help="Strict ResearchRunRequest JSON; otherwise read stdin")
    research.add_argument("--output", help="Destination for --report")
    tool = commands.add_parser("tool", help="Run a real recorded standalone tool")
    tool.add_argument("name")
    tool.add_argument("--revision", type=int, default=1, help="Exact registered tool revision")
    tool.add_argument("--arguments", help="Strict JSON arguments; otherwise read stdin")
    tool.add_argument("--timeout", type=float, default=90)
    tool.add_argument("--source-run", help="Explicit owned run containing a snapshot selected for document.read")
    baseline = commands.add_parser("baseline", help="Run the legacy single-Agent baseline; new methods use research")
    baseline.add_argument("--verify-run", help="Verify an existing saved model report without model dispatch or refetch")
    serve = commands.add_parser("serve", help="Serve the local console API with one owning Engine")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--origin", action="append", default=[], help="Explicit trusted frontend origin (repeatable)")
    args = parser.parse_args()
    if args.command == "research" and args.output and not args.report:
        parser.error("--output requires --report")
    try:
        if args.command == "serve":
            import uvicorn
            from deepresearch.engine.connections import EngineSettings
            from deepresearch.interfaces.http import create_app
            app = create_app(EngineSettings(workspace=args.workspace, storage_root=args.store,
                openalex_admission=args.admit_openalex, searxng_url=args.searxng_url), trusted_origins=tuple(args.origin))
            uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1,
                        timeout_graceful_shutdown=30, access_log=False)
            return
        raise SystemExit(asyncio.run(run(args)))
    except EngineError as error:
        sys.stderr.buffer.write(canonical_json({"schema_version": 1, "error": error.to_dict()}) + b"\n")
        raise SystemExit(2)
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
