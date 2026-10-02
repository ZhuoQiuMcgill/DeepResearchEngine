"""Compatibility import; implementation: ebd.interfaces.cli.main."""
from importlib import import_module as _import_module
if __name__ == "__main__":
    _import_module("ebd.interfaces.cli.main").main()
else:
    import sys as _sys
    _sys.modules[__name__] = _import_module("ebd.interfaces.cli.main")
