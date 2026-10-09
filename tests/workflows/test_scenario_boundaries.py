"""Model-free reproductions of failures found by the cross-scenario matrix."""
from copy import deepcopy
import pytest

from deepresearch.engine.contracts import EngineError
from deepresearch.workflows.components.search_policy import infer_topic
from deepresearch.workflows.components.retrieval import _must_stop, retrieve_candidates
from tests.workflows.test_retrieval import SearchPort, web, context


@pytest.mark.parametrize("question", [
    "Compare Meta Quest 3 (512 GB) and Apple Vision Pro (256 GB).",
    'Compare headsets for "battery life" and gaming.',
    "Compare sleep interventions (adults only).",
    "Find flights (November 15, 2026) from Guangzhou to Montreal.",
])
def test_constraints_are_not_inferred_as_the_research_subject(question):
    assert infer_topic(question) is None


@pytest.mark.parametrize("question,topic", [
    ("What is EBD (Environment Based Design)?", "Environment Based Design"),
    ("什么是 EBD（Environment Based Design）？", "Environment Based Design"),
    ('What is "event sourcing"?', "event sourcing"),
    ("What is Environment-Based Design (EBD), and how does it work?", "Environment-Based Design"),
    ("Explain RCT (randomized controlled trial).", "randomized controlled trial"),
])
def test_explicit_definition_and_matching_acronym_survive(question, topic):
    assert infer_topic(question) == topic


def throttled(name="scholar.crossref.search"):
    provider = "crossref" if "crossref" in name else "openalex"
    return {"tool": {"name": name, "revision": 2}, "status": "limit_exhausted", "result": None,
        "error": {"code": "SCHOLAR_RATE_LIMITED", "commit_state": "not_applicable",
                  "observed_effect_state": "unknown", "retryable_delivery": False,
                  "details": {"provider": provider, "http_status": 429, "observed_requests": 1, "observed_responses": 1}},
        "recording": {"status": "complete", "error": None},
        "persistence": {"required": False, "commit_state": "not_applicable", "operation_id": None, "receipt": None},
        "process": {"dispatched": True, "exit_code": 4, "termination_reason": None,
                    "cleanup": {"complete": True, "errors": [], "unconfirmed_resources": []}},
        "observations": {"scholarly_attempt": {"provider": provider, "http_status": 429,
                           "http_request_count": 1, "http_response_count": 1}}}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["scholar.crossref.search", "scholar.openalex.search"])
async def test_recorded_429_keeps_web_candidates_and_disables_provider_without_retry(name):
    outcome = throttled(name)
    original = deepcopy(outcome)
    port = SearchPort(lambda tool, args: outcome if tool == name else web(
        [("Relevant original document", "https://example.test/" + str(len(port.reads)))], args["query"]))
    items, entries = await retrieve_candidates(context(port), ["first exact query", "second exact query"],
        ["web.search", name], 5, topic=None, recovery_limit=0, rewrite_queries=False, screen_candidates=False)
    assert len(items) == 2
    assert sum(tool == name for tool, _ in port.reads) == 1
    failed = next(entry for entry in entries if entry["tool"] == name)
    assert port.artifact(failed["artifact_ref"]) == original
    assert outcome == original


@pytest.mark.parametrize("path,value", [
    (("status",), "unknown"), (("status",), "cancelled"),
    (("error", "commit_state"), "unknown"), (("persistence", "commit_state"), "unknown"),
    (("recording", "status"), "incomplete"), (("process", "cleanup", "complete"), False),
    (("error", "code"), "LIMIT_EXCEEDED"), (("process", "termination_reason"), "deadline"),
    (("observations", "scholarly_attempt", "http_response_count"), 0),
    (("error", "details", "http_status"), None),
    (("persistence", "required"), True), (("tool", "name"), "web.fetch"),
])
def test_throttle_exception_does_not_swallow_unknown_or_shared_failures(path, value):
    outcome = throttled()
    target = outcome
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    with pytest.raises(EngineError):
        _must_stop(outcome, "scholar.crossref.search")


@pytest.mark.asyncio
async def test_crossref_recorded_nondispatch_quota_denial_is_not_an_unknown_commit():
    outcome = throttled()
    outcome["error"]["code"] = "SCHOLAR_QUOTA_EXHAUSTED"
    outcome["process"].update(dispatched=False, exit_code=None)
    outcome["observations"] = {}
    port = SearchPort(lambda name, args: outcome if name == "scholar.crossref.search" else web(
        [("Document", "https://example.test/doc")], args["query"]))
    items, entries = await retrieve_candidates(context(port), ["first", "second"],
        ["web.search", "scholar.crossref.search"], 5, topic=None, recovery_limit=0, screen_candidates=False)
    assert items and sum(name == "scholar.crossref.search" for name, _ in port.reads) == 1
