# Case Study: Submission Checks on a Spreadsheet-Style Gene Symbol Risk

Status: `Frozen integration example` with a guided-support fallback

This frozen case study shows the part of the product that is easiest to trust quickly:

- a manuscript-session integrity surface
- a typed `IntegrityAuditReport v1`
- a concrete biology-specific finding
- a clear distinction between the full W7 audit and the lighter quick-scan fallback

## Scenario

The manuscript session is linked to a W7 submission-audit workflow that surfaces:

- `Potential gene naming issue`
- category: `gene_name_error`
- severity: `warning`
- detail: `SEPT2 may be misread as a spreadsheet date.`

This is an avoidable issue that maps to a documented biology workflow failure
mode and can be assessed through a specific, inspectable output.

## Why This Matters

This case provides a compact public integration example because the output is
specific, inspectable, and tied to a versioned report contract.

It shows:

- a biology-specific integrity finding rather than a generic "quality score"
- a versioned report contract
- visible provenance from the linked W7 workflow
- a product posture that prefers defensible checks over vague autonomy claims

## Frozen Output Shape

Representative `IntegrityAuditReport v1` excerpt:

```json
{
  "report_type": "IntegrityAuditReport",
  "version": "v1",
  "maturity": "validated_core",
  "summary": "1 submission-check finding is currently attached to this manuscript session.",
  "findings": [
    {
      "title": "Potential gene naming issue",
      "severity": "warning",
      "category": "gene_name_error",
      "detail": "SEPT2 may be misread as a spreadsheet date.",
      "suggestion": "Use HGNC-approved symbol formatting.",
      "status": "open",
      "generated_by": "W7:example-w7-microgravity"
    }
  ],
  "evidence_provenance": [
    "Full W7 audit contributed 1 persisted findings."
  ],
  "confidence_or_coverage": "full audit findings 1"
}
```

## How To Reproduce

Full workflow-linked path:

```bash
uv run pytest backend/tests/test_api/test_manuscript_api.py -k linking_workflows_aggregates_manuscript_outputs -q
```

This verifies:

- linked W7 findings surface in the manuscript session
- `IntegrityAuditReport v1` is returned
- the fixture preserves its maturity label for compatibility
- run metadata points back to the linked W7 workflow

Guided-support fallback path:

```bash
uv run pytest backend/tests/test_api/test_manuscript_api.py -k run_submission_checks_populates_integrity_flags_from_session_text -q
```

This second path verifies that a lighter session-text scan still returns `IntegrityAuditReport v1`, but with `maturity` set to `guided_support` when no full W7 workflow is linked.

Reference implementation:

- [backend/tests/test_api/test_manuscript_api.py](../../backend/tests/test_api/test_manuscript_api.py)
- [backend/app/api/v1/manuscript.py](../../backend/app/api/v1/manuscript.py)

## Honest Limitations

- The full value of submission checks comes from the underlying deterministic and workflow-backed engines, not from this one frozen example alone.
- The quick scan is intentionally weaker than the full W7 audit and should not be presented as equivalent.
- The supported public claim is that the repository implements inspectable manuscript-integrity outputs, not complete scientific validation.
