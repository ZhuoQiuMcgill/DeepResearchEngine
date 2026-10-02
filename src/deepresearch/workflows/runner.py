"""Execute registered methods through the same node lifecycle."""
from __future__ import annotations


class WorkflowRunner:
    async def run(self, definition, method, context, task_input, parameters):
        async with context.node("method", "method", {"method_id": definition.method_id, "revision": definition.revision}):
            return await method.run(context, task_input, parameters)
