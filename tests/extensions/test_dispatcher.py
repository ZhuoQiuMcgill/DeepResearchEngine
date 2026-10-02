"""Control confinement, observer isolation and mandatory audit boundaries."""
import asyncio
import copy

import pytest

from deepresearch.engine.contracts import EngineError, Err
from deepresearch.extensions import ExtensionRegistry, ExtensionSpec, HookDecision, HookDispatcher, HookEvent


class Recorder:
    def __init__(self):
        self.events = []

    async def __call__(self, kind, payload):
        self.events.append((kind, copy.deepcopy(payload)))


def event(point="discovery.select"):
    return HookEvent("run-a", "node-a", point, {"candidate_count": 3})


def registered(handler, *, mode="control", timeout_seconds=1, name="one", point="discovery.select"):
    registry = ExtensionRegistry()
    spec = ExtensionSpec(name, "r1", (point,), mode=mode, timeout_seconds=timeout_seconds, config={"limit": 2})
    registry.register(spec, handler)
    recorder = Recorder()
    return HookDispatcher(registry, recorder), recorder, spec


async def test_empty_registry_leaves_a_complete_host_method_usable():
    async def record(kind, payload):
        raise AssertionError("An empty registry must require no hook records")

    dispatcher = HookDispatcher(ExtensionRegistry(), record)
    steps = []

    async def base_method():
        for node in ("discovery", "acquisition", "writer"):
            await dispatcher.observe(HookEvent("run-a", node, "node.before"))
            if node == "discovery":
                ids = await dispatcher.select(event(), ["a", "b", "c"])
                assert ids == ["a", "b", "c"]
            if node == "writer":
                assert await dispatcher.select(event("context.select"), ["snapshot-a"]) == ["snapshot-a"]
            steps.append(node)
            await dispatcher.observe(HookEvent("run-a", node, "node.after"))
        return {"status": "succeeded", "output_ref": "report-a"}

    assert await base_method() == {"status": "succeeded", "output_ref": "report-a"}
    assert steps == ["discovery", "acquisition", "writer"]
    ids = ["a", "b"]
    result = await dispatcher.select(event(), ids)
    assert result == ids and result is not ids
    assert await dispatcher.select(event(), []) == []


async def test_modes_and_unsubscribed_points_do_not_run_handlers():
    async def should_not_run(*args):
        raise AssertionError("Wrong mode/point")

    dispatcher, recorder, _ = registered(should_not_run)
    await dispatcher.observe(event())
    assert await dispatcher.select(event("context.select"), ["a"]) == ["a"]
    observer, records, _ = registered(should_not_run, mode="observe")
    assert await observer.select(event(), ["a"]) == ["a"]
    await observer.observe(event("node.before"))
    assert recorder.events == records.events == []


async def test_dispatcher_pins_registry_snapshot_at_construction():
    registry, recorder = ExtensionRegistry(), Recorder()
    dispatcher = HookDispatcher(registry, recorder)
    calls = []

    async def later(event):
        calls.append(event.point)

    registry.register(ExtensionSpec("later", "r1", ("node.before",)), later)
    await dispatcher.observe(event("node.before"))
    assert calls == [] and recorder.events == []
    await HookDispatcher(registry, recorder).observe(event("node.before"))
    assert calls == ["node.before"]


async def test_controls_are_sequential_sorted_and_recorded_before_next_handler():
    registry, recorder = ExtensionRegistry(), Recorder()
    calls = []

    async def a_rank(event, ids):
        calls.append(("a-rank", ids))
        assert isinstance(ids, tuple)
        return HookDecision(("c", "a"))

    async def b_filter(event, ids):
        calls.append(("b-filter", ids))
        assert recorder.events[0][0] == "workflow.hook.decision"
        assert recorder.events[0][1]["keep_ids"] == ["c", "a"]
        return HookDecision((ids[-1],))

    registry.register(ExtensionSpec("b-filter", "v2", ("discovery.select",), mode="control"), b_filter)
    registry.register(ExtensionSpec("a-rank", "v1", ("discovery.select",), mode="control"), a_rank)
    dispatcher = HookDispatcher(registry, recorder)
    assert await dispatcher.select(event(), ["a", "b", "c"]) == ["a"]
    assert calls == [("a-rank", ("a", "b", "c")), ("b-filter", ("c", "a"))]
    assert [payload["extension_id"] for _, payload in recorder.events] == ["a-rank", "b-filter"]
    assert recorder.events[1][1]["original_candidate_ids"] == ["a", "b", "c"]
    assert recorder.events[1][1]["candidate_ids"] == ["c", "a"]


@pytest.mark.parametrize("response", [
    HookDecision(("foreign",)), HookDecision(("a", "a")), {"keep_ids": ["a"]},
    ["a"], ("a",), None,
])
async def test_invalid_decisions_fail_without_returning_broader_candidates(response):
    async def bad(event, ids):
        return response

    dispatcher, recorder, _ = registered(bad)
    with pytest.raises(EngineError) as caught:
        await dispatcher.select(event(), ["a", "b"])
    assert caught.value.code == "extension.invalid_decision"
    assert recorder.events[0][0] == "workflow.hook.failed"
    payload = recorder.events[0][1]
    assert payload["failure"] == "invalid_decision" and "keep_ids" not in payload
    assert payload["candidate_ids"] == ["a", "b"]
    assert "foreign" not in str(payload)


async def test_decision_subclasses_with_extra_fields_are_rejected():
    class OpenDecision(HookDecision):
        pass

    async def bad(event, ids):
        return OpenDecision(("a",))

    dispatcher, _, _ = registered(bad)
    with pytest.raises(EngineError) as caught:
        await dispatcher.select(event(), ["a"])
    assert caught.value.code == "extension.invalid_decision"


async def test_control_cannot_reintroduce_an_id_removed_by_an_earlier_hook():
    registry, recorder = ExtensionRegistry(), Recorder()

    async def first(event, ids):
        return HookDecision(("a",))

    async def second(event, ids):
        assert ids == ("a",)
        return HookDecision(("b",))

    registry.register(ExtensionSpec("a", "r1", ("discovery.select",), mode="control"), first)
    registry.register(ExtensionSpec("b", "r1", ("discovery.select",), mode="control"), second)
    with pytest.raises(EngineError) as caught:
        await HookDispatcher(registry, recorder).select(event(), ["a", "b"])
    assert caught.value.code == "extension.invalid_decision"
    assert [kind for kind, _ in recorder.events] == ["workflow.hook.decision", "workflow.hook.failed"]


async def test_empty_decision_is_valid_and_later_hook_cannot_resurrect_candidates():
    async def empty(event, ids):
        return HookDecision(())

    dispatcher, recorder, _ = registered(empty)
    assert await dispatcher.select(event(), ["a"]) == []
    assert recorder.events[0][1]["keep_ids"] == []
    assert await dispatcher.select(event(), []) == []


@pytest.mark.parametrize("candidate_ids", [["a", "a"], ["a", object()], ["a"] * 129, {"a"}, "a"])
async def test_invalid_host_candidates_reject_before_any_dispatch_or_record(candidate_ids):
    async def should_not_run(event, ids):
        raise AssertionError("Host candidates must validate first")

    dispatcher, recorder, _ = registered(should_not_run)
    with pytest.raises(EngineError) as caught:
        await dispatcher.select(event(), candidate_ids)
    assert caught.value.code == "extension.invalid_candidates"
    assert recorder.events == []


@pytest.mark.parametrize("fault", ["error", "timeout", "cancelled"])
async def test_observer_faults_are_recorded_and_later_observers_continue(fault):
    registry, recorder = ExtensionRegistry(), Recorder()
    calls = []

    async def broken(event):
        calls.append("broken")
        if fault == "error":
            raise RuntimeError("private-test-value")
        if fault == "cancelled":
            raise asyncio.CancelledError()
        await asyncio.sleep(60)

    async def healthy(event):
        calls.append("healthy")
        # Observer return values have no selection authority.
        return HookDecision(("foreign",))

    registry.register(ExtensionSpec("a-broken", "r1", ("node.before",), timeout_seconds=0.01), broken)
    registry.register(ExtensionSpec("b-healthy", "r2", ("node.before",)), healthy)
    await HookDispatcher(registry, recorder).observe(event("node.before"))
    assert calls == ["broken", "healthy"]
    assert [kind for kind, _ in recorder.events] == ["workflow.hook.failed", "workflow.hook.observed"]
    assert recorder.events[0][1]["failure"] == fault
    assert "private-test-value" not in str(recorder.events) and "foreign" not in str(recorder.events)


@pytest.mark.parametrize("fault,code", [("error", "extension.failed"), ("timeout", "extension.timeout"), ("cancelled", "extension.failed"), ("bad_shape", "extension.invalid_decision")])
async def test_control_faults_record_then_raise_engine_error_and_stop(fault, code):
    registry, recorder = ExtensionRegistry(), Recorder()
    later_called = False

    async def broken(event, ids):
        if fault == "error":
            raise RuntimeError("private-test-value")
        if fault == "cancelled":
            raise asyncio.CancelledError()
        if fault == "bad_shape":
            return HookDecision(["a"])
        await asyncio.sleep(60)

    async def later(event, ids):
        nonlocal later_called
        later_called = True
        return HookDecision(ids)

    registry.register(ExtensionSpec("a-broken", "r1", ("discovery.select",), mode="control", timeout_seconds=0.01), broken)
    registry.register(ExtensionSpec("b-later", "r1", ("discovery.select",), mode="control"), later)
    with pytest.raises(EngineError) as caught:
        await HookDispatcher(registry, recorder).select(event(), ["a", "b"])
    assert caught.value.code == code and not later_called
    assert [kind for kind, _ in recorder.events] == ["workflow.hook.failed"]
    assert "private-test-value" not in str(recorder.events) + str(caught.value)


@pytest.mark.parametrize("mode,broken", [("observe", False), ("observe", True), ("control", False), ("control", True)])
@pytest.mark.parametrize("record_behavior", ["raise_engine", "raise_unexpected", "return_err"])
async def test_mandatory_record_errors_propagate_unchanged_and_stop_later_hooks(mode, broken, record_behavior):
    registry = ExtensionRegistry()
    attempts, records = [], []
    failure = RuntimeError("record unavailable") if record_behavior == "raise_unexpected" else EngineError("STORAGE_IO", "Record unavailable", commit_state="unknown")

    async def handler(*args):
        attempts.append("first")
        if broken:
            raise ValueError("private-test-value")
        if mode == "control":
            return HookDecision(("a",))

    async def later(*args):
        attempts.append("later")
        return HookDecision(())

    async def record(kind, payload):
        records.append(kind)
        if record_behavior == "return_err":
            return Err(failure)
        raise failure

    registry.register(ExtensionSpec("a-first", "r1", ("discovery.select",), mode=mode), handler)
    registry.register(ExtensionSpec("b-later", "r1", ("discovery.select",), mode=mode), later)
    dispatcher = HookDispatcher(registry, record)
    with pytest.raises(type(failure)) as caught:
        if mode == "observe":
            await dispatcher.observe(event())
        else:
            await dispatcher.select(event(), ["a", "b"])
    assert caught.value is failure
    assert attempts == ["first"]
    assert len(records) == 1
    assert records[0] == ("workflow.hook.failed" if broken else "workflow.hook.observed" if mode == "observe" else "workflow.hook.decision")


async def test_host_candidate_list_mutation_during_await_does_not_change_original_selection():
    entered, release = asyncio.Event(), asyncio.Event()
    original = ["a", "b"]

    async def handler(event, ids):
        entered.set()
        await release.wait()
        assert ids == ("a", "b")
        return HookDecision(("b",))

    dispatcher, recorder, _ = registered(handler)
    task = asyncio.create_task(dispatcher.select(event(), original))
    await entered.wait()
    original[:] = ["foreign"]
    release.set()
    assert await task == ["b"]
    assert recorder.events[0][1]["original_candidate_ids"] == ["a", "b"]


async def test_timeout_does_not_wait_for_a_handler_that_suppresses_cancellation():
    cancelled, release, exited = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def resistant(event):
        try:
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
            raise RuntimeError("late-private-test-value")
        finally:
            exited.set()

    dispatcher, recorder, _ = registered(resistant, mode="observe", timeout_seconds=0.01)
    try:
        await asyncio.wait_for(dispatcher.observe(event()), 1)
        await asyncio.wait_for(cancelled.wait(), 1)
        assert not exited.is_set()
        assert recorder.events[0][1]["failure"] == "timeout"
    finally:
        release.set()
        await asyncio.wait_for(exited.wait(), 1)
        await asyncio.sleep(0)
    assert len(recorder.events) == 1  # A late result never becomes a decision/second record.


async def test_stuck_handlers_consume_finite_capacity_and_new_observation_is_diagnosed():
    release = asyncio.Event()
    entered = 0

    async def resistant(event):
        nonlocal entered
        entered += 1
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    dispatcher, recorder, _ = registered(resistant, mode="observe", timeout_seconds=0.001)
    try:
        for _ in range(33):
            await dispatcher.observe(event())
        assert entered == 32
        assert [payload["failure"] for _, payload in recorder.events] == ["timeout"] * 32 + ["capacity"]
    finally:
        pending = tuple(dispatcher._active)
        release.set()
        await asyncio.gather(*pending, return_exceptions=True)
    await dispatcher.observe(event())
    assert entered == 33 and recorder.events[-1][0] == "workflow.hook.observed"


@pytest.mark.parametrize("mode", ["observe", "control"])
async def test_caller_cancellation_is_recorded_then_propagated(mode):
    entered, exited = asyncio.Event(), asyncio.Event()

    async def handler(*args):
        try:
            entered.set()
            await asyncio.sleep(60)
        finally:
            exited.set()

    dispatcher, recorder, _ = registered(handler, mode=mode)
    operation = dispatcher.observe(event()) if mode == "observe" else dispatcher.select(event(), ["a"])
    task = asyncio.create_task(operation)
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(exited.wait(), 1)
    assert recorder.events[0][0] == "workflow.hook.failed"
    assert recorder.events[0][1]["failure"] == "caller_cancelled"


def test_dispatcher_requires_async_host_recorder():
    with pytest.raises(EngineError) as caught:
        HookDispatcher(ExtensionRegistry(), lambda kind, payload: None)
    assert caught.value.code == "extension.invalid_dispatcher"


async def test_control_timeout_discards_a_late_valid_decision():
    cancelled, release, exited = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def resistant(event, ids):
        try:
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
            return HookDecision(("a",))
        finally:
            exited.set()

    dispatcher, recorder, _ = registered(resistant, timeout_seconds=0.01)
    try:
        with pytest.raises(EngineError) as caught:
            await asyncio.wait_for(dispatcher.select(event(), ["a", "b"]), 1)
        assert caught.value.code == "extension.timeout"
        await asyncio.wait_for(cancelled.wait(), 1)
        assert not exited.is_set()
        assert [kind for kind, _ in recorder.events] == ["workflow.hook.failed"]
    finally:
        release.set()
        await asyncio.wait_for(exited.wait(), 1)
        await asyncio.sleep(0)
    assert [kind for kind, _ in recorder.events] == ["workflow.hook.failed"]


async def test_control_capacity_failure_is_recorded_and_raises_engine_error():
    release = asyncio.Event()
    entered = 0

    async def resistant(event, ids):
        nonlocal entered
        entered += 1
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return HookDecision(ids)

    dispatcher, recorder, _ = registered(resistant, timeout_seconds=0.001)
    try:
        for _ in range(32):
            with pytest.raises(EngineError) as caught:
                await dispatcher.select(event(), ["a"])
            assert caught.value.code == "extension.timeout"
        with pytest.raises(EngineError) as caught:
            await dispatcher.select(event(), ["a"])
        assert caught.value.code == "extension.capacity" and entered == 32
        assert recorder.events[-1][1]["failure"] == "capacity"
        assert all(kind == "workflow.hook.failed" for kind, _ in recorder.events)
    finally:
        release.set()
        await asyncio.gather(*tuple(dispatcher._active), return_exceptions=True)
    assert len(recorder.events) == 33
