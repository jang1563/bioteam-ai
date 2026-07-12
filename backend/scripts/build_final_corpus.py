#!/usr/bin/env python3
"""
Build final contradiction corpus from v4 (= retry) classified files.

Quality filters applied:
1. confidence > 1.0  → remove (Gemini API bug — out-of-range values)
2. confidence < 0.80 → remove for non-temporal types (quality risk)
3. label must be dict (not None)
4. Include both genuine (is_genuine_contradiction=True) and
   contextual (is_genuine_contradiction=False, type=contextual)

Output schema per entry:
{
  "id": "V3-DIR-0047",
  "source_pmid": "35843572",
  "source_doi": "...",
  "paper_title": "...",
  "domain": "molecular_biology",
  "extraction_pattern": "0",
  "claim_a": "...",
  "claim_b": "...",
  "contradiction_type": "direct",
  "is_genuine_contradiction": true,
  "confidence": 1.0,
  "rationale": "...",
  "intended_type": "direct",
  "_partial_parse": false
}
"""
import json
from pathlib import Path

OUT_DIR = Path(__file__).parent / "output" / "v3"
FINAL_FILE = OUT_DIR / "corpus_final.jsonl"
STATS_FILE = OUT_DIR / "corpus_final_stats.json"

CONF_THRESHOLD_GENERAL = 0.80
CONF_MAX = 1.0  # Gemini bug: some values are > 1.0

# For temporal type, allow conf >= 0.75 (high-quality type)
CONF_THRESHOLD_TEMPORAL = 0.75


def load_v4_entries(ctype: str) -> list[dict]:
    """Load entries from v4 file (= retry if v4 identical), preferring v4."""
    v4 = OUT_DIR / f"candidates_{ctype}_v4.jsonl"
    retry = OUT_DIR / f"candidates_{ctype}_retry.jsonl"
    src = v4 if v4.exists() else retry
    entries = []
    if not src.exists():
        return entries
    with open(src) as f:
        for line in f:
            if not line.strip():
                continue
            entries.append(json.loads(line))
    return entries


def passes_quality_filter(entry: dict, ctype_source: str) -> bool:
    """Return True if entry passes quality filters."""
    lbl = entry.get("label")
    if not isinstance(lbl, dict):
        return False

    conf = lbl.get("confidence", 0.0)
    ct = lbl.get("contradiction_type", "")

    # Remove out-of-range confidence (Gemini API bug)
    if conf > CONF_MAX:
        return False

    # Confidence threshold per type
    threshold = CONF_THRESHOLD_TEMPORAL if ct == "temporal" else CONF_THRESHOLD_GENERAL
    if conf < threshold:
        return False

    return True


def to_corpus_entry(entry: dict) -> dict:
    """Convert internal format to clean corpus schema."""
    lbl = entry["label"]
    claim_a = entry.get("claim_a", {})
    claim_b = entry.get("claim_b", {})

    return {
        "id": entry.get("pair_id", ""),
        "source_pmid": claim_a.get("source_pmid", ""),
        "source_doi": claim_a.get("source_doi", ""),
        "paper_title": claim_a.get("paper_title", ""),
        "domain": entry.get("domain", ""),
        "extraction_pattern": str(entry.get("extraction_pattern", "")),
        "claim_a": claim_a.get("text", ""),
        "claim_b": claim_b.get("text", ""),
        "contradiction_type": lbl.get("contradiction_type", ""),
        "is_genuine_contradiction": lbl.get("is_genuine_contradiction", False),
        "confidence": lbl.get("confidence", 0.0),
        "rationale": lbl.get("rationale", ""),
        "intended_type": entry.get("intended_type", ""),
        "_partial_parse": lbl.get("_partial_parse", False),
    }


def main():
    all_entries = []
    stats: dict = {
        "total_input": 0,
        "passed_filter": 0,
        "by_type": {},
        "genuine_by_type": {},
        "contextual_total": 0,
        "removed_conf_out_of_range": 0,
        "removed_conf_low": 0,
        "removed_none": 0,
    }

    for ctype in ["direct", "methodological", "temporal", "magnitude"]:
        entries = load_v4_entries(ctype)
        stats["total_input"] += len(entries)

        type_entries = []
        for e in entries:
            lbl = e.get("label")
            if not isinstance(lbl, dict):
                stats["removed_none"] += 1
                continue

            conf = lbl.get("confidence", 0.0)
            ct = lbl.get("contradiction_type", "")

            if conf > CONF_MAX:
                stats["removed_conf_out_of_range"] += 1
                continue

            threshold = CONF_THRESHOLD_TEMPORAL if ct == "temporal" else CONF_THRESHOLD_GENERAL
            if conf < threshold:
                stats["removed_conf_low"] += 1
                continue

            stats["passed_filter"] += 1
            ce = to_corpus_entry(e)
            type_entries.append(ce)

            ct2 = ce["contradiction_type"]
            if ct2 not in stats["by_type"]:
                stats["by_type"][ct2] = 0
            stats["by_type"][ct2] += 1

            if ce["is_genuine_contradiction"]:
                if ct2 not in stats["genuine_by_type"]:
                    stats["genuine_by_type"][ct2] = 0
                stats["genuine_by_type"][ct2] += 1
            else:
                stats["contextual_total"] += 1

        all_entries.extend(type_entries)
        print(f"[{ctype:15s}] input={len(entries)} passed={len(type_entries)}")

    # Sort: genuine first, then contextual; within each group sort by type then conf desc
    all_entries.sort(key=lambda e: (
        0 if e["is_genuine_contradiction"] else 1,
        e["contradiction_type"],
        -e["confidence"],
    ))

    # Write final corpus
    with open(FINAL_FILE, "w") as f:
        for e in all_entries:
            f.write(json.dumps(e) + "\n")

    # Write stats
    stats["total_output"] = len(all_entries)
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

    print("\n=== FINAL CORPUS STATS ===")
    print(f"Total input entries : {stats['total_input']}")
    print(f"Removed (None)      : {stats['removed_none']}")
    print(f"Removed (conf>1.0)  : {stats['removed_conf_out_of_range']}")
    print(f"Removed (conf<thr)  : {stats['removed_conf_low']}")
    print(f"Passed filter       : {stats['passed_filter']}")
    print(f"Output file         : {FINAL_FILE}")
    print("\nBy contradiction type (all labeled):")
    for ct, n in sorted(stats["by_type"].items()):
        g = stats["genuine_by_type"].get(ct, 0)
        print(f"  {ct:20s}: total={n} genuine={g} contextual={n-g}")
    print(f"\nTotal genuine non-contextual: {sum(stats['genuine_by_type'].values())}")
    print(f"Total contextual            : {stats['contextual_total']}")


if __name__ == "__main__":
    main()
