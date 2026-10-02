"""Outermost composition of registered methods and application services."""
from .application import create_method_registry, create_research_service

__all__ = ["create_method_registry", "create_research_service"]
