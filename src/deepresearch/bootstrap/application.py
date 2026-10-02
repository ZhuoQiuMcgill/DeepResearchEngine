"""The only layer that knows concrete methods and their reusable infrastructure."""
from __future__ import annotations

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.engine.providers.tokenization import TokenMeter
from deepresearch.extensions import ExtensionRegistry
from deepresearch.methods.baseline import BaselineMethod, definition
from deepresearch.methods.baseline.v1 import BaselineMethod as BaselineV1Method, definition as definition_v1
from deepresearch.methods.example_echo import EchoMethod, definition as echo_definition
from deepresearch.workflows import MethodRegistry


def create_method_registry():
    registry = MethodRegistry()
    registry.register(definition_v1(), BaselineV1Method())
    registry.register(definition(), BaselineMethod())
    registry.register(echo_definition(), EchoMethod())
    return registry


def create_research_service(engine, *, registry=None, agent_catalog=None, token_meter=None,
                            extensions=None, max_active_runs=8):
    from deepresearch.application.research_runs import ResearchRunService
    return ResearchRunService(engine, registry or create_method_registry(),
        agent_catalog or AgentCatalog(), token_meter or TokenMeter(),
        extension_registry=extensions or ExtensionRegistry(), max_active_runs=max_active_runs)
