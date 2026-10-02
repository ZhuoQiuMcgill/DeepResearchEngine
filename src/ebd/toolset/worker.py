"""Compatibility import; implementation: ebd.engine.toolset.worker."""
from importlib import import_module as _import_module
if __name__ == "__main__":
    _import_module("ebd.engine.toolset.worker").main()
else:
    import sys as _sys
    _sys.modules[__name__] = _import_module("ebd.engine.toolset.worker")
