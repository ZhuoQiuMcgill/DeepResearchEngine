"""Execution platform facade; submodule imports do not compose an application."""
from importlib import import_module

__all__ = ["Engine", "EngineSettings", "RunOptions", "ToolRunOptions", "AgentDefinition", "EngineError", "ToolRef"]


def __getattr__(name):
    for package in ("deepresearch.engine.connections", "deepresearch.engine.contracts"):
        module = import_module(package)
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(name)
