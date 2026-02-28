"""Preprint Delta Detector — track revision changes in bioRxiv/medRxiv preprints.

Compares v1 → vLatest of a preprint by DOI:
  1. Fetches all posted versions via the bioRxiv /details API.
  2. Extracts abstract text per version.
  3. Uses LLM (Haiku) to summarize key changes between v1 and vLatest.
  4. Flags: sample size changes, added/removed claims, conclusion shifts.

v0.1: LLM-based abstract-level diff (no full-text parsing).
"""

from __future__ import annotations

import difflib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.llm.layer import LLMLayer

logger = logging.getLogger(__name__)

BIORXIV_DETAILS_URL = "https://api.biorxiv.org/details/{server}/{doi}/na/json"


# ── Data models ────────────────────────────────────────────────────────────────


class PreprintVersion(BaseModel):
    """Metadata for one version of a preprint."""

    version: int
    doi: str
    title: str
    date: str  # YYYY-MM-DD
    abstract: str
    authors: list[str] = Field(default_factory=list)
    server: str = "biorxiv"


class DeltaClassification(BaseModel):
    """LLM-structured summary of changes between preprint versions."""

    major_changes: list[str] = Field(
        description="Substantial changes: new results, different conclusions, new/removed claims"
    )
    minor_changes: list[str] = Field(
        description="Small updates: clarifications, added citations, typo fixes"
    )
    sample_size_changed: bool = Field(
        description="True if sample size appears to have changed (e.g. n=50 → n=120)"
    )
    conclusion_shifted: bool = Field(
        description="True if the main conclusion changed in direction or strength"
    )
    methods_updated: bool = Field(
        description="True if methods section shows substantive changes"
    )
    overall_impact: str = Field(
        description="One sentence summary of the revision's scientific impact"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Self-assessed confidence in this classification (0=low, 1=high)"
    )


class PreprintDeltaResult(BaseModel):
    """Full delta report for a preprint DOI."""

    doi: str
    server: str
    title: str
    total_versions: int
    v1_date: str
    latest_date: str
    latest_version: int
    v1_abstract: str
    latest_abstract: str
    abstract_diff_lines: int  # Lines that changed in unified diff
    classification: DeltaClassification | None  # None if LLM unavailable
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


# ── LLM prompt ────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a scientific editor comparing two versions of a biomedical preprint.
Your task is to identify what changed between v1 (original) and the latest version.
Be concise and factual. Focus on scientific changes, not formatting.
"""

_USER_TEMPLATE = """\
## Preprint: {title}

### v1 Abstract (original):
{v1_abstract}

### Latest version (v{latest_version}) Abstract:
{latest_abstract}

Analyze the differences and classify the revision.
"""


# ── Engine ─────────────────────────────────────────────────────────────────────


class PreprintDeltaDetector:
    """Detects and classifies changes between preprint versions."""

    def __init__(
        self,
        llm_layer: LLMLayer | None = None,
        timeout: int = 15,
    ) -> None:
        self._llm = llm_layer
        self._timeout = timeout

    async def fetch_versions(self, doi: str, server: str = "biorxiv") -> list[PreprintVersion]:
        """Fetch all versions of a preprint by DOI from the bioRxiv API."""
        # Normalize DOI: strip protocol/domain if present
        doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        doi = doi.strip("/")

        url = BIORXIV_DETAILS_URL.format(server=server, doi=doi)
        logger.info("Fetching versions: %s", url)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        collection = data.get("collection", [])
        if not collection:
            logger.warning("No versions found for DOI %s", doi)
            return []

        versions: list[PreprintVersion] = []
        for i, item in enumerate(collection, 1):
            abstract = (
                item.get("preprint_abstract", "")
                or item.get("abstract", "")
            ).strip()
            authors_str = item.get("preprint_authors", "") or item.get("authors", "")
            authors = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []
            versions.append(PreprintVersion(
                version=i,
                doi=item.get("preprint_doi", "") or item.get("doi", doi),
                title=item.get("preprint_title", "") or item.get("title", ""),
                date=item.get("preprint_date", "") or item.get("date", ""),
                abstract=abstract,
                authors=authors,
                server=server,
            ))

        return versions

    def compute_diff(self, text_a: str, text_b: str) -> tuple[int, str]:
        """Compute unified diff between two texts. Returns (changed_lines, diff_text)."""
        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()
        diff = list(difflib.unified_diff(lines_a, lines_b, lineterm=""))
        changed = sum(1 for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
        return changed, "\n".join(diff[:50])  # cap at 50 diff lines for storage

    async def classify_delta(
        self,
        title: str,
        v1_abstract: str,
        latest_abstract: str,
        latest_version: int,
    ) -> DeltaClassification | None:
        """Use LLM (Haiku) to classify the delta between v1 and latest."""
        if self._llm is None:
            return None

        messages = [
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    title=title,
                    v1_abstract=v1_abstract[:1500],  # cap for token limit
                    latest_abstract=latest_abstract[:1500],
                    latest_version=latest_version,
                ),
            }
        ]

        try:
            result, _meta = await self._llm.complete_structured(
                messages=messages,
                model_tier="haiku",
                response_model=DeltaClassification,
                system=_SYSTEM,
                temperature=0.0,
                max_tokens=1024,
            )
            return result
        except Exception as e:
            logger.warning("Delta classification LLM call failed: %s", e)
            return None

    async def analyze(self, doi: str, server: str = "biorxiv") -> PreprintDeltaResult:
        """Full pipeline: fetch versions → diff → classify → return delta result."""
        try:
            versions = await self.fetch_versions(doi, server)
        except Exception as e:
            logger.error("Failed to fetch versions for %s: %s", doi, e)
            return PreprintDeltaResult(
                doi=doi, server=server, title="", total_versions=0,
                v1_date="", latest_date="", latest_version=0,
                v1_abstract="", latest_abstract="",
                abstract_diff_lines=0, classification=None,
                error=str(e),
            )

        if not versions:
            return PreprintDeltaResult(
                doi=doi, server=server, title="", total_versions=0,
                v1_date="", latest_date="", latest_version=0,
                v1_abstract="", latest_abstract="",
                abstract_diff_lines=0, classification=None,
                error="No versions found for this DOI",
            )

        v1 = versions[0]
        latest = versions[-1]
        title = latest.title or v1.title

        diff_lines, _ = self.compute_diff(v1.abstract, latest.abstract)

        # Only run LLM if there are actual changes and multiple versions
        classification: DeltaClassification | None = None
        if len(versions) > 1 and diff_lines > 0:
            classification = await self.classify_delta(
                title=title,
                v1_abstract=v1.abstract,
                latest_abstract=latest.abstract,
                latest_version=latest.version,
            )

        return PreprintDeltaResult(
            doi=doi,
            server=server,
            title=title,
            total_versions=len(versions),
            v1_date=v1.date,
            latest_date=latest.date,
            latest_version=latest.version,
            v1_abstract=v1.abstract,
            latest_abstract=latest.abstract,
            abstract_diff_lines=diff_lines,
            classification=classification,
        )
