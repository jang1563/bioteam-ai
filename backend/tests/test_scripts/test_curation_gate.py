import json
import sys
from pathlib import Path

from scripts import apply_curation_queue as apply_queue
from scripts import qa_corpus_v3 as qa_script


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_qa_outputs_hard_and_soft_queues(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus.jsonl"
    out_dir = tmp_path / "qa_out"
    rows = [
        {
            "id": "H1",
            "claim_a": "effect was not statistically significant (p < 0.",
            "claim_b": "replication in an independent cohort showed no difference.",
            "contradiction_type": "direct",
            "is_genuine_contradiction": True,
            "confidence": 0.95,
            "domain": "direct",
        },
        {
            "id": "S1",
            "claim_a": "The intervention increased expression of the marker in one condition.",
            "claim_b": "A separate analysis reported decreased expression under similar settings.",
            "contradiction_type": "temporal",
            "is_genuine_contradiction": True,
            "confidence": 0.95,
            "domain": "temporal",
        },
    ]
    _write_jsonl(corpus, rows)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qa_corpus_v3.py",
            "--input",
            str(corpus),
            "--out-dir",
            str(out_dir),
        ],
    )
    qa_script.main()

    hard_queue = _read_jsonl(out_dir / "corpus_curation_queue_hard.jsonl")
    soft_queue = _read_jsonl(out_dir / "corpus_curation_queue_soft.jsonl")
    report = json.loads((out_dir / "corpus_qa_report.json").read_text(encoding="utf-8"))

    assert [row["id"] for row in hard_queue] == ["H1"]
    assert [row["id"] for row in soft_queue] == ["S1"]
    assert report["curation_gate"]["hard_remove_rows"] == 1
    assert report["curation_gate"]["soft_review_rows"] == 1


def test_qa_marks_structural_fragment_as_hard(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus_structural.jsonl"
    out_dir = tmp_path / "qa_structural"
    _write_jsonl(
        corpus,
        [
            {
                "id": "H2",
                "claim_a": "moderate-certainty evidence)",
                "claim_b": "more recent studies show less benefit than earlier studies in this review.",
                "contradiction_type": "temporal",
                "is_genuine_contradiction": True,
                "confidence": 0.95,
                "domain": "magnitude",
            },
            {
                "id": "H3",
                "claim_a": "ned with the (1) open packing technique and staged relaparotomies in severe disease.",
                "claim_b": "the latter method seems to be associated with lower morbidity than alternatives.",
                "contradiction_type": "magnitude",
                "is_genuine_contradiction": True,
                "confidence": 0.95,
                "domain": "temporal",
            },
        ],
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qa_corpus_v3.py",
            "--input",
            str(corpus),
            "--out-dir",
            str(out_dir),
        ],
    )
    qa_script.main()

    hard_queue = _read_jsonl(out_dir / "corpus_curation_queue_hard.jsonl")
    hard_ids = {row["id"] for row in hard_queue}
    assert "H2" in hard_ids
    assert "H3" in hard_ids


def test_apply_curation_queue_removes_only_hard_flag_rows(tmp_path: Path, monkeypatch) -> None:
    corpus_in = tmp_path / "corpus_in.jsonl"
    queue = tmp_path / "queue.jsonl"
    corpus_out = tmp_path / "corpus_out.jsonl"
    changes_out = tmp_path / "changes.jsonl"
    stats_out = tmp_path / "stats.json"

    _write_jsonl(
        corpus_in,
        [
            {
                "id": "H1",
                "claim_a": "A",
                "claim_b": "B",
                "contradiction_type": "direct",
                "is_genuine_contradiction": True,
                "confidence": 0.95,
            },
            {
                "id": "S1",
                "claim_a": "A",
                "claim_b": "B",
                "contradiction_type": "temporal",
                "is_genuine_contradiction": True,
                "confidence": 0.95,
            },
        ],
    )
    _write_jsonl(
        queue,
        [
            {"id": "H1", "flags": ["truncated_pvalue_pattern"], "hard_flags": ["truncated_pvalue_pattern"]},
            {"id": "S1", "flags": ["temporal_without_time_cue"], "hard_flags": []},
        ],
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_curation_queue.py",
            "--input-corpus",
            str(corpus_in),
            "--curation-queue",
            str(queue),
            "--output-corpus",
            str(corpus_out),
            "--changes-out",
            str(changes_out),
            "--stats-out",
            str(stats_out),
        ],
    )
    apply_queue.main()

    out_rows = _read_jsonl(corpus_out)
    changes = _read_jsonl(changes_out)
    stats = json.loads(stats_out.read_text(encoding="utf-8"))

    assert [row["id"] for row in out_rows] == ["S1"]
    assert [row["id"] for row in changes] == ["H1"]
    assert stats["removed_rows"] == 1
