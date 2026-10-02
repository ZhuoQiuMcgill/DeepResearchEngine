"""Small real method for integration without a model or network dependency."""
from importlib.resources import files
from ebd.engine.contracts import canonical_json, digest_bytes
from ebd.workflows import MethodDefinition


def definition():
    return MethodDefinition("example.echo", 1, "Integration example: publish input through a real recorded Workflow.",
        {"type": "object", "additionalProperties": False, "properties": {
            "message": {"type": "string", "minLength": 1, "maxLength": 4096}}, "required": ["message"]},
        {"type": "object", "additionalProperties": False, "properties": {}},
        resource_digests={"__init__.py": digest_bytes(files(__package__).joinpath("__init__.py").read_bytes())})


class EchoMethod:
    async def run(self, context, task_input, parameters):
        async with context.node("publish.echo", "publication"):
            report = await context.port.publish((task_input["message"] + "\n").encode("utf-8"), "text/markdown", "echo.md")
        result = {"schema_version": 1, "method_id": "example.echo", "method_revision": 1, "report_ref": report}
        manifest = await context.port.publish(canonical_json(result), "application/json", "research-result.json")
        await context.port.update(report_ref=report, result_manifest_ref=manifest)
        await context.checkpoint({"kind": "echo-result/1", "report_ref": report, "result_manifest_ref": manifest})
        return result
