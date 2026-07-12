#!/usr/bin/env python3
"""Expand magnitude corpus candidates with Gemini free-tier classification.

Pipeline:
1) PubMed fetch using magnitude-focused queries
2) Within-abstract contrast pair extraction
3) Gemini plain-text JSON classification (resume-safe checkpoint)
4) Select high-confidence genuine magnitude additions

Usage:
  cd backend
  ../.venv/bin/python -m scripts.expand_magnitude_corpus --dry-run
  ../.venv/bin/python -m scripts.expand_magnitude_corpus --max-pairs 120 --limit-classify 80
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import httpx
from app.integrations.pubmed import PubMedClient, PubMedPaper

TYPE_QUERIES = [
    '"effect size" AND ("larger" OR "smaller") AND ("previous" OR "reported") AND (study OR meta)',
    '"odds ratio" AND ("inconsistent" OR "heterogeneous") AND (meta-analysis OR systematic)',
    '"hazard ratio" AND "discrepancy" AND (survival OR outcome OR treatment)',
    '"high heterogeneity" AND "I2" AND ("however" OR "while") AND (estimate OR effect)',
    '"overestimated" AND (risk OR effect OR association) AND (study OR cohort)',
]

CONTRAST_PATTERNS = [
    r"([A-Z][^.!?]{20,180}?)\s*,?\s*\bwhereas\b\s*([^.!?]{20,180}[.!?])",
    r"([A-Z][^.!?]{20,180}?)\s*,?\s*\bin contrast\b[,]?\s*([^.!?]{20,180}[.!?])",
    r"([A-Z][^.!?]{20,180}?)\s*,?\s*\bconversely\b[,]?\s*([^.!?]{20,180}[.!?])",
    r"([A-Z][^.!?]{20,180}?)\s*[.!?]\s*\bHowever\b[,]?\s*([^.!?]{20,180}[.!?])",
    r"([A-Z][^.!?]{20,180}?)\s*,?\s*\bwhile\b\s*([^.!?]{20,180}[.!?])",
    r"([A-Z][^.!?]{20,180}?)\s*,?\s*\byet\b\s*([^.!?]{20,180}[.!?])",
    r"([A-Z][^;.!?]{20,180}?);\s*however[,]?\s*([^.!?]{20,180}[.!?])",
]

VALID_TYPES = {"direct", "contextual", "methodological", "temporal", "magnitude"}

SYSTEM_PROMPT = """\
You are a biomedical literature expert classifying contradiction types.
Both claims come from the SAME abstract.

Use this order:
1) DIRECT: same context, opposite direction
2) MAGNITUDE: same direction/context, incompatible effect size or significance strength
3) METHODOLOGICAL: same question/context, method/platform differences drive discrepancy
4) TEMPORAL: same context, timepoint/stage differences drive discrepancy
5) CONTEXTUAL: differences explained by biological context only

Set is_genuine_contradiction=true for types 1-4, false for contextual.
Return only JSON.
"""

USER_TEMPLATE = """\
Claim A: {claim_a}

Claim B: {claim_b}

Output ONLY JSON:
{{"contradiction_type":"direct|magnitude|methodological|temporal|contextual","confidence":0.90,"is_genuine_contradiction":true,"rationale":"1-2 sentences"}}
"""


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent / "output" / "v3" / "magnitude_expand"
    parser = argparse.ArgumentParser(description="Expand magnitude candidates.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-per-query", type=int, default=40)
    parser.add_argument("--max-pairs", type=int, default=200)
    parser.add_argument("--limit-classify", type=int, default=80)
    parser.add_argument("--confidence-threshold", type=float, default=0.8)
    parser.add_argument("--sleep", type=float, default=4.5, help="Seconds between API calls.")
    parser.add_argument("--reset", action="store_true", help="Reset classification checkpoint.")
    parser.add_argument("--output-dir", type=Path, default=base)
    return parser.parse_args()


def _clean_text(text: str, max_len: int = 320) -> str:
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = re.sub(r'["\'\\]', " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _parse_response(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        data = json.loads(text)
        ctype = str(data.get("contradiction_type", ""))
        if ctype not in VALID_TYPES:
            return None
        return {
            "contradiction_type": ctype,
            "confidence": float(data.get("confidence", 0.0)),
            "is_genuine_contradiction": bool(data.get("is_genuine_contradiction", False)),
            "rationale": str(data.get("rationale", "")),
        }
    except Exception:
        return None


def fetch_papers(queries: list[str], max_per_query: int) -> list[dict]:
    client = PubMedClient()
    seen_pmids: set[str] = set()
    papers: list[dict] = []
    for query in queries:
        try:
            results: list[PubMedPaper] = client.search(query, max_results=max_per_query, sort="relevance")
            time.sleep(0.35)
        except Exception:
            continue
        for paper in results:
            if not paper.abstract or paper.pmid in seen_pmids:
                continue
            seen_pmids.add(paper.pmid)
            abstract = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", " ", paper.abstract)
            abstract = re.sub(r"\s+", " ", abstract).strip()
            papers.append(
                {
                    "pmid": paper.pmid,
                    "title": paper.title,
                    "abstract": abstract,
                    "year": str(paper.year) if paper.year else "",
                    "doi": paper.doi or "",
                    "query_source": query[:80],
                }
            )
    return papers


def extract_pairs(papers: list[dict], max_pairs: int) -> list[dict]:
    pairs: list[dict] = []
    seen_abstract: set[str] = set()
    counter = 0
    for paper in papers:
        if len(pairs) >= max_pairs:
            break
        pmid = str(paper["pmid"])
        if pmid in seen_abstract:
            continue
        abstract = paper["abstract"]
        found = False
        for pidx, pattern in enumerate(CONTRAST_PATTERNS):
            matches = re.findall(pattern, abstract, re.IGNORECASE)
            for match in matches:
                if len(match) != 2:
                    continue
                a_raw, b_raw = match[0].strip(), match[1].strip()
                if len(a_raw) < 25 or len(b_raw) < 25:
                    continue
                a = _clean_text(a_raw)
                b = _clean_text(b_raw)
                if len(a) < 20 or len(b) < 20:
                    continue
                if _norm(a) == _norm(b):
                    continue
                counter += 1
                pairs.append(
                    {
                        "pair_id": f"V3-MAGX-{counter:04d}",
                        "domain": "magnitude_expand",
                        "query_source": paper.get("query_source", ""),
                        "intended_type": "magnitude",
                        "extraction_pattern": str(pidx),
                        "claim_a": {
                            "text": a,
                            "source_pmid": pmid,
                            "source_doi": paper.get("doi", ""),
                            "paper_title": paper.get("title", "")[:160],
                            "year": paper.get("year", ""),
                        },
                        "claim_b": {
                            "text": b,
                            "source_pmid": pmid,
                            "source_doi": paper.get("doi", ""),
                            "paper_title": paper.get("title", "")[:160],
                            "year": paper.get("year", ""),
                        },
                    }
                )
                seen_abstract.add(pmid)
                found = True
                break
            if found:
                break
    return pairs


async def classify_pair(client: httpx.AsyncClient, api_key: str, pair: dict) -> dict | None:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": USER_TEMPLATE.format(
            claim_a=pair["claim_a"]["text"][:360],
            claim_b=pair["claim_b"]["text"][:360],
        )}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 512,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    try:
        resp = await client.post(url, json=payload, timeout=45.0)
        resp.raise_for_status()
        body = resp.json()
        candidates = body.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        text = parts[0].get("text", "")
        return _parse_response(text)
    except Exception:
        return None


async def classify_pairs_resume(
    pairs: list[dict],
    checkpoint_path: Path,
    api_key: str,
    sleep_sec: float,
    limit: int,
) -> list[dict]:
    done: dict[str, dict] = {}
    if checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            done[row["pair_id"]] = row

    remaining = [p for p in pairs if p["pair_id"] not in done][:limit]
    if not remaining:
        return list(done.values())

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("a", encoding="utf-8") as fp:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for idx, pair in enumerate(remaining, start=1):
                label = await classify_pair(client, api_key, pair)
                row = dict(pair)
                row["label"] = label
                row["parse_failed"] = label is None
                done[pair["pair_id"]] = row
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
                fp.flush()
                if idx % 10 == 0 or idx == len(remaining):
                    ok = sum(1 for r in done.values() if isinstance(r.get("label"), dict))
                    print(f"  {idx}/{len(remaining)} classified (ok={ok}, total={len(done)})")
                await asyncio.sleep(sleep_sec)
    return list(done.values())


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    papers_path = args.output_dir / "papers.jsonl"
    pairs_path = args.output_dir / "candidates_magnitude_expand.jsonl"
    checkpoint_path = args.output_dir / "checkpoint_classified.jsonl"
    selected_path = args.output_dir / "selected_magnitude_additions.jsonl"
    summary_path = args.output_dir / "summary.json"

    if args.reset and checkpoint_path.exists():
        checkpoint_path.unlink()

    papers = fetch_papers(TYPE_QUERIES, args.max_per_query)
    with papers_path.open("w", encoding="utf-8") as fp:
        for row in papers:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    pairs = extract_pairs(papers, args.max_pairs)
    with pairs_path.open("w", encoding="utf-8") as fp:
        for row in pairs:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.dry_run:
        summary = {
            "mode": "dry_run",
            "papers": len(papers),
            "pairs_extracted": len(pairs),
            "output_dir": str(args.output_dir),
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Dry run complete")
        print(f"  papers={len(papers)} pairs={len(pairs)}")
        print(f"  output_dir={args.output_dir}")
        return

    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")

    results = asyncio.run(
        classify_pairs_resume(
            pairs=pairs,
            checkpoint_path=checkpoint_path,
            api_key=api_key,
            sleep_sec=args.sleep,
            limit=args.limit_classify,
        )
    )

    selected = []
    for row in results:
        label = row.get("label")
        if not isinstance(label, dict):
            continue
        if (
            label.get("contradiction_type") == "magnitude"
            and label.get("is_genuine_contradiction")
            and float(label.get("confidence", 0.0)) >= args.confidence_threshold
        ):
            selected.append(row)

    with selected_path.open("w", encoding="utf-8") as fp:
        for row in selected:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    type_counts = Counter(
        row["label"]["contradiction_type"]
        for row in results
        if isinstance(row.get("label"), dict)
    )
    summary = {
        "papers": len(papers),
        "pairs_extracted": len(pairs),
        "classified_rows": len(results),
        "classified_type_counts": dict(type_counts),
        "selected_magnitude_additions": len(selected),
        "confidence_threshold": args.confidence_threshold,
        "output_dir": str(args.output_dir),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Magnitude expansion run complete")
    print(f"  papers={len(papers)} pairs={len(pairs)} classified={len(results)}")
    print(f"  selected_magnitude_additions={len(selected)}")
    print(f"  summary={summary_path}")


if __name__ == "__main__":
    main()
