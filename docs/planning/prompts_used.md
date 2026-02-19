# BioTeam-AI — Key Prompts & Instructions Used During Planning

**Purpose:** Track record of prompts and instructions that shaped the planning process.

---

## User Prompts (Korean → English Translation)

### Prompt 1: Initial Request
> "I want to build a personal AI Science Team. A dashboard-style interface showing each AI team's status, ability to assign tasks to teams and get updates. Focus on productivity. Review similar tools. Long-term maintainability, security, usability, scalability. Multi-agent development. Find useful guides/prompts/skills."

### Prompt 2: Configuration
> "Confirm using Opus 4.6. Output in English despite Korean prompts. Create expert pool with 10 biology sub-specializations. Consider company structure for workflow enhancement. Focus on structure before development."

### Prompt 3: Proposal Integration
> "Check this file and implement useful ideas from BioTeam-AI_Proposal.docx"

### Prompt 4: v1 Review Request
> "Let's thoroughly review the current plan."

### Prompt 5: v2 Update Request
> "Reflect all these issues and update the plan, then review again."

### Prompt 6: Multi-Perspective Review Request
> "Let's review the current plan from multiple perspectives."

### Prompt 7: v3 Update Request
> "Reflect the above and update the plan to v3."

### Prompt 8: Final Review Request
> "Let's have another critical review to check if there are any issues before moving ahead. I'd like to have the best plan."

---

## Review Agent Prompts

### Internal Consistency Review Prompt
```
You are a senior systems architect reviewing a complex multi-agent AI system plan
for internal consistency. Read the plan and produce a CRITICAL review focused on:

1. Internal Contradictions — Does any part contradict another?
2. Missing Dependencies — Components referenced but never defined?
3. Circular Dependencies in Roadmap — Phase N items depending on Phase N+1?
4. Specification Gaps — High-level descriptions lacking implementation detail?
5. Data Flow Gaps — Trace complete requests and flag unspecified data formats.

Be SPECIFIC. Quote section names. Focus ONLY on problems.
Output as numbered issues with severity (CRITICAL / MAJOR / MINOR).
```

### Implementation Feasibility Review Prompt
```
You are a senior Python/TypeScript developer who has built multi-agent LLM systems.
Produce a CRITICAL review focused on IMPLEMENTATION FEASIBILITY:

1. Claude Agent SDK Reality Check — Does it support the described patterns?
2. asyncio.TaskGroup Limitations — Partial failure, timeout, back-pressure?
3. Pydantic Schema Enforcement — Non-deterministic LLM outputs + validation?
4. SSE Implementation Details — Next.js navigation, Vercel serverless?
5. ChromaDB at Scale — Limits, persistence, Cold Start seeding?
6. Cost Estimation Accuracy — Actual API prices vs. estimates?
7. Week 1-2 Scope Reality — Realistic for solo developer?

Be SPECIFIC and PRACTICAL. Identify concrete implementation blockers.
```

### Edge Cases & Failure Modes Review Prompt
```
You are a QA engineer and chaos engineer. Produce a CRITICAL review focused on
EDGE CASES and FAILURE MODES:

1. Agent Output Quality — Systematic bias detection?
2. Workflow State Recovery — Checkpoint granularity, crash recovery?
3. Memory Pollution — Duplicates, stale data, circular reasoning?
4. RCMXT Gaming — Systematic over/under-scoring?
5. Negative Results False Positives — Citation context confusion?
6. Cost Runaway Scenarios — Budget edge cases?
7. Multi-User Future — Hidden single-user assumptions?
8. Dashboard State Sync — Page refresh, multiple tabs?

For each: (a) failure scenario, (b) likelihood, (c) impact, (d) mitigation.
```

---

## Multi-Perspective Review Prompt Structure

Six expert perspectives were applied to v2 plan:
1. **Software Architect** — Technical feasibility, tech stack, scalability
2. **Biology Domain Expert** — Biological abstractions, RCMXT validity
3. **Solo Researcher UX** — Daily workflow, cognitive load, onboarding
4. **DevOps/Operations** — Infrastructure complexity, monitoring, maintenance
5. **Academic/Publication** — Novelty, positioning, publication strategy
6. **Cost/ROI** — Budget realism, development opportunity cost

Each perspective produced 3-5 concerns with specific recommendations.
Total: 21 actionable changes incorporated into v3.

---

## Design Principles That Emerged

These principles crystallized through iterative review:

1. **Biology ≠ SWE** — Context-dependent truth, RCMXT not boolean
2. **Multi-agent is not always better** — Task-dependent (Google 180-study)
3. **QA must be structurally independent** — Reports to human, not to reviewed teams
4. **Memory is infrastructure** — Episodic + semantic prevents rediscovery
5. **Negative results are first-class data** — 85% file-drawer problem
6. **Bidirectional iteration** — Every workflow loops back
7. **Schema-enforced outputs** — Pydantic validation on all agent outputs
8. **Cost-aware execution** — Model tier per agent, budget per workflow
9. **Code generation, not code execution** — Agents produce code, sandbox executes
10. **Progressive complexity** — Start minimal, scale infrastructure when needed (v3)
11. **Ship research value early** — Every phase delivers usable capability (v3)

---

## Key Reference Materials

- **BioTeam-AI_Proposal.docx** — JangKeun's original working paper
- **Sakana AI Scientist** (2024) — Automated research generation
- **Stanford Virtual Lab** (Nature 2025) — PI + specialist + critic pattern
- **Google AI Co-Scientist** — Generate-Debate-Evolve for hypothesis generation
- **Google 180-experiment study** — Multi-agent not always better than single agent
- **NTT AI Constellation** — Episodic + semantic memory combination
- **Franco et al. (2014)** — 85% of negative results unpublished (file-drawer problem)
