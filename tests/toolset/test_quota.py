from __future__ import annotations

import asyncio
import time

import pytest

from ebd.contracts import ExecutionContext, deadline_after
from ebd.toolset.common import ToolFault
from ebd.toolset.executor import ToolExecutor
from ebd.toolset.scholarly import ProviderQuota, capture_limits, parse_limits


def context():
    return ExecutionContext("run", "run", "correlation", "action", attempt_id="attempt", deadline=deadline_after(15))


def test_http200_crossref_slower_headers_and_retry_after_only_narrow():
    async def check():
        quota = ProviderQuota("crossref")
        await quota.acquire("a:at", context())
        parsed = parse_limits("crossref", capture_limits("crossref", [(b"x-rate-limit-limit", b"1"), (b"x-rate-limit-interval", b"3s"), (b"x-concurrency-limit", b"1"), (b"retry-after", b"5")]))
        quota.settle("a:at", parsed, 200)
        assert quota.interval_ms == 3000 and quota.next_time - time.monotonic() >= 4.9
        faster = parse_limits("crossref", capture_limits("crossref", [(b"x-rate-limit-limit", b"10"), (b"x-rate-limit-interval", b"1s")]))
        quota.settle("another", faster, 200)
        assert quota.interval_ms == 3000
    asyncio.run(check())


def test_http200_openalex_zero_and_cost_charge_excess_once_no_billing():
    async def check():
        quota = ProviderQuota("openalex", anonymous_admission=True)
        await quota.acquire("a:at", context())
        parsed = parse_limits("openalex", capture_limits("openalex", [(b"x-ratelimit-remaining-usd", b"0"), (b"x-ratelimit-cost-usd", b"0.002"), (b"x-ratelimit-remaining", b"0"), (b"x-ratelimit-credits-used", b"20"), (b"x-ratelimit-reset", b"60")]))
        quota.settle("a:at", parsed, 200)
        assert quota.remaining == 98000 and quota.blocked
        quota.settle("a:at", parsed, 200)
        assert quota.remaining == 98000
        with pytest.raises(ToolFault): await quota.acquire("new:at", context())
    asyncio.run(check())


def test_429_missing_malformed_and_later_date_do_not_clear_block():
    quota = ProviderQuota("openalex", anonymous_admission=True)
    parsed = parse_limits("openalex", capture_limits("openalex", [(b"retry-after", b"bogus")]))
    quota.settle("unavailable", parsed, 429)
    assert quota.blocked and quota.retry_after is None
    quota.settle("later", parse_limits("openalex", dict.fromkeys(capture_limits("openalex", []))), 200)
    assert quota.blocked


def test_cancellation_waiting_serial_permit_does_not_dispatch_or_reserve():
    async def check():
        quota = ProviderQuota("crossref")
        await quota.acquire("first", context())
        pending_context = context()
        task = asyncio.create_task(quota.acquire("second", pending_context))
        await asyncio.sleep(.03); pending_context.cancellation.set()
        with pytest.raises(Exception) as exc: await task
        assert getattr(exc.value, "code", None) == "CANCELLED"
        assert "second" not in quota.reservations
        quota.settle("first", None)
    asyncio.run(check())


def test_quota_checkpoint_preserves_inflight_unknown_and_known_settlement():
    async def check():
        original = ToolExecutor(openalex_admission=True)
        await original.quotas["openalex"].acquire("a:at", context())
        state = original.export_quota_checkpoint()
        restarted = ToolExecutor(quota_checkpoint=state)
        assert restarted.quotas["openalex"].remaining == 99000
        assert restarted.quotas["openalex"].blocked
        original.quotas["openalex"].settle("a:at", None)
        settled = ToolExecutor(quota_checkpoint=original.export_quota_checkpoint())
        assert settled.quotas["openalex"].remaining == 99000
        assert not settled.quotas["openalex"].blocked
        assert "a:at" in settled.quotas["openalex"].reservations
        for executor in (original, restarted, settled): await executor.close()
    asyncio.run(check())


def test_default_openalex_has_no_implicit_restart_allowance():
    async def check():
        executor = ToolExecutor()
        with pytest.raises(ToolFault): await executor.quotas["openalex"].acquire("a:at", context())
        assert executor.quotas["openalex"].remaining == 100000
        assert not executor.quotas["openalex"].reservations
        await executor.close()
    asyncio.run(check())
