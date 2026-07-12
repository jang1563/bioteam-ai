"""Refresh eLife corpus JSONs with full body_text + sections.

For articles already collected that only have body_text_preview (500 chars),
re-fetches the XML from eLife CDN and updates the corpus JSON in place.

Usage:
    uv run python backend/scripts/refresh_corpus_body.py
    uv run python backend/scripts/refresh_corpus_body.py --dry-run   # show what would be updated
    uv run python backend/scripts/refresh_corpus_body.py --max 10    # limit to N articles
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("refresh_corpus")

CORPUS_DIR = Path(__file__).parent.parent / "data" / "elife_corpus"


async def refresh_article(article_id: str, dry_run: bool = False) -> bool:
    """Re-fetch XML and update corpus JSON with full body_text + sections.

    Returns True if updated, False if already up-to-date or failed.
    """
    from app.integrations.elife_xml import ELifeXMLClient

    corpus_path = CORPUS_DIR / f"{article_id}.json"
    if not corpus_path.exists():
        logger.warning("No corpus JSON for %s", article_id)
        return False

    with open(corpus_path) as f:
        data = json.load(f)

    # Check if already has full body_text
    body_text = data.get("body_text", "")
    if body_text and len(body_text) > 500:
        logger.info("  %s: already has body_text (%d chars) — skipping", article_id, len(body_text))
        return False

    if dry_run:
        logger.info("  %s: would re-fetch XML (body_text missing or truncated)", article_id)
        return True

    logger.info("  %s: re-fetching XML...", article_id)

    try:
        async with ELifeXMLClient() as client:
            # First get metadata to find correct CDN XML URL
            meta = await client.fetch_article_metadata(article_id)
            article = await client.fetch_article(article_id, meta=meta)

        if article is None:
            logger.warning("  %s: fetch returned None", article_id)
            return False

        # Update corpus JSON with full body_text and sections
        data["body_text"] = article.body_text
        data["sections"] = [
            {"heading": s.title, "text": s.text, "section_type": s.section_type}
            for s in article.sections
        ]
        data["sections_count"] = len(article.sections)

        # Remove old preview field if present
        data.pop("body_text_preview", None)

        with open(corpus_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(
            "  %s: updated — body_text=%d chars, sections=%d",
            article_id,
            len(article.body_text),
            len(article.sections),
        )
        return True

    except Exception as e:
        logger.error("  %s: failed — %s", article_id, e)
        return False


async def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh eLife corpus JSONs with full body_text")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    parser.add_argument("--max", type=int, default=0, dest="max_articles", help="Max articles to refresh (0 = all)")
    args = parser.parse_args()

    manifest_path = CORPUS_DIR / "manifest.json"
    if not manifest_path.exists():
        print("No manifest found. Run collect_elife_corpus.py first.")
        return

    with open(manifest_path) as f:
        manifest = json.load(f)

    article_ids = [a["article_id"] for a in manifest.get("articles", [])]
    if args.max_articles > 0:
        article_ids = article_ids[:args.max_articles]

    logger.info("Refreshing %d corpus articles (dry_run=%s)", len(article_ids), args.dry_run)

    updated = 0
    skipped = 0
    failed = 0

    for article_id in article_ids:
        result = await refresh_article(article_id, dry_run=args.dry_run)
        if result:
            updated += 1
        else:
            # Check if it's already up-to-date
            path = CORPUS_DIR / f"{article_id}.json"
            if path.exists():
                with open(path) as f:
                    d = json.load(f)
                if len(d.get("body_text", "")) > 500:
                    skipped += 1
                else:
                    failed += 1

    print(f"\n{'='*50}")
    print("Refresh complete!")
    print(f"  Updated:  {updated}")
    print(f"  Skipped (already OK): {skipped}")
    print(f"  Failed:   {failed}")
    print(f"  Total:    {len(article_ids)}")


if __name__ == "__main__":
    asyncio.run(main())
