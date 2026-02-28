# BioReview-Bench: Open Peer Review Benchmark Dataset
## Separate Project Plan

**Created:** 2026-02-27
**Status:** Planning
**Owner:** JangKeun Kim, Weill Cornell Medicine
**Parent Project:** BioTeam-AI (this plan is intentionally separate)
**Background Data:** See `docs/planning/open_peer_review_strategy.md` for full data source analysis, Phase 0 pilot results, and data model design (already done)

---

## Project Overview

Create a publicly shareable benchmark dataset for evaluating AI-assisted peer review systems in biomedical research. Collected from open peer review journals (eLife, Nature Portfolio, PLOS, EMBO, F1000Research), structured as human reviewer concern triplets with ground truth resolution labels.

**Why separate from BioTeam-AI:**
- Benchmark should be independently usable by any AI peer review tool
- Needs its own license (CC-BY data), versioning, DOI, and citation path
- HuggingFace Dataset Hub hosting for community access
- Clean governance separate from BioTeam-AI codebase

---

## Target Output

```
GitHub:       github.com/[username]/bioreview-bench
HuggingFace:  huggingface.co/datasets/jang1563/bioreview-bench
License:      CC-BY 4.0 (matches source journals)
Format:       JSONL + HuggingFace datasets library compatible
```

---

## Repository Structure

```
bioreview-bench/
├── README.md                     ← Dataset card (HF-compatible)
├── DATASHEET.md                  ← Gebru et al. datasheet format
├── LICENSE                       ← CC-BY 4.0
├── pyproject.toml                ← uv project, Python 3.12
│
├── collect/                      ← Data collection scripts
│   ├── elife_collector.py        ← eLife JSON+XML API → JSONL
│   ├── plos_collector.py         ← PLOS API → JSONL
│   ├── nature_collector.py       ← Springer Nature API → JSONL
│   ├── embo_collector.py         ← EMBO bulk XML → JSONL
│   ├── zenodo_checker.py         ← One-time: scan for existing corpora
│   └── base_collector.py         ← Shared retry/rate-limit/cache logic
│
├── parse/                        ← Parsing and extraction
│   ├── jats_xml_parser.py        ← eLife/PLOS JATS XML → structured sections
│   ├── concern_parser.py         ← LLM (Haiku): decision letter → ReviewerConcern list
│   ├── response_parser.py        ← LLM (Haiku): author response → resolution labels
│   └── resolution_classifier.py ← conceded / rebutted / partial / unclear
│
├── validate/                     ← Quality assurance
│   ├── annotation_agreement.py   ← Inter-annotator agreement (kappa)
│   ├── duplicate_detector.py     ← Cross-source dedup via DOI + title similarity
│   └── schema_validator.py       ← Pydantic validation on all entries
│
├── evaluate/                     ← Benchmark evaluation harness
│   ├── metrics.py                ← recall, precision, F1, decision_accuracy
│   ├── semantic_matcher.py       ← SPECTER2 embedding-based concern matching
│   ├── leaderboard.py            ← Format results for leaderboard
│   └── run_benchmark.py          ← CLI: evaluate any tool's output against ground truth
│
├── data/
│   ├── raw/                      ← Cached API responses (gitignored, large)
│   │   ├── elife/
│   │   ├── plos/
│   │   └── nature/
│   ├── processed/                ← Parsed + validated entries
│   │   ├── v1.0/
│   │   │   ├── train.jsonl       ← 70% split
│   │   │   ├── val.jsonl         ← 15% split
│   │   │   └── test.jsonl        ← 15% split (held-out, for leaderboard)
│   │   └── v1.1/
│   └── stats/                    ← Corpus statistics + quality reports
│       ├── concern_distribution.json
│       └── source_breakdown.json
│
├── models/                       ← Pydantic data models
│   ├── entry.py                  ← OpenPeerReviewEntry
│   ├── concern.py                ← ReviewerConcern
│   └── benchmark_result.py       ← BenchmarkRun, MetricSet
│
├── scripts/
│   ├── build_dataset.sh          ← Full pipeline: collect → parse → validate → split
│   ├── upload_to_hf.py           ← Push to HuggingFace Hub
│   └── generate_stats.py         ← Corpus statistics report
│
└── tests/
    ├── test_collectors.py        ← Mock API responses
    ├── test_parsers.py           ← JATS XML + concern extraction
    └── test_metrics.py           ← Recall/precision/F1 correctness
```

---

## Data Schema

### `OpenPeerReviewEntry` (one per article)

```json
{
  "id": "elife:84798",
  "source": "elife",
  "doi": "10.7554/eLife.84798",
  "title": "...",
  "abstract": "...",
  "subjects": ["genetics-genomics", "cell-biology"],
  "editorial_decision": "major_revision",
  "revision_round": 1,
  "published_date": "2023-08-15",
  "paper_text_sections": {
    "introduction": "...",
    "methods": "...",
    "results": "...",
    "discussion": "..."
  },
  "structured_references": [
    {"ref_id": "r1", "title": "...", "doi": "...", "pmid": "..."}
  ],
  "decision_letter_raw": "...",
  "author_response_raw": "...",
  "concerns": [...],
  "schema_version": "1.0"
}
```

### `ReviewerConcern` (one per concern within an article)

```json
{
  "concern_id": "elife:84798:R1C3",
  "reviewer_num": 1,
  "concern_text": "The ANOVA performed assumes sphericity, which was not tested...",
  "category": "statistics",
  "severity": "major",
  "author_response_text": "We thank the reviewer. We have now added Mauchly's test...",
  "resolution": "conceded",
  "resolution_confidence": 0.91,
  "was_valid": true,
  "raised_by_multiple": false,
  "source": "elife",
  "article_doi": "10.7554/eLife.84798"
}
```

### `BenchmarkResult` (tool evaluation output format)

```json
{
  "tool_name": "BioTeam-AI W8",
  "tool_version": "0.6.0",
  "git_hash": "0bcb894",
  "benchmark_version": "1.0",
  "run_date": "2026-02-27",
  "metrics": {
    "concern_recall_overall": 0.58,
    "concern_recall_major": 0.71,
    "concern_precision": 0.67,
    "decision_accuracy": 0.62,
    "f1_overall": 0.62,
    "by_category": {
      "statistics": {"recall": 0.75, "precision": 0.70},
      "methodology": {"recall": 0.68, "precision": 0.65},
      "novelty": {"recall": 0.22, "precision": 0.55},
      "controls": {"recall": 0.51, "precision": 0.60}
    }
  },
  "n_articles": 50,
  "n_concerns": 312
}
```

---

## Data Sources (Priority Order)

From `open_peer_review_strategy.md` Phase 0 analysis:

| Source | Volume | Access | Priority |
|--------|--------|--------|----------|
| **eLife** | ~50,000 | REST + full JATS XML (no auth) | **1st** |
| **PLOS ONE/Bio** | ~15,000 | PLOS API + XML | 2nd |
| **Nature Portfolio** | ~8,000 | Springer Nature API key | 3rd |
| **EMBO Press** | ~10,000 | Bulk XML download | 4th |
| **F1000Research** | ~10,000 | API + Crossref | 5th |

**v1.0 scope:** 500 eLife articles (genetics-genomics, cell-biology, neuroscience)
**v1.1 scope:** + 200 PLOS + 100 Nature Portfolio
**v2.0 scope:** Full multi-source, 2,000+ articles

---

## Evaluation Metrics

```python
# Semantic recall: what fraction of human concerns did the tool catch?
# Uses SPECTER2 embeddings, threshold 0.65 cosine similarity

concern_recall(tool_output, human_concerns)  → float [0,1]
concern_precision(tool_output, human_concerns) → float [0,1]
decision_accuracy(tool_decision, editorial_decision) → float [0,1]

# Per-category breakdown
category_recall(tool_output, human_concerns, category="statistics") → float

# Validity-weighted recall (only count valid human concerns, resolution="conceded")
valid_concern_recall(tool_output, human_concerns) → float
```

**Baseline tool (published with v1.0):** BioTeam-AI W8 (Phase 0 pilot: ~50-55% overall recall)

---

## Implementation Phases

### Phase 1: Core Infrastructure — Week 1
- [ ] Initialize repo, pyproject.toml, uv
- [ ] `models/entry.py`, `models/concern.py` (Pydantic, no SQLModel — pure data)
- [ ] `collect/elife_collector.py` — fetch JSON + XML, cache as JSONL
- [ ] `parse/jats_xml_parser.py` — JATS XML → structured sections + references
- [ ] `parse/concern_parser.py` — Claude Haiku extraction of ReviewerConcern list
- [ ] `validate/schema_validator.py` — validate all entries
- [ ] Collect 200 eLife articles, parse concerns
- [ ] Unit tests for all parsers

### Phase 2: Annotation Quality — Week 2
- [ ] `parse/response_parser.py` — link author responses to concerns, classify resolution
- [ ] `validate/annotation_agreement.py` — LLM vs. manual kappa on 30 pairs (target kappa > 0.6)
- [ ] `validate/duplicate_detector.py` — DOI-based + title-similarity dedup
- [ ] Expand to 500 articles, generate `data/stats/`
- [ ] Train/val/test split (70/15/15 stratified by editorial_decision + source)

### Phase 3: Benchmark Harness — Week 3
- [ ] `evaluate/semantic_matcher.py` — SPECTER2 embeddings + cosine matching
- [ ] `evaluate/metrics.py` — recall, precision, F1, decision_accuracy, by_category
- [ ] `evaluate/run_benchmark.py` — CLI: `python -m evaluate.run_benchmark --tool-output results.json --split test`
- [ ] `evaluate/leaderboard.py` — Markdown leaderboard table generator
- [ ] Run BioTeam-AI W8 as first tool, publish baseline results

### Phase 4: HuggingFace Release — Week 4
- [ ] `README.md` with HuggingFace dataset card format
- [ ] `DATASHEET.md` — Gebru et al. datasheet
- [ ] `scripts/upload_to_hf.py` — push to `jang1563/bioreview-bench`
- [ ] GitHub repo public with CC-BY 4.0 LICENSE
- [ ] Tag v1.0, generate DOI via Zenodo (auto-linked from GitHub release)

### Phase 5: Expand + Iterate — Month 2
- [ ] Add PLOS ONE + Nature Portfolio (v1.1)
- [ ] Re-run BioTeam-AI W8 after prompt improvements → show delta
- [ ] leaderboard.md with multiple tool comparison
- [ ] preprint on bioRxiv describing dataset + baseline

---

## Known Constraints from Phase 0 Pilot

From `open_peer_review_strategy.md` Phase 0 results:

- **Figure concerns (~20-30% of human major concerns):** W8 gets ~0% recall — structural gap, out of scope for v1.0. Mark these concerns with `requires_figure_reading: true` for future tools.
- **Prior art / novelty concerns:** W8 gets ~20% recall — improve with specificity-focused BACKGROUND_LIT prompting
- **Reagent/method specificity:** W8 too generic — few-shot examples needed in methodology_reviewer.md
- **Strong suit:** Design flaws, statistical methodology (~75-80% recall) — publish this differentiated finding

---

## Integration with BioTeam-AI

This benchmark is a separate project, but BioTeam-AI can consume it:

```python
# backend/app/eval/w8_benchmark.py (in BioTeam-AI, NOT in this project)

from datasets import load_dataset

def run_w8_on_benchmark(n_articles=20, split="val"):
    ds = load_dataset("jang1563/bioreview-bench", split=split)
    sample = ds.shuffle().select(range(n_articles))
    # Run W8 on each article's paper_text_sections
    # Compare against article's concerns (ground truth)
    # Return BenchmarkResult
```

---

## Cost Estimates

| Task | Model | Unit Cost | Volume | Total |
|------|-------|-----------|--------|-------|
| Concern extraction (concern_parser.py) | Claude Haiku | $0.01/paper | 500 | $5 |
| Response parsing (response_parser.py) | Claude Haiku | $0.01/paper | 500 | $5 |
| W8 benchmark runs (Phase 3 baseline) | Claude Opus | $0.50/paper | 30 | $15 |
| SPECTER2 embeddings | Local | $0 | — | $0 |
| **Total v1.0** | | | | **~$25** |

---

## Starting Point for New Session

Tell Claude Code in the new session:

```
새 프로젝트 bioreview-bench를 ~/[원하는 경로]/bioreview-bench 에 생성해줘.

참고 문서:
- /Users/jak4013/Dropbox/Bioinformatics/Claude/AI_Scientist_team/docs/planning/peer_review_benchmark_project.md
  (이게 이 새 프로젝트의 마스터 계획서)
- /Users/jak4013/Dropbox/Bioinformatics/Claude/AI_Scientist_team/docs/planning/open_peer_review_strategy.md
  (데이터 소스, eLife API, 데이터 모델 상세 스펙 — Phase 0 파일럿 결과 포함)

Phase 1부터 시작:
1. pyproject.toml (uv, Python 3.12, anthropic, httpx, pydantic, datasets, sentence-transformers)
2. models/entry.py, models/concern.py
3. collect/elife_collector.py (eLife JSON + XML → JSONL 캐시)
4. parse/jats_xml_parser.py (JATS XML → structured sections)
5. parse/concern_parser.py (Claude Haiku → ReviewerConcern list)
```

---

## Update Log

| Date | Note |
|------|------|
| 2026-02-27 | Plan created. Based on Phase 0 pilot results from BioTeam-AI open_peer_review_strategy.md. |
