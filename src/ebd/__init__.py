"""Deprecated import bridge to deepresearch; contains no platform implementation.

Both the former flat modules and the briefly published layered ebd modules
resolve to canonical module objects. Keep migration logic here so the source
tree does not duplicate every implementation directory for compatibility.
"""
from importlib import import_module as _import_module
from importlib.abc import Loader as _Loader, MetaPathFinder as _MetaPathFinder
from importlib.machinery import ModuleSpec as _ModuleSpec
from importlib.util import find_spec as _find_spec
import sys as _sys

from deepresearch import __version__

_ALIASES = {
    "ebd.service.models": "deepresearch.application.agent_contracts",
    "ebd.service.runs": "deepresearch.application.agent_runs",
    "ebd.service.api": "deepresearch.interfaces.http.api",
    "ebd.cli": "deepresearch.interfaces.cli.main",
    "ebd.baseline": "deepresearch.interfaces.cli.legacy_baseline",
    **{f"ebd.{name}": f"deepresearch.engine.{name}" for name in (
        "agent", "providers", "toolset", "storage", "connections", "contracts",
    )},
    **{f"ebd.{name}": f"deepresearch.{name}" for name in (
        "engine", "agent_catalog", "workflows", "methods", "extensions",
        "application", "interfaces", "bootstrap",
    )},
}
_SERVICE_EXPORTS = {
    "RunService": ("deepresearch.application.agent_runs", "RunService"),
    "create_app": ("deepresearch.interfaces.http.api", "create_app"),
}


def _service_export(name):
    if name not in _SERVICE_EXPORTS:
        raise AttributeError(name)
    module, member = _SERVICE_EXPORTS[name]
    return getattr(_import_module(module), member)


class _ServiceLoader(_Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__doc__ = "Deprecated facade for individual-Agent application and HTTP services."
        module.__all__ = list(_SERVICE_EXPORTS)
        module.__getattr__ = _service_export


class _AliasLoader(_Loader):
    def __init__(self, target, target_spec):
        self.target = target
        self.target_spec = target_spec
        self.attributes = None

    def create_module(self, spec):
        module = _import_module(self.target)
        self.attributes = {name: getattr(module, name, None) for name in (
            "__name__", "__package__", "__loader__", "__spec__", "__path__",
        )}
        return module

    def exec_module(self, module):
        # importlib assigns the alias spec even to an existing module. Restore
        # its canonical identity for resources, reload and subsequent imports.
        for name, value in self.attributes.items():
            if value is None:
                module.__dict__.pop(name, None)
            else:
                setattr(module, name, value)

    def get_code(self, fullname):
        # Support previously documented `python -m ebd.cli` / tool workers.
        return self.target_spec.loader.get_code(self.target)

    def get_filename(self, fullname):
        return self.target_spec.origin


class _LegacyFinder(_MetaPathFinder):
    _deepresearch_compat = True

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "ebd.service":
            return _ModuleSpec(fullname, _ServiceLoader(), is_package=True)
        for old, new in _ALIASES.items():
            if fullname == old or fullname.startswith(old + "."):
                canonical = new + fullname[len(old):]
                try:
                    spec = _find_spec(canonical)
                except ModuleNotFoundError as error:
                    if error.name == canonical or canonical.startswith(error.name + "."):
                        return None
                    raise
                if spec is None:
                    return None
                return _ModuleSpec(fullname, _AliasLoader(canonical, spec),
                                   origin=spec.origin,
                                   is_package=spec.submodule_search_locations is not None)
        return None


if not any(getattr(finder, "_deepresearch_compat", False) for finder in _sys.meta_path):
    _sys.meta_path.insert(0, _LegacyFinder())
