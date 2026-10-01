"""Host CLI: registered tools and applications use the same Engine boundary."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

from ebd.contracts import canonical_json, strict_json_loads


async def run(args):
    from ebd.connections import Engine, EngineSettings, RunOptions, ToolRunOptions, SnapshotReadRequest
    from ebd.contracts import RunRef, SnapshotRef
    if args.command == "baseline":
        from ebd.baseline import run_baseline
        await run_baseline(args.workspace, args.store, args.verify_run)
        return 0
    engine = (await Engine.open(EngineSettings(workspace=args.workspace, storage_root=args.store,
        openalex_admission=args.admit_openalex))).unwrap()
    try:
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
        result = await engine.run_tool(args.name, arguments, options)
        sys.stdout.buffer.write(canonical_json(result) + b"\n")
        return 0 if result.status == "succeeded" and result.recording.get("status") == "complete" else 2
    finally:
        await engine.close()


def main():
    parser = argparse.ArgumentParser(prog="ebd")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    parser.add_argument("--store", default=None)
    parser.add_argument("--admit-openalex", action="store_true", help="Authorize the initial persisted anonymous local budget; existing quota state is retained")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tools", help="List registered fixed-argv tool contracts")
    tool = commands.add_parser("tool", help="Run a real recorded standalone tool")
    tool.add_argument("name")
    tool.add_argument("--arguments", help="Strict JSON arguments; otherwise read stdin")
    tool.add_argument("--timeout", type=float, default=90)
    tool.add_argument("--source-run", help="Explicit owned run containing a snapshot selected for document.read")
    baseline = commands.add_parser("baseline", help="Generate and verify the complete EBD research report")
    baseline.add_argument("--verify-run", help="Verify an existing saved model report without model dispatch or refetch")
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
