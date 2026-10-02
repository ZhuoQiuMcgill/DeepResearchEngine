"""Static retrieval, pinned public-IP transport, and same-body extraction."""
from __future__ import annotations

import base64
import codecs
import io
import ipaddress
import logging
import re
import socket
import time
import zlib
from urllib.parse import urljoin, urlsplit

import httpx

from .common import LIMITS, ToolFault, digest, encode, prefix_utf8, url, utc_now


def public_addresses(host: str, port: int) -> list[str]:
    try:
        addresses = list(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    except OSError as exc:
        raise ToolFault("FETCH_UNAVAILABLE", "Destination name could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ToolFault("DESTINATION_DENIED", "Destination resolves to a nonpublic address")
    return addresses


def request_body(source: str, *, cap: int, timeout: float, redirects: int = 5,
                 metadata: bool = False, on_headers=None) -> tuple[bytes, dict, list[tuple[bytes, bytes]]]:
    """Connect to the checked IP; original hostname remains TLS SNI/certificate name."""
    requested = url(source)
    target, hops = requested, []
    start = time.monotonic()
    requests = responses = 0
    for hop in range(redirects + 1):
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0: raise ToolFault("DEADLINE_EXCEEDED", "Retrieval deadline expired", status="timed_out")
        original = httpx.URL(url(target))
        host, port = original.host, original.port or (443 if original.scheme == "https" else 80)
        address = public_addresses(host, port)[0]
        pinned = original.copy_with(host=address, fragment="")
        authority = host + (f":{original.port}" if original.port else "")
        request_timeout = httpx.Timeout(min(10, remaining), connect=min(8, remaining))
        headers = {"Host": authority, "Accept-Encoding": "identity", "User-Agent": "DeepResearch-Engine/0.1 (static retrieval)"}
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=request_timeout, transport=httpx.HTTPTransport(retries=0)) as client:
            try:
                requests += 1
                with client.stream("GET", pinned, headers=headers, extensions={"sni_hostname": host}) as response:
                    responses += 1
                    raw_headers = list(response.headers.raw)
                    status = response.status_code
                    info = {"requested_url": requested, "final_url": str(original.copy_with(fragment="")),
                            "redirects": hops, "retrieved_at": utc_now(), "http_status": status,
                            "content_type": response.headers.get("content-type", ""),
                            "content_encoding": response.headers.get("content-encoding"),
                            "declared_content_length": response.headers.get("content-length"),
                            "http_request_count": requests, "http_response_count": responses,
                            "response_transfer_bytes": 0, "response_decoded_bytes": 0,
                            "etag": response.headers.get("etag"), "last_modified": response.headers.get("last-modified")}
                    if on_headers is not None: on_headers(info, raw_headers)
                    if 300 <= status < 400 and not metadata:
                        location = response.headers.get("location")
                        if not location or hop >= redirects:
                            raise ToolFault("REDIRECT_LIMIT", "Redirect chain is missing a target or exceeds its limit")
                        new_target = url(urljoin(target, location))
                        hops.append({"from_url": str(original.copy_with(fragment="")), "to_url": new_target, "http_status": status})
                        target = new_target
                        continue
                    transfer = 0
                    chunks = []
                    decoded = 0
                    encoding = (response.headers.get("content-encoding") or "identity").lower()
                    decoder = None
                    if encoding == "gzip": decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    elif encoding == "deflate": decoder = zlib.decompressobj()
                    elif encoding not in ("identity", ""):
                        raise ToolFault("UNSUPPORTED_ENCODING", "Unsupported HTTP content encoding")
                    for raw in response.iter_raw(chunk_size=16384):
                        if time.monotonic() - start >= timeout:
                            raise ToolFault("DEADLINE_EXCEEDED", "Retrieval deadline expired", status="timed_out")
                        transfer += len(raw)
                        info["response_transfer_bytes"] = transfer
                        if transfer > cap:
                            raise ToolFault("RESPONSE_LIMIT", "Response transfer bytes exceed limit", status="limit_exhausted", details=info)
                        content = decoder.decompress(raw, cap - decoded + 1) if decoder else raw
                        decoded += len(content); info["response_decoded_bytes"] = decoded
                        if decoded > cap or (decoder and decoder.unconsumed_tail):
                            raise ToolFault("RESPONSE_LIMIT", "Decoded response exceeds limit", status="limit_exhausted", details=info)
                        chunks.append(content)
                    if decoder:
                        last = decoder.flush(cap - decoded + 1)
                        decoded += len(last); info["response_decoded_bytes"] = decoded
                        if decoded > cap or not decoder.eof or decoder.unused_data:
                            raise ToolFault("RESPONSE_LIMIT", "Compressed response is incomplete or exceeds limit", status="limit_exhausted", details=info)
                        chunks.append(last)
                    return b"".join(chunks), info, raw_headers
            except httpx.HTTPError as exc:
                raise ToolFault("FETCH_UNAVAILABLE", "HTTP transport failed", details={"http_request_count": requests, "http_response_count": responses}) from exc
    raise ToolFault("REDIRECT_LIMIT", "Redirect chain exceeds limit")


_CHARSETS = {"utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "ascii", "cp1252", "iso8859-1"}


def decode_text(body: bytes, content_type: str, *, html: bool = False) -> tuple[str, str, str]:
    match = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", content_type, re.I)
    declared = match.group(1) if match else None
    meta = None
    if html:
        head = body[:8192].decode("ascii", errors="ignore")
        meta_match = re.search(r"<meta[^>]+charset\s*=\s*[\"']?([^\s/>;\"']+)", head, re.I)
        meta = meta_match.group(1) if meta_match else None
    bom = "utf-8" if body.startswith(codecs.BOM_UTF8) else "utf-16-le" if body.startswith(codecs.BOM_UTF16_LE) else "utf-16-be" if body.startswith(codecs.BOM_UTF16_BE) else None
    def canon(value):
        if value is None: return None
        try: name = codecs.lookup(value).name
        except LookupError as exc: raise ToolFault("UNSUPPORTED_ENCODING", "Source declares an unknown charset") from exc
        if name not in _CHARSETS: raise ToolFault("UNSUPPORTED_ENCODING", "Source charset is not registered")
        return name
    declared, meta = canon(declared), canon(meta)
    for observed in (declared, meta):
        if bom and observed and observed != bom and not (observed == "utf-16" and bom.startswith("utf-16")) and not (observed == "utf-8-sig" and bom == "utf-8"):
            raise ToolFault("UNSUPPORTED_ENCODING", "BOM and charset declaration conflict")
    if declared and meta and declared != meta:
        raise ToolFault("UNSUPPORTED_ENCODING", "HTTP and HTML charset declarations conflict")
    charset, origin = (bom, "bom") if bom else (declared, "http") if declared else (meta, "html_meta") if meta else ("utf-8", "default_utf8")
    payload = body
    if bom == "utf-8": payload = payload[len(codecs.BOM_UTF8):]
    elif bom in ("utf-16-le", "utf-16-be"): payload = payload[2:]
    if charset == "utf-16" and not bom: raise ToolFault("UNSUPPORTED_ENCODING", "UTF-16 requires an unambiguous BOM")
    try: text = payload.decode(charset, errors="strict")
    except UnicodeError as exc: raise ToolFault("DECODING_ERROR", "Source cannot be strictly decoded using its registered charset") from exc
    if not html and any((ord(c) < 32 and c not in "\t\n\r\f") or ord(c) == 127 for c in text):
        raise ToolFault("UNSUPPORTED_CONTENT", "Plain text contains binary controls")
    return text, charset, origin


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def build_index(text: bytes, pages: list[dict] | None) -> dict:
    lines, position = [], 0
    # Only LF separates logical lines; form-feed and Unicode separators are content.
    for line, item in enumerate(text.split(b"\n"), 1):
        if position == len(text): break
        lines.append({"line": line, "start_byte": position, "end_byte": position + len(item)})
        position += len(item) + 1
    return {"schema_version": 1, "format": "document_index/1", "text_sha256": digest(text), "lines": lines, "pages": pages}


def extract(body: bytes, info: dict, limits: dict | None = None) -> dict:
    limits = LIMITS | (limits or {})
    content_type = info["content_type"]
    media = content_type.split(";", 1)[0].strip().lower()
    pages, charset, charset_source = None, None, None
    parser_warning_count = 0
    if body.startswith(b"%PDF-") and media != "application/pdf":
        raise ToolFault("CONTENT_TYPE_MISMATCH", "PDF bytes disagree with declared media type")
    if media == "application/pdf":
        if not body.startswith(b"%PDF-"): raise ToolFault("CONTENT_TYPE_MISMATCH", "Declared PDF lacks PDF magic")
        from pypdf import PdfReader
        class WarningCounter(logging.Handler):
            count = 0
            def emit(self, record):
                self.count = min(2**53 - 1, self.count + 1)
        # Parser recovery warnings can include large object strings. Preserve
        # a count without forwarding unbounded/raw source diagnostics to pipes.
        logger = logging.getLogger("pypdf")
        old_handlers, old_propagate = logger.handlers[:], logger.propagate
        counter = WarningCounter(level=logging.WARNING)
        logger.handlers, logger.propagate = [counter], False
        try:
            reader = PdfReader(io.BytesIO(body), strict=True)
            if reader.is_encrypted: raise ToolFault("PDF_ENCRYPTED", "Encrypted PDF is unsupported")
            if len(reader.pages) > limits["pdf_pages"]: raise ToolFault("PDF_PAGE_LIMIT", "PDF physical page count exceeds limit", status="limit_exhausted")
            page_texts, pages, offset = [], [], 0
            for number, page in enumerate(reader.pages, 1):
                value = normalize(page.extract_text() or "")
                encoded = value.encode("utf-8")
                pages.append({"page": number, "start_byte": offset, "end_byte": offset + len(encoded)})
                offset += len(encoded) + 1
                if offset > limits["text_bytes"] + 1: raise ToolFault("TEXT_LIMIT", "PDF extracted text exceeds limit", status="limit_exhausted")
                page_texts.append(value)
            text = "\n".join(page_texts)
            if not text.strip(): raise ToolFault("PDF_NO_TEXT", "PDF contains no usable text; OCR is required", details={"classification": "OCR_REQUIRED"})
            extraction = "pypdf/6.19.0"
        except ToolFault: raise
        except Exception as exc: raise ToolFault("PDF_INVALID", "PDF parser could not extract this document") from exc
        finally:
            parser_warning_count = counter.count
            logger.handlers, logger.propagate = old_handlers, old_propagate
    elif media in ("text/html", "application/xhtml+xml"):
        source, charset, charset_source = decode_text(body, content_type, html=True)
        lowered = source.lower()
        if any(marker in lowered for marker in ("cf-chl-", "verify you are human", "just a moment...", "enable javascript and cookies to continue")):
            raise ToolFault("SOURCE_CHALLENGE", "Source requires interactive access")
        import trafilatura
        text = trafilatura.extract(source, include_comments=False, include_tables=True, output_format="txt")
        if not text or not text.strip(): raise ToolFault("EXTRACTION_EMPTY", "Static HTML has no extractable document text")
        text, extraction = normalize(text), "trafilatura/2.2.0"
    elif media == "text/plain":
        text, charset, charset_source = decode_text(body, content_type)
        text, extraction = normalize(text), "plain_text/1"
        if not text.strip(): raise ToolFault("EXTRACTION_EMPTY", "Plain-text source is empty")
    else: raise ToolFault("UNSUPPORTED_CONTENT", "Source media type is unsupported")
    encoded = text.encode("utf-8")
    if len(body) > limits["raw_bytes"] or len(encoded) > limits["text_bytes"]:
        raise ToolFault("RESPONSE_LIMIT", "Source component exceeds limit", status="limit_exhausted")
    index = encode(build_index(encoded, pages), limits["index_bytes"])
    provenance = {**info, "representation": "content_decoded", "media_type": media,
                  "chosen_charset": charset, "charset_source": charset_source,
                  "original_bytes": len(body), "original_sha256": digest(body),
                  "text_bytes": len(encoded), "text_sha256": digest(encoded),
                  "index_bytes": len(index), "index_sha256": digest(index),
                  "extraction_version": extraction, "normalization_version": "lf/1",
                  "classification": "static_text", "physical_page_count": len(pages) if pages is not None else None,
                  "parser_warning_count": parser_warning_count}
    encode(provenance, limits["provenance_bytes"])
    return {"original": body, "text": encoded, "index": index, "provenance": provenance,
            "extraction_version": extraction, "normalization_version": "lf/1", "media_type": media}


def pack_component(data: bytes) -> dict:
    return {"base64": base64.b64encode(data).decode("ascii"), "byte_length": len(data), "sha256": digest(data)}


def unpack_component(component: dict, cap: int) -> bytes:
    if set(component) != {"base64", "byte_length", "sha256"} or type(component["byte_length"]) is not int or not 0 <= component["byte_length"] <= cap:
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Invalid component descriptor")
    if not isinstance(component["base64"], str) or len(component["base64"]) > 4 * ((cap + 2) // 3):
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Encoded component exceeds limit")
    try: data = base64.b64decode(component["base64"], validate=True)
    except (ValueError, TypeError) as exc: raise ToolFault("WORKER_PROTOCOL_ERROR", "Invalid component base64") from exc
    if len(data) != component["byte_length"] or digest(data) != component["sha256"] or base64.b64encode(data).decode() != component["base64"]:
        raise ToolFault("WORKER_PROTOCOL_ERROR", "Component content does not match descriptor")
    return data


def fetch(arguments: dict, plan: dict, limits: dict, timeout: float) -> tuple[dict, dict, dict]:
    info, proposal = {}, None
    def headers(received, _):
        nonlocal info
        info = received
    try:
        body, info, _ = request_body(arguments["url"], cap=limits["raw_bytes"], timeout=timeout, on_headers=headers)
        status = info["http_status"]
        if status == 206: raise ToolFault("PARTIAL_RESPONSE", "Partial HTTP responses are not complete documents")
        if not 200 <= status < 300: raise ToolFault("FETCH_HTTP_ERROR", "Source returned a non-success HTTP status", details={"http_status": status})
        proposal = extract(body, info, limits)
    except ToolFault as fault:
        fault.observations = {"http_status": info.get("http_status"), "redirects": info.get("redirects", []),
            "final_url": info.get("final_url", arguments["url"]), "extraction_version": None}
        fault.usage = {"http_request_count": info.get("http_request_count", fault.details.get("http_request_count")),
            "http_response_count": info.get("http_response_count", fault.details.get("http_response_count")),
            "decoded_body_bytes": info.get("response_decoded_bytes"), "text_utf8_bytes": None, "monetary_cost": None}
        fault.details = {"http_status": info.get("http_status"), **({"classification": fault.details["classification"]} if "classification" in fault.details else {})}
        raise
    prepared = {"operation_id": plan["operation_id"], "proposal": {**proposal,
                 **{key: pack_component(proposal[key]) for key in ("original", "text", "index")}}}
    observations = {"http_status": status, "redirects": info["redirects"], "final_url": info["final_url"],
                    "extraction_version": proposal["extraction_version"]}
    usage = {"http_request_count": info["http_request_count"], "http_response_count": info["http_response_count"],
             "decoded_body_bytes": len(body), "text_utf8_bytes": len(proposal["text"]), "monetary_cost": None}
    return prepared, observations, usage
