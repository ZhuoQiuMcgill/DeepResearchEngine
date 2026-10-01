"""Trusted composition root. Strategy remains outside all platform modules."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import math
import time
from pathlib import Path

from ebd.agent import Runtime, RecordedToolAction
from ebd.agent.validation import validate_schema
from ebd.contracts import (
    AgentDefinition, AgentResult, ArtifactMetadata, AttemptLease, BindingSet,
    BudgetLedger, CleanupReport, EngineError, Err, ExecutionContext, ExecutionEvent,
    Grant, GrantSet, Ok, ResourceLease, RunRef, ScopeRef, ToolRef, ToolRequest,
    ToolResult, ToolStoragePlan, canonical_json, deadline_after, digest_json, new_id,
    StateMutation,
)
from ebd.providers import ProviderFactory
from ebd.storage import StorageSession
from ebd.toolset import ToolCatalog, ToolExecutor
from .config import ProfileRegistry
from .models import *


CONNECTION_EVENTS = frozenset({"binding.resolved", "binding.failed", "binding.evidence", "invocation.intent", "invocation.outcome", "invocation.rejected"})


def finite_seconds(value, cap):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise EngineError("INVALID_DATA", "Timeout must be positive and finite")
    return min(float(value), cap)


def narrowed_limits(base, requested):
    if not isinstance(requested, dict) or set(requested) - set(base):
        raise EngineError("INVALID_DATA", "Unknown budget limit")
    result = dict(base)
    for key, value in requested.items():
        if type(value) is not int or value < 0:
            raise EngineError("INVALID_DATA", "Budget limits must be nonnegative integers")
        result[key] = min(result[key], value)
    return result


class ToolPlanFactory:
    def __init__(self, storage, scope):
        self.storage, self.scope = storage, scope

    def for_attempt(self, definition, arguments, context):
        try:
            context.assert_active()
            if not context.attempt_id or context.store_id != self.storage.store_id or context.scope != self.scope:
                raise EngineError("ACCESS_DENIED", "Tool plan requires the exact bound attempt and store")
            operation_id = new_id("operation_") if definition.name == "web.fetch" else None
            if operation_id:
                context.authorize("snapshot.commit", self.scope, operation_id)
                context.grants.grants.append(Grant("operation.status", self.scope,
                    frozenset({operation_id}), run_id=context.run_id))
            uses_storage = definition.name in {"web.fetch", "document.read"}
            return Ok(ToolStoragePlan(definition.ref, context, self.scope if uses_storage else None, operation_id,
                snapshot_store=self.storage.snapshots if uses_storage else None,
                operation_store=self.storage.operations if operation_id else None,
                limits=dict(definition.limits), request=copy.deepcopy(arguments), lease=AttemptLease(context)))
        except EngineError as error:
            return Err(error)


class Engine:
    def __init__(self, settings, storage):
        self.settings, self.storage = settings, storage
        self.catalog = ToolCatalog()
        self.executor = None
        self.runtime = Runtime()
        self.profiles = ProfileRegistry(settings)
        self._registered = {}
        self._contexts = {}
        self._sessions = []
        self._tasks = set()
        self._closing = False
        self._closed = False
        self._child_slots = asyncio.Semaphore(settings.max_active_descendants)

    @classmethod
    async def open(cls, settings=None):
        settings = settings or EngineSettings()
        try:
            if isinstance(settings, dict):
                settings = EngineSettings(**settings)
            if not isinstance(settings, EngineSettings):
                raise EngineError("INVALID_DATA", "Expected EngineSettings")
            finite_seconds(settings.max_run_seconds, 86400)
            finite_seconds(settings.max_access_seconds, 3600)
            for name in ("max_depth", "max_descendants", "max_active_descendants"):
                if type(getattr(settings, name)) is not int or getattr(settings, name) < 1:
                    raise EngineError("INVALID_DATA", "Invocation limits must be positive integers")
            narrowed_limits(settings.limits, settings.limits)
            root = Path(settings.storage_root or Path(settings.workspace) / "local" / "store")
            opened = await StorageSession.open({"root": root, "profile": settings.storage_profile})
            if isinstance(opened, Err):
                return opened
            engine = cls(settings, opened.value)
            try:
                await engine._initialize_quotas()
            except BaseException:
                await opened.value.close(deadline_after(10))
                raise
            return Ok(engine)
        except (EngineError, TypeError, ValueError) as exc:
            return Err(exc if isinstance(exc, EngineError) else EngineError("INVALID_DATA", "Invalid engine configuration"))

    def _active(self):
        if self._closing or self._closed:
            raise EngineError("SESSION_CLOSED", "Engine admissions have stopped")

    async def _initialize_quotas(self):
        run_id = "platform-tools-budget-v1"
        scope = ScopeRef("run", run_id)
        def authority():
            principal = self.settings.host_principal
            ctx = ExecutionContext(run_id, run_id, "platform-tools-budget-v1", new_id("quota_action_"),
                principal=principal, context_kind="standalone_tool", deadline=deadline_after(30),
                store_id=self.storage.store_id, scope=scope,
                ledger=BudgetLedger({"storage_writes": 4, "storage_reads": 4, "storage_bytes": 1048576}))
            ctx.grants = GrantSet([Grant(op, scope) for op in ("admin.provision", "state.read", "state.commit")], principal)
            return ctx
        ctx = authority()
        descriptor = {"run_id": run_id, "root_run_id": run_id, "correlation_id": run_id,
            "root_action_id": "quota-control", "owner_principal": "platform-internal",
            "context_kind": "standalone_tool", "agent_id": None, "definition_ref": None}
        (await self.storage.provision_run(ctx, descriptor)).unwrap()
        previous = (await self.storage.state.get(ctx, scope, "scholarly-quota")).unwrap()
        version = previous.version
        checkpoint = previous.value if previous.present else None
        persistence_lock = asyncio.Lock()
        async def persist(snapshot):
            nonlocal version
            async with persistence_lock:
                context = authority()
                try:
                    result = await self.storage.state.commit(context, new_id("quota_operation_"),
                        [StateMutation(scope, "scholarly-quota", "put", version, snapshot)])
                    if isinstance(result, Ok):
                        version += 1
                    return result
                finally:
                    await context.lease.release()
        self.executor = ToolExecutor(self.catalog, openalex_admission=self.settings.openalex_admission,
            fetch_concurrency=self.settings.fetch_concurrency,
            quota_checkpoint=checkpoint, quota_checkpoint_sink=persist)
        (await persist(self.executor.export_quota_checkpoint())).unwrap()
        await ctx.lease.release()

    def register_agent(self, definition, invocation_rules=()):
        try:
            self._active()
            if not isinstance(definition, AgentDefinition) or type(definition.schema_version) is not int or definition.schema_version != 1 or not definition.agent_id or not definition.instructions:
                raise EngineError("INVALID_DATA", "A complete version-1 AgentDefinition is required")
            if type(definition.revision) is not int or definition.revision < 1:
                raise EngineError("INVALID_DATA", "Agent revision must be a positive integer")
            definition = copy.deepcopy(definition)
            if definition.output_contract:
                definition.output_mode = definition.output_contract.get("mode", definition.output_mode)
                definition.output_schema = definition.output_contract.get("schema", definition.output_schema)
                definition.output_media_type = definition.output_contract.get("media_type", definition.output_media_type)
            validate_schema(definition.input_schema)
            validate_schema(definition.output_schema)
            canonical_json(definition, 131072)
            rules = tuple(invocation_rules)
            if any(not isinstance(rule, InvocationRule) for rule in rules):
                raise EngineError("INVALID_DATA", "Invocation rules must be trusted typed records")
            if len({r.destination for r in rules}) != len(rules):
                raise EngineError("INVALID_DATA", "Duplicate invocation destination")
            for tool in definition.allowed_tools:
                self.catalog.resolve(tool.name, tool.revision).unwrap()
            for rule in rules:
                if any(type(getattr(rule, name)) is not bool for name in ("allow_model", "allow_export", "allow_onward", "allow_evidence")):
                    raise EngineError("INVALID_DATA", "Invocation permissions must be booleans")
                if not isinstance(rule.destination, AgentRef) or type(rule.max_depth) is not int or rule.max_depth < 1:
                    raise EngineError("INVALID_DATA", "Invalid exact invocation destination or depth")
                finite_seconds(rule.timeout_seconds, self.settings.max_run_seconds)
                narrowed_limits(self.settings.limits, rule.limits)
                if set(rule.allowed_tools) - {t.name for t in definition.allowed_tools}:
                    raise EngineError("ACCESS_DENIED", "Invocation edge requests undelegable tools")
            ref = AgentRef(definition.agent_id, definition.revision)
            fingerprint = digest_json({"definition": definition, "rules": rules})
            previous = self._registered.get(ref)
            if previous and previous[2] != fingerprint:
                raise EngineError("REGISTRATION_CONFLICT", "Content changed under an existing agent revision")
            self._registered[ref] = (copy.deepcopy(definition), copy.deepcopy(rules), fingerprint)
            return Ok(RegisteredAgent(ref, definition.definition_ref))
        except EngineError as error:
            return Err(error)
        except (ValueError, TypeError) as error:
            return Err(EngineError("INVALID_DATA", "Registration validation failed", {"type": type(error).__name__}))

    def _resolve(self, ref):
        if isinstance(ref, RegisteredAgent):
            ref = ref.ref
        elif isinstance(ref, str):
            ref = AgentRef(ref)
        elif isinstance(ref, dict):
            ref = AgentRef(**ref)
        if ref not in self._registered:
            raise EngineError("AGENT_NOT_FOUND", "Exact registered agent revision is required")
        definition, rules, _ = self._registered[ref]
        return ref, copy.deepcopy(definition), rules

    def _grants(self, ctx, definition=None, rules=(), standalone_tools=()):
        scope = ctx.scope
        grants = [Grant(op, scope, run_id=ctx.run_id) for op in (
            "state.read", "state.commit", "artifact.read", "artifact.put", "snapshot.read",
            "snapshot.commit", "checkpoint.read", "checkpoint.save", "events.read", "events.status", "operation.status")]
        grants += [Grant("events.append", scope, run_id=ctx.run_id, producer="runtime"),
                   Grant("events.append", scope, run_id=ctx.run_id, producer="connections", event_kinds=CONNECTION_EVENTS),
                   Grant("admission.status", run_id=ctx.run_id)]
        tools = definition.allowed_tools if definition else standalone_tools
        grants.append(Grant("tool.execute", object_ids=frozenset(t.name for t in tools), run_id=ctx.run_id))
        capabilities = {cap for tool in tools for cap in self.catalog.resolve(tool.name, tool.revision).unwrap().capabilities}
        for capability in capabilities & {"network.search", "network.fetch"}:
            grants.append(Grant(capability, run_id=ctx.run_id))
        if definition:
            grants.append(Grant("model.generate", object_ids=frozenset({definition.model_ref}), run_id=ctx.run_id))
            for rule in rules:
                grants.append(Grant("agent.invoke", object_ids=frozenset({rule.destination.agent_id}), run_id=ctx.run_id))
                grants.append(Grant("tool.delegate", object_ids=frozenset(rule.allowed_tools), run_id=ctx.run_id))
        return GrantSet(grants, ctx.principal)

    async def _record(self, context, kind, payload, *, cleanup=False):
        context = context.for_cleanup() if cleanup else context
        event = ExecutionEvent(new_id("event_"), kind, "connections", context, payload)
        context.grants.grants.append(Grant("events.status", context.scope, frozenset({event.event_id}), run_id=context.run_id))
        result = await self.storage.recorder.append(context, event)
        if isinstance(result, Err) and (result.error.commit_state == "unknown" or result.error.retryable_delivery):
            status = await self.storage.recorder.status(context, event.event_id, digest_json(event))
            if isinstance(status, Ok) and status.value.state == "committed":
                return Ok(status.value.receipt)
        return result

    async def _new_context(self, options, definition=None, *, parent=None, invocation=None, rules=(), tools=()):
        self._active()
        self._contexts = {key: value for key, value in self._contexts.items() if value.lease.active}
        options = options or RunOptions()
        if isinstance(options, dict):
            options = RunOptions(**options)
        seconds = finite_seconds(options.timeout_seconds, self.settings.max_run_seconds)
        limits = narrowed_limits(self.settings.limits, options.limits)
        limits["descendants"] = min(limits.get("descendants", self.settings.max_descendants), self.settings.max_descendants)
        canonical_json(options.metadata, 16384)
        run_id, action = new_id("run_"), new_id("agent_" if definition else "tool_")
        if parent:
            seconds = min(seconds, parent.remaining_seconds())
        ctx = ExecutionContext(run_id, parent.root_run_id if parent else run_id,
            parent.correlation_id if parent else new_id("correlation_"), action,
            principal=self.settings.host_principal,
            context_kind="agent" if definition else "standalone_tool",
            agent_id=definition.agent_id if definition else None,
            definition_ref=definition.definition_ref if definition else None,
            parent_run_id=parent.run_id if parent else None,
            parent_action_id=invocation.action_id if invocation else None,
            parent_attempt_id=invocation.attempt_id if invocation else None,
            deadline=deadline_after(seconds), depth=parent.depth + 1 if parent else 0,
            ancestry=parent.ancestry + (parent.agent_id,) if parent else (),
            binding_ref=new_id("binding_"), policy_ref="local-platform/1",
            store_id=self.storage.store_id, scope=ScopeRef("run", run_id),
            metadata=copy.deepcopy(options.metadata),
            ledger=parent.ledger.branch(limits) if parent else BudgetLedger(limits))
        ctx.grants = self._grants(ctx, definition, rules, tools)
        if isinstance(options, ToolRunOptions) and options.read_objects:
            source = options.source_run_ref
            if definition is not None or source is None or source.store_id != self.storage.store_id:
                raise EngineError("ACCESS_DENIED", "Standalone source reads require an exact same-store source run")
            source_scope = ScopeRef("run", source.run_id)
            lookup = dataclasses.replace(ctx, grants=GrantSet([
                Grant("run.describe", source_scope, frozenset({source.run_id}))], ctx.principal))
            descriptor = (await self.storage.describe_run(lookup, source.run_id)).unwrap()
            if descriptor.get("owner_principal") != self.settings.host_principal:
                raise EngineError("ACCESS_DENIED", "Source run belongs to another host principal")
            for selector in options.read_objects:
                if not isinstance(selector, SnapshotReadRequest) or selector.ref.store_id != self.storage.store_id or selector.kind != "snapshot":
                    raise EngineError("INVALID_DATA", "Standalone source selector must be a same-store SnapshotReadRequest")
                ctx.grants.grants.append(Grant("snapshot.read", source_scope, frozenset({selector.ref.id}),
                    run_id=ctx.run_id, document_range=selector.range, max_text_bytes=selector.max_text_bytes))
        admin = dataclasses.replace(ctx, grants=GrantSet([Grant("admin.provision", ctx.scope)], ctx.principal))
        descriptor = ctx.descriptor()
        descriptor["owner_principal"] = self.settings.host_principal
        await_result = await self.storage.provision_run(admin, descriptor)
        await_result.unwrap()
        self._contexts[id(ctx)] = ctx
        return ctx

    async def bind(self, agent_ref, context):
        try:
            self._active()
            if self._contexts.get(id(context)) is not context:
                raise EngineError("ACCESS_DENIED", "Binding requires a live context issued by this engine")
            _, definition, rules = self._resolve(agent_ref)
            if definition.definition_ref != context.definition_ref:
                raise EngineError("ACCESS_DENIED", "Definition differs from the issued run")
            return await self._bind(context, definition, rules)
        except EngineError as error:
            return Err(error)

    async def open_agent_session(self, agent_ref, options=None):
        """Issue and bind a root for an explicit Python strategy without dispatch."""
        context = None
        try:
            _, definition, rules = self._resolve(agent_ref)
            context = await self._new_context(options, definition, rules=rules)
            bound = await self._bind(context, definition, rules)
            if isinstance(bound, Err):
                await context.lease.release()
            return bound
        except EngineError as error:
            if context:
                await context.lease.release()
            return Err(error)

    async def _bind(self, ctx, definition=None, rules=()):
        binding_context = ctx.for_action(ctx.binding_ref, None)
        try:
            for rule in rules:
                self._resolve(rule.destination)
            config = self.profiles.resolve(definition) if definition else None
            binding = BindingSet(self.catalog, self.executor, self.storage.recorder,
                self.storage.artifacts, self.storage.snapshots, ToolPlanFactory(self.storage, ctx.scope),
                provider_config=config, provider_factory=ProviderFactory, storage=self.storage,
                output_scope=ctx.scope)
            binding.invoker = AgentInvoker(self, ctx, definition, rules) if definition else None
            recorded = await self._record(binding_context, "binding.resolved", {
                "binding_ref": ctx.binding_ref, "definition_ref": ctx.definition_ref,
                "context_kind": ctx.context_kind, "policy_ref": ctx.policy_ref,
                "model_id": config.model_id if config else None,
                "profile_name": config.profile_name if config else None,
                "tools": [t.to_dict() for t in definition.allowed_tools] if definition else [],
            })
            recorded.unwrap()
            def release_owner(session):
                if session in self._sessions:
                    self._sessions.remove(session)
                self._contexts.pop(id(ctx), None)
            session = BoundSession(ctx, binding, definition, release_owner)
            self._sessions.append(session)
            return Ok(session)
        except EngineError as error:
            await self._record(binding_context, "binding.failed", {"error": error.to_dict()}, cleanup=True)
            return Err(error)

    async def run_agent(self, agent_ref, task_input, options=None):
        ctx = session = None
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            _, definition, rules = self._resolve(agent_ref)
            ctx = await self._new_context(options, definition, rules=rules)
            session = (await self._bind(ctx, definition, rules)).unwrap()
            admission = await self.runtime.admit(definition, task_input, session.binding, ctx)
            if isinstance(admission, Err):
                return AgentResult(ctx.descriptor(), "validation_failed", definition_ref=definition.definition_ref, error=admission.error)
            return await self.runtime.execute(admission.value)
        except EngineError as error:
            return AgentResult(ctx.descriptor() if ctx else {}, "failed", error=error)
        finally:
            self._tasks.discard(task)
            if session:
                await session.close()
            elif ctx:
                await ctx.lease.release()

    async def run_tool(self, tool_ref, arguments, options=None):
        ctx = session = None
        task = asyncio.current_task()
        self._tasks.add(task)
        if isinstance(tool_ref, str):
            tool_ref = ToolRef(tool_ref)
        try:
            self.catalog.resolve(tool_ref.name, tool_ref.revision).unwrap()
            ctx = await self._new_context(options, tools=(tool_ref,))
            session = (await self._bind(ctx)).unwrap()
            result = await RecordedToolAction().run(ToolRequest(tool_ref, arguments), session.binding, ctx)
            result.invocation.update({"run_id": ctx.run_id, "root_run_id": ctx.root_run_id,
                                      "store_id": ctx.store_id, "context_kind": ctx.context_kind})
            return result
        except EngineError as error:
            return ToolResult(tool_ref, ctx.descriptor() if ctx else {"dispatched": False}, "failed", error=error)
        finally:
            self._tasks.discard(task)
            if session:
                await session.close()
            elif ctx:
                await ctx.lease.release()

    async def open_run_access(self, run_ref, request=None, options=None):
        from .access import open_access
        return await open_access(self, run_ref, request or RunAccessRequest(), options or RunAccessOptions())

    async def bind_evidence(self, session, source_run_ref, evidence):
        """Host-selected owned source evidence for a live orchestrator binding.

        This imports read authority, not data or execution budgets. It enables
        a Reader's saved sources to feed a later Writer through a parent.
        """
        from .evidence import bind_host_evidence
        return await bind_host_evidence(self, session, source_run_ref, evidence)

    def list_agents(self):
        """Detached public catalog; registration never gives execution authority."""
        self._active()
        return [{"ref": ref.to_dict(), "definition_ref": definition.definition_ref,
                 "definition": definition.to_dict(), "invocation_rules": [r.to_dict() for r in rules]}
                for ref, (definition, rules, _) in sorted(self._registered.items(), key=lambda item: (item[0].agent_id, item[0].revision))]

    def list_profiles(self):
        """Safe catalog without credential resolution or endpoint disclosure."""
        self._active()
        profiles = {"deepseek": {"profile_ref": "deepseek", "model_ref": "deepseek-flash", "provider": "deepseek"},
                    "openai": {"profile_ref": "openai", "model_ref": "gpt-6-luna", "provider": "openai"}}
        for name, config in self.settings.profiles.items():
            profiles[name] = {"profile_ref": name, "model_ref": config.model_id, "provider": config.provider}
        return [profiles[name] for name in sorted(profiles)]

    async def list_runs(self, filters=None, cursor=None, limit=100):
        from .inspection import list_runs
        return await list_runs(self, filters, cursor, limit)

    async def describe_run(self, run_ref):
        from .inspection import describe_run
        return await describe_run(self, run_ref)

    async def list_run_objects(self, run_ref, cursor=None, limit=100):
        from .inspection import list_objects
        return await list_objects(self, run_ref, cursor, limit)

    async def read_run_state(self, run_ref, key, version=None):
        from .inspection import read_state
        return await read_state(self, run_ref, key, version)

    async def query_run_events(self, run_ref, after_seq=0, limit=100, include_descendants=False):
        from .inspection import query_events
        return await query_events(self, run_ref, after_seq, limit, include_descendants)

    async def close(self, deadline=None):
        if self._closed:
            return CleanupReport()
        self._closing = True
        deadline = deadline or deadline_after(30)
        from ebd.contracts import deadline_timestamp
        seconds = max(0.001, deadline_timestamp(deadline) - time.time())
        current = asyncio.current_task()
        tasks = [task for task in self._tasks if task is not current and not task.done()]
        for task in tasks:
            task.cancel()
        errors = []
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), seconds)
            except asyncio.TimeoutError:
                errors.append("active execution cleanup exceeded deadline")
        for session in tuple(self._sessions):
            await session.close()
        cleanup = await self.executor.close(deadline)
        if not cleanup.complete:
            errors.extend(cleanup.errors)
        closed = await self.storage.close(deadline)
        if isinstance(closed, Err):
            errors.append(closed.error.to_dict())
        self._closed = not errors
        return CleanupReport(not errors, errors)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()


class AgentInvoker:
    def __init__(self, engine, caller, definition, rules):
        self.engine, self.caller, self.definition, self.rules = engine, caller, definition, rules

    async def invoke(self, caller_context, destination, task_input, options=None):
        from .invocation import invoke
        return await invoke(self, caller_context, destination, task_input, options)
