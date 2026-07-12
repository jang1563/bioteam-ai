# Annotation Guidelines: Contradiction Taxonomy Corpus
**Version:** 1.0
**Date:** 2026-03-02
**Project:** BioTeam-AI — Paper 2 (Bioinformatics)
**Contact:** JangKeun Kim, Weill Cornell Medicine

---

## 1. Introduction

This document guides you through annotating 150 pairs of biomedical claims as part of a study on contradictions in the scientific literature. Your annotations will be used to:

1. Build a ground-truth corpus of 150 labeled contradiction pairs (across 3 domains: spaceflight biology, cancer genomics, neuroscience)
2. Measure inter-annotator agreement (Cohen's kappa) to validate the taxonomy
3. Evaluate an automated contradiction detection system (BioTeam-AI W6)

**Your contribution** will be published as supplementary material for a peer-reviewed paper targeting the journal *Bioinformatics*. Annotators who complete ≥ 80% of entries are offered **acknowledgment** in the paper; those contributing ≥ 50% of the total annotation effort (as a second full annotator) may be offered **co-authorship** at the corresponding author's discretion.

**Time estimate:** Approximately 3–4 hours for 150 entries (~90 seconds per entry on average). You may complete the annotation across multiple sessions; progress is saved automatically in the Google Sheet.

---

## 2. Task Definition

### What you are annotating

Each row in the annotation sheet contains **two scientific claims** (Claim A and Claim B) drawn from different published papers. The claims address the same biological phenomenon (e.g., the same gene, pathway, or disease context) but appear to report different or opposing findings.

Your job is to:
1. Read both claims carefully
2. Decide whether this is a **genuine contradiction** (two claims that cannot both be true under the same conditions) or a **non-genuine difference** (an apparent conflict that disappears once context is accounted for)
3. If genuine, classify the **type** of contradiction using the five-category taxonomy defined in Section 3
4. Rate your **confidence** (High / Medium / Low)

### Genuine vs. non-genuine contradiction

A **genuine contradiction** means:
> Two independent scientific groups, studying the same phenomenon under comparable conditions, reached opposite or incompatible conclusions.

A **non-genuine difference** means:
> The two claims appear to conflict, but the conflict disappears once you account for the specific conditions of each study (different species, different assays, different time points, etc.). The two claims can both be true simultaneously.

**Rule of thumb:** If you can explain why *both* claims are correct by pointing to a specific difference in experimental context, it is likely non-genuine. Mark `is_genuine = No`.

**Example of non-genuine:**
- Claim A: "VEGF is upregulated in rat skeletal muscle after 7 days of hindlimb unloading."
- Claim B: "VEGF expression is unchanged in human vastus lateralis after 60-day bed rest."
→ Different species (rat vs human) and different model (hindlimb suspension vs bed rest). Both can be true. Mark `is_genuine = No`.

**Example of genuine:**
- Claim A: "KRAS G12C promotes cell proliferation by activating PI3K/AKT in A549 cells."
- Claim B: "KRAS G12C suppresses AKT phosphorylation in A549 cells, limiting proliferation."
→ Same cell line, same oncogenic variant, opposite claim about AKT. Mark `is_genuine = Yes`.

---

## 3. The Five Contradiction Types

Once you determine a pair is genuinely contradictory (`is_genuine = Yes`), assign **exactly one** of the five types below. Use the decision tree in Section 4 to make the assignment systematic.

---

### Type 1: DIRECT

**Definition:** The two claims address the same biological phenomenon under the same experimental conditions and reach opposite, incompatible conclusions. No contextual difference explains the discrepancy.

**Characteristics:**
- Same organism / species
- Same tissue, cell line, or cell type
- Same experimental intervention or disease model
- Opposite direction of effect (increase vs. decrease; activation vs. inhibition; present vs. absent)
- No methodological or temporal difference that could account for the discrepancy

**What it is NOT:**
- Do not use DIRECT if the conditions differ even slightly in a way that could biologically explain the difference (use CONTEXTUAL or METHODOLOGICAL instead)
- Do not use DIRECT if the effect size differs but the direction is the same (use MAGNITUDE)

**Example:**
- Claim A: "Spaceflight causes a significant decrease in erythropoietin (EPO) secretion in astronauts during 6-month ISS missions."
- Claim B: "Circulating EPO levels are elevated in astronauts during the first 3 months of long-duration spaceflight."

Here: same population (astronauts), same model (ISS long-duration), same measurement (EPO), but timing partially differs (full mission vs. first 3 months). *Note: This borderline example would actually be classified as TEMPORAL because time point differs — see Section 5, Example 1.*

**Cleaner Direct example:**
- Claim A: "BRCA1 heterozygous mouse mammary gland cells show a 3-fold increase in homologous recombination efficiency."
- Claim B: "Loss of one BRCA1 allele does not alter homologous recombination rates in murine mammary epithelium."
→ Same species, same tissue, same allelic state, same assay (homologous recombination), opposite conclusion.

---

### Type 2: CONTEXTUAL

**Definition:** The two claims appear contradictory but arise from different biological contexts — different species, different tissues, different disease subtypes, or different patient populations. The difference in context is sufficient to explain why both claims can be true.

**Characteristics:**
- Different organism, cell line, tissue, disease subtype, or patient cohort
- The biological context difference is a plausible explanation for the different outcome
- If the context were equalized, the claims might agree

**What it is NOT:**
- Do not use CONTEXTUAL if the conditions are the same but the assay is different (use METHODOLOGICAL)
- Do not use CONTEXTUAL if both studies use the same context but different time points (use TEMPORAL)

**Example:**
- Claim A: "TP53 R175H gain-of-function mutation promotes invasion in colon cancer cell lines."
- Claim B: "TP53 R175H does not enhance invasive capacity in glioblastoma-derived cell lines."
→ Different tumor type (colon vs. glioblastoma). This is CONTEXTUAL.

---

### Type 3: METHODOLOGICAL

**Definition:** The two claims address the same phenomenon in the same biological context but differ in their measurement approach (assay, instrument, antibody, computational pipeline, etc.). The methodological difference is the primary explanation for the discrepancy.

**Characteristics:**
- Same organism, cell type, and conditions
- Different measurement technology, antibody/reagent, or analytical pipeline
- The discrepancy is most plausibly explained by assay characteristics (sensitivity, specificity, off-target effects)

**What it is NOT:**
- Do not use METHODOLOGICAL if the biological context also differs substantially (use CONTEXTUAL first)
- Do not use METHODOLOGICAL if both methods are measuring the same thing but the difference is in how data were analyzed (e.g., different statistical thresholds with the same raw data)

**Example:**
- Claim A: "Tau phosphorylation at Ser396 is elevated 2-fold in AD patient hippocampal lysates measured by Western blot with PHF-1 antibody."
- Claim B: "Mass spectrometry quantification of Ser396 phosphorylation shows no significant elevation in the same AD patient cohort."
→ Same cohort, same tissue, different method (Western blot vs. mass spectrometry). METHODOLOGICAL.

---

### Type 4: TEMPORAL

**Definition:** The two claims study the same phenomenon but at different time points, developmental stages, or disease progression phases. The temporal difference explains why both can be true (the biology changes over time).

**Characteristics:**
- Same biological system (organism, cell type, disease model)
- Same measurement approach
- Different time point, age, treatment duration, or disease stage
- The temporal difference is a biologically plausible explanation for the discrepancy

**What it is NOT:**
- Do not use TEMPORAL if the time difference is incidental and unlikely to affect the biological outcome
- Do not use TEMPORAL if the directions are the same and only magnitude differs (use MAGNITUDE)

**Example:**
- Claim A: "VEGF secretion by astrocytes increases 4-fold within 6 hours of ischemic injury."
- Claim B: "VEGF levels in ischemic brain tissue return to baseline by 48 hours post-injury."
→ Same model (ischemia), same cell/tissue, same molecule, but different time points. TEMPORAL.

---

### Type 5: MAGNITUDE

**Definition:** The two claims agree on the direction of effect (both show increase, or both show decrease) but disagree substantially on the magnitude or statistical significance. One paper reports a large, significant effect; the other reports a negligible or non-significant effect in the same direction.

**Characteristics:**
- Same biological context (organism, cell type, conditions)
- Same direction of effect (both "increases" or both "decreases")
- Contradictory magnitude: e.g., 50% vs. 3%; p<0.001 vs. p=0.45
- The discrepancy is in *how much* rather than *which way*

**What it is NOT:**
- Do not use MAGNITUDE if the directions differ (use DIRECT, CONTEXTUAL, METHODOLOGICAL, or TEMPORAL)
- Do not use MAGNITUDE for trivial variation within normal experimental noise

**Example:**
- Claim A: "Sunitinib treatment reduces tumor volume by 78% in mouse xenograft models of clear cell RCC."
- Claim B: "Sunitinib reduces xenograft tumor growth by 12% in the same RCC model, with the effect not reaching statistical significance."
→ Both report reduction (same direction), but 78% vs. 12% and significant vs. not significant. MAGNITUDE.

---

## 4. Decision Tree

Use these six questions in order to assign the type. **Stop at the first question that gives you a definitive answer.**

```
START
  │
  Q1. Do both claims use the same biological system?
      (Same species + same cell line/tissue type + same disease model)
      │
      ├── NO ──────────────────────────────────────► CONTEXTUAL
      │
      └── YES
            │
          Q2. Do both claims use the same measurement method/assay?
              (Same antibody, same sequencing platform, same imaging technique)
              │
              ├── NO ──────────────────────────────► METHODOLOGICAL
              │
              └── YES
                    │
                  Q3. Do both claims examine the same time point or
                      developmental/disease stage?
                      │
                      ├── NO ──────────────────────► TEMPORAL
                      │
                      └── YES
                            │
                          Q4. Do the claims report OPPOSITE directions?
                              (one "increases" / other "decreases";
                               one "promotes" / other "inhibits";
                               one "present" / other "absent")
                              │
                              ├── NO
                              │     │
                              │   Q5. Does one report statistical significance,
                              │       the other not, for the same direction?
                              │       (or: is the effect size contradictory
                              │        e.g. 60% vs 5%?)
                              │       │
                              │       ├── YES ──────► MAGNITUDE
                              │       │
                              │       └── NO ───────► NOT GENUINE
                              │                        (mark is_genuine = No)
                              │
                              └── YES
                                    │
                                  Q6. Is the specific experimental context
                                      clearly shared between the two papers?
                                      (Same lab protocol, same dose, same
                                       treatment duration, no hidden variation)
                                      │
                                      ├── YES ──────► DIRECT
                                      │
                                      └── NO ───────► Re-examine Q1
                                                       (hidden contextual diff?)
```

**Key guidance for Q6:** If you cannot identify a specific experimental difference but the two papers still seem to contradict each other, classify as DIRECT. Direct contradictions are the hardest for the scientific community to resolve and the most important to capture.

---

## 5. Worked Examples

The following ten examples are drawn from actual published literature. Read each carefully and trace through the decision tree before looking at the classification.

---

### Example 1 (DIRECT)

**Domain:** Cancer genomics
**Claim A:** "Sotorasib treatment of KRAS G12C-mutant NCI-H358 (NSCLC) cells at 1 µM for 72 hours results in >90% reduction in ERK1/2 phosphorylation, measured by Western blot with anti-pERK antibody (Cell Signaling #4370)."
**Claim B:** "Treatment of NCI-H358 cells with sotorasib (1 µM, 72 h) showed sustained ERK phosphorylation at 60–70% of untreated levels, as quantified by Western blot."

**Decision tree:**
- Q1: Same biological system? Yes — NCI-H358 cells
- Q2: Same assay? Yes — Western blot for pERK (same antibody catalog number)
- Q3: Same time point? Yes — 72 hours, 1 µM
- Q4: Opposite directions? Yes — >90% reduction vs. 60–70% of untreated = sustained
- Q6: Context fully shared? Yes — dose, duration, cell line, antibody all match

**Classification: DIRECT** ✓
**Why not MAGNITUDE?** The directions are genuinely opposite (near-complete loss vs. sustained activity), not just different magnitudes in the same direction.
**Common mistake:** Classifying as METHODOLOGICAL because the antibody dilutions might differ — resist this unless the paper actually states a different method.

---

### Example 2 (CONTEXTUAL)

**Domain:** Spaceflight biology
**Claim A:** "Murine soleus muscle shows a 40% reduction in slow-twitch (type I) fiber proportion after 30 days of hindlimb suspension."
**Claim B:** "Vastus lateralis biopsies from astronauts after 6-month ISS missions show no significant change in type I fiber proportion compared to pre-flight baseline."

**Decision tree:**
- Q1: Same biological system? No — mouse hindlimb suspension vs. human ISS mission (different species + different unloading model)

**Classification: CONTEXTUAL** ✓
**Why not DIRECT?** Species difference (mouse vs. human) and model difference (hindlimb suspension vs. real microgravity) are meaningful biological variables.
**Common mistake:** Assuming this is a genuine contradiction because both study "microgravity-induced muscle atrophy." Context matters.

---

### Example 3 (METHODOLOGICAL)

**Domain:** Neuroscience
**Claim A:** "Tau phosphorylation at Ser202/Thr205 (AT8 epitope) is elevated 3.2-fold in hippocampal homogenates from 3×Tg-AD mice at 12 months, detected by Western blot."
**Claim B:** "Quantitative mass spectrometry of hippocampal lysates from 12-month 3×Tg-AD mice reveals a non-significant 1.1-fold change in Ser202 phosphorylation compared to wild-type."

**Decision tree:**
- Q1: Same biological system? Yes — 3×Tg-AD mice, hippocampus, same age
- Q2: Same assay? No — Western blot (AT8 antibody) vs. mass spectrometry

**Classification: METHODOLOGICAL** ✓
**Why this matters for Paper 2:** Methodological contradictions often indicate assay-specific artifacts (e.g., AT8 antibody cross-reactivity) rather than true biological differences.

---

### Example 4 (TEMPORAL)

**Domain:** Spaceflight biology
**Claim A:** "Plasma EPO concentration increases by 35% during the first week of spaceflight in ISS crewmembers."
**Claim B:** "EPO levels in ISS astronauts are reduced to 70% of pre-flight baseline by mission month 3–6."

**Decision tree:**
- Q1: Same system? Yes — ISS astronauts
- Q2: Same assay? Yes — plasma EPO (ELISA)
- Q3: Same time point? No — first week vs. months 3–6

**Classification: TEMPORAL** ✓
**The biology:** EPO spikes early in spaceflight (acute neocytolysis response), then suppresses chronically. Both claims are correct at their respective time points.

---

### Example 5 (TEMPORAL)

**Domain:** Neuroscience
**Claim A:** "BDNF protein levels in the dentate gyrus are significantly elevated 24 hours after a single bout of voluntary wheel running in adult mice."
**Claim B:** "Chronic voluntary running for 6 weeks produces no significant change in dentate gyrus BDNF protein relative to sedentary controls."

**Decision tree:**
- Q1: Same system? Yes — adult mice, dentate gyrus
- Q2: Same assay? Yes — BDNF ELISA/Western blot
- Q3: Same time point? No — acute (24 h) vs. chronic (6 weeks)

**Classification: TEMPORAL** ✓
**Key insight:** Acute exercise boosts BDNF transiently; chronic exercise may trigger BDNF receptor upregulation that normalizes protein levels. Both findings can be true.

---

### Example 6 (CONTEXTUAL)

**Domain:** Cancer genomics
**Claim A:** "AMG 510 (sotorasib) treatment suppresses tumor growth by 80% in NCI-H358 NSCLC xenografts."
**Claim B:** "AMG 510 reduces SW1990 pancreatic ductal adenocarcinoma xenograft growth by only 18%, with partial responders showing rapid regrowth."

**Decision tree:**
- Q1: Same biological system? No — different cancer type (NSCLC vs. PDAC) and different cell line

**Classification: CONTEXTUAL** ✓
**Why it matters:** KRAS G12C sotorasib response is dramatically different between NSCLC (~30–40% ORR) and PDAC (~9%) in clinical trials. This contextual contradiction reflects a real and well-studied biological difference.

---

### Example 7 (METHODOLOGICAL)

**Domain:** Cancer genomics
**Claim A:** "STRING-seq single-cell RNA sequencing of KRAS G12C A549 cells shows MEK/ERK pathway genes upregulated in 78% of cells after KRAS inhibition."
**Claim B:** "Bulk RNA sequencing of A549 KRAS G12C cells treated with MRTX849 shows no significant MEK/ERK pathway upregulation by gene set enrichment analysis."

**Decision tree:**
- Q1: Same system? Yes — A549 KRAS G12C, same drug
- Q2: Same assay? No — single-cell RNA-seq vs. bulk RNA-seq

**Classification: METHODOLOGICAL** ✓
**Note:** Bulk RNA-seq averages across cells; if only a minority of cells upregulate MEK/ERK, bulk would miss it. This is a genuine methodological discrepancy that reveals something about tumor heterogeneity.

---

### Example 8 (DIRECT)

**Domain:** Neuroscience
**Claim A:** "Optogenetic stimulation of hippocampal CA3 mossy fiber inputs during encoding enhances subsequent spatial memory performance in the Morris water maze."
**Claim B:** "CA3 mossy fiber optogenetic activation during encoding impairs spatial memory consolidation in the Morris water maze."

**Decision tree:**
- Q1: Same system? Yes — mouse, hippocampal CA3, Morris water maze
- Q2: Same assay? Yes — optogenetics (ChR2) + Morris water maze
- Q3: Same time point? Yes — during encoding phase
- Q4: Opposite directions? Yes — enhances vs. impairs
- Q6: Context shared? Yes — same protocol, same stimulation target, same behavioral test

**Classification: DIRECT** ✓
**Possible explanation (for Paper 2 discussion):** Could be due to different stimulation parameters (frequency, duration), different mouse strains, or different light power — but these differences are not explicitly stated, making this a DIRECT contradiction pending further investigation.

---

### Example 9 (MAGNITUDE)

**Domain:** Cancer genomics
**Claim A:** "Combination of sotorasib and cetuximab reduces CRC tumor volume by 65% in SW480 xenograft models (p < 0.001)."
**Claim B:** "Sotorasib plus cetuximab co-treatment results in a 12% reduction in SW480 xenograft tumor volume compared to vehicle control (p = 0.38)."

**Decision tree:**
- Q1: Same system? Yes — SW480 colorectal cancer xenograft
- Q2: Same assay? Yes — tumor volume measurement
- Q3: Same time point? Yes — endpoint tumor volume after treatment
- Q4: Opposite directions? No — both show reduction (same direction)
- Q5: Different statistical significance? Yes — p<0.001 vs. p=0.38; 65% vs. 12%

**Classification: MAGNITUDE** ✓
**Why this matters:** Magnitude contradictions often arise from differences in dosing schedule, tumor passage number, or housing conditions that are not always reported. They are particularly problematic for reproducibility.

---

### Example 10 (MAGNITUDE)

**Domain:** Spaceflight biology
**Claim A:** "Bone mineral density of the lumbar spine decreases by 1.5% per month during long-duration spaceflight, totaling ~9% over 6 months."
**Claim B:** "Lumbar spine BMD loss during 6-month ISS missions averages 1.0% over the full mission duration, as measured by DXA post-flight."

**Decision tree:**
- Q1: Same system? Yes — ISS astronauts, lumbar spine
- Q2: Same assay? Yes — DXA scan
- Q3: Same time point? Yes — post 6-month mission
- Q4: Opposite directions? No — both show loss
- Q5: Different significance? Yes — 9% total vs. 1% total (9× difference in magnitude)

**Classification: MAGNITUDE** ✓
**Note:** The 9-fold difference in BMD loss estimate is clinically significant and represents a real scientific controversy in spaceflight medicine.

---

## 6. Edge Cases and Adjudication Rules

### When to choose `is_genuine = No`

Mark `is_genuine = No` (not a real contradiction) in the following situations:

| Situation | Reason |
|-----------|--------|
| One paper uses hedged language ("may", "suggests", "possibly") while the other makes a definitive claim | Hedged vs. definitive = different epistemic status, not a contradiction |
| One claim is from a review article that characterizes another paper's findings | Reviews may misquote primary sources; only primary papers count |
| The two claims address different aspects of the same phenomenon (e.g., mRNA vs. protein) without asserting equivalence | Measuring different molecular layers is not a contradiction |
| A newer paper explicitly re-analyzes the older dataset and corrects a previous error | This is a correction, not an independent contradiction |
| The difference is within normal biological variability or measurement error (< 10% for continuous measures) | Noise is not contradiction |

### Priority rules when multiple types apply

If the pair seems to fit more than one type, apply this priority order:
1. **CONTEXTUAL** — if the biological system differs, stop here regardless of other differences
2. **METHODOLOGICAL** — if the assay differs (but context is same), stop here
3. **TEMPORAL** — if the time point differs (but context and assay are same), stop here
4. **DIRECT** or **MAGNITUDE** — only when all above conditions are equalized

**Rationale:** The goal is to identify the primary driver of the discrepancy. Most pairs have one dominant driver.

### When to flag for discussion

Add a note in the **Flag** column (set to `Y`) in the following situations:
- You are split between two types and cannot resolve it with the decision tree
- The claim text is too vague to determine the experimental context
- You believe the pair should be excluded (e.g., one claim appears to be fabricated or retracted)
- You suspect the two claims are from the same laboratory's papers (within-lab variation is not a contradiction)

All flagged pairs will be reviewed by JKK before the inter-annotator agreement calculation.

### Disagreement adjudication procedure

After both annotators complete their annotation independently:
1. Compute Cohen's kappa on all non-flagged entries
2. For entries where annotators disagree: both annotators discuss synchronously (30-min video call)
3. If consensus is reached: apply consensus label
4. If no consensus: JKK makes the final decision as adjudicator
5. Final labels are used for corpus publication and Paper 2

---

## 7. Annotation Interface Instructions

### Google Sheet structure

Each row represents one claim pair. Columns you need to fill:

| Column | What to enter |
|--------|--------------|
| **A** `entry_id` | Read-only — pre-filled |
| **B** `domain` | Read-only — pre-filled |
| **C** `claim_a_text` | Read-only — Claim A |
| **D** `claim_a_doi` | Read-only — source DOI for Claim A |
| **E** `claim_b_text` | Read-only — Claim B |
| **F** `claim_b_doi` | Read-only — source DOI for Claim B |
| **G** `is_genuine` | **YOU FILL:** `Yes` or `No` |
| **H** `contradiction_type` | **YOU FILL:** `direct` / `contextual` / `methodological` / `temporal` / `magnitude` / `n/a` (if `is_genuine=No`) |
| **I** `confidence` | **YOU FILL:** `High` (>90% certain) / `Medium` (70–90%) / `Low` (<70%) |
| **J** `notes` | Optional free text — explain reasoning, flag uncertainties |
| **K** `flag` | `Y` if this pair should be reviewed; leave blank otherwise |

### Workflow

1. Open the Google Sheet (link provided separately)
2. Complete the **5 calibration pairs first** (rows 2–6; answers revealed after submission)
3. If you score <3/5 on calibration: contact JKK before proceeding
4. Annotate rows 7–156 in any order (you may skip and return)
5. Progress is auto-saved; you may close and reopen at any time
6. When done, send a completion email to JKK with the subject line: "Annotation complete — [your name]"

### Do not consult the papers

To preserve annotation independence, do **not** look up the original papers during annotation. Base your decision solely on the claim text provided. If a claim is ambiguous without additional context, note this in the **notes** column and proceed with your best judgment.

---

## 8. Pre-Annotation Calibration Set

**Complete these 5 pairs BEFORE starting the main annotation.** Answers are revealed automatically in the sheet after you submit your responses to all 5. If you score < 3/5, please contact JKK — your calibration suggests the guidelines may need clarification.

These 5 pairs are **not part of the 150 main corpus** and will not be included in the inter-annotator kappa calculation.

| # | What to look for | Common wrong answer |
|---|-----------------|-------------------|
| Cal-1 | Direct contradiction — same cell line, same assay, opposite kinase activity | Might classify as Magnitude because numbers differ |
| Cal-2 | Contextual — mouse vs. human comparison, same pathway | Might classify as Direct because "same gene" |
| Cal-3 | Methodological — scRNA-seq vs. bulk RNA-seq for same gene | Might classify as Contextual |
| Cal-4 | Temporal — acute vs. chronic treatment response | Might classify as Direct |
| Cal-5 | Not genuine (is_genuine = No) — hedged claim vs. definitive claim | Might classify as Direct |

*(Specific claim texts for calibration set to be inserted before sheet distribution)*

---

## 9. Authorship, Data Use, and Contact

### Authorship policy

- **Acknowledgment**: Annotators completing ≥ 80% of entries (120+ of 150 pairs) with ≥ 4 hours of engagement are credited in the Acknowledgments section of Paper 2.
- **Co-authorship**: The second annotator completing 100% of entries is offered co-authorship on Paper 2 if their annotation quality (kappa ≥ 0.6 with annotator 1) meets the standard for a methodological contribution. Co-authorship will be discussed individually.

### Data use

Your annotations will be:
- Used to compute inter-annotator agreement (Cohen's kappa) reported in Paper 2
- Stored alongside the published corpus as `annotator_labels.csv` (CC-BY 4.0)
- **Individually anonymized** in the supplementary material (referred to as "Annotator 1" and "Annotator 2")

Raw annotation data (including individual annotator responses) will **not** be shared publicly without your consent.

### Contact

**JangKeun Kim**
Weill Cornell Medicine
Contact: use this repository's GitHub Issues.

For questions about specific claim pairs: email with the `entry_id` (e.g., CT-047) and a brief description of your confusion.

---

*Document version 1.0 — 2026-03-02*
*Please do not redistribute this document without permission.*
