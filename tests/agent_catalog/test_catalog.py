"""Catalog boundary checks with real bundles and deliberately malformed assets."""
import json
import shutil
import traceback
from importlib import resources

import pytest

from deepresearch.agent_catalog import AgentCatalog, CatalogError
from deepresearch.engine.contracts import ToolRef, digest_bytes


@pytest.fixture
def bundle_root(tmp_path):
    root = tmp_path / "roles"
    shutil.copytree(resources.files("deepresearch.agent_catalog").joinpath("resources"), root)
    return root


def edit_json(root, filename, change):
    path = root / "baseline.writer" / "1" / filename
    value = json.loads(path.read_text(encoding="utf-8"))
    change(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_packaged_writer_has_the_parent_input_contract_and_no_tools():
    writer = AgentCatalog().load("baseline.writer", 1)
    task = writer.render_task({"question": "What is supported?", "evidence": "[source-1] Selected retained text."})
    definition = writer.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=(),
                                           limits={"max_model_calls": 2})
    assert definition.agent_id == "baseline.writer" and definition.revision == 1
    assert "What is supported?" in task and "[source-1] Selected retained text." in task
    assert definition.allowed_tools == []
    assert definition.profile_ref == "deepseek" and definition.model_ref == "deepseek-flash"
    assert definition.input_schema["type"] == "string"
    assert definition.output_mode == "text" and definition.output_media_type == "text/markdown"
    assert definition.output_contract["delivery"] == "artifact"
    assert definition.limits["max_model_calls"] == 1  # Host approval cannot raise the Writer's one-call limit.
    writer.validate_output("# Supported findings\n\nEvidence supports this claim.")
    with pytest.raises(CatalogError, match="pinned schema"):
        writer.validate_output({"markdown": "Wrong result type"})
    with pytest.raises(CatalogError):
        writer.validate_output("")


@pytest.mark.parametrize("input", [
    {"question": "Question"}, {"evidence": "Evidence"},
    {"question": "Question", "evidence": "Evidence", "tools": ["web.fetch"]},
    {"question": 42, "evidence": "Evidence"}, {"question": "", "evidence": "Evidence"},
    "Unstructured task", {"question": "Q", "evidence": float("nan")},
    {"question": "Q", "evidence": {"value": object()}},
])
def test_writer_rejects_missing_unknown_and_non_json_input(input):
    with pytest.raises(CatalogError):
        AgentCatalog().load("baseline.writer", 1).render_task(input)


def test_substitution_preserves_untrusted_dollars_braces_and_unicode(bundle_root):
    path = bundle_root / "baseline.writer" / "1" / "task.md"
    path.write_text("Cost $$5\n${question}\n$evidence", encoding="utf-8", newline="\n")
    writer = AgentCatalog(bundle_root).load("baseline.writer", 1)
    evidence = "${question} $HOME {{ config }} {evidence.__class__} café 中文"
    assert writer.render_task({"question": "Literal ${evidence}", "evidence": evidence}) == (
        "Cost $5\nLiteral ${evidence}\n" + evidence)


@pytest.mark.parametrize("template", ["${unknown}", "${question.__class__}", "${question[0]}", "$", "${question", "$optional"])
def test_invalid_or_undeclared_template_variables_reject_at_load(bundle_root, template):
    path = bundle_root / "baseline.writer" / "1" / "task.md"
    path.write_text(template, encoding="utf-8")
    edit_json(bundle_root, "input.schema.json", lambda s: s["properties"].update(optional={"type": "string"}))
    with pytest.raises(CatalogError) as error:
        AgentCatalog(bundle_root).load("baseline.writer", 1)
    assert error.value.code == "INVALID_TEMPLATE"


def test_structured_template_values_are_canonical_json(bundle_root):
    edit_json(bundle_root, "input.schema.json", lambda s: s["properties"].update(evidence={
        "type": "array", "items": {"type": "object", "additionalProperties": False,
        "properties": {"text": {"type": "string"}, "id": {"type": "integer"}}, "required": ["id", "text"]}}))
    writer = AgentCatalog(bundle_root).load("baseline.writer", 1)
    assert '[{"id":1,"text":"$question"}]' in writer.render_task({"question": "Q", "evidence": [{"text": "$question", "id": 1}]})
    with pytest.raises(CatalogError):
        writer.render_task({"question": "Q", "evidence": [{"text": "T", "id": 1, "grant": True}]})


def test_exact_host_tool_revisions_are_intersected_and_cannot_add_requests():
    spec = AgentCatalog().load("baseline.researcher", 1)
    assert spec.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash").allowed_tools == []
    approved = (ToolRef("web.search", 1), ToolRef("web.fetch", 2), ToolRef("unrequested.tool", 1))
    definition = spec.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=approved)
    assert definition.allowed_tools == [ToolRef("web.search", 1)]
    writer = AgentCatalog().load("baseline.writer", 1)
    assert writer.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=approved).allowed_tools == []
    with pytest.raises(CatalogError):
        spec.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=("web.search",))
    with pytest.raises(CatalogError):
        spec.compile_definition(profile_ref="deepseek", model_ref="deepseek-flash", tools=(ToolRef("web.search", True),))


def test_limits_only_narrow_and_compilations_are_independent(bundle_root):
    edit_json(bundle_root, "definition.json", lambda d: d["limits"].update(
        max_model_calls=3, token_budget={"max_total_tokens": 1000, "enforcement": "advisory"}))
    spec = AgentCatalog(bundle_root).load("baseline.writer", 1)
    definition = spec.compile_definition(profile_ref="p", model_ref="m", limits={
        "max_model_calls": 100, "max_run_seconds": 7.5,
        "token_budget": {"max_total_tokens": 500, "enforcement": "advisory"}})
    assert definition.limits["max_model_calls"] == 3
    assert definition.limits["max_run_seconds"] == 7.5
    assert definition.limits["token_budget"] == {"max_total_tokens": 500, "enforcement": "advisory"}
    definition.instructions = "Caller mutation"
    definition.limits["max_model_calls"] = 200
    definition.output_schema["type"] = "object"
    copied_schema = spec.input_schema
    copied_schema["properties"]["question"]["type"] = "integer"
    copied_pin = spec.ref
    copied_pin["resource_digests"].clear()
    again = spec.compile_definition(profile_ref="p", model_ref="m", limits={"token_budget": None})
    assert again.instructions != "Caller mutation" and again.limits["max_model_calls"] == 3
    assert again.limits["token_budget"]["max_total_tokens"] == 1000
    assert again.output_schema["type"] == "string" and len(spec.resource_digests) == 5
    assert spec.render_task({"question": "Still a string", "evidence": ""})


@pytest.mark.parametrize("limits", [
    {"unknown_budget": 1}, {"max_model_calls": True}, {"max_model_calls": 1.5},
    {"max_run_seconds": 0}, {"max_run_seconds": float("inf")},
    {"token_budget": {"max_total_tokens": 5, "enforcement": "strict"}},
    {"token_budget": {"max_total_tokens": 5, "enforcement": "advisory", "override": True}},
])
def test_invalid_host_limits_reject_before_registration(limits):
    with pytest.raises(CatalogError):
        AgentCatalog().load("baseline.writer", 1).compile_definition(profile_ref="p", model_ref="m", limits=limits)


def test_revision_pin_covers_every_original_file_and_rejects_content_drift(bundle_root):
    catalog = AgentCatalog(bundle_root)
    spec = catalog.load("baseline.writer", 1)
    directory = bundle_root / "baseline.writer" / "1"
    assert spec.resource_digests == {file.name: digest_bytes(file.read_bytes()) for file in directory.iterdir()}
    assert catalog.load("baseline.writer", 1, expected_digest=spec.ref["sha256"]).ref == spec.ref
    frozen = spec.compile_definition(profile_ref="p", model_ref="m").definition_ref
    path = directory / "input.schema.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(CatalogError) as error:
        catalog.load("baseline.writer", 1)
    assert error.value.code == "REVISION_CONFLICT"
    with pytest.raises(CatalogError) as error:
        AgentCatalog(bundle_root).load("baseline.writer", 1, expected_digest=spec.ref["sha256"])
    assert error.value.code == "REVISION_CONFLICT"
    changed = AgentCatalog(bundle_root).load("baseline.writer", 1)
    assert changed.compile_definition(profile_ref="p", model_ref="m").definition_ref != frozen
    assert spec.compile_definition(profile_ref="p", model_ref="m").definition_ref == frozen
    assert spec.ref["sha256"] in spec.compile_definition(profile_ref="p", model_ref="m").input_schema["$comment"]


def test_new_revisions_do_not_alias_or_overwrite_old_ones(bundle_root):
    catalog = AgentCatalog(bundle_root)
    first = catalog.load("baseline.writer", 1)
    with pytest.raises(CatalogError) as error:
        catalog.load("baseline.writer", 3)
    assert error.value.code == "RESOURCE_NOT_FOUND"
    second = bundle_root / "baseline.writer" / "3"
    shutil.copytree(second.parent / "1", second)
    path = second / "definition.json"
    definition = json.loads(path.read_text(encoding="utf-8"))
    definition["revision"] = 3
    path.write_text(json.dumps(definition), encoding="utf-8")
    two = catalog.load("baseline.writer", 3)
    assert two.revision == 3 and two.ref["sha256"] != first.ref["sha256"]
    assert catalog.load("baseline.writer", 1).ref == first.ref


@pytest.mark.parametrize("role,revision", [("../writer", 1), ("baseline/writer", 1), ("baseline.writer", "latest"), ("baseline.writer", True), ("baseline.writer", 0)])
def test_identity_validation_prevents_path_traversal_and_floating_revisions(role, revision):
    with pytest.raises(CatalogError) as error:
        AgentCatalog().load(role, revision)
    assert error.value.code == "INVALID_IDENTITY"


@pytest.mark.parametrize("filename,contents", [
    ("definition.json", b'{"role_id":"baseline.writer","role_id":"duplicate"}'),
    ("definition.json", b'{"schema_version":NaN}'),
    ("definition.json", b"[]"),
    ("instructions.md", b" "),
    ("instructions.md", b"\xff"),
    ("instructions.md", b"x" * 32769),
    ("task.md", b"x" * 65537),
    ("output.schema.json", b"{"),
], ids=["duplicate-keys", "nonfinite-json", "wrong-root", "blank-instructions", "invalid-utf8",
        "instruction-byte-bound", "task-byte-bound", "broken-schema-json"])
def test_malformed_or_oversized_resources_reject_at_load(bundle_root, filename, contents):
    (bundle_root / "baseline.writer" / "1" / filename).write_bytes(contents)
    with pytest.raises(CatalogError):
        AgentCatalog(bundle_root).load("baseline.writer", 1)


@pytest.mark.parametrize("change", [
    lambda d: d.update(settings={"secret": "resource-secret-marker"}),
    lambda d: d.update(revision=2), lambda d: d.update(schema_version=True),
    lambda d: d["limits"].update(max_model_calls=-1),
    lambda d: d["limits"].update(max_run_seconds=10 ** 400),
    lambda d: d["output"].update(schema={}), lambda d: d["output"].update(mode="json"),
    lambda d: d["output"].update(max_bytes=True),
    lambda d: d["tool_requests"].append({"name": "web.fetch", "revision": 1, "grant": True}),
])
def test_closed_definition_properties_and_runtime_invariants(bundle_root, change):
    edit_json(bundle_root, "definition.json", change)
    with pytest.raises(CatalogError) as error:
        AgentCatalog(bundle_root).load("baseline.writer", 1)
    assert "resource-secret-marker" not in str(error.value)


@pytest.mark.parametrize("schema", [
    {"type": "string", "minLenght": 1},
    {"$ref": "https://untrusted.invalid/schema"},
    {"$dynamicRef": "https://untrusted.invalid/schema"},
    {"$id": "https://untrusted.invalid/schema", "type": "string"},
    {"$ref": "#/missing"}, {"$ref": "#/enum/0", "enum": [{"type": "string"}]},
    {"$ref": "#/$defs/node", "$defs": {"node": {"$ref": "#/$defs/node"}}},
    {"type": "object", "properties": {"field": {"type": "string"}}},
    {"type": "string", "pattern": "(a+)+$"}, {"type": "string", "format": "uri"},
])
def test_schema_typos_external_resolution_and_recursive_references_reject(bundle_root, schema):
    path = bundle_root / "baseline.writer" / "1" / "output.schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(CatalogError):
        AgentCatalog(bundle_root).load("baseline.writer", 1)


def test_local_schema_references_validate_without_fetching(bundle_root):
    edit_json(bundle_root, "input.schema.json", lambda s: s.update(
        properties={"question": {"$ref": "#/$defs/text"}, "evidence": {"$ref": "#/$defs/text"}},
        **{"$defs": {"text": {"type": "string", "maxLength": 10}}}))
    spec = AgentCatalog(bundle_root).load("baseline.writer", 1)
    assert spec.render_task({"question": "Q", "evidence": "E"})
    with pytest.raises(CatalogError):
        spec.render_task({"question": "Q", "evidence": "Over ten characters"})


def test_reference_chains_cannot_evade_schema_depth_bounds(bundle_root):
    definitions = {f"s{i}": {"$ref": f"#/$defs/s{i + 1}"} for i in range(40)}
    definitions["s40"] = {"type": "string"}
    edit_json(bundle_root, "input.schema.json", lambda s: s.update(
        properties={"question": {"$ref": "#/$defs/s0"}, "evidence": {"type": "string"}},
        **{"$defs": definitions}))
    with pytest.raises(CatalogError) as error:
        AgentCatalog(bundle_root).load("baseline.writer", 1)
    assert error.value.code == "INVALID_SCHEMA"


def test_schema_error_tracebacks_do_not_echo_resource_values(bundle_root):
    edit_json(bundle_root, "input.schema.json", lambda s: s["properties"]["question"].update(
        minLength="resource-private-marker"))
    with pytest.raises(CatalogError) as error:
        AgentCatalog(bundle_root).load("baseline.writer", 1)
    assert "resource-private-marker" not in "".join(traceback.format_exception(error.value))


def test_literal_ref_properties_in_schema_data_are_never_resolved(bundle_root):
    edit_json(bundle_root, "input.schema.json", lambda s: s.update(examples=[
        {"question": "Q", "evidence": {"$ref": "https://untrusted.invalid/not-a-schema"}}]))
    assert AgentCatalog(bundle_root).load("baseline.writer", 1).render_task({"question": "Q", "evidence": "E"})


def test_rendered_task_has_a_byte_bound_in_addition_to_schema_character_bounds(bundle_root):
    edit_json(bundle_root, "definition.json", lambda d: d["limits"].update(max_task_input_bytes=512))
    spec = AgentCatalog(bundle_root).load("baseline.writer", 1)
    with pytest.raises(CatalogError):
        spec.render_task({"question": "Q", "evidence": "é" * 240})
