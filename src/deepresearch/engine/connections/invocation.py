"""Explicit child invocation and bounded result export through existing modules."""
from __future__ import annotations

import asyncio
import copy
import dataclasses

from deepresearch.engine.contracts import *
from .models import *


async def invoke(invoker, caller, destination, task_input, options):
    engine = invoker.engine
    invocation = None
    child = session = admission = None
    intent = None
    outcome = InvocationOutcome({}, destination if isinstance(destination, AgentRef) else AgentRef(str(destination)), "failed")
    acquired = False
    try:
        engine._active()
        if caller.grants is not invoker.caller.grants or caller.lease is not invoker.caller.lease or caller.run_id != invoker.caller.run_id:
            raise EngineError("ACCESS_DENIED", "Invoker belongs to another live binding")
        caller.assert_active()
        if invoker.workflow_policy is not None:
            engine._workflow_session(invoker.session)
        ref, definition, child_rules = engine._resolve(destination)
        outcome.destination = ref
        rule = next((r for r in invoker.rules if r.destination == ref), None)
        caller.authorize("agent.invoke", object_id=ref.agent_id)
        if rule is None or not rule.allow_model:
            raise EngineError("ACCESS_DENIED", "No model delegation is permitted on this edge")
        if ref.agent_id == caller.agent_id or ref.agent_id in caller.ancestry:
            raise EngineError("INVOCATION_CYCLE", "Agent lineage contains the destination")
        if caller.depth + 1 > min(engine.settings.max_depth, rule.max_depth):
            raise EngineError("LIMIT_EXCEEDED", "Invocation depth is exhausted")
        allowed = {t for t in invoker.allowed_tools if t.name in rule.allowed_tools}
        if any(t not in allowed for t in definition.allowed_tools):
            raise EngineError("ACCESS_DENIED", "Child tool request exceeds delegable caller rights")
        for tool in definition.allowed_tools:
            caller.authorize("tool.delegate", object_id=tool.name)
        # Registered invocation edges are the trusted model-delegation selection;
        # user options cannot introduce a profile, model, destination or endpoint.
        options = options or RunOptions(timeout_seconds=rule.timeout_seconds)
        if isinstance(options, dict):
            options = RunOptions(**options)
        from .evidence import freeze_evidence
        evidence = freeze_evidence(getattr(options, "evidence", None))
        task_input = copy.deepcopy(task_input)
        if evidence is not None and not rule.allow_evidence:
            raise EngineError("ACCESS_DENIED", "This edge does not permit evidence delegation")
        from .evidence import evidence_grants
        delegated = await evidence_grants(engine, caller, evidence)
        from .engine import narrowed_limits
        edge_limits = narrowed_limits(engine.settings.limits, rule.limits)
        child_limits = narrowed_limits(edge_limits, options.limits)
        child_options = dataclasses.replace(options, limits=child_limits,
            timeout_seconds=min(options.timeout_seconds, rule.timeout_seconds, caller.remaining_seconds()))
        caller.ledger.consume("descendants")
        invocation = caller.for_action(new_id("invocation_"), new_id("attempt_"))
        outcome.execution = invocation.descriptor()
        await asyncio.wait_for(engine._child_slots.acquire(), caller.remaining_seconds())
        acquired = True
        child = await engine._new_context(child_options, definition, parent=caller, invocation=invocation,
                                         rules=child_rules if rule.allow_onward else ())
        child.grants = engine._grants(child, definition, child_rules if rule.allow_onward else ())
        child.grants.grants.extend(delegated)
        child.grants._parents = (caller.grants,)
        session = (await engine._bind(child, definition, child_rules if rule.allow_onward else ())).unwrap()
        admitted = await engine.runtime.admit(definition, task_input, session.binding, child)
        admitted.unwrap()
        admission = admitted.value
        outcome.child_run = RunRef(child.store_id, child.run_id)
        intent = await engine._record(invocation, "invocation.intent", {
            "destination": ref.to_dict(), "candidate_child_run": outcome.child_run.to_dict(),
            "admission": admission.descriptor(), "input_digest": digest_json(task_input),
            "evidence": evidence.to_dict() if evidence else None,
        })
        intent.unwrap()
        outcome.intent_receipt = intent.value
        caller.assert_active()
        caller.authorize("agent.invoke", object_id=ref.agent_id)
        child_task = asyncio.create_task(engine.runtime.execute(admission))
        engine._tasks.add(child_task)
        async def propagate_cancel():
            await caller.cancellation.wait()
            child.cancellation.set()
        watcher = asyncio.create_task(propagate_cancel())
        try:
            outcome.dispatched = True
            result = await child_task
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            engine._tasks.discard(child_task)
        outcome.child_result = result
        outcome.status = result.status
        if result.status == "succeeded" and result.recording_status == "complete":
            caller.authorize("agent.invoke", object_id=ref.agent_id)
            if result.output_delivery == "inline":
                outcome.output = result.output
            elif result.output_ref:
                if not rule.allow_export:
                    raise EngineError("ACCESS_DENIED", "Artifact output requires an explicit export edge")
                caller.assert_active()
                caller.authorize("artifact.put", caller.scope)
                export = dataclasses.replace(invocation, purpose="result_export",
                    grants=GrantSet([Grant("artifact.read", child.scope, frozenset({result.output_ref.id})),
                                     Grant("artifact.put", caller.scope), Grant("operation.status", caller.scope)],
                                    caller.principal, _parents=(caller.grants,)))
                handle = (await engine.storage.artifacts.open(export, result.output_ref, max_bytes=8388608)).unwrap()
                parts = []
                try:
                    while True:
                        caller.authorize("agent.invoke", object_id=ref.agent_id)
                        chunk = (await handle.read(export, 65536)).unwrap()
                        parts.append(chunk.bytes)
                        if chunk.eof:
                            break
                finally:
                    await handle.aclose(export)
                data = b"".join(parts)
                media = (result.output_metadata or {}).get("media_type", "text/markdown")
                caller.authorize("agent.invoke", object_id=ref.agent_id)
                caller.authorize("artifact.put", caller.scope)
                receipt = (await engine.storage.artifacts.put(export, new_id("export_"), caller.scope, data,
                    ArtifactMetadata(media, metadata={"purpose": "result_export", "source": result.output_ref.to_dict()}))).unwrap()
                outcome.output_ref, outcome.export_receipt = receipt.artifact_ref, receipt
        recorded = await engine._record(invocation, "invocation.outcome", {
            "destination": ref.to_dict(), "child_run": outcome.child_run.to_dict(), "status": outcome.status,
            "dispatched": True, "child_terminal_receipt": result.terminal_event_receipt.to_dict() if result.terminal_event_receipt else None,
            "child_recording_status": result.recording_status,
            "export_receipt": outcome.export_receipt.to_dict() if outcome.export_receipt else None,
        }, cleanup=True)
        if isinstance(recorded, Ok):
            outcome.outcome_receipt = recorded.value
            outcome.recording_status = "complete" if result.recording_status == "complete" else "incomplete"
        else:
            outcome.error = recorded.error
            outcome.recording_status = "incomplete"
        return outcome
    except asyncio.CancelledError:
        if child:
            child.cancellation.set()
        if invocation and isinstance(intent, Ok):
            await asyncio.shield(engine._record(invocation, "invocation.outcome", {"status": "cancelled", "dispatched": outcome.dispatched}, cleanup=True))
        raise
    except (EngineError, asyncio.TimeoutError) as exc:
        error = exc if isinstance(exc, EngineError) else EngineError("DEADLINE_EXCEEDED", "Invocation slot deadline elapsed")
        outcome.error = error
        outcome.status = "timed_out" if error.code == "DEADLINE_EXCEEDED" else "limit_exhausted" if error.code == "LIMIT_EXCEEDED" else "failed"
        record_ctx = invocation or caller.for_action(new_id("invocation_"), None)
        recorded = await engine._record(record_ctx, "invocation.outcome" if isinstance(intent, Ok) else "invocation.rejected", {
            "destination": outcome.destination.to_dict(), "status": outcome.status, "error": error.to_dict(), "dispatched": outcome.dispatched,
            "child_status": outcome.child_result.status if outcome.child_result else None,
            "child_terminal_receipt": outcome.child_result.terminal_event_receipt.to_dict() if outcome.child_result and outcome.child_result.terminal_event_receipt else None,
            "child_recording_status": outcome.child_result.recording_status if outcome.child_result else None,
        }, cleanup=True)
        outcome.recording_status = "complete" if isinstance(recorded, Ok) else "incomplete"
        if isinstance(recorded, Ok):
            outcome.outcome_receipt = recorded.value
        return outcome
    finally:
        if admission and admission.state == "reserved":
            await admission.release()
        if session:
            await session.close()
        elif child:
            await child.lease.release()
        if acquired:
            engine._child_slots.release()
