"""Regression checks for explicit fallback, URL fidelity and diagnostic facts."""
from types import SimpleNamespace
from urllib.parse import quote

from jsonschema import Draft202012Validator
import pytest

from deepresearch.engine.toolset import ToolCatalog
from deepresearch.engine.toolset.common import ToolFault
from deepresearch.engine.toolset.search import (
    PreservedYahoo, RawTextResult, advertising_url, duckduckgo_destination,
    preserves_query, search, search_plan,
)


def engines(monkeypatch, yahoo_status=403, yahoo_rows=(), duck_status=200, duck_rows=()):
    from deepresearch.engine.toolset import search as module
    calls = []
    def factory(status, rows, backend):
        class FakeEngine:
            search_method, search_url = "GET", "https://example.org/search"
            def __init__(self, timeout):
                self.http_client = SimpleNamespace(client=SimpleNamespace(request=self.response))
                self.responses = list(status) if isinstance(status,list) else [(status,{})]
            def request(self, *args, **kwargs):
                raise AssertionError("Observed transport must replace the stock request")
            def response(self, method, source, **kwargs):
                calls.append((backend, kwargs))
                response = self.responses[0]
                if len(self.responses) > 1:
                    self.responses.pop(0)
                if isinstance(response, Exception):
                    raise response
                current, headers = response
                return SimpleNamespace(status_code=current, text="<html>search response</html>",content=b"<html>search response</html>",headers=headers)
            def build_payload(self, query, *args, **kwargs):
                return {"q":query}
            def extract_results(self, html):
                return [SimpleNamespace(**row) for row in rows]
        return FakeEngine
    monkeypatch.setattr(module, "PreservedYahoo", factory(yahoo_status, yahoo_rows, "yahoo"))
    monkeypatch.setattr(module, "PreservedDuckduckgo", factory(duck_status, duck_rows, "duckduckgo"))
    return calls


def test_named_fallback_records_http_failure_and_preserves_literal_query(monkeypatch):
    target = "https://example.org/a%2Fb?x=a%26b&plus=%2B&literal=+"
    wrapper = "https://duckduckgo.com/l/?uddg=" + quote(target, safe="")
    calls = engines(monkeypatch, duck_rows=[{"title":"Research", "href":wrapper,"body":"Discovery"}])
    query = '"environment based design" + 中文 %26'
    payload, observations, usage, fault = search({"query":query,"max_results":5}, search_plan(2), 30, 2)
    assert fault is None and payload["query"] == query
    assert payload["results"][0]["url"] == target
    assert [name for name, _ in calls] == ["yahoo", "duckduckgo"]
    assert all(kwargs["params"]["q"] == query and kwargs["follow_redirects"] is False for _, kwargs in calls)
    first, second = observations["backend_attempts"]
    assert first["http_status"] == 403 and first["failure_reason"] == "http_error"
    assert second["extracted_count"] == second["returned_count"] == second["kept_count"] == 1
    assert usage["http_request_count"] == usage["http_response_count"] == 2
    assert not list(Draft202012Validator(ToolCatalog().resolve("web.search", 2).unwrap().output_schema).iter_errors(payload))


def test_ads_hidden_inside_yahoo_wrapper_do_not_stop_fallback(monkeypatch):
    ad = "https://r.search.yahoo.com/_ylt=x/RU=" + quote("https://www.bing.com/aclick?x=ad",safe="") + "/RK=2/RS=x"
    calls = engines(monkeypatch, yahoo_status=200, yahoo_rows=[{"title":"Ad", "href":ad,"body":"Sponsored"}], duck_status=202)
    payload, observations, usage, fault = search({"query":"paper","max_results":5}, search_plan(2), 30, 2)
    assert payload is None and fault.code == "SEARCH_UNAVAILABLE"
    assert len(calls) == usage["search_backend_attempts"] == 2
    first, second = observations["backend_attempts"]
    assert first["advertisement_count"] == 1 and first["failure_reason"] == "all_candidates_rejected"
    assert second["http_status"] == 202 and second["failure_reason"] == "http_challenge"
    assert advertising_url("https://www.bing.com/aclick?x=ad")
    row = RawTextResult(title="Ad",href=ad,body="Sponsored")
    assert PreservedYahoo().post_extract_results([row]) == []


def test_success_does_not_call_another_backend_or_merge(monkeypatch):
    calls = engines(monkeypatch, yahoo_status=200, yahoo_rows=[{"title":"Paper", "href":"https://example.org/paper","body":"Abstract"}])
    payload, observations, usage, fault = search({"query":"paper","max_results":5}, search_plan(2), 30, 2)
    assert fault is None and len(calls) == usage["http_request_count"] == 1
    assert payload["results"][0]["backend"] == "yahoo"


def test_redirects_are_explicit_counted_and_query_preserving(monkeypatch):
    query = '"design" + 中文 %26'
    target = "https://example.org/search?p=" + quote(query,safe="")
    calls = engines(monkeypatch,yahoo_status=[(307,{"location":target}),(200,{})],
        yahoo_rows=[{"title":"Paper","href":"https://example.org/paper","body":"Abstract"}])
    payload,observations,usage,fault = search({"query":query,"max_results":5},search_plan(2),30,2)
    assert fault is None and payload["results"]
    assert len(calls) == usage["http_request_count"] == usage["http_response_count"] == 2
    attempt = observations["backend_attempts"][0]
    assert attempt["http_status"] == 200
    assert attempt["redirects"] == [{"from_url":"https://example.org/search","to_url":target,"http_status":307}]


@pytest.mark.parametrize("target",["https://evil.example/search?p=paper","https://example.org/search?p=different"])
def test_redirect_cannot_change_provider_or_query(monkeypatch,target):
    calls = engines(monkeypatch,yahoo_status=[(307,{"location":target})],duck_status=202)
    payload,observations,usage,fault = search({"query":"paper","max_results":5},search_plan(2),30,2)
    assert payload is None and fault.code == "SEARCH_UNAVAILABLE"
    assert len(calls) == 2 and observations["backend_attempts"][0]["failure_reason"] == "redirect_denied"


def test_yahoo_verification_redirect_keeps_embedded_query_bound_to_provider():
    query = '"design" + 中文 %26'
    original = "/search?p=" + quote(query,safe="")
    target = "https://search.yahoo.com/_bv/v.gif?orig=" + quote(original,safe="") + "&_bvc=opaque"
    assert preserves_query(target,"yahoo","search.yahoo.com",query)
    assert not preserves_query(target,"yahoo","search.yahoo.com","different")
    assert not preserves_query(target + "&orig=x","yahoo","search.yahoo.com",query)
    evil = target.replace(quote(original,safe=""),quote("https://evil.example/search?p=" + quote(query,safe=""),safe=""))
    assert not preserves_query(evil,"yahoo","search.yahoo.com",query)


def test_transport_failure_after_redirect_remains_a_transport_failure(monkeypatch):
    calls = engines(monkeypatch,yahoo_status=[(307,{"location":"https://example.org/search?p=paper"}),
        TimeoutError("provider timed out")],duck_status=202)
    payload,observations,usage,fault = search({"query":"paper","max_results":5},search_plan(2),30,2)
    assert payload is None and fault.code == "SEARCH_UNAVAILABLE"
    first = observations["backend_attempts"][0]
    assert first["failure_reason"] == "transport_error"
    assert first["http_request_count"] == 2 and first["http_response_count"] == 1
    assert len(calls) == usage["http_request_count"] == 3


def test_parser_failure_cannot_publish_partially_parsed_candidates(monkeypatch):
    calls = engines(monkeypatch,yahoo_status=200,yahoo_rows=[
        {"title":"Paper","href":"https://example.org/paper","body":"Abstract"},
        {"title":"Malformed","href":None,"body":"Not a text result"}],duck_status=202)
    payload,observations,usage,fault = search({"query":"paper","max_results":5},search_plan(2),30,2)
    assert payload is None and fault.code == "SEARCH_UNAVAILABLE"
    assert observations["backend_attempts"][0]["failure_reason"] == "parser_error"
    assert len(calls) == usage["search_backend_attempts"] == 2


def test_unregistered_fallback_plan_is_rejected_before_transport():
    plan = search_plan(2)
    plan["backend_order"].append("google")
    with pytest.raises(ToolFault, match="registered revision 2"):
        search({"query":"paper","max_results":5}, plan, 30, 2)


def test_duckduckgo_wrapper_rejects_ambiguous_or_non_http_targets():
    for wrapper in ("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org&uddg=x",
                    "https://duckduckgo.com/l/?uddg=javascript%3Aalert(1)"):
        with pytest.raises(ToolFault):
            duckduckgo_destination(wrapper)


def test_search_revisions_keep_distinct_profiles_and_old_output_schema():
    catalog = ToolCatalog()
    first = catalog.resolve("web.search", 1).unwrap()
    second = catalog.resolve("web.search", 2).unwrap()
    assert first.argv[-1] == "1" and second.argv[-1] == "2"
    assert first.output_schema["properties"]["backend_policy"]["properties"]["active_order"] == {"const":["yahoo"]}
    assert first.input_schema == second.input_schema
    assert set(catalog.list()[0].config) == {"profile","google_enabled"}
