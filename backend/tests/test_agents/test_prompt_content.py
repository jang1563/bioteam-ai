"""Validate that agent prompt files contain required Phase 2 sections.

These tests run without any LLM calls — they simply verify that the
prompt markdown files have the expected content for Phase 2 upgrades.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROMPTS_DIR = Path(__file__).parents[2] / "app" / "agents" / "prompts"


def read_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text()


# ----------------------------------------------------------------
# T01 Genomics
# ----------------------------------------------------------------

def test_t01_has_vep_tool_format():
    content = read_prompt("t01_genomics.md")
    assert "vep_results" in content
    assert "most_severe_consequence" in content


def test_t01_has_alphamissense():
    content = read_prompt("t01_genomics.md")
    assert "AlphaMissense" in content
    assert "0.564" in content  # threshold


def test_t01_has_acmg_rules():
    content = read_prompt("t01_genomics.md")
    assert "PM2" in content
    assert "PP3" in content


def test_t01_grounding_no_fabricate_ids():
    content = read_prompt("t01_genomics.md")
    assert "NEVER generate" in content or "never generate" in content.lower()


# ----------------------------------------------------------------
# T02 Transcriptomics
# ----------------------------------------------------------------

def test_t02_has_deseq2_columns():
    content = read_prompt("t02_transcriptomics.md")
    assert "baseMean" in content
    assert "log2FoldChange" in content
    assert "padj" in content


def test_t02_has_gtex_citation():
    content = read_prompt("t02_transcriptomics.md")
    assert "GTEx" in content
    assert "phs000424" in content


def test_t02_has_scrnaseq_2025():
    content = read_prompt("t02_transcriptomics.md")
    assert "scGPT" in content
    assert "Geneformer" in content


# ----------------------------------------------------------------
# T03 Proteomics
# ----------------------------------------------------------------

def test_t03_has_uniprot_format():
    content = read_prompt("t03_proteomics.md")
    assert "uniprot_results" in content
    assert "reviewed" in content
    assert "P04637" in content  # TP53 accession as example


def test_t03_has_string_thresholds():
    content = read_prompt("t03_proteomics.md")
    assert "700" in content  # high confidence threshold
    assert "400" in content  # medium confidence


# ----------------------------------------------------------------
# T04 Biostatistics
# ----------------------------------------------------------------

def test_t04_has_apa_format():
    content = read_prompt("t04_biostatistics.md")
    assert "Cohen's d" in content
    assert "eta" in content  # η²


def test_t04_has_grim_test():
    content = read_prompt("t04_biostatistics.md")
    assert "GRIM" in content


def test_t04_multiple_comparisons_mandate():
    content = read_prompt("t04_biostatistics.md")
    assert "MUST state" in content or "must state" in content.lower()


# ----------------------------------------------------------------
# T05 ML/DL
# ----------------------------------------------------------------

def test_t05_has_2025_models():
    content = read_prompt("t05_ml_dl.md")
    assert "ESM-3" in content
    assert "Evo" in content


def test_t05_ood_warning():
    content = read_prompt("t05_ml_dl.md")
    assert "Out-of-Distribution" in content or "out-of-distribution" in content.lower()


# ----------------------------------------------------------------
# T06 Systems Biology
# ----------------------------------------------------------------

def test_t06_has_gprofiler_format():
    content = read_prompt("t06_systems_bio.md")
    assert "enrichment_results" in content
    assert "g:SCS" in content
    assert "intersection_size" in content


def test_t06_go_term_grounding():
    content = read_prompt("t06_systems_bio.md")
    # Should warn against fabricating GO IDs
    assert "GO:00" in content  # example format shown


# ----------------------------------------------------------------
# T07 Structural Biology
# ----------------------------------------------------------------

def test_t07_has_alphafold3_plddt():
    content = read_prompt("t07_structural_bio.md")
    assert "90" in content  # Very high pLDDT
    assert "70" in content  # Low confidence boundary
    assert "AlphaFold3" in content


def test_t07_has_docking_interpretation():
    content = read_prompt("t07_structural_bio.md")
    assert "kcal/mol" in content
    assert "−8" in content or "-8" in content


# ----------------------------------------------------------------
# T08 SciComm
# ----------------------------------------------------------------

def test_t08_has_journal_formats():
    content = read_prompt("t08_scicomm.md")
    assert "Nature" in content
    assert "PLOS" in content


def test_t08_doi_grounding():
    content = read_prompt("t08_scicomm.md")
    assert "DOI" in content or "doi" in content.lower()
    assert "never generate" in content.lower() or "do not generate" in content.lower() or "Never generate" in content


# ----------------------------------------------------------------
# T09 Grants
# ----------------------------------------------------------------

def test_t09_has_nih_2025_format():
    content = read_prompt("t09_grants.md")
    assert "SF424" in content
    assert "2025" in content


def test_t09_has_funding_rates():
    content = read_prompt("t09_grants.md")
    assert "%" in content
    assert "FY2025" in content or "FY2024" in content


# ----------------------------------------------------------------
# T10 Data Engineering
# ----------------------------------------------------------------

def test_t10_has_nextflow_dsl2():
    content = read_prompt("t10_data_eng.md")
    assert "DSL2" in content or "process " in content
    assert "container" in content.lower()


def test_t10_has_snakemake_8():
    content = read_prompt("t10_data_eng.md")
    assert "Snakemake" in content
    assert "rule" in content


# ----------------------------------------------------------------
# Research Director
# ----------------------------------------------------------------

def test_research_director_has_generate_debate_evolve():
    content = read_prompt("research_director.md")
    assert "Generate" in content
    assert "Debate" in content
    assert "Evolve" in content


def test_research_director_has_w9_routing():
    content = read_prompt("research_director.md")
    assert "W9" in content


def test_research_director_hypothesis_scoring():
    content = read_prompt("research_director.md")
    assert "novelty_score" in content
    assert "plausibility_score" in content
    assert "testability_score" in content


# ----------------------------------------------------------------
# QA Agents
# ----------------------------------------------------------------

def test_qa_bio_has_cross_db_validation():
    content = read_prompt("qa_biological_plausibility.md")
    assert "GO" in content
    assert "KEGG" in content
    assert "Reactome" in content
    assert "cross-database" in content.lower() or "Cross-Database" in content


def test_qa_stat_has_grim_test():
    content = read_prompt("qa_statistical_rigor.md")
    assert "GRIM" in content
    assert "arithmetically impossible" in content


def test_qa_stat_has_ci_check():
    content = read_prompt("qa_statistical_rigor.md")
    assert "confidence interval" in content.lower() or "Confidence Interval" in content


def test_all_prompts_have_grounding_section():
    """Every prompt must have a Grounding rule."""
    for md_file in PROMPTS_DIR.glob("t0*.md"):
        content = md_file.read_text()
        assert "Grounding" in content, f"{md_file.name} missing Grounding section"
