---
name: paper-review
description: >
  Perform systematic peer review of a biomedical research paper.
  Extracts claims, validates citations, cross-checks literature,
  audits data integrity, detects contradictions, reviews methodology,
  scores evidence quality (RCMXT), and generates a structured review
  report with major/minor comments and decision recommendation.
metadata:
  author: bioteam-ai
  version: "1.0"
  domain: biomedical-research
allowed-tools: Bash(python:*) Read
---

# Paper Review Skill

## When to Activate
- User asks to "review a paper" or "peer review this manuscript"
- User wants to assess a paper's methodology, claims, or evidence quality
- User needs a structured review report for a journal submission

## Usage

```bash
cd backend && uv run python -m app.skills.w8_cli --pdf /path/to/paper.pdf --budget 3.0
```

### Options
- `--pdf` / `-p`: Path to the paper PDF (required)
- `--budget` / `-b`: Maximum budget in USD (default: $3.00)
- `--output` / `-o`: Output JSON file path
- `--markdown` / `-m`: Output Markdown report file path

## Pipeline (12 Steps)
1. **INGEST**: Read and validate PDF file
2. **PARSE_SECTIONS**: Extract text, split by headings (PyMuPDF)
3. **EXTRACT_CLAIMS**: LLM extracts structured claims per section
4. **CITE_VALIDATION**: Validate citations (DOI/PMID parseable)
5. **BACKGROUND_LIT**: Search PubMed/bioRxiv for supporting/contradicting evidence
6. **INTEGRITY_AUDIT**: Statistical checks, gene name validation, retraction check
7. **CONTRADICTION_CHECK**: Compare paper claims vs. literature
8. **METHODOLOGY_REVIEW**: Deep assessment (study design, controls, statistics)
9. **EVIDENCE_GRADE**: RCMXT scoring of key claims
10. **HUMAN_CHECKPOINT**: Pause for reviewer input
11. **SYNTHESIZE_REVIEW**: Generate structured peer review
12. **REPORT**: Assemble final Markdown report

## Output
- Structured review with major/minor comments
- Decision recommendation (accept/minor/major revision/reject)
- Methodology assessment with score
- RCMXT evidence quality scores
- Citation integrity report
- AI disclosure statement
