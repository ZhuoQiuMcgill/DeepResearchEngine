"""Private one-shot CLI worker. Exit zero means prepared, never final success."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from .common import LIMITS, ToolFault, closed, encode, strict_json, validate_arguments

NAMES = {"web.search", "scholar.crossref.search", "scholar.openalex.search", "web.fetch", "document.read"}
INVOKE_KEYS = {"run_id", "root_run_id", "correlation_id", "action_id", "attempt_id", "context_kind"}
EXITS = {"validation_failed": 2, "failed": 3, "limit_exhausted": 4, "timed_out": 5, "cancelled": 6}


def registered_revision(name, revision):
    return (name in NAMES and type(revision) is int and
            (revision == 1 or name == "web.search" and revision in (2, 3, 4) or
             name == "web.fetch" and revision in (2, 3) or
             name.startswith("scholar.") and revision == 2))


def validate_request(value, tool_name, revision):
    request = closed(value, {"schema_version", "message_type", "request_id", "tool", "invocation", "arguments", "execution", "plan"})
    if request["schema_version"] != 1 or type(request["schema_version"]) is not int or request["message_type"] != "worker_request":
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Unsupported private worker envelope")
    if not isinstance(request["request_id"], str) or not 1 <= len(request["request_id"]) <= 256:
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Invalid worker request identity")
    valid_revision = registered_revision(tool_name, revision)
    if request["tool"] != {"name": tool_name, "revision": revision} or tool_name not in NAMES or not valid_revision:
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker identity does not match its registered argv")
    invocation = closed(request["invocation"], INVOKE_KEYS)
    if invocation["context_kind"] not in ("agent", "standalone_tool", "workflow") or any(not isinstance(invocation[key], str) or not 1 <= len(invocation[key]) <= 256 for key in INVOKE_KEYS - {"context_kind"}):
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Private attempt identities are invalid")
    execution = closed(request["execution"], {"deadline_utc", "limits"})
    limits = closed(execution["limits"], set(LIMITS))
    if any(type(value) is not int or value <= 0 or value > LIMITS[key] for key, value in limits.items()):
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker limits exceed registered ceilings")
    try:
        deadline = datetime.fromisoformat(execution["deadline_utc"].replace("Z", "+00:00"))
        if deadline.tzinfo is None: raise ValueError()
    except (TypeError, ValueError) as exc: raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker deadline is malformed") from exc
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0: raise ToolFault("DEADLINE_EXCEEDED", "Worker deadline expired", status="timed_out")
    arguments = validate_arguments(tool_name, request["arguments"], revision)
    plan = request["plan"]
    if not isinstance(plan, dict): raise ToolFault("WORKER_PROTOCOL_ERROR", "Worker plan is missing")
    if tool_name == "web.fetch":
        phased = revision == 3
        fields = {"kind", "operation_id", "representation", "extraction_config_ref", "normalization_version"}
        closed(plan, fields | ({'stage', 'network_grant'} if phased else set()))
        if plan["kind"] != "fetch" or plan["representation"] != ("selected_capture" if revision >= 2 else "content_decoded") or plan["normalization_version"] != "lf/1" or plan["extraction_config_ref"] not in ({'adaptive/2'} if revision == 3 else {'adaptive/1'} if revision == 2 else {'static/1'}) or not isinstance(plan["operation_id"], str):
            raise ToolFault("WORKER_PROTOCOL_ERROR", "Fetch plan is invalid")
        if phased:
            grant = closed(plan['network_grant'], {'requests', 'decoded_bytes'})
            if (plan['stage'] not in {'static', 'render'} or
                    type(grant['requests']) is not int or not 1 <= grant['requests'] <= 40 or
                    type(grant['decoded_bytes']) is not int or not 1 <= grant['decoded_bytes'] <= 32 << 20 or
                    (plan['stage'] == 'render' and arguments.get('mode', 'auto') != 'auto')):
                raise ToolFault('WORKER_PROTOCOL_ERROR', 'Invalid isolated fetch stage or residual network grant')
    elif tool_name == "document.read":
        closed(plan, {"kind", "slice"})
        if plan["kind"] != "read" or not isinstance(plan["slice"], dict): raise ToolFault("WORKER_PROTOCOL_ERROR", "Read injection is missing")
        if plan["slice"].get("snapshot_ref") != arguments["snapshot_ref"] or plan["slice"].get("requested_range") != arguments["range"]:
            raise ToolFault("WORKER_PROTOCOL_ERROR", "Read slice does not match the immutable request")
    return request, arguments, limits, min(remaining, limits["work_seconds"])


def run(request, name, revision):
    start = time.monotonic()
    request, arguments, limits, timeout = validate_request(request, name, revision)
    response = {"schema_version": 1, "message_type": "worker_response", "request_id": request["request_id"],
        "tool": request["tool"], "invocation": request["invocation"], "phase": "prepared", "prepared": None,
        "error": None, "observations": {}, "usage": {}}
    fault = None
    try:
        if name == "web.search":
            from .search import search
            prepared, observations, usage, fault = search(arguments, request["plan"], timeout, revision)
        elif name.startswith("scholar."):
            from .scholarly import discover
            expected = "crossref" if name == "scholar.crossref.search" else "openalex"
            if request["plan"].get("provider") != expected: raise ToolFault("WORKER_PROTOCOL_ERROR", "Scholarly provider mismatch")
            prepared, observations, fault = discover(arguments, request["plan"], timeout, revision)
            usage = {"http_request_count": observations["scholarly_attempt"]["http_request_count"],
                     "http_response_count": observations["scholarly_attempt"]["http_response_count"], "monetary_cost": None}
        elif name == "web.fetch":
            if revision >= 2:
                from .fetch_v2 import fetch
            else:
                from .retrieval import fetch
            prepared, observations, usage = fetch(arguments, request["plan"], limits, timeout)
        else:
            prepared, observations, usage = request["plan"]["slice"], {}, {"http_request_count": 0, "http_response_count": 0, "monetary_cost": None}
        response.update(prepared=prepared, observations=observations, usage=usage)
    except ToolFault as exc:
        fault = exc
        response["observations"] = getattr(exc, "observations", {})
        response["usage"] = getattr(exc, "usage", {})
    except Exception: fault = ToolFault("WORKER_FAILED", "Worker could not complete the registered operation")
    if fault:
        effect = "unknown"
        if name == "web.fetch" and revision in (2, 3) and fault.details.get("failure_scope") == "fetch":
            # The worker returned a settled read-only acquisition failure; its
            # HTTP observations are distinct from the parent's snapshot commit.
            if response["usage"].get("http_response_count", 0):
                effect = "observed"
            elif response["usage"].get("http_request_count") == 0:
                effect = "not_observed"
        response.update(phase="failed", prepared=None, error=fault.wire(effect))
    response["usage"]["duration_ms"] = int((time.monotonic() - start) * 1000)
    return response, EXITS.get(fault.status, 3) if fault else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[1] not in ("1", "2", "3", "4") or not registered_revision(argv[0], int(argv[1])):
        sys.stderr.write("Private worker requires registered tool identity and a bound envelope.\n")
        return 2
    try:
        raw = sys.stdin.buffer.read(LIMITS["stdin_bytes"] + 1)
        request = strict_json(raw, LIMITS["stdin_bytes"])
        response, exit_code = run(request, argv[0], int(argv[1]))
        cap = LIMITS["fetch_stdout_bytes"] if argv[0] == "web.fetch" else LIMITS["stdout_bytes"]
        try:
            output = encode(response, cap)
        except ToolFault as exc:
            response.update(phase="failed", prepared=None, error=exc.wire())
            output = encode(response, cap)
            exit_code = EXITS.get(exc.status, 3)
        sys.stdout.buffer.write(output); sys.stdout.buffer.flush()
        return exit_code
    except ToolFault:
        # Unbound/malformed input has no trusted request identity to echo.
        sys.stderr.write("Private worker rejected its envelope or output limit.\n")
        return 2
    except Exception:
        sys.stderr.write("Private worker failed before a valid response.\n")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
