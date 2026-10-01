"""Real HTTP provider connectors with explicit native continuation."""
from .models import (
    ModelCall, ModelRequest, ModelResponse, ModelTool, NativeContinuation,
    PLATFORM_SEARCH_POLICY, PreparedRequest, ProviderConfig,
)

__all__ = ["ProviderConfig", "ModelRequest", "ModelResponse", "ModelTool", "ModelCall", "NativeContinuation", "PreparedRequest", "PLATFORM_SEARCH_POLICY", "ProviderFactory"]


def __getattr__(name):
    if name == "ProviderFactory":
        from .factory import ProviderFactory
        return ProviderFactory
    raise AttributeError(name)
