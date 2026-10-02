"""Compatibility import; implementation: ebd.engine.connections.access."""
from importlib import import_module as _import_module
import sys as _sys
_sys.modules[__name__] = _import_module("ebd.engine.connections.access")
