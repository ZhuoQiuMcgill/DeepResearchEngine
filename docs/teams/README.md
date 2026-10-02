# Team documentation index

The platform is implemented and available for teammate integration.
**Start with [Team start](../team-start.md)** for setup, role-specific paths,
runnable commands and interface ownership.

The current platform package and CLI are `deepresearch`; source blocks live
under `src/deepresearch/`. EBD is a research method, not the platform namespace.
The [structure and migration map](../architecture/project-structure.md) explains
the one-file `ebd` compatibility bridge. Historical designs and acceptance
records below retain their original paths and commands.

## Current handoff documents

| Purpose | Document |
| --- | --- |
| New teammate onboarding | [Team start](../team-start.md) |
| Python orchestrator integration | [Connections](../usage/connections.md), [Agents](../usage/agents.md), [Storage](../usage/storage.md), [Tools](../usage/tools.md) |
| Frontend integration | [HTTP walkthrough](../usage/console-quickstart.md), [service reference](../usage/service.md), [OpenAPI JSON](../api/openapi.json) |
| Shared consumer boundary | [Consumer contract v1](consumer-contract-v1.md) |
| Platform invariants | [Platform contract v1](platform-contract-v1.md) |
| Actual verification | [Platform acceptance](../platform-acceptance.md), [consumer acceptance](../consumer-acceptance.md) |
| Source ownership and Git | [AGENTS](../../AGENTS.md), [CONTRIBUTING](../../CONTRIBUTING.md) |

Development coordination is in the current root chat and its in-chat subagents.
The former cross-session module chats are closed assignments; do not contact
or redispatch them based on the historical documents below.

## Historical design records

These documents retain earlier requirements, design rationale and review
history. Their original phase holds, proposed interfaces, ownership and chat
instructions describe the earlier design stage. Current public source/DTOs,
usage guides and root instructions take precedence.

| Module | Original brief | Reviewed design | Historical status |
| --- | --- | --- | --- |
| Agent Container | [Brief](agent-container.md) | [Design](designs/agent-container-design.md) | [Report](reports/agent-container-status.md) |
| CLI Toolset | [Brief](cli-toolset.md) | [Design](designs/cli-toolset-design.md) | [Report](reports/cli-toolset-status.md) |
| Storage | [Brief](storage.md) | [Design](designs/storage-design.md) | [Report](reports/storage-status.md) |
| Connections | [Brief](connections.md) | [Design](designs/connections-design.md) | [Report](reports/connections-status.md) |

Historical context: [shared brief](shared-platform.md), [missions](missions.md),
[coordination history](coordination.md), [reconciliation](reconciliation.md),
[decision log](decisions.md), [search research](../research/free-search-fetch.md).
The [baseline criteria](baseline-acceptance.md) remain the acceptance requirements;
their actual results are in the current acceptance documents above.

Research background is in `docs/proposal/INSE691_Proposal_EBD-DeepResearch_Group7.docx`
and `docs/proposal/EBD-DeepResearch_Design_v0.1.docx`. Later user decisions
established CLI tools, uv/Python 3.11+, and a reusable execution platform as
the foundation for independently developed strategies.
