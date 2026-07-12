"""Build a balanced contradiction corpus v2 using type-specific PubMed queries.

Strategy:
- direct / methodological / temporal / magnitude: type-specific PubMed queries
- contextual: reuse 30 existing entries from corpus_150.jsonl (Phase 1 output)
- Phase 1: PubMed fetch per type (free, NCBI E-utilities)
- Phase 2: candidate pair extraction (marker-based, cross-paper)
- Phase 3: Gemini 2.5 Flash classification with type-hint (free)
- Phase 4: filter + balance (target 20/type, min 15/type)

Usage:
    export GEMINI_API_KEY=<your-key>
    # dry run (skip Gemini):
    uv run python backend/scripts/build_corpus_v2.py --dry-run
    # full run:
    uv run python backend/scripts/build_corpus_v2.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("corpus_v2")

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))

from app.integrations.pubmed import PubMedClient, PubMedPaper  # noqa: E402

# ── Output paths ──────────────────────────────────────────────────────────────

_OUT = _REPO / "backend/scripts/output/v2"

# ── Type-specific PubMed queries ──────────────────────────────────────────────

TYPE_QUERIES: dict[str, list[str]] = {
    "direct": [
        '"failed to replicate" AND (gene OR protein) AND (cancer OR disease)',
        '"opposite results" AND (cell line OR in vitro) AND (gene expression OR protein)',
        '"in direct contradiction" AND (biology OR genomics OR cell)',
        '"contradicts previous" AND (study OR findings) AND (molecular OR cellular)',
        '"conflicting results" AND (same cell line OR identical conditions) AND gene',
        '"opposite direction" AND (expression OR activity) AND (same cell type OR same model)',
    ],
    "methodological": [
        '"RNA-seq" AND "microarray" AND ("discordant" OR "conflicting" OR "different results")',
        '"single-cell" AND "bulk RNA" AND ("discrepancy" OR "contradictory" OR "inconsistent")',
        '"ChIP-seq" AND "ChIP-qPCR" AND ("inconsistent" OR "conflicting" OR "different")',
        '"whole genome sequencing" AND "exome sequencing" AND discordant',
        '"platform-dependent" AND (genomics OR transcriptomics OR proteomics)',
        '"assay-dependent" AND (binding OR activity OR expression)',
        '"method-dependent" AND (result OR finding OR conclusion)',
    ],
    "temporal": [
        '"acute" AND "chronic" AND "opposite" AND (response OR effect OR regulation)',
        '"longitudinal" AND "conflicting" AND (biomarker OR gene OR protein)',
        '"time-dependent" AND "reversal" AND (expression OR activation OR inhibition)',
        '"early" AND "late" AND "opposite effects" AND (treatment OR disease OR condition)',
        '"initial response" AND "subsequent" AND "reversed" AND (drug OR therapy)',
        '"short-term" AND "long-term" AND ("opposite" OR "conflicting") AND (effect OR result)',
    ],
    "magnitude": [
        '"overestimated" AND (effect size OR odds ratio OR risk) AND (study OR trial)',
        '"high heterogeneity" AND "meta-analysis" AND (I2 OR inconsistency)',
        '"odds ratio" AND "conflicting" AND (exposure OR risk factor) AND disease',
        '"effect size" AND "discrepancy" AND (replication OR validation OR study)',
        '"significantly larger" AND "significantly smaller" AND same AND (treatment OR drug)',
        '"inflated" AND (effect OR association OR estimate) AND (study OR publication)',
    ],
}

# Papers per query (keep low to stay fast and get diverse pairs)
MAX_PER_QUERY = 30
# Max candidate pairs per type (before Gemini)
MAX_PAIRS_PER_TYPE = 200

# ── Contradiction markers for pair extraction ─────────────────────────────────

CONTRADICTION_MARKERS: list[tuple[str, str]] = [
    ("increase", "decrease"), ("upregulate", "downregulate"),
    ("activate", "inhibit"), ("promote", "suppress"),
    ("enhance", "reduce"), ("stimulate", "block"),
    ("higher", "lower"), ("greater", "lesser"),
    ("positive", "negative"), ("agonist", "antagonist"),
    ("overexpressed", "underexpressed"), ("elevated", "reduced"),
    ("significant", "nonsignificant"), ("associated", "not associated"),
    ("protect", "exacerbate"), ("improve", "worsen"),
]

# ── Data models ───────────────────────────────────────────────────────────────

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
    intended_type: str  # v2: type-hint from acquisition


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
    haiku_confidence: float   # field name kept for schema compat; value is Gemini's
    haiku_rationale: str
    is_genuine: bool
    suggested_resolution: str | None = None
    annotator_1_type: str | None = None
    annotator_2_type: str | None = None
    final_type: str | None = None
    curation_notes: str | None = None


# ── PubMed Phase 1 (via existing PubMedClient) ───────────────────────────────

def fetch_papers_for_type(ctype: str, queries: list[str]) -> list[dict]:
    """Phase 1: Fetch papers via type-specific queries using PubMedClient."""
    client = PubMedClient()
    seen_pmids: set[str] = set()
    papers: list[dict] = []

    for query in queries:
        try:
            results: list[PubMedPaper] = client.search(
                query, max_results=MAX_PER_QUERY, sort="relevance"
            )
            time.sleep(0.35)  # NCBI rate limit
        except Exception as e:
            logger.warning("[%s] PubMed search failed for %r: %s", ctype, query[:50], e)
            continue

        new = 0
        for paper in results:
            if not paper.abstract or paper.pmid in seen_pmids:
                continue
            seen_pmids.add(paper.pmid)
            papers.append({
                "pmid": paper.pmid,
                "title": paper.title,
                "abstract": paper.abstract,
                "year": str(paper.year) if paper.year else "",
                "doi": paper.doi or "",
                "query_source": query[:60],
            })
            new += 1

        logger.info("  [%s] query=%r → %d new papers (total %d)",
                    ctype, query[:50], new, len(papers))

    logger.info("[%s] Phase 1 complete: %d unique papers", ctype, len(papers))
    return papers


# ── Phase 2: Candidate pair extraction ───────────────────────────────────────

def _extract_sentences(text: str, max_sentences: int = 8) -> list[str]:
    """Extract sentences from abstract text."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 30][:max_sentences]


def _has_contradiction_marker(sent_a: str, sent_b: str) -> bool:
    """Check if two sentences have opposing marker terms."""
    a_low = sent_a.lower()
    b_low = sent_b.lower()
    for term_a, term_b in CONTRADICTION_MARKERS:
        if (term_a in a_low and term_b in b_low) or (term_b in a_low and term_a in b_low):
            return True
    return False


def find_candidate_pairs(
    papers: list[dict],
    ctype: str,
    max_pairs: int = MAX_PAIRS_PER_TYPE,
) -> list[CandidatePair]:
    """Phase 2: Cross-paper sentence pair extraction with contradiction markers."""
    pairs: list[CandidatePair] = []
    pair_counter = 0
    seen_pmid_pairs: set[tuple[str, str]] = set()

    for i, paper_a in enumerate(papers):
        if len(pairs) >= max_pairs:
            break
        sents_a = _extract_sentences(paper_a["abstract"])

        for paper_b in papers[i + 1:]:
            if len(pairs) >= max_pairs:
                break

            pmid_pair = (min(paper_a["pmid"], paper_b["pmid"]),
                         max(paper_a["pmid"], paper_b["pmid"]))
            if pmid_pair in seen_pmid_pairs:
                continue

            sents_b = _extract_sentences(paper_b["abstract"])
            found = False
            for sa in sents_a:
                for sb in sents_b:
                    if _has_contradiction_marker(sa, sb):
                        pair_counter += 1
                        pairs.append(CandidatePair(
                            pair_id=f"V2-{ctype[:3].upper()}-{pair_counter:04d}",
                            domain=ctype,
                            query_source=paper_a.get("query_source", ""),
                            claim_a=ClaimRecord(
                                text=sa,
                                source_pmid=paper_a["pmid"],
                                source_doi=paper_a.get("doi", ""),
                                paper_title=paper_a["title"],
                                year=paper_a.get("year", ""),
                            ),
                            claim_b=ClaimRecord(
                                text=sb,
                                source_pmid=paper_b["pmid"],
                                source_doi=paper_b.get("doi", ""),
                                paper_title=paper_b["title"],
                                year=paper_b.get("year", ""),
                            ),
                            intended_type=ctype,
                        ))
                        seen_pmid_pairs.add(pmid_pair)
                        found = True
                        break
                if found:
                    break

    logger.info("[%s] Phase 2 complete: %d candidate pairs", ctype, len(pairs))
    return pairs


# ── Phase 3: Gemini classification ───────────────────────────────────────────

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
CONCURRENCY = 5  # free tier: 15 req/min

_SYSTEM = """\
You are a biomedical literature expert classifying scientific contradictions.
Assign the MOST SPECIFIC type that applies — work through types 1→5 in order and stop at the first match.

TYPES (most specific → least specific):

1. DIRECT: Same gene/protein/phenomenon, same organism/cell-type/condition, results point
   in opposite directions (up vs down, activates vs inhibits, increases vs decreases).
   → is_genuine_contradiction = true

2. MAGNITUDE: Same direction of effect, same biological context, but effect sizes are
   quantitatively incompatible (e.g., 10-fold vs 1.2-fold; OR=5.0 vs OR=1.1 for
   identical exposure+outcome).
   → is_genuine_contradiction = true

3. METHODOLOGICAL: Same research question, same or equivalent biological context, but
   different measurement assays or platforms produce opposite/incompatible conclusions.
   → is_genuine_contradiction = true

4. TEMPORAL: Same phenomenon in the same biological context, results differ specifically
   because one study uses an earlier vs later timepoint, developmental stage, or disease phase.
   → is_genuine_contradiction = true

5. CONTEXTUAL [LAST RESORT — only if 1–4 do not apply]: Results differ SOLELY because of
   genuinely different biological contexts (different species, tissue, patient population).
   → is_genuine_contradiction = false

DECISION PROCESS (apply in order):
① Same entity, same context, opposite direction? → DIRECT
② Same direction, same context, incompatible effect sizes? → MAGNITUDE
③ Same question, same context, different methods give opposite results? → METHODOLOGICAL
④ Same context, results differ due to TIMEPOINT or disease phase? → TEMPORAL
⑤ Only different species/tissue/population explains the difference? → CONTEXTUAL

CRITICAL: Do NOT default to contextual because papers come from different labs.
Different labs, same context, same methods, opposite results = DIRECT.
Confidence: 0.90+ = unambiguous, 0.70–0.89 = probable, 0.50–0.69 = uncertain.
"""

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "contradiction_type": {
            "type": "STRING",
            "enum": ["direct", "contextual", "methodological", "temporal", "magnitude"],
        },
        "confidence": {"type": "NUMBER"},
        "rationale": {"type": "STRING"},
        "is_genuine_contradiction": {"type": "BOOLEAN"},
        "suggested_resolution": {"type": "STRING", "nullable": True},
    },
    "required": ["contradiction_type", "confidence", "rationale", "is_genuine_contradiction"],
}


async def _classify_one(
    client: httpx.AsyncClient,
    pair: CandidatePair,
    api_key: str,
    sem: asyncio.Semaphore,
) -> tuple[CandidatePair, ContradictionTypeLabel | None]:
    hint = f"[TYPE HINT: This pair was acquired as a candidate for a {pair.intended_type} contradiction. Check that type first.]\n"
    prompt = (
        f"Domain: {pair.domain}\n{hint}\n"
        f"Claim A (PMID {pair.claim_a.source_pmid}, {pair.claim_a.year}):\n{pair.claim_a.text}\n\n"
        f"Claim B (PMID {pair.claim_b.source_pmid}, {pair.claim_b.year}):\n{pair.claim_b.text}\n\n"
        "Classify this pair following the 5-step decision process."
    )
    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0, "maxOutputTokens": 1024,
            "responseMimeType": "application/json", "responseSchema": _SCHEMA,
        },
    }

    async with sem:
        for attempt in range(3):
            try:
                resp = await client.post(
                    GEMINI_URL, params={"key": api_key},
                    json=payload, timeout=30.0,
                )
                if resp.status_code == 429:
                    wait = 5.0 * (attempt + 1)
                    logger.warning("Rate limited on %s — waiting %.1fs", pair.pair_id, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                body = resp.json()
                candidates = body.get("candidates", [])
                if not candidates:
                    raise ValueError("Empty candidates list from Gemini")
                raw = candidates[0]["content"]["parts"][0]["text"].strip()
                data = json.loads(raw)
                label = ContradictionTypeLabel(**data)
                return pair, label
            except Exception as exc:
                if attempt < 2:
                    await asyncio.sleep(4.0 * (attempt + 1))
                else:
                    logger.warning("Gemini failed for %s: %s", pair.pair_id, exc)
                    return pair, None
    return pair, None


async def classify_pairs(
    pairs: list[CandidatePair],
    api_key: str,
) -> list[tuple[CandidatePair, ContradictionTypeLabel | None]]:
    sem = asyncio.Semaphore(CONCURRENCY)
    results: list[tuple[CandidatePair, ContradictionTypeLabel | None]] = []

    async with httpx.AsyncClient() as client:
        tasks = [_classify_one(client, p, api_key, sem) for p in pairs]
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            if i % 25 == 0:
                ok = sum(1 for _, l in results if l is not None)
                logger.info("  %d / %d classified (%d ok)", i, len(pairs), ok)

    ok = sum(1 for _, l in results if l is not None)
    logger.info("Gemini classification complete: %d ok, %d failed", ok, len(pairs) - ok)
    return results


# ── Phase 4: Filter + balance ─────────────────────────────────────────────────

def filter_type(
    classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]],
    target_type: str,
    target_count: int = 20,
    min_count: int = 15,
    confidence_threshold: float = 0.65,
) -> list[CorpusEntry]:
    """Select top-confidence entries for a single contradiction type."""
    pool: list[tuple[CandidatePair, ContradictionTypeLabel]] = []

    for pair, label in classified:
        if label is None:
            continue
        if label.confidence < confidence_threshold:
            continue
        if label.contradiction_type == target_type:
            pool.append((pair, label))

    pool.sort(key=lambda x: x[1].confidence, reverse=True)
    selected = pool[:target_count]

    if len(selected) < min_count:
        logger.warning("[%s] Only %d entries (min=%d, target=%d)",
                       target_type, len(selected), min_count, target_count)
    else:
        logger.info("[%s] Selected %d / %d pool entries", target_type, len(selected), len(pool))

    return selected


# ── Load existing contextual entries ─────────────────────────────────────────

def load_existing_contextual(path: Path, target: int = 20) -> list[CorpusEntry]:
    """Load contextual entries from existing corpus_150.jsonl."""
    entries = []
    if not path.exists():
        logger.warning("Existing corpus not found at %s — contextual will be empty", path)
        return entries
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("contradiction_type") == "contextual":
                entries.append(CorpusEntry(**row))
            if len(entries) >= target:
                break
    logger.info("Loaded %d existing contextual entries", len(entries))
    return entries


# ── Export ────────────────────────────────────────────────────────────────────

def export_corpus(entries: list[CorpusEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for e in entries:
            f.write(e.model_dump_json() + "\n")
    logger.info("Wrote %d entries → %s", len(entries), path)


def export_candidates(pairs: list[CandidatePair], classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    label_map = {p.pair_id: l for p, l in classified}
    with open(path, "w") as f:
        for pair in pairs:
            label = label_map.get(pair.pair_id)
            row = {
                "pair_id": pair.pair_id,
                "domain": pair.domain,
                "query_source": pair.query_source,
                "intended_type": pair.intended_type,
                "claim_a": pair.claim_a.model_dump(),
                "claim_b": pair.claim_b.model_dump(),
                "label": label.model_dump() if label else None,
            }
            f.write(json.dumps(row) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build balanced contradiction corpus v2")
    parser.add_argument("--dry-run", action="store_true", help="Skip Gemini (Phase 3)")
    parser.add_argument("--target-per-type", type=int, default=20)
    parser.add_argument("--min-per-type", type=int, default=15)
    parser.add_argument("--max-pairs-per-type", type=int, default=MAX_PAIRS_PER_TYPE)
    parser.add_argument("--confidence-threshold", type=float, default=0.65)
    parser.add_argument(
        "--existing-corpus",
        type=Path,
        default=_REPO / "backend/scripts/output/corpus_150.jsonl",
        help="Existing corpus for contextual entries",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not args.dry_run and not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. Export it in the current environment.")

    _OUT.mkdir(parents=True, exist_ok=True)

    all_pairs: list[CandidatePair] = []
    all_classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]] = []
    final_entries: list[CorpusEntry] = []
    entry_counter = 0
    type_stats: dict[str, dict] = {}

    # ── Process each non-contextual type ──────────────────────────────────────
    for ctype, queries in TYPE_QUERIES.items():
        logger.info("\n%s\n[%s] Starting type-specific pipeline\n%s", "=" * 60, ctype.upper(), "=" * 60)

        # Phase 1
        papers = fetch_papers_for_type(ctype, queries)
        type_stats[ctype] = {"papers": len(papers)}

        if len(papers) < 5:
            logger.error("[%s] Only %d papers — skipping", ctype, len(papers))
            type_stats[ctype]["pairs"] = 0
            type_stats[ctype]["selected"] = 0
            continue

        # Phase 2
        pairs = find_candidate_pairs(papers, ctype, max_pairs=args.max_pairs_per_type)
        type_stats[ctype]["pairs"] = len(pairs)
        all_pairs.extend(pairs)

        if not pairs:
            logger.warning("[%s] No candidate pairs found", ctype)
            type_stats[ctype]["selected"] = 0
            continue

        # Save candidates
        cands_path = _OUT / f"candidates_{ctype}.jsonl"
        with open(cands_path, "w") as f:
            for p in pairs:
                row = {
                    "pair_id": p.pair_id, "domain": p.domain,
                    "query_source": p.query_source, "intended_type": p.intended_type,
                    "claim_a": p.claim_a.model_dump(), "claim_b": p.claim_b.model_dump(),
                    "label": None,
                }
                f.write(json.dumps(row) + "\n")
        logger.info("[%s] Saved %d candidates → %s", ctype, len(pairs), cands_path)

        # Phase 3: Gemini
        if args.dry_run:
            logger.info("[%s] DRY RUN — skipping Gemini", ctype)
            classified = [(p, None) for p in pairs]
        else:
            classified = asyncio.run(classify_pairs(pairs, api_key))
            # Save classified candidates
            export_candidates(pairs, classified, _OUT / f"candidates_{ctype}_classified.jsonl")

        all_classified.extend(classified)

        # Phase 4: filter
        if args.dry_run:
            type_stats[ctype]["selected"] = 0
            logger.info("[%s] DRY RUN — filter skipped", ctype)
            continue

        pool_entries = filter_type(
            classified,
            target_type=ctype,
            target_count=args.target_per_type,
            min_count=args.min_per_type,
            confidence_threshold=args.confidence_threshold,
        )

        for pair, label in pool_entries:
            entry_counter += 1
            final_entries.append(CorpusEntry(
                entry_id=f"V2-{entry_counter:03d}",
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

        type_stats[ctype]["selected"] = len(pool_entries)
        logger.info("[%s] → %d entries added to corpus", ctype, len(pool_entries))

    # ── Contextual: reuse existing 30 ─────────────────────────────────────────
    if not args.dry_run:
        logger.info("\n%s\n[CONTEXTUAL] Loading from existing corpus\n%s", "=" * 60, "=" * 60)
        contextual_entries = load_existing_contextual(args.existing_corpus, target=args.target_per_type)
        # Re-ID to v2 scheme
        for ce in contextual_entries:
            entry_counter += 1
            final_entries.append(ce.model_copy(update={"entry_id": f"V2-{entry_counter:03d}"}))
        type_stats["contextual"] = {"papers": 0, "pairs": 0, "selected": len(contextual_entries)}

    # ── Export ────────────────────────────────────────────────────────────────
    corpus_path = _OUT / "corpus_v2.jsonl"
    if not args.dry_run:
        export_corpus(final_entries, corpus_path)

    # Stats report
    print("\n" + "=" * 60)
    print("BUILD CORPUS V2 STATS")
    print("=" * 60)
    all_types = list(TYPE_QUERIES.keys()) + ["contextual"]
    for t in all_types:
        s = type_stats.get(t, {})
        papers = s.get("papers", "—")
        pairs = s.get("pairs", "—")
        selected = s.get("selected", "—")
        flag = " ⚠" if isinstance(selected, int) and selected < args.min_per_type else ""
        print(f"  {t:<20} papers={papers!s:<6} pairs={pairs!s:<6} selected={selected!s:<4}{flag}")
    print(f"\nTotal corpus entries: {len(final_entries)}")
    print(f"Output: {corpus_path}")
    print("=" * 60)

    # Save stats
    stats_path = _OUT / "build_stats_v2.json"
    with open(stats_path, "w") as f:
        json.dump({
            "target_per_type": args.target_per_type,
            "min_per_type": args.min_per_type,
            "confidence_threshold": args.confidence_threshold,
            "dry_run": args.dry_run,
            "type_stats": type_stats,
            "total_entries": len(final_entries),
        }, f, indent=2)
    logger.info("Stats → %s", stats_path)


if __name__ == "__main__":
    main()
