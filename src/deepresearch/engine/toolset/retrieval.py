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



_HTML_EXTRACTION = "html_article/1+trafilatura/2.2.0"
_ABSTRACT_NAMES = {"abstract", "articleabstract", "abstracttext", "abstractcontent", "abstractsection", "abstractbody"}
_BODY_NAMES = {"articlebody", "articlecontent", "articletext", "fulltext", "fulltextcontent", "bodytext"}
_REFERENCE_NAMES = {"reference", "references", "referencelist", "referenceslist", "refs", "reflist", "bibliography", "referencessection"}
_NOISE_NAMES = {"nav", "navigation", "navbar", "menu", "sidebar", "toolbar", "social", "share", "sharing",
                "related", "relatedarticles", "recommendedarticles", "recommendations", "advertisement", "ads",
                "cookiebanner", "citationtools", "metrics", "hidden", "sronly", "visuallyhidden", "paywallcontent"}
_HTML_BLOCKS = {"article", "section", "main", "div", "p", "h1", "h2", "h3", "h4", "h5", "h6",
                "ul", "ol", "li", "table", "tr", "td", "th", "blockquote", "pre", "br", "dl", "dt", "dd"}
_CITATION_FIELDS = (
    ("Title", ("citation_title", "dc.title")),
    ("Authors", ("citation_author", "citation_authors", "dc.creator")),
    ("Publication date", ("citation_publication_date", "citation_date", "dc.date")),
    ("Online date", ("citation_online_date",)),
    ("Journal", ("citation_journal_title",)),
    ("DOI", ("citation_doi",)),
    ("Volume", ("citation_volume",)),
    ("Issue", ("citation_issue",)),
    ("First page", ("citation_firstpage",)),
    ("Last page", ("citation_lastpage",)),
    ("Keywords", ("citation_keywords",)),
)


def _html_names(node) -> set[str]:
    # Whitespace separates class names. Do not confuse 'reference-implementation'
    # or 'abstract-art' with actual reference/abstract containers.
    return {re.sub(r"[^a-z0-9]", "", value.lower())
            for value in ((node.get("id") or "") + " " + (node.get("class") or "")).split()}


def _html_text(node) -> str:
    from lxml import etree
    parts = []
    for event, element in etree.iterwalk(node, events=("start", "end")):
        if element.tag in _HTML_BLOCKS: parts.append("\n")
        if event == "start" and element.text: parts.append(element.text)
        if event == "end" and element is not node and element.tail: parts.append(element.tail)
    # Preserve inline concatenation, paragraph/table boundaries and literal data.
    return "\n".join(line for raw in normalize("".join(parts)).split("\n")
                     if (line := " ".join(raw.split())))


def _html_top_nodes(root, nodes) -> list:
    selected = set(nodes)
    return [node for node in root.iter() if node in selected
            and not any(parent in selected for parent in node.iterancestors())]


def _html_heading_scope(node) -> list:
    """A labelled section or following siblings, never an entire enclosing article."""
    heading = node
    while heading is not None and heading.tag not in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        heading = heading.getparent()
    if heading is None: return [node]
    parent = heading.getparent()
    if parent is None: return [heading]
    if "panelheading" in _html_names(parent):
        panel = parent.getparent()
        if panel is not None and "panel" in _html_names(panel): return [panel]
    if (parent.tag in {"div", "section"} and len(parent) and parent[0] is heading
            and not any(child is not heading and child.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}
                        and child.tag <= heading.tag for child in parent.iter())):
        return [parent]
    siblings = [heading]
    for sibling in heading.itersiblings():
        if sibling.tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and sibling.tag <= heading.tag: break
        siblings.append(sibling)
    return siblings


def _html_access_url(value: str, info: dict) -> str | None:
    value = value.strip()
    if not value or value.startswith(("#", "javascript:", "data:")): return None
    try:
        base = info.get("final_url") or info.get("requested_url") or ""
        # Resolution uses only the known response URL, never a page-controlled base
        # or JavaScript onclick. URL validation performs no DNS/network access.
        return url(urljoin(base, value))
    except (ToolFault, ValueError):
        return None


def _extract_html(source: str, info: dict) -> tuple[str, str]:
    """Retain visible same-body article sections and labelled public metadata."""
    from lxml import html
    import trafilatura
    try:
        root = html.document_fromstring(source.encode("utf-8"), parser=html.HTMLParser(
            encoding="utf-8", no_network=True, remove_comments=True,
        ))
    except (ValueError, html.etree.ParserError) as exc:
        raise ToolFault("EXTRACTION_EMPTY", "Static HTML has no extractable document text") from exc
    meta = {}
    for node in root.xpath("//head/meta[@name or @property]"):
        name = (node.get("name") or node.get("property") or "").lower()
        value = " ".join((node.get("content") or "").split())
        if value and value not in meta.setdefault(name, []): meta[name].append(value)
    for node in list(root.iter()):
        if node is root or node.getparent() is None: continue
        style = node.get("style") or ""
        if (node.tag in {"script", "style", "noscript", "template", "nav", "aside", "footer", "iframe", "object", "embed",
                         "input", "select", "textarea", "button"}
                or "hidden" in node.attrib or (node.get("aria-hidden") or "").lower() == "true"
                or re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", style, re.I)
                or (node.get("role") or "").lower() in {"navigation", "menu", "menubar", "search"}
                or _html_names(node) & _NOISE_NAMES):
            node.drop_tree()
    # Publisher forms can wrap real article text. Only discard their controls;
    # unwrapping prevents trafilatura from dropping a legitimate abstract form.
    for node in list(root.iter("form")): node.drop_tag()
    metadata = []
    for label, names in _CITATION_FIELDS:
        for name in names:
            if meta.get(name):
                metadata.append(label + ": " + "; ".join(meta[name]))
                break
    if not any(item.startswith("Title:") for item in metadata):
        title = root.xpath("//article//h1 | //main//h1")
        if title and _html_text(title[0]): metadata.insert(0, "Title: " + " ".join(_html_text(title[0]).split()))
    reference_nodes = []
    for node in root.iter():
        if _html_names(node) & _REFERENCE_NAMES:
            reference_nodes.extend(_html_heading_scope(node) if node.tag in {"a", "h1", "h2", "h3", "h4", "h5", "h6"} else [node])
        elif node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and _html_text(node).strip(" :：").lower() in {"references", "bibliography", "reference list"}:
            reference_nodes.extend(_html_heading_scope(node))
    references = []
    for node in _html_top_nodes(root, reference_nodes):
        value = _html_text(node)
        if len(value) >= 20: references.append(value)
        node.drop_tree()
    access_urls = set()
    for name in ("citation_pdf_url", "citation_fulltext_html_url", "citation_abstract_html_url"):
        for value in meta.get(name, []):
            target = _html_access_url(value, info)
            if target and target not in access_urls:
                metadata.append(f"Access URL ({name}; not fetched): {target}")
                access_urls.add(target)
    for node in root.iter("a"):
        label, href = " ".join(_html_text(node).split()), node.get("href") or ""
        try: pdf_path = urlsplit(href).path.lower().endswith(".pdf")
        except ValueError: pdf_path = False
        if (re.fullmatch(r"(?:view\s+|download\s+)?(?:pdf|full\s*text)(?:\s*\([^)]*\))?(?:\s*\d+)?", label, re.I)
                or pdf_path):
            target = _html_access_url(href, info)
            if target and target not in access_urls:
                metadata.append(f"Access URL (same-body href; not fetched): {target}")
                access_urls.add(target)
    abstract_nodes = []
    for node in root.iter():
        if node.tag in {"div", "section", "p"} and _html_names(node) & _ABSTRACT_NAMES:
            abstract_nodes.append(node)
        elif node.tag == "p" and re.match(r"^(?:abstract|摘要)\s*[:：]", _html_text(node), re.I):
            abstract_nodes.append(node)
    # A standalone Abstract heading may introduce multiple paragraphs. If a
    # labelled paragraph already supplies it, avoid taking a whole tab panel
    # (which may also contain keyword, share and citation-manager widgets).
    for node in root.iter():
        if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and _html_text(node).strip(" :：").lower() in {"abstract", "摘要"}:
            scope = _html_heading_scope(node)
            if not any(candidate is section or section in candidate.iterancestors()
                       for section in scope for candidate in abstract_nodes):
                abstract_nodes.extend(scope)
    abstracts = []
    for node in _html_top_nodes(root, abstract_nodes):
        value = _html_text(node)
        if len(value) >= 20: abstracts.append(value)
        node.drop_tree()
    if not abstracts and meta.get("citation_abstract"):
        abstracts.extend("Abstract (citation_abstract metadata): " + value for value in meta["citation_abstract"])
    bodies = []
    explicit = [node for node in root.iter() if node.tag in {"div", "section", "article", "main"}
                and (_html_names(node) & _BODY_NAMES or "articleBody" in (node.get("itemprop") or "").split())]
    for candidates, marked in ((explicit, True), (list(root.iter("article")), False), (list(root.iter("main")), False)):
        for node in _html_top_nodes(root, candidates):
            value = _html_text(node)
            substantive = marked or any(len(_html_text(p)) >= 40 for p in node.iter("p")) or len(" ".join((node.text or "").split())) >= 80
            if len(value) >= 40 and substantive: bodies.append(value)
        if bodies: break
    sections = []
    if metadata: sections.append("[Same-body article metadata; not article full text]\n" + "\n".join(metadata))
    if abstracts: sections.append("[Same-body abstract; not full text]\n" + "\n\n".join(dict.fromkeys(abstracts)))
    if bodies:
        sections.append("[Same-body article body; completeness not verified]\n" + "\n\n".join(dict.fromkeys(bodies)))
        classification = "article_body"
    elif abstracts:
        classification = "article_abstract"
    else:
        # A generic page still uses trafilatura. Exclude references/navigation
        # before selection so a large bibliography cannot win over article prose.
        fallback = trafilatura.extract(html.tostring(root, encoding="unicode"), include_comments=False,
                                       include_tables=True, output_format="txt")
        if fallback and fallback.strip():
            sections.append("[Same-body extracted text; article coverage unverified]\n" + normalize(fallback) if metadata or references else normalize(fallback))
        classification = "article_metadata" if metadata and not fallback else "static_text"
    if references: sections.append("[Same-body references; not article body]\n" + "\n\n".join(dict.fromkeys(references)))
    text = "\n\n".join(sections)
    if not text.strip(): raise ToolFault("EXTRACTION_EMPTY", "Static HTML has no extractable document text")
    return text, classification

def extract(body: bytes, info: dict, limits: dict | None = None) -> dict:
    limits = LIMITS | (limits or {})
    content_type = info["content_type"]
    media = content_type.split(";", 1)[0].strip().lower()
    pages, charset, charset_source = None, None, None
    parser_warning_count = 0
    classification = "static_text"
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
        if len(body) > limits["raw_bytes"]:
            raise ToolFault("RESPONSE_LIMIT", "Source component exceeds limit", status="limit_exhausted")
        source, charset, charset_source = decode_text(body, content_type, html=True)
        lowered = source.lower()
        if any(marker in lowered for marker in ("cf-chl-", "verify you are human", "just a moment...", "enable javascript and cookies to continue")):
            raise ToolFault("SOURCE_CHALLENGE", "Source requires interactive access")
        text, classification = _extract_html(source, info)
        text, extraction = normalize(text), _HTML_EXTRACTION
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
                  "classification": classification, "physical_page_count": len(pages) if pages is not None else None,
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
