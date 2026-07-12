"""Benchmark scorers for W9 evaluation.

4-layer composable scorer:
1. GeneLevelScorer  — Jaccard, recall, precision, F1 (pure Python)
2. PathwayLevelScorer — Fuzzy term matching (pure Python)
3. DirectionLevelScorer — Up/down accuracy + Spearman correlation
4. BiologyLevelScorer — LLM-as-judge via Gemini (free, fallback=0.5)
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from app.benchmarks.models import BenchmarkDataset, BenchmarkResult
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# BioAgent Score composite weights (extractable for experimentation)
BIOAGENT_WEIGHTS: dict[str, float] = {
    "gene_recall": 0.30,
    "pathway_overlap": 0.20,
    "direction_accuracy": 0.20,
    "biology_score": 0.15,
    "gene_precision": 0.10,
    "fc_correlation": 0.05,
}

# Fair mode weights: equal precision/recall, no LLM-as-judge (biology_score).
# Used when fair=True to avoid ground-truth leakage in benchmark comparisons.
FAIR_WEIGHTS: dict[str, float] = {
    "gene_recall": 0.25,
    "pathway_overlap": 0.20,
    "direction_accuracy": 0.20,
    "gene_precision": 0.25,
    "fc_correlation": 0.10,
}

# KEGG pathway names often include species suffix: "Phagosome Homo sapiens hsa04145"
_KEGG_SPECIES_SUFFIX = re.compile(
    r"\s+(?:homo sapiens|mus musculus|rattus norvegicus|"
    r"drosophila melanogaster|caenorhabditis elegans|"
    r"saccharomyces cerevisiae|danio rerio)\s+[a-z]{2,4}\d+$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 1. Gene Level
# ---------------------------------------------------------------------------


class GeneLevelScorer:
    """Set-based gene overlap metrics."""

    @staticmethod
    def score(predicted: list[str], expected: list[str]) -> dict[str, float]:
        pred_set = {g.upper() for g in predicted}
        exp_set = {g.upper() for g in expected}

        if not exp_set:
            return {"gene_recall": 0.0, "gene_precision": 0.0, "gene_f1": 0.0, "gene_jaccard": 0.0}

        tp = len(pred_set & exp_set)
        recall = tp / len(exp_set) if exp_set else 0.0
        precision = tp / len(pred_set) if pred_set else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        union = len(pred_set | exp_set)
        jaccard = tp / union if union > 0 else 0.0

        return {"gene_recall": recall, "gene_precision": precision, "gene_f1": f1, "gene_jaccard": jaccard}


# ---------------------------------------------------------------------------
# 2. Pathway Level
# ---------------------------------------------------------------------------


class PathwayLevelScorer:
    """Pathway overlap via normalized string matching."""

    @staticmethod
    def _normalize_pathway(name: str) -> str:
        """Lowercase, strip KEGG species suffixes and common suffixes for fuzzy matching."""
        n = name.lower().strip()
        # Strip KEGG species+ID suffix: "phagosome homo sapiens hsa04145" → "phagosome"
        n = _KEGG_SPECIES_SUFFIX.sub("", n)
        for suffix in (" pathway", " signaling pathway", " signaling", " cascade"):
            if n.endswith(suffix):
                n = n[: -len(suffix)]
        return n

    @staticmethod
    def score(predicted: list[str], expected: list[str]) -> dict[str, float]:
        if not expected:
            return {"pathway_overlap": 0.0}

        pred_norm = [PathwayLevelScorer._normalize_pathway(p) for p in predicted]
        exp_norm = [PathwayLevelScorer._normalize_pathway(p) for p in expected]

        matched = 0
        for exp in exp_norm:
            # 1. Exact match
            if exp in pred_norm:
                matched += 1
                continue
            # 2. Substring containment
            if any(exp in p or p in exp for p in pred_norm):
                matched += 1
                continue
            # 3. Fuzzy match: SequenceMatcher ratio >= 0.70
            if any(SequenceMatcher(None, exp, p).ratio() >= 0.70 for p in pred_norm):
                matched += 1

        overlap = matched / len(exp_norm) if exp_norm else 0.0
        return {"pathway_overlap": overlap}


# ---------------------------------------------------------------------------
# 3. Direction Level
# ---------------------------------------------------------------------------


class DirectionLevelScorer:
    """DEG direction accuracy + fold-change correlation."""

    @staticmethod
    def score(
        predicted_directions: dict[str, str],
        expected_directions: dict[str, str],
        predicted_fcs: dict[str, float] | None = None,
        expected_fcs: dict[str, float] | None = None,
    ) -> dict[str, float]:
        result: dict[str, float] = {"direction_accuracy": 0.0, "fc_correlation": 0.0}

        if not expected_directions:
            return result

        # Direction accuracy on overlapping genes
        common_genes = set(predicted_directions.keys()) & set(expected_directions.keys())
        if common_genes:
            correct = sum(
                1 for g in common_genes
                if predicted_directions.get(g, "").lower() == expected_directions.get(g, "").lower()
            )
            result["direction_accuracy"] = correct / len(common_genes)

        # Spearman correlation on fold changes
        if predicted_fcs and expected_fcs:
            common_fc_genes = sorted(set(predicted_fcs.keys()) & set(expected_fcs.keys()))
            if len(common_fc_genes) >= 3:
                try:
                    from scipy.stats import spearmanr
                    pred_vals = [predicted_fcs[g] for g in common_fc_genes]
                    exp_vals = [expected_fcs[g] for g in common_fc_genes]
                    rho, _ = spearmanr(pred_vals, exp_vals)
                    # Clamp to [0, 1]: anti-correlated predictions score 0, not negative
                    rho_val = float(rho) if rho == rho else 0.0  # NaN check
                    result["fc_correlation"] = max(0.0, rho_val)
                except ImportError:
                    logger.warning("scipy not available — skipping FC correlation")
                    result["fc_correlation"] = 0.0

        return result


# ---------------------------------------------------------------------------
# 4. Biology Level (LLM-as-judge)
# ---------------------------------------------------------------------------


class _BiologyJudgeResult(BaseModel):
    """LLM-as-judge response model."""
    score: float = Field(0.5, ge=0.0, le=1.0, description="Biological plausibility score 0-1")
    reasoning: str = Field("", description="Brief explanation of the score")


class BiologyLevelScorer:
    """LLM-as-judge using Gemini 2.5 Flash (free tier).

    Falls back to score=0.5 if Gemini unavailable.
    """

    JUDGE_PROMPT = (
        "You are a bioinformatics expert evaluating an AI system's gene/pathway predictions.\n\n"
        "Research question: {query}\n\n"
        "Expected key genes: {expected_genes}\n"
        "Predicted genes: {predicted_genes}\n\n"
        "Expected pathways: {expected_pathways}\n"
        "Predicted pathways: {predicted_pathways}\n\n"
        "Score the predictions on a 0.0-1.0 scale using THESE criteria:\n"
        "- 0.9-1.0: Predicted set captures core biology; false positives are mechanistically related\n"
        "- 0.7-0.8: Most predictions relevant but missing key genes OR including unrelated ones\n"
        "- 0.4-0.6: Mix of relevant and irrelevant predictions\n"
        "- 0.0-0.3: Mostly irrelevant predictions that miss the core biology\n\n"
        "Consider: Are predicted genes mechanistically connected to expected ones? "
        "Are false positives at least in the same pathway family? "
        "Penalize predictions that are generic (e.g., TP53 for everything) rather than specific."
    )

    @staticmethod
    def _sanitize(name: str, max_len: int = 80) -> str:
        """Strip non-alphanumeric chars (except hyphens/spaces) to prevent prompt injection."""
        clean = re.sub(r"[^\w\s\-/(),.]", "", str(name))
        return clean[:max_len]

    async def score(
        self,
        query: str,
        predicted_genes: list[str],
        predicted_pathways: list[str],
        dataset: BenchmarkDataset,
    ) -> dict[str, Any]:
        try:
            from app.llm.gemini_layer import GeminiLayer
            gemini = GeminiLayer()

            san = self._sanitize
            prompt = self.JUDGE_PROMPT.format(
                query=san(query, 200),
                expected_genes=", ".join(san(g) for g in dataset.expected_genes[:30]),
                predicted_genes=", ".join(san(g) for g in predicted_genes[:30]),
                expected_pathways=", ".join(san(p) for p in dataset.expected_pathways[:15]),
                predicted_pathways=", ".join(san(p) for p in predicted_pathways[:15]),
            )

            result, _meta = await gemini.complete_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=_BiologyJudgeResult,
                system="You are a biology expert scorer.",
            )

            bio_score = max(0.0, min(1.0, result.score))

            return {
                "biology_score": bio_score,
                "reasoning": result.reasoning,
                "is_fallback": False,
            }

        except Exception as e:
            logger.warning("BiologyLevelScorer: Gemini unavailable (%s), returning neutral score", e)
            return {
                "biology_score": 0.5,
                "reasoning": f"Gemini unavailable ({type(e).__name__}), neutral score",
                "is_fallback": True,
            }


# ---------------------------------------------------------------------------
# Composite Scorer
# ---------------------------------------------------------------------------


class W9BenchmarkScorer:
    """Composite scorer combining all 4 levels.

    BioAgent Score formula:
        0.30 × gene_recall
      + 0.20 × pathway_overlap
      + 0.20 × direction_accuracy
      + 0.15 × biology_score
      + 0.10 × gene_precision
      + 0.05 × fc_correlation
    """

    def __init__(self) -> None:
        self.gene_scorer = GeneLevelScorer()
        self.pathway_scorer = PathwayLevelScorer()
        self.direction_scorer = DirectionLevelScorer()
        self.biology_scorer = BiologyLevelScorer()

    async def score(
        self,
        predicted_genes: list[str],
        predicted_pathways: list[str],
        predicted_directions: dict[str, str],
        predicted_fcs: dict[str, float],
        dataset: BenchmarkDataset,
        query: str = "",
        run_id: str = "",
        template: str = "multi_omics",
        cost_mode: str = "standard",
        total_cost: float = 0.0,
        runtime_seconds: float = 0.0,
        fair: bool = False,
    ) -> BenchmarkResult:
        # Individual scores
        gene_scores = self.gene_scorer.score(predicted_genes, dataset.expected_genes)
        pathway_scores = self.pathway_scorer.score(predicted_pathways, dataset.expected_pathways)
        direction_scores = self.direction_scorer.score(
            predicted_directions, dataset.expected_directions,
            predicted_fcs, dataset.expected_fold_changes,
        )
        biology_result = await self.biology_scorer.score(
            query or dataset.query, predicted_genes, predicted_pathways, dataset,
        )

        # Composite BioAgent Score (weights from module constant, renormalized
        # when ground truth is unavailable — same pattern as RCMXT X=NULL)
        metrics = {
            "gene_recall": gene_scores["gene_recall"],
            "pathway_overlap": pathway_scores["pathway_overlap"],
            "direction_accuracy": direction_scores["direction_accuracy"],
            "biology_score": biology_result["biology_score"],
            "gene_precision": gene_scores["gene_precision"],
            "fc_correlation": direction_scores["fc_correlation"],
        }

        base_weights = FAIR_WEIGHTS if fair else BIOAGENT_WEIGHTS
        active_weights = dict(base_weights)
        if not dataset.expected_directions:
            active_weights.pop("direction_accuracy", None)
        if not dataset.expected_fold_changes:
            active_weights.pop("fc_correlation", None)

        total_w = sum(active_weights.values())
        bioagent_score = sum(
            (active_weights[k] / total_w) * metrics[k]
            for k in active_weights
        )
        # Clamp to [0, 1]
        bioagent_score = max(0.0, min(1.0, bioagent_score))

        return BenchmarkResult(
            dataset_id=dataset.id,
            run_id=run_id,
            template=template,
            cost_mode=cost_mode,
            gene_recall=gene_scores["gene_recall"],
            gene_precision=gene_scores["gene_precision"],
            gene_f1=gene_scores["gene_f1"],
            gene_jaccard=gene_scores["gene_jaccard"],
            pathway_overlap=pathway_scores["pathway_overlap"],
            direction_accuracy=direction_scores["direction_accuracy"],
            fc_correlation=direction_scores["fc_correlation"],
            biology_score=biology_result["biology_score"],
            bioagent_score=bioagent_score,
            predicted_genes=predicted_genes,
            predicted_pathways=predicted_pathways,
            predicted_directions=predicted_directions,
            predicted_fold_changes=predicted_fcs,
            total_cost_usd=total_cost,
            runtime_seconds=runtime_seconds,
            is_biology_fallback=biology_result.get("is_fallback", False),
            fair_mode=fair,
        )
