#!/usr/bin/env python3
"""
build_corpus_v4_cross.py — Cross-Paper Contradiction Corpus Expansion

Builds contradiction pairs from DIFFERENT papers (cross-paper), complementing
the existing within-abstract corpus (v3). Uses type-specific PubMed queries
to find papers discussing conflicting results, then extracts claim pairs
using contradiction marker matching.

Architecture:
  Phase 1: Paper acquisition via PubMed (type-specific queries)
  Phase 2: Cross-paper pair extraction (marker-based sentence matching)
  Phase 3: Gemini 2.5 Flash classification (contrastive prompt, plain text JSON)
  Phase 4: Quality filtering + corpus merge

Key differences from build_corpus_v2.py:
  - Plain text JSON (NOT responseSchema — avoids Gemini STRING truncation bug)
  - Contrastive decision-tree prompt (83.7% type match vs baseline 25.8%)
  - Checkpoint-based resume for Gemini classification
  - Separate output: corpus_cross_paper.jsonl

Usage:
  export GEMINI_API_KEY=<your-key>
  python build_corpus_v4_cross.py --dry-run     # Phase 1-2 only (no Gemini)
  python build_corpus_v4_cross.py               # Full pipeline
  python build_corpus_v4_cross.py --phase 3     # Resume from Phase 3

Output:
  output/v4/papers_{type}.jsonl
  output/v4/candidates_{type}.jsonl
  output/v4/checkpoint.jsonl
  output/v4/corpus_cross_paper.jsonl
  output/v4/corpus_final_v5.jsonl (merged with v3)
"""
import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

# Add backend to path
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from app.integrations.pubmed import PubMedClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("corpus_v4_cross")

# ── Output paths ──────────────────────────────────────────────────────────────
OUT_DIR = Path(__file__).parent / "output" / "v4"
V3_CORPUS = Path(__file__).parent / "output" / "v3" / "corpus_final.jsonl"

# ── Type-specific PubMed queries (evolved from build_corpus_v2) ──────────────
TYPE_QUERIES: dict[str, list[str]] = {
    "direct": [
        '"failed to replicate" AND (gene OR protein) AND (cancer OR disease)',
        '"opposite results" AND (cell line OR in vitro) AND (gene expression OR protein)',
        '"in direct contradiction" AND (biology OR genomics OR cell)',
        '"contradicts previous" AND (study OR findings) AND (molecular OR cellular)',
        '"conflicting results" AND (same cell line OR identical conditions) AND gene',
        '"opposite direction" AND (expression OR activity) AND (same cell type OR same model)',
        '"contradictory findings" AND (overexpression OR knockdown) AND (tumor OR cancer)',
        '"inconsistent with previous" AND (signaling OR pathway) AND (cancer OR inflammation)',
    ],
    "methodological": [
        '"RNA-seq" AND "microarray" AND ("discordant" OR "conflicting" OR "different results")',
        '"single-cell" AND "bulk RNA" AND ("discrepancy" OR "contradictory" OR "inconsistent")',
        '"ChIP-seq" AND "ChIP-qPCR" AND ("inconsistent" OR "conflicting" OR "different")',
        '"platform-dependent" AND (genomics OR transcriptomics OR proteomics)',
        '"assay-dependent" AND (binding OR activity OR expression)',
        '"method-dependent" AND (result OR finding OR conclusion)',
        '"measurement bias" AND (assay OR technique) AND (biomedical OR clinical)',
        '"technical variability" AND (sequencing OR imaging) AND (discrepancy OR inconsistent)',
    ],
    "temporal": [
        '"acute" AND "chronic" AND "opposite" AND (response OR effect OR regulation)',
        '"longitudinal" AND "conflicting" AND (biomarker OR gene OR protein)',
        '"time-dependent" AND "reversal" AND (expression OR activation OR inhibition)',
        '"early" AND "late" AND "opposite effects" AND (treatment OR disease OR condition)',
        '"initial response" AND "subsequent" AND "reversed" AND (drug OR therapy)',
        '"short-term" AND "long-term" AND ("opposite" OR "conflicting") AND (effect OR result)',
        '"biphasic response" AND (drug OR treatment OR compound) AND (cellular OR molecular)',
        '"temporal dynamics" AND "switching" AND (gene expression OR signaling)',
    ],
    "magnitude": [
        '"overestimated" AND (effect size OR odds ratio OR risk) AND (study OR trial)',
        '"high heterogeneity" AND "meta-analysis" AND (I2 OR inconsistency)',
        '"odds ratio" AND "conflicting" AND (exposure OR risk factor) AND disease',
        '"effect size" AND "discrepancy" AND (replication OR validation OR study)',
        '"significantly larger" AND "significantly smaller" AND same AND (treatment OR drug)',
        '"inflated" AND (effect OR association OR estimate) AND (study OR publication)',
        '"modest effect" AND "large effect" AND (same endpoint OR same outcome)',
        '"replication crisis" AND (effect size OR reproducibility) AND (biomedical OR clinical)',
    ],
}

MAX_PER_QUERY = 30
MAX_PAIRS_PER_TYPE = 200

# ── Contradiction markers ────────────────────────────────────────────────────
MARKERS: list[tuple[str, str]] = [
    ("increase", "decrease"), ("upregulate", "downregulate"),
    ("activate", "inhibit"), ("promote", "suppress"),
    ("enhance", "reduce"), ("stimulate", "block"),
    ("higher", "lower"), ("greater", "lesser"),
    ("positive", "negative"), ("agonist", "antagonist"),
    ("overexpressed", "underexpressed"), ("elevated", "reduced"),
    ("significant", "nonsignificant"), ("associated", "not associated"),
    ("protect", "exacerbate"), ("improve", "worsen"),
    ("beneficial", "detrimental"), ("effective", "ineffective"),
]

# ── Gemini config ────────────────────────────────────────────────────────────
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={API_KEY}"
)
SLEEP = 4.5  # 15 RPM free tier

# Contrastive prompt (best type classification: 83.7% match on within-abstract)
SYSTEM_PROMPT = """\
You are a biomedical literature expert classifying contradictions between scientific claims.
These claims come from DIFFERENT papers.

DECISION PROCEDURE — follow these steps IN ORDER. Stop at the first YES.

STEP 1  METHODOLOGICAL?
  Are two DIFFERENT measurement methods, assays, imaging modalities, or analytical
  techniques being compared? And do they yield different results for the SAME biological question?
  → YES = methodological.

STEP 2  TEMPORAL?
  Do the claims describe the SAME system but at DIFFERENT time-points, phases, or
  stages (e.g., acute vs chronic, baseline vs follow-up, early vs late)?
  Time-point differences are GENUINE contradictions, NOT contextual.
  → YES = temporal.

STEP 3  MAGNITUDE?
  Do BOTH claims agree on the DIRECTION of an effect but DISAGREE on HOW LARGE or
  HOW SIGNIFICANT it is?
  → YES = magnitude.

STEP 4  CONTEXTUAL?
  Can the difference be fully explained by different biological contexts: different
  species, cell lines, patient populations, organs, or experimental conditions?
  → YES = contextual. is_genuine_contradiction = false.

STEP 5  If none of the above: DIRECT.
  Opposite directional effects on the same target under the same conditions.

IMPORTANT: Claims from different papers may still be about the SAME biological context.
Do NOT assume "different papers = contextual." Only use contextual when explicit context
differences (species, tissue, cell type, etc.) explain the disagreement.
"""

USER_TEMPLATE = """\
Claim A (PMID {pmid_a}):
{claim_a}

Claim B (PMID {pmid_b}):
{claim_b}

Follow the 5-step decision procedure.
Output ONLY a JSON object (no markdown, no extra text):
{{"is_genuine_contradiction": true, "contradiction_type": "direct", "confidence": 0.90, "rationale": "Step 1: no..."}}"""


# ── Phase 1: Paper acquisition ───────────────────────────────────────────────
def fetch_papers(ctype: str) -> list[dict]:
    """Fetch papers via type-specific PubMed queries."""
    client = PubMedClient()
    seen_pmids: set[str] = set()
    papers: list[dict] = []
    queries = TYPE_QUERIES.get(ctype, [])

    for query in queries:
        try:
            results = client.search(query, max_results=MAX_PER_QUERY, sort="relevance")
            time.sleep(0.35)  # NCBI rate limit
        except Exception as e:
            log.warning("[%s] PubMed search failed: %s", ctype, e)
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

        log.info("  [%s] query=%r → %d new (total %d)", ctype, query[:50], new, len(papers))

    log.info("[%s] Phase 1: %d papers", ctype, len(papers))
    return papers


# ── Phase 2: Cross-paper pair extraction ─────────────────────────────────────
def extract_sentences(text: str, max_sentences: int = 8) -> list[str]:
    """Extract sentences from abstract text."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 30][:max_sentences]


def has_marker(sent_a: str, sent_b: str) -> bool:
    """Check if two sentences have opposing marker terms."""
    a_low = sent_a.lower()
    b_low = sent_b.lower()
    for t1, t2 in MARKERS:
        if (t1 in a_low and t2 in b_low) or (t2 in a_low and t1 in b_low):
            return True
    return False


def find_cross_pairs(papers: list[dict], ctype: str) -> list[dict]:
    """Extract cross-paper sentence pairs with contradiction markers."""
    pairs: list[dict] = []
    pair_counter = 0
    seen_pmid_pairs: set[tuple[str, str]] = set()

    for i, pa in enumerate(papers):
        if len(pairs) >= MAX_PAIRS_PER_TYPE:
            break
        sents_a = extract_sentences(pa["abstract"])

        for pb in papers[i + 1:]:
            if len(pairs) >= MAX_PAIRS_PER_TYPE:
                break

            pmid_pair = (min(pa["pmid"], pb["pmid"]), max(pa["pmid"], pb["pmid"]))
            if pmid_pair in seen_pmid_pairs:
                continue

            sents_b = extract_sentences(pb["abstract"])
            found = False
            for sa in sents_a:
                for sb in sents_b:
                    if has_marker(sa, sb):
                        pair_counter += 1
                        pairs.append({
                            "pair_id": f"V4-CROSS-{ctype[:3].upper()}-{pair_counter:04d}",
                            "domain": ctype,
                            "intended_type": ctype,
                            "claim_a": sa,
                            "claim_b": sb,
                            "pmid_a": pa["pmid"],
                            "pmid_b": pb["pmid"],
                            "doi_a": pa.get("doi", ""),
                            "doi_b": pb.get("doi", ""),
                            "title_a": pa["title"],
                            "title_b": pb["title"],
                            "year_a": pa.get("year", ""),
                            "year_b": pb.get("year", ""),
                        })
                        seen_pmid_pairs.add(pmid_pair)
                        found = True
                        break
                if found:
                    break

    log.info("[%s] Phase 2: %d cross-paper pairs", ctype, len(pairs))
    return pairs


# ── Phase 3: Gemini classification ──────────────────────────────────────────
def parse_response(text: str) -> dict | None:
    """Parse Gemini JSON response (plain text, no responseSchema)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    valid_types = {"direct", "magnitude", "methodological", "temporal", "contextual"}

    try:
        data = json.loads(text)
        ct = (data.get("contradiction_type") or "").strip().lower()
        genuine = bool(data.get("is_genuine_contradiction", False))
        if not genuine and (not ct or ct not in valid_types):
            ct = "contextual"
        if ct not in valid_types:
            return None
        return {
            "contradiction_type": ct,
            "confidence": float(data.get("confidence", 0.0)),
            "is_genuine_contradiction": genuine,
            "rationale": str(data.get("rationale", "")),
        }
    except (json.JSONDecodeError, ValueError):
        pass

    # Regex fallback
    ct_m = re.search(r'"contradiction_type"\s*:\s*"(\w+)"', text)
    conf_m = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    genuine_m = re.search(r'"is_genuine_contradiction"\s*:\s*(true|false)', text)
    rationale_m = re.search(r'"rationale"\s*:\s*"([^"]{5,})"', text)

    if ct_m and conf_m and genuine_m:
        ct = ct_m.group(1)
        if ct not in valid_types:
            return None
        return {
            "contradiction_type": ct,
            "confidence": float(conf_m.group(1)),
            "is_genuine_contradiction": genuine_m.group(1) == "true",
            "rationale": rationale_m.group(1) if rationale_m else "[truncated]",
        }
    return None


async def classify_pairs(all_pairs: list[dict], checkpoint_file: Path) -> list[dict]:
    """Classify all pairs with Gemini, checkpoint-safe."""
    done: dict[str, dict] = {}
    if checkpoint_file.exists():
        for line in open(checkpoint_file):
            if line.strip():
                r = json.loads(line)
                done[r["pair_id"]] = r
        log.info("Checkpoint loaded: %d rows", len(done))

    remaining = [p for p in all_pairs if p["pair_id"] not in done]
    log.info("Classify: %d total | %d done | %d remaining", len(all_pairs), len(done), len(remaining))

    if not remaining:
        return list(done.values())

    est = len(remaining) * SLEEP / 60
    log.info("Estimated: %.0f min", est)

    ckpt_f = open(checkpoint_file, "a")
    ok = fail = 0

    async with httpx.AsyncClient(timeout=60) as client:
        for i, pair in enumerate(remaining):
            user_msg = USER_TEMPLATE.format(
                pmid_a=pair["pmid_a"],
                claim_a=pair["claim_a"][:400],
                pmid_b=pair["pmid_b"],
                claim_b=pair["claim_b"][:400],
            )

            payload = {
                "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 768,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }

            pred = None
            try:
                resp = await client.post(API_URL, json=payload, timeout=45.0)
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        pred = parse_response(parts[0].get("text", ""))
            except Exception as e:
                log.warning("API error for %s: %s", pair["pair_id"], e)

            result = {
                "pair_id": pair["pair_id"],
                "domain": pair["domain"],
                "intended_type": pair["intended_type"],
                "claim_a": pair["claim_a"],
                "claim_b": pair["claim_b"],
                "pmid_a": pair["pmid_a"],
                "pmid_b": pair["pmid_b"],
                "doi_a": pair.get("doi_a", ""),
                "doi_b": pair.get("doi_b", ""),
                "title_a": pair.get("title_a", ""),
                "title_b": pair.get("title_b", ""),
                "year_a": pair.get("year_a", ""),
                "year_b": pair.get("year_b", ""),
                "label": pred,
                "parse_failed": pred is None,
            }

            done[pair["pair_id"]] = result
            ckpt_f.write(json.dumps(result) + "\n")
            ckpt_f.flush()

            if pred:
                ok += 1
            else:
                fail += 1

            if (i + 1) % 20 == 0 or (i + 1) == len(remaining):
                log.info("  %d/%d | ok=%d fail=%d", i + 1, len(remaining), ok, fail)

            await asyncio.sleep(SLEEP)

    ckpt_f.close()
    return list(done.values())


# ── Phase 4: Filter + merge ─────────────────────────────────────────────────
def filter_and_build_corpus(classified: list[dict], conf_threshold: float = 0.80) -> list[dict]:
    """Filter classified pairs into corpus entries."""
    corpus = []
    type_counts: Counter = Counter()

    for entry in classified:
        label = entry.get("label")
        if not label or entry.get("parse_failed"):
            continue

        conf = label.get("confidence", 0.0)
        if conf < conf_threshold or conf > 1.0:
            continue

        ct = label["contradiction_type"]
        genuine = label["is_genuine_contradiction"]

        corpus_entry = {
            "id": entry["pair_id"],
            "source_pmid": entry["pmid_a"],
            "source_pmid_b": entry["pmid_b"],
            "source_doi": entry.get("doi_a", ""),
            "source_doi_b": entry.get("doi_b", ""),
            "paper_title": entry.get("title_a", ""),
            "paper_title_b": entry.get("title_b", ""),
            "domain": entry["domain"],
            "extraction_pattern": "cross_paper",
            "claim_a": entry["claim_a"],
            "claim_b": entry["claim_b"],
            "contradiction_type": ct,
            "is_genuine_contradiction": genuine,
            "confidence": conf,
            "rationale": label.get("rationale", ""),
            "intended_type": entry["intended_type"],
            "_partial_parse": False,
            "_source": "cross_paper",
        }

        corpus.append(corpus_entry)
        type_counts[ct] += 1

    # Sort: genuine first, then by type, then confidence desc
    corpus.sort(key=lambda e: (
        0 if e["is_genuine_contradiction"] else 1,
        e["contradiction_type"],
        -e["confidence"],
    ))

    log.info("Phase 4: %d entries after filtering (conf >= %.2f)", len(corpus), conf_threshold)
    for ct in ["direct", "temporal", "magnitude", "methodological", "contextual"]:
        log.info("  %s: %d", ct, type_counts.get(ct, 0))

    return corpus


def merge_with_v3(cross_corpus: list[dict], v3_path: Path, output_path: Path) -> list[dict]:
    """Merge cross-paper corpus with existing v3 within-abstract corpus."""
    v3_entries = []
    if v3_path.exists():
        v3_entries = [json.loads(l) for l in open(v3_path) if l.strip()]

    # Check for ID collisions
    v3_ids = {e["id"] for e in v3_entries}
    cross_new = [e for e in cross_corpus if e["id"] not in v3_ids]

    merged = v3_entries + cross_new
    merged.sort(key=lambda e: (
        0 if e["is_genuine_contradiction"] else 1,
        e["contradiction_type"],
        -e.get("confidence", 0),
    ))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for e in merged:
            f.write(json.dumps(e) + "\n")

    genuine_v3 = sum(1 for e in v3_entries if e.get("is_genuine_contradiction"))
    genuine_cross = sum(1 for e in cross_new if e.get("is_genuine_contradiction"))

    log.info("Merged corpus:")
    log.info("  v3 (within-abstract): %d entries (%d genuine)", len(v3_entries), genuine_v3)
    log.info("  v4 (cross-paper):     %d entries (%d genuine)", len(cross_new), genuine_cross)
    log.info("  Total merged:         %d entries", len(merged))
    log.info("  Output: %s", output_path)

    return merged


# ── Main ─────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Cross-paper contradiction corpus expansion")
    parser.add_argument("--dry-run", action="store_true",
                        help="Phase 1-2 only (no Gemini classification)")
    parser.add_argument("--phase", type=int, default=1,
                        help="Start from phase (1=papers, 2=pairs, 3=classify, 4=filter+merge)")
    parser.add_argument("--conf", type=float, default=0.80,
                        help="Confidence threshold for filtering")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    types = ["direct", "methodological", "temporal", "magnitude"]

    # ── Phase 1: Paper acquisition ──
    if args.phase <= 1:
        print("\n" + "=" * 65)
        print("Phase 1: Paper Acquisition via PubMed")
        print("=" * 65)

        for ctype in types:
            papers = fetch_papers(ctype)
            out = OUT_DIR / f"papers_{ctype}.jsonl"
            with open(out, "w") as f:
                for p in papers:
                    f.write(json.dumps(p) + "\n")
            log.info("  → %s (%d papers)", out.name, len(papers))

    # ── Phase 2: Cross-paper pair extraction ──
    if args.phase <= 2:
        print("\n" + "=" * 65)
        print("Phase 2: Cross-Paper Pair Extraction")
        print("=" * 65)

        all_pairs: list[dict] = []
        for ctype in types:
            papers_file = OUT_DIR / f"papers_{ctype}.jsonl"
            if not papers_file.exists():
                log.warning("[%s] No papers file — skipping", ctype)
                continue
            papers = [json.loads(l) for l in open(papers_file) if l.strip()]
            pairs = find_cross_pairs(papers, ctype)

            out = OUT_DIR / f"candidates_{ctype}.jsonl"
            with open(out, "w") as f:
                for p in pairs:
                    f.write(json.dumps(p) + "\n")
            all_pairs.extend(pairs)
            log.info("  → %s (%d pairs)", out.name, len(pairs))

        log.info("Phase 2 total: %d candidate pairs", len(all_pairs))

        if args.dry_run:
            print("\nDRY RUN complete. Phase 1-2 summary:")
            for ctype in types:
                p_file = OUT_DIR / f"papers_{ctype}.jsonl"
                c_file = OUT_DIR / f"candidates_{ctype}.jsonl"
                n_papers = len([l for l in open(p_file) if l.strip()]) if p_file.exists() else 0
                n_pairs = len([l for l in open(c_file) if l.strip()]) if c_file.exists() else 0
                print(f"  {ctype:20s}: {n_papers:>4} papers → {n_pairs:>4} pairs")
            return

    # ── Phase 3: Gemini classification ──
    if args.phase <= 3:
        if not API_KEY:
            raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")

        print("\n" + "=" * 65)
        print("Phase 3: Gemini Classification (contrastive prompt)")
        print("=" * 65)

        # Load all candidate pairs
        all_pairs = []
        for ctype in types:
            c_file = OUT_DIR / f"candidates_{ctype}.jsonl"
            if c_file.exists():
                all_pairs.extend(json.loads(l) for l in open(c_file) if l.strip())

        checkpoint = OUT_DIR / "checkpoint.jsonl"
        classified = await classify_pairs(all_pairs, checkpoint)
        log.info("Phase 3 complete: %d classified", len(classified))

    # ── Phase 4: Filter + merge ──
    if args.phase <= 4:
        print("\n" + "=" * 65)
        print("Phase 4: Filter + Merge")
        print("=" * 65)

        # Load classified results from checkpoint
        checkpoint = OUT_DIR / "checkpoint.jsonl"
        if not checkpoint.exists():
            log.error("No checkpoint file found — run Phase 3 first")
            return

        # Dedup checkpoint (resume can append duplicates)
        seen: dict[str, dict] = {}
        for line in open(checkpoint):
            if line.strip():
                r = json.loads(line)
                seen[r["pair_id"]] = r
        classified = list(seen.values())

        # Filter
        cross_corpus = filter_and_build_corpus(classified, conf_threshold=args.conf)

        # Save cross-paper corpus separately
        cross_out = OUT_DIR / "corpus_cross_paper.jsonl"
        with open(cross_out, "w") as f:
            for e in cross_corpus:
                f.write(json.dumps(e) + "\n")
        log.info("Cross-paper corpus: %s (%d entries)", cross_out, len(cross_corpus))

        # Merge with v3
        merged_out = OUT_DIR / "corpus_final_v5.jsonl"
        merge_with_v3(cross_corpus, V3_CORPUS, merged_out)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
