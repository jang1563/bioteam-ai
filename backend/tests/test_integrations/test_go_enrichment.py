"""Tests for g:Profiler GO enrichment client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.go_enrichment import GOEnrichmentClient, GPROFILER_CITATION, GO_SOURCES


@pytest.fixture
def client():
    return GOEnrichmentClient()


@pytest.fixture
def mock_gprofiler_result():
    """Typical g:Profiler result entry."""
    return {
        "source": "GO:BP",
        "native": "GO:0006977",
        "name": "DNA damage response, signal transduction by p53 class mediator",
        "p_value": 1.2e-15,
        "significant": True,
        "term_size": 148,
        "query_size": 25,
        "intersection_size": 18,
        "intersections": ["TP53", "BRCA1", "ATM", "CHEK2"],
    }


class TestGOEnrichmentClient:
    @pytest.mark.asyncio
    async def test_run_enrichment_with_gprofiler(self, client, mock_gprofiler_result):
        """When gprofiler-official is available, use it."""
        mock_gp = MagicMock()
        mock_gp.profile.return_value = [mock_gprofiler_result]
        client._gp = mock_gp

        results = await client.run_enrichment(["TP53", "BRCA1", "ATM", "CHEK2"])

        assert len(results) == 1
        assert results[0]["native"] == "GO:0006977"
        assert results[0]["_source"] == "g:Profiler v0.3"
        assert results[0]["_citation"] == GPROFILER_CITATION
        assert "_retrieved_at" in results[0]

    @pytest.mark.asyncio
    async def test_run_enrichment_disabled(self, client):
        with patch("app.integrations.go_enrichment.settings") as mock_settings:
            mock_settings.go_enrichment_enabled = False
            results = await client.run_enrichment(["TP53"])
        assert results == []

    @pytest.mark.asyncio
    async def test_run_enrichment_empty_list(self, client):
        results = await client.run_enrichment([])
        assert results == []

    @pytest.mark.asyncio
    async def test_run_enrichment_gprofiler_unavailable(self, client):
        """When gprofiler-official is not installed, return empty stub."""
        client._gp = None
        with patch.object(client, "_get_gp", return_value=None):
            results = await client.run_enrichment(["TP53", "BRCA1"])
        assert results == []

    @pytest.mark.asyncio
    async def test_run_enrichment_exception_handled(self, client):
        """GProfiler raising exception returns empty list."""
        mock_gp = MagicMock()
        mock_gp.profile.side_effect = Exception("network error")
        client._gp = mock_gp

        results = await client.run_enrichment(["TP53"])
        assert results == []

    def test_format_for_agent_filters_significant(self, client, mock_gprofiler_result):
        not_significant = {**mock_gprofiler_result, "significant": False, "p_value": 0.3}
        tagged = [
            {**mock_gprofiler_result, "_source": "g:Profiler v0.3", "_citation": GPROFILER_CITATION},
            {**not_significant, "_source": "g:Profiler v0.3", "_citation": GPROFILER_CITATION},
        ]
        formatted = client.format_for_agent(tagged)
        assert len(formatted) == 1
        assert formatted[0]["native"] == "GO:0006977"

    def test_format_for_agent_top_n(self, client, mock_gprofiler_result):
        results = []
        for i in range(10):
            entry = {
                **mock_gprofiler_result,
                "native": f"GO:000000{i}",
                "p_value": 1e-10 + i * 1e-11,
                "_source": "g:Profiler v0.3",
                "_citation": GPROFILER_CITATION,
            }
            results.append(entry)

        formatted = client.format_for_agent(results, top_n=5)
        assert len(formatted) == 5

    def test_format_for_agent_sorted_by_pvalue(self, client, mock_gprofiler_result):
        results = [
            {**mock_gprofiler_result, "native": "GO:0000001", "p_value": 0.001, "_source": "g:Profiler v0.3", "_citation": GPROFILER_CITATION},
            {**mock_gprofiler_result, "native": "GO:0000002", "p_value": 1e-15, "_source": "g:Profiler v0.3", "_citation": GPROFILER_CITATION},
        ]
        formatted = client.format_for_agent(results)
        assert formatted[0]["native"] == "GO:0000002"  # smaller p_value first

    def test_format_for_agent_gene_ratio_format(self, client, mock_gprofiler_result):
        tagged = [{**mock_gprofiler_result, "_source": "g:Profiler v0.3", "_citation": GPROFILER_CITATION}]
        formatted = client.format_for_agent(tagged)
        assert formatted[0]["gene_ratio"] == "18/25"

    def test_go_sources_constant(self):
        """GO_SOURCES should contain the three GO namespaces."""
        assert "GO:BP" in GO_SOURCES
        assert "GO:MF" in GO_SOURCES
        assert "GO:CC" in GO_SOURCES

    def test_gprofiler_citation_content(self):
        assert "g:Profiler" in GPROFILER_CITATION
        assert "g:SCS" in GPROFILER_CITATION
