import pytest
from pydantic import ValidationError

from ebd.contracts import EngineError
from ebd.workflows import FetchManifest, ResearchRunRequest, SourceRecord, SourceRange, TokenMeasurement, MethodRegistry
from ebd.methods.example_echo import EchoMethod, definition


@pytest.mark.parametrize("patch", [
    {"grants": {}}, {"items": [{"item_id": "a", "url": "file:///private"}]},
    {"items": [{"item_id": "a", "url": "https://user:password@example.org"}]},
    {"items": [{"item_id": "a", "url": "https://example.org"}, {"item_id": "a", "url": "https://example.org/other"}]},
])
def test_manifest_cannot_supply_authority_or_invalid_source_identity(patch):
    with pytest.raises((ValidationError, ValueError)):
        FetchManifest.model_validate(patch)


def test_success_requires_snapshot_and_complete_acknowledgment():
    with pytest.raises(ValidationError):
        SourceRecord(item_id="a", url="https://example.org", status="succeeded")


def test_literal_query_urls_preserve_distinct_targets():
    value = FetchManifest.model_validate({"items": [
        {"item_id": "a", "url": "https://example.org/?q=a%2Bb"},
        {"item_id": "b", "url": "https://example.org/?q=a+b"}]})
    assert value.items[0].url != value.items[1].url


@pytest.mark.parametrize("value", [
    {"kind": "pages", "start": 1, "end_exclusive": 12},
    {"kind": "lines", "start": 3, "end_exclusive": 3},
    {"kind": "lines", "start": True, "end_exclusive": 2},
])
def test_saved_source_ranges_remain_bounded(value):
    with pytest.raises(ValidationError):
        SourceRange.model_validate(value)


def test_verified_tokens_require_tokenizer_identity():
    with pytest.raises(ValidationError):
        TokenMeasurement(model_ref="model", text_sha256="sha256:" + "0" * 64, text_bytes=4, kind="verified", count=1)


def test_method_registry_pins_revision_and_validates_independent_input():
    registry = MethodRegistry()
    method = EchoMethod()
    spec = definition()
    registry.register(spec, method)
    registry.register(spec, method)
    with pytest.raises(EngineError, match="pinned"):
        registry.register(spec, EchoMethod())
    with pytest.raises(EngineError):
        registry.validate(spec, {"question": "different method"}, {})
    registry.validate(spec, {"message": "real example"}, {})


def test_frontend_request_cannot_construct_credentials_or_live_grants():
    with pytest.raises(ValidationError):
        ResearchRunRequest(client_request_id="test", input={"question": "test"}, api_key="not-a-public-field")
