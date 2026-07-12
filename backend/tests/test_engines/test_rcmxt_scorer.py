"""Tests for RCMXTScorer — deterministic heuristic evidence scorer."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.engines.rcmxt_scorer import RCMXTScorer


def _make_papers(n: int, with_doi: bool = True, year: int = 2024) -> list[dict]:
    """Create n mock paper dicts."""
    return [
        {
            "doi": f"10.1234/paper{i}" if with_doi else None,
            "pmid": f"{30000000 + i}",
            "title": f"Paper {i}",
            "year": year + (i % 3),
        }
        for i in range(n)
    ]


def _make_extracted(n: int, organism: str = "human", tech: str = "RNA-seq", sample_size: int = 10) -> list[dict]:
    """Create n mock extracted paper dicts."""
    return [
        {
            "paper_id": f"p{i}",
            "organism": organism,
            "technology": tech,
            "sample_size": sample_size,
        }
        for i in range(n)
    ]


# === R-axis tests ===


def test_r_score_many_sources():
    """R approaches 1.0 with many unique sources."""
    scorer = RCMXTScorer()
    scorer.load_step_data(search_output={"papers": _make_papers(10)})
    score = scorer.score_claim("test claim")
    assert score.R >= 0.8


def test_r_score_few_sources():
    """R is low with few sources."""
    scorer = RCMXTScorer()
    scorer.load_step_data(search_output={"papers": _make_papers(2)})
    score = scorer.score_claim("test claim")
    assert score.R <= 0.5


def test_r_score_no_papers():
    """R is 0.0 with no papers."""
    scorer = RCMXTScorer()
    score = scorer.score_claim("test claim")
    assert score.R == 0.0


# === C-axis tests ===


def test_c_score_with_organisms():
    """C > 0 when organisms present in extract data."""
    scorer = RCMXTScorer()
    scorer.load_step_data(extract_output={"papers": _make_extracted(3, organism="human")})
    score = scorer.score_claim("test claim")
    assert score.C > 0.0


def test_c_score_multiple_organisms():
    """C increases with more organisms."""
    scorer = RCMXTScorer()
    papers = [
        {"organism": "human", "technology": "RNA-seq"},
        {"organism": "mouse", "technology": "RNA-seq"},
        {"organism": "zebrafish", "technology": "RNA-seq"},
    ]
    scorer.load_step_data(extract_output={"papers": papers})
    score = scorer.score_claim("test claim")
    assert score.C == 1.0  # 3 organisms / 3 = 1.0


def test_c_score_no_organisms():
    """C is 0.0 when no organisms in data."""
    scorer = RCMXTScorer()
    scorer.load_step_data(extract_output={"papers": [{"technology": "RNA-seq"}]})
    score = scorer.score_claim("test claim")
    assert score.C == 0.0


# === M-axis tests ===


def test_m_score_with_sample_sizes():
    """M increases with papers that have sample_size > 0."""
    scorer = RCMXTScorer()
    scorer.load_step_data(extract_output={"papers": _make_extracted(5, sample_size=100)})
    score = scorer.score_claim("test claim")
    assert score.M >= 0.9


def test_m_score_no_extraction():
    """M defaults to 0.3 when no extraction data."""
    scorer = RCMXTScorer()
    score = scorer.score_claim("test claim")
    assert score.M == 0.3


# === X-axis tests ===


def test_x_score_multi_tech():
    """X is not None when multiple technologies present."""
    scorer = RCMXTScorer()
    papers = [
        {"organism": "human", "technology": "RNA-seq"},
        {"organism": "human", "technology": "proteomics"},
    ]
    scorer.load_step_data(extract_output={"papers": papers})
    score = scorer.score_claim("test claim")
    assert score.X is not None
    assert score.X > 0.0


def test_x_score_single_tech():
    """X is None when single technology."""
    scorer = RCMXTScorer()
    scorer.load_step_data(extract_output={"papers": _make_extracted(3)})
    score = scorer.score_claim("test claim")
    assert score.X is None


# === T-axis tests ===


def test_t_score_recent_papers():
    """T is high with recent papers."""
    scorer = RCMXTScorer()
    scorer.load_step_data(search_output={"papers": _make_papers(5, year=2025)})
    score = scorer.score_claim("test claim")
    assert score.T >= 0.5


def test_t_score_no_years():
    """T defaults to 0.3 with no year data."""
    scorer = RCMXTScorer()
    score = scorer.score_claim("test claim")
    assert score.T == 0.3


# === Composite & score_all tests ===


def test_composite_computed():
    """composite is set after scoring."""
    scorer = RCMXTScorer()
    scorer.load_step_data(
        search_output={"papers": _make_papers(10)},
        extract_output={"papers": _make_extracted(5)},
    )
    score = scorer.score_claim("test claim")
    assert score.composite is not None
    assert 0.0 <= score.composite <= 1.0


def test_score_all_multiple_findings():
    """score_all() scores each key_finding."""
    scorer = RCMXTScorer()
    scorer.load_step_data(
        search_output={"papers": _make_papers(5)},
        synthesis_output={"key_findings": ["finding A", "finding B", "finding C"]},
    )
    scores = scorer.score_all()
    assert len(scores) == 3
    assert all(s.composite is not None for s in scores)


def test_score_all_empty_findings():
    """score_all() returns empty list when no key_findings."""
    scorer = RCMXTScorer()
    scores = scorer.score_all()
    assert scores == []


def test_scorer_version_set():
    """scorer_version is v0.1-heuristic."""
    scorer = RCMXTScorer()
    score = scorer.score_claim("test")
    assert score.scorer_version == "v0.1-heuristic"
    assert score.model_version == "deterministic"


def test_load_step_data_none_inputs():
    """Graceful handling of None inputs."""
    scorer = RCMXTScorer()
    scorer.load_step_data(None, None, None)
    score = scorer.score_claim("test")
    assert score.R == 0.0
    assert score.composite is not None


if __name__ == "__main__":
    print("Testing RCMXTScorer:")
    test_r_score_many_sources()
    test_r_score_few_sources()
    test_r_score_no_papers()
    test_c_score_with_organisms()
    test_c_score_multiple_organisms()
    test_c_score_no_organisms()
    test_m_score_with_sample_sizes()
    test_m_score_no_extraction()
    test_x_score_multi_tech()
    test_x_score_single_tech()
    test_t_score_recent_papers()
    test_t_score_no_years()
    test_composite_computed()
    test_score_all_multiple_findings()
    test_score_all_empty_findings()
    test_scorer_version_set()
    test_load_step_data_none_inputs()
    print("All RCMXTScorer tests passed!")
