"""Tests for CostRecord, EpisodicEvent, and NegativeResult models."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from datetime import datetime, timezone

import pytest
from app.models.cost import CostAccuracyReport, CostRecord
from app.models.memory import EpisodicEvent, SemanticEntry
from app.models.negative_result import FailedProtocol, NegativeResult
from app.models.refinement import RefinementConfig
from pydantic import ValidationError

# === CostRecord Tests ===


class TestCostRecord:
    def test_defaults(self):
        r = CostRecord(agent_id="t01_genomics", model_tier="sonnet")
        assert r.id  # UUID auto-generated
        assert r.agent_id == "t01_genomics"
        assert r.model_tier == "sonnet"
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.cost_usd == 0.0
        assert r.timestamp.tzinfo is not None

    def test_with_values(self):
        r = CostRecord(
            agent_id="research_director",
            model_tier="opus",
            model_version="claude-opus-4-6",
            input_tokens=1500,
            output_tokens=800,
            cached_input_tokens=500,
            cost_usd=0.045,
            workflow_id="w1_abc",
            step_id="SYNTHESIZE",
        )
        assert r.workflow_id == "w1_abc"
        assert r.step_id == "SYNTHESIZE"
        assert r.cost_usd == 0.045

    def test_unique_ids(self):
        r1 = CostRecord(agent_id="a", model_tier="haiku")
        r2 = CostRecord(agent_id="a", model_tier="haiku")
        assert r1.id != r2.id


class TestCostAccuracyReport:
    def test_construction(self):
        report = CostAccuracyReport(
            workflow_id="w1_abc",
            template="W1",
            estimated_cost=0.50,
            actual_cost=0.42,
            ratio=0.84,
            per_step_breakdown=[{"step": "SEARCH", "est": 0.1, "actual": 0.08}],
            generated_at=datetime.now(timezone.utc),
        )
        assert report.ratio == 0.84
        assert len(report.per_step_breakdown) == 1


# === EpisodicEvent Tests ===


class TestEpisodicEvent:
    def test_defaults(self):
        e = EpisodicEvent(event_type="query")
        assert e.id
        assert e.event_type == "query"
        assert e.agent_id is None
        assert e.workflow_id is None
        assert e.summary == ""
        assert e.details == {}
        assert e.timestamp.tzinfo is not None

    def test_with_details(self):
        e = EpisodicEvent(
            event_type="contradiction_detected",
            agent_id="ambiguity_engine",
            workflow_id="w6_xyz",
            summary="Found 3 contradictions about VEGF levels",
            details={"count": 3, "claims": ["A", "B", "C"]},
        )
        assert e.details["count"] == 3
        assert len(e.details["claims"]) == 3

    def test_unique_ids(self):
        e1 = EpisodicEvent(event_type="a")
        e2 = EpisodicEvent(event_type="a")
        assert e1.id != e2.id


class TestSemanticEntry:
    def test_defaults(self):
        entry = SemanticEntry(collection="literature", text="Test paper abstract")
        assert entry.id
        assert entry.collection == "literature"
        assert entry.metadata == {}

    def test_with_metadata(self):
        entry = SemanticEntry(
            collection="synthesis",
            text="Agent-generated interpretation",
            metadata={"doi": "10.1234/test", "agent_id": "t02_transcriptomics"},
        )
        assert entry.metadata["doi"] == "10.1234/test"


# === NegativeResult Tests ===


class TestNegativeResult:
    def test_defaults(self):
        nr = NegativeResult(
            claim="Expected upregulation of VEGF",
            outcome="No significant change observed",
            source="internal",
        )
        assert nr.id
        assert nr.confidence == 0.5
        assert nr.verification_status == "unverified"
        assert nr.verified_by is None
        assert nr.created_by == "human"
        assert nr.created_at.tzinfo is not None

    def test_full_construction(self):
        nr = NegativeResult(
            claim="Gene X knockout expected lethal",
            outcome="Mice survived with compensatory pathway",
            conditions={"organism": "mouse", "gene": "X", "method": "CRISPR"},
            source="internal",
            confidence=0.85,
            failure_category="biological",
            implications=["Compensatory pathway exists", "Need double KO"],
            organism="Mus musculus",
            verified_by="jak4013",
            verification_status="confirmed",
        )
        assert nr.confidence == 0.85
        assert nr.verification_status == "confirmed"
        assert len(nr.implications) == 2
        assert nr.conditions["method"] == "CRISPR"

    def test_unique_ids(self):
        nr1 = NegativeResult(claim="a", outcome="b", source="internal")
        nr2 = NegativeResult(claim="a", outcome="b", source="internal")
        assert nr1.id != nr2.id


class TestFailedProtocol:
    def test_construction(self):
        fp = FailedProtocol(
            protocol_name="ChIP-seq for H3K4me3",
            target="H3K4me3",
            expected_result="Enrichment at promoters",
            actual_result="No enrichment above background",
            conditions={"cell_line": "HeLa", "antibody": "ab8580"},
            failure_reason="Antibody lot variability",
            suggested_modifications=["Try different lot", "Use CUT&RUN instead"],
        )
        assert fp.protocol_name == "ChIP-seq for H3K4me3"
        assert len(fp.suggested_modifications) == 2


# === RefinementConfig Validator Tests ===


class TestRefinementConfigValidation:
    def test_valid_scorer_models(self):
        for model in ("opus", "sonnet", "haiku"):
            cfg = RefinementConfig(scorer_model=model)
            assert cfg.scorer_model == model

    def test_invalid_scorer_model_rejected(self):
        with pytest.raises(ValidationError, match="scorer_model"):
            RefinementConfig(scorer_model="gpt-4")

    def test_invalid_scorer_model_typo(self):
        with pytest.raises(ValidationError, match="scorer_model"):
            RefinementConfig(scorer_model="haikuu")

    def test_max_iterations_bounds(self):
        with pytest.raises(ValidationError):
            RefinementConfig(max_iterations=0)
        with pytest.raises(ValidationError):
            RefinementConfig(max_iterations=6)

    def test_quality_threshold_bounds(self):
        with pytest.raises(ValidationError):
            RefinementConfig(quality_threshold=-0.1)
        with pytest.raises(ValidationError):
            RefinementConfig(quality_threshold=1.1)
