# RCMXT Evidence Confidence Framework — Annotation Guidelines

**Version:** 1.0
**Date:** 2026-02-28
**Contact:** JangKeun Kim, Weill Cornell Medicine

---

## 1. Purpose

These guidelines support **two annotation tasks**:
1. **Inter-rater reliability (IRR) study** — 5 domain experts independently score 150 biological claims. Used to validate LLM RCMXT scoring.
2. **Benchmark corpus construction** — curate and label 150 claims + ground-truth scores for reproducible LLM evaluation.

---

## 2. What is RCMXT?

RCMXT is a 5-axis evidence confidence framework for biomedical claims. Each axis captures an orthogonal dimension of evidence quality:

| Axis | Full Name | Core Question |
|------|-----------|---------------|
| **R** | Reproducibility | Has this been independently replicated? |
| **C** | Condition Specificity | How broadly does this generalize? |
| **M** | Methodological Robustness | How rigorous was the study design? |
| **X** | Cross-Omics Concordance | Do different data layers agree? *(NULL if single-omics)* |
| **T** | Temporal Stability | Has this finding been consistent over time? |

All axes score **0.0–1.0** (higher = more confidence). X may be **NULL** (not applicable).

### Overall Evidence Confidence

The composite score is a weighted mean of applicable axes:
- R: 0.30 weight
- C: 0.20 weight
- M: 0.25 weight
- X: 0.15 weight (ignored if NULL, weights renormalized)
- T: 0.10 weight

---

## 3. Scoring Unit: The Biological Claim

A **claim** is a specific, testable declarative statement about a biological phenomenon. Examples:

✅ **Valid claims:**
- "Splenic hemolysis increases by ~54% during long-duration spaceflight in healthy adults"
- "EGFR L858R mutation confers sensitivity to erlotinib in non-small-cell lung cancer"
- "Hippocampal neurogenesis in adult humans declines significantly with age"

❌ **Not valid claims:**
- "Cancer is complex" (too vague)
- "BRCA1 should be tested in all patients" (recommendation, not observation)
- "Further research is needed" (not a claim)

**Unit of scoring:** One claim = one set of 4–5 axis scores.

---

## 4. Axis-by-Axis Rubric

### 4.1 R — Reproducibility (0.0–1.0)

**Core question:** How many **independent** research groups have confirmed this exact finding?

"Independent" means: different institutions, different first authors, funded separately. Same-lab replications count minimally.

**Anchor examples:**

| Score | Description | Example claim + reason |
|-------|-------------|----------------------|
| **0.1** (Low) | No independent replication | "SIRT7 interacts with H3K18Ac to promote rDNA transcription" — Reported in one lab (Barber et al., 2012). No independent replication at time of scoring. |
| **0.5** (Mid) | 2–3 independent groups, partial agreement | "Splenic hemolysis increases in microgravity" — Confirmed in NASA Twin Study + Trudel et al. 2022, but sample sizes remain small; mechanisms debated. |
| **0.9** (High) | Textbook-level, many replications | "p53 is mutated in >50% of human cancers" — Confirmed by The Cancer Genome Atlas, COSMIC, TP53 database, hundreds of studies. |

**Common pitfalls:**
- Do NOT credit re-analyses of the same dataset as independent replications.
- Meta-analyses count as high R only if they pool genuinely independent cohorts.
- Pre-registered replications count more than post-hoc replications.

---

### 4.2 C — Condition Specificity (0.0–1.0)

**Core question:** How broadly does this finding generalize across biological contexts (species, cell types, disease states, experimental conditions)?

Higher C = more universal. Lower C = more context-specific or contains absolutist overreach.

**Anchor examples:**

| Score | Description | Example claim + reason |
|-------|-------------|----------------------|
| **0.1** (Low) | Single model system or absolutist overreach | "Wnt signaling is always pro-tumorigenic" — Demonstrably false; Wnt is tumor-suppressive in some contexts (e.g., colorectal cancer in certain stages). |
| **0.5** (Mid) | Generalized 2–3 contexts, exceptions known | "CRISPR-Cas9 efficiency is reduced at heterochromatic loci" — True in most cell types but efficiency varies with chromatin accessibility, guide design, and delivery method. |
| **0.9** (High) | Fundamental biological principle | "Telomere length decreases with each cell division in somatic cells without active telomerase" — True across species, cell types, and conditions. |

**Common pitfalls:**
- Claims with "always," "universally," "never," or "all" that are empirically wrong → score C ≤ 0.2.
- Claims that are technically correct but only in a single model organism → score C ≤ 0.3.

---

### 4.3 M — Methodological Robustness (0.0–1.0)

**Core question:** What is the quality of the study designs supporting this claim?

Assess the **best available evidence** for the claim, not just the study you encountered it in.

**Anchor examples:**

| Score | Description | Example claim + reason |
|-------|-------------|----------------------|
| **0.1** (Low) | Preprint only, no controls, or major design flaw | "Ivermectin prevents COVID-19 transmission" — Multiple early claims from case series and confounded retrospective studies. Later RCTs showed no effect. |
| **0.5** (Mid) | Peer-reviewed but limited power | "Gut microbiome composition differs in spaceflight crews" — Peer-reviewed (Garrett-Bakelman et al. 2019) but n=1 twin pair, limited generalizability. |
| **0.9** (High) | Gold-standard methodology | "Daily low-dose aspirin reduces non-fatal myocardial infarction in high-risk adults" — Multiple large pre-registered RCTs (ISIS-2, Physicians' Health Study), meta-analyses, consistent across cohorts. |

**Common pitfalls:**
- A finding supported only by in vitro data (no animal or human validation) → M ≤ 0.5.
- Retrospective observational studies → M ≤ 0.6 without prospective validation.
- Sample size n < 10 → M ≤ 0.4 regardless of statistical significance.

---

### 4.4 X — Cross-Omics Concordance (0.0–1.0 or NULL)

**Step 1 — Is X applicable?**

X is applicable ONLY when the claim involves or is supported by **multiple omics data types** (e.g., genomics + transcriptomics, proteomics + metabolomics, multi-modal measurement).

**Set X = NULL if:**
- The claim and all supporting evidence come from a single data modality (e.g., only genomics, only imaging, only clinical measurements, only behavioral assays).
- The claim makes no reference to molecular-level data.

**Step 2 — If X is applicable, score concordance:**

| Score | Description | Example |
|-------|-------------|---------|
| **0.1** (Low) | Multi-omics data exists, actively contradicts | Proteomics shows protein X upregulated but transcriptomics shows mRNA downregulated (without post-transcriptional explanation). |
| **0.5** (Mid) | Mixed concordance | Genomic variant associated with disease, transcriptomics partially confirms, but metabolomics inconclusive. |
| **0.9** (High) | Strong cross-layer agreement | EGFR amplification (genomics) → EGFR overexpression (transcriptomics) → EGFR protein high (proteomics) → downstream PI3K phosphorylation (phosphoproteomics) all concordant. |

**CRITICAL:** Never assign X = 0.5 as a "I don't know" hedge. If uncertain, mark NULL.

---

### 4.5 T — Temporal Stability (0.0–1.0)

**Core question:** Has this finding been consistent over time? Has later work confirmed, refuted, or substantially reinterpreted it?

**Anchor examples:**

| Score | Description | Example claim + reason |
|-------|-------------|----------------------|
| **0.1** (Low) | Very recent (<2 years) with no follow-up, or contradicted | Claim from a 2025 preprint with no subsequent citation or replication. OR a 2010 finding since refuted by 2020 large-cohort studies. |
| **0.5** (Mid) | 5–10 year old finding, partially consistent | "cfDNA as a cancer screening biomarker" — Introduced ~2017–2019, multiple studies in progress, interpretation evolving as sensitivity/specificity data matures. |
| **0.9** (High) | Decades-old, withstood technology revolutions | "DNA replication is semiconservative" — Meselson-Stahl 1958, confirmed by every subsequent molecular biology approach. |

**Common pitfalls:**
- Old age alone does not guarantee high T. An old finding that later work has questioned → T ≤ 0.4.
- A claim first made 20 years ago but widely questioned in the last 5 years → T ≤ 0.3.

---

## 5. Decision Rules

### 5.1 Ambiguous Claim Scope

If a claim is ambiguous about its scope (e.g., "BRCA1 loss causes genomic instability" — in all cells? in specific cancer types?), annotators should:
1. Interpret it in the **narrowest defensible sense** (most specific scope).
2. Note the ambiguity in the "notes" column.

### 5.2 Conflicting Evidence

When evidence directly contradicts the claim:
- R should reflect this (2 labs confirm, 1 refutes → R ≈ 0.4).
- C should reflect known exceptions.
- Do NOT inflate M because some good studies exist.

### 5.3 Claim vs. Mechanism

Some claims assert a **mechanism** ("via the PI3K/AKT pathway") while others assert an **outcome** ("reduces tumor growth"). Score what is explicitly claimed. Mechanistic claims often have lower M unless the mechanism was directly tested.

### 5.4 Known False Claims

Claims that are known to be false (refuted findings):
- R: < 0.3 (replication attempts failed)
- C: < 0.3 (if absolutist, overreach)
- M: < 0.4 (if the refutation came from better-designed studies)

---

## 6. Annotation Workflow

### 6.1 Per-Claim Process (estimated 5–8 minutes/claim)

1. **Read the claim** and its domain context.
2. **Identify evidence sources** — Use provided PMIDs or your domain knowledge.
3. **Determine X applicability** — Is multi-omics involved? If no, mark X = NULL.
4. **Score each axis independently.** Do NOT look at other annotators' scores.
5. **Write brief reasoning** (1–2 sentences) per axis using this format:
   - *"R=0.65: Replicated by [Author] et al. [Year] in [context], but not yet in [other context]."*
6. **Flag if uncertain** — Use the `uncertain` column to flag any axis where you are unsure.

### 6.2 Corpus Format

The claim corpus CSV has these columns:

| Column | Description |
|--------|-------------|
| `claim_id` | Unique identifier (e.g., `SB-001`, `CG-001`, `NS-001`) |
| `domain` | `spaceflight_biology`, `cancer_genomics`, `neuroscience` |
| `claim_text` | The exact biological claim to score |
| `context` | 1–3 sentence context (paper, year, organism) |
| `pmids` | Comma-separated PMIDs of source papers |
| `R_score` | 0.0–1.0 |
| `C_score` | 0.0–1.0 |
| `M_score` | 0.0–1.0 |
| `X_score` | 0.0–1.0 or `NULL` |
| `T_score` | 0.0–1.0 |
| `R_reasoning` | Free text |
| `C_reasoning` | Free text |
| `M_reasoning` | Free text |
| `X_reasoning` | Free text (or `"N/A — single omics"`) |
| `T_reasoning` | Free text |
| `uncertain` | Comma-separated axes where annotator was uncertain (e.g., `R,X`) |
| `notes` | Any other comments |

---

## 7. Worked Examples

### Example 1: Spaceflight Biology

**Claim:** "Long-duration spaceflight causes a ~54% increase in red blood cell hemolysis, resulting in space anemia."

| Axis | Score | Reasoning |
|------|-------|-----------|
| R | 0.55 | Confirmed by Trudel et al. (Nature Medicine, 2022) and the NASA Twin Study (Garrett-Bakelman et al. 2019). Two independent groups, but sample sizes remain small (n < 20). |
| C | 0.50 | Observed in ISS long-duration missions (≥6 months) in healthy adults. Whether shorter missions or different gravitational environments (e.g., lunar) show the same effect is unknown. |
| M | 0.60 | Trudel et al. used stable isotope breath tests (validated methodology), prospective design, 14 astronauts. Adequate for small-n physiology but not large-cohort powered. |
| X | 0.65 | Genomic (hemolysis pathway upregulation), proteomic (hemopexin, bilirubin), and metabolomic (carboxyhemoglobin) data partially concordant across omics. |
| T | 0.40 | First formally quantified by Trudel 2022 — recent finding, no 5-year follow-up data yet. |

**Composite:** 0.30×0.55 + 0.20×0.50 + 0.25×0.60 + 0.15×0.65 + 0.10×0.40 = **0.545**

---

### Example 2: Cancer Genomics

**Claim:** "KRAS G12C mutation renders NSCLC sensitive to sotorasib."

| Axis | Score | Reasoning |
|------|-------|-----------|
| R | 0.80 | Phase I/II CodeBreaK100 trial (Skoulidis et al. NEJM 2021), Phase III CodeBreaK200 (de Langen et al. NEJM 2023), FDA approved 2021. Multiple independent clinical trials. |
| C | 0.70 | Specific to KRAS G12C (not other KRAS variants). Effective in NSCLC. Less clear benefit in colorectal cancer (lower response rate confirmed). |
| M | 0.90 | Phase III randomized controlled trial, pre-registered, regulatory-standard endpoints. |
| X | NULL | Clinical drug sensitivity data; not multi-omics. |
| T | 0.65 | Emerged 2020–2021; 3 years of follow-up data now available with consistent results, but long-term resistance mechanisms emerging. |

**Composite (X = NULL, renormalized):** (0.30×0.80 + 0.20×0.70 + 0.25×0.90 + 0.10×0.65) / (1 - 0.15) ≈ **0.823**

---

### Example 3: Neuroscience

**Claim:** "Adult hippocampal neurogenesis declines substantially in humans after age 13."

| Axis | Score | Reasoning |
|------|-------|-----------|
| R | 0.30 | Sorrells et al. (Nature 2018) found negligible neurogenesis in adults. But Boldrini et al. (Cell Stem Cell 2018) found continued neurogenesis. Studies use different methods, contradictory. |
| C | 0.40 | Even within humans, method-dependence (immunohistochemistry with different antibodies) makes generalizability uncertain. |
| M | 0.35 | Post-mortem tissue with variable fixation quality; antibody specificity disputed; small n (n=17–28). |
| X | NULL | Histology + immunohistochemistry only; not multi-omics. |
| T | 0.35 | Actively contested 2018–2024; interpretation has shifted significantly. Not yet resolved. |

**Composite (X = NULL):** (0.30×0.30 + 0.20×0.40 + 0.25×0.35 + 0.10×0.35) / 0.85 ≈ **0.340**

---

## 8. Inter-Rater Reliability Protocol

### IRR Calculation Method

We will use **Intraclass Correlation Coefficient ICC(2,k)** (two-way random effects, absolute agreement) per axis. Target: ICC > 0.60 per axis.

If ICC < 0.50 on any axis after the pilot round:
1. Discussion round: annotators compare scores for disagreed claims.
2. Guideline refinement based on systematic disagreements.
3. Re-score the 10 pilot claims.

### Pilot Round (10 claims)

Before scoring all 150 claims, all annotators complete a **10-claim pilot round** using this subset. Pilot results will be shared to calibrate before the full annotation.

The pilot set includes:
- 3 high-consensus claims (expected ICC > 0.8)
- 4 medium-consensus claims (expected ICC 0.5–0.7)
- 3 adversarial claims (known disagreement traps)

---

## 9. Ethics and Data Handling

- All paper abstracts and titles come from public databases (PubMed, PMC OA).
- No patient-level data is involved.
- Annotation data will be used for scientific publication and open-source release.
- Annotators will be acknowledged in publications and may be listed as co-authors depending on contribution.

---

## 10. Quick Reference Card

```
RCMXT Scoring Quick Reference

R (Reproducibility)      C (Condition Spec.)    M (Methodology)
0.1 = No replication     0.1 = 1 system/wrong   0.1 = No peer review
0.3 = Same-lab only      0.3 = Narrow scope      0.3 = Small n, no ctrl
0.5 = 2-3 groups, mixed  0.5 = 2-3 contexts     0.5 = Published, limited
0.7 = Multiple, consist. 0.7 = Multi-species    0.7 = Good design
0.9 = Textbook fact      0.9 = Universal law    0.9 = Gold-standard RCT

X (Cross-Omics)          T (Temporal Stability)
NULL = Single modality   0.1 = <2yr, no follow-up
0.1  = Active conflict   0.3 = Contested/revised
0.5  = Mixed             0.5 = 5-10yr, consistent
0.9  = Strong concordance 0.7 = 10+yr, consistent
                         0.9 = Decades, untouched
```
