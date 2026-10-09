"""Freeze and execute paired live research scenarios, retaining every failure.

Use the same OS/interpreter as the stores. No credentials enter this protocol.
Source files must stay frozen until every independent child process settles.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from threading import Lock
import time


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def freeze(workspace):
    paths = list((workspace / "src/deepresearch").rglob("*"))
    paths += [workspace / p for p in ("pyproject.toml", "uv.lock", "examples/live_research_check.py")]
    paths += list((workspace / "examples/benchmarks").glob("*.py"))
    paths += list((workspace / "examples/benchmarks").glob("*.json"))
    paths += list((workspace / "deploy/web-tools").rglob("*.yaml"))
    return {p.relative_to(workspace).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths)) if p.is_file() and "__pycache__" not in p.parts}


def verify(workspace, expected):
    changed = [name for name, digest in expected.items()
               if not (workspace / name).exists()
               or hashlib.sha256((workspace / name).read_bytes()).hexdigest() != digest]
    if changed:
        raise RuntimeError("Frozen experiment files changed: " + repr(changed))


def execute(case, output, workspace, frozen):
    verify(workspace, frozen)
    label = case["label"]
    store = output / (label + "-store")
    if store.exists():
        raise RuntimeError("Fresh store required: " + label)
    start = time.monotonic()
    print(json.dumps({"started": label}), flush=True)
    command = [sys.executable, "-X", "utf8", "examples/live_research_check.py",
               "--store", str(store), "--request", str(output / case["request"]),
               "--expected-question", case["question"], "--output", str(output / (label + "-evidence"))]
    with (output / (label + ".log")).open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=workspace, stdout=log, stderr=subprocess.STDOUT, check=False)
    view_path = output / (label + "-evidence") / "run.json"
    view = json.loads(view_path.read_text(encoding="utf-8")) if view_path.exists() else {}
    record = {"label": label, "exit_code": result.returncode,
              "wall_seconds": round(time.monotonic() - start, 3),
              "status": view.get("status", "no_final_view"), "error": view.get("error"),
              "run_id": view.get("run_id"), "quality": view.get("quality"),
              "fetch_attempts": len(view.get("sources", {}).get("items", [])),
              "fetch_successes": sum(s["status"] == "succeeded" for s in view.get("sources", {}).get("items", [])),
              "report_exists": (output / (label + "-evidence") / "report.md").exists()}
    if (store / "store.sqlite3").exists():
        audit = subprocess.run([sys.executable, "-X", "utf8", "examples/benchmarks/audit_research_store.py",
                                str(store), "--output", str(output / (label + "-audit.json"))],
                               cwd=workspace, capture_output=True, text=True, encoding="utf-8", check=False)
        record["audit_exit_code"] = audit.returncode
        (output / (label + "-audit.log")).write_text(audit.stdout + audit.stderr, encoding="utf-8")
    verify(workspace, frozen)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("examples/benchmarks/scenario-matrix.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parallel-runs", type=int, choices=(1, 2), default=2)
    parser.add_argument("--cases", nargs="+")
    args = parser.parse_args()
    workspace = Path.cwd().resolve()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError("Use a fresh experiment output directory; existing history is never overwritten")
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    selected = [case for case in suite["cases"] if not args.cases or case["id"] in args.cases]
    if not selected or (args.cases and set(args.cases) - {case["id"] for case in selected}):
        raise ValueError("Unknown or empty case selection")
    output.mkdir(parents=True)
    cases = []
    for index, case in enumerate(selected):
        models = suite["models"] if index % 2 == 0 else list(reversed(suite["models"]))
        for model in models:
            label = case["id"] + "-" + model["id"]
            request = {"schema_version": 1, "client_request_id": output.name + "-" + label,
                       "method_id": "baseline", "method_revision": suite["method_revision"],
                       "input": {"question": case["question"]},
                       "parameters": {**suite["parameters"], **case.get("parameters", {})},
                       "profile_ref": model["profile_ref"], "model_ref": model["model_ref"],
                       "timeout_seconds": 1800}
            name = label + "-request.json"
            save(output / name, request)
            cases.append({**case, "label": label, "model": model, "request": name})
    frozen = freeze(workspace)
    frozen.update({(output / c["request"]).relative_to(workspace).as_posix():
                   hashlib.sha256((output / c["request"]).read_bytes()).hexdigest() for c in cases})
    protocol = {"created_at": datetime.now(timezone.utc).isoformat(), "suite": suite,
                "parallel_runs": args.parallel_runs, "parallel_runs_per_model": 1,
                "cases": cases, "file_sha256": frozen}
    save(output / "protocol.json", protocol)
    state = {"started_at": datetime.now(timezone.utc).isoformat(), "runs": []}
    save(output / "progress.json", state)
    model_locks = {model["id"]: Lock() for model in suite["models"]}
    def locked_execute(case):
        with model_locks[case["model"]["id"]]:
            return execute(case, output, workspace, frozen)
    with ThreadPoolExecutor(max_workers=args.parallel_runs) as pool:
        pending = {pool.submit(locked_execute, case): case for case in cases}
        for future in as_completed(pending):
            try:
                record = future.result()
            except Exception as error:
                record = {"label": pending[future]["label"], "status": "harness_error",
                          "error": {"type": type(error).__name__, "message": str(error)}}
            state["runs"].append(record)
            save(output / "progress.json", state)
    try:
        verify(workspace, frozen)
    except RuntimeError as error:
        state.update(finished_at=datetime.now(timezone.utc).isoformat(), frozen_inputs_unchanged=False, invalidation=str(error))
        save(output / "progress.json", state)
        raise
    state.update(finished_at=datetime.now(timezone.utc).isoformat(), frozen_inputs_unchanged=True)
    save(output / "progress.json", state)


if __name__ == "__main__":
    main()

# Source-fidelity replays must pass before admitting a new verification batch.
