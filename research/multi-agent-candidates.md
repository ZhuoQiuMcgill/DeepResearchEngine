# Multi-agent deep research candidates

Filtered from `open-source-deep-research-workflows.md` (2026-09-09) for the goal of building a multi-agent deep research system. Excluded: RL-trained open-weight models, single-agent iterative loops, answer engines, autonomous-science pipelines, training frameworks, benchmarks.

## Tier 1: profiled in depth, study first

| # | Project | Why it matters for a multi-agent system | Status |
|---|---|---|---|
| 1 | Open Deep Research (LangChain) | Canonical supervisor + parallel researcher subgraphs; per-researcher compression; concurrency cap that returns a retry-with-fewer-units error to the supervisor. | Archived 2026-08-21, complete and readable |
| 2 | deepagents (LangChain) | The live successor harness: subagent delegation middleware, filesystem offload, summarization/compaction, permissions. The research pipeline is one example's prompts. | Active, pre-1.0, breaking changes |
| 3 | GPT Researcher | Plan-once then flat asyncio fan-out over sub-queries with embedding compression; separate LangGraph editorial team in `multi_agents/` (planner, researcher, writer, reviewer, reviser, publisher, human node); committed eval logs; 27 LLM providers, 21 retrievers. | Active, v3.6.x |
| 4 | Local Deep Research | Default LangGraph lead agent + parallel researcher subagents, pluggable alternative strategies, 30+ academic sources, local-first. | Active |
| 5 | STORM / Co-STORM | Parallel persona-conditioned researcher dialogues; Co-STORM turn-policy discourse manager over a shared mind map; outline-driven writing with citations. | Dormant since 2025-09 |
| 6 | smolagents open_deep_research | Two-level manager CodeAgent + browser ToolCallingAgent, re-plan every 4 steps, remaining-steps budget. Skeleton only, no citation layer. | Frozen |
| 7 | Gemini Fullstack LangGraph Quickstart | Smallest complete fan-out (Send) + reflection-gated loop; best live activity timeline UI. | Frozen since 2025-06 |

## Tier 2: multi-agent, appendix only (one-line evidence, not yet profiled)

Direct deep-research systems
- MindSearch (InternLM) - https://github.com/InternLM/MindSearch - WebPlanner builds a DAG of sub-questions, WebSearcher agents execute in parallel; ~6.9k stars; largely dormant.
- Enterprise Deep Research (Salesforce) - https://github.com/SalesforceAIResearch/enterprise-deep-research - LangGraph master planner + specialized search agents, HITL steering.
- DeepResearchAgent (Skywork) - https://github.com/SkyworkAI/DeepResearchAgent - hierarchical planner over deep-researcher / analyzer / browser sub-agents.
- agents-deep-research (QX Labs) - https://github.com/qx-labs/agents-deep-research - OpenAI Agents SDK implementation of the supervisor pattern.
- Together Open Deep Research - https://github.com/togethercomputer/open_deep_research - planner, parallel searchers, writer; vendor reference.
- MiroFlow (MiroMind) - https://github.com/MiroMindAI/MiroFlow - orchestration harness (main agent + sub-agents) behind the MiroThinker results.
- CognitiveKernel-Pro (Tencent) - https://github.com/Tencent/CognitiveKernel-Pro - multi-module planner/web/file agent.
- Marco-DeepResearch (Alibaba International) - https://github.com/AIDC-AI/Marco-DeepResearch - low adoption.
- Yunque DeepResearch Agent (Tencent BAC) - https://github.com/Tencent-BAC/YunqueAgent - low adoption.
- FlowSearch - https://github.com/Alpha-Innovator/FlowSearch - knowledge-flow multi-agent design.
- PanelWise (inclusionAI) - https://github.com/inclusionAI/PanelWise - parallel multi-model panel fusion.
- HiRA (RUC-NLPIR) - https://github.com/RUC-NLPIR/HiRA - planner/executor decoupling method.

Vendor pattern references
- Anthropic claude-cookbooks multi-agent research pattern - https://github.com/anthropics/claude-cookbooks - orchestrator-worker prompts behind the closed Research feature.
- OpenAI Agents SDK research_bot - https://github.com/openai/openai-agents-python - planner, parallel search agents, writer in a few hundred lines.
- Magentic-One (Microsoft AutoGen) - https://github.com/microsoft/autogen - orchestrator with task ledger and progress ledger over specialized agents; general-purpose.
- Google ADK deep-search sample - https://github.com/google/adk-samples
- NVIDIA AI-Q Research Assistant - https://github.com/NVIDIA-AI-Blueprints/aiq - enterprise blueprint built on deepagents.
- Azure-Samples deepresearch - https://github.com/Azure-Samples/deepresearch

Hierarchical / recursive meta-agent frameworks with a deep research application
- ROMA (Sentient) - https://github.com/sentient-agi/ROMA - recursive planner/executor/aggregator tree.
- OWL (CAMEL-AI) - https://github.com/camel-ai/owl
- AgentScope - https://github.com/agentscope-ai/agentscope - official DeepResearch example.
- MS-Agent (ModelScope) - https://github.com/modelscope/ms-agent
- AutoAgent (HKUDS) - https://github.com/HKUDS/AutoAgent - parent of Auto-Deep-Research.
- JoyAgent-JDGenie - https://github.com/jd-opensource/joyagent-jdgenie
- OpenManus - https://github.com/FoundationAgents/OpenManus
- Youtu-Agent (Tencent) - https://github.com/TencentCloudADP/youtu-agent

Human-in-the-loop multi-agent canvases
- Open Research ANA (CopilotKit) - https://github.com/CopilotKit/open-research-ANA
- ResearStudio - https://github.com/ResearAI/ResearStudio

Teaching companions
- deep_research_from_scratch (LangChain) - https://github.com/langchain-ai/deep_research_from_scratch
- deep-agents-from-scratch (LangChain) - https://github.com/langchain-ai/deep-agents-from-scratch

## Excluded, but one feature worth borrowing

- DeerFlow: citation verification against a tool-receipt ledger; `batch_task` bounded parallel delegation; ordered middleware chain.
- Dexter: read-only, non-recursive parallel subagents as a safety boundary.
- Khoj: mid-run interrupt queue for user steering.
- deep-research (dzhng): breadth-halving recursion as a depth/breadth budget heuristic.

## Excluded categories

RL-trained open-weight models (Tongyi DeepResearch, MiroThinker, DR Tulu, WebThinker and ~30 training repos), single-agent loops (DeerFlow, Khoj, PaperQA2, Dexter, node-DeepResearch, dzhng and its ports/UI wrappers), answer engines (Perplexica, Scira, Morphic, Farfalle), autonomous-science pipelines (AI Scientist, Agent Laboratory, RD-Agent), survey writers (AutoSurvey, SurveyX, OmniThink), benchmarks.
