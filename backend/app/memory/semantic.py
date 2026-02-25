"""Semantic Memory — ChromaDB vector store with 3 provenance-separated collections.

Design decision (Day 0): ChromaDB runs in embedded mode inside the backend process.
No separate Docker service needed for Phase 1-3. Data persists to disk at ./data/chroma/.

Collections:
- literature: Published papers, preprints (source of truth for RCMXT R-axis)
- synthesis: Agent-generated interpretations (excluded from replication counts)
- lab_kb: Manually entered lab knowledge (human-verified)
"""

from __future__ import annotations

import os
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", "data/chroma"))
COLLECTION_NAMES = ["literature", "synthesis", "lab_kb"]


class SemanticMemory:
    """Manages ChromaDB vector store with provenance-separated collections."""

    def __init__(self, persist_dir: str | Path | None = None) -> None:
        persist_path = str(persist_dir or CHROMA_DIR)
        os.makedirs(persist_path, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Initialize collections
        self.collections: dict[str, chromadb.Collection] = {}
        for name in COLLECTION_NAMES:
            self.collections[name] = self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )

    def add(
        self,
        collection: str,
        doc_id: str,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """Add a document to a collection with DOI/PMID deduplication."""
        coll = self.collections[collection]
        # Check for existing by ID (DOI/PMID-based)
        existing = coll.get(ids=[doc_id])
        if existing["ids"]:
            return  # Already exists, skip (dedup)
        add_kwargs: dict = {"ids": [doc_id], "documents": [text]}
        if metadata:
            add_kwargs["metadatas"] = [metadata]
        coll.add(**add_kwargs)

    def search(
        self,
        collection: str,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[dict]:
        """Search a collection by semantic similarity."""
        coll = self.collections[collection]
        kwargs = {"query_texts": [query], "n_results": n_results}
        if where:
            kwargs["where"] = where
        results = coll.query(**kwargs)

        # Flatten results into list of dicts
        items = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                items.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })
        return items

    def count(self, collection: str) -> int:
        """Count documents in a collection."""
        return self.collections[collection].count()

    def delete(self, collection: str, doc_id: str) -> None:
        """Delete a document by ID."""
        self.collections[collection].delete(ids=[doc_id])

    def search_literature(
        self,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[dict]:
        """Convenience method: search only primary literature + preprints.

        v4.2: Restricts to 'literature' collection to prevent
        agent-generated synthesis from contaminating evidence retrieval.
        Use search('synthesis', ...) explicitly when synthesis context is needed.
        """
        return self.search("literature", query, n_results=n_results, where=where)

    def search_all(
        self,
        query: str,
        n_results: int = 10,
        collections: list[str] | None = None,
    ) -> list[dict]:
        """Search across multiple collections, returning merged results.

        Args:
            query: Search query.
            n_results: Max results per collection.
            collections: Which collections to search (default: all).

        Returns:
            Merged results sorted by distance (closest first).
        """
        target_collections = collections or COLLECTION_NAMES
        all_results = []
        for coll_name in target_collections:
            if coll_name not in self.collections:
                continue
            results = self.search(coll_name, query, n_results=n_results)
            for r in results:
                r["collection"] = coll_name
            all_results.extend(results)
        all_results.sort(key=lambda x: x.get("distance", 999.0))
        return all_results
