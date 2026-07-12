# Case Study: Reviewer Risks on a Microgravity Manuscript

Status: `Frozen integration example`

This is a frozen, repo-native example for the manuscript-support path.

It demonstrates the project through a compact, inspectable validation path:

- a concrete manuscript objective
- a selected story frame
- a concern-level `ReviewerRiskReport v1`
- evidence provenance and run metadata that a reviewer can inspect quickly

## Scenario

The manuscript session asks:

> Build a defensible manuscript around erythroid adaptation in microgravity.

The linked W11 frame is mechanism-first. The linked W8 review fixture extracts one central claim and then surfaces four reviewer-facing risks:

- underspecified controls for the perturbation experiment
- a missing landmark comparison for novelty framing
- potential batch effects between flights
- sparse protocol detail for replication

## Why This Matters

This is useful as a public software example because it goes beyond an
unstructured model-generated review.

The stronger signal is that the system:

- preserves a manuscript-oriented workflow state
- aggregates W11, W8, and W7 into one session
- produces a typed reviewer-risk contract
- keeps evidence provenance visible

## Frozen Output Shape

Representative `ReviewerRiskReport v1` excerpt:

```json
{
  "report_type": "ReviewerRiskReport",
  "version": "v1",
  "maturity": "validated_core",
  "summary": "Promising but vulnerable to reviewer questions.",
  "findings": [
    {
      "title": "Controls are underspecified for the perturbation experiment.",
      "severity": "high",
      "section": "Methods",
      "detail": "Controls are underspecified for the perturbation experiment.",
      "evidence_basis": "The methods section omits matched ground controls.",
      "generated_by": "W8:example-w8-microgravity"
    },
    {
      "title": "Missing landmark comparison",
      "severity": "medium",
      "section": "Novelty",
      "detail": "Compare against PMID 12345 before submission.",
      "evidence_basis": "",
      "generated_by": "W8:example-w8-microgravity"
    }
  ],
  "evidence_provenance": [
    "Claim extraction grounded 1 manuscript claims for review synthesis.",
    "Novelty assessment surfaced 1 missing landmark comparisons."
  ],
  "confidence_or_coverage": "4 surfaced reviewer risks from the linked W8 run."
}
```

## How To Reproduce

Run the manuscript-session aggregation test:

```bash
uv run pytest backend/tests/test_api/test_manuscript_api.py -k linking_workflows_aggregates_manuscript_outputs -q
```

What this verifies:

- W11, W8, and W7 can be linked into one `ManuscriptSession`
- reviewer risks are surfaced at concern level
- `ReviewerRiskReport v1` is returned
- the fixture preserves its maturity label for compatibility
- run metadata points back to the linked W8 workflow

Reference implementation:

- [backend/tests/test_api/test_manuscript_api.py](../../backend/tests/test_api/test_manuscript_api.py)
- [backend/app/api/v1/manuscript.py](../../backend/app/api/v1/manuscript.py)

## Honest Limitations

- This case study uses a frozen repo fixture, not a blinded external review exercise.
- Historical W8 evaluations depend on held inputs and are not independently reproducible from this code release.
- The right public claim is "reviewer-risk support with typed outputs," not "fully automated peer review."
