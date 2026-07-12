"""Shadow Miner API — trigger automated negative-result mining from PubMed.

POST /api/v1/shadow-miner/run
    Mine PubMed for negative results matching a topic query.
    Stores confirmed negatives directly in the Lab KB.
"""

from __future__ import annotations

from app.db.database import get_session
from app.engines.negative_results.shadow_miner import MineRunResult, ShadowMiner
from app.llm.layer import LLMLayer
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

router = APIRouter(prefix="/api/v1/shadow-miner", tags=["shadow-miner"])

# Injected at startup by main.py
_llm_layer: LLMLayer | None = None


def set_llm_layer(layer: LLMLayer) -> None:
    """Set the LLM layer dependency (called at application startup)."""
    global _llm_layer
    _llm_layer = layer


def get_llm_layer() -> LLMLayer:
    if _llm_layer is None:
        raise HTTPException(status_code=503, detail="LLM layer not available")
    return _llm_layer


# ── Request / response models ──────────────────────────────────────────────────


class MineRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500, description="Research topic to mine")
    max_papers: int = Field(default=10, ge=1, le=50, description="Max PubMed papers to fetch")
    min_confidence: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Min LLM confidence to store a result"
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/run", response_model=MineRunResult)
async def run_shadow_miner(
    req: MineRequest,
    session: Session = Depends(get_session),
    llm: LLMLayer = Depends(get_llm_layer),
) -> MineRunResult:
    """Mine PubMed for negative results matching a topic and store them in the Lab KB.

    This endpoint is synchronous from the caller's perspective — it blocks until
    all papers are classified. Keep `max_papers` ≤ 20 for reasonable response times.
    """
    miner = ShadowMiner(llm_layer=llm, session=session)
    return await miner.run(
        topic=req.query,
        max_papers=req.max_papers,
        min_confidence=req.min_confidence,
    )
