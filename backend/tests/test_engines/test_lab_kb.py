"""Tests for LabKBEngine — CRUD, search, verification."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from sqlmodel import SQLModel, Session, create_engine

from app.engines.negative_results.lab_kb import LabKBEngine
from app.models.negative_result import NegativeResult


def _make_engine():
    """Create an in-memory SQLite engine with tables."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _make_kb():
    """Create a LabKBEngine with in-memory SQLite session."""
    engine = _make_engine()
    session = Session(engine)
    return LabKBEngine(session)


# === Create Tests ===


def test_create_entry():
    kb = _make_kb()
    entry = kb.create(
        claim="TNFSF11 upregulated in spaceflight blood samples",
        outcome="No significant change observed (p=0.45)",
        organism="human",
        source="internal",
        confidence=0.3,
        failure_category="biological",
        implications=["May be tissue-specific, not systemic"],
    )
    assert entry.id is not None
    assert entry.claim == "TNFSF11 upregulated in spaceflight blood samples"
    assert entry.outcome == "No significant change observed (p=0.45)"
    assert entry.organism == "human"
    assert entry.confidence == 0.3
    assert entry.failure_category == "biological"
    assert len(entry.implications) == 1
    print("  PASS: create_entry")


# === Get Tests ===


def test_get_existing():
    kb = _make_kb()
    entry = kb.create(claim="Test claim", outcome="Test outcome")
    fetched = kb.get(entry.id)
    assert fetched is not None
    assert fetched.claim == "Test claim"
    print("  PASS: get_existing")


def test_get_nonexistent():
    kb = _make_kb()
    assert kb.get("nonexistent_id") is None
    print("  PASS: get_nonexistent")


# === List Tests ===


def test_list_all():
    kb = _make_kb()
    kb.create(claim="Claim 1", outcome="Outcome 1")
    kb.create(claim="Claim 2", outcome="Outcome 2")
    kb.create(claim="Claim 3", outcome="Outcome 3")
    all_entries = kb.list_all()
    assert len(all_entries) == 3
    print("  PASS: list_all")


# === Update Tests ===


def test_update_entry():
    kb = _make_kb()
    entry = kb.create(claim="Original claim", outcome="Original outcome")
    updated = kb.update(entry.id, claim="Updated claim", confidence=0.9)
    assert updated is not None
    assert updated.claim == "Updated claim"
    assert updated.confidence == 0.9
    assert updated.outcome == "Original outcome"  # Unchanged
    print("  PASS: update_entry")


# === Delete Tests ===


def test_delete_entry():
    kb = _make_kb()
    entry = kb.create(claim="To be deleted", outcome="Outcome")
    assert kb.delete(entry.id) is True
    assert kb.get(entry.id) is None
    print("  PASS: delete_entry")


def test_delete_nonexistent():
    kb = _make_kb()
    assert kb.delete("nonexistent_id") is False
    print("  PASS: delete_nonexistent")


# === Search Tests ===


def test_search_by_text():
    kb = _make_kb()
    kb.create(claim="Spaceflight anemia in mice", outcome="No hemolysis detected")
    kb.create(claim="Radiation damage to DNA", outcome="Significant strand breaks")
    kb.create(claim="Anemia recovery post-flight", outcome="Hemoglobin normalized in 30 days")

    results = kb.search("anemia")
    assert len(results) == 2
    claims = [r.claim for r in results]
    assert "Spaceflight anemia in mice" in claims
    assert "Anemia recovery post-flight" in claims
    print("  PASS: search_by_text")


def test_search_by_organism():
    kb = _make_kb()
    kb.create(claim="Human anemia", outcome="Observed", organism="human")
    kb.create(claim="Mouse anemia", outcome="Observed", organism="mouse")
    kb.create(claim="Rat anemia", outcome="Not observed", organism="rat")

    results = kb.search_by_organism("human")
    assert len(results) == 1
    assert results[0].organism == "human"
    print("  PASS: search_by_organism")


def test_search_by_category():
    kb = _make_kb()
    kb.create(claim="Claim A", outcome="Failed", failure_category="protocol")
    kb.create(claim="Claim B", outcome="Failed", failure_category="biological")
    kb.create(claim="Claim C", outcome="Failed", failure_category="protocol")

    results = kb.search_by_category("protocol")
    assert len(results) == 2
    print("  PASS: search_by_category")


# === Verify Tests ===


def test_verify_entry():
    kb = _make_kb()
    entry = kb.create(claim="Test claim", outcome="Test outcome")
    assert entry.verification_status == "unverified"

    verified = kb.verify(entry.id, verified_by="dr_smith", status="confirmed")
    assert verified is not None
    assert verified.verified_by == "dr_smith"
    assert verified.verification_status == "confirmed"
    print("  PASS: verify_entry")


if __name__ == "__main__":
    print("Testing Lab KB Engine:")
    test_create_entry()
    test_get_existing()
    test_get_nonexistent()
    test_list_all()
    test_update_entry()
    test_delete_entry()
    test_delete_nonexistent()
    test_search_by_text()
    test_search_by_organism()
    test_search_by_category()
    test_verify_entry()
    print("\nAll Lab KB Engine tests passed!")
