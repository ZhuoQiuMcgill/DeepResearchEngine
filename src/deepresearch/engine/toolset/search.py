"""Named DDGS engines with raw destination preservation and no merged search."""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qsl, unquote, urlsplit

from ddgs.engines.google import Google
from ddgs.engines.yahoo import Yahoo
from ddgs.results import TextResult

from .common import ToolFault, encode, prefix_utf8, url, utc_now


class RawTextResult(TextResult):
    _normalizers = {key: value for key, value in TextResult._normalizers.items() if key not in {"href", "url"}}


def yahoo_destination(raw: str) -> str:
    if "/RU=" not in raw: return url(raw)
    parsed = urlsplit(raw)
    if parsed.hostname not in {"r.search.yahoo.com", "search.yahoo.com"} or raw.count("/RU=") != 1:
        raise ToolFault("SEARCH_URL_INVALID", "Unexpected Yahoo wrapper")
    target = raw.split("/RU=", 1)[1]
    if "/RK=" not in target and "/RS=" not in target:
        raise ToolFault("SEARCH_URL_INVALID", "Yahoo wrapper has no terminator")
    target = target.split("/RK=", 1)[0].split("/RS=", 1)[0]
    # Percent decoding once; a literal + in a path segment is never a space.
    return url(unquote(target, errors="strict"))


def google_destination(raw: str) -> str:
    parsed = urlsplit(raw)
    if parsed.scheme in ("http", "https") and parsed.hostname not in {"google.com", "www.google.com"}: return url(raw)
    if parsed.path != "/url": raise ToolFault("SEARCH_URL_INVALID", "Google href is not a recognized destination")
    pairs = parse_qsl(parsed.query, keep_blank_values=True, errors="strict")
    targets = [value for key, value in pairs if key == "q"]
    if len(targets) != 1 or any(key not in {"q", "sa", "usg", "ved"} for key, _ in pairs):
        raise ToolFault("SEARCH_URL_INVALID", "Google wrapper is duplicate or ambiguous")
    return url(targets[0])


class PreservedYahoo(Yahoo):
    @property
    def result_type(self): return RawTextResult

    def post_extract_results(self, results):
        kept = []
        for result in results:
            if result.href.startswith("https://www.bing.com/aclick?"): continue
            try: result.href = yahoo_destination(result.href)
            except (ToolFault, UnicodeError): continue
            kept.append(result)
        return kept


class CorrectedGoogle(Google):
    @property
    def result_type(self): return RawTextResult

    def pre_process_html(self, html_text):
        marker = html_text.find("?>")
        return html_text[marker + 2:] if marker >= 0 else html_text

    def post_extract_results(self, results):
        kept = []
        for result in results:
            try: result.href = google_destination(result.href)
            except (ToolFault, UnicodeError): continue
            if result.title: kept.append(result)
        return kept


def search_plan() -> dict:
    return {"kind": "search", "backend_order": ["yahoo"],
        "fallback_on": ["no_results", "unavailable", "invalid_urls"], "max_backend_attempts": 1,
        "backend_settings": {"yahoo": {"timeout_seconds": 8}},
        "disabled_backends": [{"backend": "google", "reason": "URL_FIDELITY_GATE_PENDING"}]}


def search(arguments: dict, plan: dict, timeout: float):
    # No public or private unchecked flag enables the Google live gate.
    if plan != search_plan(): raise ToolFault("WORKER_PROTOCOL_ERROR", "Search plan differs from registered gated profile")
    results, attempts = [], []
    for backend in plan["backend_order"]:
        start = time.monotonic(); error = None
        try:
            engine = PreservedYahoo(timeout=max(1, min(8, int(timeout))))
            rows = engine.search(arguments["query"], page=1) or []
            seen = set()
            for row in rows:
                destination = url(row.href)
                if destination in seen: continue
                seen.add(destination)
                title, snippet = prefix_utf8(row.title, 4096), prefix_utf8(row.body, 16384)
                results.append({"rank": len(results) + 1, "title": title, "url": destination, "snippet": snippet,
                    "source_date": None, "backend": backend, "declared_provider": "bing", "discovery_only": True,
                    "truncated_fields": [key for key, shortened, original in (("title", title, row.title), ("snippet", snippet, row.body)) if shortened != original]})
                if len(results) >= arguments["max_results"]: break
            outcome = "returned" if results else "unavailable"
        except Exception:
            rows = []; outcome = "failed"
            error = {"code": "SEARCH_BACKEND_UNAVAILABLE", "message": "Named search backend did not return usable discoveries", "details": {}, "observed_effect_state": "unknown"}
        attempts.append({"backend_attempt_index": len(attempts) + 1, "backend": backend, "declared_provider": "bing",
            "outcome": outcome, "elapsed_ms": int((time.monotonic() - start) * 1000), "returned_count": len(rows),
            "kept_count": len(results), "error": error})
        if results: break
    payload = {"query": arguments["query"], "searched_at": utc_now(),
        "backend_policy": {"configured_order": ["yahoo", "google"], "active_order": plan["backend_order"], "disabled_backends": plan["disabled_backends"]},
        "backend_attempts": attempts, "results": results}
    encode(payload, 512 << 10)
    observations = {"backend_attempts": attempts, "disabled_backends": plan["disabled_backends"]}
    usage = {"search_backend_attempts": len(attempts), "http_request_count": None, "http_response_count": None, "monetary_cost": None}
    if not results:
        fault = ToolFault("SEARCH_UNAVAILABLE", "Approved backend returned no usable discovery; Google fidelity gate remains pending")
        return None, observations, usage, fault
    return payload, observations, usage, None
