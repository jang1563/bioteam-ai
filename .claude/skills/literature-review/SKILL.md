---
name: literature-review
description: >
  Run a systematic biomedical literature review using the BioTeam-AI W1
  pipeline. Searches PubMed and bioRxiv, screens and extracts data from
  papers, synthesizes findings with anti-hallucination grounding, validates
  citations against retrieved sources, and scores evidence via the RCMXT
  framework. Supports MCP healthcare connectors for enhanced data access.
metadata:
  author: bioteam-ai
  version: "1.0"
  domain: biomedical-research
allowed-tools: Bash(python:*) Read
---

# Literature Review Skill

## When to Activate
- User asks to "review literature" or "find papers" on a biomedical topic
- User asks about evidence for/against a hypothesis
- User wants to identify research gaps, contradictions, or novel findings

## Prerequisites
- Python 3.11+ with the BioTeam-AI backend installed
- `ANTHROPIC_API_KEY` and `NCBI_EMAIL` environment variables set
- Optional: `NCBI_API_KEY` for higher PubMed rate limits

## Usage

```bash
cd backend && uv run python -m app.skills.w1_cli --query "your research question" --budget 5.0
```

## Pipeline Steps (13 total)

1. **SCOPE** — Research Director defines search scope and strategy
2. **SEARCH** — Knowledge Manager searches PubMed + Semantic Scholar (or MCP connectors)
3. **SCREEN** — T02 Transcriptomics screens papers for relevance
4. **EXTRACT** — T02 extracts structured data from included papers
5. **NEGATIVE_CHECK** — Lab KB search for relevant negative results
6. **SYNTHESIZE** — Research Director synthesizes findings (with anti-hallucination grounding)
7. **CONTRADICTION_CHECK** — Ambiguity Engine detects contradictions
8. **CITATION_CHECK** — Validates all citations against retrieved sources
9. **RCMXT_SCORE** — Scores evidence claims (heuristic/LLM/hybrid)
10. **INTEGRITY_CHECK** — Data integrity audit (gene names, retractions, stats)
11. **NOVELTY_CHECK** — Knowledge Manager assesses novelty vs existing knowledge
12. **REPORT** — Final output assembly with session manifest

## Output Format
- JSON report with: executive summary, evidence table, contradiction matrix
- PRISMA flow data (identified → screened → included)
- RCMXT scores per claim (0.0-1.0)
- Citation validation report (verified/unverified counts)
- Session manifest with cost, model versions, step durations

## Anti-Hallucination Guarantees
- SYNTHESIZE receives explicit paper list — only listed papers may be cited
- Citation validator cross-checks all citations against SEARCH results
- Unverified citations are flagged with warnings
- Empty-context queries labeled as "general knowledge"
