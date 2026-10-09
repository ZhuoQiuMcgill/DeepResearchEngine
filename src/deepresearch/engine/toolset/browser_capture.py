"""Ephemeral Chromium DOM capture through the public-IP transport only.

Chromium and its Playwright driver inherit the owning worker's process Job.
The worker's hard deadline also covers native DNS, browser IPC and teardown.
"""
from __future__ import annotations

import re
import time
from contextlib import ExitStack
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import sync_playwright

from .common import LIMITS, ToolFault, url, utc_now

_RESOURCE_CAP = 2 << 20
_BLOCKED_TYPES = {"image", "font", "media"}
_HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
                "te", "trailer", "transfer-encoding", "upgrade", "content-encoding", "content-length"}


def _reject_access(body: bytes, status: int | None):
    # Restrict textual checks to titles/visible text. A normal page can mention
    # CAPTCHA in a script, or offer a login link alongside publicly visible data.
    from lxml import html
    try:
        root = html.document_fromstring(body, parser=html.HTMLParser(no_network=True))
        title = " ".join(root.xpath("//title/text()")).strip().lower()
        for node in root.xpath("//script | //style | //noscript"):
            node.drop_tree()
        visible = " ".join(root.text_content().lower().split())
        password = bool(root.xpath('//input[translate(@type,"PASSWORD","password")="password"]'))
    except (ValueError, html.etree.ParserError):
        title, visible, password = "", "", False
    if (re.search(r"^(?:just a moment|attention required|security verification|verify you are human)", title)
            or (len(visible) < 12000 and any(marker in visible for marker in
                ("verify you are human", "enable javascript and cookies to continue", "checking your browser")))):
        raise ToolFault("SOURCE_CHALLENGE", "Source requires interactive access")
    if status == 401 or (password and re.search(r"^(?:log\s*in|sign\s*in)(?:\b|$)", title)):
        raise ToolFault("SOURCE_LOGIN", "Source requires authentication")
    if status in {403, 407, 429, 451} or re.search(r"^(?:access denied|request blocked|forbidden)(?:\b|$)", title):
        raise ToolFault("SOURCE_DENIED", "Source denied public access")


def capture(source, transport, limits, timeout):
    """Return UTF-8 rendered DOM and provenance; HTTP status is never rewritten.

    GET is the only relayed method. Disallowed resources are aborted; ordinary
    subresource transport errors are counted, while policy/budget faults fail
    the entire capture. The caller owns and closes ``transport``.
    """
    deadline = min(transport.deadline, time.monotonic() + timeout)
    limits = LIMITS | (limits or {})
    script_cap = limits.get('browser_script_bytes', _RESOURCE_CAP)
    if type(script_cap) is not int or not 1 <= script_cap <= 8 << 20:
        raise ToolFault('WORKER_PROTOCOL_ERROR', 'Invalid browser script resource allowance')
    main_info: dict = {}
    main_hops: list[dict] = []
    blocked = failed_resources = relayed = 0
    fatal = None
    page = None
    main_documents = 0
    pending_navigation = None
    resource_failures = []

    def remaining_ms():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise ToolFault("DEADLINE_EXCEEDED", "Browser capture deadline expired", status="timed_out")
        return max(1, seconds * 1000)

    def relay(route):
        nonlocal blocked, failed_resources, relayed, fatal, main_info, main_documents, pending_navigation
        request = route.request
        is_main = request.is_navigation_request() and request.frame == page.main_frame
        try:
            if fatal is not None:
                route.abort("blockedbyclient")
                return
            if (request.method != "GET" or request.resource_type in _BLOCKED_TYPES
                    or urlsplit(request.url).scheme not in {"http", "https"}):
                blocked += 1
                route.abort("blockedbyclient")
                if is_main:
                    raise ToolFault("DESTINATION_DENIED", "Main navigation is not an allowed HTTP GET")
                return
            remaining_ms()
            if transport.http_request_count >= transport.max_requests or transport.decoded_bytes >= transport.total_bytes:
                raise ToolFault("RESPONSE_LIMIT", "Browser network budget exhausted", status="limit_exhausted",
                    details={"limit_scope": "fetch", "limit_kind": "browser_network_budget"})
            if is_main:
                main_documents += 1
                if main_documents > 6:
                    raise ToolFault("REDIRECT_LIMIT", "Main navigation exceeds its redirect limit")
            target = request.url
            for depth in range(6):
                body, info, raw_headers = transport.request(
                    target, cap=min(script_cap if request.resource_type == 'script' else _RESOURCE_CAP,
                                    transport.total_bytes - transport.decoded_bytes),
                    timeout=remaining_ms() / 1000, follow_redirects=False,
                    headers={key: value for key, value in request.headers.items()
                             if key.lower() in {"accept", "accept-language"}},
                )
                relayed += 1
                status = info["http_status"]
                if not 300 <= status < 400:
                    break
                if is_main:
                    main_info = dict(info)
                    main_info.update(requested_url=source, redirects=main_hops)
                location = next((value.decode("latin-1") for key, value in raw_headers
                                 if key.lower() == b"location"), None)
                if not location or depth >= 5 or (is_main and len(main_hops) >= 5):
                    raise ToolFault("REDIRECT_LIMIT", "Browser redirect chain is missing a target or exceeds its limit")
                target = url(urljoin(target, location))
                if is_main:
                    main_hops.append({"from_url": info["final_url"], "to_url": target, "http_status": status})
                    # Chromium follows fulfilled 3xx outside Playwright routing.
                    # Abort and explicitly navigate so each target is intercepted.
                    pending_navigation = target
                    route.abort("aborted")
                    return
            if is_main:
                main_info = dict(info)
                main_info["requested_url"] = source
                main_info["redirects"] = main_hops
            response_headers = {}
            # route.fulfill requires a mapping. Preserve multiple Set-Cookie
            # fields with newline separation, as Playwright's own API does.
            for key, value in raw_headers:
                key, value = key.decode("latin-1").lower(), value.decode("latin-1")
                if key not in _HOP_HEADERS:
                    separator = "\n" if key == "set-cookie" else ", "
                    response_headers[key] = response_headers[key] + separator + value if key in response_headers else value
            if is_main:
                _reject_access(body, status)
            remaining_ms()
            route.fulfill(status=status, headers=response_headers, body=body)
        except ToolFault as fault:
            failed_resources += 1
            fault.details = {**fault.details, "resource_url": request.url[:8192],
                             "resource_type": request.resource_type, "is_main_document": is_main}
            # Resource byte caps remain enforced; an optional script/style need
            # not invalidate HTML already delivered. Aggregate/policy faults do.
            local_limit = fault.code == "RESPONSE_LIMIT" and fault.details.get("limit_scope") == "resource"
            if is_main or (fault.code != "FETCH_UNAVAILABLE" and not local_limit):
                fatal = fault
            elif len(resource_failures) < 8:
                resource_failures.append({"url": request.url[:1024], "resource_type": request.resource_type,
                    "code": fault.code, "limit_scope": fault.details.get("limit_scope"),
                    "limit_kind": fault.details.get("limit_kind"), "limit": fault.details.get("limit")})
            try:
                route.abort("failed")
            except Exception:
                pass
        except Exception:
            fatal = ToolFault("BROWSER_UNAVAILABLE", "Browser network relay failed")
            try:
                route.abort("failed")
            except Exception:
                pass

    try:
        source = url(source)
        # Narrow the supplied aggregate budget as well, so a caller cannot grant
        # Chromium larger limits through a differently configured transport.
        transport.max_requests = min(transport.max_requests, 40)
        transport.total_bytes = min(transport.total_bytes, 32 << 20)
        with ExitStack() as owned:
            runtime = owned.enter_context(sync_playwright())
            browser = runtime.chromium.launch(headless=True, timeout=remaining_ms(), args=[
                "--disable-background-networking", "--disable-quic", "--disable-dns-prefetch",
                "--disable-features=Prerender2,SpeculationRulesPrefetch,PreconnectToSearch",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--host-resolver-rules=MAP * ~NOTFOUND",
                "--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=<-loopback>",
            ])
            owned.callback(browser.close)
            context = browser.new_context(service_workers="block", accept_downloads=False)
            owned.callback(context.close)
            context.set_default_timeout(remaining_ms())
            context.route("**/*", relay)
            def block_web_socket(socket):
                nonlocal blocked
                blocked += 1
                # Interception does not connect unless connect_to_server is
                # called. Leave this local mock for context teardown: calling
                # sync close inside the 1.63 route callback can deadlock.
            context.route_web_socket("**/*", block_web_socket)
            context.add_init_script("""(() => {
                for (const key of ['RTCPeerConnection', 'webkitRTCPeerConnection', 'WebTransport']) {
                    Object.defineProperty(globalThis, key, {value: undefined, configurable: false});
                }
            })();""")
            page = context.new_page()
            def navigate(target):
                nonlocal pending_navigation
                while True:
                    pending_navigation = None
                    try:
                        page.goto(target, wait_until="domcontentloaded", timeout=remaining_ms())
                    except Exception:
                        if fatal:
                            raise fatal from None
                        if pending_navigation is None:
                            raise
                    if pending_navigation is None:
                        return
                    target = pending_navigation

            try:
                navigate(source)
                if fatal:
                    raise fatal
                page.wait_for_timeout(min(1000, remaining_ms()))
                if fatal:
                    raise fatal
                if pending_navigation is not None:
                    navigate(pending_navigation)
                remaining_ms()
                dom = page.content().encode("utf-8")
                remaining_ms()
                if len(dom) > limits["raw_bytes"]:
                    raise ToolFault("RESPONSE_LIMIT", "Rendered DOM exceeds limit", status="limit_exhausted")
                if not main_info or main_info.get("http_status") is None:
                    raise ToolFault("BROWSER_UNAVAILABLE", "Browser produced no main HTTP response")
                final_url = url(page.url)
                _reject_access(dom, main_info["http_status"])
                info = {**main_info, "final_url": final_url, "redirects": main_hops,
                        "captured_at": utc_now(), "representation": "rendered_dom",
                        "chosen_charset": "utf-8", "charset_source": "browser",
                        "content_type": "text/html; charset=utf-8",
                        "http_request_count": transport.http_request_count,
                        "http_response_count": transport.http_response_count,
                        "decoded_body_bytes": transport.decoded_bytes,
                        "capture_backend": "playwright/1.63.0/chromium",
                        "capture": {"relayed_requests": relayed, "blocked_requests": blocked,
                                    "failed_resources": failed_resources, "dom_bytes": len(dom),
                                    "wait_until": "domcontentloaded", "settle_ms": 1000,
                                    "resource_failures": resource_failures}}
            except Exception:
                if fatal:
                    raise fatal from None
                raise
        return dom, info
    except Exception as exc:
        if isinstance(exc, ToolFault):
            fault = exc
        elif time.monotonic() >= deadline or type(exc).__name__ == "TimeoutError":
            fault = ToolFault("DEADLINE_EXCEEDED", "Browser capture deadline expired", status="timed_out")
        else:
            fault = ToolFault("BROWSER_UNAVAILABLE", "Chromium capture failed")
        counts = {"http_request_count": transport.http_request_count,
                  "http_response_count": transport.http_response_count,
                  "decoded_body_bytes": transport.decoded_bytes}
        fault.details = {**main_info, **fault.details, **counts}
        fault.observations = {"http_status": main_info.get("http_status"),
                              "final_url": main_info.get("final_url"), "redirects": main_hops}
        fault.usage = {**counts, "text_utf8_bytes": None, "monetary_cost": None}
        raise fault from None
