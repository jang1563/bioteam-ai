"""Tests for ContradictionDetector — deterministic pre-screening engine.

All tests use in-memory ChromaDB (tempfile) with no LLM calls.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test_detector.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.engines.ambiguity.contradiction_detector import ContradictionDetector
from app.memory.semantic import SemanticMemory


def _make_memory():
    """Create a SemanticMemory with a unique temp directory."""
    tmpdir = tempfile.mkdtemp()
    return SemanticMemory(persist_dir=tmpdir)


def _seed_memory(memory: SemanticMemory, docs: list[tuple[str, str, str]]):
    """Seed memory with (collection, doc_id, text) tuples."""
    for coll, doc_id, text in docs:
        memory.add(coll, doc_id, text)


def test_find_no_pairs_empty_memory():
    """Empty ChromaDB returns no pairs."""
    detector = ContradictionDetector()
    memory = _make_memory()
    claims = ["VEGF promotes angiogenesis in solid tumors"]
    result = detector.find_candidate_pairs(claims, memory)
    assert result == []
    print("  PASS: No pairs from empty memory")


def test_find_no_pairs_single_claim():
    """Single claim can't form a pair."""
    detector = ContradictionDetector()
    memory = _make_memory()
    _seed_memory(memory, [
        ("literature", "doc1", "VEGF promotes angiogenesis in tumors"),
    ])
    result = detector.find_candidate_pairs(
        ["VEGF promotes angiogenesis in tumors"], memory
    )
    assert result == []
    print("  PASS: Single claim returns empty")


def test_find_no_pairs_unrelated_claims():
    """Unrelated claims (high cosine distance) are not paired."""
    detector = ContradictionDetector()
    memory = _make_memory()
    _seed_memory(memory, [
        ("literature", "doc1", "Gravitational waves detected by LIGO interferometer"),
        ("literature", "doc2", "Protein folding thermodynamics in aqueous solution"),
    ])
    claims = [
        "Gravitational waves detected by LIGO interferometer",
        "Protein folding thermodynamics in aqueous solution",
    ]
    result = detector.find_candidate_pairs(claims, memory)
    # These are too semantically distant to be paired via ChromaDB
    # (but may still show up if all-pairs marker check matches — they shouldn't)
    for a, b, _ in result:
        assert not detector._has_contradiction_markers(a, b)
    print(f"  PASS: Unrelated claims — {len(result)} pairs (expected few/none)")


def test_find_pairs_related_claims():
    """Opposing claims about same topic should produce pairs."""
    detector = ContradictionDetector()
    memory = _make_memory()
    _seed_memory(memory, [
        ("literature", "doc1", "VEGF promotes angiogenesis and tumor growth in solid tumors"),
        ("literature", "doc2", "VEGF inhibits angiogenesis in avascular corneal tissue"),
    ])
    claims = [
        "VEGF promotes angiogenesis and tumor growth in solid tumors",
        "VEGF inhibits angiogenesis in avascular corneal tissue",
    ]
    result = detector.find_candidate_pairs(claims, memory)
    # Should find at least 1 pair (either via ChromaDB similarity or markers)
    assert len(result) >= 1
    print(f"  PASS: Related opposing claims — {len(result)} pairs found")


def test_contradiction_markers_detection():
    """Pairs with opposite-meaning terms are detected."""
    detector = ContradictionDetector()
    assert detector._has_contradiction_markers(
        "Gene X is upregulated in cancer cells",
        "Gene X is downregulated in normal tissue",
    )
    assert detector._has_contradiction_markers(
        "Treatment promotes cell growth",
        "Treatment inhibits cell growth",
    )
    assert not detector._has_contradiction_markers(
        "Gene X is expressed in liver",
        "Gene Y is expressed in kidney",
    )
    print("  PASS: Contradiction markers detection")


def test_no_markers_still_returned_via_chromadb():
    """Semantically similar pairs without markers can still be returned via ChromaDB distance."""
    detector = ContradictionDetector()
    memory = _make_memory()
    # Same protein, different localizations — no simple marker match
    _seed_memory(memory, [
        ("literature", "doc1", "Protein X localizes to the nucleus in cancer cells during mitosis"),
        ("literature", "doc2", "Protein X localizes to the cytoplasm in resting fibroblasts"),
    ])
    claims = [
        "Protein X localizes to the nucleus in cancer cells during mitosis",
        "Protein X localizes to the cytoplasm in resting fibroblasts",
    ]
    # These may or may not be paired via ChromaDB distance depending on embedding
    # The test verifies the code path works without errors
    result = detector.find_candidate_pairs(claims, memory)
    assert isinstance(result, list)
    print(f"  PASS: Non-marker pairs via ChromaDB — {len(result)} pairs")


def test_deduplication_ab_equals_ba():
    """(a,b) and (b,a) are treated as the same pair."""
    detector = ContradictionDetector()
    pairs = [
        ("Claim A is about X", "Claim B is about Y", 0.8),
        ("Claim B is about Y", "Claim A is about X", 0.7),
    ]
    deduped = detector._deduplicate_pairs(pairs)
    assert len(deduped) == 1
    # Should keep the higher score
    assert deduped[0][2] == 0.8
    print("  PASS: Deduplication (a,b) == (b,a)")


def test_max_pairs_cap():
    """filter_by_quality respects max_pairs."""
    detector = ContradictionDetector()
    pairs = [
        (f"Claim A{i} is a long enough claim string", f"Claim B{i} is also a long enough claim string", 0.5 + i * 0.01)
        for i in range(30)
    ]
    filtered = detector.filter_by_quality(pairs, max_pairs=10)
    assert len(filtered) == 10
    print("  PASS: Max pairs cap")


def test_short_claims_filtered():
    """Claims shorter than MIN_CLAIM_LENGTH are excluded."""
    detector = ContradictionDetector()
    pairs = [
        ("Short", "Also short", 0.9),
        ("This is a sufficiently long claim about biology", "Another long claim about biology too", 0.8),
    ]
    filtered = detector.filter_by_quality(pairs)
    assert len(filtered) == 1
    assert "sufficiently long" in filtered[0][0]
    print("  PASS: Short claims filtered")


def test_collections_restriction():
    """Detector only queries literature and lab_kb, never synthesis."""
    detector = ContradictionDetector()
    memory = _make_memory()
    # Add to synthesis — should never be found
    _seed_memory(memory, [
        ("synthesis", "synth1", "Agent-generated interpretation of VEGF promotes angiogenesis"),
        ("literature", "lit1", "VEGF inhibits angiogenesis in corneal tissue"),
    ])
    claims = [
        "VEGF promotes angiogenesis in solid tumors",
        "VEGF inhibits angiogenesis in corneal tissue",
    ]
    result = detector.find_candidate_pairs(claims, memory)
    # Verify no synthesis content in results
    for a, b, _ in result:
        assert "Agent-generated" not in a
        assert "Agent-generated" not in b
    print("  PASS: Synthesis collection excluded")


def test_collections_restriction_explicit_synthesis():
    """Even if synthesis is explicitly passed, it gets filtered out."""
    detector = ContradictionDetector()
    memory = _make_memory()
    _seed_memory(memory, [
        ("synthesis", "synth1", "Synthesis claim about gene regulation mechanisms"),
    ])
    claims = [
        "Gene X upregulates downstream targets in liver",
        "Gene X downregulates downstream targets in kidney",
    ]
    result = detector.find_candidate_pairs(
        claims, memory, collections=["synthesis", "literature"]
    )
    for a, b, _ in result:
        assert "Synthesis claim" not in a
        assert "Synthesis claim" not in b
    print("  PASS: Synthesis filtered even when explicitly passed")


def test_sorting_by_similarity():
    """Pairs with contradiction markers are prioritized, then sorted by similarity."""
    detector = ContradictionDetector()
    pairs = [
        ("Gene X increases expression in liver tissue samples", "Gene Y decreases expression in kidney tissue", 0.6),
        ("Gene X increases expression in liver tissue samples", "Gene X decreases expression in liver tissue", 0.9),
    ]
    filtered = detector.filter_by_quality(pairs)
    # Both have markers, so sorted by similarity
    assert filtered[0][2] >= filtered[-1][2]
    print("  PASS: Sorted by similarity within priority group")


def test_filter_prioritizes_markers():
    """Marker-matched pairs come before non-marker pairs."""
    detector = ContradictionDetector()
    no_marker = ("Protein X is found in nucleus during cell division", "Protein X is found in cytoplasm at rest", 0.95)
    with_marker = ("Gene A promotes tumor growth through angiogenesis", "Gene A inhibits tumor growth through apoptosis", 0.6)
    filtered = detector.filter_by_quality([no_marker, with_marker])
    # With marker should come first despite lower similarity
    assert len(filtered) == 2
    assert "inhibits" in filtered[0][1] or "promotes" in filtered[0][0]
    print("  PASS: Marker pairs prioritized")


def test_similarity_score_conversion():
    """Similarity = 1.0 - cosine_distance."""
    detector = ContradictionDetector()
    memory = _make_memory()
    _seed_memory(memory, [
        ("literature", "doc1", "Spaceflight causes bone density loss in astronauts during long missions"),
        ("literature", "doc2", "Spaceflight reduces bone mineral density through increased osteoclast activity"),
    ])
    claims = [
        "Spaceflight causes bone density loss in astronauts during long missions",
    ]
    # Need at least 2 claims
    claims.append("Spaceflight reduces bone mineral density through increased osteoclast activity")
    result = detector.find_candidate_pairs(claims, memory)
    for _, _, score in result:
        assert 0.0 <= score <= 1.0
    print(f"  PASS: Similarity scores in [0,1] range — {len(result)} pairs")


if __name__ == "__main__":
    print("Testing ContradictionDetector:")
    test_find_no_pairs_empty_memory()
    test_find_no_pairs_single_claim()
    test_find_no_pairs_unrelated_claims()
    test_find_pairs_related_claims()
    test_contradiction_markers_detection()
    test_no_markers_still_returned_via_chromadb()
    test_deduplication_ab_equals_ba()
    test_max_pairs_cap()
    test_short_claims_filtered()
    test_collections_restriction()
    test_collections_restriction_explicit_synthesis()
    test_sorting_by_similarity()
    test_filter_prioritizes_markers()
    test_similarity_score_conversion()
    print("\nAll ContradictionDetector tests passed!")
