"""Build P2 Contradiction Taxonomy Corpus (150 labeled pairs).

Pipeline (PubMed-standalone mode — no W1 / ChromaDB required):

  Phase 1: PubMed fetch — 15 queries × 40 papers = ~600 papers (FREE)
  Phase 2: Contradiction pre-screening — marker matching, all-pairs (FREE)
  Phase 3: Haiku classification — 5-type taxonomy (PAID ~$0.60)
  Phase 4: Quality filter + balance — 30 per type, sorted by confidence (FREE)
  Phase 5: JSONL export (FREE)

Usage:
    # Dry run — PubMed fetch + pre-screening only (no Haiku, $0)
    uv run python backend/scripts/build_contradiction_corpus.py --dry-run

    # Full run
    uv run python backend/scripts/build_contradiction_corpus.py \
        --output data/contradiction_corpus/corpus_150.jsonl \
        --target-per-type 30 \
        --min-per-type 20

    # Full run with custom max papers per query
    uv run python backend/scripts/build_contradiction_corpus.py \
        --max-per-query 60 \
        --output data/contradiction_corpus/corpus_150.jsonl
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# ── Path setup ───────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

load_dotenv(_REPO_ROOT / ".env")

from app.integrations.pubmed import PubMedClient, PubMedPaper  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("corpus_builder")

# ── Query corpus ──────────────────────────────────────────────────────────────

QUERIES: dict[str, list[str]] = {
    "spaceflight": [
        "spaceflight muscle atrophy mechanism microgravity",
        "spaceflight bone density loss rate microgravity",
        "spaceflight immune suppression activation lymphocyte",
        "spaceflight anemia erythropoiesis red blood cell",
        "circadian rhythm spaceflight disruption recovery",
    ],
    "cancer_genomics": [
        "KRAS G12C drug resistance mechanism sotorasib",
        "TP53 mutation cancer prognosis outcome survival",
        "tumor heterogeneity clonal evolution driver mutation",
        "BRCA1 BRCA2 DNA repair function homologous recombination",
        "mTOR inhibitor cancer cell proliferation apoptosis",
    ],
    "neuroscience": [
        "BDNF neuroplasticity depression mechanism",
        "tau phosphorylation Alzheimer disease cause consequence",
        "synaptic plasticity LTP LTD memory consolidation",
        "neuroinflammation neuroprotection microglia activation",
        "adult neurogenesis hippocampus cognitive function behavior",
    ],
}

CONTRADICTION_MARKERS: list[tuple[str, str]] = [
    ("increase", "decrease"),
    ("upregulate", "downregulate"),
    ("upregulated", "downregulated"),
    ("promote", "inhibit"),
    ("promotes", "inhibits"),
    ("activate", "suppress"),
    ("activates", "suppresses"),
    ("enhance", "reduce"),
    ("enhances", "reduces"),
    ("positive", "negative"),
    ("significant", "not significant"),
    ("significantly", "no significant"),
    ("required", "dispensable"),
    ("elevated", "reduced"),
    ("elevated", "unchanged"),
    ("increased", "decreased"),
    ("increased", "unchanged"),
    ("higher", "lower"),
    ("greater", "lesser"),
    ("stimulates", "inhibits"),
    ("induce", "suppress"),
    ("induces", "suppresses"),
]

# ── Data models ───────────────────────────────────────────────────────────────

ContradictionType = Literal[
    "direct",
    "contextual",
    "methodological",
    "temporal",
    "magnitude",
]


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
    detected_by: str  # "marker_match"
    pre_screen_score: float = 0.7


class ContradictionTypeLabel(BaseModel):
    """Structured output from Haiku — one per candidate pair."""

    contradiction_type: ContradictionType
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
    # Annotation fields — filled by 2 annotators
    annotator_1_type: str | None = None
    annotator_2_type: str | None = None
    final_type: str | None = None
    curation_notes: str | None = None


# ── Haiku prompt ──────────────────────────────────────────────────────────────

_HAIKU_SYSTEM = """\
You are a biomedical literature expert. Determine whether two scientific claims
genuinely contradict each other and classify the type of contradiction.

CONTRADICTION TYPES:
- direct: Same experimental conditions, same organism/cell type, opposite conclusions.
- contextual: Results differ due to different biological context (species, cell type,
  tissue, patient population). Context explains the difference — not a true contradiction.
- methodological: Different measurement methods or assays produce opposite results.
- temporal: Results differ due to different time point, developmental stage, or disease phase.
- magnitude: Same direction but contradictory effect size or statistical significance.

DECISION RULES:
1. If the biological context fully explains the difference (different species, cell type,
   disease model) → is_genuine_contradiction=false, type=contextual.
2. If both claims address the same context but opposite conclusions → is_genuine_contradiction=true.
3. Assign the SINGLE most specific type (contextual > methodological > temporal > direct/magnitude).
4. Confidence: 0.9+ = clear, 0.7-0.89 = probable, <0.7 = uncertain.

Respond with a JSON object matching this schema:
{
  "contradiction_type": "<direct|contextual|methodological|temporal|magnitude>",
  "confidence": <0.0-1.0>,
  "rationale": "<1-2 sentences>",
  "is_genuine_contradiction": <true|false>,
  "suggested_resolution": "<optional hypothesis for why both could be true, or null>"
}
"""

_HAIKU_USER_TEMPLATE = """\
Domain: {domain}

Claim A (PMID {pmid_a}, {year_a}):
{claim_a}

Claim B (PMID {pmid_b}, {year_b}):
{claim_b}

Classify this pair."""


# ── Phase 1: PubMed fetch ─────────────────────────────────────────────────────

def fetch_papers(
    queries: dict[str, list[str]],
    max_per_query: int = 40,
) -> dict[str, list[PubMedPaper]]:
    """Fetch abstracts from PubMed for all queries.

    Returns: domain → list of papers (some may have empty abstracts).
    """
    client = PubMedClient()
    results: dict[str, list[PubMedPaper]] = defaultdict(list)
    seen_pmids: set[str] = set()

    for domain, domain_queries in queries.items():
        for query in domain_queries:
            logger.info("PubMed search: [%s] %r", domain, query)
            try:
                papers = client.search(query, max_results=max_per_query, sort="relevance")
                time.sleep(0.35)  # NCBI rate limit (3 req/sec without API key)
            except Exception as exc:
                logger.warning("PubMed search failed for %r: %s", query, exc)
                continue

            new = 0
            for paper in papers:
                if not paper.abstract:
                    continue
                if paper.pmid in seen_pmids:
                    continue
                seen_pmids.add(paper.pmid)
                # Attach query source to paper for tracing
                paper._query_source = query  # type: ignore[attr-defined]
                paper._domain = domain  # type: ignore[attr-defined]
                results[domain].append(paper)
                new += 1

            logger.info("  → %d new papers with abstracts", new)

    total = sum(len(v) for v in results.values())
    logger.info("Phase 1 complete: %d papers total across %d domains", total, len(results))
    return dict(results)


# ── Phase 2: Contradiction pre-screening ──────────────────────────────────────

def _has_marker(text_a: str, text_b: str) -> bool:
    """True if any marker pair appears (one term in A, other in B)."""
    a = text_a.lower()
    b = text_b.lower()
    for term_a, term_b in CONTRADICTION_MARKERS:
        if (term_a in a and term_b in b) or (term_b in a and term_a in b):
            return True
    return False


def _abstract_sentences(abstract: str) -> list[str]:
    """Split abstract into sentences (rough split on '. ')."""
    import re
    # Split on ". " followed by capital letter — catches most sentence boundaries
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", abstract)
    return [s.strip() for s in sents if len(s.strip()) > 40]


def find_candidate_pairs(
    papers_by_domain: dict[str, list[PubMedPaper]],
    max_pairs: int = 800,
) -> list[CandidatePair]:
    """Find cross-paper sentence pairs that contain contradiction markers.

    Strategy:
    - Per-domain cap = max_pairs // n_domains to ensure balanced domain coverage.
    - For each domain, cross-compare sentences from DIFFERENT papers.
    - Avoid same-paper pairs (circular).
    """
    n_domains = len(papers_by_domain)
    per_domain_cap = max_pairs // n_domains if n_domains else max_pairs

    candidates: list[CandidatePair] = []
    pair_counter = 0

    for domain, papers in papers_by_domain.items():
        logger.info("Pre-screening domain: %s (%d papers, cap=%d)", domain, len(papers), per_domain_cap)

        # Build sentence list with paper attribution
        paper_sentences: list[tuple[str, PubMedPaper]] = []
        for paper in papers:
            for sent in _abstract_sentences(paper.abstract):
                paper_sentences.append((sent, paper))

        # Cross-paper pairs only (i.e., different PMIDs)
        found_in_domain = 0
        for (sent_a, paper_a), (sent_b, paper_b) in combinations(paper_sentences, 2):
            if paper_a.pmid == paper_b.pmid:
                continue
            if _has_marker(sent_a, sent_b):
                pair_counter += 1
                pair_id = f"CP-{pair_counter:04d}"
                query_src = getattr(paper_a, "_query_source", "unknown")
                candidates.append(CandidatePair(
                    pair_id=pair_id,
                    domain=domain,
                    query_source=query_src,
                    claim_a=ClaimRecord(
                        text=sent_a,
                        source_pmid=paper_a.pmid,
                        source_doi=paper_a.doi,
                        paper_title=paper_a.title,
                        year=paper_a.year,
                    ),
                    claim_b=ClaimRecord(
                        text=sent_b,
                        source_pmid=paper_b.pmid,
                        source_doi=paper_b.doi,
                        paper_title=paper_b.title,
                        year=paper_b.year,
                    ),
                    detected_by="marker_match",
                ))
                found_in_domain += 1
                if found_in_domain >= per_domain_cap:
                    break

        logger.info("  → %d candidate pairs", found_in_domain)

    logger.info("Phase 2 complete: %d candidate pairs total", len(candidates))
    return candidates


# ── Phase 3: Haiku classification ─────────────────────────────────────────────

async def _classify_one(
    client: anthropic.AsyncAnthropic,
    pair: CandidatePair,
    sem: asyncio.Semaphore,
) -> tuple[CandidatePair, ContradictionTypeLabel | None]:
    """Classify a single pair with Haiku. Returns (pair, label | None)."""
    prompt = _HAIKU_USER_TEMPLATE.format(
        domain=pair.domain,
        pmid_a=pair.claim_a.source_pmid,
        year_a=pair.claim_a.year,
        claim_a=pair.claim_a.text,
        pmid_b=pair.claim_b.source_pmid,
        year_b=pair.claim_b.year,
        claim_b=pair.claim_b.text,
    )

    async with sem:
        for attempt in range(3):
            try:
                resp = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=512,
                    temperature=0.0,
                    system=_HAIKU_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = resp.content[0].text.strip()
                # Strip markdown code fences if present
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                data = json.loads(raw)
                label = ContradictionTypeLabel(**data)
                return pair, label
            except Exception as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning("Haiku failed for %s: %s", pair.pair_id, exc)
                    return pair, None


async def classify_all(
    pairs: list[CandidatePair],
    concurrency: int = 8,
) -> list[tuple[CandidatePair, ContradictionTypeLabel | None]]:
    """Classify all pairs concurrently with Haiku."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    sem = asyncio.Semaphore(concurrency)

    logger.info("Phase 3: Classifying %d pairs with Haiku (concurrency=%d)...", len(pairs), concurrency)

    tasks = [_classify_one(client, pair, sem) for pair in pairs]
    results: list[tuple[CandidatePair, ContradictionTypeLabel | None]] = []

    for i, coro in enumerate(asyncio.as_completed(tasks), 1):
        result = await coro
        results.append(result)
        if i % 50 == 0:
            logger.info("  Classified %d / %d pairs", i, len(pairs))

    logger.info("Phase 3 complete: %d classified, %d failed",
                sum(1 for _, l in results if l is not None),
                sum(1 for _, l in results if l is None))
    return results


# ── Phase 4: Filter + balance ─────────────────────────────────────────────────

def filter_and_balance(
    classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]],
    target_per_type: int = 30,
    min_per_type: int = 20,
    confidence_threshold: float = 0.65,
) -> tuple[list[CorpusEntry], dict]:
    """Filter genuine contradictions and select balanced 150-entry corpus.

    Returns:
        (selected_entries, stats_dict)
    """
    all_types: list[ContradictionType] = ["direct", "contextual", "methodological", "temporal", "magnitude"]

    # Pool: genuine + confident
    by_type: dict[str, list[tuple[CandidatePair, ContradictionTypeLabel]]] = defaultdict(list)
    n_not_genuine = 0
    n_low_confidence = 0
    n_failed = 0

    for pair, label in classified:
        if label is None:
            n_failed += 1
            continue
        if not label.is_genuine_contradiction:
            n_not_genuine += 1
            continue
        if label.confidence < confidence_threshold:
            n_low_confidence += 1
            continue
        by_type[label.contradiction_type].append((pair, label))

    # Sort each type pool by confidence (highest first)
    for t in all_types:
        by_type[t].sort(key=lambda x: x[1].confidence, reverse=True)

    # Select up to target_per_type per type
    selected: list[CorpusEntry] = []
    entry_counter = 0
    stats: dict[str, int] = {}

    for t in all_types:
        pool = by_type[t]
        take = min(target_per_type, len(pool))
        stats[t] = take

        if take < min_per_type:
            logger.warning(
                "Type '%s': only %d entries available (min=%d). "
                "Consider increasing --max-per-query.",
                t, take, min_per_type,
            )

        for pair, label in pool[:take]:
            entry_counter += 1
            entry_id = f"CT-{entry_counter:03d}"
            selected.append(CorpusEntry(
                entry_id=entry_id,
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
        "total_classified": len(classified),
        "failed": n_failed,
        "not_genuine": n_not_genuine,
        "low_confidence": n_low_confidence,
        "genuine_pool_size": sum(len(v) for v in by_type.values()),
        "selected": len(selected),
        "by_type": stats,
        "shortfall_types": [t for t in all_types if stats.get(t, 0) < min_per_type],
    }

    return selected, stats_out


# ── Phase 5: Export ───────────────────────────────────────────────────────────

def export_jsonl(entries: list[CorpusEntry], output_path: Path) -> None:
    """Write corpus entries to JSONL (one entry per line)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.model_dump_json() + "\n")
    logger.info("Exported %d entries → %s", len(entries), output_path)


def export_candidates_jsonl(
    classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]],
    output_path: Path,
) -> None:
    """Write all classified pairs (for transparency / debugging)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for pair, label in classified:
            row = {
                "pair_id": pair.pair_id,
                "domain": pair.domain,
                "query_source": pair.query_source,
                "claim_a": pair.claim_a.model_dump(),
                "claim_b": pair.claim_b.model_dump(),
                "label": label.model_dump() if label else None,
            }
            f.write(json.dumps(row) + "\n")
    logger.info("Exported %d candidate pairs → %s", len(classified), output_path)


# ── Main ──────────────────────────────────────────────────────────────────────

def _print_stats(stats: dict, candidates: list[CandidatePair]) -> None:
    print("\n" + "=" * 60)
    print("CORPUS BUILDING STATS")
    print("=" * 60)
    print(f"Candidate pairs (pre-screen):  {len(candidates)}")
    print(f"Total classified by Haiku:     {stats['total_classified']}")
    print(f"  Failed (API error):          {stats['failed']}")
    print(f"  Not genuine:                 {stats['not_genuine']}")
    print(f"  Low confidence (<0.65):      {stats['low_confidence']}")
    print(f"  Genuine pool:                {stats['genuine_pool_size']}")
    print(f"\nSelected for corpus:           {stats['selected']}")
    print("\nBy type:")
    for t, n in stats.get("by_type", {}).items():
        flag = " ⚠ SHORTFALL" if t in stats.get("shortfall_types", []) else ""
        print(f"  {t:<20} {n:>3}{flag}")
    if stats.get("shortfall_types"):
        print(f"\n⚠  Shortfall types: {stats['shortfall_types']}")
        print("   → Re-run with --max-per-query 80 to get more candidates")
    print("=" * 60 + "\n")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build P2 Contradiction Taxonomy Corpus (150 labeled pairs)",
    )
    parser.add_argument(
        "--output",
        default="data/contradiction_corpus/corpus_150.jsonl",
        help="Output path for final 150-entry corpus",
    )
    parser.add_argument(
        "--max-per-query",
        type=int,
        default=40,
        help="Max papers to fetch per PubMed query (default: 40)",
    )
    parser.add_argument(
        "--target-per-type",
        type=int,
        default=30,
        help="Target corpus entries per contradiction type (default: 30)",
    )
    parser.add_argument(
        "--min-per-type",
        type=int,
        default=20,
        help="Minimum acceptable entries per type (default: 20)",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.65,
        help="Minimum Haiku confidence to include a pair (default: 0.65)",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=800,
        help="Max candidate pairs to send to Haiku (default: 800)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Phase 1+2 only (PubMed + pre-screening, no Haiku, $0 cost)",
    )
    args = parser.parse_args()

    output_path = _REPO_ROOT / args.output
    candidates_path = output_path.parent / "candidates_all.jsonl"
    stats_path = output_path.parent / "build_stats.json"

    # Phase 1
    papers_by_domain = fetch_papers(QUERIES, max_per_query=args.max_per_query)

    # Phase 2
    candidates = find_candidate_pairs(papers_by_domain, max_pairs=args.max_pairs)

    if args.dry_run:
        print(f"\nDRY RUN complete. Found {len(candidates)} candidate pairs.")
        print("No Haiku calls made. Re-run without --dry-run to classify.")
        by_domain: dict[str, int] = defaultdict(int)
        for c in candidates:
            by_domain[c.domain] += 1
        for domain, count in sorted(by_domain.items()):
            print(f"  {domain}: {count} pairs")
        return

    # Phase 3
    classified = asyncio.run(classify_all(candidates))

    # Save all candidates (for debugging)
    export_candidates_jsonl(classified, candidates_path)

    # Phase 4
    selected, stats = filter_and_balance(
        classified,
        target_per_type=args.target_per_type,
        min_per_type=args.min_per_type,
        confidence_threshold=args.confidence_threshold,
    )
    _print_stats(stats, candidates)

    # Phase 5
    export_jsonl(selected, output_path)

    # Save stats
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    logger.info("Stats saved → %s", stats_path)


if __name__ == "__main__":
    main()
