#!/usr/bin/env python3
"""Export ContradictBio-1138 (v5 merged) corpus for HuggingFace dataset publication.

Merges v3 (338 within-abstract) + v4 (800 cross-paper) entries into a unified format:
  - Drops internal fields (domain, extraction_pattern, _partial_parse, intended_type, _source, _classifier)
  - Adds entry_source: "within_abstract" (v3) or "cross_paper" (v4)
  - Adds abstract_text / abstract_text_b fetched from PubMed (cached)
  - Adds confidence_tier: derived from 6-rater panel (v3) or 0 (unrated, v4)

Output: docs/huggingface/ContradictBio-1138/data/contradictbio_1138.jsonl

Usage:
    cd backend
    set -a && source ../.env && set +a
    UV_NO_SYNC=1 uv run python scripts/export_corpus_v5_for_hf.py
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

V5_CORPUS_PATH = BACKEND_ROOT / "scripts/output/v4/corpus_final_v5.jsonl"
PANEL_PATH = BACKEND_ROOT / "scripts/output/v3/panel_agreement_mega/mega_panel_results.jsonl"
CACHE_PATH = BACKEND_ROOT / "scripts/output/v5_abstract_cache.json"
OUTPUT_DIR = REPO_ROOT / "docs/huggingface/ContradictBio-1138/data"
OUTPUT_PATH = OUTPUT_DIR / "contradictbio_1138.jsonl"


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

    Tier derivation (v3 entries only):
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
    print(f"Panel tier map: tier1={tier_counts[1]}, tier2={tier_counts[2]}, tier3={tier_counts[3]} (v3 only)")
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


def fetch_abstracts_batch(pmids: list[str], ncbi_email: str) -> dict[str, str]:
    """Fetch abstracts in batches of 200 (NCBI limit) via Bio.Entrez."""
    try:
        from Bio import Entrez, Medline  # type: ignore[import]
    except ImportError:
        print("ERROR: biopython is required. Run: uv add biopython", file=sys.stderr)
        sys.exit(1)

    Entrez.email = ncbi_email
    results: dict[str, str] = {}
    batch_size = 200  # NCBI recommends <=200 per request

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i : i + batch_size]
        print(f"  Fetching batch {i // batch_size + 1} ({len(batch)} PMIDs)...")
        try:
            handle = Entrez.efetch(
                db="pubmed",
                id=",".join(batch),
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

            # Respect NCBI rate limit (3 requests/sec without API key)
            time.sleep(0.5)
        except Exception as e:
            print(f"WARNING: PubMed fetch failed for batch {i // batch_size + 1}: {e}", file=sys.stderr)
            time.sleep(2)

    return results


def get_abstracts(pmids: list[str], cache_path: Path, ncbi_email: str) -> dict[str, str]:
    """Return abstracts for all PMIDs, using cache + batch fetch for misses."""
    cache = load_cache(cache_path)
    uncached = [p for p in pmids if p and p not in cache]

    if uncached:
        print(f"Fetching {len(uncached)} uncached abstracts from PubMed...")
        fetched = fetch_abstracts_batch(uncached, ncbi_email)
        cache.update(fetched)
        save_cache(cache, cache_path)
    else:
        print("All abstracts found in cache — no PubMed fetch needed.")

    return cache


# ---------------------------------------------------------------------------
# Step 4: Build and write output records
# ---------------------------------------------------------------------------

INTERNAL_FIELDS = {"domain", "extraction_pattern", "_partial_parse", "intended_type", "_source", "_classifier"}


def is_cross_paper(entry: dict) -> bool:
    """Determine if an entry is cross-paper (v4) or within-abstract (v3)."""
    return entry.get("_source") == "cross_paper" or entry["id"].startswith("V4-")


def build_output_record(entry: dict, tier: int, abstract_a: str, abstract_b: str) -> dict:
    """Produce the final HuggingFace-ready record for one corpus entry."""
    cross = is_cross_paper(entry)
    rec = {
        "id": entry["id"],
        "entry_source": "cross_paper" if cross else "within_abstract",
        "source_pmid": str(entry.get("source_pmid", "")),
        "source_doi": entry.get("source_doi", ""),
        "paper_title": entry.get("paper_title", ""),
        "claim_a": entry["claim_a"],
        "claim_b": entry["claim_b"],
        "is_genuine_contradiction": bool(entry.get("is_genuine_contradiction", False)),
        "contradiction_type": entry.get("contradiction_type", ""),
        "confidence": float(entry.get("confidence", 0.0)),
        "rationale": entry.get("rationale", ""),
        "abstract_text": abstract_a,
        "confidence_tier": tier,
    }
    # Cross-paper entries have second paper metadata
    if cross:
        rec["source_pmid_b"] = str(entry.get("source_pmid_b", ""))
        rec["source_doi_b"] = entry.get("source_doi_b", "")
        rec["paper_title_b"] = entry.get("paper_title_b", "")
        rec["abstract_text_b"] = abstract_b
    else:
        rec["source_pmid_b"] = ""
        rec["source_doi_b"] = ""
        rec["paper_title_b"] = ""
        rec["abstract_text_b"] = ""

    return rec


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
    with_abstract_a = sum(1 for r in records if r.get("abstract_text"))
    cross_paper = sum(1 for r in records if r["entry_source"] == "cross_paper")
    within_abstract = total - cross_paper
    with_abstract_b = sum(1 for r in records if r.get("abstract_text_b"))

    tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for r in records:
        tier_counts[r["confidence_tier"]] = tier_counts.get(r["confidence_tier"], 0) + 1

    type_counts: dict[str, int] = {}
    for r in records:
        t = r["contradiction_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print("\n" + "=" * 60)
    print("ContradictBio-1138 (v5 merged) Export Summary")
    print("=" * 60)
    print(f"Total records:         {total}")
    print(f"  within_abstract (v3): {within_abstract}")
    print(f"  cross_paper (v4):     {cross_paper}")
    print(f"Genuine contradictions: {genuine}")
    print(f"Contextual (negative):  {contextual}")
    print(f"Abstracts (paper A):    {with_abstract_a}/{total}")
    print(f"Abstracts (paper B):    {with_abstract_b}/{cross_paper} (cross-paper only)")
    print("\nConfidence tiers:")
    print(f"  Tier 0 (unrated/v4):  {tier_counts.get(0, 0)}")
    print(f"  Tier 1 (high conf):   {tier_counts.get(1, 0)}")
    print(f"  Tier 2 (medium conf): {tier_counts.get(2, 0)}")
    print(f"  Tier 3 (uncertain):   {tier_counts.get(3, 0)}")
    print("\nType distribution:")
    for typ, cnt in sorted(type_counts.items()):
        genuine_of_type = sum(1 for r in records if r["contradiction_type"] == typ and r["is_genuine_contradiction"])
        print(f"  {typ:20s}: {genuine_of_type:4d} genuine / {cnt:4d} total")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Resolve NCBI email
    ncbi_email = os.environ.get("NCBI_EMAIL", "")
    if not ncbi_email:
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("NCBI_EMAIL="):
                    ncbi_email = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not ncbi_email:
        print("WARNING: NCBI_EMAIL not set. Using fallback email.", file=sys.stderr)
        ncbi_email = "bioteam@example.com"

    print(f"NCBI email: {ncbi_email}")

    # Load v5 merged corpus
    corpus = load_corpus(V5_CORPUS_PATH)

    # Build panel tier map (v3 entries only)
    tier_map = build_tier_map(PANEL_PATH)

    # Collect ALL unique PMIDs (paper A + paper B)
    all_pmids = set()
    for entry in corpus:
        if entry.get("source_pmid"):
            all_pmids.add(str(entry["source_pmid"]))
        if entry.get("source_pmid_b"):
            all_pmids.add(str(entry["source_pmid_b"]))
    print(f"Unique PMIDs to fetch: {len(all_pmids)}")

    # Fetch abstracts
    abstract_map = get_abstracts(sorted(all_pmids), CACHE_PATH, ncbi_email)

    # Build output records
    output_records: list[dict] = []
    for entry in corpus:
        entry_id = entry["id"]
        cross = is_cross_paper(entry)

        # Confidence tier: v3 entries use panel data, v4 entries get tier 0 (unrated)
        if cross:
            tier = 0
        else:
            tier = tier_map.get(entry_id, 3)

        pmid_a = str(entry.get("source_pmid", ""))
        pmid_b = str(entry.get("source_pmid_b", ""))
        abstract_a = abstract_map.get(pmid_a, "")
        abstract_b = abstract_map.get(pmid_b, "") if cross else ""

        output_records.append(build_output_record(entry, tier, abstract_a, abstract_b))

    # Validate field set consistency
    expected_keys = {
        "id", "entry_source", "source_pmid", "source_doi", "paper_title",
        "claim_a", "claim_b", "is_genuine_contradiction", "contradiction_type",
        "confidence", "rationale", "abstract_text", "confidence_tier",
        "source_pmid_b", "source_doi_b", "paper_title_b", "abstract_text_b",
    }
    actual_keys = set(output_records[0].keys()) if output_records else set()
    if actual_keys != expected_keys:
        extra = actual_keys - expected_keys
        missing = expected_keys - actual_keys
        if extra:
            print(f"WARNING: unexpected fields: {extra}", file=sys.stderr)
        if missing:
            print(f"WARNING: missing fields: {missing}", file=sys.stderr)

    # Write output
    write_output(output_records, OUTPUT_PATH)

    # Print summary
    print_summary(output_records)


if __name__ == "__main__":
    main()
