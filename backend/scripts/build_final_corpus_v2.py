#!/usr/bin/env python3
"""
Phase A: Quality-cleaned corpus (corpus_final_v2.jsonl)

Removes 9 entries identified via manual audit:
  - 3 Direct/Method: limitation statements or mutual-uncertainty (not genuine contradictions)
  - 3 Magnitude: truncated claims or knowledge-gap statements
  - 3 Structural: truncated claims (text cut mid-sentence/mid-value, outcome unknown)

Run AFTER build_final_corpus.py (reads corpus_final.jsonl as input).
"""
import json
from collections import Counter
from pathlib import Path

OUT_DIR = Path(__file__).parent / "output" / "v3"
IN_FILE  = OUT_DIR / "corpus_final.jsonl"
OUT_FILE = OUT_DIR / "corpus_final_v2.jsonl"

# Manually verified removal list (Phase A audit)
REMOVE_IDS = {
    # Direct / Method — limitation statements or mutual uncertainty (not genuine contradiction)
    "V3-DIR-0037",  # "hinders their further development" — limitation, not contradiction
    "V3-DIR-0052",  # "BAG3 might interact" (uncertain) vs "was unclear" (uncertain) — both uncertain, no opposition
    "V3-MET-0077",  # "consistency remains controversial" — vague controversy, not direct opposite

    # Magnitude — structural quality issues
    "V3-MAG-0007",  # claim_a truncated mid-sentence ("moderate-certainty evidence)")
    "V3-MAG-0040",  # claim_b truncated mid-value ("it was not statistically significant (p=0.")
    "V3-MAG-0049",  # knowledge gap ("few studies have directly examined") ≠ magnitude conflict

    # Truncated claims — extraction artifact (outcome/context unknown)
    "V3-TEM-0092",  # claim_a = "x 10(-9) m(2)/s or T(2) >or= 130 ms" (truncated start); claim_b ADC < 0. (truncated p-value)
    "V3-TEM-0075",  # claim_a = "cases per 100,000 consumers by PR, CE..." (truncated start); claim_b "p < 0." (truncated)
    "V3-MET-0083",  # claim_b = "glutaraldehyde-killed or heat-killed F." (truncated — no outcome; Gemini inferred result)
}

def main():
    entries = [json.loads(l) for l in open(IN_FILE) if l.strip()]
    kept, removed = [], []

    for e in entries:
        if e["id"] in REMOVE_IDS:
            removed.append(e)
        else:
            kept.append(e)

    # Write cleaned corpus
    with open(OUT_FILE, "w") as f:
        for e in kept:
            f.write(json.dumps(e) + "\n")

    # Stats
    genuine_types = Counter(
        e["contradiction_type"] for e in kept if e["is_genuine_contradiction"]
    )
    total_genuine = sum(genuine_types.values())
    total_contextual = sum(1 for e in kept if not e["is_genuine_contradiction"])

    print("=== corpus_final_v2.jsonl ===")
    print(f"Input  : {len(entries)} entries")
    print(f"Removed: {len(removed)} (quality issues)")
    print(f"Output : {len(kept)} entries")
    print(f"\nGenuine non-contextual: {total_genuine}")
    for ct in ["direct", "temporal", "magnitude", "methodological"]:
        n = genuine_types.get(ct, 0)
        print(f"  {ct:20s}: {n}")
    print(f"Contextual (negative) : {total_contextual}")
    print(f"\nRemoved IDs: {[e['id'] for e in removed]}")
    print(f"Output file: {OUT_FILE}")


if __name__ == "__main__":
    main()
