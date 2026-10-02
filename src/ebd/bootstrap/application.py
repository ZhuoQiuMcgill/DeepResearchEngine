"""The only layer that knows concrete methods and their reusable infrastructure."""
from __future__ import annotations

from ebd.agent_catalog import AgentCatalog
from ebd.engine.providers.tokenization import TokenMeter
from ebd.extensions import ExtensionRegistry
from ebd.methods.baseline import BaselineMethod, definition
from ebd.methods.example_echo import EchoMethod, definition as echo_definition
from ebd.workflows import MethodRegistry


def create_method_registry():
    registry = MethodRegistry()
    registry.register(definition(), BaselineMethod())
    registry.register(echo_definition(), EchoMethod())
    return registry


def create_research_service(engine, *, registry=None, agent_catalog=None, token_meter=None,
                            extensions=None, max_active_runs=8):
    from ebd.application.research_runs import ResearchRunService
    return ResearchRunService(engine, registry or create_method_registry(),
        agent_catalog or AgentCatalog(), token_meter or TokenMeter(),
        extension_registry=extensions or ExtensionRegistry(), max_active_runs=max_active_runs)
