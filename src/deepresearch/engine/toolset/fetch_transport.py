"""Bounded GET transport with Chrome TLS and independently pinned public DNS.

The deadline is an absolute ``time.monotonic()`` value. Instances are owned by
one worker/thread; their cookie jar and aggregate budgets span all requests.
"""
from __future__ import annotations

import math
import time
from urllib.parse import urljoin

import httpx
from curl_cffi import CurlOpt
from curl_cffi.requests import Session

from . import retrieval
from .common import ToolFault, url, utc_now


class CurlTransport:
    def __init__(self, deadline: float, max_requests: int = 40, total_bytes: int = 32 << 20):
        if not math.isfinite(deadline) or max_requests < 1 or total_bytes < 1:
            raise ValueError("Invalid transport limits")
        self.deadline = deadline
        self.max_requests, self.total_bytes = max_requests, total_bytes
        self.http_request_count = self.http_response_count = self.decoded_bytes = 0
        self._session = None
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._closed = True
        if self._session is not None:
            self._session.close()
            self._session = None

    def _annotate(self, fault: ToolFault, info: dict) -> ToolFault:
        counts = {"http_request_count": self.http_request_count,
                  "http_response_count": self.http_response_count,
                  "decoded_body_bytes": self.decoded_bytes}
        fault.details = {**info, **fault.details, **counts}
        fault.observations = {key: info.get(key) for key in
                              ("http_status", "final_url", "redirects")}
        fault.usage = {**counts, "text_utf8_bytes": None, "monetary_cost": None}
        return fault

    def request(self, source, *, cap: int, timeout: float | None = None,
                follow_redirects: bool = True, headers: dict | None = None):
        info: dict = {}
        try:
            if self._closed:
                raise ToolFault("FETCH_UNAVAILABLE", "HTTP transport is closed")
            if type(cap) is not int or cap < 1 or (timeout is not None and not math.isfinite(timeout)):
                raise ToolFault("INVALID_ARGUMENT", "Invalid HTTP request limits")
            requested = url(source)
            target = requested
            deadline = min(self.deadline, time.monotonic() + timeout) if timeout is not None else self.deadline
            hops = []
            info = {"requested_url": requested, "final_url": requested, "redirects": hops,
                    "http_status": None, "response_transfer_bytes": 0, "response_decoded_bytes": 0}
            # Do not permit callers to override routing or supply credentials.
            safe_headers = {key: value for key, value in (headers or {}).items()
                            if key.lower() in {"accept", "accept-language", "user-agent"}}
            for hop in range(6):
                self._remaining(deadline)
                if self.http_request_count >= self.max_requests:
                    raise ToolFault("REQUEST_LIMIT", "HTTP request budget exhausted", status="limit_exhausted",
                        details={"limit_scope": "fetch", "limit_kind": "request_count", "limit": self.max_requests})
                if self.decoded_bytes >= self.total_bytes:
                    raise ToolFault("RESPONSE_LIMIT", "HTTP byte budget exhausted", status="limit_exhausted",
                        details={"limit_scope": "fetch", "limit_kind": "decoded_bytes", "limit": self.total_bytes})
                original = httpx.URL(url(target)).copy_with(fragment=None)
                host = original.raw_host.decode("ascii")
                port = original.port or (443 if original.scheme == "https" else 80)
                addresses = retrieval.public_addresses(host, port)
                remaining = self._remaining(deadline)
                address = addresses[0]
                resolve_host = f"[{host}]" if ":" in host else host
                resolve_ip = f"[{address}]" if ":" in address else address
                if self._session is None:
                    self._session = Session(impersonate="chrome", verify=True, trust_env=False,
                                            allow_redirects=False, retry=0)
                chunks: list[bytes] = []
                raw_headers: list[tuple[bytes, bytes]] = []
                received = header_bytes = 0
                response_seen = False
                callback_fault = None
                remaining_bytes = self.total_bytes - self.decoded_bytes
                effective_cap = min(cap, remaining_bytes)
                limit_detail = {"limit_scope": "resource" if cap < remaining_bytes else "fetch",
                                "limit_kind": "decoded_bytes", "limit": effective_cap,
                                "resource_url": str(original)}
                info.update(final_url=str(original), http_status=None, response_transfer_bytes=0,
                            response_decoded_bytes=0, retrieved_at=utc_now())

                def on_header(line):
                    nonlocal header_bytes, response_seen, callback_fault
                    header_bytes += len(line)
                    if time.monotonic() >= deadline:
                        callback_fault = ToolFault("DEADLINE_EXCEEDED", "Retrieval deadline expired", status="timed_out")
                    elif header_bytes > 64 << 10:
                        callback_fault = ToolFault("RESPONSE_LIMIT", "HTTP headers exceed limit", status="limit_exhausted",
                            details={"limit_scope": "resource", "limit_kind": "header_bytes", "limit": 64 << 10,
                                     "resource_url": str(original)})
                    if callback_fault:
                        return 0xFFFFFFFF  # CURL_WRITEFUNC_ERROR; returning 0 is ignored by curl_cffi.
                    if line.startswith(b"HTTP/"):
                        status = int(line.split()[1])
                        raw_headers.clear()
                        if status >= 200:
                            info["http_status"] = status
                            if not response_seen:
                                self.http_response_count += 1
                                response_seen = True
                    elif b":" in line:
                        key, value = line.split(b":", 1)
                        raw_headers.append((key.strip(), value.strip()))
                    return len(line)

                def on_body(chunk):
                    nonlocal received, callback_fault
                    received += len(chunk)
                    self.decoded_bytes += len(chunk)
                    info["response_decoded_bytes"] = received
                    if time.monotonic() >= deadline:
                        callback_fault = ToolFault("DEADLINE_EXCEEDED", "Retrieval deadline expired", status="timed_out")
                    elif received > cap or self.decoded_bytes > self.total_bytes:
                        callback_fault = ToolFault("RESPONSE_LIMIT", "Decoded HTTP body exceeds limit", status="limit_exhausted",
                                                   details=limit_detail)
                    if callback_fault:
                        return 0xFFFFFFFF
                    chunks.append(chunk)
                    return len(chunk)

                # Disable proxies explicitly: libcurl itself reads proxy environment
                # variables even when the requests wrapper has trust_env=False.
                # Fresh connections prevent reuse/coalescing bypassing a new pin.
                self._session.curl_options = {
                    CurlOpt.RESOLVE: [f"{resolve_host}:{port}:{resolve_ip}".encode("ascii")],
                    CurlOpt.PROXY: "", CurlOpt.NOPROXY: "*",
                    CurlOpt.FRESH_CONNECT: 1, CurlOpt.FORBID_REUSE: 1,
                    CurlOpt.SSL_VERIFYPEER: 1, CurlOpt.SSL_VERIFYHOST: 2,
                    CurlOpt.TIMEOUT_MS: max(1, int(remaining * 1000)),
                    CurlOpt.CONNECTTIMEOUT_MS: max(1, int(min(8, remaining) * 1000)),
                    CurlOpt.MAXFILESIZE_LARGE: min(cap, self.total_bytes - self.decoded_bytes),
                    CurlOpt.HEADERFUNCTION: on_header,
                }
                self.http_request_count += 1
                response = None
                failure = None
                try:
                    response = self._session.request("GET", str(original), headers=safe_headers,
                                                     timeout=remaining, allow_redirects=False,
                                                     verify=True, content_callback=on_body)
                except Exception as exc:
                    response = getattr(exc, "response", None)
                    transport_code = getattr(exc, "code", None)
                    failure = callback_fault or ToolFault(
                        "DEADLINE_EXCEEDED" if getattr(exc, "code", None) == 28 else
                        "RESPONSE_LIMIT" if getattr(exc, "code", None) == 63 else "FETCH_UNAVAILABLE",
                        "HTTP transport deadline expired" if getattr(exc, "code", None) == 28 else "HTTP transport failed",
                        status="timed_out" if getattr(exc, "code", None) == 28 else
                        "limit_exhausted" if getattr(exc, "code", None) == 63 else "failed")
                    if isinstance(transport_code, int):
                        failure.details["transport_error_code"] = int(transport_code)
                header_map = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in raw_headers}
                info.update(content_type=header_map.get("content-type", ""),
                            content_encoding=header_map.get("content-encoding"),
                            declared_content_length=header_map.get("content-length"),
                            etag=header_map.get("etag"), last_modified=header_map.get("last-modified"),
                            http_request_count=self.http_request_count, http_response_count=self.http_response_count,
                            response_transfer_bytes=getattr(response, "download_size", None))
                if failure:
                    if failure.code == "RESPONSE_LIMIT":
                        failure.details = {**limit_detail, **failure.details}
                    raise failure from None
                self._remaining(deadline)
                if 300 <= info["http_status"] < 400 and follow_redirects:
                    location = header_map.get("location")
                    if not location or hop >= 5:
                        raise ToolFault("REDIRECT_LIMIT", "Redirect chain is missing a target or exceeds its limit")
                    target = url(urljoin(str(original), location))
                    hops.append({"from_url": str(original), "to_url": target, "http_status": info["http_status"]})
                    continue
                return b"".join(chunks), info, raw_headers
        except ToolFault as fault:
            raise self._annotate(fault, info) from None
        except Exception:
            raise self._annotate(ToolFault("FETCH_UNAVAILABLE", "HTTP transport failed"), info) from None

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ToolFault("DEADLINE_EXCEEDED", "Retrieval deadline expired", status="timed_out")
        return remaining
