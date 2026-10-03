"""Visible layout and external Python compatibility after the package rename."""
from importlib import import_module
from pathlib import Path
import subprocess
import sys

import pytest

from tests.architecture.test_layers import Source, import_edges, within
import ast

ROOT = Path(__file__).resolve().parents[2]
BLOCKS = {"engine", "agent_catalog", "workflows", "methods", "extensions",
          "application", "interfaces", "bootstrap"}
ALIASES = [
    *[(f"ebd.{name}", f"deepresearch.engine.{name}") for name in (
        "agent", "providers", "toolset", "storage", "connections", "contracts",
    )],
    *[(f"ebd.{name}", f"deepresearch.{name}") for name in sorted(BLOCKS)],
    ("ebd.agent.runtime", "deepresearch.engine.agent.runtime"),
    ("ebd.providers.factory", "deepresearch.engine.providers.factory"),
    ("ebd.storage._backend", "deepresearch.engine.storage._backend"),
    ("ebd.toolset.catalog", "deepresearch.engine.toolset.catalog"),
    ("ebd.engine.contracts.core", "deepresearch.engine.contracts.core"),
    ("ebd.agent_catalog.catalog", "deepresearch.agent_catalog.catalog"),
    ("ebd.methods.baseline.workflow", "deepresearch.methods.baseline.workflow"),
    ("ebd.service.models", "deepresearch.application.agent_contracts"),
    ("ebd.service.runs", "deepresearch.application.agent_runs"),
    ("ebd.service.api", "deepresearch.interfaces.http.api"),
    ("ebd.cli", "deepresearch.interfaces.cli.main"),
    ("ebd.baseline", "deepresearch.interfaces.cli.legacy_baseline"),
]


def child(code, *arguments):
    return subprocess.run([sys.executable, "-c", code, *arguments], cwd=ROOT,
                          capture_output=True, text=True, timeout=30, check=True)


def test_source_tree_has_only_the_designed_blocks_and_one_compatibility_file():
    source = ROOT / "src"
    assert {p.name for p in source.iterdir() if p.is_dir() and p.name != "__pycache__"} == {
        "deepresearch", "ebd",
    }
    canonical = source / "deepresearch"
    assert {p.name for p in canonical.iterdir() if p.is_dir() and p.name != "__pycache__"} == BLOCKS
    assert {p.name for p in canonical.iterdir() if p.is_file()} == {"__init__.py"}
    assert {p.relative_to(source / "ebd").as_posix() for p in (source / "ebd").rglob("*")
            if "__pycache__" not in p.parts} == {"__init__.py"}


def test_repository_consumers_use_the_canonical_namespace():
    failures = []
    for directory in ("tests", "examples"):
        for path in (ROOT / directory).rglob("*.py"):
            if path == Path(__file__):
                continue  # This file alone exercises obsolete external imports.
            source = Source(path, "consumer", False, ast.parse(path.read_text(encoding="utf-8-sig")))
            for edge in import_edges(source):
                if within(edge.target, "ebd"):
                    failures.append(f"{path.relative_to(ROOT)}:{edge.line}: {edge.target}")
    assert not failures, "Repository consumers still import the compatibility namespace:\n" + "\n".join(failures)


@pytest.mark.parametrize("legacy,canonical", ALIASES)
def test_legacy_alias_has_canonical_module_identity_and_metadata(legacy, canonical):
    expected = import_module(canonical)
    attributes = {name: getattr(expected, name, None) for name in (
        "__name__", "__package__", "__loader__", "__spec__", "__path__",
    )}
    assert import_module(legacy) is expected
    assert {name: getattr(expected, name, None) for name in attributes} == attributes
    assert expected.__spec__.name == canonical


def test_legacy_first_import_resources_reload_and_monkeypatch_share_one_implementation():
    child('''
from importlib import import_module, reload, resources
old = import_module("ebd.storage._backend")
new = import_module("deepresearch.engine.storage._backend")
assert old is new and new.__spec__.name == "deepresearch.engine.storage._backend"
old._compatibility_probe = object()
assert new._compatibility_probe is old._compatibility_probe
assert reload(old) is new and new.__spec__.name == "deepresearch.engine.storage._backend"
old_catalog = resources.files("ebd.agent_catalog").joinpath("resources", "baseline.writer", "1", "definition.json")
new_catalog = resources.files("deepresearch.agent_catalog").joinpath("resources", "baseline.writer", "1", "definition.json")
assert old_catalog.read_bytes() == new_catalog.read_bytes()
assert import_module("ebd.agent_catalog").__spec__.name == "deepresearch.agent_catalog"
''')


def test_service_facade_preserves_both_existing_exports():
    service = import_module("ebd.service")
    assert service.RunService is import_module("deepresearch.application.agent_runs").RunService
    assert service.create_app is import_module("deepresearch.interfaces.http.api").create_app
    with pytest.raises(AttributeError):
        getattr(service, "unknown_export")
    with pytest.raises(ModuleNotFoundError):
        import_module("ebd.service.unknown_module")
    with pytest.raises(ModuleNotFoundError):
        import_module("ebd.agent_catalogue")


def test_canonical_root_does_not_load_compatibility_or_http():
    child('''
import sys
import deepresearch
assert "ebd" not in sys.modules
assert "fastapi" not in sys.modules
assert not any(getattr(finder, "_deepresearch_compat", False) for finder in sys.meta_path)
''')


@pytest.mark.parametrize("module", ["ebd.cli", "ebd.interfaces.cli.main"])
def test_legacy_cli_module_entrypoint(module):
    result = subprocess.run([sys.executable, "-m", module, "--help"], cwd=ROOT,
                            capture_output=True, text=True, timeout=30, check=True)
    assert "usage: deepresearch" in result.stdout and "research" in result.stdout


def test_legacy_worker_entrypoint_preserves_canonical_protocol():
    outcomes = []
    for module in ("ebd.toolset.worker", "deepresearch.engine.toolset.worker"):
        result = subprocess.run([sys.executable, "-m", module, "web.fetch", "1"],
                                input="{}", cwd=ROOT, capture_output=True, text=True, timeout=30)
        outcomes.append((result.returncode, result.stdout, result.stderr))
    assert outcomes[0] == outcomes[1]
    assert outcomes[0] == (2, "", "Private worker rejected its envelope or output limit.\n")
