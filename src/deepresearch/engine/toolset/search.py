"""Named DDGS engines with raw destination preservation and no merged search."""
from __future__ import annotations

import math
import time
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

from ddgs.engines.duckduckgo import Duckduckgo
from ddgs.engines.google import Google
from ddgs.engines.yahoo import Yahoo
from ddgs.results import TextResult

from .common import ToolFault, digest, encode, prefix_utf8, url, utc_now


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
            if advertising_url(result.href): continue
            kept.append(result)
        return kept


def advertising_url(destination: str) -> bool:
    parsed = urlsplit(destination)
    return ((parsed.hostname in {"www.bing.com", "bing.com"} and parsed.path == "/aclick") or
            (parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"} and parsed.path == "/y.js"))


def duckduckgo_destination(raw: str) -> str:
    parsed = urlsplit(raw)
    if parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com"} and parsed.path == "/l/":
        targets = [value for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key == "uddg"]
        if len(targets) != 1:
            raise ToolFault("SEARCH_URL_INVALID", "DuckDuckGo wrapper is ambiguous")
        return url(targets[0])
    if raw.startswith("//duckduckgo.com/l/"):
        return duckduckgo_destination("https:" + raw)
    return url(raw)


class PreservedDuckduckgo(Duckduckgo):
    @property
    def result_type(self): return RawTextResult

    def post_extract_results(self, results):
        kept = []
        for result in results:
            try: result.href = duckduckgo_destination(result.href)
            except (ToolFault, UnicodeError): continue
            if result.title and not advertising_url(result.href): kept.append(result)
        return kept


def preserves_query(target, backend, host, query):
    """Allow the fixed search host and Yahoo's bounded verification wrapper."""
    parsed = urlsplit(target)
    if parsed.scheme != "https" or parsed.hostname != host:
        return False
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    key = "p" if backend == "yahoo" else "q"
    values = [value for name,value in pairs if name == key]
    if backend == "yahoo" and parsed.path == "/_bv/v.gif":
        originals = [value for name,value in pairs if name == "orig"]
        if len(originals) == 1:
            original = urlsplit(urljoin(target, originals[0]))
            return (original.scheme == "https" and original.hostname == host and
                    [value for name,value in parse_qsl(original.query) if name == key] == [query])
        return False
    return values == [query]


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


def search_plan(revision=1) -> dict:
    if revision == 2:
        return {"kind": "search", "backend_order": ["yahoo", "duckduckgo"],
            "fallback_on": ["no_results", "unavailable", "invalid_urls"], "max_backend_attempts": 2,
            "backend_settings": {name:{"timeout_seconds":8,"max_redirects":2,"max_http_requests":3}
                                 for name in ("yahoo","duckduckgo")},
            "disabled_backends": [{"backend": "google", "reason": "URL_FIDELITY_GATE_PENDING"}]}
    return {"kind": "search", "backend_order": ["yahoo"],
        "fallback_on": ["no_results", "unavailable", "invalid_urls"], "max_backend_attempts": 1,
        "backend_settings": {"yahoo": {"timeout_seconds": 8}},
        "disabled_backends": [{"backend": "google", "reason": "URL_FIDELITY_GATE_PENDING"}]}


def search(arguments: dict, plan: dict, timeout: float, revision=1):
    if revision == 2:
        return observed_search(arguments, plan, timeout)
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


def observed_search(arguments: dict, plan: dict, timeout: float):
    """Explicit, bounded backends; preserve literal queries and diagnostic facts."""
    if plan != search_plan(2):
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Search plan differs from registered revision 2")
    deadline = time.monotonic() + timeout
    attempts, results = [], []
    for backend in plan["backend_order"]:
        remaining = deadline - time.monotonic()
        if remaining < 1:
            break
        engine_type = PreservedYahoo if backend == "yahoo" else PreservedDuckduckgo
        engine = engine_type(timeout=max(1, min(8, math.floor(remaining))))
        started = time.monotonic()
        observation = {"backend_attempt_index":len(attempts) + 1, "backend":backend,"declared_provider":"bing",
            "outcome":"unavailable","elapsed_ms":0,"returned_count":0,"kept_count":0,"error":None,
            "http_status":None,"http_request_count":0,"http_response_count":0,
            "response_bytes":None,"response_sha256":None,"extracted_count":0,
            "rejected_url_count":0,"advertisement_count":0,"failure_reason":None,"redirects":[]}
        original_request = engine.request
        def request(method, source, **kwargs):
            for hop in range(3):
                left = min(deadline, started + 8) - time.monotonic()
                if left <= 0:
                    raise ToolFault("DEADLINE_EXCEEDED", "Search backend deadline expired")
                observation["http_request_count"] += 1
                response = engine.http_client.client.request(method, source, follow_redirects=False, timeout=left, **kwargs)
                observation["http_response_count"] += 1
                observation["http_status"] = response.status_code
                text = response.text
                raw = response.content
                observation["response_bytes"], observation["response_sha256"] = len(raw), digest(raw)
                # The client receives the body before this parser cap; process
                # memory and the shared deadline also bound that transport stage.
                if len(raw) > 1 << 20:
                    raise ToolFault("SEARCH_RESPONSE_LIMIT", "Search HTML exceeds the parser byte cap")
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location or hop == 2:
                        observation["failure_reason"] = "redirect_limit"
                        return None
                    target = url(urljoin(source, location))
                    if not preserves_query(target,backend,urlsplit(engine.search_url).hostname,arguments["query"]):
                        observation["failure_reason"] = "redirect_denied"
                        return None
                    observation["redirects"].append({"from_url":source,"to_url":target,"http_status":response.status_code})
                    source = target
                    if response.status_code == 303:
                        method = "GET"
                        kwargs = {}
                    elif method == "GET":
                        kwargs = {}
                    continue
                if response.status_code != 200:
                    observation["failure_reason"] = "http_rate_limited" if response.status_code == 429 else "http_challenge" if response.status_code == 202 else "http_error"
                    return None
                return text
        engine.request = request
        phase = "transport"
        try:
            # Read raw candidates first, so post-extraction rejection is visible.
            params = engine.build_payload(arguments["query"], "us-en", "moderate", None, page=1)
            html = engine.request(engine.search_method, engine.search_url,
                **{"params" if engine.search_method == "GET" else "data":params})
            phase = "parser"
            raw_rows = engine.extract_results(html) if html else []
            observation["extracted_count"] = len(raw_rows)
            seen = set()
            for row in raw_rows:
                if len(row.href.encode("utf-8")) > 8192:
                    observation["rejected_url_count"] += 1
                    continue
                try:
                    destination = yahoo_destination(row.href) if backend == "yahoo" else duckduckgo_destination(row.href)
                except (ToolFault, UnicodeError, ValueError):
                    observation["rejected_url_count"] += 1
                    continue
                if advertising_url(destination):
                    observation["advertisement_count"] += 1
                    continue
                if not row.title or destination in seen:
                    continue
                seen.add(destination)
                observation["returned_count"] += 1
                if len(results) >= arguments["max_results"]:
                    continue
                title, snippet = prefix_utf8(row.title, 4096), prefix_utf8(row.body, 16384)
                results.append({"rank":len(results) + 1,"title":title,"url":destination,"raw_url":row.href,"snippet":snippet,
                    "source_date":None,"backend":backend,"declared_provider":"bing","discovery_only":True,
                    "truncated_fields":[key for key, short, original in (("title",title,row.title),("snippet",snippet,row.body)) if short != original]})
            observation["kept_count"] = len(results)
            if results:
                observation["outcome"] = "returned"
            elif observation["failure_reason"] is None:
                lower = (html or "").lower()
                observation["failure_reason"] = ("no_results" if any(marker in lower for marker in
                    ("no results found", "we did not find results", "no results.", "no results for")) else
                    "all_candidates_rejected" if raw_rows else "parser_no_matches")
        except Exception as error:
            results.clear()
            observation["outcome"] = "failed"
            observation["failure_reason"] = ("response_limit" if isinstance(error, ToolFault) and error.code == "SEARCH_RESPONSE_LIMIT" else
                "backend_deadline" if isinstance(error, ToolFault) and error.code == "DEADLINE_EXCEEDED" else
                "transport_error" if phase == "transport" else "parser_error")
            observation["error"] = {"code":"SEARCH_BACKEND_UNAVAILABLE","message":"Named search backend did not return usable discoveries",
                "details":{},"observed_effect_state":"unknown"}
        finally:
            engine.request = original_request
        observation["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        attempts.append(observation)
        if results:
            break
    payload = {"query":arguments["query"],"searched_at":utc_now(),
        "backend_policy":{"configured_order":["yahoo","duckduckgo","google"],"active_order":plan["backend_order"],
            "disabled_backends":plan["disabled_backends"]},"backend_attempts":attempts,"results":results}
    observations = {"backend_attempts":attempts,"disabled_backends":plan["disabled_backends"]}
    usage = {"search_backend_attempts":len(attempts),"http_request_count":sum(row["http_request_count"] for row in attempts),
        "http_response_count":sum(row["http_response_count"] for row in attempts),"monetary_cost":None}
    try:
        encode(payload, 512 << 10)
    except ToolFault as fault:
        return None, observations, usage, fault
    if not results:
        return None, observations, usage, ToolFault("SEARCH_UNAVAILABLE", "Named backends returned no usable discovery; inspect backend_attempts")
    return payload, observations, usage, None
