"""Build balanced contradiction corpus v3 — within-abstract extraction.

Key pivot from v2: extract BOTH claims from the SAME paper abstract.
The author themselves describes the contradiction, so:
- Claims share the same biological context → Gemini can assign non-contextual types
- Type is more explicit (author signals it via contrast language)
- Higher signal-to-noise ratio

Strategy:
- Phase 1: PubMed search with type-specific queries (papers containing contrast language)
- Phase 2: Within-abstract pair extraction via contrast connective regex
- Phase 3: Gemini classification with type-hint (free tier)
- Phase 4: Filter + balance (target 20/type, min 12/type)
- Contextual: reuse existing 20 from corpus_150.jsonl

Usage:
    export GEMINI_API_KEY=<your-key>
    uv run python backend/scripts/build_corpus_v3.py --dry-run
    uv run python backend/scripts/build_corpus_v3.py
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
logger = logging.getLogger("corpus_v3")

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))

from app.integrations.pubmed import PubMedClient, PubMedPaper  # noqa: E402

_OUT = _REPO / "backend/scripts/output/v3"

# ── Within-abstract type-specific PubMed queries ──────────────────────────────
# These find papers that EXPLICITLY discuss a contradiction within one abstract.

TYPE_QUERIES: dict[str, list[str]] = {
    "direct": [
        # Papers where authors explicitly contradict a prior study
        '"contrary to" AND "previous" AND (expression OR activity OR level OR function)',
        '"in contrast to" AND "prior report" AND (gene OR protein OR pathway)',
        '"failed to confirm" AND (expression OR activity OR finding)',
        '"could not replicate" AND (result OR finding OR effect)',
        '"opposite" AND "previous study" AND (regulation OR expression OR effect)',
    ],
    "methodological": [
        # Papers comparing two assay methods with discordant conclusions
        '"RNA-seq" AND "microarray" AND ("whereas" OR "in contrast") AND (expression OR upregulation)',
        '"ChIP-seq" AND "ChIP" AND "discordant" AND (binding OR enrichment)',
        '"single-cell" AND "bulk" AND ("however" OR "whereas") AND (expression OR heterogeneity)',
        '"ELISA" AND "western blot" AND ("inconsistent" OR "discrepant" OR "contrast")',
        '"whole exome" AND "RNA-seq" AND ("however" OR "whereas" OR "contrast")',
        '"proteomics" AND "transcriptomics" AND ("discordant" OR "inconsistent" OR "contrast")',
    ],
    "temporal": [
        # Papers discussing time-dependent opposing results within one study
        '"acute" AND "chronic" AND ("whereas" OR "however") AND (response OR effect OR regulation)',
        '"early" AND "late" AND ("conversely" OR "however" OR "in contrast") AND (phase OR stage)',
        '"short-term" AND "long-term" AND ("opposite" OR "reversed" OR "contrast") AND effect',
        '"initial" AND "prolonged" AND ("however" OR "whereas") AND (activation OR inhibition)',
        '"baseline" AND "follow-up" AND ("whereas" OR "however") AND (level OR expression OR activity)',
    ],
    "magnitude": [
        # Papers where quantitative effect size discrepancy is the main finding
        '"effect size" AND ("larger" OR "smaller") AND ("previous" OR "reported") AND (study OR meta)',
        '"odds ratio" AND ("inconsistent" OR "heterogeneous") AND (meta-analysis OR systematic)',
        '"hazard ratio" AND "discrepancy" AND (survival OR outcome OR treatment)',
        '"high heterogeneity" AND "I2" AND ("however" OR "while") AND (estimate OR effect)',
        '"overestimated" AND (risk OR effect OR association) AND (study OR cohort)',
    ],
}

MAX_PER_QUERY = 40
MAX_PAIRS_PER_TYPE = 200

# ── Contrast connectives for within-abstract pair extraction ──────────────────

# Ordered by specificity — try each pattern; stop at first match per sentence
CONTRAST_PATTERNS = [
    # Pattern: (lookbehind clause) [connective] (clause)
    r"([A-Z][^.!?]{20,150}?)\s*,?\s*\bwhereas\b\s*([^.!?]{20,150}[.!?])",
    r"([A-Z][^.!?]{20,150}?)\s*,?\s*\bin contrast\b[,]?\s*([^.!?]{20,150}[.!?])",
    r"([A-Z][^.!?]{20,150}?)\s*,?\s*\bconversely\b[,]?\s*([^.!?]{20,150}[.!?])",
    r"([A-Z][^.!?]{20,150}?)\s*[.!?]\s*\bHowever\b[,]?\s*([^.!?]{20,150}[.!?])",
    r"([A-Z][^.!?]{20,150}?)\s*,?\s*\bwhile\b\s*([^.!?]{20,150}[.!?])",
    r"([A-Z][^.!?]{20,150}?)\s*,?\s*\byet\b\s*([^.!?]{20,150}[.!?])",
    # "X; however, Y"
    r"([A-Z][^;.!?]{20,150}?);\s*however[,]?\s*([^.!?]{20,150}[.!?])",
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
    intended_type: str
    extraction_pattern: str = ""  # which contrast pattern matched


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


# ── Phase 1: PubMed fetch ─────────────────────────────────────────────────────

def fetch_papers_for_type(ctype: str, queries: list[str]) -> list[dict]:
    client = PubMedClient()
    seen_pmids: set[str] = set()
    papers: list[dict] = []

    for query in queries:
        try:
            results: list[PubMedPaper] = client.search(
                query, max_results=MAX_PER_QUERY, sort="relevance"
            )
            time.sleep(0.35)
        except Exception as e:
            logger.warning("[%s] PubMed failed for %r: %s", ctype, query[:50], e)
            continue

        new = 0
        for paper in results:
            if not paper.abstract or paper.pmid in seen_pmids:
                continue
            seen_pmids.add(paper.pmid)
            # Sanitize abstract: remove control chars, normalize whitespace
            abstract = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", " ", paper.abstract)
            abstract = re.sub(r"\s+", " ", abstract).strip()
            papers.append({
                "pmid": paper.pmid,
                "title": paper.title,
                "abstract": abstract,
                "year": str(paper.year) if paper.year else "",
                "doi": paper.doi or "",
                "query_source": query[:60],
            })
            new += 1

        logger.info("  [%s] %r → %d new papers (total %d)", ctype, query[:50], new, len(papers))

    logger.info("[%s] Phase 1 complete: %d papers", ctype, len(papers))
    return papers


# ── Phase 2: Within-abstract pair extraction ──────────────────────────────────

def _clean_claim(text: str, max_len: int = 300) -> str:
    """Clean and truncate claim text; remove JSON-unsafe characters."""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = re.sub(r'["\'\\]', " ", text)  # remove quotes/backslashes (JSON-safe)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def extract_within_pairs(
    papers: list[dict],
    ctype: str,
    max_pairs: int = MAX_PAIRS_PER_TYPE,
) -> list[CandidatePair]:
    """Phase 2: Extract contrast pairs from within single abstracts."""
    pairs: list[CandidatePair] = []
    pair_counter = 0
    seen_pmids: set[str] = set()  # one pair per abstract

    for paper in papers:
        if len(pairs) >= max_pairs:
            break
        if paper["pmid"] in seen_pmids:
            continue

        abstract = paper["abstract"]
        found = False

        for pattern_idx, pattern in enumerate(CONTRAST_PATTERNS):
            matches = re.findall(pattern, abstract, re.IGNORECASE)
            for m in matches:
                if len(m) != 2:
                    continue
                claim_a_raw, claim_b_raw = m[0].strip(), m[1].strip()
                # Filter out too-short or trivially different claims
                if len(claim_a_raw) < 25 or len(claim_b_raw) < 25:
                    continue
                if claim_a_raw.lower()[:30] == claim_b_raw.lower()[:30]:
                    continue  # near-duplicate

                claim_a = _clean_claim(claim_a_raw)
                claim_b = _clean_claim(claim_b_raw)

                if len(claim_a) < 20 or len(claim_b) < 20:
                    continue

                pair_counter += 1
                pairs.append(CandidatePair(
                    pair_id=f"V3-{ctype[:3].upper()}-{pair_counter:04d}",
                    domain=ctype,
                    query_source=paper.get("query_source", ""),
                    claim_a=ClaimRecord(
                        text=claim_a,
                        source_pmid=paper["pmid"],
                        source_doi=paper.get("doi", ""),
                        paper_title=paper["title"][:120],
                        year=paper.get("year", ""),
                    ),
                    claim_b=ClaimRecord(
                        text=claim_b,
                        source_pmid=paper["pmid"],  # SAME paper = within-abstract
                        source_doi=paper.get("doi", ""),
                        paper_title=paper["title"][:120],
                        year=paper.get("year", ""),
                    ),
                    intended_type=ctype,
                    extraction_pattern=str(pattern_idx),
                ))
                seen_pmids.add(paper["pmid"])
                found = True
                break  # one pair per paper
            if found:
                break

    logger.info("[%s] Phase 2 complete: %d within-abstract pairs", ctype, len(pairs))
    return pairs


# ── Phase 3: Gemini classification ───────────────────────────────────────────

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
CONCURRENCY = 4  # conservative free tier

_SYSTEM = """\
You are a biomedical literature expert classifying scientific contradictions.
Both claims below come from the SAME paper — the authors themselves describe a contradiction.
Assign the MOST SPECIFIC type that applies.

TYPES (most specific → least specific):

1. DIRECT: Same entity, same context, results point in opposite directions.
   Authors found the opposite of what a prior study reported (same conditions).
   → is_genuine_contradiction = true

2. MAGNITUDE: Same direction, same context, but effect sizes are quantitatively incompatible.
   → is_genuine_contradiction = true

3. METHODOLOGICAL: Same research question, same context, but DIFFERENT assays/platforms
   produce opposite/incompatible results (e.g., RNA-seq vs microarray discordance).
   → is_genuine_contradiction = true

4. TEMPORAL: Same phenomenon, same context, results differ by timepoint or disease phase
   (e.g., acute vs chronic effects are opposite).
   → is_genuine_contradiction = true

5. CONTEXTUAL: Results differ because biological context differs (species, tissue, population).
   → is_genuine_contradiction = false

DECISION PROCESS:
① Same entity, same context, opposite direction? → DIRECT
② Same direction, same context, incompatible effect size? → MAGNITUDE
③ Same question, same context, different methods? → METHODOLOGICAL
④ Same context, different timepoints/phases? → TEMPORAL
⑤ Different species/tissue/population? → CONTEXTUAL

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
    hint = f"[TYPE HINT: Likely a {pair.intended_type} contradiction — check this type first.]\n"
    # Both claims from same paper — note this explicitly
    prompt = (
        f"Domain: {pair.domain}\n"
        f"NOTE: Both claims are from the SAME paper (PMID {pair.claim_a.source_pmid}, {pair.claim_a.year}).\n"
        f"{hint}\n"
        f"Claim A: {pair.claim_a.text}\n\n"
        f"Claim B: {pair.claim_b.text}\n\n"
        "Classify using the 5-step decision process."
    )

    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
            "responseSchema": _SCHEMA,
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
                    wait = 6.0 * (attempt + 1)
                    logger.warning("Rate limit on %s — wait %.1fs", pair.pair_id, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                body = resp.json()
                candidates = body.get("candidates", [])
                if not candidates:
                    raise ValueError("Empty candidates")
                raw = candidates[0]["content"]["parts"][0]["text"].strip()
                data = json.loads(raw)
                label = ContradictionTypeLabel(**data)
                return pair, label
            except Exception as exc:
                if attempt < 2:
                    await asyncio.sleep(4.0 * (attempt + 1))
                else:
                    logger.warning("Failed %s: %s", pair.pair_id, exc)
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
            if i % 30 == 0:
                ok = sum(1 for _, l in results if l is not None)
                logger.info("  %d / %d classified (%d ok)", i, len(pairs), ok)
    ok = sum(1 for _, l in results if l is not None)
    logger.info("Classification complete: %d ok / %d total", ok, len(pairs))
    return results


# ── Phase 4: Filter ───────────────────────────────────────────────────────────

def filter_type(
    classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]],
    target_type: str,
    target_count: int = 20,
    min_count: int = 12,
    confidence_threshold: float = 0.65,
) -> list[tuple[CandidatePair, ContradictionTypeLabel]]:
    pool = [
        (p, l) for p, l in classified
        if l is not None
        and l.contradiction_type == target_type
        and l.confidence >= confidence_threshold
    ]
    pool.sort(key=lambda x: x[1].confidence, reverse=True)
    selected = pool[:target_count]

    if len(selected) < min_count:
        logger.warning("[%s] Only %d entries (min=%d)", target_type, len(selected), min_count)
    else:
        logger.info("[%s] Selected %d / %d pool entries", target_type, len(selected), len(pool))
    return selected


# ── Load existing contextual ──────────────────────────────────────────────────

def load_existing_contextual(path: Path, target: int = 20) -> list[CorpusEntry]:
    entries = []
    if not path.exists():
        logger.warning("Existing corpus not found: %s", path)
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
    logger.info("Exported %d entries → %s", len(entries), path)


def export_candidates(
    pairs: list[CandidatePair],
    classified: list[tuple[CandidatePair, ContradictionTypeLabel | None]],
    path: Path,
) -> None:
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
                "extraction_pattern": pair.extraction_pattern,
                "claim_a": pair.claim_a.model_dump(),
                "claim_b": pair.claim_b.model_dump(),
                "label": label.model_dump() if label else None,
            }
            f.write(json.dumps(row) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build balanced contradiction corpus v3 (within-abstract)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target-per-type", type=int, default=20)
    parser.add_argument("--min-per-type", type=int, default=12)
    parser.add_argument("--max-pairs-per-type", type=int, default=MAX_PAIRS_PER_TYPE)
    parser.add_argument("--confidence-threshold", type=float, default=0.65)
    parser.add_argument(
        "--existing-corpus",
        type=Path,
        default=_REPO / "backend/scripts/output/corpus_150.jsonl",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not args.dry_run and not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. Export it in the current environment.")

    _OUT.mkdir(parents=True, exist_ok=True)

    final_entries: list[CorpusEntry] = []
    entry_counter = 0
    type_stats: dict[str, dict] = {}

    for ctype, queries in TYPE_QUERIES.items():
        logger.info("\n%s\n[%s]\n%s", "=" * 55, ctype.upper(), "=" * 55)

        papers = fetch_papers_for_type(ctype, queries)
        type_stats[ctype] = {"papers": len(papers)}

        if len(papers) < 5:
            logger.error("[%s] Only %d papers — skipping", ctype, len(papers))
            type_stats[ctype].update({"pairs": 0, "classified": 0, "selected": 0})
            continue

        pairs = extract_within_pairs(papers, ctype, max_pairs=args.max_pairs_per_type)
        type_stats[ctype]["pairs"] = len(pairs)

        # Save raw candidates
        cands_path = _OUT / f"candidates_{ctype}.jsonl"
        with open(cands_path, "w") as f:
            for p in pairs:
                row = {
                    "pair_id": p.pair_id, "domain": p.domain,
                    "query_source": p.query_source, "intended_type": p.intended_type,
                    "extraction_pattern": p.extraction_pattern,
                    "claim_a": p.claim_a.model_dump(), "claim_b": p.claim_b.model_dump(),
                    "label": None,
                }
                f.write(json.dumps(row) + "\n")
        logger.info("[%s] Saved %d raw candidates → %s", ctype, len(pairs), cands_path)

        if not pairs:
            logger.warning("[%s] No pairs found — skipping Gemini", ctype)
            type_stats[ctype].update({"classified": 0, "selected": 0})
            continue

        if args.dry_run:
            logger.info("[%s] DRY RUN — skipping Gemini", ctype)
            type_stats[ctype].update({"classified": 0, "selected": 0})
            continue

        classified = asyncio.run(classify_pairs(pairs, api_key))
        export_candidates(pairs, classified, _OUT / f"candidates_{ctype}_classified.jsonl")

        n_ok = sum(1 for _, l in classified if l is not None)
        type_stats[ctype]["classified"] = n_ok

        pool = filter_type(
            classified,
            target_type=ctype,
            target_count=args.target_per_type,
            min_count=args.min_per_type,
            confidence_threshold=args.confidence_threshold,
        )

        for pair, label in pool:
            entry_counter += 1
            final_entries.append(CorpusEntry(
                entry_id=f"V3-{entry_counter:03d}",
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

        type_stats[ctype]["selected"] = len(pool)
        logger.info("[%s] → %d entries added", ctype, len(pool))

    # Contextual: existing entries
    if not args.dry_run:
        logger.info("\n[CONTEXTUAL] Loading from existing corpus")
        ctx_entries = load_existing_contextual(args.existing_corpus, target=args.target_per_type)
        for ce in ctx_entries:
            entry_counter += 1
            final_entries.append(ce.model_copy(update={"entry_id": f"V3-{entry_counter:03d}"}))
        type_stats["contextual"] = {"papers": 0, "pairs": 0, "classified": 0, "selected": len(ctx_entries)}

    # Export
    corpus_path = _OUT / "corpus_v3.jsonl"
    if not args.dry_run:
        export_corpus(final_entries, corpus_path)

    # Stats
    print("\n" + "=" * 60)
    print("BUILD CORPUS V3 STATS  (within-abstract extraction)")
    print("=" * 60)
    all_types = list(TYPE_QUERIES.keys()) + ["contextual"]
    for t in all_types:
        s = type_stats.get(t, {})
        papers = s.get("papers", "—")
        pairs = s.get("pairs", "—")
        classified = s.get("classified", "—")
        selected = s.get("selected", "—")
        flag = " ⚠" if isinstance(selected, int) and selected < args.min_per_type else ""
        print(f"  {t:<20} papers={papers!s:<5} pairs={pairs!s:<5} ok={classified!s:<5} sel={selected!s:<4}{flag}")
    print(f"\nTotal corpus entries: {len(final_entries)}")
    if not args.dry_run:
        print(f"Output: {corpus_path}")
    print("=" * 60)

    stats_path = _OUT / "build_stats_v3.json"
    _OUT.mkdir(parents=True, exist_ok=True)
    with open(stats_path, "w") as f:
        json.dump({
            "version": "v3",
            "strategy": "within-abstract",
            "target_per_type": args.target_per_type,
            "min_per_type": args.min_per_type,
            "type_stats": type_stats,
            "total_entries": len(final_entries),
        }, f, indent=2)
    logger.info("Stats → %s", stats_path)


if __name__ == "__main__":
    main()
