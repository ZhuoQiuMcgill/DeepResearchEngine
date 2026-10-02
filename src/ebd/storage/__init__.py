"""Compatibility import; implementation: ebd.engine.storage."""
from importlib import import_module as _import_module
_impl = _import_module("ebd.engine.storage")
__all__ = getattr(_impl, "__all__", [n for n in dir(_impl) if not n.startswith("_")])
def __getattr__(name):
    return getattr(_impl, name)
