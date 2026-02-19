# BioTeam-AI: Curated Resource Guide

*Compiled: 2026-02-16 | Focus: Current, actionable resources for building a multi-agent biology research system*

---

## 1. Anthropic Client SDK Patterns

### 1.1 "Building Effective Agents" (Anthropic Research Blog)
- **URL**: https://www.anthropic.com/research/building-effective-agents
- **What it provides**: Anthropic's canonical guide to agent architecture patterns: prompt chaining, routing, parallelization, orchestrator-workers, and evaluator-optimizer. Establishes the principle that the most successful implementations use simple, composable patterns rather than complex frameworks.
- **BioTeam-AI relevance**: Directly maps to BioTeam-AI's orchestrator architecture. The orchestrator-workers pattern (central LLM breaks tasks into subtasks, delegates to workers, synthesizes results) is the exact pattern needed for a research lead agent coordinating 15+ specialists.
- **Priority**: **MUST USE**

### 1.2 "How We Built Our Multi-Agent Research System" (Anthropic Engineering)
- **URL**: https://www.anthropic.com/engineering/multi-agent-research-system
- **What it provides**: Detailed engineering walkthrough of Anthropic's own multi-agent research system. Covers orchestrator-worker architecture with a lead agent coordinating subagents in parallel. Documents real failure modes (agents spawning 50 subagents for simple queries, duplicating work, endless web scouring). Shows that a system using Opus as the lead agent and Sonnet as subagents outperformed single-agent by 90%+.
- **BioTeam-AI relevance**: This is the closest existing system to what BioTeam-AI is building. The architecture (lead agent + specialized subagents), the failure modes documented, and the prompt engineering solutions are directly transferable. The CitationAgent pattern maps to BioTeam-AI's evidence synthesis needs.
- **Priority**: **MUST USE**

### 1.3 Claude Agent SDK (Python)
- **URL**: https://github.com/anthropics/claude-agent-sdk-python
- **Docs**: https://platform.claude.com/docs/en/agent-sdk/overview
- **What it provides**: Official Python SDK giving the same tools, agent loop, and context management that power Claude Code. Supports subagents with isolated context windows, concurrent subagent writes with write locks, MCP tool annotations, and extended thinking configuration (low/medium/high/max).
- **BioTeam-AI relevance**: Could serve as the foundation layer for agent orchestration instead of building from scratch. Subagent isolation and concurrent execution are directly needed for parallel literature searches, hypothesis generation, and review workflows.
- **Priority**: **SHOULD CONSIDER** (evaluate vs. building custom orchestration with the base Anthropic SDK)

### 1.4 Claude Agent SDK Demos
- **URL**: https://github.com/anthropics/claude-agent-sdk-demos
- **What it provides**: Working demo code including a multi-agent research system that coordinates specialized subagents to research topics and generate comprehensive reports.
- **BioTeam-AI relevance**: Provides starter code and patterns that can be adapted for BioTeam-AI's research workflow agents.
- **Priority**: **SHOULD CONSIDER**

### 1.5 Anthropic Cookbook (Agent Patterns)
- **URL**: https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents
- **URL (legacy)**: https://github.com/anthropics/claude-cookbooks
- **What it provides**: Jupyter notebooks with practical examples: tool use integration, memory management, context editing strategies (tool use clearing when context grows large, thinking block management), using Haiku as a sub-agent with Opus, and a research_lead_agent prompt template.
- **BioTeam-AI relevance**: The research_lead_agent.md prompt is a direct template for BioTeam-AI's orchestrator agent. Context management patterns are critical for long-running research sessions that can easily exceed context limits.
- **Priority**: **MUST USE**

### 1.6 Anthropic Prompt Caching
- **URL**: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- **What it provides**: Up to 90% cost reduction and 85% latency reduction for repeated prompts. Supports 5-minute (default) and 1-hour cache durations. Cache read tokens cost 0.1x the base input token price. Maximum 4 cache points per request.
- **BioTeam-AI relevance**: Critical for cost management. BioTeam-AI sends the same system prompts to 15+ agents repeatedly. Caching system prompts, tool definitions, and shared context (like a research brief) across agent calls will dramatically reduce costs. With Sonnet at $3/M input tokens, caching reduces repeated context to $0.30/M.
- **Priority**: **MUST USE**

### 1.7 Advanced Tool Use (Anthropic Engineering)
- **URL**: https://www.anthropic.com/engineering/advanced-tool-use
- **What it provides**: Three new capabilities: Tool Search Tool (access thousands of tools without consuming context), Programmatic Tool Calling (invoke tools in code execution environment), and Tool Use Examples (demonstrate correct tool invocation). Addresses context bloat from tool definitions.
- **BioTeam-AI relevance**: With 15+ agents each having specialized tools, context bloat from tool definitions is a real risk. Tool Search Tool allows agents to dynamically discover relevant tools without loading all definitions upfront.
- **Priority**: **SHOULD CONSIDER**

### 1.8 Effective Harnesses for Long-Running Agents (Anthropic Engineering)
- **URL**: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- **What it provides**: Patterns for managing agents that run for extended periods. Covers context management, progress tracking (claude-progress.txt pattern), and incremental session handoffs.
- **BioTeam-AI relevance**: Research workflows can run for hours. The progress file pattern and session handoff strategy are directly applicable to multi-step hypothesis generation and literature review workflows.
- **Priority**: **SHOULD CONSIDER**

---

## 2. Multi-Agent Orchestration Frameworks

### 2.1 LangGraph
- **URL**: https://www.langchain.com/langgraph
- **Docs**: https://python.langchain.com/docs/langgraph
- **What it provides**: Python framework for multi-agent workflows using directed graph architectures. Nodes represent agents/functions/decision points; edges dictate data flow. Centralized StateGraph maintains context. Features: time-travel debugging, human-in-the-loop interrupts, fault tolerance, conditional branching, parallel execution. Fastest framework with lowest latency across benchmarks.
- **BioTeam-AI relevance**: Strong candidate for orchestrating the research workflow graph (e.g., Literature Search -> Evidence Synthesis -> Hypothesis Generation -> Peer Review -> Revision). The StateGraph can maintain research session state. Human-in-the-loop interrupts map to researcher approval checkpoints.
- **Priority**: **SHOULD CONSIDER** (evaluate complexity vs. building custom orchestration)

### 2.2 CrewAI
- **URL**: https://www.crewai.com/open-source
- **GitHub**: https://github.com/crewAIInc/crewAI
- **What it provides**: Framework for orchestrating role-playing, autonomous AI agents. Role-based architecture with Manager, Worker, and Researcher agent types. Assigns distinct roles to individual agents, creating specialized teams that mimic real-world organizations. 100K+ developers.
- **BioTeam-AI relevance**: The role-based metaphor (Manager/Worker/Researcher) maps naturally to BioTeam-AI's scientist/reviewer/synthesizer agent roles. However, it may impose too much abstraction for a system that needs fine-grained control over biology-specific prompts and tool integration.
- **Priority**: **NICE TO HAVE** (study for patterns, but likely too opinionated for BioTeam-AI's needs)

### 2.3 Microsoft Agent Framework (formerly AutoGen)
- **URL**: https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview
- **GitHub**: https://github.com/microsoft/autogen
- **What it provides**: Merges AutoGen's multi-agent orchestration with Semantic Kernel's production foundations. Released October 2025 in public preview. Asynchronous, event-driven architecture. Cross-language agent interop (Python, .NET). Note: AutoGen itself is in maintenance mode; new features go to the Agent Framework.
- **BioTeam-AI relevance**: The event-driven architecture and cross-language support could be useful if BioTeam-AI needs to integrate non-Python components. However, it's Microsoft-ecosystem focused and may not integrate as cleanly with Anthropic's Claude.
- **Priority**: **NICE TO HAVE** (study architecture patterns only)

### 2.4 Google DeepMind AI Co-Scientist (Generate-Debate-Evolve)
- **URL**: https://arxiv.org/abs/2502.18864
- **Blog**: https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/
- **What it provides**: Multi-agent system using generate-debate-evolve paradigm for hypothesis generation. Coalition of specialized agents that iteratively generate, evaluate, and refine hypotheses. Uses self-play scientific debate, ranking tournaments, and evolution processes. Validated in drug repurposing for AML and liver fibrosis research. Built on Gemini 2.0.
- **BioTeam-AI relevance**: This is the most directly relevant prior art for BioTeam-AI's hypothesis workflow. The generate-debate-evolve architecture should be studied and adapted. The ranking tournament approach for hypothesis comparison and the self-play debate for novelty checking are implementable patterns.
- **Priority**: **MUST USE** (as an architectural reference for the hypothesis generation pipeline)

### 2.5 Pydantic AI
- **URL**: https://ai.pydantic.dev/
- **GitHub**: https://github.com/pydantic/pydantic-ai
- **What it provides**: Agent framework built on Pydantic. Model-agnostic (supports Anthropic). Features: structured output via Pydantic models, MCP integration, Agent2Agent protocol, human-in-the-loop tool approval, built-in CodeExecutionTool for computational tasks. Integrates with prompt caching for Anthropic models.
- **BioTeam-AI relevance**: Strong candidate for building individual agents that need structured, validated outputs (e.g., evidence grading agents returning typed `EvidenceScore` objects, hypothesis agents returning `Hypothesis` Pydantic models). The model-agnostic design means you're not locked into one provider.
- **Priority**: **SHOULD CONSIDER** (especially for structured output enforcement on individual agents)

---

## 3. Agent Prompting Best Practices & Guardrails

### 3.1 Instructor Library (Structured Output)
- **URL**: https://python.useinstructor.com/
- **Anthropic Integration**: https://python.useinstructor.com/integrations/anthropic/
- **GitHub**: https://github.com/567-labs/instructor
- **What it provides**: Python library for extracting structured, validated data from LLMs using Pydantic models. Automatic validation, retries, and error handling. Supports prompt caching with Anthropic. Works with streaming responses. Each yielded item is validated against its Pydantic model.
- **BioTeam-AI relevance**: Ideal for enforcing structured outputs from all agents. Every agent in BioTeam-AI should return typed Pydantic objects (HypothesisResult, EvidenceGrade, LiteratureReview, etc.) rather than free-text. Instructor handles validation and automatic retries when output doesn't match schema.
- **Priority**: **MUST USE**

### 3.2 Claude Native Structured Outputs
- **URL**: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- **What it provides**: As of November 2025, Anthropic offers native structured outputs in public beta. Guarantees JSON schema compliance directly from the API, eliminating parsing errors and retry logic. Supports Pydantic/Zod schema definitions.
- **BioTeam-AI relevance**: Reduces dependency on Instructor for simple structured outputs. For agents that return well-defined JSON schemas, this native feature may be simpler and more reliable. Evaluate against Instructor for each agent's needs.
- **Priority**: **MUST USE**

### 3.3 Guardrails AI
- **URL**: https://github.com/guardrails-ai/guardrails
- **Website**: https://www.guardrailsai.com/
- **What it provides**: Python framework for adding structural, type, and quality guarantees to LLM outputs. Uses RAIL spec or Pydantic schemas. Automatic corrective prompts when output fails validation. Iterative retry loop. Complementary to NeMo Guardrails.
- **BioTeam-AI relevance**: Adds a validation layer on top of agent outputs. For biology research, this can enforce that cited papers are real (format validation), that evidence grades use valid GRADE categories, that statistical claims include proper qualifiers, and that outputs don't contain hallucinated references.
- **Priority**: **SHOULD CONSIDER**

### 3.4 NVIDIA NeMo Guardrails
- **URL**: https://github.com/NVIDIA-NeMo/Guardrails
- **What it provides**: Open-source toolkit for adding programmable guardrails to LLM-based systems. Five guardrail types: input rails, dialog rails, retrieval rails, execution rails, and output rails. Uses Colang (a modeling language) for defining conversational guardrails.
- **BioTeam-AI relevance**: The input/output rails pattern is useful for preventing agents from making unsupported scientific claims, enforcing citation requirements, and adding safety checks for medical/biological content. Dialog rails can prevent agents from going off-topic during research tasks.
- **Priority**: **NICE TO HAVE** (Guardrails AI may be sufficient; NeMo adds complexity)

### 3.5 Anthropic Cookbook: Research Lead Agent Prompt
- **URL**: https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/agents/prompts/research_lead_agent.md
- **What it provides**: A complete, production-tested system prompt for a research lead agent that coordinates sub-agents. Directly from Anthropic's own examples.
- **BioTeam-AI relevance**: Starting template for BioTeam-AI's orchestrator agent prompt. Adapt for biology-specific research coordination, adding domain-specific instructions for literature search strategy, evidence hierarchy awareness, and hypothesis evaluation criteria.
- **Priority**: **MUST USE**

### 3.6 Learn Prompting / PromptHub (Prompt Libraries)
- **URL**: https://learnprompting.org/docs/basics/roles
- **URL**: https://www.prompthub.us/blog/prompt-engineering-for-ai-agents
- **What it provides**: Prompt engineering patterns for role-playing agents, including scientist, reviewer, and critic personas. Covers self-criticism techniques, decomposition prompts, and agent-specific prompt patterns.
- **BioTeam-AI relevance**: Reference for designing the 15+ agent personas. The self-criticism pattern maps to the peer review agent; the decomposition pattern maps to the research planning agent. Role prompting best practices ensure each agent stays in character.
- **Priority**: **NICE TO HAVE**

---

## 4. Biology AI Tools and APIs

### 4.1 NCBI E-Utilities / PubMed API
- **URL**: https://www.ncbi.nlm.nih.gov/books/NBK25497/
- **Quick Start**: https://www.ncbi.nlm.nih.gov/books/NBK25500/
- **What it provides**: Public API to all NCBI Entrez databases (PubMed, PMC, Gene, Protein, etc.). Eight server-side programs: ESearch, EFetch, EInfo, ELink, EPost, ESpell, EGQuery, ECitMatch. Rate limit: 3 req/sec without API key, 10 req/sec with key. Batch operations via Entrez History for large-scale retrieval.
- **BioTeam-AI relevance**: Core data source for the Literature Search Agent. Every research query will hit PubMed. Must implement: API key registration, batch retrieval via EPost/EFetch, MEDLINE format parsing, and MeSH term-aware querying.
- **Priority**: **MUST USE**

### 4.2 Biopython (Bio.Entrez)
- **URL**: https://biopython.org/docs/latest/Tutorial/chapter_entrez.html
- **What it provides**: Python wrapper for NCBI E-Utilities. Automatic rate limiting (max 1 request per 3 seconds). XML parsing of Entrez responses. MEDLINE format parser (Bio.Medline). Handles authentication, session cookies, and batch downloads.
- **BioTeam-AI relevance**: The Python interface layer for PubMed access. Handles rate limiting automatically, parses XML responses, and provides Bio.Medline for structured paper metadata extraction. Saves significant development time vs. raw HTTP calls.
- **Priority**: **MUST USE**

### 4.3 Semantic Scholar API
- **URL**: https://www.semanticscholar.org/product/api
- **Python Client**: https://pypi.org/project/semanticscholar/
- **API Docs**: https://api.semanticscholar.org/api-docs/
- **What it provides**: REST API for academic papers, authors, citations, venues. Includes SPECTER2 embeddings for semantic search. Recommendations API for finding similar papers. 1000 req/sec shared among unauthenticated users. Python client library with typed responses.
- **BioTeam-AI relevance**: Complements PubMed with citation graph analysis, semantic similarity search (finding related papers by meaning, not just keywords), and paper recommendations. The SPECTER2 embeddings could power a "find papers similar to this hypothesis" feature.
- **Priority**: **MUST USE**

### 4.4 OpenAlex API
- **URL**: https://docs.openalex.org/
- **Website**: https://openalex.org/
- **What it provides**: Fully open index of 260M+ scholarly works, authors, venues, institutions, and concepts. Free under CC0 license. No authentication required. 100K credits/day with free API key. Semantic search. REST API. Replaces the deprecated Microsoft Academic Graph.
- **BioTeam-AI relevance**: Free, open alternative/complement to Semantic Scholar for large-scale bibliometric analysis. Useful for: mapping research landscapes, identifying research trends, finding institutional expertise, and citation network analysis. The CC0 license means no legal concerns about data use.
- **Priority**: **SHOULD CONSIDER**

### 4.5 bioRxiv / medRxiv API
- **URL**: https://api.biorxiv.org/
- **Help**: https://api.biorxiv.org/pubs/help
- **What it provides**: REST API for bioRxiv and medRxiv preprints. JSON and XML formats. Paginated results (100 per call). Query by date range, recent count, or recent days. Covers preprint metadata, DOIs, and publication status.
- **BioTeam-AI relevance**: Critical for finding cutting-edge research not yet in PubMed. The Preprint Monitor Agent should poll this daily for new preprints in tracked topics. The API's simplicity (date-based queries, pagination) makes it easy to build an automated preprint scanner.
- **Priority**: **MUST USE**

### 4.6 UniProt REST API
- **URL**: https://www.uniprot.org/help/programmatic_access
- **API Docs**: https://www.uniprot.org/api-documentation
- **What it provides**: Free, open-access REST API for protein sequence and functional data. Covers UniProtKB, UniRef, UniParc, Proteomes. ID Mapping service for cross-referencing biological databases. Structured queries with logical operators. 303M requests/month in active use. No authentication required.
- **BioTeam-AI relevance**: Essential for protein-focused research queries. The ID Mapping service allows agents to cross-reference between gene names, protein IDs, and pathway databases. Useful for the Molecular Biology Agent and Drug Target Analysis Agent.
- **Priority**: **SHOULD CONSIDER** (depends on BioTeam-AI's biological domain focus)

### 4.7 BioGPT (Microsoft)
- **URL**: https://huggingface.co/microsoft/biogpt
- **GitHub**: https://github.com/microsoft/BioGPT
- **What it provides**: Domain-specific GPT-2-based model pretrained on 15M PubMed abstracts. Achieves 81% on PubMedQA. Available via Hugging Face Transformers. Capabilities: biomedical text generation, relation extraction, question answering.
- **BioTeam-AI relevance**: Could serve as a specialized model for biomedical entity extraction, relation extraction from papers, and preliminary literature analysis. However, Claude likely outperforms it on most tasks. Consider using BioGPT for specific NER/relation extraction subtasks where a fine-tuned model adds value.
- **Priority**: **NICE TO HAVE** (Claude may handle these tasks adequately)

### 4.8 GRADEpro / GRADE Evidence Assessment
- **URL**: https://www.gradepro.org/
- **Automated GRADE (URSE)**: https://pubmed.ncbi.nlm.nih.gov/40194821/
- **What it provides**: GRADEpro is the standard tool for evidence quality assessment in clinical research. The URSE open-source tool attempts semi-automated GRADE classification, achieving 63.2% agreement with human evaluators. GRADE domains: risk of bias, imprecision, heterogeneity, methodological quality.
- **BioTeam-AI relevance**: BioTeam-AI's Evidence Grading Agent should implement GRADE-like scoring. The URSE tool's approach (automated scoring of specific domains like imprecision and risk of bias) can be adapted as a prompt template for Claude-based evidence assessment. Semi-automated approach (LLM suggests, human validates) is most realistic.
- **Priority**: **SHOULD CONSIDER**

---

## 5. Dashboard / Real-Time Architecture Patterns

### 5.1 sse-starlette (FastAPI SSE)
- **URL**: https://github.com/sysid/sse-starlette
- **PyPI**: https://pypi.org/project/sse-starlette/
- **What it provides**: Production-ready SSE implementation for Starlette/FastAPI following W3C spec. Provides EventSourceResponse and ServerSentEvent classes. Features: automatic client disconnect detection, graceful shutdown, context-local event management, multi-event-loop support. Latest version: 3.2.0.
- **BioTeam-AI relevance**: The SSE transport layer for streaming agent progress, results, and status updates from FastAPI backend to Next.js frontend. Use EventSourceResponse to stream token-by-token LLM output and structured status events (agent started, tool called, result available).
- **Priority**: **MUST USE**

### 5.2 use-next-sse (Next.js SSE Hook)
- **URL**: https://github.com/alexanderkasten/use-next-sse
- **What it provides**: Lightweight React hook library for SSE in Next.js. Provides createSSEHandler for server-side and useSSE hook for client-side. Built-in cleanup/destructor for connection management.
- **BioTeam-AI relevance**: Client-side SSE consumption in the Next.js dashboard. Pairs with sse-starlette on the backend. Handles connection lifecycle, reconnection, and cleanup automatically.
- **Priority**: **SHOULD CONSIDER** (evaluate vs. native EventSource API or other SSE libraries)

### 5.3 React Flow (XyFlow)
- **URL**: https://reactflow.dev/
- **Workflow Editor Template**: https://reactflow.dev/ui/templates/workflow-editor
- **What it provides**: React library for building interactive node-based graphs, flowcharts, and workflow editors. Next.js workflow editor template available. Features: drag-and-drop, custom nodes/edges, automatic layout via ELKjs, zoom/pan, and Tailwind CSS/shadcn/ui styling. Rebranded as XyFlow.
- **BioTeam-AI relevance**: Ideal for visualizing the research workflow as an interactive graph. Each agent becomes a node; data flow between agents becomes edges. Users can see which agents are active, what data is flowing, and where the workflow currently is. The workflow editor template provides a ready-made starting point.
- **Priority**: **MUST USE**

### 5.4 FastAPI + SSE for LLM Streaming Pattern
- **URL**: https://medium.com/@2nick2patel2/fastapi-server-sent-events-for-llm-streaming-smooth-tokens-low-latency-1b211c94cff5
- **URL**: https://akanuragkumar.medium.com/streaming-ai-agents-responses-with-server-sent-events-sse-a-technical-case-study-f3ac855d0755
- **What it provides**: Implementation guides for streaming LLM token output via SSE. Covers: decoupling work from request cycle (use Celery for heavy operations), heartbeat events to prevent proxy timeout, ASGI server requirements (Uvicorn/Daphne), and error handling in streaming contexts.
- **BioTeam-AI relevance**: Architecture pattern for streaming agent outputs to the dashboard. Key takeaways: use background task queues for long agent operations, send heartbeat events during long-running research tasks, always use ASGI servers, and implement proper error communication in streams.
- **Priority**: **SHOULD CONSIDER**

### 5.5 Next.js Streaming with React Suspense
- **URL**: https://nextjs.org/learn/dashboard-app/streaming
- **What it provides**: Built-in Next.js pattern for streaming specific components using React Suspense. Allows immediate display of page UI while deferring rendering of components waiting for data.
- **BioTeam-AI relevance**: Use Suspense boundaries for each agent's output panel. Show the research dashboard immediately; individual agent results stream in as they complete. This creates a responsive UX even when some agents take minutes to finish.
- **Priority**: **SHOULD CONSIDER**

---

## 6. Observability, Cost Management & DevOps

### 6.1 Langfuse (LLM Observability)
- **URL**: https://langfuse.com/
- **GitHub**: https://github.com/langfuse/langfuse
- **Agent Monitoring**: https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse
- **What it provides**: Open-source LLM engineering platform. Captures traces, monitors latency, tracks costs, debugs issues. Supports session tracking for multi-step agent workflows. LLM-as-a-Judge evaluation tracing. Integrates with LangChain, OpenAI, and custom implementations. Self-hostable. Free tier available.
- **BioTeam-AI relevance**: Essential for understanding what 15+ agents are actually doing in production. Track per-agent token usage, latency, error rates, and cost. Session traces let you debug entire research workflows end-to-end. The LLM-as-a-Judge feature can evaluate agent output quality over time.
- **Priority**: **MUST USE**

### 6.2 LiteLLM (LLM Gateway & Cost Tracking)
- **URL**: https://github.com/BerriAI/litellm
- **Docs**: https://docs.litellm.ai/docs/
- **What it provides**: Python SDK and proxy server for 100+ LLM APIs in OpenAI-compatible format. Automatic cost tracking per key/user/team. Budget caps. Load balancing across providers. Built-in guardrails. Integrates with Langfuse for observability.
- **BioTeam-AI relevance**: If BioTeam-AI ever needs to use multiple LLM providers (e.g., Claude for reasoning, a smaller model for classification, a specialized model for embeddings), LiteLLM provides a unified interface and cost tracking across all of them. Even for Claude-only usage, the proxy's cost tracking and rate limiting features are valuable.
- **Priority**: **SHOULD CONSIDER**

---

## Summary: Priority Matrix

### MUST USE (Critical Path)
| Resource | Category | Why |
|----------|----------|-----|
| Building Effective Agents (Anthropic) | SDK Patterns | Canonical architecture guide |
| Multi-Agent Research System (Anthropic) | SDK Patterns | Closest prior art to BioTeam-AI |
| Anthropic Cookbook (Agent Patterns) | SDK Patterns | Working code + research_lead_agent prompt |
| Prompt Caching | SDK Patterns | Up to 90% cost reduction |
| AI Co-Scientist (Generate-Debate-Evolve) | Orchestration | Architecture reference for hypothesis workflow |
| Instructor Library | Guardrails | Structured output enforcement |
| Claude Native Structured Outputs | Guardrails | JSON schema compliance guarantee |
| Research Lead Agent Prompt | Prompting | Starting template for orchestrator |
| NCBI E-Utilities / PubMed API | Biology APIs | Core literature data source |
| Biopython (Bio.Entrez) | Biology APIs | Python interface for PubMed |
| Semantic Scholar API | Biology APIs | Citation graphs + semantic search |
| bioRxiv/medRxiv API | Biology APIs | Preprint access |
| sse-starlette | Dashboard | SSE transport layer |
| React Flow (XyFlow) | Dashboard | Workflow visualization |
| Langfuse | Observability | Agent monitoring + cost tracking |

### SHOULD CONSIDER (High Value)
| Resource | Category | Why |
|----------|----------|-----|
| Claude Agent SDK | SDK Patterns | May replace custom orchestration |
| Claude Agent SDK Demos | SDK Patterns | Working multi-agent code |
| Advanced Tool Use | SDK Patterns | Solves context bloat from tools |
| Long-Running Agent Harnesses | SDK Patterns | Progress tracking patterns |
| LangGraph | Orchestration | Graph-based workflow orchestration |
| Pydantic AI | Orchestration | Structured agent framework |
| Guardrails AI | Guardrails | Output validation layer |
| OpenAlex API | Biology APIs | Free bibliometric data (CC0) |
| UniProt REST API | Biology APIs | Protein data for molecular biology |
| GRADEpro / URSE | Biology APIs | Evidence quality assessment |
| use-next-sse | Dashboard | SSE React hooks |
| Next.js Streaming/Suspense | Dashboard | Progressive UI rendering |
| FastAPI + SSE streaming pattern | Dashboard | LLM token streaming architecture |
| LiteLLM | Observability | Multi-provider gateway + costs |

### NICE TO HAVE (Study for Patterns)
| Resource | Category | Why |
|----------|----------|-----|
| CrewAI | Orchestration | Role-based agent patterns |
| Microsoft Agent Framework | Orchestration | Event-driven architecture patterns |
| NeMo Guardrails | Guardrails | Programmable safety rails |
| Learn Prompting / PromptHub | Prompting | Role-playing prompt patterns |
| BioGPT | Biology APIs | Specialized biomedical NER/QA |

---

## Recommended Implementation Order

1. **Foundation (Week 1-2)**: Set up Anthropic SDK with prompt caching. Implement Instructor for structured outputs. Study the "Building Effective Agents" and "Multi-Agent Research System" posts.
2. **Core Agents (Week 3-4)**: Build orchestrator using research_lead_agent prompt template. Implement PubMed (Biopython), Semantic Scholar, and bioRxiv API integrations. Add Langfuse tracing from day one.
3. **Hypothesis Pipeline (Week 5-6)**: Implement generate-debate-evolve pattern inspired by AI Co-Scientist. Build peer review agent with evaluator-optimizer pattern.
4. **Dashboard (Week 7-8)**: FastAPI SSE backend with sse-starlette. Next.js frontend with React Flow for workflow visualization. React Suspense for progressive loading.
5. **Hardening (Week 9-10)**: Add Guardrails AI for output validation. Implement evidence grading (GRADE-inspired). Add cost monitoring and budget caps.
