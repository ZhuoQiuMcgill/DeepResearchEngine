"""Library-led generic HTML extraction; retain scholarly section provenance."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from .common import ToolFault, digest, encode
from .retrieval import build_index, decode_text, extract, normalize


def _normalize_inline_components(tree):
    """Present transparent custom inline elements as spans to the extractor.

    Unknown tags can cause the library to move links past their following text
    or drop that text entirely. Only normalize phrasing-only custom components
    inside an explicit prose block. Keep attributes, children, text and tails;
    block components, semantic roles and literal code remain untouched. This
    modifies the parsed working tree, never the archived original bytes.
    """
    inline = {"a", "span", "em", "strong", "b", "i", "u", "s", "small", "sub", "sup",
              "abbr", "mark", "q", "cite", "time", "br", "wbr", "code"}
    prose = {"p", "li", "dd", "dt", "td", "th", "caption"}
    literal = {"pre", "code", "svg", "math", "script", "style", "template"}
    # Inner components first, so a nested transparent component can qualify too.
    for node in reversed(list(tree.iter())):
        if not isinstance(node.tag, str) or not re.fullmatch(r"[a-z][a-z0-9._]*-[a-z0-9._-]+", node.tag):
            continue
        ancestors = {parent.tag for parent in node.iterancestors()}
        if not ancestors & prose or ancestors & literal or node.get("role") is not None:
            continue
        if any(child.tag not in inline for child in node.iterdescendants() if isinstance(child.tag, str)):
            continue
        node.tag = "span"


def _structured_markdown(source, tree, url):
    """Restore structure flattened by the library's short-text rescue.

    Keep the normal extraction/recall policy. A second pass may replace a flat
    result only if it preserves every retained text block (ignoring whitespace
    and explicitly marked navigation), so a short lead cannot hide a long body.
    """
    from trafilatura import bare_extraction
    from trafilatura.core import determine_returnstring
    from trafilatura.settings import Extractor, use_config

    from .html_recovery import _visible_body
    from lxml import html
    visible = _visible_body(tree)
    if visible is not None and visible.xpath('./article|./main|./*[@role="main"]'):
        # An explicit article/main is a selection boundary, not just another
        # density hint. Keep unrelated cards outside it out of both renderers.
        root = html.Element("html")
        root.append(visible)
        source = html.tostring(root, encoding="unicode")
    options = Extractor(output_format="markdown", comments=False, links=True,
                        images=True, tables=True, url=url)
    document = bare_extraction(source, options=options)
    if document is None:
        return None, None
    structural_tags = {"ref", "graphic", "code", "table", "list", "head", "hi"}
    if (not any(node.tag in structural_tags for node in document.body.iter())
            and tree.xpath('//a[@href]|//pre|//table|//ol|//ul|//sup|//sub|//img[@alt]')):
        config = use_config()
        config.set("DEFAULT", "MIN_EXTRACTED_SIZE", "1")
        candidate = bare_extraction(source, options=Extractor(config=config,
            output_format="markdown", comments=False, links=True, images=True, tables=True, url=url))
        if candidate is not None and any(node.tag in structural_tags for node in candidate.body.iter()):
            compact = lambda value: "".join(value.split())
            candidate_text = compact("".join(candidate.body.itertext()))
            navigation = [compact("".join(node.itertext())) for node in tree.xpath('//nav')]
            retained = [compact("".join(node.itertext())) for node in document.body]
            for index, block in enumerate(retained):
                for nav in navigation:
                    if nav:
                        block = block.replace(nav, "")
                retained[index] = block
            if all(block in candidate_text for block in retained):
                document = candidate
    from .html_recovery import recover_document
    document, diagnostic = recover_document(tree, document, options)
    from .html_structure import recover_structure
    text, structural = recover_structure(tree, document, determine_returnstring(document, options))
    diagnostic["structure"] = structural
    from .html_graphics import unbound_diagnostic
    graphics = structural.pop('graphics', None) or unbound_diagnostic(visible)
    if graphics:
        diagnostic['graphics'] = graphics
    return text, diagnostic


def _image_links(text, tree):
    """Retain destinations on retained image-only anchors after body selection.

    Adding labels to the input DOM changes the extractor's content-density
    decisions. Work on already selected images instead, using the same escaping
    as the pinned library. An image reused by different anchors keeps all its
    source-declared destinations rather than guessing a unique association.
    """
    from trafilatura.xml import _md_link

    links = {}
    for anchor in tree.xpath('//a[@href][.//img[@src]]'):
        target = anchor.get("href")
        if anchor.text_content().strip() or not target.startswith(("https://", "http://")):
            continue
        for node in anchor.xpath('.//img[@src]'):
            label = node.get("alt") or ""
            image = _md_link(label, node.get("src"), image=True)
            if image in text:
                link = _md_link(label or "Image link", target)
                if link not in links.setdefault(image, []):
                    links[image].append(link)
    for image, targets in links.items():
        def append_missing(match):
            # A structure renderer may already have retained the outer anchor.
            if match.start() and text[match.start() - 1] == '[' and text[match.end():].startswith(']('):
                return image
            return image + " (" + ", ".join(targets) + ")"
        text = re.sub(re.escape(image), append_missing, text)
    return text


def extract_source(body, info, limits):
    media = info["content_type"].split(";", 1)[0].strip().lower()
    if media not in {"text/html", "application/xhtml+xml"}:
        return extract(body, info, limits, recover_pdf=media == "application/pdf")
    if len(body) > limits["raw_bytes"]:
        raise ToolFault("RESPONSE_LIMIT", "Source component exceeds limit", status="limit_exhausted")
    if body.startswith(b"%PDF-"):
        raise ToolFault("CONTENT_TYPE_MISMATCH", "PDF bytes disagree with declared media type")
    from lxml import html
    from .browser_capture import _reject_access
    _reject_access(body, info["http_status"])
    source, charset, charset_source = decode_text(body, info["content_type"], html=True)
    try:
        tree = html.document_fromstring(source, parser=html.HTMLParser(no_network=True))
    except (ValueError, html.etree.ParserError) as error:
        raise ToolFault("EXTRACTION_EMPTY", "HTML contains no document") from error
    scholarly = tree.xpath('//meta[@name="citation_doi" or @name="citation_title" or @name="citation_journal_title"]')
    from .document_metadata import declared_dates
    from .html_structured_data import append_structured_data
    dates = declared_dates(tree)
    if scholarly:
        # These pages need explicit abstract/metadata/reference boundaries and
        # access URLs. In particular, a publisher HTML landing page is not PDF.
        proposal = extract(body, info, limits)
        proposal["provenance"]["document_dates"] = dates
        if proposal["provenance"]["classification"] == "article_body":
            proposal["provenance"]["classification"] = "article_sections_unverified"
        proposal['extraction_version'] += '+inline-jsonld/1'
        proposal['provenance']['extraction_version'] = proposal['extraction_version']
        append_structured_data(proposal, tree, limits)
        encode(proposal["provenance"], limits["provenance_bytes"])
        return proposal
    # Retain image alt text: dropping image-bearing containers can also remove
    # the product names that label a comparison table's columns. No images are
    # downloaded; this keeps only source-provided text/URLs in Markdown.
    # The library's origin-only URL base loses paths for relative links and
    # fragments. Resolve explicit document links before extraction, without
    # changing the original archived bytes or making any network request.
    bases = tree.xpath("//head/base[@href]/@href")
    base_url = info["final_url"]
    if bases:
        try:
            candidate_base = urljoin(base_url, bases[0])
            if urlsplit(candidate_base).scheme in {"http", "https"}:
                base_url = candidate_base
        except ValueError:
            pass  # A malformed source link cannot invalidate usable body text.
    for element in tree.xpath("//a[@href]|//img[@src]"):
        attribute = "href" if element.tag == "a" else "src"
        try:
            destination = urljoin(base_url, element.get(attribute))
            if urlsplit(destination).scheme in {"http", "https"}:
                element.set(attribute, destination)
        except ValueError:
            continue
    # Keep the library's normal string-input preparation (including comment
    # removal); passing our pre-parsed tree bypasses that cleanup.
    _normalize_inline_components(tree)
    resolved_html = html.tostring(tree, encoding="unicode")
    text, diagnostic = _structured_markdown(resolved_html, tree, info["final_url"])
    if not text or text.strip().lower() in {"skip to content", "skip to main content"}:
        raise ToolFault("EXTRACTION_EMPTY", "HTML contains no extractable source text")
    if len(text) < 1000 and re.search(r"cookies must be enabled|enable cookies.{0,100}reload", text, re.I | re.S):
        raise ToolFault("SOURCE_CHALLENGE", "Source returned a cookie challenge rather than document text")
    text = _image_links(text, tree)
    encoded = normalize(text).encode("utf-8")
    if len(encoded) > limits["text_bytes"]:
        raise ToolFault("RESPONSE_LIMIT", "Extracted text exceeds limit", status="limit_exhausted")
    from .html_recovery import finalize_diagnostic, recover_rendered_prose
    diagnostic = finalize_diagnostic(tree, encoded.decode('utf-8'), diagnostic)
    recovered, diagnostic = recover_rendered_prose(tree, encoded.decode('utf-8'), diagnostic)
    if diagnostic.get('prose_render_recovery_applied'):
        encoded = normalize(recovered).encode('utf-8')
        if len(encoded) > limits['text_bytes']:
            raise ToolFault('RESPONSE_LIMIT', 'Extracted text exceeds limit', status='limit_exhausted')
        diagnostic = finalize_diagnostic(tree, encoded.decode('utf-8'), diagnostic)
    index = encode(build_index(encoded, None), limits["index_bytes"])
    extraction = "trafilatura_markdown/17+trafilatura/2.2.0+markdownify/1.2.3"
    graphics = diagnostic.get('graphics') or {}
    provenance = {**info, "representation": "content_decoded", "media_type": media,
        "chosen_charset": charset, "charset_source": charset_source,
        "original_bytes": len(body), "original_sha256": digest(body),
        "text_bytes": len(encoded), "text_sha256": digest(encoded),
        "index_bytes": len(index), "index_sha256": digest(index),
        "extraction_version": extraction, "normalization_version": "lf/1",
        "classification": "web_text_unverified", "physical_page_count": None,
        "parser_warning_count": (int(diagnostic["substantial_omission"]) + int(diagnostic["structure"]["unresolved"])
            + int(bool(graphics) and (bool(graphics.get('unresolved_svg_count')) or not graphics.get('coverage_complete')))),
        "html_extraction": diagnostic,
        "document_dates": dates}
    proposal = {"original": body, "text": encoded, "index": index, "provenance": provenance,
        "extraction_version": extraction, "normalization_version": "lf/1", "media_type": media}
    append_structured_data(proposal, tree, limits)
    encode(proposal['provenance'], limits["provenance_bytes"])
    return proposal
