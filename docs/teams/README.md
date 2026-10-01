# Module team specs

These briefs prepare independent team chats for the basic engine. Current
work is design and research; implementation has not been authorized.

The platform comes first so group members can build research strategies
against working, decoupled interfaces. The orchestrator and EBD strategies
are later consumers of this platform.

| Team | Spec | Current assignment |
| --- | --- | --- |
| Agent Container | [agent-container.md](agent-container.md) | Propose agent definition, execution interfaces, and real provider adapter design. |
| CLI Toolset | [cli-toolset.md](cli-toolset.md) | Research free, open-source search/fetch combinations and propose tool contracts. |
| Storage | [storage.md](storage.md) | Propose persistence, scoped access, artifacts, and automatic recording contracts. |
| Connections | [connections.md](connections.md) | Propose bindings, context propagation, configuration, and agent invocation contracts. |

All leaders first read [shared-platform.md](shared-platform.md) and
[coordination.md](coordination.md). Agent Container and CLI Toolset are the
first implementation priorities after design approval. Storage and
Connections can resolve their design boundaries in parallel now.

Suggested starting prompts, from sessions opened in this workspace:

```text
You are the leader of Agent Container team, now read your spec.
You are the leader of CLI Toolset team, now read your spec.
You are the leader of Storage team, now read your spec.
You are the leader of Connections team, now read your spec.
```

Each leader registers with PM, completes the current assignment, saves an
owned report, and notifies PM. PM reconciles interface proposals and selects
the web tool combination after the CLI research arrives. No search or fetch
backend is selected by this brief.

Background sources:

- Final proposal: `docs/proposal/INSE691_Proposal_EBD-DeepResearch_Group7.docx`.
- Earlier internal design: `docs/proposal/EBD-DeepResearch_Design_v0.1.docx`.

Use the final proposal for research goals. Later user decisions recorded in
these specs take precedence: CLI tools replace MCP, the environment is uv
and Python 3.11+, and the basic execution platform precedes orchestration.
