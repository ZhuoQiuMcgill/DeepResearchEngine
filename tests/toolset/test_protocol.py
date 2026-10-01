from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

from ebd.toolset.common import ToolFault, digest, encode, strict_json, validate_arguments
from ebd.toolset.retrieval import build_index, decode_text, extract, pack_component, unpack_component
from ebd.toolset.scholarly import capture_limits, parse_limits, project, request_url
from ebd.toolset.search import CorrectedGoogle, PreservedYahoo, google_destination, yahoo_destination


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'\xef\xbb\xbf{}', b'{}{}', br'"\ud800"'])
def test_strict_json_rejects_invalid(raw):
    with pytest.raises(ToolFault): strict_json(raw, 1024)


def test_exact_encoded_cap_and_depth():
    value = {"x": "\\\"\n中" * 100}
    raw = encode(value)
    assert strict_json(raw, len(raw)) == value
    with pytest.raises(ToolFault): encode(value, len(raw) - 1)
    deep = "[" * 34 + "0" + "]" * 34
    with pytest.raises(ToolFault): strict_json(deep.encode(), 1024)


@pytest.mark.parametrize("args", [{"query": "x", "max_results": True}, {"query": " "}, {"query": "x", "backend": "google"}, {"query": "中" * 1366}])
def test_closed_queries(args):
    with pytest.raises(ToolFault): validate_arguments("web.search", args)


@pytest.mark.parametrize("target", ["https://example.com/a%2Fb?q=a%26b&plus=%2B&literal=+", "https://example.com/path+a?q=one&b=two", "https://example.com/?x=%2526"])
def test_raw_google_and_yahoo_preserve_destination(target):
    from urllib.parse import quote
    google = "/url?q=" + quote(target, safe="") + "&sa=U"
    yahoo = "https://r.search.yahoo.com/_ylt=x/RU=" + quote(target, safe="") + "/RK=2/RS=x"
    assert google_destination(google) == target
    assert yahoo_destination(yahoo) == target
    # Integrated DDGS extraction bypasses stock TextResult URL unquote.
    g = CorrectedGoogle()
    markup = '<div><div><a href="' + google.replace("&", "&amp;") + '"><span>Title</span></a></div><div><table>Snippet</table></div></div>'
    assert g.post_extract_results(g.extract_results(markup))[0].href == target
    y = PreservedYahoo()
    markup = '<div class="relsrch"><div class="Title"><h3>Title</h3><a href="' + yahoo + '"></a></div><div class="Text">Snippet</div></div>'
    assert y.post_extract_results(y.extract_results(markup))[0].href == target


@pytest.mark.parametrize("raw", ["/url?q=https%3A%2F%2Fexample.com&q=x", "/url?q=https%3A%2F%2Fexample.com%3Fa%3D1&b=2", "/url?q=javascript%3Aalert(1)"])
def test_google_rejects_ambiguous_wrappers(raw):
    with pytest.raises(ToolFault): google_destination(raw)


@pytest.mark.parametrize("text,count", [(b"", 0), (b"a", 1), (b"a\n", 1), (b"\n", 1), (b"a\n\n", 2), (b"a\fb", 1)])
def test_logical_lines_do_not_create_phantoms(text, count):
    index = build_index(text, None)
    assert len(index["lines"]) == count
    for span in index["lines"]: assert b"\n" not in text[span["start_byte"]:span["end_byte"]]


def test_plain_utf16_and_exact_normalization():
    source = "中\r\n\ttext\f\rnext\n"
    body = source.encode("utf-16")
    info = {"content_type": "text/plain", "http_status": 200}
    proposal = extract(body, info)
    assert proposal["original"] == body
    assert proposal["text"] == "中\n\ttext\f\nnext\n".encode()
    assert json.loads(proposal["index"])["text_sha256"] == digest(proposal["text"])
    with pytest.raises(ToolFault): decode_text(body, "text/plain; charset=utf-8")
    with pytest.raises(ToolFault): decode_text(b"a\0b", "text/plain")
    with pytest.raises(ToolFault): decode_text(b"\xff", "text/plain")


def test_component_max_fit_hash_and_canonical_base64():
    body = b"a" * 1024
    assert unpack_component(pack_component(body), 1024) == body
    with pytest.raises(ToolFault): unpack_component(pack_component(body + b"b"), 1024)
    bad = pack_component(body); bad["sha256"] = digest(b"changed")
    with pytest.raises(ToolFault): unpack_component(bad, 1024)


def test_header_capture_projection_both_provider_units():
    captured = capture_limits("openalex", [(b"x-ratelimit-remaining-usd", b"0"), (b"x-ratelimit-cost-usd", b"0.002"), (b"x-ratelimit-remaining", b"0"), (b"x-ratelimit-credits-used", b"20"), (b"x-ratelimit-reset", b"60")])
    parsed = parse_limits("openalex", captured, datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert parsed["remaining_microusd"] == 0
    assert parsed["cost_microusd"] == 2000
    assert parsed["remaining_credits"] == 0 and parsed["cost_credits"] == 20
    assert parsed["currency"] == "USD" and parsed["credit_unit"] == "openalex_credit"
    assert parsed["reset_at"] == "2026-10-01T00:01:00+00:00"
    assert "openalex_remaining_usd" not in parsed["missing_fields"]


def test_duplicates_unknown_and_overflow_remain_invalid():
    capture = capture_limits("openalex", [(b"x-ratelimit-cost-usd", b"0.001"), (b"x-ratelimit-cost-usd", b"0.002"), (b"retry-after", b"bogus")])
    parsed = parse_limits("openalex", capture)
    assert parsed["invalid_fields"] == ["openalex_cost_usd", "retry_after"]
    capture["reservation"] = {"balance": 100}
    with pytest.raises(ToolFault): parse_limits("openalex", capture)
    capture = capture_limits("crossref", [(b"x-rate-limit-limit", b"9007199254740992"), (b"x-rate-limit-interval", b"0s")])
    assert parse_limits("crossref", capture)["invalid_fields"] == ["crossref_rate_limit", "crossref_rate_interval"]


def test_literal_scholarly_query_transport_and_smaller_url_cap():
    query = '"Environment Based Design" + 汉字 %26'
    from urllib.parse import parse_qs, urlsplit
    for provider, parameter in (("crossref", "query.bibliographic"), ("openalex", "search")):
        assert parse_qs(urlsplit(request_url(provider, {"query": query, "max_results": 3})).query)[parameter] == [query]
    with pytest.raises(ToolFault): request_url("openalex", {"query": "中" * 600, "max_results": 3})


def test_actual_max_components_fit_fetch_envelope_and_aggregate_is_bounded():
    sizes = {"original": 8 << 20, "text": 4 << 20, "index": 1 << 20}
    prepared = {key: pack_component(b"a" * size) for key, size in sizes.items()}
    envelope = {"prepared": prepared, "metadata": "quoted \\\"" * 1000}
    result = encode(envelope, 20 << 20)
    assert 17 << 20 < len(result) < 20 << 20
    for key, size in sizes.items(): assert unpack_component(prepared[key], size) == b"a" * size
    with pytest.raises(ToolFault): encode({"prepared": prepared, "metadata": "\\" * (2 << 20)}, 20 << 20)


def pdf_fixture(page_texts, *, encrypted=False):
    import io
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if text is not None:
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 10 10 Td (" + text.encode("ascii") + b") Tj ET")
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            page[NameObject("/Contents")] = writer._add_object(stream)
            page.compress_content_streams()
    if encrypted: writer.encrypt("test-password")
    body = io.BytesIO(); writer.write(body)
    return body.getvalue()


def test_pdf_empty_physical_pages_and_compressed_expansion_limits():
    body = pdf_fixture(["first", None, "last"])
    result = extract(body, {"content_type": "application/pdf"})
    index = json.loads(result["index"])
    assert len(index["pages"]) == 3
    assert index["pages"][1]["start_byte"] == index["pages"][1]["end_byte"]
    assert result["original"] == body
    assert result["text"] == b"first\n\nlast"
    expanded = pdf_fixture(["a" * 100000])
    assert len(expanded) < 10000
    with pytest.raises(ToolFault) as caught: extract(expanded, {"content_type": "application/pdf"}, {"text_bytes": 1024})
    assert caught.value.code == "TEXT_LIMIT"
    with pytest.raises(ToolFault) as caught: extract(pdf_fixture([None]), {"content_type": "application/pdf"})
    assert caught.value.code == "PDF_NO_TEXT"
    with pytest.raises(ToolFault) as caught: extract(pdf_fixture(["secret"], encrypted=True), {"content_type": "application/pdf"})
    assert caught.value.code == "PDF_ENCRYPTED"
