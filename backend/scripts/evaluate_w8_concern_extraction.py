"""Evaluate concern extraction fidelity against a manually curated gold fixture.

Usage:
    python3 backend/scripts/evaluate_w8_concern_extraction.py
    python3 backend/scripts/evaluate_w8_concern_extraction.py --fixture backend/tests/fixtures/w8_concern_extraction_fixture.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


DEFAULT_FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "w8_concern_extraction_fixture.json"
EXTRACTION_EVAL_DIR = Path(__file__).parent.parent / "data" / "w8_benchmark" / "extraction_eval"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate W8 concern extraction fidelity")
    parser.add_argument("--fixture", type=str, default=str(DEFAULT_FIXTURE))
    parser.add_argument("--save", action="store_true", help="Save evaluation artifact under backend/data/w8_benchmark/extraction_eval/")
    args = parser.parse_args()

    from app.engines.review_corpus.concern_parser import evaluate_extraction_against_gold
    from app.models.review_corpus import ReviewerConcern

    fixture_path = Path(args.fixture)
    payload = json.loads(fixture_path.read_text())
    cases = payload.get("cases", [])
    print(f"\nFixture: {fixture_path}")
    print(f"Cases: {len(cases)}")

    aggregate = {
        "gold_count": 0,
        "predicted_count": 0,
        "count_within_tolerance": 0,
        "id_precision": 0.0,
        "id_recall": 0.0,
        "id_f1": 0.0,
        "category_accuracy": 0.0,
        "severity_accuracy": 0.0,
        "resolution_accuracy": 0.0,
    }

    for case in cases:
        gold = [ReviewerConcern(**item) for item in case["gold_concerns"]]
        predicted = [ReviewerConcern(**item) for item in case["predicted_concerns"]]
        metrics = evaluate_extraction_against_gold(
            gold_concerns=gold,
            predicted_concerns=predicted,
            count_tolerance=case.get("count_tolerance", payload.get("count_tolerance", 2)),
        )
        print(f"\nCase: {case['case_id']}")
        print(f"  Description:       {case.get('description', '')}")
        print(f"  Gold concerns:     {metrics['gold_count']}")
        print(f"  Predicted concerns:{metrics['predicted_count']}")
        print(f"  Count delta:       {metrics['count_delta']:+d}")
        print(f"  Within tolerance:  {metrics['count_within_tolerance']}")
        print(f"  ID precision:      {metrics['id_precision']:.2%}")
        print(f"  ID recall:         {metrics['id_recall']:.2%}")
        print(f"  ID F1:             {metrics['id_f1']:.2%}")
        print(f"  Category accuracy: {metrics['category_accuracy']:.2%}")
        print(f"  Severity accuracy: {metrics['severity_accuracy']:.2%}")
        print(f"  Resolution acc.:   {metrics['resolution_accuracy']:.2%}")
        print(f"  Missing IDs:       {metrics['missing_ids']}")
        print(f"  Extra IDs:         {metrics['extra_ids']}")

        aggregate["gold_count"] += metrics["gold_count"]
        aggregate["predicted_count"] += metrics["predicted_count"]
        aggregate["count_within_tolerance"] += int(metrics["count_within_tolerance"])
        for key in ("id_precision", "id_recall", "id_f1", "category_accuracy", "severity_accuracy", "resolution_accuracy"):
            aggregate[key] += metrics[key]

    if cases:
        n = len(cases)
        aggregate_result = {
            "fixture_path": str(fixture_path),
            "case_count": n,
            "total_gold_concerns": aggregate["gold_count"],
            "total_predicted_concerns": aggregate["predicted_count"],
            "cases_within_tolerance": aggregate["count_within_tolerance"],
            "mean_id_precision": aggregate["id_precision"] / n,
            "mean_id_recall": aggregate["id_recall"] / n,
            "mean_id_f1": aggregate["id_f1"] / n,
            "mean_category_accuracy": aggregate["category_accuracy"] / n,
            "mean_severity_accuracy": aggregate["severity_accuracy"] / n,
            "mean_resolution_accuracy": aggregate["resolution_accuracy"] / n
        }
        print("\nAggregate:")
        print(f"  Total gold concerns:      {aggregate['gold_count']}")
        print(f"  Total predicted concerns: {aggregate['predicted_count']}")
        print(f"  Cases within tolerance:   {aggregate['count_within_tolerance']}/{n}")
        print(f"  Mean ID precision:        {aggregate['id_precision']/n:.2%}")
        print(f"  Mean ID recall:           {aggregate['id_recall']/n:.2%}")
        print(f"  Mean ID F1:               {aggregate['id_f1']/n:.2%}")
        print(f"  Mean category accuracy:   {aggregate['category_accuracy']/n:.2%}")
        print(f"  Mean severity accuracy:   {aggregate['severity_accuracy']/n:.2%}")
        print(f"  Mean resolution accuracy: {aggregate['resolution_accuracy']/n:.2%}")
        if args.save:
            EXTRACTION_EVAL_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_path = EXTRACTION_EVAL_DIR / f"w8_concern_extraction_eval_{ts}.json"
            artifact = {
                "schema_version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "fixture_path": str(fixture_path),
                "aggregate": aggregate_result,
                "cases": cases
            }
            out_path.write_text(json.dumps(artifact, indent=2))
            print(f"  Saved artifact:           {out_path}")


if __name__ == "__main__":
    main()
