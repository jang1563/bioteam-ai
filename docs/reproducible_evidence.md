# Reproducible Evidence

This page defines what can be verified from the public repository without
private data or paid model calls.

## Clean-checkout gates

| Gate | Command | Expected condition |
|---|---|---|
| Backend lint | `uv run ruff check backend/` | No lint errors |
| Public tree | `uv run python scripts/check_public_manifest.py` | Release boundary passes |
| Public history | `uv run python scripts/check_public_history.py` | Reachable history passes |
| Backend offline suite | `uv run pytest backend/tests/ -m "not integration and not benchmark_slow and not benchmark" -x -q --tb=short` | Tests exit successfully |
| Frontend lint | `cd frontend && npm run lint` | ESLint exits successfully |
| Frontend build | `cd frontend && npm run build` | Production build completes |

These commands are encoded in [CI](../.github/workflows/ci.yml). Exact test
totals can change; the default-branch CI result is the authoritative status.

## Frozen integration examples

- [Reviewer risks on a microgravity manuscript](./case_studies/reviewer_risks_microgravity.md)
- [Submission checks on a spreadsheet-style gene-symbol risk](./case_studies/submission_checks_microgravity.md)

The examples exercise typed aggregation and provenance fields. They use
repo-native fixtures and do not establish external scientific generalization.

## Public release checks

[`release/public_release_manifest.json`](../release/public_release_manifest.json)
records required files, excluded path classes, forbidden local literals, and
the status of held data artifacts. Two small validators enforce the manifest:

- [`scripts/check_public_manifest.py`](../scripts/check_public_manifest.py)
  checks the currently tracked tree;
- [`scripts/check_public_history.py`](../scripts/check_public_history.py)
  checks all reachable Git objects and commit metadata.

## What is not reproduced here

- live model evaluations and paid API calls;
- full biomedical abstracts;
- private ContradictBio working datasets;
- cached third-party benchmark content;
- historical metrics whose inputs are not in the public release.

See [Data release status](./data_release_status.md) for the reason these
artifacts are held.
