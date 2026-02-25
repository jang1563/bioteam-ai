"""Benchmark: LAB-Bench LitQA2 — literature search retrieval evaluation.

Tests whether our PubMed and Semantic Scholar search pipelines can find
the ground-truth paper for LitQA2 questions. Each question has a known
DOI; we check if that DOI appears in search results.

Metrics:
- Recall@K: fraction of questions where the target DOI was found in top K results
- MRR: Mean Reciprocal Rank (1/rank of target DOI, or 0 if not found)

NOTE: This benchmark makes REAL API calls to PubMed and Semantic Scholar.
Set NCBI_EMAIL env var for PubMed. S2_API_KEY is optional.
ANTHROPIC_API_KEY required for LLM-enhanced strategies.

Usage:
    # Run quick sample (20 questions, PubMed only)
    NCBI_EMAIL=you@example.com pytest backend/tests/benchmarks/test_benchmark_litqa2.py -v -s -k sample

    # Run full benchmark (199 questions, ~10 min)
    NCBI_EMAIL=you@example.com pytest backend/tests/benchmarks/test_benchmark_litqa2.py -v -s -k full

    # Run multi-strategy comparison (10 questions, requires ANTHROPIC_API_KEY)
    NCBI_EMAIL=you@example.com pytest backend/tests/benchmarks/test_benchmark_litqa2.py -v -s -k strategy

Empirical results (2025-02-25, 10-question sample):
    Strategy A (raw question as query):       Recall@20 =  0%
    Strategy B (keyword extraction):          Recall@20 =  0%
    Strategy C (entity extraction):           Recall@20 = 10%
    Strategy F (LLM single-query):            Recall@20 = 10%
    Strategy G (LLM multi-query, 3 queries):  Recall@20 = 20%  ← best
    Strategy D (DOI direct lookup, ceiling):  Recall@20 = 90%

    Root cause: PubMed is keyword-based, not semantic. Complex biology
    questions don't translate to effective search terms without LLM
    query reformulation AND multi-source aggregation.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

# Ensure backend is importable
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

# ── Data loading ──

CACHE_DIR = Path(__file__).parent / ".litqa2_cache"


def _load_litqa2() -> list[dict]:
    """Load LitQA2 questions from HuggingFace (cached locally)."""
    cache_file = CACHE_DIR / "litqa2_questions.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text())

    from datasets import load_dataset
    ds = load_dataset("futurehouse/lab-bench", "LitQA2")
    rows = []
    for r in ds["train"]:
        doi = ""
        if r.get("sources"):
            for s in r["sources"]:
                if "doi.org/" in s:
                    doi = s.split("doi.org/")[-1].rstrip("/")
                    break
        rows.append({
            "id": r["id"],
            "question": r["question"],
            "ideal": r["ideal"],
            "doi": doi,
            "key_passage": r.get("key-passage", ""),
        })

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    return rows


def _normalize_doi(doi: str) -> str:
    """Normalize DOI for comparison (lowercase, strip URL prefix)."""
    doi = doi.lower().strip()
    if "doi.org/" in doi:
        doi = doi.split("doi.org/")[-1]
    return doi.rstrip("/")


# ── Search wrappers ──


def _search_pubmed(query: str, max_results: int = 20) -> list[dict]:
    """Search PubMed and return list of {title, doi, pmid}."""
    try:
        from app.integrations.pubmed import PubMedClient
        client = PubMedClient()
        papers = client.search(query, max_results=max_results)
        return [
            {
                "title": p.title,
                "doi": _normalize_doi(p.doi) if p.doi else "",
                "pmid": p.pmid,
                "source": "pubmed",
            }
            for p in papers
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _search_semantic_scholar(query: str, limit: int = 10) -> list[dict]:
    """Search Semantic Scholar and return list of {title, doi, paper_id}."""
    try:
        from app.integrations.semantic_scholar import SemanticScholarClient
        client = SemanticScholarClient(timeout=8)
        papers = client.search(query, limit=limit)
        return [
            {
                "title": p.title,
                "doi": _normalize_doi(p.doi) if p.doi else "",
                "paper_id": p.paper_id,
                "source": "semantic_scholar",
            }
            for p in papers
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _find_doi_rank(results: list[dict], target_doi: str) -> int | None:
    """Find the rank (1-indexed) of target DOI in results, or None if not found."""
    target = _normalize_doi(target_doi)
    if not target:
        return None
    for i, r in enumerate(results):
        if r.get("doi") and _normalize_doi(r["doi"]) == target:
            return i + 1
    return None


def _is_s2_available() -> bool:
    """Quick probe: can Semantic Scholar respond within 10s?"""
    try:
        results = _search_semantic_scholar("CRISPR", limit=1)
        return len(results) > 0 and "error" not in results[0]
    except Exception:
        return False


# ── Query strategies ──

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "of", "in", "to", "and",
    "or", "at", "by", "for", "with", "on", "has", "have", "been", "which",
    "what", "how", "does", "do", "did", "that", "this", "from", "its",
    "their", "about", "than", "into", "both", "also", "but", "not", "only",
    "showed", "compared", "show", "using", "used", "between", "while",
    "more", "figure", "data", "results", "found", "we", "they", "these",
    "those", "test", "each", "further", "such", "can", "may", "would",
    "should", "could", "however", "thus", "therefore", "significantly",
    "whereas", "being", "if", "when", "then", "upon", "after", "before",
    "during", "approximately", "based", "among",
})

_SKIP_FIRST_WORDS = frozenset({
    "Among", "Approximately", "Active", "Are", "Based", "What", "Which",
    "How", "Does", "The", "This", "That", "These", "Those", "For", "From",
    "During", "After", "Before", "Between", "According", "Given",
})


def strategy_raw(question: str) -> list[str]:
    """Strategy A: raw question truncated to 40 words."""
    words = question.split()[:40]
    return [" ".join(words)]


def strategy_keywords(question: str) -> list[str]:
    """Strategy B: stopword removal, top 10 terms."""
    words = question.split()
    kw = [
        w.strip(".,;:?!()[]")
        for w in words
        if w.lower().strip(".,;:?!()[]") not in _STOP_WORDS and len(w) > 2
    ][:10]
    return [" ".join(kw)] if kw else strategy_raw(question)


def strategy_entities(question: str) -> list[str]:
    """Strategy C: extract biological entities (capitalized terms, gene names)."""
    entities = []
    for w in question.split():
        clean = w.strip(".,;:?!()[]")
        if not clean or len(clean) < 2:
            continue
        if clean[0].isupper() and len(clean) > 2 and clean not in _SKIP_FIRST_WORDS:
            entities.append(clean)
        elif re.match(r"[A-Z][a-z]*\d|[A-Z]{2,}\d|[a-z]+-\d", clean):
            entities.append(clean)
    return [" ".join(entities[:8])] if entities else strategy_keywords(question)


def strategy_llm_single(question: str) -> list[str]:
    """Strategy F: LLM reformulates question into single PubMed query."""
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": (
                "Convert this biology research question into an effective "
                "PubMed search query. Return ONLY the search terms, no "
                f"explanation:\n\n{question}"
            ),
        }],
    )
    return [resp.content[0].text.strip()]


def strategy_llm_multi(question: str) -> list[str]:
    """Strategy G: LLM generates 3 diverse PubMed queries."""
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                "Generate 3 different PubMed search queries for this biology "
                "question. Each should use a different strategy:\n"
                "1. Specific: key biological terms and gene/protein names\n"
                "2. Broad: general topic and organism\n"
                "3. MeSH-style: formal biomedical vocabulary\n\n"
                "Return ONLY 3 lines, one query per line, no numbering.\n\n"
                f"Question: {question}"
            ),
        }],
    )
    lines = [ln.strip() for ln in resp.content[0].text.strip().split("\n") if ln.strip()]
    return lines[:3]


# ── Benchmark runner ──


class LitQA2BenchmarkResult:
    """Aggregate results from a LitQA2 benchmark run."""

    def __init__(self):
        self.results: list[dict] = []

    def add(self, question_id: str, question: str, target_doi: str,
            pubmed_rank: int | None, s2_rank: int | None,
            combined_rank: int | None, pubmed_count: int, s2_count: int):
        self.results.append({
            "id": question_id,
            "question": question[:80],
            "target_doi": target_doi,
            "pubmed_rank": pubmed_rank,
            "s2_rank": s2_rank,
            "combined_rank": combined_rank,
            "pubmed_results": pubmed_count,
            "s2_results": s2_count,
        })

    def recall_at_k(self, k: int, source: str = "combined") -> float:
        """Fraction of questions where target DOI was found in top K."""
        rank_key = f"{source}_rank"
        found = sum(1 for r in self.results
                    if r.get(rank_key) is not None and r[rank_key] <= k)
        return found / len(self.results) if self.results else 0

    def mrr(self, source: str = "combined") -> float:
        """Mean Reciprocal Rank."""
        rank_key = f"{source}_rank"
        rr_sum = 0.0
        for r in self.results:
            rank = r.get(rank_key)
            if rank is not None:
                rr_sum += 1.0 / rank
        return rr_sum / len(self.results) if self.results else 0

    def summary(self) -> str:
        """Human-readable summary."""
        n = len(self.results)
        lines = [f"\n{'='*60}", f"LitQA2 Benchmark Results ({n} questions)", f"{'='*60}"]

        for source in ["pubmed", "s2", "combined"]:
            label = {"pubmed": "PubMed", "s2": "Semantic Scholar", "combined": "Combined"}[source]
            lines.append(f"\n--- {label} ---")
            for k in [1, 5, 10, 20]:
                r = self.recall_at_k(k, source)
                lines.append(f"  Recall@{k:2d}: {r:.3f} ({int(r*n)}/{n})")
            lines.append(f"  MRR:       {self.mrr(source):.3f}")

        missed = [r for r in self.results if r["combined_rank"] is None]
        if missed:
            lines.append(f"\nMissed ({len(missed)}/{n}):")
            for r in missed[:10]:
                lines.append(f"  DOI: {r['target_doi']}")
                lines.append(f"  Q:   {r['question']}")

        return "\n".join(lines)


def _run_benchmark(
    questions: list[dict],
    rate_delay: float = 0.5,
    skip_s2: bool = False,
) -> LitQA2BenchmarkResult:
    """Run the baseline benchmark (raw question as query)."""
    result = LitQA2BenchmarkResult()

    for i, q in enumerate(questions):
        if not q["doi"]:
            continue

        query = " ".join(q["question"].split()[:40])
        target_doi = q["doi"]

        pm_results = _search_pubmed(query, max_results=20)
        time.sleep(rate_delay)

        if skip_s2:
            s2_results = []
        else:
            s2_results = _search_semantic_scholar(query, limit=10)
            time.sleep(rate_delay / 2)

        pm_rank = _find_doi_rank(pm_results, target_doi)
        s2_rank = _find_doi_rank(s2_results, target_doi)

        combined = []
        seen_dois = set()
        for r in pm_results + s2_results:
            doi = r.get("doi", "")
            if doi and doi not in seen_dois:
                seen_dois.add(doi)
                combined.append(r)
            elif not doi:
                combined.append(r)
        combined_rank = _find_doi_rank(combined, target_doi)

        pm_count = len([r for r in pm_results if "error" not in r])
        s2_count = len([r for r in s2_results if "error" not in r])

        result.add(
            question_id=q["id"], question=q["question"],
            target_doi=target_doi, pubmed_rank=pm_rank,
            s2_rank=s2_rank, combined_rank=combined_rank,
            pubmed_count=pm_count, s2_count=s2_count,
        )

        if (i + 1) % 5 == 0:
            found = sum(1 for r in result.results if r["combined_rank"] is not None)
            print(f"  [{i+1}/{len(questions)}] Found: {found}/{len(result.results)}")

    return result


def _run_strategy_benchmark(
    questions: list[dict],
    strategy_fn,
    strategy_name: str,
    rate_delay: float = 0.4,
) -> dict:
    """Run a single-strategy benchmark returning {recall@K, MRR, details}."""
    details = []
    for i, q in enumerate(questions):
        if not q["doi"]:
            continue
        target = q["doi"]
        queries = strategy_fn(q["question"])

        # Merge results from all generated queries
        all_results = []
        seen_dois = set()
        for qstr in queries:
            papers = _search_pubmed(qstr, max_results=10)
            for p in papers:
                d = p.get("doi", "")
                if d and d not in seen_dois:
                    seen_dois.add(d)
                    all_results.append(p)
                elif not d:
                    all_results.append(p)
            time.sleep(rate_delay)

        rank = _find_doi_rank(all_results, target)
        details.append({
            "id": q["id"], "target_doi": target,
            "rank": rank, "n_results": len(all_results),
            "queries": queries,
        })

    n = len(details)
    recall_at = {}
    for k in [1, 5, 10, 20]:
        found = sum(1 for d in details if d["rank"] is not None and d["rank"] <= k)
        recall_at[k] = found / n if n else 0

    rr_sum = sum(1.0 / d["rank"] for d in details if d["rank"] is not None)
    mrr = rr_sum / n if n else 0

    return {
        "strategy": strategy_name,
        "n_questions": n,
        "recall_at": recall_at,
        "mrr": mrr,
        "details": details,
    }


# ── Tests ──


class TestLitQA2Sample:
    """Quick sample benchmark — 20 questions (raw query baseline)."""

    @pytest.mark.skipif(
        not os.environ.get("NCBI_EMAIL"),
        reason="NCBI_EMAIL not set — skipping live API benchmark",
    )
    def test_sample_20(self):
        """Run baseline benchmark on 20 questions."""
        questions = _load_litqa2()
        sample = [q for q in questions if q["doi"]][:20]

        s2_up = _is_s2_available()
        if not s2_up:
            print("\nSemantic Scholar API unavailable — running PubMed only")

        print(f"\nRunning LitQA2 sample benchmark ({len(sample)} questions)...")
        result = _run_benchmark(sample, rate_delay=0.4, skip_s2=not s2_up)
        print(result.summary())

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / "sample_results.json").write_text(
            json.dumps(result.results, indent=2),
        )

        source = "combined" if s2_up else "pubmed"
        recall_10 = result.recall_at_k(10, source)
        print(f"\nRecall@10 ({source}) = {recall_10:.3f}")
        assert recall_10 >= 0.0  # Exploratory — no hard threshold


class TestLitQA2Full:
    """Full benchmark — all 199 questions."""

    @pytest.mark.skipif(
        not os.environ.get("NCBI_EMAIL"),
        reason="NCBI_EMAIL not set — skipping live API benchmark",
    )
    def test_full_benchmark(self):
        """Run baseline benchmark on all 199 questions."""
        questions = _load_litqa2()
        valid = [q for q in questions if q["doi"]]

        s2_up = _is_s2_available()
        if not s2_up:
            print("\nSemantic Scholar API unavailable — running PubMed only")

        print(f"\nRunning LitQA2 full benchmark ({len(valid)} questions)...")
        result = _run_benchmark(valid, rate_delay=0.5, skip_s2=not s2_up)
        print(result.summary())

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / "full_results.json").write_text(
            json.dumps(result.results, indent=2),
        )


class TestLitQA2StrategyComparison:
    """Compare query reformulation strategies on a 10-question sample.

    Requires NCBI_EMAIL + ANTHROPIC_API_KEY for LLM strategies.
    """

    @pytest.mark.skipif(
        not os.environ.get("NCBI_EMAIL"),
        reason="NCBI_EMAIL not set",
    )
    def test_compare_strategies(self):
        """Run all strategies and compare Recall@K."""
        questions = _load_litqa2()
        sample = [q for q in questions if q["doi"]][:10]

        has_llm = os.environ.get("ANTHROPIC_API_KEY", "test") != "test"

        strategies = [
            (strategy_raw, "A: Raw question"),
            (strategy_keywords, "B: Keywords"),
            (strategy_entities, "C: Entities"),
        ]
        if has_llm:
            strategies.extend([
                (strategy_llm_single, "F: LLM single"),
                (strategy_llm_multi, "G: LLM multi-query"),
            ])

        all_results = []
        for fn, name in strategies:
            print(f"\n--- Running {name} ---")
            result = _run_strategy_benchmark(sample, fn, name, rate_delay=0.35)
            all_results.append(result)

            found = sum(1 for d in result["details"] if d["rank"] is not None)
            print(f"  Found: {found}/{result['n_questions']}")
            for k in [1, 5, 10, 20]:
                print(f"  Recall@{k:2d}: {result['recall_at'][k]:.1%}")
            print(f"  MRR:       {result['mrr']:.3f}")

        # DOI ceiling check (direct DOI lookup in PubMed)
        print("\n--- D: DOI direct lookup (ceiling) ---")
        doi_found = 0
        for q in sample:
            papers = _search_pubmed(f"{q['doi']}[DOI]", max_results=5)
            if any(_normalize_doi(p.get("doi", "")) == _normalize_doi(q["doi"])
                   for p in papers if p.get("doi")):
                doi_found += 1
            time.sleep(0.3)
        print(f"  In PubMed: {doi_found}/{len(sample)} ({doi_found/len(sample):.0%})")

        # Summary table
        print(f"\n{'='*60}")
        print(f"{'Strategy':<25} {'R@1':>5} {'R@5':>5} {'R@10':>5} {'R@20':>5} {'MRR':>6}")
        print(f"{'-'*60}")
        for r in all_results:
            print(
                f"{r['strategy']:<25} "
                f"{r['recall_at'][1]:>5.0%} "
                f"{r['recall_at'][5]:>5.0%} "
                f"{r['recall_at'][10]:>5.0%} "
                f"{r['recall_at'][20]:>5.0%} "
                f"{r['mrr']:>6.3f}"
            )
        print(f"{'D: DOI ceiling':<25} {'—':>5} {'—':>5} {'—':>5} {doi_found/len(sample):>5.0%} {'—':>6}")
        print(f"{'='*60}")

        # Save
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / "strategy_comparison.json").write_text(
            json.dumps(all_results, indent=2, default=str),
        )


class TestLitQA2DataIntegrity:
    """Verify the LitQA2 dataset loaded correctly (no API calls)."""

    def test_dataset_loads(self):
        """LitQA2 dataset should load with 199 questions."""
        questions = _load_litqa2()
        assert len(questions) == 199

    def test_all_have_dois(self):
        """All (or nearly all) questions should have ground-truth DOIs."""
        questions = _load_litqa2()
        with_doi = [q for q in questions if q["doi"]]
        assert len(with_doi) >= 190

    def test_doi_format(self):
        """DOIs should be properly formatted (10.xxxx/yyyy)."""
        questions = _load_litqa2()
        for q in questions:
            if q["doi"]:
                assert q["doi"].startswith("10."), f"Bad DOI format: {q['doi']}"

    def test_questions_non_empty(self):
        """Questions should be non-empty strings."""
        questions = _load_litqa2()
        for q in questions:
            assert len(q["question"]) > 10, f"Question too short: {q['question']}"
