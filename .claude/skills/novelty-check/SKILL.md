---
name: novelty-check
description: >
  Assess whether a biomedical finding is novel compared to existing
  knowledge in the BioTeam-AI Lab Knowledge Base. Uses semantic search
  and LLM assessment to score novelty from 0.0 (well-known) to 1.0
  (completely novel).
metadata:
  author: bioteam-ai
  version: "1.0"
  domain: biomedical-research
allowed-tools: Bash(python:*) Read
---

# Novelty Check Skill

## When to Activate
- User asks "is this finding new?" or "has this been reported before?"
- User wants to assess the novelty of experimental results
- User needs to compare findings against existing literature

## Usage

```bash
cd backend && uv run python -m app.skills.novelty_cli --finding "your finding description"
```

## Process
1. Search ChromaDB literature collection for similar findings
2. Search Lab KB for related internal results
3. LLM assessment of novelty vs retrieved evidence
4. Return novelty score with reasoning and similar existing work
