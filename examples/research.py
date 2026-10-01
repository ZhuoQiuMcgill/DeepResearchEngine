"""A runnable consumer of the public platform, with strategy in its prompt."""
import asyncio
from ebd.connections import Engine, RunOptions
from ebd.contracts import AgentDefinition, ToolRef


async def main():
    engine = (await Engine.open()).unwrap()
    async with engine:
        agent = engine.register_agent(AgentDefinition(
            "research-example",
            "Use registered discovery tools, fetch accessible sources, and read saved snapshots before citing. Answer concisely with sources. Internal/provider search is forbidden.",
            allowed_tools=[ToolRef(n) for n in ("web.search", "scholar.crossref.search", "web.fetch", "document.read")],
            limits={"max_run_seconds": 240, "max_model_calls": 12, "max_tool_calls": 20},
        )).unwrap()
        result = await engine.run_agent(agent.ref, "What is Environment Based Design?", RunOptions(timeout_seconds=240))
        print(result.status)
        if result.output:
            print(result.output)
        elif result.error:
            print(result.error.code, result.error.message)


if __name__ == "__main__":
    asyncio.run(main())
