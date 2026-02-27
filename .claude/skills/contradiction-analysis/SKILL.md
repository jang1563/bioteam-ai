---
name: contradiction-analysis
description: >
  Detect contradictions and ambiguities in biomedical evidence using the
  BioTeam-AI W6 Ambiguity Engine. Analyzes claims across papers, scores
  evidence with RCMXT, and generates hypothesis-driven research directions
  from identified contradictions.
metadata:
  author: bioteam-ai
  version: "1.0"
  domain: biomedical-research
allowed-tools: Bash(python:*) Read
---

# Contradiction Analysis Skill

## When to Activate
- User asks to "find contradictions" in a set of papers or findings
- User wants to assess ambiguity or conflicting evidence
- User asks about research gaps that stem from contradictory results

## Usage

```bash
cd backend && uv run python -m app.skills.w6_cli --topic "your research topic" --budget 2.0
```

## Pipeline
1. Gather evidence from Lab KB and prior W1 literature reviews
2. Run ContradictionDetector across all claim pairs
3. Score each contradiction with RCMXT framework
4. Generate hypotheses explaining contradictions
5. Produce structured report with action items

## Output
- Contradiction matrix with confidence scores
- RCMXT evidence scores per conflicting claim
- Generated hypotheses for further investigation
- Recommended experimental approaches to resolve contradictions
