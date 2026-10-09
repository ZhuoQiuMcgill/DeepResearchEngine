"""Instruction revisions keep executable contracts and authority unchanged."""
import json
from importlib import resources
import re
from string import Template

import pytest

from deepresearch.agent_catalog import AgentCatalog
from deepresearch.bootstrap import create_method_registry


REVISIONS = [("planner", 3, 4), ("selector", 1, 2), ("distiller", 1, 2),
             ("analyst", 3, 4), ("writer", 5, 6), ("reviewer", 4, 5)]
REFINEMENTS = [("selector", 2, 3), ("distiller", 2, 3), ("analyst", 4, 5)]


@pytest.mark.parametrize("role,old_revision,new_revision", REVISIONS + REFINEMENTS)
def test_instruction_revision_retains_schemas_limits_and_all_task_fields(role, old_revision, new_revision):
    catalog = AgentCatalog()
    old = catalog.load("baseline." + role, old_revision)
    new = catalog.load("baseline." + role, new_revision)
    root = resources.files("deepresearch.agent_catalog").joinpath("resources", "baseline." + role)
    for name in ("input.schema.json", "output.schema.json"):
        assert root.joinpath(str(old_revision), name).read_bytes() == root.joinpath(str(new_revision), name).read_bytes()
    definitions = [json.loads(root.joinpath(str(revision), "definition.json").read_text())
                   for revision in (old_revision, new_revision)]
    for definition in definitions:
        definition.pop("revision")
        definition.pop("description", None)
    assert definitions[0] == definitions[1]
    assert new.instructions != old.instructions
    assert new.task_template != old.task_template
    assert set(Template(new.task_template).get_identifiers()) == set(new.input_schema["required"])
    compiled = new.compile_definition(profile_ref="controlled", model_ref="deepseek-flash")
    assert compiled.limits["max_context_tokens"] == 262144
    assert compiled.limits["max_model_calls"] == 1
    assert compiled.allowed_tools == []
    assert compiled.output_mode == ("text" if role == "writer" else "json")


@pytest.mark.parametrize("role,old_revision,new_revision", [row for row in REVISIONS + REFINEMENTS if row[0] != "writer"])
def test_prompt_output_examples_are_instances_accepted_by_the_real_contract(role, old_revision, new_revision):
    spec = AgentCatalog().load("baseline." + role, new_revision)
    examples = re.findall(r"```json\s*\n(.*?)\n```", spec.instructions, re.S)
    assert examples, "JSON roles require at least one concrete output instance"
    for example in examples:
        value = json.loads(example)
        spec.validate_output(value)
        assert not {"$defs", "properties", "required", "type"} & value.keys()


def test_baseline_eight_changes_role_pins_only():
    registry = create_method_registry()
    old, old_method = registry.resolve("baseline", 7)
    new, new_method = registry.resolve("baseline", 8)
    assert type(new_method) is type(old_method)
    assert new_method.agent_selection is old_method.agent_selection is True
    assert new.input_schema == old.input_schema
    assert new.parameters_schema == old.parameters_schema
    assert new.tool_revisions == old.tool_revisions
    assert old.agent_roles == tuple(("baseline." + role, old_revision) for role, old_revision, _ in REVISIONS)
    assert new.agent_roles == tuple(("baseline." + role, new_revision) for role, _, new_revision in REVISIONS)


def test_baseline_nine_preserves_eight_and_refines_three_instruction_pins():
    registry = create_method_registry()
    old, old_method = registry.resolve("baseline", 8)
    new, new_method = registry.resolve("baseline", 9)
    assert type(new_method) is type(old_method)
    assert new.input_schema == old.input_schema
    assert new.parameters_schema == old.parameters_schema
    assert new.tool_revisions == old.tool_revisions
    expected = dict(old.agent_roles)
    expected.update({"baseline." + role: revision for role, _, revision in REFINEMENTS})
    assert dict(new.agent_roles) == expected
