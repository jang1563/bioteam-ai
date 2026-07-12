"""Semantic Memory API — search and inspect ChromaDB collections.

GET  /api/v1/memory/search  — semantic similarity search
GET  /api/v1/memory/stats   — document counts per collection
"""

from __future__ import annotations

from app.memory.semantic import COLLECTION_NAMES, SemanticMemory
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])

_memory: SemanticMemory | None = None


def set_dependencies(memory: SemanticMemory) -> None:
    global _memory
    _memory = memory


def _get_memory() -> SemanticMemory:
    if _memory is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    return _memory


# === Response models ===


class MemorySearchResult(BaseModel):
    id: str
    text: str
    collection: str
    similarity: float          # 1 - distance (cosine)
    metadata: dict


class MemorySearchResponse(BaseModel):
    query: str
    collection: str
    results: list[MemorySearchResult]
    total: int


class CollectionStats(BaseModel):
    name: str
    count: int


class MemoryStatsResponse(BaseModel):
    collections: list[CollectionStats]
    total_documents: int


# === Endpoints ===


@router.get("/stats", response_model=MemoryStatsResponse)
def get_memory_stats() -> MemoryStatsResponse:
    """Return document counts for all ChromaDB collections."""
    mem = _get_memory()
    stats = []
    total = 0
    for name in COLLECTION_NAMES:
        try:
            n = mem.count(name)
        except Exception:
            n = 0
        stats.append(CollectionStats(name=name, count=n))
        total += n
    return MemoryStatsResponse(collections=stats, total_documents=total)


@router.get("/search", response_model=MemorySearchResponse)
def search_memory(
    q: str = Query(..., min_length=2, max_length=500, description="Search query"),
    collection: str = Query(
        default="all",
        description="Collection to search: literature | synthesis | lab_kb | all",
    ),
    n: int = Query(default=8, ge=1, le=50, description="Max results"),
) -> MemorySearchResponse:
    """Semantic similarity search across ChromaDB collections."""
    mem = _get_memory()

    valid = set(COLLECTION_NAMES) | {"all"}
    if collection not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid collection '{collection}'. Must be one of: {sorted(valid)}",
        )

    try:
        if collection == "all":
            raw = mem.search_all(q, n_results=n)
        else:
            raw = mem.search(collection, q, n_results=n)
            for r in raw:
                r["collection"] = collection
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}") from e

    results = [
        MemorySearchResult(
            id=r["id"],
            text=r.get("text", ""),
            collection=r.get("collection", collection),
            similarity=round(max(0.0, 1.0 - float(r.get("distance", 1.0))), 4),
            metadata=r.get("metadata", {}),
        )
        for r in raw
    ]

    return MemorySearchResponse(
        query=q,
        collection=collection,
        results=results,
        total=len(results),
    )
