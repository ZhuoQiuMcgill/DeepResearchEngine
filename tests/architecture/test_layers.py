"""Guard the canonical module migration without importing executable EBD code.

Compatibility entrypoints are exempt from dependency rules. Canonical modules
must use the new paths even in deferred/TYPE_CHECKING imports. Packaging and
catalog-asset loading are covered by catalog tests, not duplicated here.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path

import pytest


SRC = Path(__file__).resolve().parents[2] / "src"
LEGACY_ROOTS = tuple(f"ebd.{name}" for name in (
    "agent", "providers", "toolset", "storage", "connections", "contracts",
    "service", "cli", "baseline",
))
ENGINE_FORBIDDEN = tuple(f"ebd.{name}" for name in (
    "workflows", "methods", "application", "interfaces", "bootstrap",
    "agent_catalog", "extensions",
))
WORKFLOW_FORBIDDEN = tuple(f"ebd.{name}" for name in (
    "methods", "application", "interfaces", "bootstrap",
))
WORKFLOW_ENGINE_ALLOWED = ("ebd.engine.contracts", "ebd.engine.providers.tokenization")
# Intra-layer imports remain valid, including a method package's .workflow.
METHOD_ALLOWED = ("ebd.methods", "ebd.workflows", "ebd.engine.contracts")
METHOD_HTTP = (
    "httpx", "requests", "aiohttp", "urllib3", "urllib.request", "http.client",
    "fastapi", "starlette", "uvicorn",
)
APPLICATION_FORBIDDEN = ("ebd.methods", "ebd.interfaces", "ebd.bootstrap")

# Definitions, rather than mere files/re-exports, prove implementations moved.
# Shared agent DTOs belong to application, and the legacy single-agent script
# belongs to the CLI; neither is an implementation under methods or HTTP DTOs.
MIGRATED_DEFINITIONS = (
    ("ebd.engine.agent.runtime", "Runtime", ast.ClassDef),
    ("ebd.engine.providers.factory", "ProviderFactory", ast.ClassDef),
    ("ebd.engine.toolset.catalog", "ToolCatalog", ast.ClassDef),
    ("ebd.engine.storage.session", "StorageSession", ast.ClassDef),
    ("ebd.engine.connections.engine", "Engine", ast.ClassDef),
    ("ebd.engine.contracts.core", "EngineError", ast.ClassDef),
    ("ebd.application.agent_runs", "RunService", ast.ClassDef),
    ("ebd.application.agent_contracts", "RegisterAgentRequest", ast.ClassDef),
    ("ebd.interfaces.http.api", "create_app", ast.FunctionDef),
    ("ebd.interfaces.cli.main", "main", ast.FunctionDef),
    ("ebd.interfaces.cli.legacy_baseline", "run_baseline", ast.AsyncFunctionDef),
)


@dataclass(frozen=True)
class Source:
    path: Path
    module: str
    is_package: bool
    tree: ast.Module

    @property
    def package(self) -> str:
        return self.module if self.is_package else self.module.rpartition(".")[0]


@dataclass(frozen=True)
class ImportEdge:
    line: int
    target: str
    statement: str


def within(module: str, root: str) -> bool:
    # ebd.agent_catalog is not a child of the old ebd.agent package.
    return module == root or module.startswith(root + ".")


def compatibility(module: str) -> bool:
    return module == "ebd" or any(within(module, root) for root in LEGACY_ROOTS)


def from_base(source: Source, node: ast.ImportFrom) -> str:
    name = "." * node.level + (node.module or "")
    if node.level:
        try:
            return resolve_name(name, source.package)
        except (ImportError, ValueError):
            pytest.fail(f"{source.path}:{node.lineno}: relative import escapes its package: {ast.unparse(node)}")
    return name


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def literal_import_edges(source: Source):
    """Catch literal dynamic imports through unambiguous module-level aliases.

    Ordinary string literals, resource names and nonliteral runtime import
    expressions are not dependencies inferred by this static check. Aliases
    shadowed elsewhere are ignored rather than guessing their runtime binding.
    """
    aliases = {"__import__": "__import__"}
    for node in source.tree.body:
        if isinstance(node, ast.Import):
            for name in node.names:
                aliases[name.asname or name.name.split(".")[0]] = name.name if name.asname else name.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            base = from_base(source, node)
            for name in node.names:
                if name.name != "*":
                    aliases[name.asname or name.name] = f"{base}.{name.name}"
    shadowed = {
        node.id for node in ast.walk(source.tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    shadowed.update(node.arg for node in ast.walk(source.tree) if isinstance(node, ast.arg))
    shadowed.update(node.name for node in ast.walk(source.tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if not name:
            continue
        head, _, suffix = name.partition(".")
        if head in shadowed or head not in aliases:
            continue
        called = aliases[head] + ("." + suffix if suffix else "")
        if called not in ("importlib.import_module", "__import__"):
            continue
        argument = node.args[0] if node.args else next(
            (item.value for item in node.keywords if item.arg == "name"), None,
        )
        if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
            continue
        target = argument.value
        if target.startswith("."):
            if called != "importlib.import_module":
                continue
            package = node.args[1] if len(node.args) > 1 else next(
                (item.value for item in node.keywords if item.arg == "package"), None,
            )
            if isinstance(package, ast.Name) and package.id == "__package__":
                package_name = source.package
            elif isinstance(package, ast.Constant) and isinstance(package.value, str):
                package_name = package.value
            else:
                continue
            target = resolve_name(target, package_name)
        yield ImportEdge(node.lineno, target, ast.unparse(node))


def import_edges(source: Source) -> tuple[ImportEdge, ...]:
    edges = []
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Import):
            edges.extend(ImportEdge(node.lineno, name.name, ast.unparse(node)) for name in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = from_base(source, node)
            # Resolve imported members too: 'from ebd import storage' and
            # 'from ebd.engine import contracts' identify different boundaries.
            # Do not reject the parent ebd.engine for an allowed contracts import.
            edges.extend(ImportEdge(node.lineno, base if name.name == "*" else f"{base}.{name.name}",
                                    ast.unparse(node)) for name in node.names)
    edges.extend(literal_import_edges(source))
    return tuple(sorted(edges, key=lambda edge: (edge.line, edge.target)))


def violation(module: str, target: str) -> str | None:
    if compatibility(module):
        return None
    if any(within(target, root) for root in LEGACY_ROOTS):
        return "canonical implementation imports an old compatibility path"
    if within(module, "ebd.engine") and any(within(target, root) for root in ENGINE_FORBIDDEN):
        return "engine depends on a higher layer"
    if within(module, "ebd.workflows"):
        if any(within(target, root) for root in WORKFLOW_FORBIDDEN):
            return "workflow framework depends on a concrete method or host layer"
        if within(target, "ebd.engine") and not any(within(target, root) for root in WORKFLOW_ENGINE_ALLOWED):
            return "workflow bypasses its platform port; only engine contracts/tokenization are allowed"
    if within(module, "ebd.methods"):
        if within(target, "ebd") and not any(within(target, root) for root in METHOD_ALLOWED):
            return "method depends outside workflows/shared contracts or its own layer"
        if any(within(target, root) for root in METHOD_HTTP):
            return "method imports HTTP transport/framework code"
    if within(module, "ebd.application") and any(within(target, root) for root in APPLICATION_FORBIDDEN):
        return "application imports concrete composition or an interface"
    # bootstrap is the composition root; canonical concrete imports are valid.
    return None


@pytest.fixture(scope="module")
def sources() -> dict[str, Source]:
    assert SRC.is_dir(), f"Missing source tree: {SRC}"
    result = {}
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC)
        parts = relative.with_suffix("").parts
        is_package = parts[-1] == "__init__"
        module = ".".join(parts[:-1] if is_package else parts)
        assert module not in result, f"Module/file-package collision: {result.get(module)} and {relative}"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
        result[module] = Source(relative, module, is_package, tree)
    assert result, f"No Python sources found under {SRC}"
    return result


@pytest.mark.parametrize("module,name,node_type", MIGRATED_DEFINITIONS,
                         ids=[item[0] for item in MIGRATED_DEFINITIONS])
def test_implementations_live_in_canonical_layers(sources, module, name, node_type):
    assert module in sources, f"Migration target missing: {module}"
    source = sources[module]
    assert any(isinstance(node, node_type) and node.name == name for node in source.tree.body), (
        f"{source.path}: {name} must be defined here, not merely forwarded to a legacy implementation"
    )


def test_canonical_imports_respect_layer_boundaries(sources):
    failures = []
    for source in sources.values():
        for edge in import_edges(source):
            reason = violation(source.module, edge.target)
            if reason:
                failures.append(f"{source.path}:{edge.line}: {reason}: {edge.target} ({edge.statement})")
    assert not failures, "Architecture boundary violations:\n" + "\n".join(failures)


# These cases exercise the analyzer's important blind spots/false positives,
# independently of the repository migration and without runtime EBD imports.
@pytest.mark.parametrize("module,is_package,code,targets", [
    ("ebd.workflows.context", False, "from .contracts import Contract", ("ebd.workflows.contracts.Contract",)),
    ("ebd.workflows", True, "from . import contracts", ("ebd.workflows.contracts",)),
    ("ebd.workflows.components.discovery", False, "from ..contracts import FetchItem", ("ebd.workflows.contracts.FetchItem",)),
    ("ebd.workflows.components.discovery", False, "from ...contracts import EngineError", ("ebd.contracts.EngineError",)),
    ("ebd.engine.connections.engine", False, "from ..contracts import EngineError", ("ebd.engine.contracts.EngineError",)),
    ("ebd.engine.connections.engine", False, "from ... import extensions", ("ebd.extensions",)),
    ("ebd.application.agent_runs", False, "from .agent_contracts import RunView", ("ebd.application.agent_contracts.RunView",)),
    ("ebd.application.agent_runs", False, "from ..interfaces.http import create_app", ("ebd.interfaces.http.create_app",)),
    ("ebd.workflows.context", False, "from ebd.engine import contracts", ("ebd.engine.contracts",)),
    ("ebd.workflows.context", False, "from ebd.engine.providers import tokenization", ("ebd.engine.providers.tokenization",)),
    ("ebd.engine.agent.runtime", False, "from ebd import methods as strategy", ("ebd.methods",)),
    ("ebd.methods.baseline.workflow", False, "import ebd.engine.connections as platform, httpx as client", ("ebd.engine.connections", "httpx")),
    ("ebd.workflows.context", False, "from ebd.engine.providers import *", ("ebd.engine.providers",)),
    ("ebd.application.agent_runs", False, "if TYPE_CHECKING:\n    from ebd.interfaces.http import create_app", ("ebd.interfaces.http.create_app",)),
    ("ebd.engine.agent.runtime", False, "async def run():\n    from ebd.application.agent_runs import RunService", ("ebd.application.agent_runs.RunService",)),
    ("ebd.bootstrap.application", False, 'from importlib import import_module as load\nload("ebd.methods.baseline")', ("importlib.import_module", "ebd.methods.baseline")),
    ("ebd.workflows.context", False, 'import importlib as loader\nloader.import_module("..storage", package=__package__)', ("importlib", "ebd.storage")),
    ("ebd.application.agent_runs", False, '__import__("ebd.service.models")', ("ebd.service.models",)),
    ("ebd.workflows.context", False, 'label = "from ebd.storage import StorageSession"\n# from ebd.methods import baseline', ()),
    ("ebd.workflows.context", False, 'def load(name):\n    return name\nload("ebd.storage")', ()),
    ("ebd.workflows.context", False, 'from importlib import import_module as load\ndef helper(load):\n    return load("ebd.storage")', ("importlib.import_module",)),
])
def test_analyzer_resolves_packages_and_actual_import_nodes(module, is_package, code, targets):
    source = Source(Path("synthetic.py"), module, is_package, ast.parse(code))
    assert tuple(edge.target for edge in import_edges(source)) == targets


@pytest.mark.parametrize("module,target,forbidden", [
    ("ebd.engine.agent.runtime", "ebd.methods.baseline.BaselineMethod", True),
    ("ebd.engine.storage.session", "ebd.workflows.contracts.ResearchRunView", True),
    ("ebd.engine.providers.factory", "ebd.application.agent_contracts.RunView", True),
    ("ebd.engine.contracts.core", "ebd.interfaces.http.create_app", True),
    ("ebd.engine.connections.engine", "ebd.bootstrap.create_method_registry", True),
    ("ebd.engine.agent.runtime", "ebd.agent_catalog.AgentCatalog", True),
    ("ebd.engine.agent.runtime", "ebd.extensions.HookEvent", True),
    ("ebd.workflows.context", "ebd.engine.Engine", True),
    ("ebd.workflows.context", "ebd.engine.storage.StorageSession", True),
    ("ebd.workflows.components.discovery", "ebd.engine.toolset.ToolCatalog", True),
    ("ebd.workflows.context", "ebd.engine.agent.Runtime", True),
    ("ebd.workflows.context", "ebd.engine.providers.ProviderFactory", True),
    ("ebd.workflows.context", "ebd.engine.providers.tokenization_extra.TokenMeter", True),
    ("ebd.workflows.context", "ebd.methods.baseline.BaselineMethod", True),
    ("ebd.workflows.context", "ebd.application.platform.ResearchPlatformPort", True),
    ("ebd.workflows.context", "ebd.interfaces.http.research", True),
    ("ebd.workflows.context", "ebd.bootstrap.application", True),
    ("ebd.methods.baseline.workflow", "ebd.engine.Engine", True),
    ("ebd.methods.baseline.workflow", "ebd.engine.providers.tokenization.TokenMeter", True),
    ("ebd.methods.baseline.workflow", "ebd.engine.storage.StorageSession", True),
    ("ebd.methods.baseline.workflow", "ebd.engine.toolset.ToolCatalog", True),
    ("ebd.methods.baseline.workflow", "ebd.application.platform.ResearchPlatformPort", True),
    ("ebd.methods.baseline.workflow", "ebd.agent_catalog.AgentCatalog", True),
    ("ebd.methods.baseline.workflow", "ebd.extensions.HookDispatcher", True),
    ("ebd.methods.baseline.workflow", "httpx.AsyncClient", True),
    ("ebd.methods.baseline.workflow", "fastapi.FastAPI", True),
    ("ebd.methods.baseline.workflow", "urllib.request.urlopen", True),
    ("ebd.application.agent_runs", "ebd.methods.baseline.BaselineMethod", True),
    ("ebd.application.agent_runs", "ebd.interfaces.http.api.create_app", True),
    ("ebd.application.agent_contracts", "ebd.interfaces.http.models.RunView", True),
    ("ebd.application.agent_runs", "ebd.bootstrap.create_research_service", True),
    ("ebd.extensions.types", "ebd.contracts.EngineError", True),
    ("ebd.agent_catalog.catalog", "ebd.agent.runtime.DEFAULT_LIMITS", True),
    ("ebd.bootstrap.application", "ebd.connections.Engine", True),
    ("ebd.workflows.context", "ebd.engine.contracts.EngineError", False),
    ("ebd.workflows.context", "ebd.engine.providers.tokenization.TokenMeter", False),
    ("ebd.workflows.context", "ebd.extensions.HookEvent", False),
    ("ebd.workflows.context", "ebd.workflows.contracts.Contract", False),
    ("ebd.methods.baseline", "ebd.methods.baseline.workflow.BaselineMethod", False),
    ("ebd.methods.baseline.workflow", "ebd.workflows.components.discovery.discover", False),
    ("ebd.methods.baseline.workflow", "ebd.engine.contracts.EngineError", False),
    ("ebd.methods.baseline.workflow", "urllib.parse.urlsplit", False),
    ("ebd.application.agent_runs", "ebd.application.agent_contracts.RunView", False),
    ("ebd.application.agent_runs", "ebd.engine.connections.Engine", False),
    ("ebd.interfaces.http.api", "ebd.application.agent_contracts.RunView", False),
    ("ebd.interfaces.cli.legacy_baseline", "ebd.engine.connections.Engine", False),
    ("ebd.bootstrap.application", "ebd.methods.baseline.BaselineMethod", False),
    ("ebd.bootstrap.application", "ebd.engine.Engine", False),
    ("ebd.service.models", "ebd.application.agent_contracts.RunView", False),
    ("ebd.service.api", "ebd.interfaces.http.api.create_app", False),
    ("ebd.baseline", "ebd.interfaces.cli.legacy_baseline.run_baseline", False),
    ("ebd.cli", "ebd.bootstrap.create_research_service", False),
    ("ebd.agent.runtime", "ebd.contracts.EngineError", False),
    ("ebd", "ebd.contracts.EngineError", False),
    ("ebd.engine.agent.runtime", "ebd.engine.contracts.EngineError", False),
    ("ebd.engine.agent.runtime", "ebd.engine.providers.ProviderFactory", False),
    ("ebd.application.agent_runs", "ebd.agent_catalog.AgentCatalog", False),
])
def test_policy_covers_forbidden_edges_and_intended_exceptions(module, target, forbidden):
    assert (violation(module, target) is not None) is forbidden
