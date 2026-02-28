# Open Peer Review Data Strategy
# BioTeam-AI W8 Paper Review Agent — Training, Evaluation & Improvement

**Created:** 2026-02-27
**Status:** Planning — Living Document
**Owner:** JangKeun Kim
**Linked system:** W8 Paper Review pipeline (`backend/app/workflows/runners/w8_paper_review.py`)

---

## Core Insight

Open peer review data is unique because it includes **author responses** alongside reviewer
comments. This creates a ground truth signal unavailable in any other dataset:

- **Reviewer concern + author concedes + paper revised** → concern was valid and important
- **Reviewer concern + author rebuts convincingly + editor agrees** → concern was overblown
- **Multiple reviewers raise the same point** → high-confidence ground truth

This allows calibrating not just whether W8 *finds* issues, but whether it finds *real* issues.

---

## Continuous Improvement Loop

```
Open Peer Review Corpus
        ↓
   Data Collection Layer      ← peer_review_corpus.py
        ↓
   Parsed & Normalized DB     ← OpenPeerReviewEntry + ReviewerConcern
        ↓
   ┌──────────────────────────────────────────┐
   │  W8 Benchmark Harness                    │
   │   • Concern recall vs. human reviewers   │
   │   • Decision calibration (accept/reject) │
   │   • RCMXT score vs. editorial decision   │
   │   • Per-category miss analysis           │
   └──────────────────────────────────────────┘
        ↓
   Pattern Analysis            ← clustering, gap identification
        ↓
   ┌──────────────────────────────────────────┐
   │  Improvement Outputs                     │
   │   A. Prompt engineering (methodology_    │
   │      reviewer.md, claim_extractor.md)    │
   │   B. RCMXT score calibration             │
   │   C. Fine-tuning dataset (future)        │
   └──────────────────────────────────────────┘
        ↓ (feeds back)
   W8 Agent improvements → re-run benchmark → track delta
```

---

## Data Sources

### Priority 1: Biomedical, Structured, High Quality

| Source | Content | License | API / Access | Estimated Volume |
|--------|---------|---------|-------------|-----------------|
| **eLife** | Decision letter + author response + **full XML text** | CC-BY | REST + XML (no auth) | ~50,000 articles |
| **Nature Portfolio** | Review reports + author responses (Nature, Nat Commun, etc.) | CC-BY | Springer Nature API / Crossref | ~8,000 (2020+) |
| **PLOS Journals** | Academic Editor comments + reviewer reports (PLOS ONE, PLOS Bio) | CC-BY | PLOS API + Crossref | ~15,000 |
| **EMBO Press** | Review history for EMBO J, Mol Sys Bio, etc. | CC-BY | XML bulk download | ~10,000 |
| **Review Commons** | Portable peer review linked to bioRxiv | CC-BY | Manual + Crossref | ~5,000 |
| **F1000Research** | Versioned open review, reviewer names public | CC-BY | API + Crossref | ~10,000 |
| **Wellcome Open Research** | Life sciences, fully open | CC-BY | Manual | ~3,000 |

### Priority 2: Curated Datasets & Supplemental

| Source | Content | Notes |
|--------|---------|-------|
| **Zenodo peer review collections** | Pre-curated (paper, review, response) datasets by researchers | Search: `peer review dataset` on zenodo.org; avoid duplicating curation work |
| **OpenReview.net** | ICLR/NeurIPS/ICML reviews with numerical scores | CS/ML — not biomedical, but excellent for review *structure* calibration |
| **PeerRead** (Allen AI) | AI conference reviews with accept/reject labels | GitHub: `allenai/PeerRead`, good for decision calibration |
| **PCI (Peer Community In)** | Free open peer review for preprints | Biology, ecology, evolution |

### Notes on New Sources

**Nature Portfolio (2020+):**
Nature journals began publishing peer review reports ("Peer Review File") and author responses
as supplementary PDFs alongside accepted articles. Available via:
- Springer Nature API (`api.springernature.com`) with free academic key
- Crossref `references` field for DOI → review file links
- Scope: Nature, Nature Communications, Nature Methods, Nature Genetics — all highly relevant
- Caveat: only available for papers that *opted in* (~40% of articles); review reports are PDFs
  not structured XML → requires our `PaperParser` for text extraction

**PLOS Journals:**
PLOS ONE and PLOS Biology publish Academic Editor decision letters and often full reviewer
reports as part of the article XML. Access via:
- PLOS API: `api.plos.org/search?q=...&fl=id,title,editor_decision`
- Article XML: `journals.plos.org/plosone/article/file?id={doi}&type=manuscript`
- Unique value: PLOS ONE covers *all* life sciences without impact filter — better
  representation of typical (non-elite) papers, balancing eLife's quality bias

**Zenodo:**
Search `https://zenodo.org/search?q=peer+review+dataset&type=dataset` — several researchers
have already assembled curated collections. Check before building our own to avoid duplicating
work. Notable existing datasets:
- "OpenPeerReview" corpus (if exists — verify on Zenodo)
- EMBO-specific review collections
- Any dataset with CC-BY that covers biomedical reviews

### eLife API — JSON + XML Endpoints

**JSON (metadata + review text):**
```
GET https://api.elifesciences.org/articles/{id}

{
  "type": "research-article",
  "title": "...",
  "subjects": [{"id": "genetics-genomics"}, {"id": "cell-biology"}],
  "decisionLetter": {
    "content": [{"type": "paragraph", "text": "Reviewer 1:\n1. The sample size..."}]
  },
  "authorResponse": {
    "content": [{"type": "paragraph", "text": "Response to Reviewer 1, point 1:..."}]
  }
}

Pagination (filter by subject):
GET https://api.elifesciences.org/articles?per-page=100&page=1&subject[]=genetics-genomics
```

**XML (full paper text — KEY DISCOVERY):**
```
GET https://elifesciences.org/articles/{id}.xml

Returns complete JATS XML including:
  <body>         ← full paper text, structured by section
  <back>         ← references in structured format
  <sub-article type="decision-letter">   ← reviewer comments
  <sub-article type="reply">             ← author response
```

This means **no PDF parsing required for eLife papers**. The XML provides:
- Structured sections (Introduction, Methods, Results, Discussion)
- Structured references (DOI, PMID, titles)
- Decision letter and author response in the same document
- Figure captions and table data

**Impact on pipeline:** For eLife papers, skip the INGEST → PARSE_SECTIONS steps entirely.
Feed structured XML text directly to EXTRACT_CLAIMS. This removes the most fragile part of W8
(PDF parsing) and gives cleaner, more consistent input.

**Why eLife is the primary source:**
- Genuinely biomedical (our domain)
- No authentication required for JSON or XML
- Consistent high quality (eLife rejects ~90% before external review)
- CC-BY license — explicitly allows reuse including for training
- Reviewer names anonymous in published letters — no privacy issue
- Subject taxonomy maps cleanly to our domains
- **Full-text XML eliminates PDF dependency entirely**

---

## Data Model

### `OpenPeerReviewEntry` (new DB model)

```python
# backend/app/models/review_corpus.py

class OpenPeerReviewEntry(SQLModel, table=True):
    id: str = Field(primary_key=True)   # "{source}:{article_id}"
    source: str                          # "elife" | "embo" | "f1000" | "pci"
    doi: str = Field(index=True)
    title: str
    abstract: str
    subject_area: str                    # JSON list of subject tags
    paper_url: str = ""                  # Full-text PDF URL if available
    decision_letter: str                 # Raw text of editorial decision + reviewer comments
    author_response: str = ""            # Raw text of author rebuttal
    editorial_decision: str = ""         # "accept" | "major_revision" | "minor_revision" | "reject"
    revision_round: int = 1              # R1, R2, R3...
    published_date: datetime
    parsed_concerns: str = ""            # JSON: list[ReviewerConcern]
    w8_workflow_id: str = ""             # FK to WorkflowInstance if W8 was run on this paper
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### `ReviewerConcern` (extracted unit of analysis)

```python
class ReviewerConcern(BaseModel):
    concern_id: str            # "R1C3" = Reviewer 1, Concern 3
    reviewer_num: int          # 1, 2, 3
    concern_text: str          # The concern as stated by reviewer
    category: str              # "methodology" | "statistics" | "interpretation"
                               # | "citation" | "clarity" | "novelty" | "controls"
    severity: str              # "major" | "minor" | "question" | "suggestion"
    author_response_text: str  # Author's point-by-point response
    resolution: str            # "conceded" | "rebutted" | "partially_addressed" | "unclear"
    was_valid: bool | None     # Ground truth signal (None if unclear)
    raised_by_multiple: bool   # Was same concern raised by 2+ reviewers?
```

### Mapping: Human concern → W8 output

```
Human reviewer concern          W8 source
────────────────────────────────────────────────────────────
"Sample size too small"       → MethodologyAssessment.sample_size_assessment
"Wrong statistical test"      → MethodologyAssessment.statistical_methods
"Missing control group"       → MethodologyAssessment.controls_adequacy
"Overclaimed conclusion"      → ContradictionFindings or ReviewComment
"Missing/wrong citation"      → CitationReport
"Gene name outdated/wrong"    → IntegrityAudit (GeneNameChecker)
"Retracted paper cited"       → IntegrityAudit (RetractionChecker)
"Inconsistent with field"     → BACKGROUND_LIT + ContradictionCheck
"Insufficient methods detail" → MethodologyAssessment.reproducibility_concerns
"GRIM/SPRITE inconsistency"   → IntegrityAudit (StatisticalChecker)
```

This explicit mapping enables **per-category recall** measurement.

---

## Implementation Plan

### Phase 0: Manual Pilot — 1-2 days (Do This First)

Before building any infrastructure, run this immediately to get qualitative signal:

1. Manually browse eLife and pick 5 papers in `genetics-genomics` with open decision letters
   - 3 papers with `minor_revision` decision (clear, focused concerns)
   - 2 papers with `major_revision` (more concerns to compare against)
2. Download each paper PDF and run W8
3. Manually compare `synthesis.comments` with human reviewer concerns
4. Answer: What categories does W8 consistently miss? What does it over-flag?

**Cost:** $0 infrastructure + ~$1 LLM API + 2-3 hours analysis

This phase justifies all subsequent infrastructure investment.

### Phase 1: Data Collection — Week 1

**New files:**
```
backend/app/integrations/peer_review_corpus.py    ← eLife JSON/XML + Nature + PLOS clients
backend/app/models/review_corpus.py               ← OpenPeerReviewEntry, ReviewerConcern
backend/scripts/collect_peer_reviews.py           ← Batch collection script
backend/scripts/check_zenodo_datasets.py          ← One-time: scan Zenodo for existing corpora
```

**Scope (initial):**
- 200 eLife articles across: `genetics-genomics`, `cell-biology`, `neuroscience`
- Filter: must have both `decisionLetter` AND `authorResponse`
- Store raw JSON + full-text XML in SQLite/JSONL

**Text retrieval strategy — XML-first:**
```
Priority 1: eLife XML       → https://elifesciences.org/articles/{id}.xml
              ↓ (no XML)
Priority 2: PLOS XML        → journals.plos.org/plosone/article/file?id={doi}&type=manuscript
              ↓ (no XML)
Priority 3: bioRxiv preprint → use existing biorxiv.py (DOI lookup)
              ↓ (no preprint)
Priority 4: Unpaywall PDF   → api.unpaywall.org/v2/{doi} → PaperParser
              ↓ (paywalled)
Priority 5: metadata-only   → mark paper_text = ""; skip W8 run; still use review text
```

**eLife XML parser (new):**
- Parse JATS XML `<body>` → sections with headings (replaces PaperParser for eLife)
- Parse `<back>/<ref-list>` → structured references (better than PDF extraction)
- Parse `<sub-article type="decision-letter">` → decision letter text
- Parse `<sub-article type="reply">` → author response text
- All in one request: `GET https://elifesciences.org/articles/{id}.xml`

**Nature Portfolio collection:**
- Springer Nature API key (free academic): `api.springernature.com`
- Filter: `journalName:"Nature Communications"&hasReviewReport:true`
- Review report PDFs linked as supplementary → download + parse with PaperParser

**Zenodo pre-check (do first, before building collection from scratch):**
- Search: `https://zenodo.org/api/records?q=peer+review+biomedical&type=dataset`
- If a suitable dataset exists, download and integrate instead of re-scraping
- Expected to save 1-2 weeks of collection work if a good corpus exists

**Rate limiting:** 0.5s delay between requests; cache all responses locally as JSONL backup

### Phase 2: Concern Parser — Week 1-2

**New file:** `backend/app/engines/review_corpus/concern_parser.py`

Decision letters follow semi-structured format. Extract individual concerns using Claude Haiku:

```
Input: full decision letter text
Output: list[ReviewerConcern]
```

Then parse author response to link point-by-point responses:
- Match "Response to Reviewer 1, Comment 3:" → concern_id = "R1C3"
- Classify resolution: conceded / rebutted / partially_addressed / unclear

**Cost estimate:** ~$0.01/paper × 200 papers = **~$2 total** (Haiku)

**Validation:** manually check 20 parsed outputs for accuracy before scaling.

### Phase 3: W8 Benchmark Harness — Week 2

**New file:** `backend/tests/benchmarks/test_benchmark_peer_review_corpus.py`

```python
async def compute_recall(w8_result, human_concerns, threshold=0.65):
    """Semantic recall: what fraction of human concerns did W8 catch?"""
    w8_texts = extract_w8_concern_texts(w8_result)
    matched = 0
    for hc in human_concerns:
        best_sim = max(semantic_similarity(hc.concern_text, w8t) for w8t in w8_texts)
        if best_sim >= threshold:
            matched += 1
    return matched / len(human_concerns)

async def compute_precision(w8_result, human_concerns, threshold=0.65):
    """What fraction of W8 concerns are validated by human review?"""
    w8_texts = extract_w8_concern_texts(w8_result)
    valid = sum(
        1 for w8t in w8_texts
        if any(semantic_similarity(w8t, hc.concern_text) >= threshold
               for hc in human_concerns if hc.was_valid)
    )
    return valid / len(w8_texts) if w8_texts else 0

async def compute_decision_accuracy(w8_result, ground_truth_decision):
    """Does W8 recommended decision match editorial decision?"""
    w8_decision = w8_result["synthesis"]["decision"]
    # Map: "accept"/"minor_revision"/"major_revision"/"reject"
    # Allow ±1 category error as partial credit
    return w8_decision == ground_truth_decision
```

**Embedding model:** `allenai-specter2` (biomedical papers, scientific text)
or `microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-3m-large`

**W8 run scope for benchmarking:**
- Run only on 20-30 papers initially (full LLM pipeline: ~$0.50/paper → ~$15 total)
- Use mock layer for code-only steps to reduce cost
- Scale to 100+ papers after baseline confirmed

**Baseline targets:**

| Metric | Initial Target | Stretch Goal |
|--------|---------------|-------------|
| Concern Recall (overall) | > 0.55 | > 0.70 |
| Concern Recall (major only) | > 0.65 | > 0.80 |
| Concern Precision | > 0.65 | > 0.80 |
| Decision Accuracy | > 0.55 | > 0.70 |
| Methodology concern recall | > 0.60 | > 0.75 |

### Phase 4: Pattern Analysis & Prompt Improvement — Week 3

**Goal:** Identify what W8 systematically misses, then improve prompts.

**Analysis steps:**
1. Cluster all human concerns by category and subcategory
2. For each category: compute W8 recall — find worst-performing categories
3. Pull representative high-quality examples of missed concern type from corpus
4. Update `methodology_reviewer.md` with real-review patterns (anonymized)
5. Update `claim_extractor.md` prompt with examples of claims reviewers challenge most

**Few-shot example format for methodology_reviewer.md:**
```markdown
## Validated Review Patterns (from open peer review corpus, anonymized)

### Statistics: Insufficient Power with Specific Quantification
Strong: "The authors report p=0.04 with n=4 per group. Given the reported
SD (±45%) and the 1.5-fold effect size claimed, post-hoc power analysis
yields ~22% — far below conventional thresholds. The conclusion should be
stated as preliminary."

Weak (avoid): "Sample size seems small."

[Calibration: strong critique was conceded and led to paper revision]
```

### Phase 5: Fine-tuning Dataset — Month 2+

Build JSONL dataset for future model calibration:

```json
{
  "paper_excerpt": "...methods section text...",
  "reviewer_concern": "The ANOVA performed assumes sphericity, which was not tested...",
  "category": "statistics",
  "severity": "major",
  "was_valid": true,
  "resolution": "conceded",
  "source": "elife:84798",
  "revision_round": 1
}
```

**Applications:**
1. Calibrate `overall_methodology_score` thresholds in MethodologyAssessment
2. Map RCMXT score ranges to editorial decisions
3. Build preference dataset for RLHF-style calibration
4. Future: model fine-tuning if Anthropic API supports it

---

## Key Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| eLife API rate limits / downtime | Medium | Cache XML responses as local JSONL; 0.5s delays; retry with backoff |
| Decision letter text unstructured (parsing fails) | High | LLM-based extraction (Haiku); manual spot-check 20 papers; ~15-20% failure rate expected |
| No space biology papers in eLife subject taxonomy | Medium | Keyword search ("spaceflight", "ISS", "microgravity") in titles; NASA GeneLab pub list |
| Author response unclear about concern validity | Medium | Use `resolution_confidence` float (0-1) instead of binary was_valid; exclude < 0.5 |
| Semantic matching threshold miscalibrated | Medium | Spot-check 50 pairs manually; tune on held-out set; use SPECTER2 for biomedical text |
| W8 benchmark cost too high at scale | Medium | Start with 20-30 papers; `skip_human_checkpoint=True` in W8.run() for batch runs |
| eLife quality bias (only top-tier papers) | Medium | Supplement with PLOS ONE (broad quality range) and F1000Research |
| Nature Portfolio review files are PDFs not XML | Medium | PaperParser handles PDFs; lower parsing quality than XML but acceptable |
| Zenodo dataset search finds nothing useful | Low | Time-box to 2 hours; proceed with original scraping plan if nothing found |
| OpenReview (CS/ML) contaminates biomedical criteria | Low | Use only for structure/format reference, never for biomedical-specific criteria |
| Multi-round review R2 confounds R1 analysis | Medium | Track `revision_round` field; analyze R1 and R2+ separately |

---

## Critical Gaps (Identified in Review)

### Gap 1: Space Biology Representation
`methodology_reviewer.md` has detailed space biology criteria (ISS, microgravity, radiation dose,
crew variability). eLife's subject taxonomy doesn't have "space biology" — these papers appear
under `cell-biology` or `genetics-genomics`. **Solution:** keyword search for "spaceflight",
"ISS", "microgravity" in titles; also pull from NASA GeneLab publication list.

### Gap 2: Multi-round Review Signal
R2 tells us which R1 concerns were satisfactorily resolved — richer than R1 alone.
**Solution:** collect R1 and R2+ for same papers where available (eLife often has this);
store `revision_round` and allow differential analysis.

### Gap 3: Reviewer Disagreement Handling
Multiple reviewers often disagree. Naive averaging loses information.
**Solution:** store per-reviewer concerns separately; concerns raised by 2+ reviewers get
`raised_by_multiple=True` and higher ground truth confidence.

### Gap 4: "Negative Examples" for Calibration
We need examples of concerns that were convincingly rebutted — to teach W8 "don't over-flag
this." The `was_valid=False` (resolution="rebutted") cases in our dataset serve this purpose.
This is as important as the positive examples.

### Gap 5: Full-text Access — RESOLVED for eLife via XML
**Resolution:** eLife publishes complete JATS XML at `https://elifesciences.org/articles/{id}.xml`.
This provides structured full-text (sections, references, figures) without any PDF parsing.
For eLife papers, the W8 INGEST → PARSE_SECTIONS steps can be replaced by a direct XML parser,
eliminating the most fragile part of the pipeline.

For non-eLife sources (Nature, PLOS, EMBO):
- PLOS: full XML available via `journals.plos.org/plosone/article/file?id={doi}&type=manuscript`
- Nature Portfolio: review reports are PDFs → use PaperParser; paper text via Unpaywall
- EMBO: full XML via bulk download; individual: Unpaywall fallback
- Fallback for any source: store metadata + review text only; paper_text = ""; still useful
  for concern parser and ground truth collection even without running full W8

### Gap 6: Evaluation Reproducibility
Benchmark must be reproducible as W8 evolves. **Solution:** version-stamp each benchmark run
with W8 git hash + prompt versions; store results in SQLite; track improvement delta over time.

### Gap 7: Embedding Model Choice
Semantic matching quality depends on embedding model. BioBERT/PubMedBERT vs. SPECTER2 vs.
general sentence-transformers — they behave differently on methodology critique text.
**Solution:** during Phase 0 pilot, manually validate which model gives best match quality
on 20 concern pairs.

### Gap 8: Annotation Noise in Resolution Classification
LLM-parsed "resolution" field (conceded/rebutted/unclear) has inherent noise.
**Solution:** compute inter-annotator agreement on 30 pairs (LLM vs. human); accept only
if kappa > 0.6.

---

## File Structure

```
backend/
  app/
    integrations/
      peer_review_corpus.py         ← eLife JSON/XML + Nature + PLOS + F1000 clients
    models/
      review_corpus.py              ← OpenPeerReviewEntry, ReviewerConcern
    engines/
      review_corpus/
        __init__.py
        xml_parser.py               ← eLife/PLOS JATS XML → structured paper text (NEW)
        concern_parser.py           ← LLM-based concern extraction from decision letters
        concern_matcher.py          ← Semantic matching: W8 output vs. human concerns
        corpus_stats.py             ← Aggregated benchmark statistics
  scripts/
    check_zenodo_datasets.py        ← One-time: scan Zenodo for existing corpora (NEW)
    collect_peer_reviews.py         ← Batch collection (run weekly)
    run_w8_benchmark.py             ← Run W8 on corpus sample; output benchmark report
    analyze_concern_patterns.py     ← Cluster concerns for prompt improvement

  tests/
    benchmarks/
      test_benchmark_peer_review_corpus.py  ← Automated benchmark (pytest)

docs/
  planning/
    open_peer_review_strategy.md    ← This document
```

---

## Success Metrics

| Metric | Pre-corpus (unknown) | 3-month Target |
|--------|---------------------|---------------|
| Major concern recall | ? | > 0.75 |
| Overall concern recall | ? | > 0.60 |
| Concern precision | ? | > 0.70 |
| Decision accuracy | ? | > 0.65 |
| Space biology recall | ? | > 0.70 |
| Benchmark run cost (20 papers) | — | < $15 |

---

## Phase 0 Results (2026-02-27)

### Papers Run
- 00969 (BRAF/JNK, cancer-biology), 83069 (GAS6/macrophage, immunology), 11058 (mTORC1, cell-biology)
- Scripts: `backend/scripts/run_w8_pilot.py`
- Data: `backend/data/phase0_pilot/` (PDFs + eLife JSON + W8 results)
- Full findings: `backend/data/phase0_pilot/PHASE0_FINDINGS.md`

### Qualitative Recall Estimates

| Concern type | W8 recall |
|-------------|-----------|
| Study design flaws / confounds | ~80% |
| Statistical methodology | ~75% |
| Bias identification | ~70% — W8 finds some biases human reviewers miss |
| Controls adequacy | ~50% |
| Reproducibility / methods completeness | ~40% — too generic |
| Figure-level data inconsistency | ~0% — W8 cannot read figures |
| Prior literature / novelty | ~20% |
| Missing experiments (specific) | ~25% |
| **Overall estimated recall** | **~50-55%** |

### Key Strength
W8 produces BETTER-JUSTIFIED methodology concerns than human reviewers for design flaws
(confounds, biases, statistical gaps). The 83069 comparison shows W8 found the mouse model
ApoE efferocytosis confound with more mechanistic detail than the human reviewer.

### Key Gap 1: Figure Reading
~20-30% of human major concerns are figure-level data inconsistencies (cross-figure
contradictions, mislabeled axes, scale bars). W8 cannot currently read figures.
**Long-term fix:** PDF image extraction + vision model for figure validation.

### Key Gap 2: Prior Art / Novelty
W8 misses "this experiment was published before" concerns. BACKGROUND_LIT helps generally
but doesn't identify specific methodological precedents.
**Fix:** Improve BACKGROUND_LIT step with specificity-focused prompting.

### Key Gap 3: Reagent/Methods Completeness
W8 raises generic reproducibility concerns ("no data availability") but misses specific
missing items ("shRNA sequences not described", "antibody catalog number missing").
**Fix:** Add few-shot examples of specific reagent concerns to methodology_reviewer.md.

### Critical Bug Found: SYNTHESIZE_REVIEW Schema Mismatch
`research_director.synthesize()` returns ResearchDirector's generic schema (key_findings,
evidence_gaps), NOT `PeerReviewSynthesis` (decision, comments). This means:
- `synthesis.decision` is always None
- `synthesis.comments` is always empty
- The final report is incomplete
**Must fix before Phase 3 benchmarking.**

### Revised Baseline Targets (updated from pilot data)

| Metric | Revised Target |
|--------|---------------|
| Overall concern recall (top-10 W8 concerns only) | > 0.55 |
| Design/methodology recall | > 0.75 |
| Figure-inconsistency recall | ~0.05 (structural gap — out of scope until vision added) |
| Decision accuracy (after SYNTHESIZE_REVIEW fix) | > 0.60 |

---

## Update Log

| Date | Update | Author |
|------|--------|--------|
| 2026-02-27 | Initial plan created. Multi-angle review done: risks, gaps, data sources, metrics defined. | JK |
| 2026-02-27 | Added Nature Portfolio, PLOS Journals, Zenodo as data sources. eLife XML full-text discovery: eliminates PDF dependency for eLife papers. XML-first retrieval strategy defined. Gap 5 resolved. Risk table updated. `xml_parser.py` and `check_zenodo_datasets.py` added to file structure. | JK |
| 2026-02-27 | **Phase 0 complete.** 3 papers run (00969, 83069, 11058). Overall recall ~50-55%. 3 key gaps identified: figure reading, prior art, reagent specificity. Critical SYNTHESIZE_REVIEW schema bug found. Revised baseline targets set. See `backend/data/phase0_pilot/PHASE0_FINDINGS.md`. | JK |
| 2026-02-27 | **Phase 0 → fixes applied.** (1) W8 NOVELTY_CHECK step added (addresses Gap 2: Prior Art/Novelty) — `NoveltyAssessment` model, landmark paper search via KnowledgeManager, structured novelty score + already_established/unique_contributions output. (2) SYNTHESIZE_REVIEW bug fixed: `research_director.synthesize_peer_review()` now returns `PeerReviewSynthesis` (decision, comments, confidence) instead of generic `SynthesisReport`. (3) Tests updated: W8_STEPS → 13 steps, registry → 23 agents. All 486 tests passing. | JK |
