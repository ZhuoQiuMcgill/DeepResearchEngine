from __future__ import annotations

import asyncio

import pytest

from ebd.contracts import ArtifactContent, ArtifactMetadata, Err, deadline_after, digest_bytes
from ebd.storage import StorageSession
from test_storage import opened, context, read_all


class ByteSource:
    """A real bounded byte source with observable ownership for fault vectors."""
    def __init__(self, data, *, pause=False, oversize=False):
        self.data, self.offset, self.reads, self.closes = data, 0, 0, 0
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.pause, self.oversize = pause, oversize

    async def read(self, max_bytes):
        self.reads += 1
        self.entered.set()
        if self.pause:
            await self.release.wait()
        size = len(self.data) if self.oversize else max_bytes
        result = self.data[self.offset:self.offset + size]
        self.offset += len(result)
        return result

    async def aclose(self):
        self.closes += 1


def content(source, *, length=None, sha256=None):
    return ArtifactContent(source=source, byte_length=len(source.data) if length is None else length, sha256=sha256 or digest_bytes(source.data))


async def test_real_stream_dedup_precedes_source_consumption_and_final_quota(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    ctx.ledger.limits["storage_writes"] = 1
    source = ByteSource(b"streamed bytes")
    first = (await session.artifacts.put(ctx, "stable-source", ctx.scope, content(source), ArtifactMetadata("text/plain"))).unwrap()
    assert source.reads >= 2 and source.closes == 1
    assert await read_all(session, ctx, first.artifact_ref) == b"streamed bytes"
    replay = ByteSource(source.data)
    duplicate = (await session.artifacts.put(ctx, "stable-source", ctx.scope, content(replay), ArtifactMetadata("text/plain"))).unwrap()
    assert duplicate.duplicate and duplicate.event_receipt.recorded_seq == first.event_receipt.recorded_seq
    assert replay.reads == replay.closes == 0
    fresh = ByteSource(source.data)
    failed = await session.artifacts.put(ctx, "new-source", ctx.scope, content(fresh), ArtifactMetadata("text/plain"))
    assert failed.error.code == "LIMIT_EXCEEDED" and fresh.reads == fresh.closes == 0
    changed = ByteSource(b"changed bytes")
    assert (await session.artifacts.put(ctx, "stable-source", ctx.scope, content(changed), ArtifactMetadata("text/plain"))).error.code == "IDEMPOTENCY_CONFLICT"
    assert changed.reads == changed.closes == 0
    await replay.aclose()
    await fresh.aclose()
    await changed.aclose()
    await session.close()


@pytest.mark.parametrize("mode", ["short", "wrong_digest", "exceeds_declared", "oversized_chunk"])
async def test_stream_descriptor_or_chunk_failure_aborts_and_closes_source(tmp_path, mode):
    session, ctx = await opened(tmp_path / "store")
    source = ByteSource(b"bytes" if mode != "oversized_chunk" else b"x" * (128 << 10), oversize=mode == "oversized_chunk")
    length = len(source.data) + 1 if mode == "short" else len(source.data) - 1 if mode == "exceeds_declared" else len(source.data)
    sha256 = "sha256:" + "0" * 64 if mode == "wrong_digest" else digest_bytes(source.data)
    failed = await session.artifacts.put(ctx, "invalid-source", ctx.scope, content(source, length=length, sha256=sha256))
    assert failed.error.code == ("INVALID_DATA" if mode == "oversized_chunk" else "INTEGRITY_ERROR")
    assert failed.error.commit_state == "not_committed"
    assert source.closes == 1
    assert (await session.operations.status(ctx, "invalid-source")).unwrap().state == "aborted"
    assert (await session.activity.query(ctx)).unwrap().events == []
    await session.close()
    session = (await StorageSession.open(tmp_path / "store")).unwrap()
    assert (await session.operations.status(context(session), "invalid-source")).unwrap().state == "aborted"
    await session.close()


async def test_source_oversize_descriptor_rejection_keeps_caller_ownership(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    source = ByteSource(b"small actual source")
    failed = await session.artifacts.put(ctx, "oversize-descriptor", ctx.scope, content(source, length=(8 << 20) + 1))
    assert failed.error.code == "LIMIT_EXCEEDED" and source.reads == source.closes == 0
    assert (await session.operations.status(ctx, "oversize-descriptor")).unwrap().state == "absent"
    await source.aclose()
    await session.close()


async def test_cancelled_stream_borrower_close_retains_owner_until_source_settles(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    source = ByteSource(b"owned until settled", pause=True)
    task = asyncio.create_task(session.artifacts.put(ctx, "cancelled-source", ctx.scope, content(source)))
    await asyncio.wait_for(source.entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await session.close(deadline_after(0.01))).error.code == "STORAGE_BUSY"
    assert (await StorageSession.open(tmp_path / "store")).error.code == "STORAGE_BUSY"
    source.release.set()
    assert (await session.close(deadline_after(5))).unwrap().closed
    assert source.closes == 1
    session = (await StorageSession.open(tmp_path / "store")).unwrap()
    ctx = context(session)
    status = (await session.operations.status(ctx, "cancelled-source")).unwrap()
    assert status.state == "committed"
    assert await read_all(session, ctx, status.receipt.artifact_ref) == source.data
    await session.close()


async def test_max_fit_stream_exact_8mib_and_current_byte_quota(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    ctx.ledger.limits["storage_bytes"] = 8 << 20
    source = ByteSource(b"x" * (8 << 20))
    first = (await session.artifacts.put(ctx, "max-fit", ctx.scope, content(source))).unwrap()
    assert first.byte_length == 8 << 20 and first.sha256 == digest_bytes(source.data)
    assert source.closes == 1 and ctx.ledger.remaining("storage_bytes") == 0
    next_source = ByteSource(b"x")
    failed = await session.artifacts.put(ctx, "no-byte-quota", ctx.scope, content(next_source))
    assert failed.error.code == "LIMIT_EXCEEDED" and next_source.reads == next_source.closes == 0
    await next_source.aclose()
    await session.close()


async def test_source_deadline_aborts_unsealed_bytes_and_closes_owned_source(tmp_path):
    session, ctx = await opened(tmp_path / "store")
    ctx._monotonic_deadline = asyncio.get_running_loop().time() + 0.03
    source = ByteSource(b"bounded deadline", pause=True)
    failed = await session.artifacts.put(ctx, "source-deadline", ctx.scope, content(source))
    assert failed.error.code == "DEADLINE_EXCEEDED" and failed.error.commit_state == "not_committed"
    assert source.closes == 1
    fresh = context(session)
    assert (await session.operations.status(fresh, "source-deadline")).unwrap().state == "aborted"
    await session.close()


async def test_source_cleanup_failure_keeps_root_until_owned_cleanup_succeeds(tmp_path):
    class CleanupSource(ByteSource):
        async def aclose(self):
            self.closes += 1
            if self.closes == 1:
                raise RuntimeError("controlled cleanup failure")
    session, ctx = await opened(tmp_path / "store")
    source = CleanupSource(b"owned source")
    failed = await session.artifacts.put(ctx, "source-cleanup", ctx.scope, content(source))
    assert failed.error.code == "STORAGE_BUSY" and failed.error.commit_state == "not_committed"
    assert source.closes == 1 and (await session.operations.status(ctx, "source-cleanup")).unwrap().state == "aborted"
    assert (await StorageSession.open(tmp_path / "store")).error.code == "STORAGE_BUSY"
    assert (await session.close()).unwrap().closed and source.closes == 2


async def test_source_io_failure_returns_confirmed_abort_without_sensitive_details(tmp_path):
    class FailingSource(ByteSource):
        async def read(self, size):
            self.reads += 1
            raise OSError("controlled internal path must not be returned")
    session, ctx = await opened(tmp_path / "store")
    source = FailingSource(b"not published")
    failed = await session.artifacts.put(ctx, "source-io", ctx.scope, content(source))
    assert failed.error.code == "STORAGE_UNAVAILABLE" and failed.error.commit_state == "not_committed"
    assert "internal path" not in str(failed.error) and source.closes == 1
    assert (await session.operations.status(ctx, "source-io")).unwrap().state == "aborted"
    await session.close()
