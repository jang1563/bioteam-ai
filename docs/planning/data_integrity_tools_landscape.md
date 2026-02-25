# Data Integrity Tools Landscape

Comprehensive survey of existing tools for detecting errors in published papers and public biological databases. Compiled February 2026 for the BioTeam-AI Data Integrity Auditor design.

---

## 1. Statistical Integrity

| Tool | Language | License | What it does | URL/Package |
|------|----------|---------|-------------|-------------|
| **statcheck** | R | GPL | Extracts APA-style stats from text, recalculates p-values, flags inconsistencies | CRAN: `statcheck` |
| **JATSdecoder** | R | GPL | Extracts statistical results from JATS XML (journal articles) | CRAN: `JATSdecoder` |
| **grim** (GRIM test) | Python | MIT | Tests whether reported means are mathematically possible given sample size (integer data) | PyPI: `grim` |
| **pysprite** | Python | MIT | SPRITE test: checks if reported SD/mean are consistent with integer-constrained data | PyPI: `pysprite` |
| **rsprite2** | R | GPL | R implementation of SPRITE (Sample Parameter Reconstruction via Iterative TEchniques) | CRAN: `rsprite2` |
| **benford_py** | Python | MIT | Benford's Law analysis — detects anomalous first-digit distributions in numerical data | PyPI: `benford_py` |
| **Problematic Paper Screener** | Web | — | Screens papers for tortured phrases, statistical anomalies, paper mill patterns | problematicpaperscreener.com |

### Key Concepts
- **GRIM test** (Granularity-Related Inconsistency of Means): For Likert/count data, only certain mean values are achievable for a given N. Mean=3.47 with N=15 is impossible for integer data.
- **SPRITE test**: Extends GRIM to standard deviations. Reconstructs possible datasets that could produce reported descriptive statistics.
- **Benford's Law**: In naturally occurring datasets, the leading digit follows a specific distribution (1 appears ~30%, 9 appears ~5%). Deviations suggest data fabrication.
- **statcheck**: Most widely used tool. Has found errors in ~50% of psychology papers checked.

---

## 2. Gene & Biological Data Errors

| Tool | Language | What it does | URL/Package |
|------|----------|-------------|-------------|
| **Gene Updater** | Python/R | Fixes Excel gene-name mangling (MARCH1→1-Mar, SEPT7→7-Sep) | Various implementations |
| **Truke** | Database | Database of known gene symbol errors in published literature | truke.ensg.eu |
| **HGNC REST API** | REST API | Official HUGO Gene Nomenclature Committee — validates/corrects gene symbols | rest.genenames.org |
| **CrossMap** | Python | Genome coordinate liftover between assemblies (hg19↔hg38, mm9↔mm10) | PyPI: `CrossMap` |
| **liftOver** | Binary | UCSC genome coordinate conversion | genome.ucsc.edu |

### The Excel Gene Name Problem
A landmark 2016 study (Ziemann et al.) found that ~20% of supplementary data files in genomics papers contained gene names converted to dates by Excel. Common victims:
- **MARCH** family (MARCH1-11): Membrane Associated Ring-CH-Type → 1-Mar, 2-Mar, etc.
- **SEPT** family (SEPT1-12): Septin → 1-Sep, 2-Sep, etc.
- **DEC** family (DEC1-2): Deleted In Esophageal Cancer → 1-Dec, 2-Dec
- **OCT** family (OCT4): Organic Cation Transporter / POU5F1 → 4-Oct

In 2023, HGNC officially renamed many of these genes to avoid Excel corruption (MARCH1→MARCHF1, SEPT1→SEPTIN1), but legacy names persist in literature and databases.

---

## 3. Publication Integrity

| Tool | Type | What it does | URL |
|------|------|-------------|-----|
| **Crossref API** | REST API | Check retraction status, corrections, expressions of concern for DOIs | api.crossref.org |
| **Retraction Watch Database** | Database | Comprehensive database of retracted papers (~47,000+ entries) | retractionwatch.com |
| **PubPeer** | API/Web | Post-publication commentary — community-flagged issues | pubpeer.com/api |
| **scite.ai** | API/Web | Smart citations — classifies citations as supporting/contrasting/mentioning | scite.ai |
| **OpenAlex API** | REST API | Open scholarly metadata (works, authors, institutions, concepts) | openalex.org |
| **Unpaywall** | API | Open access status for DOIs | unpaywall.org |
| **GROBID** | Java/REST | Machine learning PDF→structured XML extraction (headers, references, body) | github.com/kermitt2/grobid |
| **Dimensions** | API | Research analytics — publications, grants, patents, clinical trials | dimensions.ai |

### Crossref Retraction Checking
The Crossref API provides `update-to` relationships:
- `retraction`: Paper has been retracted
- `correction`: Paper has a published correction/erratum
- `expression-of-concern`: Publisher has issued an expression of concern
- Rate limit: Without registered email, ~1 req/sec. With polite pool email: higher limits

---

## 4. Image & Figure Integrity

| Tool | Type | What it does | URL |
|------|------|-------------|-----|
| **Proofig** | SaaS | AI-powered image duplication/manipulation detection for journals | proofig.com |
| **Imagetwin** | SaaS | Detects duplicated images across publications | imagetwin.ai |
| **Barzooka** | Open source | Detects inappropriate bar charts, AI-generated images in papers | barzooka.com |
| **SILA** | Tool | Scientific Image Literacy Assessment — forensic image analysis | — |
| **Sherloq** | Open source | Digital image forensic toolkit (ELA, noise analysis, clone detection) | github.com/GuidoBartoli/sherloq |
| **FotoForensics** | Web | Error Level Analysis, metadata extraction for images | fotoforensics.com |

### Detection Approaches
- **Perceptual hashing**: Generate image fingerprints → detect near-duplicates across papers
- **Error Level Analysis (ELA)**: Reveals regions of different compression levels (indicates splicing)
- **Clone detection**: Finds duplicated regions within a single image
- **EXIF metadata**: Reveals editing software, timestamps, camera info

---

## 5. Omics Data Quality

| Tool | Language | What it does | URL |
|------|----------|-------------|-----|
| **FastQC** | Java | Quality control for raw sequencing data (per-base quality, adapter content, etc.) | bioinformatics.babraham.ac.uk |
| **MultiQC** | Python | Aggregates QC reports from multiple tools into a single report | PyPI: `multiqc` |
| **fastp** | C++ | Fast all-in-one FASTQ preprocessor (QC, adapter trimming, filtering) | github.com/OpenGene/fastp |
| **RNA-SeQC** | Java/Python | RNA-seq specific QC (gene body coverage, rRNA contamination, etc.) | github.com/getzlab/rnaseqc |
| **IDCheck** | R | Sample identity verification via genotype concordance | — |
| **nf-core pipelines** | Nextflow | Standardized bioinformatics pipelines with built-in QC | nf-core.re |
| **GEO metadata standards** | — | MIAME/MINSEQE compliance for GEO/SRA submissions | ncbi.nlm.nih.gov/geo |

### Common Data Quality Issues in Public Repositories
- Mislabeled samples (e.g., tumor vs. normal swapped)
- Missing or incorrect metadata (organism, tissue, platform)
- Genome build inconsistency (hg19 coordinates in hg38-annotated files)
- Batch effects not documented
- Incomplete raw data (processed-only deposits)

---

## 6. AI/Text Integrity

| Tool | Type | What it does | URL |
|------|------|-------------|-----|
| **SciDetect** | Python | Detects SCIgen-generated fake computer science papers | — |
| **SciScore** | API/Web | Evaluates rigor and reproducibility of methods sections | sciscore.com |
| **ODDPub** | R | Detects whether open data/code is mentioned and actually shared | github.com/quest-bih/oddpub |
| **DataSeer** | ML/Web | Detects datasets mentioned in papers that aren't publicly shared | dataseer.ai |
| **Tortured Phrases Detector** | Various | Detects papers from paper mills using synonym-substituted "tortured phrases" | — |

### Tortured Phrases Examples
Paper mills use automatic synonym substitution to evade plagiarism detection:
- "artificial neural network" → "counterfeit neural system"
- "deep learning" → "profound learning"
- "random forest" → "arbitrary woodland"
- "breast cancer" → "bosom malignancy"

---

## 7. Platforms & Services

| Platform | Type | What it does | URL |
|----------|------|-------------|-----|
| **STM Integrity Hub** | Consortium | Publisher consortium for sharing integrity screening tools | stm-assoc.org |
| **Papermill Alarm** | Service | Detects paper mill patterns (shared authors, template text, citation rings) | — |
| **Paperpal Preflight** | SaaS | Pre-submission manuscript checker (ethics, stats, references) | paperpal.com |
| **Signals/Sleuth AI** | Service | AI-powered screening for publishers (paper mills, data fabrication) | — |
| **ScreenIT** | Pipeline | Automated screening pipeline combining multiple integrity checks | — |
| **Hypothesis** | Platform | Open web annotation layer — community annotations on any web page | hypothes.is |
| **FAIRDOM-SEEK** | Platform | FAIR data management and sharing | fair-dom.org |

---

## 8. Implementation Priority for BioTeam-AI

Based on automation feasibility and impact:

### Tier 1 — Fully Automatable (implement natively)
1. **Gene name Excel errors** — regex patterns + HGNC API validation
2. **GRIM test** — ~30 lines of math, no external deps
3. **Benford's law** — ~50 lines + scipy chi-squared
4. **Retraction checking** — Crossref REST API (free, public)
5. **PubPeer commentary** — PubPeer API (free, public)
6. **GEO/SRA accession validation** — regex patterns

### Tier 2 — Partially Automatable (implement with caveats)
7. **P-value recalculation** — regex extraction of APA stats + scipy
8. **SPRITE test** — more complex reconstruction, useful for detailed audits
9. **Genome coordinate validation** — CrossMap integration
10. **Sample size consistency** — heuristic checks

### Tier 3 — Requires External Services (integrate later)
11. **Image duplication** — would need Proofig/Imagetwin API or perceptual hashing library
12. **Tortured phrase detection** — NLP-based, could use LLM
13. **PDF structure extraction** — GROBID integration
14. **Citation network analysis** — OpenAlex API for citation ring detection

---

## References

- Ziemann M, Eren Y, El-Osta A. "Gene name errors are widespread in the scientific literature." Genome Biol. 2016;17:177.
- Abeysooriya M, et al. "Gene name errors: Lessons not learned." PLOS Comput Biol. 2021;17(7):e1008984.
- Brown NJL, Heathers JAT. "The GRIM Test." Social Psychological and Personality Science. 2017;8(4):363-369.
- Heathers JAT, et al. "The SPRITE test." PeerJ Preprints. 2018.
- Nuijten MB, et al. "The prevalence of statistical reporting errors in psychology (1985-2013)." Behav Res Methods. 2016;48(4):1205-1226.
- Bik EM, et al. "The prevalence of inappropriate image duplication in biomedical research publications." mBio. 2016;7(3):e00809-16.
- Cabanac G, Labbé C, Magazinov A. "Tortured phrases: A dubious writing style emerging in science." arXiv:2107.06751. 2021.
