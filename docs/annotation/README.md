# RCMXT Annotation Corpus

This directory contains materials for the RCMXT inter-rater reliability study (Paper 1).

## Files

| File | Description |
|------|-------------|
| `rcmxt_guidelines.md` | Complete annotation guidelines — read this first |
| `claim_corpus_template.csv` | 15 seed claims (target: 150) across 3 domains |

## Target Corpus

- **150 biological claims** across 3 domains:
  - `SB-*`: Spaceflight biology (50 claims)
  - `CG-*`: Cancer genomics (50 claims)
  - `NS-*`: Neuroscience (50 claims)
- **5 expert annotators** per claim
- **Axes**: R, C, M, X (nullable), T
- **Agreement target**: ICC(2,k) > 0.60 per axis

## Status

- [x] Guidelines v1.0 written
- [x] 15 seed claims curated (pilot round candidates included)
- [ ] Pilot round (10 claims × 2 annotators)
- [ ] Full corpus 150 claims curated
- [ ] Expert annotation round
- [ ] LLM calibration run
- [ ] ICC computation
