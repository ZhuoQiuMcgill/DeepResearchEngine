"""Snapshot safety, exact revision pins and the closed decision contract."""
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from ebd.contracts import EngineError
from ebd.extensions import ExtensionRegistry, ExtensionSpec, HookDecision, HookEvent


async def observer(event):
    pass


def test_event_and_config_are_independent_recursive_immutable_copies():
    source = {"candidate_ids": ["a", "b"], "measurements": {"count": 2}, "nullable": None}
    config = {"rules": [{"rank_limit": 2}]}
    event = HookEvent("run-a", "node-a", "discovery.select", source)
    spec = ExtensionSpec("ranker", "r1", ["context.select", "discovery.select"], config=config)
    event_digest, config_digest = event.payload_digest, spec.config_digest
    source["candidate_ids"].append("foreign")
    source["measurements"]["count"] = 9
    config["rules"][0]["rank_limit"] = 99
    assert event.payload["candidate_ids"] == ("a", "b")
    assert event.payload["measurements"]["count"] == 2
    assert spec.config["rules"][0]["rank_limit"] == 2
    assert event.payload_digest == event_digest and spec.config_digest == config_digest
    with pytest.raises(TypeError):
        event.payload["new"] = True
    with pytest.raises(TypeError):
        event.payload["measurements"]["count"] = 0
    with pytest.raises(AttributeError):
        event.payload["candidate_ids"].append("foreign")
    with pytest.raises(TypeError):
        spec.config["rules"][0]["rank_limit"] = 0
    with pytest.raises(FrozenInstanceError):
        event.run_id = "other-run"
    with pytest.raises(FrozenInstanceError):
        spec.revision = "r2"
    exported = event.to_dict()
    exported["payload"]["candidate_ids"].append("foreign")
    exported_config = spec.to_dict()
    exported_config["config"]["rules"][0]["rank_limit"] = 100
    assert event.payload["candidate_ids"] == ("a", "b")
    assert spec.config["rules"][0]["rank_limit"] == 2
    assert spec.points == ("context.select", "discovery.select")


def test_wrapped_mutable_input_is_copied_and_digest_is_canonical():
    original = {"count": 1, "ids": ["x"]}
    event = HookEvent("run-a", None, "node.before", MappingProxyType(original))
    equivalent = HookEvent("run-b", "node-b", "node.after", {"ids": ("x",), "count": 1})
    original["ids"].append("y")
    assert event.payload_digest == equivalent.payload_digest
    assert event.payload["ids"] == ("x",)
    first = ExtensionSpec("one", "r1", ("node.before",), config={"enabled": True, "limit": 2})
    second = ExtensionSpec("two", "r7", ("node.after",), config={"limit": 2, "enabled": True})
    assert first.config_digest == second.config_digest


@pytest.mark.parametrize("payload", [
    [], {1: "invalid-key"}, {"count": float("inf")}, {"count": float("nan")},
    {"client": object()}, {"callback": observer}, {"data": b"raw"}, {"data": {"a"}},
    {"label": "x" * 513}, {"label": "\U0001f600" * 129}, {"label": "\ud800"},
    {"count": 1 << 64}, {"ids": [0] * 1024},
    {"ids": ["\"" * 500] * 17},
    {"nested": {"api_key": "private-test-value"}}, {"text": "private-test-value"},
    {"raw_text": "private-test-value"}, {"prompt": "private-test-value"},
    {"apiKey": "private-test-value"}, {"OpenAI_API_KEY": "private-test-value"},
])
def test_unsafe_or_unbounded_metadata_rejects_without_echoing_values(payload):
    with pytest.raises(EngineError) as caught:
        HookEvent("run-a", "node-a", "node.before", payload)
    assert caught.value.code == "extension.invalid_event"
    assert "private-test-value" not in str(caught.value)
    assert caught.value.details == {}


def test_cycles_and_depth_limits_are_rejected_before_recursion_overflow():
    cyclic = {}
    cyclic["nested"] = cyclic
    with pytest.raises(EngineError):
        HookEvent("run-a", None, "node.before", cyclic)
    nested = 1
    for _ in range(8):
        nested = {"nested": nested}
    assert HookEvent("run-a", None, "node.before", nested).payload
    with pytest.raises(EngineError):
        HookEvent("run-a", None, "node.before", {"nested": nested})
    with pytest.raises(EngineError):
        ExtensionSpec("one", "r1", ("node.before",), config={"ids": ["x" * 512] * 17})


@pytest.mark.parametrize("changes", [
    {"extension_id": "contains whitespace"}, {"revision": 1}, {"points": "node.before"},
    {"points": ()}, {"points": ("node.before", "node.before")},
    {"points": ("Node.Before",)}, {"points": ("node",)},
    {"points": tuple(f"node.point{n}" for n in range(33))},
    {"mode": "admin"}, {"timeout_seconds": True}, {"timeout_seconds": 0},
    {"timeout_seconds": -1}, {"timeout_seconds": 31}, {"timeout_seconds": float("nan")},
    {"timeout_seconds": float("inf")}, {"timeout_seconds": "1"},
    {"timeout_seconds": 1 << 2048}, {"config": {"secret": "private-test-value"}},
])
def test_specs_validate_identity_point_mode_and_bounds(changes):
    args = {"extension_id": "one", "revision": "r1", "points": ("node.before",)}
    args.update(changes)
    with pytest.raises(EngineError) as caught:
        ExtensionSpec(**args)
    assert caught.value.code == "extension.invalid_spec"


@pytest.mark.parametrize("point", ["acquisition.fetch.before", "custom_2.rank.select", "node.failed"])
def test_stable_custom_points_are_supported_without_imports(point):
    assert ExtensionSpec("one", "r1", (point,)).points == (point,)
    assert HookEvent("run-a", None, point).point == point


@pytest.mark.parametrize("args", [
    ("bad run", "node-a", "node.before"), ("run-a", "bad node", "node.before"),
    ("run-a", None, "node.Before"), ("run-a", None, "x."),
])
def test_event_identities_and_points_validate(args):
    with pytest.raises(EngineError):
        HookEvent(*args)


def test_decision_is_closed_frozen_and_bounded():
    decision = HookDecision(("b", "a"))
    assert decision.to_dict() == {"keep_ids": ["b", "a"]}
    with pytest.raises(FrozenInstanceError):
        decision.keep_ids = ("foreign",)
    with pytest.raises(TypeError):
        HookDecision(("a",), authority="admin")
    for invalid in (["a"], ("a",) * 129, (object(),), ("raw text",)):
        with pytest.raises(EngineError) as caught:
            HookDecision(invalid)
        assert caught.value.code == "extension.invalid_decision"


def test_identical_registration_is_idempotent_and_pinned_revision_is_immutable():
    registry = ExtensionRegistry()
    spec = ExtensionSpec("one", "r1", ("node.before",), config={"limit": 2})
    assert registry.register(spec, observer) is spec
    equivalent = ExtensionSpec("one", "r1", ["node.before"], timeout_seconds=1, config={"limit": 2})
    assert registry.register(equivalent, observer) is spec
    assert registry.specs == (spec,)


@pytest.mark.parametrize("changes", [
    {"revision": "r2"}, {"points": ("node.after",)}, {"timeout_seconds": 2},
    {"config": {"limit": 3}}, {"mode": "control"},
])
def test_conflicting_revision_or_spec_is_rejected(changes):
    async def compatible(*args):
        return HookDecision(())

    registry = ExtensionRegistry()
    spec = ExtensionSpec("one", "r1", ("node.before",), config={"limit": 2})
    registry.register(spec, compatible)
    args = {"extension_id": "one", "revision": "r1", "points": ("node.before",), "config": {"limit": 2}}
    args.update(changes)
    with pytest.raises(EngineError) as caught:
        registry.register(ExtensionSpec(**args), compatible)
    assert caught.value.code == "extension.registration_conflict"
    assert registry.specs == (spec,)


def test_changed_handler_cannot_replace_same_revision():
    registry = ExtensionRegistry()
    spec = ExtensionSpec("one", "r1", ("node.before",))
    registry.register(spec, observer)

    async def replacement(event):
        pass

    with pytest.raises(EngineError) as caught:
        registry.register(spec, replacement)
    assert caught.value.code == "extension.registration_conflict"


def test_only_async_handlers_with_matching_signatures_are_registered():
    registry = ExtensionRegistry()
    spec = ExtensionSpec("one", "r1", ("node.before",))

    async def wrong_signature(event, candidates):
        pass

    for handler in (object(), lambda event: None, wrong_signature):
        with pytest.raises(EngineError) as caught:
            registry.register(spec, handler)
        assert caught.value.code == "extension.invalid_registration"

    class Handler:
        async def __call__(self, event):
            pass

    assert registry.register(spec, Handler()) == spec


def test_registry_has_finite_capacity():
    registry = ExtensionRegistry()
    for index in range(32):
        registry.register(ExtensionSpec(f"observer-{index}", "r1", ("node.before",)), observer)
    with pytest.raises(EngineError) as caught:
        registry.register(ExtensionSpec("overflow", "r1", ("node.before",)), observer)
    assert caught.value.code == "extension.capacity"
