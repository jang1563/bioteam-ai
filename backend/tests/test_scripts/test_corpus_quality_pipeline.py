import json
import sys
from pathlib import Path

import pytest
from scripts.corpus_quality_utils import LEGACY_EXCLUDED_IDS, pair_quality_issues

from scripts import add_candidates_by_id as add_by_id
from scripts import recompute_corpus_metrics as recompute


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_pair_quality_issues_detect_fragment_and_truncation() -> None:
    issues = pair_quality_issues(
        "ned with the (1) open packing technique, (2) staged relaparotomies",
        "the latter method seems to be associated with lower morbidity.",
    )
    assert "claim_a:suspicious_fragment_prefix" in issues

    issues = pair_quality_issues(
        "moderate-certainty evidence)",
        "more recent studies show less benefit than earlier studies.",
    )
    assert "claim_a:unmatched_closing_paren" in issues
    assert "V3-MAG-0007" in LEGACY_EXCLUDED_IDS


def test_add_candidates_by_id_blocks_legacy_ids_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidates_dir = tmp_path
    corpus_in = tmp_path / "corpus_in.jsonl"
    corpus_out = tmp_path / "corpus_out.jsonl"
    changes_out = tmp_path / "changes.jsonl"
    rejected_out = tmp_path / "rejected.jsonl"

    _write_jsonl(corpus_in, [])
    _write_jsonl(
        candidates_dir / "candidates_magnitude_v5.jsonl",
        [
            {
                "pair_id": "V3-MAG-0007",
                "domain": "magnitude",
                "intended_type": "magnitude",
                "claim_a": {"text": "This is a full sentence with enough tokens for quality screening to pass."},
                "claim_b": {"text": "Another full sentence that would otherwise pass quality filtering."},
                "label": {
                    "contradiction_type": "magnitude",
                    "confidence": 0.95,
                    "is_genuine_contradiction": True,
                    "rationale": "test",
                },
            },
            {
                "pair_id": "X-OK-001",
                "domain": "magnitude",
                "intended_type": "magnitude",
                "claim_a": {"text": "This intervention showed a stronger effect than the comparator in pooled analyses."},
                "claim_b": {"text": "Sensitivity analyses reduced effect size but still showed a meaningful association."},
                "label": {
                    "contradiction_type": "magnitude",
                    "confidence": 0.95,
                    "is_genuine_contradiction": True,
                    "rationale": "test",
                },
            },
        ],
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "add_candidates_by_id.py",
            "--candidates-dir",
            str(candidates_dir),
            "--corpus-in",
            str(corpus_in),
            "--corpus-out",
            str(corpus_out),
            "--changes-out",
            str(changes_out),
            "--rejected-out",
            str(rejected_out),
            "--ids",
            "V3-MAG-0007",
            "X-OK-001",
        ],
    )
    add_by_id.main()

    added = [json.loads(line) for line in changes_out.read_text(encoding="utf-8").splitlines() if line.strip()]
    rejected = [json.loads(line) for line in rejected_out.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert [row["id"] for row in added] == ["X-OK-001"]
    assert any(row["id"] == "V3-MAG-0007" for row in rejected)


def test_recompute_reports_gold_coverage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    preds = tmp_path / "preds.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    report_out = tmp_path / "report.json"
    misclassified_out = tmp_path / "misclassified.jsonl"

    _write_jsonl(
        preds,
        [
            {"id": "A", "pred_type": "direct", "pred_genuine": True, "parse_failed": False},
            {"id": "B", "pred_type": "contextual", "pred_genuine": False, "parse_failed": False},
            {"id": "X", "pred_type": "direct", "pred_genuine": True, "parse_failed": False},
        ],
    )
    _write_jsonl(
        corpus,
        [
            {"id": "A", "contradiction_type": "direct", "is_genuine_contradiction": True},
            {"id": "B", "contradiction_type": "contextual", "is_genuine_contradiction": False},
            {"id": "C", "contradiction_type": "temporal", "is_genuine_contradiction": True},
        ],
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "recompute_corpus_metrics.py",
            "--predictions",
            str(preds),
            "--corpus",
            str(corpus),
            "--report-out",
            str(report_out),
            "--misclassified-out",
            str(misclassified_out),
        ],
    )
    recompute.main()

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["gold_total_rows"] == 3
    assert report["gold_covered_rows"] == 2
    assert report["unscored_gold_rows"] == 1
    assert report["scope_note"].startswith("matched_subset_only")
