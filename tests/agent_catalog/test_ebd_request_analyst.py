"""ebd.request_analyst@1: the EBD request-analysis role bundle in the shared catalog."""

import json

import pytest

from deepresearch.agent_catalog import AgentCatalog, CatalogError


ROLE = ("ebd.request_analyst", 1)
QUESTION = "What is EBD (Environment Based Design)?"


def role():
    return AgentCatalog().load(*ROLE)


def worked_example_replies(task):
    """The JSON replies the task message shows as worked examples."""
    examples = task.split("# Request to analyse", 1)[0]
    return [json.loads(block.split("\n\n## Example", 1)[0])
            for block in examples.split("### Reply\n")[1:]]


def test_role_is_tool_free_and_compiles_for_both_api_profiles():
    spec = role()
    assert spec.tool_requests == ()
    for profile, model in (("deepseek", "deepseek-flash"), ("openai", "gpt-6-luna")):
        definition = spec.compile_definition(profile_ref=profile, model_ref=model)
        assert definition.allowed_tools == []
        assert definition.output_mode == "json"
        assert definition.limits["max_model_calls"] == 1


def test_task_renders_the_exact_question_after_the_worked_examples():
    rendered = role().render_task({"question": QUESTION, "run_date": "2026-10-04", "retry_feedback": ""})
    examples, request = rendered.split("# Request to analyse", 1)
    assert "## Example E1" in examples
    assert f"<run_date>2026-10-04</run_date>\n<client_request>\n{QUESTION}\n</client_request>" in request
    assert rendered.rstrip().endswith("no code fence, and no text before or after the object.")


@pytest.mark.parametrize("value", [
    {"question": "", "run_date": "2026-10-04", "retry_feedback": ""},
    {"question": QUESTION, "run_date": "October 4, 2026", "retry_feedback": ""},
    {"question": QUESTION, "run_date": "2026-10-04"},
    {"question": QUESTION, "run_date": "2026-10-04", "retry_feedback": "", "topic": "EBD"},
])
def test_task_input_is_closed_and_bounded(value):
    with pytest.raises(CatalogError) as error:
        role().render_task(value)
    assert error.value.code == "INVALID_INPUT"


def test_worked_examples_are_valid_outputs_of_the_role():
    spec = role()
    replies = worked_example_replies(spec.task_template)
    assert [reply["status"] for reply in replies] == ["ok", "ok", "needs_clarification", "out_of_scope"]
    for reply in replies:
        spec.validate_output(reply)
    stale = dict(replies[-1], schema_version="request-analysis/1.0")
    with pytest.raises(CatalogError):
        spec.validate_output(stale)


def test_every_output_object_is_closed_with_all_fields_required():
    schema = role().output_schema

    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for child in node.values():
                check(child)
        elif isinstance(node, list):
            for child in node:
                check(child)

    check(schema)
