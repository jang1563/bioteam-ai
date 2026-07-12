"""Preprint Delta API — compare versions of a bioRxiv/medRxiv preprint.

POST /api/v1/preprint-delta/compare
    Fetch all versions of a preprint by DOI, diff abstracts, classify changes.

GET  /api/v1/preprint-delta/batch
    Compare multiple DOIs at once (max 10).
"""

from __future__ import annotations

import logging

from app.engines.preprint_delta import PreprintDeltaDetector, PreprintDeltaResult
from app.llm.layer import LLMLayer
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/preprint-delta", tags=["preprint-delta"])

# ── LLM dependency ─────────────────────────────────────────────────────────────

_llm_layer: LLMLayer | None = None


def set_llm_layer(layer: LLMLayer) -> None:
    global _llm_layer
    _llm_layer = layer


def get_llm_layer() -> LLMLayer | None:
    """Return LLM layer if available; None = heuristic-only mode."""
    return _llm_layer


# ── Request / response models ─────────────────────────────────────────────────


class CompareRequest(BaseModel):
    doi: str = Field(min_length=5, max_length=200, description="bioRxiv DOI (e.g. 10.1101/2020.01.01.123456)")
    server: str = Field(default="biorxiv", pattern="^(biorxiv|medrxiv)$")


class BatchCompareRequest(BaseModel):
    dois: list[str] = Field(min_length=1, max_length=10, description="List of DOIs to compare")
    server: str = Field(default="biorxiv", pattern="^(biorxiv|medrxiv)$")


class BatchCompareResponse(BaseModel):
    total: int
    results: list[PreprintDeltaResult]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/compare", response_model=PreprintDeltaResult)
async def compare_preprint(
    req: CompareRequest,
    llm: LLMLayer | None = Depends(get_llm_layer),
) -> PreprintDeltaResult:
    """Compare v1 vs latest version of a bioRxiv/medRxiv preprint.

    - Fetches all posted versions for the given DOI.
    - Computes abstract diff (unified diff line count).
    - If multiple versions found with changes, uses Haiku to classify the delta.
    - LLM classification is optional; if unavailable, returns diff stats only.
    """
    detector = PreprintDeltaDetector(llm_layer=llm)
    result = await detector.analyze(doi=req.doi, server=req.server)

    if result.error and result.total_versions == 0:
        raise HTTPException(status_code=404, detail=result.error)

    return result


@router.post("/batch", response_model=BatchCompareResponse)
async def batch_compare(
    req: BatchCompareRequest,
    llm: LLMLayer | None = Depends(get_llm_layer),
) -> BatchCompareResponse:
    """Compare multiple DOIs in a single request.

    Processes DOIs sequentially to avoid overwhelming the bioRxiv API.
    Returns results for all DOIs, including errors per DOI (does not fail-fast).
    """
    detector = PreprintDeltaDetector(llm_layer=llm)
    results: list[PreprintDeltaResult] = []
    for doi in req.dois:
        result = await detector.analyze(doi=doi, server=req.server)
        results.append(result)

    return BatchCompareResponse(total=len(results), results=results)
