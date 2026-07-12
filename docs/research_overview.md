# BioTeam-AI Research Overview

BioTeam-AI investigates whether structured, biology-specific AI workflows can
make manuscript support more inspectable. The repository combines typed report
contracts, human checkpoints, frozen examples, and optional model-backed
workflows.

The system is research decision support. It does not replace scientific,
statistical, safety, or peer-review judgment.

## Capability scope

### Tested core

- manuscript sessions and workflow linking;
- versioned reviewer-risk and integrity-report contracts;
- offline API, workflow, security, and model tests;
- a reproducible frontend lint and production-build gate.

### Guided research support

- candidate story frames for researcher selection;
- claim maps and RCMXT multi-axis evidence annotations;
- quick submission scans that are explicitly weaker than a full workflow run.

### Experimental surfaces

- live LLM evaluation and network integrations;
- extended workflow orchestration;
- data-dependent benchmark scripts whose source artifacts are not in the
  public code release.

## Public evidence map

| Question | Public evidence |
|---|---|
| What does a clean checkout verify? | [Reproducible evidence](./reproducible_evidence.md) |
| How are reviewer risks represented? | [Frozen reviewer-risk example](./case_studies/reviewer_risks_microgravity.md) |
| How are submission risks represented? | [Frozen submission-check example](./case_studies/submission_checks_microgravity.md) |
| Where are the report contracts implemented? | [`backend/app/models/manuscript.py`](../backend/app/models/manuscript.py) |
| Which data are excluded? | [Data release status](./data_release_status.md) |

## Interpretation boundaries

- Passing tests establishes software behavior for the tested paths, not
  scientific validity across manuscripts or fields.
- Frozen examples demonstrate contracts and provenance plumbing; they are not
  blinded external validation.
- Reviewer-risk output is a prompt for human review, not automated peer review.
- Dataset-dependent historical evaluations must be interpreted with their data,
  split, annotation process, and failure modes. The underlying held datasets
  are not presented as public benchmarks in this release.

The strongest supported public claim is that BioTeam-AI provides inspectable,
biology-specific manuscript-support components with explicit scope and
limitations.
