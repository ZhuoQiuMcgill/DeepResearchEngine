import asyncio

import pytest

from deepresearch.extensions import ExtensionRegistry, ExtensionSpec, HookDispatcher, HookEvent


@pytest.mark.asyncio
async def test_timed_out_observer_retains_owned_handler_until_cleanup_settles():
    release, entered = asyncio.Event(), asyncio.Event()

    async def stubborn(event):
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                pass

    records = []
    async def record(kind, payload):
        records.append(kind)

    registry = ExtensionRegistry()
    registry.register(ExtensionSpec("test.observer", "1", ("node.after",),
                                   timeout_seconds=.01), stubborn)
    dispatcher = HookDispatcher(registry, record)
    try:
        await dispatcher.observe(HookEvent("run-test", "node-test", "node.after"))
        assert entered.is_set() and records == ["workflow.hook.failed"]
        cleanup = await dispatcher.close(.01)
        assert not cleanup.complete and cleanup.unconfirmed_resources
        release.set()
        assert (await dispatcher.close(1)).complete
    finally:
        release.set()
        await dispatcher.close(1)
