"""Separate metadata discoveries and parent-only provider limit accounting."""
from __future__ import annotations

import asyncio
import calendar
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from .common import LIMITS, ToolFault, closed, encode, strict_json, url, utc_now
from .retrieval import request_body
from .discovery_metadata import bibliography, coverage, extend_scholarly_schema, retain_valid_locations

SCHEMA = json.loads(Path(__file__).with_name("scholarly.schema.json").read_text(encoding="utf-8"))
extend_scholarly_schema(SCHEMA["$defs"])
HEADERS = {
    "crossref_rate_limit": "x-rate-limit-limit", "crossref_rate_interval": "x-rate-limit-interval",
    "crossref_concurrency_limit": "x-concurrency-limit", "openalex_limit_usd": "x-ratelimit-limit-usd",
    "openalex_remaining_usd": "x-ratelimit-remaining-usd", "openalex_cost_usd": "x-ratelimit-cost-usd",
    "openalex_limit_credits": "x-ratelimit-limit", "openalex_remaining_credits": "x-ratelimit-remaining",
    "openalex_cost_credits": "x-ratelimit-credits-used", "openalex_reset_seconds": "x-ratelimit-reset",
    "retry_after": "retry-after"}
MAX_EXACT = 2**53 - 1


def validate_schema(value, name):
    schema = {"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors: raise ToolFault("WORKER_PROTOCOL_ERROR", "Scholarly record does not match its closed schema")
    def byte_limits(node, spec):
        if "$ref" in spec: spec = SCHEMA["$defs"][spec["$ref"].rsplit("/", 1)[1]]
        if isinstance(node, str) and len(node.encode("utf-8")) > spec.get("maxLength", 1 << 20):
            raise ToolFault("SCHOLAR_RESPONSE_LIMIT", "Scholarly field exceeds its UTF-8 byte cap", status="limit_exhausted")
        if isinstance(node, dict):
            for key, item in node.items(): byte_limits(item, spec.get("properties", {}).get(key, {}))
        elif isinstance(node, list):
            for item in node: byte_limits(item, spec.get("items", {}))
    byte_limits(value, schema)
    encode(value, 512 << 10)


def provider_plan(provider: str, reservation_id: str | None) -> dict:
    crossref = provider == "crossref"
    return {"kind": "scholarly", "provider": provider,
        "endpoint_id": "crossref_works_public" if crossref else "openalex_works_anonymous",
        "query_parameter": "query.bibliographic" if crossref else "search",
        "count_parameter": "rows" if crossref else "per-page", "request_method": "GET",
        "max_http_requests": 1, "follow_redirects": False,
        "max_response_transfer_bytes": 1 << 20, "max_response_decoded_bytes": 1 << 20,
        "max_response_json_depth": 32, "max_metadata_duration_ms": 30000,
        "max_encoded_request_url_bytes": 16384 if crossref else 4094,
        "quota_reservation_id": reservation_id}


def request_url(provider: str, arguments: dict) -> str:
    base = "https://api.crossref.org/works" if provider == "crossref" else "https://api.openalex.org/works"
    params = {"query.bibliographic" if provider == "crossref" else "search": arguments["query"],
              "rows" if provider == "crossref" else "per-page": arguments["max_results"]}
    result = str(httpx.URL(base, params=params))
    if len(result.encode()) > (16384 if provider == "crossref" else 4094):
        raise ToolFault("INVALID_ARGUMENT", "Encoded scholarly URL exceeds provider cap", status="validation_failed")
    if parse_qs(urlsplit(result).query) != {key: [str(value)] for key, value in params.items()}:
        raise ToolFault("INVALID_ARGUMENT", "Literal query did not round-trip through URL encoding", status="validation_failed")
    return result


def applicable(provider: str) -> list[str]:
    return [key for key in HEADERS if key.startswith(provider + "_") or key == "retry_after"]


def capture_limits(provider, entries):
    result = dict.fromkeys(HEADERS)
    for field in applicable(provider):
        values = [value for key, value in entries if key.decode("ascii", "ignore").lower() == HEADERS[field]]
        if not values: continue
        raw = values[0]
        if len(values) != 1 or not raw or len(raw) > 128 or any(byte < 32 or byte > 126 for byte in raw):
            result[field] = {"capture": "invalid", "raw": None}
        else: result[field] = {"capture": "single", "raw": raw.decode("ascii")}
    encode(result, 8192)
    return result


def parse_limits(provider: str, captures: dict, received: datetime | None = None) -> dict:
    validate_schema(captures, "worker_provider_limits")
    allowed = applicable(provider)
    if any(value is not None for key, value in captures.items() if key not in allowed):
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Cross-provider limit capture is forbidden")
    received = received or datetime.now(timezone.utc)
    out = dict.fromkeys(SCHEMA["$defs"]["provider_limit_observation"]["required"])
    out["missing_fields"], out["invalid_fields"] = [], []
    mapping = {"crossref_rate_limit": "rate_limit_requests", "crossref_rate_interval": "rate_interval_ms",
        "crossref_concurrency_limit": "concurrency_limit", "openalex_limit_usd": "budget_limit_microusd",
        "openalex_remaining_usd": "remaining_microusd", "openalex_cost_usd": "cost_microusd",
        "openalex_limit_credits": "credit_limit", "openalex_remaining_credits": "remaining_credits",
        "openalex_cost_credits": "cost_credits", "openalex_reset_seconds": "reset_after_seconds", "retry_after": "retry_after_seconds"}
    def number(raw):
        if not re.fullmatch(r"0|[1-9][0-9]*", raw): raise ValueError()
        value = int(raw)
        if value > MAX_EXACT: raise ValueError()
        return value
    for key in allowed:
        capture = captures[key]
        if capture is None: out["missing_fields"].append(key); continue
        if capture["capture"] == "invalid": out["invalid_fields"].append(key); continue
        raw = capture["raw"].strip(" ")
        try:
            if key == "crossref_rate_interval":
                if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,3})?s", raw): raise ValueError()
                value = int(Decimal(raw[:-1]) * 1000)
                if not 0 < value <= 172800000: raise ValueError()
            elif key.endswith("_usd"):
                if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?", raw): raise ValueError()
                value = int(Decimal(raw) * 1000000)
                if value > MAX_EXACT: raise ValueError()
            elif key == "retry_after" and not re.fullmatch(r"0|[1-9][0-9]*", raw):
                if not re.fullmatch(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), [0-9]{2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT", raw): raise ValueError()
                when = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
                if when.strftime("%a, %d %b %Y %H:%M:%S GMT") != raw: raise ValueError()
                value = max(0, math.ceil((when - received).total_seconds()))
                if value > 172800: raise ValueError()
            else:
                value = number(raw)
                if key in ("retry_after", "openalex_reset_seconds") and value > 172800: raise ValueError()
            out[mapping[key]] = value
        except (ValueError, OverflowError): out["invalid_fields"].append(key)
    if any(out[field] is not None for field in ("budget_limit_microusd", "remaining_microusd", "cost_microusd")): out["currency"] = "USD"
    if any(out[field] is not None for field in ("credit_limit", "remaining_credits", "cost_credits")): out["credit_unit"] = "openalex_credit"
    if out["reset_after_seconds"] is not None: out["reset_at"] = (received + timedelta(seconds=out["reset_after_seconds"])).isoformat()
    validate_schema(out, "provider_limit_observation")
    return out


def _location(source):
    if source is None: return None
    if not isinstance(source, dict): raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Invalid OpenAlex location")
    host = source.get("source")
    if host is not None:
        host = {"source_id": host.get("id"), "display_name": host.get("display_name"), "source_type": host.get("type"),
            "host_organization_id": host.get("host_organization"), "host_organization_name": host.get("host_organization_name"), "is_oa": host.get("is_oa")}
    return {"location_id": source.get("id"), "landing_page_url": source.get("landing_page_url"), "pdf_url": source.get("pdf_url"),
            "is_oa": source.get("is_oa"), "version": source.get("version"), "license": source.get("license"), "source": host}


def project(provider: str, source: dict, arguments: dict, revision=1) -> dict:
    if provider == "crossref":
        if source.get("status") != "ok" or not isinstance(source.get("message"), dict):
            raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Crossref response lacks its expected message")
        message = source["message"]; rows = message.get("items")
        total = message.get("total-results")
    else: rows, total = source.get("results"), source.get("meta", {}).get("count")
    if not isinstance(rows, list) or len(rows) > arguments["max_results"]:
        raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Scholarly result count is invalid")
    results = []
    for rank, row in enumerate(rows, 1):
        if not isinstance(row, dict): raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Scholarly row is not an object")
        if provider == "crossref":
            dates = row.get("published", {}).get("date-parts")
            for date in dates or []:
                if not isinstance(date, list) or not 1 <= len(date) <= 3 or any(type(n) is not int for n in date): raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Invalid published date parts")
                year = date[0]
                if not 1 <= year <= 9999 or len(date) >= 2 and not 1 <= date[1] <= 12 or len(date) == 3 and not 1 <= date[2] <= calendar.monthrange(year, date[1])[1]:
                    raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Invalid publication calendar date")
            links = [{"url": item.get("URL"), "content_type": item.get("content-type"), "content_version": item.get("content-version"), "intended_application": item.get("intended-application")} for item in row.get("link", [])]
            results.append({"rank": rank, "titles": row.get("title", []), "doi": row.get("DOI"), "doi_url": row.get("URL"),
                "member_id": row.get("member"), "publisher": row.get("publisher"), "work_type": row.get("type"), "published_date_parts": dates, "links": links})
        else:
            access = row.get("open_access")
            access = {key: access.get(key) for key in ("is_oa", "oa_status", "oa_url")} if isinstance(access, dict) else {"is_oa": None, "oa_status": None, "oa_url": None}
            results.append({"rank": rank, "work_id": row.get("id"), "title": row.get("title"), "doi_url": row.get("doi"),
                "publication_year": row.get("publication_year"), "open_access": access, "primary_location": _location(row.get("primary_location")),
                "best_oa_location": _location(row.get("best_oa_location")), "locations": [_location(item) for item in row.get("locations", [])]})
    result = {"provider": provider, "scope": "scholarly_metadata", "query": arguments["query"], "searched_at": utc_now(),
        "discovery_only": True, "provider_total_results": total, "results": results}
    try:
        metadata = []
        if revision == 2:
            for item, row in zip(results, rows):
                detail = bibliography(provider, row)
                detail["invalid_fields"] = sorted(set(detail["invalid_fields"] + retain_valid_locations(item)))
                metadata.append(detail)
        validate_schema(result, provider + "_result")
        if revision == 2:
            for item, detail in zip(results, metadata):
                item["bibliography"] = detail
            result["coverage"] = coverage(arguments["max_results"], len(results), len(rows), total)
            validate_schema(result, provider + "_result_v2")
    except ToolFault as exc:
        raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Provider metadata does not match the closed projection") from exc
    def check_urls(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if item is not None and (key.endswith("_url") or key == "url"): url(item)
                check_urls(item)
        elif isinstance(value, list):
            for item in value: check_urls(item)
    try:
        check_urls(result)
    except ToolFault as exc:
        # A returned metadata field is provider data, not the caller's request
        # or an uncertain transport outcome. Legacy projections remain strict.
        raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Provider metadata contains an invalid URL") from exc
    for item in results:
        if provider == "openalex" and (not isinstance(item["work_id"], str) or not re.fullmatch(r"https://openalex.org/W[0-9]+", item["work_id"])):
            raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Invalid OpenAlex work identifier")
        if provider == "crossref" and item["doi"] is not None and not re.fullmatch(r"10\.[0-9]{4,9}/\S+", item["doi"], re.I):
            raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Invalid DOI identity")
    return result


def discover(arguments: dict, plan: dict, timeout: float, revision=1):
    provider = plan["provider"]
    if plan != provider_plan(provider, plan.get("quota_reservation_id")):
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Scholarly provider plan does not match fixed registration")
    start = time.monotonic(); info = {}; captures = dict.fromkeys(HEADERS)
    def headers(received, raw):
        nonlocal info
        info = received
        captures.update(capture_limits(provider, raw))
    fault, prepared = None, None
    try:
        body, observed, _ = request_body(request_url(provider, arguments), cap=LIMITS["metadata_bytes"],
            timeout=min(30, timeout), redirects=0, metadata=True, on_headers=headers)
        info.update(observed)
        status = info["http_status"]
        if status != 200:
            mapping = {403: ("SCHOLAR_HTTP_FORBIDDEN", "http_forbidden", "failed"), 429: ("SCHOLAR_RATE_LIMITED", "rate_limited", "limit_exhausted"),
                       401: ("SCHOLAR_AUTH_UNSUPPORTED", "auth_required", "failed")}
            code, reason, terminal = mapping.get(status, ("SCHOLAR_UNEXPECTED_REDIRECT", "unexpected_redirect", "failed") if 300 <= status < 400 else ("SCHOLAR_HTTP_ERROR", "http_error", "failed"))
            fault = ToolFault(code, "Metadata endpoint returned a non-success HTTP status", status=terminal, details={"reason": reason})
        else:
            if "json" not in info["content_type"].split(";")[0].lower(): raise ToolFault("SCHOLAR_PROTOCOL_ERROR", "Metadata endpoint did not return JSON")
            prepared = project(provider, strict_json(body, LIMITS["metadata_bytes"]), arguments, revision)
    except ToolFault as exc:
        fault = exc
        if fault.code == "INVALID_JSON":
            fault = ToolFault("SCHOLAR_PROTOCOL_ERROR", "Metadata response is not strict finite JSON")
        if exc.details.get("http_status") is not None: info.update(exc.details)
    except Exception:
        fault = ToolFault("SCHOLAR_UNAVAILABLE", "Metadata endpoint is unavailable")
    attempt = {"provider": provider, "endpoint_id": plan["endpoint_id"], "http_request_count": info.get("http_request_count"),
        "http_response_count": info.get("http_response_count"), "http_status": info.get("http_status"),
        "response_transfer_bytes": info.get("response_transfer_bytes"), "response_decoded_bytes": info.get("response_decoded_bytes"),
        "duration_ms": int((time.monotonic() - start) * 1000)}
    observations = {"scholarly_attempt": attempt, "provider_limits": captures}
    validate_schema(observations, "worker_scholarly_observations")
    if fault:
        details = {"provider": provider, "http_status": attempt["http_status"], "reason": fault.details.get("reason", "response_limit" if fault.status == "limit_exhausted" else "deadline" if fault.status == "timed_out" else "invalid_provider_response" if "PROTOCOL" in fault.code or fault.code == "INVALID_JSON" else "transport_unavailable"),
            "observed_requests": attempt["http_request_count"], "observed_responses": attempt["http_response_count"],
            "response_transfer_bytes": attempt["response_transfer_bytes"], "response_decoded_bytes": attempt["response_decoded_bytes"],
            "quota_source": None, "remaining_microusd": None, "reset_at": None, "retry_after_seconds": None}
        validate_schema(details, "scholar_error_details"); fault.details = details
        return None, observations, fault
    return prepared, observations, None


class ProviderQuota:
    """Executor-local serial permits. A restart requires explicit host admission."""
    def __init__(self, provider, *, anonymous_admission=False):
        self.provider, self.lock = provider, asyncio.Lock()
        self.interval_ms, self.next_time = 1000, 0.0
        self.blocked = provider == "openalex" and not anonymous_admission
        self.bucket = datetime.now(timezone.utc).date().isoformat()
        self.remaining = 100000
        self.remote_remaining = None
        self.remote_cost = None
        self.reset_at = None
        self.retry_after = None
        self.reservations = set()
        self.adjusted = set()
        self.inflight = set()

    def export_checkpoint(self):
        return {"provider": self.provider, "bucket": self.bucket, "remaining_microusd": self.remaining,
            "remote_remaining_microusd": self.remote_remaining, "remote_cost_microusd": self.remote_cost,
            "interval_ms": self.interval_ms, "next_admission_at": (datetime.now(timezone.utc) + timedelta(seconds=max(0, self.next_time - time.monotonic()))).isoformat(),
            "blocked": self.blocked, "reset_at": self.reset_at, "retry_after_seconds": self.retry_after,
            "reservations": sorted(self.reservations), "adjusted": sorted(self.adjusted), "inflight": sorted(self.inflight)}

    def restore_checkpoint(self, state):
        fields = {"provider", "bucket", "remaining_microusd", "remote_remaining_microusd", "remote_cost_microusd", "interval_ms", "next_admission_at", "blocked", "reset_at", "retry_after_seconds", "reservations", "adjusted", "inflight"}
        closed(state, fields)
        if state["provider"] != self.provider or type(state["blocked"]) is not bool or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", state["bucket"]):
            raise ToolFault("INVALID_QUOTA_CHECKPOINT", "Quota checkpoint identity is invalid")
        for key in ("remaining_microusd", "remote_remaining_microusd", "remote_cost_microusd", "interval_ms", "retry_after_seconds"):
            value = state[key]
            if value is not None and (type(value) is not int or not 0 <= value <= MAX_EXACT): raise ToolFault("INVALID_QUOTA_CHECKPOINT", "Quota checkpoint quantity is invalid")
        if state["remaining_microusd"] is None or state["remaining_microusd"] > 100000 or state["interval_ms"] is None or state["interval_ms"] < 1000:
            raise ToolFault("INVALID_QUOTA_CHECKPOINT", "Quota checkpoint expands the configured local allowance")
        for key in ("reservations", "adjusted", "inflight"):
            values = state[key]
            if not isinstance(values, list) or len(values) > 10000 or any(not isinstance(v, str) or not 1 <= len(v) <= 512 for v in values) or len(values) != len(set(values)):
                raise ToolFault("INVALID_QUOTA_CHECKPOINT", "Quota checkpoint reservation identities are invalid")
        if not set(state["adjusted"]).issubset(state["reservations"]) or not set(state["inflight"]).issubset(state["reservations"]):
            raise ToolFault("INVALID_QUOTA_CHECKPOINT", "Quota checkpoint reservations are inconsistent")
        when = datetime.fromisoformat(state["next_admission_at"].replace("Z", "+00:00"))
        if when.tzinfo is None: raise ToolFault("INVALID_QUOTA_CHECKPOINT", "Quota checkpoint pacing has no timezone")
        self.bucket, self.remaining = state["bucket"], state["remaining_microusd"]
        self.remote_remaining, self.remote_cost = state["remote_remaining_microusd"], state["remote_cost_microusd"]
        self.interval_ms = state["interval_ms"]
        self.next_time = time.monotonic() + max(0, (when - datetime.now(timezone.utc)).total_seconds())
        self.blocked = state["blocked"] or bool(state["inflight"])
        self.reset_at, self.retry_after = state["reset_at"], state["retry_after_seconds"]
        self.reservations, self.adjusted, self.inflight = set(state["reservations"]), set(state["adjusted"]), set(state["inflight"])

    async def acquire(self, reservation, context):
        while self.lock.locked():
            context.assert_active(); await asyncio.sleep(.02)
        await self.lock.acquire()
        try:
            context.assert_active()
            while time.monotonic() < self.next_time:
                context.assert_active(); await asyncio.sleep(min(.05, self.next_time - time.monotonic()))
            today = datetime.now(timezone.utc).date().isoformat()
            if today != self.bucket:
                self.bucket = today; self.remaining = 100000  # local bucket only; remote restrictions remain
            if self.blocked or self.provider == "openalex" and (self.remaining < 1000 or self.remote_remaining is not None and self.remote_remaining < 1000):
                raise ToolFault("SCHOLAR_QUOTA_EXHAUSTED", "Executor-local or observed provider allowance denies admission", status="limit_exhausted")
            if reservation in self.reservations: raise ToolFault("ATTEMPT_REUSED", "Scholarly attempt already reserved")
            self.reservations.add(reservation)
            self.inflight.add(reservation)
            if self.provider == "openalex": self.remaining -= 1000
        except BaseException:
            self.lock.release(); raise

    def settle(self, reservation, parsed, http_status=None, *, dispatched=True):
        self.inflight.discard(reservation)
        if not dispatched and reservation in self.reservations:
            self.reservations.remove(reservation)
            if self.provider == "openalex": self.remaining += 1000
        if parsed is not None:
            rate, interval = parsed["rate_limit_requests"], parsed["rate_interval_ms"]
            if rate == 0 or parsed["concurrency_limit"] == 0 or parsed["remaining_credits"] == 0: self.blocked = True
            if rate and interval: self.interval_ms = max(self.interval_ms, math.ceil(interval / rate))
            cost, remaining, budget = parsed["cost_microusd"], parsed["remaining_microusd"], parsed["budget_limit_microusd"]
            self.remote_cost, self.remote_remaining = cost, remaining if self.remote_remaining is None else min(self.remote_remaining, remaining) if remaining is not None else self.remote_remaining
            if self.provider == "openalex":
                if budget is not None: self.remaining = min(self.remaining, budget)
                if cost is not None and cost > 1000 and reservation not in self.adjusted:
                    self.remaining = max(0, self.remaining - (cost - 1000)); self.adjusted.add(reservation)
                if remaining is not None and remaining < max(1000, cost or 1000): self.blocked = True
                if parsed["remaining_credits"] is not None and parsed["cost_credits"] is not None and parsed["remaining_credits"] < parsed["cost_credits"]: self.blocked = True
            if parsed["reset_at"] is not None: self.reset_at = parsed["reset_at"]
            if parsed["retry_after_seconds"] is not None:
                self.retry_after = parsed["retry_after_seconds"]
                self.next_time = max(self.next_time, time.monotonic() + self.retry_after)
        if http_status == 429: self.blocked = True
        self.next_time = max(self.next_time, time.monotonic() + self.interval_ms / 1000)
        if self.lock.locked(): self.lock.release()

    def observation(self, reservation, parsed=None):
        return {"owner_scope": "executor_local", "reservation_id": reservation,
            "local_utc_bucket": self.bucket if self.provider == "openalex" else None,
            "reserved_microusd": 1000 if self.provider == "openalex" and reservation in self.reservations else None,
            "local_remaining_microusd": self.remaining if self.provider == "openalex" else None,
            "provider_reported_remaining_microusd": parsed["remaining_microusd"] if parsed else None,
            "provider_reported_cost_microusd": parsed["cost_microusd"] if parsed else None,
            "effective_min_interval_ms": self.interval_ms, "reset_at": self.reset_at,
            "retry_after_seconds": self.retry_after, "admission_blocked": self.blocked}
