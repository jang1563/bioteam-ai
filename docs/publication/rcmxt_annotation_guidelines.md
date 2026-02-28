# RCMXT Evidence Confidence Annotation Guidelines

**Version:** 1.0 (2026-02-28)
**Study:** BioTeam-AI — LLM Evidence Scoring Calibration
**PI:** JangKeun Kim, Weill Cornell Medicine
**Contact:** [your email]

---

## Introduction

This document provides instructions for **domain expert annotators** participating in the RCMXT calibration study. You will independently score a set of biological claims across five evidence-quality axes. Your scores serve as the **human expert ground truth** for evaluating BioTeam-AI's automated evidence confidence framework.

**What you will do:**
- Read each claim independently (no web search — score from expert memory)
- Score the claim on five axes (R, C, M, X, T) using 0.0–1.0 continuous scales
- Mark X as **Not Applicable (N/A)** if only one data modality is involved
- Write a 1–3 sentence rationale for your scores

**Estimated time:** 3–5 minutes per claim × 30 assigned claims ≈ 2–3 hours total

---

## The RCMXT Framework

RCMXT scores **evidence quality and generalizability**, not whether a claim is interesting or important. A claim can be highly reliable (high scores) but narrow in scope, or highly generalizable but poorly supported. The framework captures five orthogonal dimensions:

| Axis | Name | Question |
|------|------|----------|
| **R** | Reproducibility | How many independent groups have confirmed this? |
| **C** | Condition Specificity | How broadly does this generalize across contexts? |
| **M** | Methodological Robustness | How strong are the study designs? |
| **X** | Cross-Omics Concordance | Do multiple data layers agree? (N/A if single-omics) |
| **T** | Temporal Stability | Is this finding consistent over time? |

**Key principle:** Score what the *evidence actually supports*, not what *should* be true or what is theoretically plausible. A well-replicated finding with limited generalizability should receive high R and low C — this is not a contradiction.

---

## Axis R — Reproducibility (0.0–1.0)

### Definition
The fraction of independent research groups and contexts in which this finding has been confirmed. Reproducibility measures whether other labs can obtain the same result, not whether the underlying mechanism is understood.

### Scoring Rubric

| Score | Interpretation |
|-------|----------------|
| 0.0–0.20 | **No independent replication.** Single study, single lab. Preprint-only or conference abstract. May be contradicted by subsequent work. |
| 0.20–0.40 | **Minimal replication.** One partial replication, or same-lab repeat. Small n. Finding not yet independently confirmed. |
| 0.40–0.60 | **Emerging consensus.** 2–3 independent groups, partial agreement. Some contradictory reports exist. |
| 0.60–0.80 | **Established finding.** Multiple independent replications with consistent results. Minor methodological disagreements may exist. |
| 0.80–1.00 | **Textbook-level.** Replicated across many labs, species, and conditions over decades. Foundational to the field. |

### Anchor Examples

**LOW (R = 0.15):**
> *"Parkinson's disease motor symptoms are caused exclusively by dopaminergic neuron loss in the substantia nigra pars compacta, and complete symptom control can be achieved by dopamine replacement therapy alone, with no involvement of non-dopaminergic systems in disease manifestation."*

Score R = 0.15 because this absolutist framing is **contradicted** by extensive replication studies. While dopaminergic loss is primary, non-dopaminergic pathology (locus coeruleus, raphe nuclei, nucleus basalis) is independently replicated across numerous labs. The claim's "exclusively" and "complete control" language is demonstrably false across the literature.

---

**MEDIUM (R = 0.55):**
> *"Cell-free RNA (cfRNA) profiles in astronaut blood plasma can distinguish pre-flight, in-flight, and post-flight physiological states with distinct temporal signatures."*

Score R = 0.55 because this is an **emerging finding** with support from JAXA and SpaceX Inspiration4 mission data (Overbey et al., 2024, *Nature*), but sample sizes are small (n=4 for Inspiration4). The overall direction is consistent but insufficient independent replication to be considered established.

---

**HIGH (R = 0.95):**
> *"APOE4 is the strongest genetic risk factor for late-onset Alzheimer's disease, increasing risk 3–4 fold for heterozygous carriers and 8–15 fold for homozygous carriers."*

Score R = 0.95 because this is **among the most replicated findings** in neurogenetics. Identified by Corder et al. (1993, *Science*) and confirmed across dozens of GWAS and cohort studies globally. Risk magnitude is consistent across populations (with known ethnic variation). Independently replicated in genetics, neuropathology, neuroimaging, and CSF biomarker studies.

### Common Mistakes
- **Don't score R based on the claim's importance.** A trivial but well-replicated finding gets high R; a pivotal but unreplicated finding gets low R.
- **Don't factor mechanism into R.** Mechanism can be unknown while the phenomenological observation is highly replicated (e.g., aspirin prevents cardiovascular events was replicated before the mechanism was understood).

---

## Axis C — Condition Specificity (0.0–1.0)

### Definition
How broadly the finding generalizes across biological contexts (cell types, species, conditions, experimental systems). Higher scores indicate **broader generalizability**. Lower scores indicate the finding is narrow, context-dependent, or applies only under specific circumstances.

> **Important:** Low C is not inherently bad. A finding that is specifically true for a single cell type under defined conditions can be highly valuable — it should receive a low C score without implying the finding is wrong or unimportant.

### Scoring Rubric

| Score | Interpretation |
|-------|----------------|
| 0.0–0.20 | **Narrow/absolutist failure.** Finding applies to a single cell line or experimental condition. OR the claim uses absolutist language ("always", "universally") that is demonstrably incorrect. |
| 0.20–0.40 | **Highly context-specific.** Observed under narrow conditions (one organism, one cell type, one disease subtype). Generalizability unknown or unlikely. |
| 0.40–0.60 | **Partially generalizable.** Confirmed in 2–3 biological contexts. Significant exceptions or caveats exist. Important moderating variables known. |
| 0.60–0.80 | **Broadly generalizable.** Consistent across multiple species, tissues, or conditions. Known caveats documented but do not undermine the core finding. |
| 0.80–1.00 | **Fundamental biological principle.** Holds across all or nearly all relevant biological contexts. Cell biology dogma, evolutionary conservation across all eukaryotes, etc. |

### Anchor Examples

**LOW (C = 0.05):**
> *"Tumor genomic profiling by next-generation sequencing has completely replaced traditional histopathology in cancer diagnosis."*

Score C = 0.05 because the absolutist claim ("completely replaced") is **false across virtually all clinical contexts**. Histopathology remains the diagnostic gold standard in all major cancer types. The absolutist framing makes the claim inapplicable to real clinical settings.

---

**MEDIUM (C = 0.55):**
> *"Spaceflight induces a hemolytic anemia phenotype characterized by elevated carbon monoxide production and increased red blood cell destruction."*

Score C = 0.55 because this finding is confirmed in **ISS astronauts on 6-month missions** (Trudel et al., 2022, *Nature Medicine*), but it may not generalize to shorter missions, sub-orbital flight, or lunar surface gravity (~1/6 g). The condition is inherently specific to orbital microgravity and may have individual variation not yet characterized across diverse populations.

---

**HIGH (C = 0.75):**
> *"TP53 is the most frequently mutated gene across human cancers, with somatic mutations detected in approximately 50% of all cancer types."*

Score C = 0.75 because TP53 mutation is confirmed **across all major solid tumor types** (TCGA Pan-Cancer Atlas; PCAWG Consortium). The finding generalizes broadly across histological subtypes, tissues of origin, and patient populations. Caveats: some hematological malignancies have lower rates; frequency varies by cancer subtype (near 100% in high-grade serous ovarian cancer, ~15% in papillary thyroid cancer).

### Common Mistakes
- **Don't confuse C with whether the claim is correct.** A narrow finding (e.g., a specific splice variant of gene X is overexpressed in a specific lymphoma subtype) should get low C regardless of its scientific validity.
- **Watch for absolutist language** ("always", "completely", "universally") — these typically drop C to 0.0–0.2 regardless of underlying truth.

---

## Axis M — Methodological Robustness (0.0–1.0)

### Definition
The quality and rigor of the study designs supporting the claim. This includes sample size, controls, statistical power, peer review status, experimental design, and whether results are validated with multiple orthogonal methods.

### Scoring Rubric

| Score | Interpretation |
|-------|----------------|
| 0.0–0.20 | **No peer review or clearly flawed.** Preprint-only, no methods described, obvious design flaws, data fabrication suspected, or claim contradicted by better-designed subsequent work. |
| 0.20–0.40 | **Weak methodology.** Published but serious limitations: very small n (<5 biological replicates for animal studies, <20 for human studies), no controls, single timepoint, non-validated assays. |
| 0.40–0.60 | **Adequate but limited.** Published in peer-reviewed journals. Methods are valid but statistical power is limited. Single-lab validation. Some confounders acknowledged but not fully addressed. |
| 0.60–0.80 | **Well-designed studies.** Proper controls, adequate sample sizes, validated methods, statistical rigor, multivariate analysis of confounders. Results replicated with orthogonal methods. |
| 0.80–1.00 | **Gold-standard methodology.** Pre-registered study designs, multi-site validation, randomized controlled trials (where applicable), systematic reviews with meta-analysis, ENCODE/TCGA-scale consortium data. |

### Anchor Examples

**LOW (M = 0.25):**
> *"Cosmic ray-induced carcinogenesis risk in astronauts can be fully mitigated by polyethylene shielding in spacecraft habitat modules."*

Score M = 0.25 because the supporting evidence comes from **ground-based accelerator simulations** (not actual spaceflight), small laboratory studies, and modeling. Polyethylene shields against solar protons but not high-Z, high-energy (HZE) galactic cosmic rays. No human clinical data exists; claim extrapolates beyond experimental evidence.

---

**MEDIUM (M = 0.55):**
> *"Circulating cell-free mitochondrial DNA (cf-mtDNA) levels are elevated in astronaut blood during spaceflight compared to pre-flight baselines."*

Score M = 0.55 because supporting data exists from **Inspiration4 and limited ISS studies** using well-validated cf-mtDNA quantification methods. However, sample sizes are small (n=4–14 astronauts), and confounders including stress, sleep disruption, and exercise changes are hard to dissociate from microgravity effects specifically. RNA-seq pipelines are methodologically sound; the spaceflight-specific interpretation is less certain.

---

**HIGH (M = 0.90):**
> *"TP53 is the most frequently mutated gene across human cancers, with somatic mutations detected in approximately 50% of all cancer types."*

Score M = 0.90 because this rests on **large-scale consortium sequencing** (TCGA: >10,000 tumor samples; PCAWG: >2,600 whole genomes) using validated bioinformatics pipelines and orthogonal validation across cohorts. Multi-site, multi-platform, independently analyzed. Represents the highest standard for genomic epidemiology.

### Common Mistakes
- **M is about the supporting evidence, not the claim's plausibility.** A mechanistically plausible claim supported only by a single n=3 mouse study gets low M.
- **Don't average up for large sample size alone.** Big data with systematic bias (e.g., survivor bias, lack of controls) should not automatically score high M.

---

## Axis X — Cross-Omics Concordance (0.0–1.0 or **N/A**)

### Definition
When multiple omics data types (e.g., transcriptomics + proteomics + metabolomics + genomics) or orthogonal measurement modalities are available, how well do they agree? This axis is **only scored when the claim explicitly involves or implies multi-omics data.** For single-omics findings, clinical measurements, behavioral data, or imaging studies, mark X as **N/A**.

> **Critical rule:** When in doubt, mark N/A. It is always better to mark N/A than to assign an arbitrary 0.5 for an axis that does not apply.

### Scoring Rubric

| Score | Interpretation |
|-------|----------------|
| **N/A** | Single-omics, clinical measurements, imaging, behavioral studies. Only one data modality available or claimed. |
| 0.0–0.30 | **Active contradiction.** Multi-omics data exists but different layers give conflicting signals (e.g., transcript upregulated but protein downregulated with no explanation). |
| 0.30–0.50 | **Mixed or inconclusive.** Multi-omics data is inconsistent across studies or layers. Discordance noted but not explained. |
| 0.50–0.70 | **Partial concordance.** At least 2 omics layers agree on direction but effect sizes or specifics differ. |
| 0.70–1.00 | **Strong concordance.** Multiple independent omics layers (3+) agree on direction and general magnitude. Findings are mutually reinforcing. |

### N/A Examples (these should NOT receive an X score)

> *"Spaceflight induces hemolytic anemia characterized by elevated carbon monoxide production and increased red blood cell destruction."*
→ **X = N/A.** This is a hematological/metabolic finding (CBC, CO breath analysis). Single measurement modality; no multi-omics component.

> *"Microgravity exposure causes bone mineral density loss at approximately 1–2% per month in the proximal femur."*
→ **X = N/A.** DEXA scan measurement. Single modality; no omics component.

### Applicable Examples

**LOW (X = 0.50):**
> *"Spaceflight causes epigenetic changes including altered DNA methylation patterns that persist after return to Earth."*

Score X = 0.50 because methylation data (bisulfite sequencing) and some functional genomics exist, but concordance with gene expression changes is **partial and inconsistent** across studies. The direction of methylation changes is reported but the functional consequences (transcriptional impact) are not consistently confirmed by RNA-seq data.

---

**MEDIUM-HIGH (X = 0.75):**
> *"Mitochondrial dysfunction is a convergent molecular pathway across multiple tissues in spaceflight biology."*

Score X = 0.75 because transcriptomic, proteomic, and metabolomic data from multiple spaceflight studies **converge** on mitochondrial pathway perturbations (Ludtka et al., 2021; Garrett-Bakelman et al., 2019). Different omics layers independently flag similar pathways, though the specific genes/proteins involved vary by tissue.

### Common Mistakes
- **Do not assign X = 0.5 as a "don't know" answer.** Use N/A when the claim does not involve multi-omics data.
- **X does not measure whether the finding is important.** A single-technology finding that is perfectly reproducible still gets N/A.
- **"Multi-omics" requires different types of molecular data, not just multiple studies using the same assay.** Five RNA-seq studies = N/A (single-omics). One RNA-seq + one proteomics + one metabolomics = applicable.

---

## Axis T — Temporal Stability (0.0–1.0)

### Definition
How consistently this finding has held over time, across publications, and through methodological evolution. High T means the finding has been repeatedly confirmed over years/decades as technologies improved. Low T means the finding is very recent, has been contradicted by subsequent work, or its interpretation has shifted significantly.

### Scoring Rubric

| Score | Interpretation |
|-------|----------------|
| 0.0–0.20 | **Very recent or contradicted.** Published within last 2 years with no follow-up. OR finding was once accepted but has since been contradicted by better-powered studies. |
| 0.20–0.40 | **Recent with limited follow-up.** Published 2–5 years ago. Some confirmatory studies exist but the finding has not been tested across the full range of relevant conditions. OR interpretation has shifted significantly since initial publication. |
| 0.40–0.60 | **Established within last decade.** 5–10 year-old finding with consistent replication. Methods have evolved but finding has survived methodological scrutiny. |
| 0.60–0.80 | **Mature finding (10+ years).** Consistent support spanning at least one cycle of major technological change. May have been refined but core finding is stable. |
| 0.80–1.00 | **Decades-old, time-tested.** Withstood multiple technological revolutions (pre-molecular → molecular → genomic → single-cell → spatial). Increasingly confirmed with each methodological advance. |

### Anchor Examples

**LOW (T = 0.10):**
> *"Tumor genomic profiling by next-generation sequencing has completely replaced traditional histopathology in cancer diagnosis."*

Score T = 0.10 because this claim **misrepresents current clinical practice** and was never accurately true. While NGS panels have become standard of care in many cancers since ~2015, they complement rather than replace histopathology. The claim's framing would have been contradicted immediately upon publication.

---

**MEDIUM (T = 0.55):**
> *"Spaceflight causes a shift in the immune system toward a pro-inflammatory state, with elevated cytokines including IL-6 and IL-8 during and immediately after orbital missions."*

Score T = 0.55 because the general theme of immune dysregulation in spaceflight has been studied since the 1970s, but specific cytokine profiles have evolved with better measurement technology (Crucian et al., 2015; Stowe et al., 2011). The pro-inflammatory interpretation is broadly consistent but **specific cytokine elevations have shown variability** across missions, with some more recent data suggesting the picture is more nuanced.

---

**HIGH (T = 0.90):**
> *"APOE4 is the strongest genetic risk factor for late-onset Alzheimer's disease, increasing risk 3–4 fold for heterozygous carriers and 8–15 fold for homozygous carriers."*

Score T = 0.90 because this finding was established by Corder et al. in **1993** and has been consistently confirmed across 30+ years of subsequent GWAS, cohort studies, biomarker research, and mechanistic studies. Each new methodological advance (microarray, sequencing, PET imaging, CSF biomarkers) has further confirmed and refined the relationship, not contradicted it. Risk magnitude estimates have been refined (ethnic variation documented) but the core finding is unshaken.

### Common Mistakes
- **Don't confuse T with historical interest.** A finding discovered in 1950 that has since been contradicted should get low T.
- **T reflects the stability of the finding, not the stability of the mechanistic explanation.** The mechanistic understanding of LTP has evolved considerably while the phenomenological finding (NMDA-dependent LTP at CA3-CA1 synapses) has remained stable for 40+ years.

---

## Handling Difficult Cases

### Negative Control Claims
The benchmark includes deliberately **incorrect or overstated claims** (marked `difficulty: negative_control`). These often use absolutist language ("completely replaced", "exclusively caused by", "fully mitigated"). Score them as you would any claim — if the evidence contradicts the claim, scores should reflect that (typically low R, low C, low M, low T).

### Partially True Claims
Many real biological claims are partially correct — true under certain conditions but overstated. Score the axes independently:
- R: Has the core finding been replicated?
- C: Under what range of conditions is the core finding true?
- M: What is the evidence quality for the true portion?
- X: Does multi-omics data agree with the true portion?
- T: How long has the finding been consistent?

### Claims at the Edge of Your Expertise
**Score within your domain.** If a claim is outside your area of expertise, note this in the rationale and provide your best estimate. The study includes claims from three domains (spaceflight biology, cancer genomics, neuroscience); you are assigned claims within your stated expertise area.

### Claims With Uncertain X
When unsure whether multi-omics data is available:
- Default to **N/A** if the claim does not explicitly reference multiple data types
- If you know that multi-omics data exists even though the claim doesn't mention it, you may score X based on that knowledge and note it in your rationale

---

## Annotator Worksheet Format

For each claim, provide:

```
CLAIM ID: [e.g., claim_042]
CLAIM TEXT: [copy the claim text]

R SCORE: [0.00–1.00]
C SCORE: [0.00–1.00]
M SCORE: [0.00–1.00]
X SCORE: [0.00–1.00 or N/A]
T SCORE: [0.00–1.00]

RATIONALE:
[1–3 sentences explaining your scores, citing key supporting or contradicting studies if known]

CONFIDENCE IN YOUR SCORES: [High / Medium / Low]
```

---

## Inter-Rater Reliability Protocol

Each claim is independently scored by **3 domain experts**. Scores will be compared using:

- **Intraclass Correlation Coefficient (ICC)** across annotators per axis
- **Weighted Cohen's κ** for quartile-binned scores
- Claims with ICC < 0.60 or any pairwise axis discrepancy > 0.35 will be **flagged for adjudication**

During adjudication, disagreeing annotators discuss their rationale. If consensus is not reached, the claim is **excluded from calibration analysis** (not scored zero — excluded).

**Target:** ICC ≥ 0.75 per axis across annotators before the dataset is used for model calibration.

---

## Data Handling and Consent

- Your scores will be stored in the BioTeam-AI research database, identified by your annotator ID (not name)
- De-identified scores may appear in publications describing the RCMXT calibration study
- You may withdraw your scores at any time before data analysis begins by contacting the PI
- This annotation task qualifies as a quality improvement/education activity — an IRB determination of non-human-subjects research is pending (Weill Cornell IRB)

---

## Quick Reference Card

| Axis | 0.0 | 0.5 | 1.0 |
|------|-----|-----|-----|
| **R** | Never replicated | ~3 independent replications | Textbook, decades of replication |
| **C** | Single cell line; absolutist falsehood | Applies in 2–3 contexts with caveats | Fundamental biological principle |
| **M** | Preprint, n<5, no controls | Published, adequate design, limited power | RCT / consortium-scale, pre-registered |
| **X** | Multi-omics contradict each other | Partial concordance, some gaps | 3+ omics layers strongly agree |
| **T** | <2 years or actively contradicted | 5–10 years, refined but stable | 30+ years, confirmed through tech revolutions |

**When to mark X = N/A:** Any claim involving only one data modality (single-omics, imaging, clinical labs, behavioral data, animal physiology).

---

*Document version 1.0 — Questions? Contact JangKeun Kim ([contact info])*
