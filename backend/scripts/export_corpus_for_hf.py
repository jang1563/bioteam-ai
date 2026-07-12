#!/usr/bin/env python3
"""Export ContradictBio-338 corpus for HuggingFace dataset publication.

Transforms corpus_final.jsonl into the canonical HuggingFace-ready format:
  - Drops internal fields (domain, extraction_pattern, _partial_parse)
  - Adds abstract_text fetched in batch from PubMed (cached to abstract_cache.json)
  - Adds confidence_tier (1/2/3) derived from 6-rater panel agreement data

Output: docs/huggingface/ContradictBio-338/data/contradictbio_338.jsonl

Usage:
    cd backend
    set -a && source ../.env && set +a
    UV_NO_SYNC=1 uv run python scripts/export_corpus_for_hf.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

CORPUS_PATH = BACKEND_ROOT / "scripts/output/v3/corpus_final.jsonl"
PANEL_PATH = BACKEND_ROOT / "scripts/output/v3/panel_agreement_mega/mega_panel_results.jsonl"
CACHE_PATH = BACKEND_ROOT / "scripts/output/v3/abstract_cache.json"
OUTPUT_DIR = REPO_ROOT / "docs/huggingface/ContradictBio-338/data"
OUTPUT_PATH = OUTPUT_DIR / "contradictbio_338.jsonl"


# ---------------------------------------------------------------------------
# Step 1: Load corpus
# ---------------------------------------------------------------------------

def load_corpus(path: Path) -> list[dict]:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(records)} corpus entries from {path.name}")
    return records


# ---------------------------------------------------------------------------
# Step 2: Load panel data and derive confidence_tier
# ---------------------------------------------------------------------------

def build_tier_map(panel_path: Path) -> dict[str, int]:
    """Return {entry_id: confidence_tier} from mega_panel_results.jsonl.

    Tier derivation:
      agreement_rate = max(votes_genuine, votes_contextual) / votes_total
      tier 1 if agreement_rate >= 5/6 (~0.833)
      tier 2 if agreement_rate >= 4/6 (~0.667)
      tier 3 otherwise
    """
    tier_map: dict[str, int] = {}
    for line in panel_path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        entry_id = r["id"]
        votes_genuine = r.get("votes_genuine", 0)
        votes_contextual = r.get("votes_contextual", 0)
        votes_total = r.get("votes_total", 1)
        agreement_rate = max(votes_genuine, votes_contextual) / votes_total
        if agreement_rate >= 5 / 6:
            tier = 1
        elif agreement_rate >= 4 / 6:
            tier = 2
        else:
            tier = 3
        tier_map[entry_id] = tier

    tier_counts = {1: 0, 2: 0, 3: 0}
    for t in tier_map.values():
        tier_counts[t] += 1
    print(f"Tier map built: tier1={tier_counts[1]}, tier2={tier_counts[2]}, tier3={tier_counts[3]}")
    return tier_map


# ---------------------------------------------------------------------------
# Step 3: Fetch PubMed abstracts (batch, cached)
# ---------------------------------------------------------------------------

def load_cache(cache_path: Path) -> dict[str, str]:
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())
        print(f"Loaded abstract cache: {len(cache)} entries")
        return cache
    return {}


def save_cache(cache: dict[str, str], cache_path: Path) -> None:
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    print(f"Saved abstract cache: {len(cache)} entries → {cache_path.name}")


def fetch_abstracts(pmids: list[str], ncbi_email: str) -> dict[str, str]:
    """Fetch abstracts for a list of PMIDs using Bio.Entrez in a single batch call.

    Returns {pmid: abstract_text}. PMIDs with no abstract get empty string.
    """
    try:
        from Bio import Entrez, Medline  # type: ignore[import]
    except ImportError:
        print("ERROR: biopython is required. Run: uv add biopython", file=sys.stderr)
        sys.exit(1)

    Entrez.email = ncbi_email
    results: dict[str, str] = {}

    if not pmids:
        return results

    print(f"Fetching {len(pmids)} abstracts from PubMed (single batch)...")
    try:
        # NCBI efetch supports comma-separated IDs; 338 is well within limits
        handle = Entrez.efetch(
            db="pubmed",
            id=",".join(pmids),
            rettype="medline",
            retmode="text",
        )
        records = list(Medline.parse(handle))
        handle.close()

        for rec in records:
            pmid = rec.get("PMID", "")
            abstract = rec.get("AB", "")
            if pmid:
                results[pmid] = abstract

        print(f"Fetched {len(results)} abstracts ({len(pmids) - len(results)} missing)")
    except Exception as e:
        print(f"WARNING: PubMed fetch failed: {e}", file=sys.stderr)
        print("Continuing with empty abstracts for uncached entries.", file=sys.stderr)
        # Brief wait before giving up — NCBI may have rate-limited us
        time.sleep(2)

    return results


def get_abstracts(pmids: list[str], cache_path: Path, ncbi_email: str) -> dict[str, str]:
    """Return abstracts for all PMIDs, using cache + batch fetch for misses."""
    cache = load_cache(cache_path)
    uncached = [p for p in pmids if p not in cache]

    if uncached:
        fetched = fetch_abstracts(uncached, ncbi_email)
        cache.update(fetched)
        save_cache(cache, cache_path)
    else:
        print("All abstracts found in cache — no PubMed fetch needed.")

    return cache


# ---------------------------------------------------------------------------
# Step 4: Build and write output records
# ---------------------------------------------------------------------------

INTERNAL_FIELDS = {"domain", "extraction_pattern", "_partial_parse"}


def build_output_record(entry: dict, tier: int, abstract: str) -> dict:
    """Produce the final HuggingFace-ready record for one corpus entry."""
    return {
        "id": entry["id"],
        "source_pmid": entry.get("source_pmid", ""),
        "source_doi": entry.get("source_doi", ""),
        "paper_title": entry.get("paper_title", ""),
        "claim_a": entry["claim_a"],
        "claim_b": entry["claim_b"],
        "is_genuine_contradiction": bool(entry.get("is_genuine_contradiction", False)),
        "contradiction_type": entry.get("contradiction_type", ""),
        "confidence": float(entry.get("confidence", 0.0)),
        "rationale": entry.get("rationale", ""),
        "abstract_text": abstract,
        "confidence_tier": tier,
    }


def write_output(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} records → {output_path}")


# ---------------------------------------------------------------------------
# Step 5: Print summary statistics
# ---------------------------------------------------------------------------

def print_summary(records: list[dict]) -> None:
    total = len(records)
    genuine = sum(1 for r in records if r["is_genuine_contradiction"])
    contextual = total - genuine
    with_abstract = sum(1 for r in records if r.get("abstract_text"))
    tier_counts = {1: 0, 2: 0, 3: 0}
    for r in records:
        tier_counts[r["confidence_tier"]] += 1
    type_counts: dict[str, int] = {}
    for r in records:
        t = r["contradiction_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print("\n" + "=" * 60)
    print("ContradictBio-338 Export Summary")
    print("=" * 60)
    print(f"Total records:         {total}")
    print(f"Genuine contradictions:{genuine}")
    print(f"Contextual (negative): {contextual}")
    print(f"Abstracts populated:   {with_abstract}/{total}")
    print(f"Tier 1 (high conf):    {tier_counts[1]}")
    print(f"Tier 2 (medium conf):  {tier_counts[2]}")
    print(f"Tier 3 (uncertain):    {tier_counts[3]}")
    print("\nType distribution (genuine only):")
    for typ, cnt in sorted(type_counts.items()):
        genuine_of_type = sum(1 for r in records if r["contradiction_type"] == typ and r["is_genuine_contradiction"])
        print(f"  {typ:20s}: {genuine_of_type} genuine / {cnt} total")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Resolve NCBI email
    ncbi_email = os.environ.get("NCBI_EMAIL", "")
    if not ncbi_email:
        # Try loading from .env manually
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("NCBI_EMAIL="):
                    ncbi_email = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not ncbi_email:
        print("WARNING: NCBI_EMAIL not set. Using fallback email for PubMed API.", file=sys.stderr)
        ncbi_email = "bioteam@example.com"

    print(f"NCBI email: {ncbi_email}")

    # Load corpus
    corpus = load_corpus(CORPUS_PATH)

    # Build tier map
    tier_map = build_tier_map(PANEL_PATH)

    # Collect all PMIDs and fetch abstracts
    pmids = [entry["source_pmid"] for entry in corpus if entry.get("source_pmid")]
    abstract_map = get_abstracts(pmids, CACHE_PATH, ncbi_email)

    # Build output records
    output_records: list[dict] = []
    missing_tier = 0
    for entry in corpus:
        entry_id = entry["id"]
        tier = tier_map.get(entry_id, 3)
        if entry_id not in tier_map:
            missing_tier += 1
        pmid = entry.get("source_pmid", "")
        abstract = abstract_map.get(pmid, "")
        output_records.append(build_output_record(entry, tier, abstract))

    if missing_tier:
        print(f"WARNING: {missing_tier} entries had no panel match → assigned tier 3")

    # Validate expected field set
    expected_keys = {
        "id", "source_pmid", "source_doi", "paper_title",
        "claim_a", "claim_b", "is_genuine_contradiction",
        "contradiction_type", "confidence", "rationale",
        "abstract_text", "confidence_tier",
    }
    actual_keys = set(output_records[0].keys()) if output_records else set()
    if actual_keys != expected_keys:
        extra = actual_keys - expected_keys
        missing = expected_keys - actual_keys
        if extra:
            print(f"WARNING: unexpected fields in output: {extra}", file=sys.stderr)
        if missing:
            print(f"WARNING: missing expected fields: {missing}", file=sys.stderr)

    # Write output
    write_output(output_records, OUTPUT_PATH)

    # Print summary
    print_summary(output_records)


if __name__ == "__main__":
    main()
