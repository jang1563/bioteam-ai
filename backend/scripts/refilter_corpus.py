"""Re-apply Phase 4 filter to already-classified candidates_gemini.jsonl.

Reads candidates_gemini.jsonl and re-runs filter_and_balance with updated logic
(include all typed pairs regardless of is_genuine_contradiction).
"""

from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger("refilter")

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))


class ClaimRecord(BaseModel):
    text: str
    source_pmid: str
    source_doi: str
    paper_title: str
    year: str


class CandidatePair(BaseModel):
    pair_id: str
    domain: str
    query_source: str
    claim_a: ClaimRecord
    claim_b: ClaimRecord


class ContradictionTypeLabel(BaseModel):
    contradiction_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    is_genuine_contradiction: bool
    suggested_resolution: str | None = None


class CorpusEntry(BaseModel):
    entry_id: str
    domain: str
    query_source: str
    claim_a: ClaimRecord
    claim_b: ClaimRecord
    contradiction_type: str
    haiku_confidence: float
    haiku_rationale: str
    is_genuine: bool
    suggested_resolution: str | None = None
    annotator_1_type: str | None = None
    annotator_2_type: str | None = None
    final_type: str | None = None
    curation_notes: str | None = None


def load_classified(path: Path) -> list[tuple[CandidatePair, ContradictionTypeLabel | None]]:
    results = []
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            pair = CandidatePair(
                pair_id=row["pair_id"],
                domain=row["domain"],
                query_source=row["query_source"],
                claim_a=ClaimRecord(**row["claim_a"]),
                claim_b=ClaimRecord(**row["claim_b"]),
            )
            lbl_data = row.get("label")
            label = ContradictionTypeLabel(**lbl_data) if lbl_data else None
            results.append((pair, label))
    return results


def filter_and_balance(
    classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]],
    target_per_type: int = 30,
    min_per_type: int = 10,
    confidence_threshold: float = 0.65,
) -> tuple[list[CorpusEntry], dict]:
    all_types = ["direct", "contextual", "methodological", "temporal", "magnitude"]
    by_type: dict[str, list] = defaultdict(list)
    n_failed = n_low_conf = n_not_genuine = 0

    for pair, label in classified:
        if label is None:
            n_failed += 1
            continue
        if not label.is_genuine_contradiction:
            n_not_genuine += 1  # count but don't skip
        if label.confidence < confidence_threshold:
            n_low_conf += 1
            continue
        by_type[label.contradiction_type].append((pair, label))

    for t in all_types:
        by_type[t].sort(key=lambda x: x[1].confidence, reverse=True)

    selected: list[CorpusEntry] = []
    entry_counter = 0
    stats: dict[str, int] = {}

    for t in all_types:
        pool = by_type[t]
        take = min(target_per_type, len(pool))
        stats[t] = take
        if take < min_per_type:
            logger.warning("Type '%s': only %d entries (min=%d)", t, take, min_per_type)
        for pair, label in pool[:take]:
            entry_counter += 1
            selected.append(CorpusEntry(
                entry_id=f"CT-{entry_counter:03d}",
                domain=pair.domain,
                query_source=pair.query_source,
                claim_a=pair.claim_a,
                claim_b=pair.claim_b,
                contradiction_type=label.contradiction_type,
                haiku_confidence=label.confidence,
                haiku_rationale=label.rationale,
                is_genuine=label.is_genuine_contradiction,
                suggested_resolution=label.suggested_resolution,
            ))

    stats_out = {
        "model": "gemini-2.5-flash",
        "total_input": len(classified),
        "failed": n_failed,
        "not_genuine_flagged": n_not_genuine,
        "low_confidence": n_low_conf,
        "genuine_pool_size": sum(len(v) for v in by_type.values()),
        "selected": len(selected),
        "by_type": stats,
        "shortfall_types": [t for t in all_types if stats.get(t, 0) < min_per_type],
    }
    return selected, stats_out


def main() -> None:
    candidates_path = _REPO / "backend/scripts/output/candidates_gemini.jsonl"
    output_path = _REPO / "backend/scripts/output/corpus_150.jsonl"
    stats_path = _REPO / "backend/scripts/output/build_stats_gemini.json"

    classified = load_classified(candidates_path)
    logger.info("Loaded %d classified pairs", len(classified))

    selected, stats = filter_and_balance(classified, target_per_type=30, min_per_type=10)

    # Write corpus
    with open(output_path, "w") as f:
        for e in selected:
            f.write(e.model_dump_json() + "\n")
    logger.info("Wrote %d corpus entries → %s", len(selected), output_path)

    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    print("\n" + "=" * 55)
    print(f"CORPUS STATS  (model: {stats['model']})")
    print("=" * 55)
    print(f"Input pairs:              {stats['total_input']}")
    print(f"  Failed (API error):     {stats['failed']}")
    print(f"  Not-genuine flagged:    {stats['not_genuine_flagged']}  (included if conf≥0.65)")
    print(f"  Low confidence:         {stats['low_confidence']}")
    print(f"  Typed pool:             {stats['genuine_pool_size']}")
    print(f"\nSelected for corpus:      {stats['selected']}")
    print("\nBy type:")
    for t, n in stats["by_type"].items():
        flag = " ⚠" if t in stats.get("shortfall_types", []) else ""
        print(f"  {t:<22} {n:>3}{flag}")
    print("=" * 55)


if __name__ == "__main__":
    main()
