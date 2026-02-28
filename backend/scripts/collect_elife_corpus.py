"""Phase 1-B: Bulk collect eLife open peer review articles.

Fetches eLife articles with decision letters + author responses via the
ELifeXMLClient, saves them to backend/data/elife_corpus/ as JSON files,
and writes a manifest for downstream processing.

Usage:
    # Collect 50 articles from all subjects (default)
    uv run python backend/scripts/collect_elife_corpus.py

    # Collect 20 immunology articles
    uv run python backend/scripts/collect_elife_corpus.py --subject immunology --max 20

    # Collect from a specific ID range (recent papers)
    uv run python backend/scripts/collect_elife_corpus.py --start-id 80000 --end-id 110000 --max 50

    # Report only (show manifest without fetching)
    uv run python backend/scripts/collect_elife_corpus.py --report-only

Output:
    backend/data/elife_corpus/{article_id}.json   ← article + DL + AR
    backend/data/elife_corpus/manifest.json        ← collection index
    backend/data/elife_corpus/CORPUS_STATS.md      ← summary report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("collect_elife")

CORPUS_DIR = Path(__file__).parent.parent / "data" / "elife_corpus"

# eLife subject area IDs (from eLife API taxonomy)
SUBJECT_MAP = {
    "immunology": "immunology-inflammation",
    "cell-biology": "cell-biology",
    "cancer": "cancer-biology",
    "genetics": "genetics-genomics",
    "neuroscience": "neuroscience",
    "microbiology": "microbiology-infectious-disease",
    "biochemistry": "biochemistry-chemical-biology",
    "evolutionary": "evolutionary-biology",
    "structural": "structural-biology-molecular-biophysics",
    "developmental": "developmental-biology",
    "medicine": "medicine",
    "computational": "computational-systems-biology",
    "ecology": "ecology",
    "plant-biology": "plant-biology",
    "stem-cell": "stem-cells-regenerative-medicine",
}

# Phase 0 pilot papers — skip these (already collected)
PILOT_IDS = {"85560", "83069", "11058", "107189", "00969", "969"}


async def collect_corpus(
    subject: str | None,
    max_articles: int,
    start_id: int,
    end_id: int,
    require_author_response: bool,
    resume: bool,
) -> list[dict]:
    """Collect eLife articles with open peer review data."""
    from app.integrations.elife_xml import ELifeXMLClient

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing manifest if resuming
    existing_ids: set[str] = set()
    manifest_path = CORPUS_DIR / "manifest.json"
    if resume and manifest_path.exists():
        with open(manifest_path) as f:
            existing = json.load(f)
        existing_ids = {str(e["article_id"]) for e in existing.get("articles", [])}
        logger.info("Resume mode: %d articles already collected", len(existing_ids))

    skip_ids = PILOT_IDS | existing_ids
    collected: list[dict] = []

    # Map subject alias to eLife subject ID
    elife_subject = SUBJECT_MAP.get(subject or "", subject) if subject else None

    logger.info(
        "Collecting up to %d eLife articles (IDs %d→%d, subject=%s)",
        max_articles,
        end_id,
        start_id,
        elife_subject or "all",
    )

    async with ELifeXMLClient(rate_limit_delay=1.2) as client:
        articles = await client.fetch_reviewed_articles(
            subject=elife_subject,
            max_articles=max_articles + len(skip_ids),  # overfetch to account for skips
            start_id=start_id,
            end_id=end_id,
            require_author_response=require_author_response,
        )

    # Filter and save
    saved = 0
    for article in articles:
        if saved >= max_articles:
            break
        if article.article_id in skip_ids:
            logger.debug("Skipping already-collected article %s", article.article_id)
            continue

        out_path = CORPUS_DIR / f"{article.article_id}.json"
        data = article.to_ground_truth()
        data["body_text_preview"] = article.body_text[:500]
        data["sections_count"] = len(article.sections)
        data["collected_at"] = datetime.now(timezone.utc).isoformat()

        with open(out_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        collected.append({
            "article_id": article.article_id,
            "doi": article.doi,
            "title": article.title[:120],
            "subjects": article.subjects[:3],
            "pub_date": article.pub_date,
            "dl_length": len(article.decision_letter),
            "ar_length": len(article.author_response),
            "has_author_response": article.has_author_response,
            "path": str(out_path.relative_to(CORPUS_DIR.parent.parent)),
        })
        saved += 1
        logger.info("[%d/%d] Saved %s — %s", saved, max_articles, article.article_id, article.title[:60])

    return collected


def update_manifest(new_articles: list[dict]) -> dict:
    """Merge new articles into the manifest file."""
    manifest_path = CORPUS_DIR / "manifest.json"

    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "articles": [],
            "stats": {},
        }

    # Merge (avoid duplicates)
    existing_ids = {a["article_id"] for a in manifest["articles"]}
    for a in new_articles:
        if a["article_id"] not in existing_ids:
            manifest["articles"].append(a)

    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["stats"] = _compute_stats(manifest["articles"])

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return manifest


def _compute_stats(articles: list[dict]) -> dict:
    if not articles:
        return {}

    dl_lengths = [a["dl_length"] for a in articles]
    ar_lengths = [a["ar_length"] for a in articles]
    with_ar = sum(1 for a in articles if a["has_author_response"])

    # Subject distribution
    subject_counts: dict[str, int] = {}
    for a in articles:
        for subj in a.get("subjects", []):
            subject_counts[subj] = subject_counts.get(subj, 0) + 1

    return {
        "total_articles": len(articles),
        "with_author_response": with_ar,
        "avg_dl_length": int(sum(dl_lengths) / len(dl_lengths)),
        "avg_ar_length": int(sum(ar_lengths) / len(ar_lengths)) if ar_lengths else 0,
        "subject_distribution": dict(sorted(subject_counts.items(), key=lambda x: -x[1])[:10]),
    }


def write_stats_report(manifest: dict) -> None:
    """Write a markdown summary of the corpus."""
    stats = manifest.get("stats", {})
    articles = manifest.get("articles", [])
    report_path = CORPUS_DIR / "CORPUS_STATS.md"

    lines = [
        "# eLife Open Peer Review Corpus",
        "",
        f"**Updated:** {manifest.get('updated_at', 'N/A')}",
        f"**Total articles:** {stats.get('total_articles', 0)}",
        f"**With author response:** {stats.get('with_author_response', 0)}",
        f"**Avg decision letter length:** {stats.get('avg_dl_length', 0):,} chars",
        f"**Avg author response length:** {stats.get('avg_ar_length', 0):,} chars",
        "",
        "## Subject Distribution",
        "",
    ]
    for subj, count in stats.get("subject_distribution", {}).items():
        lines.append(f"- {subj}: {count}")

    lines += [
        "",
        "## Article List",
        "",
        "| ID | Title | Subjects | DL | AR |",
        "|----|-------|----------|----|----|",
    ]
    for a in articles[:100]:
        title = a["title"][:60]
        subjects = ", ".join(a.get("subjects", [])[:2])
        dl = f"{a['dl_length']:,}"
        ar = f"{a['ar_length']:,}" if a["has_author_response"] else "—"
        lines.append(f"| {a['article_id']} | {title} | {subjects} | {dl} | {ar} |")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))

    logger.info("Stats report written to %s", report_path)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Collect eLife open peer review corpus")
    parser.add_argument("--subject", default=None,
                        help=f"Filter by subject ({', '.join(SUBJECT_MAP)})")
    parser.add_argument("--max", type=int, default=50, dest="max_articles",
                        help="Maximum articles to collect (default: 50)")
    parser.add_argument("--start-id", type=int, default=1,
                        help="Starting eLife article ID (default: 1)")
    parser.add_argument("--end-id", type=int, default=110000,
                        help="Ending eLife article ID (default: 110000)")
    parser.add_argument("--require-ar", action="store_true",
                        help="Only collect articles with author responses")
    parser.add_argument("--resume", action="store_true",
                        help="Skip already-collected articles (resume mode)")
    parser.add_argument("--report-only", action="store_true",
                        help="Show existing manifest stats without fetching")
    args = parser.parse_args()

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    if args.report_only:
        manifest_path = CORPUS_DIR / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            write_stats_report(manifest)
            stats = manifest.get("stats", {})
            print("\n=== Corpus Stats ===")
            print(f"Total articles: {stats.get('total_articles', 0)}")
            print(f"With author response: {stats.get('with_author_response', 0)}")
            print(f"Avg DL length: {stats.get('avg_dl_length', 0):,} chars")
        else:
            print("No manifest found. Run without --report-only to collect articles.")
        return

    new_articles = await collect_corpus(
        subject=args.subject,
        max_articles=args.max_articles,
        start_id=args.start_id,
        end_id=args.end_id,
        require_author_response=args.require_ar,
        resume=args.resume,
    )

    if not new_articles:
        logger.warning("No new articles collected.")
        return

    manifest = update_manifest(new_articles)
    write_stats_report(manifest)

    stats = manifest["stats"]
    print(f"\n{'='*60}")
    print("Collection complete!")
    print(f"New articles: {len(new_articles)}")
    print(f"Total corpus: {stats.get('total_articles', 0)}")
    print(f"With author response: {stats.get('with_author_response', 0)}")
    print(f"Corpus directory: {CORPUS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
