"""Retained-content measurement stays local, labelled and tied to actual text."""
from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import FrozenInstanceError

import pytest

from ebd.contracts import EngineError
from ebd.engine.providers.tokenization import TokenCount, TokenMeter
from ebd.workflows.contracts import TokenMeasurement


MODEL = "research-model"
TOKENIZER = "fixture/utf8"
REVISION = "fixture-revision-1"


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def registered(callback=None) -> TokenMeter:
    meter = TokenMeter()
    meter.register(MODEL, TOKENIZER, REVISION, callback or (lambda text: len(text.encode("utf-8"))))
    return meter


def assert_error(code, action):
    with pytest.raises(EngineError) as failed:
        action()
    assert failed.value.code == code
    return failed.value


def test_pinned_callback_measures_whole_rendering_and_matches_workflow_wire_contract():
    calls = []
    text = "<source>\n雪🙂\r\n</source>"

    def count(value):
        calls.append(value)
        return len(value.encode("utf-8"))

    result = registered(count).measure(text, MODEL, scope="assembled", rendering_revision="evidence/2", require_verified=True)
    assert isinstance(result, TokenCount)
    assert calls == [text]
    assert result.kind == "verified" and result.estimator is None
    assert (result.tokenizer_id, result.tokenizer_revision) == (TOKENIZER, REVISION)
    assert result.count == result.text_bytes == len(text.encode("utf-8"))
    assert result.text_sha256 == digest(text)
    assert result.scope == "assembled" and result.rendering_revision == "evidence/2"
    wire = result.to_dict()
    assert wire["schema_version"] == 1
    assert TokenMeasurement.model_validate(wire).to_dict() == wire
    assert json.loads(json.dumps(wire)) == wire
    assert "input_tokens" not in wire and "total_tokens" not in wire


@pytest.mark.parametrize("text,expected", [("", 0), ("a", 1), ("abcd", 1), ("abcde", 2), ("雪🙂", 2)])
def test_unsupported_model_is_explicit_named_byte_estimate(text, expected):
    result = TokenMeter().measure(text, "unsupported")
    assert result.kind == "estimated" and result.estimator == "utf8-byte-size/4"
    assert result.count == expected
    assert result.text_bytes == len(text.encode("utf-8"))
    assert result.text_sha256 == digest(text)
    assert result.tokenizer_id is None and result.tokenizer_revision is None
    assert TokenMeasurement.model_validate(result.to_dict()).kind == "estimated"


def test_no_network_or_model_is_needed_even_for_unknown_remote_looking_profiles(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Token measurement must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", denied)
    meter = TokenMeter()
    result = meter.measure("saved evidence", "remote/model")
    assert result.kind == "estimated"
    meter.register("remote/model", "local/pinned", "revision-7", len)
    assert meter.measure("saved evidence", "remote/model", require_verified=True).kind == "verified"


def test_strict_unsupported_profile_rejects_measure_and_fit_even_after_estimate_is_cached():
    meter = TokenMeter()
    assert meter.measure("evidence", "unsupported").kind == "estimated"
    failed = assert_error("UNVERIFIED_TOKENIZER", lambda: meter.measure("evidence", "unsupported", require_verified=True))
    assert failed.details == {"model_ref": "unsupported"}
    assert_error("UNVERIFIED_TOKENIZER", lambda: meter.fit("evidence", "unsupported", 3, 16, require_verified=True))
    assert_error("UNVERIFIED_TOKENIZER", lambda: meter.fit("", "unsupported", 0, 0, require_verified=True))


@pytest.mark.parametrize("supported", [False, True])
def test_document_size_estimate_stays_estimated_and_never_calls_tokenizer(supported):
    meter = TokenMeter()

    def forbidden(_):
        pytest.fail("A size/hash document estimate cannot tokenize absent text")

    if supported:
        meter.register(MODEL, TOKENIZER, REVISION, forbidden)
    result = meter.estimate_document(9, digest("document!"), MODEL)
    assert result.scope == "document" and result.kind == "estimated"
    assert result.count == 3 and result.text_bytes == 9
    assert result.estimator == "utf8-byte-size/4"
    assert result.text_sha256 == digest("document!")
    assert result.rendering_revision == "source-text/1"
    assert result.tokenizer_id == (TOKENIZER if supported else None)
    assert result.tokenizer_revision == (REVISION if supported else None)
    assert TokenMeasurement.model_validate(result.to_dict()).to_dict() == result.to_dict()
    assert meter.estimate_document(0, digest(""), MODEL).count == 0


def test_document_estimate_does_not_poison_verified_document_measurement_cache():
    calls = []

    def count(text):
        calls.append(text)
        return len(text.encode("utf-8"))

    meter = registered(count)
    text = "document!"
    estimate = meter.estimate_document(9, digest(text), MODEL)
    exact = meter.measure(text, MODEL, scope="document", require_verified=True)
    assert estimate.kind == "estimated" and estimate.count == 3
    assert exact.kind == "verified" and exact.count == 9
    assert calls == [text]
    assert meter.estimate_document(9, digest(text), MODEL) == estimate
    assert meter.measure(text, MODEL, scope="document") == exact
    assert calls == [text]


def test_cache_separates_model_text_scope_and_rendering_and_reuses_identical_measurement():
    calls = []

    def count(text):
        calls.append(text)
        return len(text)

    meter = registered(count)
    meter.register("other-model", TOKENIZER, REVISION, count)
    first = meter.measure("first", MODEL)
    assert meter.measure("first", MODEL, require_verified=True) == first
    assert calls == ["first"]
    changed = [
        meter.measure("other", MODEL),
        meter.measure("first", "other-model"),
        meter.measure("first", MODEL, scope="assembled"),
        meter.measure("first", MODEL, rendering_revision="source-text/2"),
    ]
    assert len(calls) == 5
    assert changed[0].text_sha256 != first.text_sha256
    assert changed[1].model_ref != first.model_ref
    assert changed[2].scope == "assembled"
    assert changed[3].rendering_revision == "source-text/2"
    meter.measure("first", MODEL)
    assert len(calls) == 5


def test_tokenizer_revision_replacement_and_tokenizer_identity_never_reuse_old_count():
    meter = registered(lambda _: 11)
    first = meter.measure("same retained text", MODEL)
    meter.register(MODEL, TOKENIZER, "revision-2", lambda _: 22)
    second = meter.measure("same retained text", MODEL)
    assert first.count == 11 and first.tokenizer_revision == REVISION
    assert second.count == 22 and second.tokenizer_revision == "revision-2"
    meter.register(MODEL, "fixture/other", "revision-2", lambda _: 33)
    third = meter.measure("same retained text", MODEL)
    assert third.count == 33 and third.tokenizer_id == "fixture/other"
    # Replacing a callback under the same declared identity also invalidates it.
    meter.register(MODEL, "fixture/other", "revision-2", lambda _: 44)
    assert meter.measure("same retained text", MODEL).count == 44


def test_registering_support_invalidates_preexisting_fallback():
    meter = TokenMeter()
    estimate = meter.measure("abcde", MODEL)
    assert estimate.kind == "estimated" and estimate.count == 2
    meter.register(MODEL, TOKENIZER, REVISION, len)
    exact = meter.measure("abcde", MODEL, require_verified=True)
    assert exact.kind == "verified" and exact.count == 5


def test_cached_metadata_is_frozen_and_serialized_copies_cannot_corrupt_cache():
    meter = registered()
    result = meter.measure("雪", MODEL)
    with pytest.raises(FrozenInstanceError):
        result.count = 999
    wire = result.to_dict()
    wire["count"] = 999
    wire["tokenizer_revision"] = "corrupted"
    again = meter.measure("雪", MODEL)
    assert again.count == 3 and again.tokenizer_revision == REVISION
    assert again.to_dict() is not result.to_dict()


@pytest.mark.parametrize("invalid_count", [None, True, False, -1, 1.0, float("nan"), float("inf"), "1", [1], {"count": 1}])
def test_invalid_callback_counts_raise_without_fallback_or_poisoning_cache(invalid_count):
    replies = [invalid_count, 2]
    calls = []

    def count(text):
        calls.append(text)
        return replies.pop(0)

    meter = registered(count)
    assert_error("INVALID_DATA", lambda: meter.measure("xy", MODEL, require_verified=True))
    assert meter.measure("xy", MODEL, require_verified=True).count == 2
    assert calls == ["xy", "xy"]


def test_callback_exception_is_sanitized_and_never_becomes_an_estimate():
    def failed(_):
        raise RuntimeError("private retained text and callback details")

    error = assert_error("INVALID_DATA", lambda: registered(failed).measure("private retained text", MODEL))
    assert "private" not in json.dumps(error.to_dict())


def test_async_callbacks_are_rejected_without_unawaited_coroutine_warning():
    async def count(_):
        return 1

    assert_error("INVALID_DATA", lambda: TokenMeter().register(MODEL, TOKENIZER, REVISION, count))
    # Also reject a sync wrapper returning a coroutine instead of an integer.
    meter = registered(lambda text: count(text))
    assert_error("INVALID_DATA", lambda: meter.measure("evidence", MODEL))


@pytest.mark.parametrize("byte_cap,expected", [(0, ""), (1, "A"), (2, "A"), (3, "A"), (4, "A雪"), (7, "A雪"), (8, "A雪🙂"), (9, "A雪🙂Z"), (100, "A雪🙂Z")])
def test_fit_utf8_byte_cap_never_splits_code_points_and_hashes_actual_selection(byte_cap, expected):
    text = "A雪🙂Z"
    selected, measurement, truncated = registered().fit(text, MODEL, 100, byte_cap, require_verified=True)
    assert selected == expected and text.startswith(selected)
    assert len(selected.encode("utf-8")) <= byte_cap
    assert measurement.kind == "verified" and measurement.scope == "selected"
    assert measurement.count == measurement.text_bytes == len(selected.encode("utf-8"))
    assert measurement.text_sha256 == digest(selected)
    assert truncated is (selected != text)


def test_fit_token_budget_measures_final_prefix_as_a_whole():
    calls = []

    def count(text):
        calls.append(text)
        # This fixture merges an entire boundary-spanning pattern into one token.
        return len(text.replace("a雪🙂", "x"))

    text = "a雪🙂bcdefghij"
    meter = registered(count)
    selected, measurement, truncated = meter.fit(text, MODEL, 3, 100, require_verified=True)
    assert selected == "a雪🙂bc" and truncated is True
    assert selected in calls
    assert measurement.count == count(selected) == 3
    assert measurement.count <= 3
    assert measurement.text_bytes == len(selected.encode("utf-8"))
    assert measurement.text_sha256 == digest(selected)
    assert meter.measure(selected, MODEL) == measurement


def test_nonmonotonic_prefix_counts_return_only_an_actually_measured_fit():
    counts = {"": 0, "a": 9, "ab": 1, "abc": 6, "abcd": 7}
    calls = []

    def count(text):
        calls.append(text)
        return counts[text]

    selected, measurement, truncated = registered(count).fit("abcd", MODEL, 1, 100, require_verified=True)
    assert selected == "ab" and selected in calls and truncated is True
    assert measurement.count == counts[selected] == 1
    assert measurement.text_sha256 == digest(selected)


def test_counts_of_separate_fragments_are_not_used_for_assembled_text():
    meter = registered(lambda text: len(text.replace("ab", "x")))
    left = meter.measure("a", MODEL)
    right = meter.measure("b", MODEL)
    assembled = meter.measure("ab", MODEL, scope="assembled")
    assert left.count + right.count == 2
    assert assembled.count == 1 and assembled.scope == "assembled"
    selected, measurement, truncated = meter.fit("ab", MODEL, 1, 2, require_verified=True)
    assert selected == "ab" and measurement.count == 1 and truncated is False


@pytest.mark.parametrize("budget,byte_cap,expected", [(0, 100, ""), (1, 100, "A雪"), (2, 100, "A雪🙂"), (3, 5, "A雪")])
def test_estimated_fit_respects_bytes_but_keeps_unverified_label(budget, byte_cap, expected):
    selected, measurement, truncated = TokenMeter().fit("A雪🙂Z", MODEL, budget, byte_cap)
    assert selected == expected and truncated is True
    assert measurement.kind == "estimated" and measurement.estimator == "utf8-byte-size/4"
    assert measurement.tokenizer_id is None and measurement.tokenizer_revision is None
    assert measurement.count <= budget
    assert measurement.text_bytes == len(selected.encode("utf-8")) <= byte_cap
    assert measurement.text_sha256 == digest(selected)


def test_zero_counts_and_empty_selection_are_preserved_without_assuming_empty_is_free():
    selected, measurement, truncated = registered(lambda _: 0).fit("whole", MODEL, 0, 10, require_verified=True)
    assert selected == "whole" and measurement.count == 0 and truncated is False
    selected, measurement, truncated = registered().fit("🙂", MODEL, 3, 100, require_verified=True)
    assert selected == "" and measurement.count == 0 and truncated is True
    selected, measurement, truncated = TokenMeter().fit("", MODEL, 0, 0)
    assert selected == "" and measurement.count == 0 and truncated is False
    assert_error("INVALID_DATA", lambda: registered(lambda _: 2).fit("abc", MODEL, 1, 100, require_verified=True))


def test_fit_pins_one_callback_revision_even_if_host_replaces_registration_during_probe():
    meter = TokenMeter()
    calls = []

    def original(text):
        calls.append(text)
        if len(calls) == 1:
            meter.register(MODEL, TOKENIZER, "revision-2", lambda _: 99)
        return len(text)

    meter.register(MODEL, TOKENIZER, REVISION, original)
    selected, measurement, truncated = meter.fit("abcdef", MODEL, 2, 100, require_verified=True)
    assert selected == "ab" and measurement.count == 2 and truncated is True
    assert measurement.tokenizer_revision == REVISION
    fresh = meter.measure(selected, MODEL, require_verified=True)
    assert fresh.count == 99 and fresh.tokenizer_revision == "revision-2"


@pytest.mark.parametrize("action", [
    lambda m: m.register("", TOKENIZER, REVISION, len),
    lambda m: m.register(MODEL, " ", REVISION, len),
    lambda m: m.register(MODEL, TOKENIZER, "", len),
    lambda m: m.register(MODEL, TOKENIZER, REVISION, None),
    lambda m: m.register("x" * 129, TOKENIZER, REVISION, len),
    lambda m: m.register(MODEL, "x" * 257, REVISION, len),
    lambda m: m.register(MODEL, TOKENIZER, "x" * 129, len),
    lambda m: m.measure(b"bytes", MODEL),
    lambda m: m.measure("\ud800", MODEL),
    lambda m: m.measure("valid", "\ud800"),
    lambda m: m.measure("valid", MODEL, scope="invalid"),
    lambda m: m.measure("valid", MODEL, scope=[]),
    lambda m: m.measure("valid", MODEL, rendering_revision=""),
    lambda m: m.measure("valid", MODEL, rendering_revision="x" * 129),
    lambda m: m.measure("valid", MODEL, require_verified="yes"),
    lambda m: m.estimate_document(True, digest(""), MODEL),
    lambda m: m.estimate_document(-1, digest(""), MODEL),
    lambda m: m.estimate_document(1.0, digest(""), MODEL),
    lambda m: m.estimate_document(1, "not-a-sha256", MODEL),
    lambda m: m.estimate_document(1, "sha256:" + "A" * 64, MODEL),
    lambda m: m.fit("valid", MODEL, True, 10),
    lambda m: m.fit("valid", MODEL, -1, 10),
    lambda m: m.fit("valid", MODEL, 1.5, 10),
    lambda m: m.fit("valid", MODEL, 1, False),
    lambda m: m.fit("valid", MODEL, 1, -1),
    lambda m: m.fit("valid", MODEL, 1, 2.5),
    lambda m: m.fit("valid", MODEL, 1, 10, require_verified=1),
])
def test_invalid_inputs_are_engine_errors(action):
    assert_error("INVALID_DATA", lambda: action(TokenMeter()))
