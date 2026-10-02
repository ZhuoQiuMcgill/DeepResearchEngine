"""Versioned role resources compiled for the existing Agent runtime."""

from .catalog import AgentCatalog, AgentSpec, CatalogError

__all__ = ["AgentCatalog", "AgentSpec", "CatalogError"]
