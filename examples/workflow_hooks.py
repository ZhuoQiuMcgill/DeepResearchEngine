"""Register bounded observer/selection Hooks for model-free example.echo@2.

Run: uv run --locked python examples/workflow_hooks.py
No credentials, provider requests, discovery tools or HTTP server are used.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import tempfile
from typing import Any

from deepresearch.bootstrap import create_research_service
from deepresearch.engine import Engine, EngineSettings
from deepresearch.extensions import ExtensionRegistry, ExtensionSpec, HookDecision, HookEvent

from workflow_method import build_registry, close_host, run_echo


DEFAULT_MESSAGE = "First candidate\nSecond candidate\nThird candidate"
LIFECYCLE_FIELDS = {"kind", "status", "detail_sha256"}


class LifecycleObserver:
    def __init__(self, spec: ExtensionSpec):
        self.spec = spec
        self.rows: list[dict[str, Any]] = []

    async def __call__(self, event: HookEvent) -> None:
        # Identity/point are envelope fields; node payload exposes only these three facts.
        if set(event.payload) != LIFECYCLE_FIELDS:
            raise ValueError("Unexpected lifecycle hook payload")
        if len(self.rows) < self.spec.config["max_observations"]:
            self.rows.append({"node_id": event.node_id, "point": event.point,
                              **dict(event.payload)})


class KeepLastParts:
    def __init__(self, spec: ExtensionSpec):
        self.spec = spec

    async def __call__(self, event: HookEvent, candidate_ids: tuple[str, ...]) -> HookDecision:
        # Work from the current allowlist supplied by the dispatcher. Return only existing IDs.
        ordered = tuple(reversed(candidate_ids)) if self.spec.config["reverse"] else candidate_ids
        return HookDecision(keep_ids=ordered[:self.spec.config["keep"]])


def configured_hooks(keep: int = 2):
    if type(keep) is not int or not 1 <= keep <= 32:
        raise ValueError("keep must be between 1 and 32")
    registry = ExtensionRegistry()
    observer_spec = ExtensionSpec(
        extension_id="example.lifecycle", revision="v1",
        points=("node.before", "node.after", "node.failed"), mode="observe",
        timeout_seconds=0.5, config={"max_observations": 16},
    )
    selection_spec = ExtensionSpec(
        extension_id="example.selection", revision="v1",
        points=("context.select",), mode="control",
        timeout_seconds=0.5, config={"keep": keep, "reverse": True},
    )
    observer = LifecycleObserver(observer_spec)
    registry.register(observer_spec, observer)
    registry.register(selection_spec, KeepLastParts(selection_spec))
    return registry, observer


async def run_example(store: Path, message: str, *, hooks_enabled: bool = True,
                      keep: int = 2) -> dict[str, Any]:
    extensions, observer = configured_hooks(keep) if hooks_enabled else (ExtensionRegistry(), None)
    # Only bootstrap owns Engine; handlers receive immutable events and selected IDs.
    engine = (await Engine.open(EngineSettings(storage_root=store))).unwrap()
    service = None
    try:
        service = create_research_service(engine, registry=build_registry(), extensions=extensions)
        result = await run_echo(service, message)
        events = result.pop("events")
        decisions = [row for row in events if row["event"]["kind"] == "workflow.hook.decision"]
        failures = [row for row in events if row["event"]["kind"] == "workflow.hook.failed"]
        if failures:
            raise RuntimeError("An example Hook failed: " + json.dumps(failures, ensure_ascii=False))
        lines = message.splitlines() or [message]
        ids = tuple(f"part-{index:03d}" for index in range(1, len(lines) + 1))
        expected_ids = tuple(reversed(ids))[:keep] if hooks_enabled else ids
        by_id = dict(zip(ids, lines))
        if result["report"] != "\n".join(by_id[item_id] for item_id in expected_ids) + "\n":
            raise RuntimeError("Saved report differs from the validated selection")
        if hooks_enabled:
            if len(decisions) != 1 or decisions[0]["event"]["payload"]["keep_ids"] != list(expected_ids):
                raise RuntimeError("Committed selection decision is missing or mismatched")
            recorded = [row for row in events if row["event"]["kind"] == "workflow.hook.observed"]
            if not observer.rows or len(recorded) != len(observer.rows):
                raise RuntimeError("Observer acknowledgements are incomplete")
            result["observations"] = observer.rows
        else:
            if any(row["event"]["kind"].startswith("workflow.hook.") for row in events):
                raise RuntimeError("Disabled Hooks unexpectedly executed")
            result["observations"] = []
        result["selected_ids"] = list(expected_ids)
        result["extensions"] = [spec.to_dict() for spec in extensions.specs]
        result["decision_receipts"] = [row["receipt"] for row in decisions]
    finally:
        if service is None:
            cleanup = await engine.close()
            if not cleanup.complete or cleanup.errors or cleanup.unconfirmed_resources:
                raise RuntimeError("Engine cleanup is incomplete")
        else:
            cleanup = await close_host(service, engine)
    return {**result, "cleanup": cleanup}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, help="Retain a real Store; default uses an isolated temporary Store")
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--keep", type=int, choices=range(1, 33), default=2)
    parser.add_argument("--no-hooks", action="store_true", help="Run the same complete method without optional extensions")
    args = parser.parse_args()
    if args.store is None:
        with tempfile.TemporaryDirectory(prefix="deepresearch-workflow-hooks-") as directory:
            result = asyncio.run(run_example(Path(directory), args.message,
                hooks_enabled=not args.no_hooks, keep=args.keep))
    else:
        result = asyncio.run(run_example(args.store, args.message,
            hooks_enabled=not args.no_hooks, keep=args.keep))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
