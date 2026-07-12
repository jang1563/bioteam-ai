#!/usr/bin/env python3
"""
Phase C: Expand methodological contradiction corpus via targeted PubMed queries.

Current methodological genuine: 7 entries
Target: +8 more (total ~15)

Strategy: New PubMed queries focused on papers that EXPLICITLY compare two
different methods/approaches within the same abstract, yielding discordant results.

Output: corpus_final_v4.jsonl (= corpus_final_v3.jsonl + new methodological entries)
"""
from __future__ import annotations

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))
from app.integrations.pubmed import PubMedClient  # noqa: E402

OUT_DIR = Path(__file__).parent / "output" / "v3"
CORPUS_V3 = OUT_DIR / "corpus_final_v3.jsonl"
CORPUS_V4 = OUT_DIR / "corpus_final_v4.jsonl"
CANDIDATES_FILE = OUT_DIR / "candidates_methodological_phase_c.jsonl"

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
CONCURRENCY = 3
MIN_SLEEP = 4.0
CONF_THRESHOLD_METHODOLOGICAL = 0.80

# ── New methodological PubMed queries ─────────────────────────────────────────
# Focused on method comparison papers with within-abstract discordance

MET_QUERIES = [
    # Omics method comparison
    '"RNA-seq" AND "microarray" AND ("whereas" OR "however") AND ("expression" OR "upregulat")',
    '"proteomics" AND "transcriptomics" AND ("discordant" OR "inconsistent" OR "whereas") AND (correlation OR agreement)',
    '"single-cell" AND "bulk" AND ("however" OR "whereas") AND (heterogeneity OR expression)',
    # Imaging method comparison
    '"PET" AND ("MRI" OR "CT") AND ("however" OR "whereas" OR "contrast") AND (detection OR sensitivity)',
    '"ultrasound" AND "MRI" AND ("however" OR "whereas") AND (detection OR measurement OR accuracy)',
    # Diagnostic test comparison
    '"sensitivity" AND "specificity" AND "versus" AND ("however" OR "whereas") AND (method OR assay OR test)',
    '"ELISA" AND ("western blot" OR "PCR") AND ("inconsistent" OR "discordant" OR "contrast")',
    '"immunohistochemistry" AND ("PCR" OR "FISH") AND ("discordant" OR "inconsistent" OR "contrast")',
    # Statistical method comparison in meta-analyses
    '"fixed-effect" AND "random-effect" AND ("however" OR "whereas" OR "difference") AND (heterogeneity OR estimate)',
    '"pooled" AND "subgroup" AND ("however" OR "whereas") AND (analysis OR inconsistent OR heterogeneous)',
    # Clinical trial vs observational
    '"randomized" AND "observational" AND ("whereas" OR "however" OR "in contrast") AND (effect OR association OR benefit)',
    '"clinical trial" AND "real-world" AND ("however" OR "whereas" OR "discordant") AND (outcome OR efficacy)',
    # Sequencing technology comparison
    '"whole genome sequencing" AND "whole exome" AND ("however" OR "whereas") AND (variant OR detection)',
    '"short-read" AND "long-read" AND ("however" OR "whereas") AND (assembly OR accuracy OR detection)',
]

MAX_PER_QUERY = 30

# ── Contrast patterns ──────────────────────────────────────────────────────────
CONTRAST_PATTERNS = [
    r"([A-Z][^.!?]{20,200}?)\s*,?\s*\bwhereas\b\s*([^.!?]{20,200}[.!?])",
    r"([A-Z][^.!?]{20,200}?)\s*,?\s*\bin contrast\b[,]?\s*([^.!?]{20,200}[.!?])",
    r"([A-Z][^.!?]{20,200}?)\s*,?\s*\bconversely\b[,]?\s*([^.!?]{20,200}[.!?])",
    r"([A-Z][^.!?]{20,200}?)\s*[.!?]\s*\bHowever\b[,]?\s*([^.!?]{20,200}[.!?])",
    r"([A-Z][^.!?]{20,200}?)\s*,?\s*\bwhile\b\s*([^.!?]{20,200}[.!?])",
    r"([A-Z][^;.!?]{20,200}?);\s*however[,]?\s*([^.!?]{20,200}[.!?])",
    r"([A-Z][^.!?]{20,200}?)\s*,?\s*\bin contrast to\b\s*([^.!?]{20,200}[.!?])",
]

VALID_TYPES = {"direct", "magnitude", "methodological", "temporal", "contextual"}

_SYSTEM = """\
You are a biomedical literature expert classifying scientific contradictions.
Both claims come from the SAME abstract. Assign the MOST SPECIFIC type.

TYPES (apply in order 1→5, stop at first match):
1. DIRECT: Same gene/protein/phenomenon, same biological context, OPPOSITE direction
2. MAGNITUDE: Same direction, same context, INCOMPATIBLE effect sizes
3. METHODOLOGICAL: Same question, same context, DIFFERENT methods yield opposite results
   Key: Explicitly mentions two DIFFERENT methods/assays/technologies with discordant results
4. TEMPORAL: Same context, results differ specifically due to TIMEPOINT
5. CONTEXTUAL [LAST RESORT]: Results differ SOLELY due to different biological contexts

METHODOLOGICAL examples:
- "RNA-seq showed upregulation whereas microarray showed no change"
- "PCR detected the mutation whereas FISH was negative"
- "Fixed-effect model showed significant association; however, random-effects showed borderline"

Set is_genuine_contradiction=true for types 1-4, false for type 5.
Output ONLY a JSON object (no markdown, no extra text). Use these exact string values:
- "direct", "magnitude", "methodological", "temporal", or "contextual"
"""

_USER = """\
Claim A (from same abstract as Claim B):
{claim_a}

Claim B:
{claim_b}

Type hint: methodological (different methods, same question, discordant results)
Classify following types 1→5 in order.

{{"contradiction_type": "direct or magnitude or methodological or temporal or contextual", "confidence": 0.95, "is_genuine_contradiction": true, "rationale": "2-3 sentences"}}"""


def _clean(text: str, max_len: int = 350) -> str:
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = re.sub(r'["\'\\]', " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def extract_pairs(paper: dict, existing_pmids: set) -> list[dict]:
    """Extract within-abstract contrast pairs from a paper."""
    if paper["pmid"] in existing_pmids:
        return []

    abstract = paper["abstract"]
    pairs = []
    seen = set()

    for i, pattern in enumerate(CONTRAST_PATTERNS):
        for m in re.finditer(pattern, abstract, re.IGNORECASE):
            a = _clean(m.group(1))
            b = _clean(m.group(2))
            key = (a[:60], b[:60])
            if key in seen or len(a) < 25 or len(b) < 25:
                continue
            seen.add(key)
            pairs.append({
                "paper": paper,
                "claim_a": a,
                "claim_b": b,
                "pattern": i,
            })

    return pairs


def _parse_response(text: str) -> dict | None:
    """Parse JSON from Gemini plain text response."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    try:
        data = json.loads(text)
        ct = data.get("contradiction_type", "")
        if ct not in VALID_TYPES:
            return None
        return {
            "contradiction_type": ct,
            "confidence": float(data.get("confidence", 0.0)),
            "is_genuine_contradiction": bool(data.get("is_genuine_contradiction", False)),
            "rationale": str(data.get("rationale", "")),
            "_partial_parse": False,
        }
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    ct_m = re.search(r'"contradiction_type"\s*:\s*"(\w+)"', text)
    conf_m = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    genuine_m = re.search(r'"is_genuine_contradiction"\s*:\s*(true|false)', text)
    rationale_m = re.search(r'"rationale"\s*:\s*"([^"]{5,})"', text)

    if ct_m and conf_m and genuine_m:
        ct = ct_m.group(1)
        if ct not in VALID_TYPES:
            return None
        return {
            "contradiction_type": ct,
            "confidence": float(conf_m.group(1)),
            "is_genuine_contradiction": genuine_m.group(1) == "true",
            "rationale": rationale_m.group(1) if rationale_m else "[truncated]",
            "_partial_parse": True,
        }
    return None


async def classify_pair(client: httpx.AsyncClient, pair: dict, sem: asyncio.Semaphore) -> dict | None:
    async with sem:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": _USER.format(
                claim_a=pair["claim_a"][:350],
                claim_b=pair["claim_b"][:350],
            )}]}],
            "systemInstruction": {"parts": [{"text": _SYSTEM}]},
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 1024,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        try:
            resp = await client.post(API_URL, json=payload, timeout=45.0)
            resp.raise_for_status()
            data = resp.json()
            cand = data.get("candidates", [{}])[0]
            parts = cand.get("content", {}).get("parts", [])
            if not parts:
                return None
            text = parts[0].get("text", "")
            return _parse_response(text)
        except Exception as e:
            log.warning("classify failed: %s", e)
            return None


def load_existing_pmids() -> set:
    """Get PMIDs already in corpus_final_v3 to avoid duplication."""
    if not CORPUS_V3.exists():
        return set()
    entries = [json.loads(l) for l in open(CORPUS_V3) if l.strip()]
    return {e.get("source_pmid", "") for e in entries}


def load_existing_candidates_pmids() -> set:
    """Get PMIDs already processed in phase C candidates to avoid re-fetching."""
    if not CANDIDATES_FILE.exists():
        return set()
    pairs = [json.loads(l) for l in open(CANDIDATES_FILE) if l.strip()]
    return {p.get("claim_a", {}).get("source_pmid", "") for p in pairs}


async def main():
    if not API_KEY:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")

    print("\n" + "=" * 60)
    print("PHASE C: Methodological expansion via meta-analysis queries")
    print("=" * 60)

    # Load existing PMIDs to avoid duplication
    existing_pmids = load_existing_pmids()
    candidate_pmids = load_existing_candidates_pmids()
    skip_pmids = existing_pmids | candidate_pmids
    log.info("Skipping %d already-processed PMIDs", len(skip_pmids))

    # Phase 1: PubMed fetch
    print("\n[Phase 1] PubMed fetch...")
    pubmed = PubMedClient()
    all_papers = []
    seen_pmids = set(skip_pmids)

    for q in MET_QUERIES:
        try:
            results = pubmed.search(q, max_results=MAX_PER_QUERY, sort="relevance")
            time.sleep(0.35)
        except Exception as e:
            log.warning("PubMed failed for %r: %s", q[:50], e)
            continue

        new_papers = 0
        for paper in results:
            if not paper.abstract or paper.pmid in seen_pmids:
                continue
            seen_pmids.add(paper.pmid)
            abstract = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", " ", paper.abstract)
            abstract = re.sub(r"\s+", " ", abstract).strip()
            all_papers.append({
                "pmid": paper.pmid,
                "title": paper.title,
                "abstract": abstract,
                "year": str(paper.year) if paper.year else "",
                "doi": paper.doi or "",
            })
            new_papers += 1

        log.info("  %r → +%d papers (total: %d)", q[:60], new_papers, len(all_papers))

    log.info("[Phase 1] Total new papers: %d", len(all_papers))

    # Phase 2: Pair extraction
    print("\n[Phase 2] Within-abstract pair extraction...")
    all_pairs = []
    pair_counter = 0
    for paper in all_papers:
        pairs = extract_pairs(paper, skip_pmids)
        for p in pairs:
            pair_counter += 1
            pid = f"V3-MET-C{pair_counter:03d}"
            all_pairs.append({
                "pair_id": pid,
                "domain": "biomedical",
                "intended_type": "methodological",
                "extraction_pattern": p["pattern"],
                "claim_a": {
                    "text": p["claim_a"],
                    "source_pmid": p["paper"]["pmid"],
                    "source_doi": p["paper"]["doi"],
                    "paper_title": p["paper"]["title"],
                    "year": p["paper"]["year"],
                },
                "claim_b": {
                    "text": p["claim_b"],
                    "source_pmid": p["paper"]["pmid"],
                    "source_doi": p["paper"]["doi"],
                    "paper_title": p["paper"]["title"],
                    "year": p["paper"]["year"],
                },
                "label": None,
            })

    log.info("[Phase 2] Extracted %d candidate pairs", len(all_pairs))

    if not all_pairs:
        print("No new pairs found — all papers already processed. Exiting.")
        return

    # Phase 3: Gemini classification
    print(f"\n[Phase 3] Classifying {len(all_pairs)} pairs with Gemini...")
    sem = asyncio.Semaphore(CONCURRENCY)
    labeled = []

    async with httpx.AsyncClient(timeout=60) as client:
        tasks = [(p, asyncio.create_task(classify_pair(client, {
            "claim_a": p["claim_a"]["text"],
            "claim_b": p["claim_b"]["text"],
        }, sem))) for p in all_pairs]

        ok = 0
        for i, (pair, task) in enumerate(tasks):
            lbl = await task
            pair["label"] = lbl
            labeled.append(pair)
            if lbl:
                ok += 1
            if (i + 1) % 20 == 0 or (i + 1) == len(tasks):
                log.info("  %d/%d classified (ok=%d)", i + 1, len(tasks), ok)
            await asyncio.sleep(MIN_SLEEP)

    log.info("[Phase 3] Done: ok=%d / %d", ok, len(labeled))

    # Save candidates
    with open(CANDIDATES_FILE, "w") as f:
        for p in labeled:
            f.write(json.dumps(p) + "\n")
    log.info("Saved %d candidates → %s", len(labeled), CANDIDATES_FILE.name)

    # Phase 4: Filter genuine methodological
    print("\n[Phase 4] Filtering genuine methodological entries...")
    genuine_met = []
    for p in labeled:
        lbl = p.get("label")
        if not isinstance(lbl, dict):
            continue
        ct = lbl.get("contradiction_type", "")
        conf = lbl.get("confidence", 0.0)
        genuine = lbl.get("is_genuine_contradiction", False)
        if not genuine or conf < CONF_THRESHOLD_METHODOLOGICAL:
            continue
        if ct != "methodological":
            continue  # Only add genuine methodological type

        corpus_entry = {
            "id": p["pair_id"],
            "source_pmid": p["claim_a"]["source_pmid"],
            "source_doi": p["claim_a"]["source_doi"],
            "paper_title": p["claim_a"]["paper_title"],
            "domain": "biomedical",
            "extraction_pattern": str(p.get("extraction_pattern", "")),
            "claim_a": p["claim_a"]["text"],
            "claim_b": p["claim_b"]["text"],
            "contradiction_type": "methodological",
            "is_genuine_contradiction": True,
            "confidence": conf,
            "rationale": lbl.get("rationale", ""),
            "intended_type": "methodological",
            "_partial_parse": lbl.get("_partial_parse", False),
            "_classifier": "gemini_phase_c",
        }
        genuine_met.append(corpus_entry)
        log.info("  GENUINE: %s  conf=%.2f  A: %s", p["pair_id"], conf, p["claim_a"]["text"][:60])

    log.info("[Phase 4] New genuine methodological: %d", len(genuine_met))

    # Build corpus_final_v4
    existing = [json.loads(l) for l in open(CORPUS_V3) if l.strip()] if CORPUS_V3.exists() else []
    combined = existing + genuine_met
    combined.sort(key=lambda e: (
        0 if e["is_genuine_contradiction"] else 1,
        e["contradiction_type"],
        -e["confidence"],
    ))

    with open(CORPUS_V4, "w") as f:
        for e in combined:
            f.write(json.dumps(e) + "\n")

    genuine_counts = Counter(e["contradiction_type"] for e in combined if e["is_genuine_contradiction"])
    contextual = sum(1 for e in combined if not e["is_genuine_contradiction"])

    print("\n=== corpus_final_v4.jsonl ===")
    print(f"Base (v3)     : {len(existing)} entries")
    print(f"New (Phase C) : {len(genuine_met)} entries (methodological)")
    print(f"Total         : {len(combined)} entries")
    print(f"\nGenuine non-contextual: {sum(genuine_counts.values())}")
    for ct in ["direct", "temporal", "magnitude", "methodological"]:
        print(f"  {ct:20s}: {genuine_counts.get(ct, 0)}")
    print(f"Contextual    : {contextual}")
    print(f"\nOutput: {CORPUS_V4}")


if __name__ == "__main__":
    asyncio.run(main())
