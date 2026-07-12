"""Tests for PTC handler dispatcher and bioinformatics tool routing."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.llm.ptc_handler import (
    build_tool_implementations,
    handle_ptc_tool_call,
)
from app.llm.ptc_tools import (
    BLAST_TOOL,
    GENE_NAME_CHECKER_TOOL,
    GO_ENRICHMENT_TOOL,
    GWAS_ASSOCIATIONS_TOOL,
    STATISTICAL_CHECKER_TOOL,
    STRING_PPI_TOOL,
    UNIPROT_LOOKUP_TOOL,
    VEP_TOOL,
    get_all_ptc_tools,
    get_bio_ptc_tools,
)

# ---------------------------------------------------------------------------
# New tool definitions
# ---------------------------------------------------------------------------

class TestBioToolDefinitions:
    def test_gene_name_checker_schema(self):
        assert GENE_NAME_CHECKER_TOOL["name"] == "check_gene_names"
        assert "gene_list" in GENE_NAME_CHECKER_TOOL["input_schema"]["properties"]
        assert "allowed_callers" in GENE_NAME_CHECKER_TOOL

    def test_statistical_checker_schema(self):
        assert STATISTICAL_CHECKER_TOOL["name"] == "check_statistics"
        assert "stats" in STATISTICAL_CHECKER_TOOL["input_schema"]["properties"]
        assert "allowed_callers" in STATISTICAL_CHECKER_TOOL

    def test_blast_tool_schema(self):
        assert BLAST_TOOL["name"] == "run_blast"
        assert "sequence" in BLAST_TOOL["input_schema"]["properties"]
        assert "program" in BLAST_TOOL["input_schema"]["properties"]
        assert "allowed_callers" in BLAST_TOOL

    def test_vep_tool_schema(self):
        assert VEP_TOOL["name"] == "run_vep"
        assert "hgvs" in VEP_TOOL["input_schema"]["properties"]
        assert "allowed_callers" in VEP_TOOL

    def test_go_enrichment_tool_schema(self):
        assert GO_ENRICHMENT_TOOL["name"] == "run_go_enrichment"
        assert "gene_list" in GO_ENRICHMENT_TOOL["input_schema"]["properties"]
        assert "allowed_callers" in GO_ENRICHMENT_TOOL

    def test_uniprot_lookup_tool_schema(self):
        assert UNIPROT_LOOKUP_TOOL["name"] == "lookup_protein"
        props = UNIPROT_LOOKUP_TOOL["input_schema"]["properties"]
        assert "gene_symbol" in props
        assert "accession" in props
        assert "allowed_callers" in UNIPROT_LOOKUP_TOOL

    def test_string_ppi_tool_schema(self):
        assert STRING_PPI_TOOL["name"] == "get_ppi_network"
        props = STRING_PPI_TOOL["input_schema"]["properties"]
        assert "genes" in props
        assert props["genes"]["type"] == "array"
        assert "min_score" in props
        assert "allowed_callers" in STRING_PPI_TOOL

    def test_gwas_associations_tool_schema(self):
        assert GWAS_ASSOCIATIONS_TOOL["name"] == "get_gwas_associations"
        props = GWAS_ASSOCIATIONS_TOOL["input_schema"]["properties"]
        assert "gene" in props
        assert "rsid" in props
        assert "p_threshold" in props
        assert "allowed_callers" in GWAS_ASSOCIATIONS_TOOL

    def test_get_all_ptc_tools_includes_bio_tools(self):
        tools = get_all_ptc_tools()
        names = [t.get("name") for t in tools]
        assert "check_gene_names" in names
        assert "check_statistics" in names
        assert "run_blast" in names
        assert "run_vep" in names
        assert "run_go_enrichment" in names
        assert "lookup_protein" in names
        assert "get_ppi_network" in names
        assert "get_gwas_associations" in names

    def test_get_bio_ptc_tools_returns_bio_tools_only(self):
        bio_tools = get_bio_ptc_tools()
        names = [t.get("name") for t in bio_tools if "name" in t]
        assert "run_vep" in names
        assert "check_gene_names" in names
        assert "lookup_protein" in names
        assert "get_ppi_network" in names
        assert "get_gwas_associations" in names
        # Should not include legacy ChromaDB tools
        assert "search_memory" not in names


# ---------------------------------------------------------------------------
# PTC handler dispatcher
# ---------------------------------------------------------------------------

class TestHandlePTCToolCall:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_json(self):
        result = await handle_ptc_tool_call("nonexistent_tool", {})
        data = json.loads(result)
        assert "error" in data
        assert "nonexistent_tool" in data["error"]

    @pytest.mark.asyncio
    async def test_vep_hgvs_dispatched(self):
        mock_results = [{"most_severe_consequence": "missense_variant", "_source": "Ensembl VEP v112"}]
        with patch("app.integrations.ensembl.EnsemblClient") as MockClient:
            instance = AsyncMock()
            instance.vep_hgvs = AsyncMock(return_value=mock_results)
            MockClient.return_value = instance

            result = await handle_ptc_tool_call("run_vep", {"hgvs": "9:g.107545939A>T"})

        data = json.loads(result)
        assert "vep_results" in data
        assert data["count"] == 1
        assert data["_source"] == "Ensembl VEP v112"

    @pytest.mark.asyncio
    async def test_vep_region_dispatched(self):
        mock_results = [{"most_severe_consequence": "synonymous_variant", "_source": "Ensembl VEP v112"}]
        with patch("app.integrations.ensembl.EnsemblClient") as MockClient:
            instance = AsyncMock()
            instance.vep_region = AsyncMock(return_value=mock_results)
            MockClient.return_value = instance

            result = await handle_ptc_tool_call("run_vep", {
                "chrom": "17", "pos": 41234451, "ref": "A", "alt": "G"
            })

        data = json.loads(result)
        assert "vep_results" in data

    @pytest.mark.asyncio
    async def test_vep_missing_input_returns_error(self):
        result = await handle_ptc_tool_call("run_vep", {})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_go_enrichment_dispatched(self):
        mock_enrichment = [
            {
                "source": "GO:BP",
                "native": "GO:0006977",
                "name": "DNA damage response",
                "p_value": 1e-15,
                "significant": True,
                "term_size": 148,
                "query_size": 25,
                "intersection_size": 18,
                "_source": "g:Profiler v0.3",
                "_citation": "g:Profiler",
            }
        ]
        with patch("app.integrations.go_enrichment.GOEnrichmentClient") as MockClient:
            instance = MagicMock()
            instance.run_enrichment = AsyncMock(return_value=mock_enrichment)
            instance.format_for_agent = MagicMock(return_value=[{
                "source": "GO:BP",
                "native": "GO:0006977",
                "name": "DNA damage response",
                "p_value": 1e-15,
                "significant": True,
                "gene_ratio": "18/25",
                "_source": "g:Profiler v0.3",
            }])
            MockClient.return_value = instance

            result = await handle_ptc_tool_call("run_go_enrichment", {"gene_list": ["BRCA1", "TP53"]})

        data = json.loads(result)
        assert "enrichment_results" in data
        assert data["genes_submitted"] == 2
        assert "_source" in data

    @pytest.mark.asyncio
    async def test_go_enrichment_empty_list_returns_error(self):
        result = await handle_ptc_tool_call("run_go_enrichment", {})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_blast_biopython_unavailable_graceful(self):
        """When biopython is not installed, return helpful error message."""
        with patch.dict("sys.modules", {"Bio": None, "Bio.Blast": None}):
            result = await handle_ptc_tool_call("run_blast", {"sequence": "ATGCGT"})

        data = json.loads(result)
        assert "error" in data
        # Either biopython import error or graceful message
        assert "_source" in data

    @pytest.mark.asyncio
    async def test_blast_empty_sequence_returns_error(self):
        result = await handle_ptc_tool_call("run_blast", {"sequence": ""})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_deduplicate_papers_works(self):
        papers = [
            {"doi": "10.1234/test", "title": "Paper A"},
            {"doi": "10.1234/test", "title": "Paper A duplicate"},
            {"doi": "10.5678/other", "title": "Paper B"},
        ]
        result = await handle_ptc_tool_call("deduplicate_papers", {"papers": papers})
        data = json.loads(result)
        assert data["deduplicated_count"] == 2
        assert data["original_count"] == 3

    @pytest.mark.asyncio
    async def test_uniprot_lookup_by_gene(self):
        mock_entry = {
            "primaryAccession": "P38398",
            "genes": [{"geneName": {"value": "BRCA1"}}],
            "proteinDescription": {"recommendedName": {"fullName": {"value": "Breast cancer type 1"}}},
            "comments": [
                {"commentType": "FUNCTION", "texts": [{"value": "E3 ubiquitin ligase"}]},
                {"commentType": "SUBCELLULAR LOCATION", "subcellularLocations": [
                    {"location": {"value": "Nucleus"}},
                ]},
            ],
            "sequence": {"length": 1863},
        }
        with patch("app.integrations.uniprot.UniProtClient") as MockClient:
            instance = MagicMock()
            instance.search_by_gene = AsyncMock(return_value=[mock_entry])
            MockClient.return_value = instance

            result = await handle_ptc_tool_call("lookup_protein", {"gene_symbol": "BRCA1"})

        data = json.loads(result)
        assert data["accession"] == "P38398"
        assert data["gene"] == "BRCA1"
        assert data["sequence_length"] == 1863
        assert data["_source"] == "UniProt REST v2"

    @pytest.mark.asyncio
    async def test_uniprot_lookup_missing_input_returns_error(self):
        result = await handle_ptc_tool_call("lookup_protein", {})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_string_ppi_dispatched(self):
        mock_interactions = [
            {"preferredName_A": "BRCA1", "preferredName_B": "TP53", "score": 0.999},
            {"preferredName_A": "BRCA1", "preferredName_B": "ATM", "score": 0.987},
        ]
        with patch("app.integrations.stringdb.STRINGClient") as MockClient:
            instance = MagicMock()
            instance.get_interactions = AsyncMock(return_value=mock_interactions)
            MockClient.return_value = instance

            result = await handle_ptc_tool_call("get_ppi_network", {"genes": ["BRCA1", "TP53", "ATM"]})

        data = json.loads(result)
        assert "interactions" in data
        assert data["total"] == 2
        assert data["interactions"][0]["protein_a"] == "BRCA1"
        assert data["_source"] == "STRING DB v12"

    @pytest.mark.asyncio
    async def test_string_ppi_missing_genes_returns_error(self):
        result = await handle_ptc_tool_call("get_ppi_network", {})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_gwas_associations_by_gene(self):
        mock_assoc = [
            {
                "pvalue": "1e-20",
                "loci": [{"strongestRiskAlleles": [{"riskAlleleName": "rs1234-A"}]}],
                "trait": "Breast cancer",
                "study": "GCST001",
            }
        ]
        with patch("app.integrations.gwas_catalog.GWASCatalogClient") as MockClient:
            instance = MagicMock()
            instance.get_associations_by_gene = AsyncMock(return_value=mock_assoc)
            MockClient.return_value = instance

            result = await handle_ptc_tool_call("get_gwas_associations", {"gene": "BRCA1"})

        data = json.loads(result)
        assert "associations" in data
        assert data["total"] == 1
        assert data["associations"][0]["risk_allele"] == "rs1234-A"
        assert data["_source"] == "GWAS Catalog v1.0"

    @pytest.mark.asyncio
    async def test_gwas_associations_by_rsid(self):
        mock_assoc = [{"pvalue": "5e-12", "risk_allele": "rs999-T", "disease_trait": "Diabetes", "study_accession": "GCST002"}]
        with patch("app.integrations.gwas_catalog.GWASCatalogClient") as MockClient:
            instance = MagicMock()
            instance.get_associations_by_snp = AsyncMock(return_value=mock_assoc)
            MockClient.return_value = instance

            result = await handle_ptc_tool_call("get_gwas_associations", {"rsid": "rs999"})

        data = json.loads(result)
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_gwas_missing_input_returns_error(self):
        result = await handle_ptc_tool_call("get_gwas_associations", {})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_exception_in_handler_returns_error_json(self):
        """Handler exceptions should be caught, not propagated."""
        with patch("app.llm.ptc_handler._handle_vep", side_effect=RuntimeError("crash")):
            result = await handle_ptc_tool_call("run_vep", {"hgvs": "9:g.107545939A>T"})
        data = json.loads(result)
        assert "error" in data
        assert "_retrieved_at" in data


# ---------------------------------------------------------------------------
# build_tool_implementations
# ---------------------------------------------------------------------------

class TestBuildToolImplementations:
    def test_returns_all_tools_by_default(self):
        impls = build_tool_implementations()
        assert "run_vep" in impls
        assert "check_gene_names" in impls
        assert "check_statistics" in impls
        assert "run_blast" in impls
        assert "run_go_enrichment" in impls
        assert "lookup_protein" in impls
        assert "get_ppi_network" in impls
        assert "get_gwas_associations" in impls

    def test_filter_by_tool_names(self):
        impls = build_tool_implementations(["run_vep", "check_gene_names"])
        assert "run_vep" in impls
        assert "check_gene_names" in impls
        assert "run_blast" not in impls
        assert "run_go_enrichment" not in impls

    @pytest.mark.asyncio
    async def test_implementations_are_callable(self):
        impls = build_tool_implementations(["run_vep"])
        impl = impls["run_vep"]
        # Call with empty input — should return error JSON, not raise
        result = await impl({})
        data = json.loads(result)
        assert "error" in data  # Missing required input


# ---------------------------------------------------------------------------
# tool_registry updates
# ---------------------------------------------------------------------------

class TestToolRegistryUpdates:
    def test_t01_genomics_has_vep_and_gene_check(self):
        from app.llm.tool_registry import get_classification
        clf = get_classification("t01_genomics")
        assert "run_vep" in clf["always_loaded"]
        assert "check_gene_names" in clf["always_loaded"]
        assert "lookup_protein" in clf["always_loaded"]
        assert "get_gwas_associations" in clf["always_loaded"]
        assert "run_blast" in clf["deferred"]

    def test_t06_systems_bio_has_go_enrichment_and_ppi(self):
        from app.llm.tool_registry import get_classification
        clf = get_classification("t06_systems_bio")
        assert "run_go_enrichment" in clf["always_loaded"]
        assert "get_ppi_network" in clf["always_loaded"]
        assert "lookup_protein" in clf["always_loaded"]

    def test_t03_proteomics_has_protein_tools(self):
        from app.llm.tool_registry import get_classification
        clf = get_classification("t03_proteomics")
        assert "lookup_protein" in clf["always_loaded"]
        assert "get_ppi_network" in clf["deferred"]

    def test_t04_biostatistics_has_stat_checker(self):
        from app.llm.tool_registry import get_classification
        clf = get_classification("t04_biostatistics")
        assert "check_statistics" in clf["always_loaded"]

    def test_data_integrity_auditor_has_both_checkers(self):
        from app.llm.tool_registry import get_classification
        clf = get_classification("data_integrity_auditor")
        assert "check_gene_names" in clf["always_loaded"]
        assert "check_statistics" in clf["always_loaded"]
