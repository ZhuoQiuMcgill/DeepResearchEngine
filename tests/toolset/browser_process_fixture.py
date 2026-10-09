"""Real guarded Chromium fixture stopped only by its owning ProcessRunner Job."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from deepresearch.engine.toolset.browser_capture import capture
from deepresearch.engine.toolset.common import ToolFault, utc_now


class ReadyTransport:
    def __init__(self, marker):
        self.marker = Path(marker)
        self.deadline = time.monotonic() + 60
        self.max_requests, self.total_bytes = 40, 32 << 20
        self.http_request_count = self.http_response_count = self.decoded_bytes = 0

    def request(self, source, **options):
        if source != "https://example.test/" or options.get("follow_redirects") is not False:
            raise ToolFault("DESTINATION_DENIED", "Fixture permits only its synthetic main page")
        body = b"<title>Job cancellation fixture</title><script>while (true) {}</script>"
        self.http_request_count += 1
        self.http_response_count += 1
        self.decoded_bytes += len(body)
        self.marker.write_text("ready", encoding="ascii")
        return body, {"requested_url": source, "final_url": source, "http_status": 200,
                      "redirects": [], "retrieved_at": utc_now(), "content_type": "text/html",
                      "content_encoding": None, "declared_content_length": str(len(body)),
                      "response_decoded_bytes": len(body), "response_transfer_bytes": len(body),
                      "etag": None, "last_modified": None}, [(b"content-type", b"text/html; charset=utf-8")]


if __name__ == "__main__":
    try:
        capture("https://example.test/", ReadyTransport(sys.argv[1]), {}, 60)
    except ToolFault as fault:
        # Only the absent bundled executable is an optional CI prerequisite.
        # Never print raw browser diagnostics, paths or exception chains.
        cause = fault.__context__
        while cause is not None:
            if "Executable doesn't exist" in str(cause):
                print("CHROMIUM_NOT_INSTALLED", flush=True)
                sys.exit(77)
            cause = cause.__context__
        print(fault.code, flush=True)
        sys.exit(1)
