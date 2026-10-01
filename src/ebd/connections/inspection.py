"""Fresh host reads for console consumers; no execution budgets are restored."""
from __future__ import annotations

from ebd.contracts import (
    BudgetLedger, EngineError, Err, ExecutionContext, Grant, GrantSet, Ok,
    RunRef, ScopeRef, deadline_after, new_id,
)


def _context(engine, run_id="host-inspection", grants=()):
    engine._active()
    principal = engine.settings.host_principal
    return ExecutionContext(run_id, run_id, new_id("inspection_"), new_id("host_read_"),
        principal=principal, purpose="inspection", store_id=engine.storage.store_id,
        scope=ScopeRef("run", run_id), deadline=deadline_after(60),
        grants=GrantSet(list(grants), principal),
        ledger=BudgetLedger({"storage_reads": 2048, "storage_read_bytes": 16777216}))


async def _owned(engine, run_ref):
    if not isinstance(run_ref, RunRef) or run_ref.store_id != engine.storage.store_id or run_ref.schema_version != 1:
        raise EngineError("ACCESS_DENIED", "Expected a same-store RunRef")
    scope = ScopeRef("run", run_ref.run_id)
    ctx = _context(engine, run_ref.run_id, [Grant("run.describe", scope, frozenset({run_ref.run_id}))])
    try:
        descriptor = (await engine.storage.describe_run(ctx, run_ref.run_id)).unwrap()
        if descriptor.get("owner_principal") != engine.settings.host_principal:
            raise EngineError("ACCESS_DENIED", "Run belongs to another host principal")
        return descriptor
    finally:
        await ctx.lease.release()


async def list_runs(engine, filters, cursor, limit):
    ctx = None
    try:
        ctx = _context(engine, grants=[Grant("runs.list", object_ids=frozenset({engine.settings.host_principal}))])
        return await engine.storage.list_runs(ctx, filters, cursor, limit)
    except EngineError as error:
        return Err(error)
    finally:
        if ctx:
            await ctx.lease.release()


async def describe_run(engine, run_ref):
    ctx = None
    try:
        descriptor = await _owned(engine, run_ref)
        ctx = _context(engine, run_ref.run_id, [Grant("events.read", ScopeRef("run", run_ref.run_id))])
        kind = "tool.outcome" if descriptor.get("context_kind") == "standalone_tool" else "agent.finished"
        terminal = (await engine.storage.latest_run_event(ctx, run_ref.run_id, kind)).unwrap()
        if terminal is None and kind == "tool.outcome":
            terminal = (await engine.storage.latest_run_event(ctx, run_ref.run_id, "tool.rejected")).unwrap()
        return Ok({**descriptor, "terminal_event": terminal})
    except EngineError as error:
        return Err(error)
    finally:
        if ctx:
            await ctx.lease.release()


async def list_objects(engine, run_ref, cursor, limit):
    ctx = None
    try:
        await _owned(engine, run_ref)
        scope = ScopeRef("run", run_ref.run_id)
        ctx = _context(engine, run_ref.run_id, [Grant("objects.list", scope)])
        return await engine.storage.list_objects(ctx, scope, cursor, limit)
    except EngineError as error:
        return Err(error)
    finally:
        if ctx:
            await ctx.lease.release()


async def read_state(engine, run_ref, key, version):
    ctx = None
    try:
        await _owned(engine, run_ref)
        if not isinstance(key, str) or not key or len(key) > 256:
            raise EngineError("INVALID_DATA", "Expected one bounded state key")
        scope = ScopeRef("run", run_ref.run_id)
        ctx = _context(engine, run_ref.run_id, [Grant("state.read", scope, frozenset({key}), max_bytes=1049600)])
        return await (engine.storage.state.get(ctx, scope, key) if version is None
                      else engine.storage.state.get_version(ctx, scope, key, version))
    except EngineError as error:
        return Err(error)
    finally:
        if ctx:
            await ctx.lease.release()


async def query_events(engine, run_ref, after_seq, limit, include_descendants):
    ctx = None
    try:
        descriptor = await _owned(engine, run_ref)
        if type(include_descendants) is not bool:
            raise EngineError("INVALID_DATA", "Lineage selector must be a boolean")
        run_ids = [run_ref.run_id]
        filters = {"run_id": run_ref.run_id}
        through_seq = None
        if include_descendants:
            # A root is required: a child's root selector would expose siblings.
            if descriptor["root_run_id"] != run_ref.run_id:
                raise EngineError("ACCESS_DENIED", "Lineage polling requires an owned root run")
            watermark_context = _context(engine, run_ref.run_id,
                [Grant("events.read", ScopeRef("run", run_ref.run_id))])
            try:
                through_seq = (await engine.storage.history_watermark(watermark_context)).unwrap()
            finally:
                await watermark_context.lease.release()
            filters = {"root_run_id": run_ref.run_id}
            cursor = None
            run_ids = []
            for _ in range(32):
                page = (await list_runs(engine, filters, cursor, 100)).unwrap()
                run_ids.extend(item["run_id"] for item in page["runs"])
                cursor = page["cursor"]
                if cursor is None:
                    break
            else:
                raise EngineError("LIMIT_EXCEEDED", "Lineage exceeds host inspection bounds")
        ctx = _context(engine, run_ref.run_id, [Grant("events.read", ScopeRef("run", identity)) for identity in run_ids])
        return await engine.storage.activity.poll(ctx, filters, after_seq, limit, through_seq=through_seq)
    except EngineError as error:
        return Err(error)
    finally:
        if ctx:
            await ctx.lease.release()
