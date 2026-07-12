"""Benchmark dataset definitions for W9 evaluation.

Datasets are classified into tiers:
  Tier 0 (query-only): No data files needed — LLM knowledge evaluation only
  Tier 1 (fixture): Use existing test fixtures — CI-safe, no download
  Tier 2 (small download): ~50MB public data — auto-download via script
  Tier 3 (large/restricted): >1GB — manual download only

Data files are stored in backend/data/benchmarks/ (gitignored) and
downloaded via backend/scripts/download_benchmark_data.py.
"""

from __future__ import annotations

from pathlib import Path

from app.benchmarks.models import BenchmarkDataset

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# Tier 0: Query-only (knowledge benchmarks — no data files needed)
# ---------------------------------------------------------------------------

CANCER_PATHWAY = BenchmarkDataset(
    id="cancer_pathway",
    name="TCGA BRCA Pathway Enrichment",
    query="Perform pathway enrichment analysis on differentially expressed genes from TCGA breast cancer (BRCA) cohort. Identify key oncogenic pathways and tumor suppressors.",
    data_type="pathway",
    data_manifest_path="",  # Query-only: LLM knowledge evaluation
    budget=5.0,
    expected_genes=[
        "TP53", "PIK3CA", "PTEN", "AKT1", "ERBB2", "ESR1", "MYC",
        "CDH1", "GATA3", "RB1", "CDKN2A", "MAP3K1",
    ],
    expected_pathways=[
        "PI3K-Akt signaling", "p53 signaling", "cell cycle",
        "DNA repair", "estrogen signaling", "MAPK signaling",
        "apoptosis", "mTOR signaling",
    ],
    expected_directions={
        "TP53": "down", "PTEN": "down", "PIK3CA": "up",
        "ERBB2": "up", "MYC": "up", "ESR1": "up",
    },
    ground_truth_confidence="silver",
    benchmark_type="knowledge",
)


GTEx_TISSUE_MARKERS = BenchmarkDataset(
    id="gtex_tissue_markers",
    name="GTEx Tissue-Specific Marker Genes",
    query="Identify tissue-specific marker genes from GTEx expression data. Focus on brain, liver, heart, and skeletal muscle markers.",
    data_type="expression",
    data_manifest_path="",  # Query-only: LLM knowledge evaluation
    budget=5.0,
    expected_genes=[
        # Brain markers
        "GFAP", "MBP", "SYP", "SNAP25", "ENO2",
        # Liver markers
        "ALB", "APOB", "CYP3A4", "F2", "HP",
        # Heart markers
        "MYH7", "TNNT2", "MYL2", "ACTC1",
        # Muscle markers
        "ACTA1", "MYH1", "TTN", "DES",
    ],
    expected_pathways=[
        "synaptic signaling", "lipid metabolism",
        "cardiac muscle contraction", "muscle contraction",
    ],
    expected_directions={},
    ground_truth_confidence="gold",
    benchmark_type="knowledge",
)


# ---------------------------------------------------------------------------
# Tier 1: Fixture datasets (CI-safe, no download needed)
# ---------------------------------------------------------------------------

FIXTURE_DEGS = BenchmarkDataset(
    id="fixture_degs",
    name="Test Fixture DEGs (cancer panel)",
    query="Analyze the provided DEG list for oncogenic pathway enrichment. Identify key cancer drivers, tumor suppressors, and relevant signaling pathways.",
    data_type="expression",
    data_manifest_path=str(_FIXTURE_DIR / "sample_degs.tsv"),
    budget=2.0,
    expected_genes=[
        "BRCA1", "TP53", "EGFR", "MYC", "KRAS", "PIK3CA",
        "CDH1", "ERBB2", "CDKN2A", "PTEN",
    ],
    expected_pathways=[
        "PI3K-Akt signaling", "p53 signaling", "MAPK signaling",
        "cell cycle", "Wnt signaling",
    ],
    expected_directions={
        "BRCA1": "down", "TP53": "up", "EGFR": "up", "MYC": "down",
        "KRAS": "up", "PIK3CA": "up", "CDH1": "down", "ERBB2": "up",
    },
    expected_fold_changes={
        "BRCA1": -2.45, "TP53": 1.82, "EGFR": 3.21, "MYC": -1.05,
        "KRAS": 2.67, "PIK3CA": 1.43, "CDH1": -3.14, "ERBB2": 4.12,
    },
    ground_truth_confidence="gold",
    benchmark_type="internal",
)


FIXTURE_VCF = BenchmarkDataset(
    id="fixture_vcf",
    name="Test Fixture VCF (minimal)",
    query="Annotate the provided VCF variants. Identify any clinically significant variants and their potential functional impact.",
    data_type="variant",
    data_manifest_path=str(_FIXTURE_DIR / "sample.vcf"),
    budget=2.0,
    expected_genes=[],  # Minimal fixture — no gene-level ground truth
    expected_pathways=[],
    expected_directions={},
    ground_truth_confidence="bronze",
    benchmark_type="internal",
)


# ---------------------------------------------------------------------------
# Tier 3: Large/restricted datasets (manual download only)
# ---------------------------------------------------------------------------

MAQC_A_VS_B = BenchmarkDataset(
    id="maqc_a_vs_b",
    name="MAQC A vs B (FDA reference)",
    query="Differential gene expression analysis between MAQC Sample A (Universal Human Reference RNA) and Sample B (Human Brain Reference RNA). Identify DEGs, enriched pathways, and tissue-specific signatures.",
    data_type="expression",
    data_manifest_path="backend/data/benchmarks/maqc_a_vs_b/manifest.json",
    budget=8.0,
    expected_genes=[
        "GFAP", "MBP", "SNAP25", "SYP", "SLC17A7", "GAD1", "GAD2",
        "SLC1A2", "OLIG2", "NEFH", "NEFL", "MAP2", "DLG4", "CAMK2A",
        "GRIA1", "NRGN", "ENO2", "CLU", "CD24", "TUBB3",
    ],
    expected_pathways=[
        "synaptic signaling", "neurotransmitter transport",
        "nervous system development", "axon guidance",
    ],
    expected_directions={
        "GFAP": "up", "MBP": "up", "SNAP25": "up", "SYP": "up",
        "SLC17A7": "up", "GAD1": "up", "GAD2": "up",
    },
    ground_truth_confidence="gold",
)


CLINVAR_BRCA = BenchmarkDataset(
    id="clinvar_brca",
    name="ClinVar BRCA1/2 Pathogenic Variants",
    query="Annotate BRCA1 and BRCA2 variants from ClinVar. Identify pathogenic variants, classify by ACMG criteria, and assess functional impact on DNA repair pathways.",
    data_type="variant",
    data_manifest_path="backend/data/benchmarks/clinvar_brca/manifest.json",
    budget=10.0,
    expected_genes=["BRCA1", "BRCA2", "RAD51", "PALB2", "ATM", "CHEK2"],
    expected_pathways=[
        "homologous recombination", "DNA repair",
        "double-strand break repair", "BRCA1/2 pathway",
    ],
    expected_directions={},
    ground_truth_confidence="gold",
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BENCHMARK_DATASETS: dict[str, BenchmarkDataset] = {
    "cancer_pathway": CANCER_PATHWAY,
    "gtex_tissue_markers": GTEx_TISSUE_MARKERS,
    "fixture_degs": FIXTURE_DEGS,
    "fixture_vcf": FIXTURE_VCF,
    "maqc_a_vs_b": MAQC_A_VS_B,
    "clinvar_brca": CLINVAR_BRCA,
}

BENCHMARK_SUITES: dict[str, list[str]] = {
    "core_bioinfo": ["maqc_a_vs_b", "clinvar_brca", "cancer_pathway", "gtex_tissue_markers"],
    "expression_only": ["maqc_a_vs_b", "gtex_tissue_markers"],
    "query_only": ["cancer_pathway", "gtex_tissue_markers"],
    "ci_quick": ["fixture_degs", "fixture_vcf", "cancer_pathway"],
    "quick_smoke": ["cancer_pathway"],
}


def get_dataset(dataset_id: str) -> BenchmarkDataset | None:
    """Get a benchmark dataset by ID."""
    return BENCHMARK_DATASETS.get(dataset_id)


def get_suite(suite_id: str) -> list[BenchmarkDataset]:
    """Get all datasets in a benchmark suite."""
    dataset_ids = BENCHMARK_SUITES.get(suite_id, [])
    return [BENCHMARK_DATASETS[did] for did in dataset_ids if did in BENCHMARK_DATASETS]
