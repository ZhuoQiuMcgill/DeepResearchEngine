"""Transport boundaries and actual Chromium with a controlled HTTP relay."""
from __future__ import annotations

import socket
import time
from types import SimpleNamespace

import pytest
from curl_cffi import CurlOpt

from deepresearch.engine.toolset import browser_capture, fetch_transport, retrieval
from deepresearch.engine.toolset.common import ToolFault


@pytest.fixture
def curl_boundary(monkeypatch):
    sessions, calls, replies = [], [], []

    class Session:
        def __init__(self, **options):
            self.options, self.curl_options, self.closed = options, {}, False
            sessions.append(self)

        def close(self):
            self.closed = True

        def request(self, method, target, **options):
            calls.append((method, target, options, dict(self.curl_options)))
            response = replies.pop(0)
            if isinstance(response, Exception):
                raise response
            status, headers, chunks = response
            header = self.curl_options[CurlOpt.HEADERFUNCTION]
            for line in [f"HTTP/2 {status}\r\n".encode(), *[key + b": " + value + b"\r\n" for key, value in headers], b"\r\n"]:
                if header(line) == 0xFFFFFFFF:
                    raise RuntimeError("secret header failure")
            for chunk in chunks:
                if options["content_callback"](chunk) == 0xFFFFFFFF:
                    raise RuntimeError("secret body failure")
            return SimpleNamespace(download_size=sum(map(len, chunks)))

    monkeypatch.setattr(fetch_transport, "Session", Session)
    monkeypatch.setattr(retrieval, "public_addresses", lambda host, port: ["93.184.215.14"])
    return sessions, calls, replies


def transport(**options):
    return fetch_transport.CurlTransport(time.monotonic() + 20, **options)


def test_public_dns_rejects_mixed_private_answers(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    with transport() as client, pytest.raises(ToolFault) as caught:
        client.request("https://example.com", cap=100)
    assert caught.value.code == "DESTINATION_DENIED"
    assert caught.value.usage["http_request_count"] == 0


def test_pin_tls_session_redirect_and_headers(curl_boundary, monkeypatch):
    sessions, calls, replies = curl_boundary
    resolved = []
    monkeypatch.setattr(retrieval, "public_addresses", lambda host, port: resolved.append((host, port)) or ["93.184.215.14"])
    replies.extend([(302, [(b"Location", b"/article"), (b"Set-Cookie", b"visit=1; Secure")], [b"hop"]),
                    (202, [(b"Content-Type", b"text/html"), (b"ETag", b"abc")], [b"hello"]),
                    (200, [], [b"again"])])
    with transport() as client:
        body, info, headers = client.request("https://example.com/start#fragment", cap=100,
                                             headers={"Host": "localhost", "Authorization": "secret", "Accept": "text/html"})
        client.request("https://example.com/next", cap=100)
        assert (client.http_request_count, client.http_response_count, client.decoded_bytes) == (3, 3, 13)
    assert len(sessions) == 1 and sessions[0].closed
    assert sessions[0].options == dict(impersonate="chrome", verify=True, trust_env=False, allow_redirects=False, retry=0)
    assert resolved == [("example.com", 443)] * 3
    assert body == b"hello" and info["http_status"] == 202
    assert info["redirects"] == [{"from_url": "https://example.com/start", "to_url": "https://example.com/article", "http_status": 302}]
    assert headers == [(b"Content-Type", b"text/html"), (b"ETag", b"abc")]
    for method, target, options, native in calls:
        assert method == "GET" and "#" not in target
        assert native[CurlOpt.RESOLVE] == [b"example.com:443:93.184.215.14"]
        assert native[CurlOpt.PROXY] == "" and native[CurlOpt.SSL_VERIFYHOST] == 2
        assert native[CurlOpt.FRESH_CONNECT] == native[CurlOpt.FORBID_REUSE] == 1
        assert options["allow_redirects"] is False and options["verify"] is True
        assert "Host" not in options["headers"] and "Authorization" not in options["headers"]


def test_redirect_dns_revalidated_and_failure_counted(curl_boundary, monkeypatch):
    _, calls, replies = curl_boundary
    replies.append((302, [(b"Location", b"https://internal.test/")], [b"hop"]))
    def resolve(host, port):
        if host == "internal.test":
            raise ToolFault("DESTINATION_DENIED", "Destination resolves to a nonpublic address")
        return ["93.184.215.14"]
    monkeypatch.setattr(retrieval, "public_addresses", resolve)
    with transport() as client, pytest.raises(ToolFault) as caught:
        client.request("https://example.com/", cap=100)
    assert len(calls) == 1 and caught.value.code == "DESTINATION_DENIED"
    assert caught.value.details["http_response_count"] == 1
    assert caught.value.usage["decoded_body_bytes"] == 3


def test_no_follow_and_redirect_cap(curl_boundary):
    _, calls, replies = curl_boundary
    replies.extend([(302, [(b"Location", b"/loop")], [])] * 7)
    with transport() as client:
        _, info, _ = client.request("https://example.com/", cap=100, follow_redirects=False)
        assert info["http_status"] == 302 and len(calls) == 1
        with pytest.raises(ToolFault) as caught:
            client.request("https://example.com/", cap=100)
        assert caught.value.code == "REDIRECT_LIMIT" and len(calls) == 7


@pytest.mark.parametrize("options,cap", [({}, 4), ({"total_bytes": 4}, 100)])
def test_decoded_byte_limit_and_cleanup(curl_boundary, options, cap):
    sessions, _, replies = curl_boundary
    replies.append((200, [(b"Content-Encoding", b"gzip")], [b"abc", b"def"]))
    with pytest.raises(ToolFault) as caught:
        with transport(**options) as client:
            client.request("https://example.com/", cap=cap)
    assert caught.value.code == "RESPONSE_LIMIT"
    assert caught.value.details["response_decoded_bytes"] == 6
    assert caught.value.usage["decoded_body_bytes"] == 6 and sessions[0].closed
    assert "secret" not in str(caught.value)


def test_request_budget_and_network_failure(curl_boundary):
    sessions, calls, replies = curl_boundary
    replies.append(RuntimeError("secret transport failure"))
    with transport(max_requests=1) as client:
        with pytest.raises(ToolFault) as caught:
            client.request("https://example.com/", cap=100)
        assert caught.value.code == "FETCH_UNAVAILABLE"
        assert caught.value.usage["http_response_count"] == 0
        assert "secret" not in str(caught.value)
        with pytest.raises(ToolFault) as caught:
            client.request("https://example.com/", cap=100)
        assert caught.value.code == "REQUEST_LIMIT"
    assert len(calls) == 1 and sessions[0].closed


def test_header_limit_is_not_mislabeled_as_body_limit(curl_boundary):
    _, _, replies = curl_boundary
    replies.append((200, [(b"Huge", b"x" * (64 << 10))], []))
    with transport() as client, pytest.raises(ToolFault) as caught:
        client.request("https://example.com/", cap=1 << 20)
    assert caught.value.details["limit_kind"] == "header_bytes"
    assert caught.value.details["limit_scope"] == "resource"
    assert caught.value.details["limit"] == 64 << 10


def test_numeric_transport_error_retained_without_sensitive_exception_text(curl_boundary):
    _, _, replies = curl_boundary
    error = RuntimeError("sensitive arbitrary network error text")
    error.code = 35
    replies.append(error)
    with transport() as client, pytest.raises(ToolFault) as caught:
        client.request("https://example.com/", cap=100)
    assert caught.value.details["transport_error_code"] == 35
    assert "sensitive" not in str(caught.value.details)


def test_shared_deadline_during_callback(curl_boundary, monkeypatch):
    _, _, replies = curl_boundary
    replies.append((200, [], [b"body"]))
    now = [100.0]
    monkeypatch.setattr(fetch_transport.time, "monotonic", lambda: now[0])
    client = fetch_transport.CurlTransport(101)
    # Name resolution consumed the entire grant: no request may be dispatched.
    monkeypatch.setattr(retrieval, "public_addresses", lambda *args: now.__setitem__(0, 102) or ["93.184.215.14"])
    with client, pytest.raises(ToolFault) as caught:
        client.request("https://example.com/", cap=100)
    assert caught.value.code == "DEADLINE_EXCEEDED" and client.http_request_count == 0


class RelayTransport:
    """No sockets: Chromium's only successful HTTP path is this test boundary."""
    def __init__(self, responses):
        self.deadline = time.monotonic() + 20
        self.max_requests, self.total_bytes = 40, 32 << 20
        self.http_request_count = self.http_response_count = self.decoded_bytes = 0
        self.responses, self.calls = responses, []

    def request(self, source, **options):
        self.calls.append((source, options))
        self.http_request_count += 1
        response = self.responses[source]
        if isinstance(response, Exception):
            raise response
        status, headers, body = response
        self.http_response_count += 1
        self.decoded_bytes += len(body)
        return body, {"requested_url": source, "final_url": source, "redirects": [], "http_status": status,
                      "retrieved_at": "2026-10-03T00:00:00+00:00", "content_type": "text/html",
                      "content_encoding": None, "declared_content_length": str(len(body)),
                      "etag": None, "last_modified": None, "response_transfer_bytes": len(body),
                      "response_decoded_bytes": len(body)}, headers


def html_reply(body, status=200):
    return status, [(b"content-type", b"text/html; charset=utf-8")], body


@pytest.mark.parametrize("scope,success", [("resource", True), ("fetch", False)])
def test_browser_local_resource_cap_preserves_dom_but_fetch_cap_stops(scope, success):
    client = RelayTransport({
        "https://example.test/page": html_reply(b'<html><title>Article</title><body><p>Retained article text.</p><script src="/optional.js"></script></body></html>'),
        "https://example.test/optional.js": ToolFault("RESPONSE_LIMIT", "Decoded limit", status="limit_exhausted",
            details={"limit_scope": scope, "limit_kind": "decoded_bytes", "limit": 2 << 20})})
    if success:
        dom, info = browser_capture.capture("https://example.test/page", client, {"raw_bytes": 10000}, 15)
        assert b"Retained article text" in dom
        failed = info["capture"]["resource_failures"]
        assert len(failed) == 1 and failed[0]["url"] == "https://example.test/optional.js"
        assert failed[0]["limit"] == 2 << 20
    else:
        with pytest.raises(ToolFault) as caught:
            browser_capture.capture("https://example.test/page", client, {"raw_bytes": 10000}, 15)
        assert caught.value.code == "RESPONSE_LIMIT"
        assert caught.value.details["resource_url"] == "https://example.test/optional.js"
        assert caught.value.details["limit_scope"] == "fetch"


def test_actual_chromium_relay_redirect_scripts_and_202():
    client = RelayTransport({
        "https://example.test/start": (302, [(b"location", b"/page")], b""),
        "https://example.test/page": html_reply(b'''<html><head><title>Public table</title></head><body>
          <img src="/image"><script src="/script"></script></body></html>''', 202),
        "https://example.test/script": (200, [(b"content-type", b"application/javascript")], b'''
          document.body.insertAdjacentHTML('beforeend', '<table><tr><td>Rendered evidence</td></tr></table>');
          fetch('/post', {method:'POST'}).catch(()=>{});
          fetch('/data').then(r=>r.text()).then(t=>document.body.append(t));
          new WebSocket('wss://example.test/socket');
          navigator.serviceWorker.register('/worker').catch(()=>{});
        '''),
        "https://example.test/data": (302, [(b"location", b"/final-data")], b""),
        "https://example.test/final-data": (200, [(b"content-type", b"text/plain")], b"Relayed data"),
    })
    dom, info = browser_capture.capture("https://example.test/start", client, {"raw_bytes": 10000}, 15)
    assert b"<td>Rendered evidence</td>" in dom and b"Relayed data" in dom
    assert info["http_status"] == 202 and info["final_url"] == "https://example.test/page"
    assert info["representation"] == "rendered_dom" and info["chosen_charset"] == "utf-8"
    assert len(info["redirects"]) == 1
    assert {source for source, _ in client.calls} == set(client.responses)
    assert all(options["cap"] == 2 << 20 and options["follow_redirects"] is False for _, options in client.calls)
    assert info["capture"]["blocked_requests"] >= 2


@pytest.mark.parametrize("reply,code", [
    (html_reply(b"<title>Just a moment...</title><p>Verify you are human</p>", 403), "SOURCE_CHALLENGE"),
    (html_reply(b"<title>Access denied</title>", 403), "SOURCE_DENIED"),
    (html_reply(b'<title>Sign in</title><input type="password">'), "SOURCE_LOGIN"),
    (ToolFault("FETCH_UNAVAILABLE", "HTTP transport failed"), "FETCH_UNAVAILABLE"),
])
def test_actual_chromium_access_and_failure_cleanup(reply, code, monkeypatch):
    from playwright.sync_api import Browser, BrowserContext
    closed = []
    for cls, name in [(Browser, "browser"), (BrowserContext, "context")]:
        original = cls.close
        def close(self, *args, _original=original, _name=name, **kwargs):
            closed.append(_name)
            return _original(self, *args, **kwargs)
        monkeypatch.setattr(cls, "close", close)
    client = RelayTransport({"https://example.test/": reply})
    with pytest.raises(ToolFault) as caught:
        browser_capture.capture("https://example.test/", client, {}, 15)
    assert caught.value.code == code
    assert caught.value.usage["http_request_count"] == 1
    assert closed == ["context", "browser"]
    if not isinstance(reply, Exception):
        assert caught.value.observations["http_status"] == reply[0]


def test_actual_chromium_private_subresource_fails_closed():
    client = RelayTransport({
        "https://example.test/": html_reply(b'<script src="https://internal.test/private"></script>'),
        "https://internal.test/private": ToolFault("DESTINATION_DENIED", "Destination resolves to a nonpublic address"),
    })
    with pytest.raises(ToolFault) as caught:
        browser_capture.capture("https://example.test/", client, {}, 15)
    assert caught.value.code == "DESTINATION_DENIED"


def test_actual_chromium_dom_byte_limit():
    client = RelayTransport({"https://example.test/": html_reply(b"<p>body</p>")})
    with pytest.raises(ToolFault) as caught:
        browser_capture.capture("https://example.test/", client, {"raw_bytes": 8}, 15)
    assert caught.value.code == "RESPONSE_LIMIT"


@pytest.mark.parametrize("private", [False, True])
def test_actual_chromium_redirect_limit_and_private_target(private):
    responses = {f"https://example.test/{i}": (302, [(b"location", f"/{i + 1}".encode())], b"")
                 for i in range(7)}
    if private:
        responses["https://example.test/1"] = ToolFault("DESTINATION_DENIED", "Destination resolves to a nonpublic address")
    client = RelayTransport(responses)
    with pytest.raises(ToolFault) as caught:
        browser_capture.capture("https://example.test/0", client, {}, 15)
    assert caught.value.code == ("DESTINATION_DENIED" if private else "REDIRECT_LIMIT")
    assert client.http_request_count == (2 if private else 6)
    assert len(caught.value.observations["redirects"]) == (1 if private else 5)


def test_actual_curl_cookie_retention_and_compressed_cap(monkeypatch):
    import gzip
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen_cookie = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            body = gzip.compress(b"x" * 1024) if self.path == "/large" else b"public body"
            self.send_response(302 if self.path == "/start" else 200)
            if self.path == "/start":
                self.send_header("Location", "/final")
                self.send_header("Set-Cookie", "visit=1; Path=/")
            if self.path == "/final":
                seen_cookie.append(self.headers.get("Cookie") == "visit=1")
            if self.path == "/large":
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Only this controlled network test substitutes DNS validation. Production
    # public_addresses never permits loopback; that boundary is tested above.
    monkeypatch.setattr(retrieval, "public_addresses", lambda *args: ["127.0.0.1"])
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    try:
        with transport() as client:
            base = f"http://example.test:{server.server_port}"
            body, info, _ = client.request(base + "/start", cap=2048)
            assert body == b"public body" and seen_cookie == [True]
            assert info["http_status"] == 200 and client.http_request_count == 2
            with pytest.raises(ToolFault) as caught:
                client.request(base + "/large", cap=128)
            assert caught.value.code == "RESPONSE_LIMIT"
            assert client.http_response_count == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_capture_launch_failure_is_sanitized(monkeypatch):
    class Runtime:
        def __enter__(self):
            self.chromium = self
            return self
        def __exit__(self, *_):
            self.stopped = True
        def launch(self, **kwargs):
            raise RuntimeError("secret launcher diagnostics")
    runtime = Runtime()
    monkeypatch.setattr(browser_capture, "sync_playwright", lambda: runtime)
    client = RelayTransport({})
    with pytest.raises(ToolFault) as caught:
        browser_capture.capture("https://example.test/", client, {}, 1)
    assert caught.value.code == "BROWSER_UNAVAILABLE" and runtime.stopped
    assert "secret" not in str(caught.value) and client.http_request_count == 0

