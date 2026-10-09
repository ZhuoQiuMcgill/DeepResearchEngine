"""The only layer that knows concrete methods and their reusable infrastructure."""
from __future__ import annotations

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.engine.providers.tokenization import TokenMeter
from deepresearch.extensions import ExtensionRegistry
from deepresearch.methods.baseline import BaselineMethod, EnglishBaselineMethod, ExpandedBaselineMethod, ParallelBaselineMethod, SelectionBaselineMethod, definition
from deepresearch.methods.baseline.v1 import BaselineMethod as BaselineV1Method, definition as definition_v1
from deepresearch.methods.example_echo import EchoMethod, definition as echo_definition
from deepresearch.workflows import MethodRegistry


def create_method_registry():
    registry = MethodRegistry()
    registry.register(definition_v1(), BaselineV1Method())
    registry.register(definition(), BaselineMethod())
    registry.register(definition(3), ExpandedBaselineMethod())
    registry.register(definition(4), EnglishBaselineMethod())
    registry.register(definition(5), ParallelBaselineMethod())
    registry.register(definition(6), ParallelBaselineMethod(6))
    registry.register(definition(7), SelectionBaselineMethod())
    registry.register(definition(8), SelectionBaselineMethod(8))
    registry.register(definition(9), SelectionBaselineMethod(9))
    registry.register(definition(10), SelectionBaselineMethod(10))
    registry.register(definition(11), SelectionBaselineMethod(11))
    registry.register(definition(12), SelectionBaselineMethod(12))
    registry.register(definition(13), SelectionBaselineMethod(13))
    registry.register(echo_definition(), EchoMethod())
    return registry


def create_research_service(engine, *, registry=None, agent_catalog=None, token_meter=None,
                            extensions=None, max_active_runs=8, recovery_policy=None):
    from deepresearch.application.research_runs import ResearchRunService
    return ResearchRunService(engine, registry or create_method_registry(),
        agent_catalog or AgentCatalog(), token_meter or TokenMeter(),
        extension_registry=extensions or ExtensionRegistry(), max_active_runs=max_active_runs,
        recovery_policy=recovery_policy)
