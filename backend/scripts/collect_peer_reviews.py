"""Phase 6: Batch collect open peer review data and persist to DB.

Fetches eLife decision letters + author responses via PeerReviewCorpusClient,
parses XML with ELifeXMLParser, optionally extracts structured concerns via
ConcernParser (Haiku), and saves to the open_peer_review_entry table.

Usage:
    # Collect 50 eLife articles by subject (no concern extraction):
    uv run python backend/scripts/collect_peer_reviews.py --source elife --max 50

    # Collect with LLM concern extraction (~$0.002/article via Haiku):
    uv run python backend/scripts/collect_peer_reviews.py --source elife --max 20 --extract-concerns

    # Collect PLOS articles by DOI list file:
    uv run python backend/scripts/collect_peer_reviews.py --source plos --doi-file dois.txt

    # Dry-run (no DB writes, preview only):
    uv run python backend/scripts/collect_peer_reviews.py --source elife --max 5 --dry-run

    # Show corpus stats from existing DB:
    uv run python backend/scripts/collect_peer_reviews.py --stats

Output:
    DB table: open_peer_review_entry
    Log file: backend/data/peer_review_corpus/collection.log
    Stats:    backend/data/peer_review_corpus/STATS.md
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("collect_peer_reviews")

DATA_DIR = Path(__file__).parent.parent / "data" / "peer_review_corpus"

# eLife subject area identifiers
ELIFE_SUBJECTS = {
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


# ---------------------------------------------------------------------------
# eLife collection pipeline
# ---------------------------------------------------------------------------


async def collect_elife(
    subject: str | None,
    max_articles: int,
    start_date: str,
    extract_concerns: bool,
    dry_run: bool,
    llm_layer=None,
) -> list[dict]:
    """Collect eLife articles and parse their open peer review XML.

    Returns list of summary dicts (one per article).
    """
    from app.engines.review_corpus.concern_parser import ConcernParser
    from app.engines.review_corpus.xml_parser import ELifeXMLParser
    from app.integrations.peer_review_corpus import PeerReviewCorpusClient
    from app.models.review_corpus import OpenPeerReviewEntry

    client = PeerReviewCorpusClient()
    parser = ELifeXMLParser()
    concern_parser = ConcernParser(llm_layer=llm_layer if extract_concerns else None)

    elife_subject = ELIFE_SUBJECTS.get(subject or "", subject) if subject else ""

    logger.info(
        "Searching eLife (subject=%s, start_date=%s, max=%d)",
        elife_subject or "all",
        start_date,
        max_articles,
    )

    # Fetch article metadata list
    meta_list = await client.search_elife_articles(
        subject=elife_subject,
        start_date=start_date,
        page_size=min(max_articles, 100),
    )

    if not meta_list:
        logger.warning("No eLife articles returned for subject=%s", subject)
        return []

    results = []
    processed = 0
    skipped = 0

    for meta in meta_list:
        if processed >= max_articles:
            break

        article_id = str(meta.get("id", ""))
        doi = meta.get("doi", "")
        entry_id = f"elife:{article_id}"

        if not article_id:
            skipped += 1
            continue

        # Check if already in DB (avoid duplicates)
        if not dry_run and _entry_exists(entry_id):
            logger.debug("Skipping %s (already in DB)", entry_id)
            skipped += 1
            continue

        # Fetch review XML from eLife CDN
        xml_text = await client.get_elife_reviews_xml(article_id)
        if not xml_text:
            logger.debug("No review XML for eLife %s", article_id)
            skipped += 1
            continue

        # Parse XML
        parsed = parser.parse(xml_text)
        decision_letter = parsed["decision_letter"]
        author_response = parsed["author_response"]
        editorial_decision = parsed["editorial_decision"]

        if not decision_letter:
            logger.debug("Empty decision letter for eLife %s — skipping", article_id)
            skipped += 1
            continue

        # Optionally extract structured concerns (costs ~$0.002/article via Haiku)
        concerns = []
        if extract_concerns and llm_layer is not None:
            batch = await concern_parser.extract_concerns(
                article_id=entry_id,
                decision_letter=decision_letter,
                author_response=author_response,
            )
            concerns = batch.concerns
            logger.debug(
                "Extracted %d concerns from eLife %s (reviewers=%d)",
                len(concerns),
                article_id,
                batch.total_reviewers,
            )

        entry = OpenPeerReviewEntry(
            id=entry_id,
            source="elife",
            doi=doi,
            title=meta.get("title", ""),
            journal="eLife",
            published_year=meta.get("published_year"),
            decision_letter=decision_letter,
            author_response=author_response,
            editorial_decision=editorial_decision,
            collected_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        if concerns:
            entry.set_concerns(concerns)

        if not dry_run:
            _save_entry(entry)

        summary = {
            "id": entry_id,
            "doi": doi,
            "title": meta.get("title", "")[:80],
            "source": "elife",
            "editorial_decision": editorial_decision,
            "concerns_extracted": len(concerns),
            "dl_length": len(decision_letter),
            "ar_length": len(author_response),
        }
        results.append(summary)
        processed += 1
        logger.info(
            "[%d/%d] eLife %s → decision=%s, concerns=%d",
            processed,
            max_articles,
            article_id,
            editorial_decision,
            len(concerns),
        )

        # Rate-limit courtesy: 1 req/s for CDN
        await asyncio.sleep(0.5)

    logger.info(
        "eLife collection done: %d saved, %d skipped",
        len(results),
        skipped,
    )
    return results


# ---------------------------------------------------------------------------
# PLOS collection pipeline
# ---------------------------------------------------------------------------


async def collect_plos(
    doi_list: list[str],
    extract_concerns: bool,
    dry_run: bool,
    llm_layer=None,
) -> list[dict]:
    """Collect PLOS articles from a list of DOIs.

    PLOS embeds peer review text in JATS XML under <sec sec-type="peer-review">.
    """
    from app.engines.review_corpus.concern_parser import ConcernParser
    from app.engines.review_corpus.xml_parser import PLOSXMLParser
    from app.integrations.peer_review_corpus import PeerReviewCorpusClient
    from app.models.review_corpus import OpenPeerReviewEntry

    client = PeerReviewCorpusClient()
    parser = PLOSXMLParser()
    concern_parser = ConcernParser(llm_layer=llm_layer if extract_concerns else None)

    results = []
    skipped = 0

    for i, doi in enumerate(doi_list, 1):
        doi = doi.strip()
        if not doi:
            continue

        # Derive stable entry ID from DOI slug
        doi_slug = doi.replace("/", "_").replace(".", "-")
        entry_id = f"plos:{doi_slug}"

        if not dry_run and _entry_exists(entry_id):
            logger.debug("Skipping %s (already in DB)", entry_id)
            skipped += 1
            continue

        xml_text = await client.get_plos_review_xml(doi)
        if not xml_text:
            logger.debug("No PLOS XML for %s", doi)
            skipped += 1
            continue

        parsed = parser.parse(xml_text)
        decision_letter = parsed["decision_letter"]
        author_response = parsed["author_response"]
        editorial_decision = parsed["editorial_decision"]

        if not decision_letter:
            logger.debug("Empty peer review section for PLOS %s — skipping", doi)
            skipped += 1
            continue

        concerns = []
        if extract_concerns and llm_layer is not None:
            batch = await concern_parser.extract_concerns(
                article_id=entry_id,
                decision_letter=decision_letter,
                author_response=author_response,
            )
            concerns = batch.concerns

        entry = OpenPeerReviewEntry(
            id=entry_id,
            source="plos",
            doi=doi,
            title="",  # PLOS title not fetched here (would require separate API call)
            journal="PLOS ONE",
            collected_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            decision_letter=decision_letter,
            author_response=author_response,
            editorial_decision=editorial_decision,
        )
        if concerns:
            entry.set_concerns(concerns)

        if not dry_run:
            _save_entry(entry)

        summary = {
            "id": entry_id,
            "doi": doi,
            "title": "",
            "source": "plos",
            "editorial_decision": editorial_decision,
            "concerns_extracted": len(concerns),
            "dl_length": len(decision_letter),
            "ar_length": len(author_response),
        }
        results.append(summary)
        logger.info(
            "[%d/%d] PLOS %s → decision=%s, concerns=%d",
            i,
            len(doi_list),
            doi,
            editorial_decision,
            len(concerns),
        )

        await asyncio.sleep(0.3)

    logger.info(
        "PLOS collection done: %d saved, %d skipped",
        len(results),
        skipped,
    )
    return results


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _entry_exists(entry_id: str) -> bool:
    """Return True if an entry with this ID already exists in the DB."""
    try:
        from app.db import engine
        from app.models.review_corpus import OpenPeerReviewEntry
        from sqlmodel import Session, select

        with Session(engine) as session:
            existing = session.exec(
                select(OpenPeerReviewEntry).where(OpenPeerReviewEntry.id == entry_id)
            ).first()
            return existing is not None
    except Exception as e:
        logger.debug("DB existence check failed (%s): %s", entry_id, e)
        return False


def _save_entry(entry) -> None:
    """Upsert an OpenPeerReviewEntry to the database."""
    try:
        from app.db import engine
        from sqlmodel import Session

        with Session(engine) as session:
            session.merge(entry)
            session.commit()
    except Exception as e:
        logger.error("DB save failed for %s: %s", entry.id, e)


# ---------------------------------------------------------------------------
# Stats reporting
# ---------------------------------------------------------------------------


def show_db_stats() -> None:
    """Print corpus statistics from the open_peer_review_entry table."""
    try:
        from app.db import engine
        from app.models.review_corpus import OpenPeerReviewEntry
        from sqlmodel import Session, select

        with Session(engine) as session:
            entries = session.exec(select(OpenPeerReviewEntry)).all()

        if not entries:
            print("No entries in open_peer_review_entry table.")
            return

        total = len(entries)
        by_source: dict[str, int] = {}
        by_decision: dict[str, int] = {}
        with_concerns = 0
        with_w8 = 0

        for e in entries:
            by_source[e.source] = by_source.get(e.source, 0) + 1
            by_decision[e.editorial_decision] = by_decision.get(e.editorial_decision, 0) + 1
            concerns = e.get_concerns()
            if concerns:
                with_concerns += 1
            if e.w8_workflow_id:
                with_w8 += 1

        print(f"\n{'='*50}")
        print("Open Peer Review Corpus Stats")
        print(f"{'='*50}")
        print(f"Total entries:          {total}")
        print(f"With concerns extracted:{with_concerns}")
        print(f"With W8 benchmark run:  {with_w8}")
        print("\nBy source:")
        for src, cnt in sorted(by_source.items()):
            print(f"  {src:12s}: {cnt}")
        print("\nBy editorial decision:")
        for dec, cnt in sorted(by_decision.items(), key=lambda x: -x[1]):
            pct = cnt * 100 // total
            print(f"  {dec:20s}: {cnt:4d}  ({pct}%)")
        print(f"{'='*50}\n")

        # Write markdown report
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        report = DATA_DIR / "STATS.md"
        _write_stats_md(entries, by_source, by_decision, with_concerns, with_w8)
        print(f"Report saved to: {report}")

    except Exception as e:
        logger.error("Failed to load DB stats: %s", e)


def _write_stats_md(entries, by_source, by_decision, with_concerns, with_w8) -> None:
    """Write a markdown stats report."""
    total = len(entries)
    report_path = DATA_DIR / "STATS.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Open Peer Review Corpus",
        "",
        f"**Updated:** {now}  ",
        f"**Total entries:** {total}  ",
        f"**With concerns extracted:** {with_concerns}  ",
        f"**With W8 benchmark run:** {with_w8}  ",
        "",
        "## Source Distribution",
        "",
    ]
    for src, cnt in sorted(by_source.items()):
        lines.append(f"- **{src}**: {cnt} articles")

    lines += [
        "",
        "## Editorial Decision Distribution",
        "",
        "| Decision | Count | % |",
        "|----------|-------|---|",
    ]
    for dec, cnt in sorted(by_decision.items(), key=lambda x: -x[1]):
        pct = cnt * 100 // total
        lines.append(f"| {dec} | {cnt} | {pct}% |")

    lines += [
        "",
        "## Recent Entries (last 20)",
        "",
        "| ID | Source | Decision | Concerns |",
        "|----|--------|----------|----------|",
    ]
    for e in sorted(entries, key=lambda x: x.collected_at, reverse=True)[:20]:
        n_concerns = len(e.get_concerns())
        lines.append(f"| {e.id} | {e.source} | {e.editorial_decision} | {n_concerns} |")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Report collection results
# ---------------------------------------------------------------------------


def print_summary(results: list[dict], dry_run: bool) -> None:
    """Print a concise summary of the collection run."""
    if not results:
        print("\nNo articles collected.")
        return

    total = len(results)
    decisions: dict[str, int] = {}
    total_concerns = 0

    for r in results:
        dec = r.get("editorial_decision", "unknown")
        decisions[dec] = decisions.get(dec, 0) + 1
        total_concerns += r.get("concerns_extracted", 0)

    print(f"\n{'='*55}")
    print(f"Collection {'(DRY RUN — no DB writes) ' if dry_run else ''}complete!")
    print(f"Articles collected: {total}")
    print(f"Concerns extracted: {total_concerns}")
    print("Editorial decisions:")
    for dec, cnt in sorted(decisions.items(), key=lambda x: -x[1]):
        print(f"  {dec:20s}: {cnt}")
    print(f"{'='*55}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect open peer review data for W8 benchmark (Phase 6)"
    )
    parser.add_argument(
        "--source",
        choices=["elife", "plos"],
        default="elife",
        help="Source journal (default: elife)",
    )
    parser.add_argument(
        "--subject",
        default=None,
        help=f"eLife subject filter. Options: {', '.join(ELIFE_SUBJECTS)}",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=50,
        dest="max_articles",
        help="Max articles to collect (default: 50)",
    )
    parser.add_argument(
        "--start-date",
        default="2021-01-01",
        help="Earliest publication date for eLife search (default: 2021-01-01)",
    )
    parser.add_argument(
        "--doi-file",
        default=None,
        help="Path to file with one PLOS DOI per line (required for --source plos)",
    )
    parser.add_argument(
        "--extract-concerns",
        action="store_true",
        help="Use Haiku to extract structured concerns (~$0.002/article)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and log without writing to DB",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show corpus stats from DB and exit",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Stats-only mode
    if args.stats:
        show_db_stats()
        return

    # Initialise LLM layer if concern extraction requested
    llm_layer = None
    if args.extract_concerns:
        try:
            from app.llm.layer import LLMLayer

            llm_layer = LLMLayer()
            logger.info("LLM layer initialised for concern extraction (Haiku)")
        except Exception as e:
            logger.warning("Could not initialise LLM layer: %s — skipping extraction", e)

    # Run collection
    if args.source == "elife":
        results = await collect_elife(
            subject=args.subject,
            max_articles=args.max_articles,
            start_date=args.start_date,
            extract_concerns=args.extract_concerns,
            dry_run=args.dry_run,
            llm_layer=llm_layer,
        )
    else:
        # PLOS requires explicit DOI list
        if not args.doi_file:
            print("Error: --doi-file required for --source plos")
            sys.exit(1)
        doi_path = Path(args.doi_file)
        if not doi_path.exists():
            print(f"Error: DOI file not found: {doi_path}")
            sys.exit(1)
        doi_list = doi_path.read_text().splitlines()
        results = await collect_plos(
            doi_list=doi_list,
            extract_concerns=args.extract_concerns,
            dry_run=args.dry_run,
            llm_layer=llm_layer,
        )

    print_summary(results, dry_run=args.dry_run)

    # Save run log
    log_path = DATA_DIR / "collection.log"
    with open(log_path, "a") as f:
        f.write(
            json.dumps(
                {
                    "run_at": datetime.now(timezone.utc).isoformat(),
                    "source": args.source,
                    "subject": args.subject,
                    "max_articles": args.max_articles,
                    "extract_concerns": args.extract_concerns,
                    "dry_run": args.dry_run,
                    "collected": len(results),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    logger.info("Run log appended to %s", log_path)


if __name__ == "__main__":
    asyncio.run(main())
