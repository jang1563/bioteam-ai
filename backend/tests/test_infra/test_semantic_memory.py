"""Tests for SemanticMemory — delete, metadata filtering, search_all, search_literature."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.memory.semantic import SemanticMemory, COLLECTION_NAMES


def _make_memory() -> SemanticMemory:
    """Create a SemanticMemory with a temporary directory."""
    tmpdir = tempfile.mkdtemp()
    return SemanticMemory(persist_dir=tmpdir)


# === Collection Setup ===


def test_collections_created():
    mem = _make_memory()
    for name in COLLECTION_NAMES:
        assert name in mem.collections
    assert len(mem.collections) == 3
    print("  PASS: collections_created")


# === Delete Tests ===


def test_delete_existing():
    mem = _make_memory()
    mem.add("literature", "doi:10.1234/test", "Test paper about anemia.")
    assert mem.count("literature") == 1
    mem.delete("literature", "doi:10.1234/test")
    assert mem.count("literature") == 0
    print("  PASS: delete_existing")


def test_delete_nonexistent():
    """Deleting a non-existent ID should not raise."""
    mem = _make_memory()
    mem.delete("literature", "nonexistent_id")  # No error
    assert mem.count("literature") == 0
    print("  PASS: delete_nonexistent")


def test_delete_from_correct_collection():
    """Deleting from one collection should not affect another."""
    mem = _make_memory()
    mem.add("literature", "doc1", "Paper about spaceflight.")
    mem.add("synthesis", "doc2", "Agent synthesis about spaceflight.")
    mem.delete("literature", "doc1")
    assert mem.count("literature") == 0
    assert mem.count("synthesis") == 1
    print("  PASS: delete_from_correct_collection")


# === Deduplication Tests ===


def test_add_dedup():
    """Adding same ID twice should not create duplicate."""
    mem = _make_memory()
    mem.add("literature", "doi:10.1234/test", "Version 1")
    mem.add("literature", "doi:10.1234/test", "Version 2")
    assert mem.count("literature") == 1
    print("  PASS: add_dedup")


# === Metadata Filtering ===


def test_search_with_where_filter():
    mem = _make_memory()
    mem.add("literature", "doc1", "Spaceflight anemia study in humans.",
            metadata={"organism": "human", "year": 2024})
    mem.add("literature", "doc2", "Mouse model of spaceflight anemia.",
            metadata={"organism": "mouse", "year": 2023})
    mem.add("literature", "doc3", "Another human spaceflight study.",
            metadata={"organism": "human", "year": 2025})

    results = mem.search("literature", "spaceflight anemia", n_results=10,
                         where={"organism": "human"})
    assert len(results) == 2
    ids = [r["id"] for r in results]
    assert "doc1" in ids
    assert "doc3" in ids
    assert "doc2" not in ids
    print("  PASS: search_with_where_filter")


def test_search_no_results():
    mem = _make_memory()
    results = mem.search("literature", "quantum physics", n_results=10)
    assert len(results) == 0
    print("  PASS: search_no_results")


# === search_literature Tests ===


def test_search_literature():
    mem = _make_memory()
    mem.add("literature", "doc1", "Erythropoiesis in microgravity.")
    mem.add("synthesis", "doc2", "Agent analysis of erythropoiesis.")

    results = mem.search_literature("erythropoiesis", n_results=10)
    ids = [r["id"] for r in results]
    assert "doc1" in ids
    # synthesis collection is NOT searched
    assert "doc2" not in ids
    print("  PASS: search_literature")


# === search_all Tests ===


def test_search_all_default():
    mem = _make_memory()
    mem.add("literature", "lit1", "Spaceflight-induced bone loss study.")
    mem.add("synthesis", "syn1", "Synthesis of bone loss mechanisms.")
    mem.add("lab_kb", "lab1", "Our lab found no bone loss in short flights.")

    results = mem.search_all("bone loss", n_results=10)
    ids = [r["id"] for r in results]
    assert "lit1" in ids
    assert "syn1" in ids
    assert "lab1" in ids
    # Each result should have a "collection" field
    for r in results:
        assert "collection" in r
    print("  PASS: search_all_default")


def test_search_all_specific_collections():
    mem = _make_memory()
    mem.add("literature", "lit1", "Paper about anemia.")
    mem.add("synthesis", "syn1", "Synthesis about anemia.")
    mem.add("lab_kb", "lab1", "Lab note about anemia.")

    results = mem.search_all("anemia", n_results=10, collections=["literature", "lab_kb"])
    ids = [r["id"] for r in results]
    assert "lit1" in ids
    assert "lab1" in ids
    assert "syn1" not in ids
    print("  PASS: search_all_specific_collections")


def test_search_all_sorted_by_distance():
    """Results should be sorted by distance (closest first)."""
    mem = _make_memory()
    mem.add("literature", "doc1", "Spaceflight radiation effects on DNA repair.")
    mem.add("synthesis", "doc2", "Complete analysis of DNA repair mechanisms in space.")
    mem.add("lab_kb", "doc3", "Lab protocol for cell culture.")

    results = mem.search_all("DNA repair in spaceflight", n_results=10)
    # Results should be sorted by distance ascending
    distances = [r.get("distance", 999.0) for r in results]
    assert distances == sorted(distances)
    print("  PASS: search_all_sorted_by_distance")


def test_search_all_invalid_collection_ignored():
    """Invalid collection names should be silently ignored."""
    mem = _make_memory()
    mem.add("literature", "doc1", "Test paper.")
    results = mem.search_all("test", collections=["literature", "nonexistent"])
    assert len(results) >= 1
    print("  PASS: search_all_invalid_collection_ignored")


# === Count Tests ===


def test_count_empty():
    mem = _make_memory()
    assert mem.count("literature") == 0
    assert mem.count("synthesis") == 0
    assert mem.count("lab_kb") == 0
    print("  PASS: count_empty")


def test_count_after_add():
    mem = _make_memory()
    mem.add("literature", "doc1", "Paper 1")
    mem.add("literature", "doc2", "Paper 2")
    mem.add("synthesis", "syn1", "Synthesis 1")
    assert mem.count("literature") == 2
    assert mem.count("synthesis") == 1
    assert mem.count("lab_kb") == 0
    print("  PASS: count_after_add")


# === Search Result Structure ===


def test_search_result_structure():
    mem = _make_memory()
    mem.add("literature", "doi:test", "A study about erythropoiesis.",
            metadata={"organism": "human"})
    results = mem.search("literature", "erythropoiesis")
    assert len(results) == 1
    r = results[0]
    assert r["id"] == "doi:test"
    assert "erythropoiesis" in r["text"]
    assert r["metadata"]["organism"] == "human"
    assert "distance" in r
    assert isinstance(r["distance"], float)
    print("  PASS: search_result_structure")


if __name__ == "__main__":
    print("Testing SemanticMemory:")
    test_collections_created()
    # Delete
    test_delete_existing()
    test_delete_nonexistent()
    test_delete_from_correct_collection()
    # Dedup
    test_add_dedup()
    # Metadata filtering
    test_search_with_where_filter()
    test_search_no_results()
    # search_literature
    test_search_literature()
    # search_all
    test_search_all_default()
    test_search_all_specific_collections()
    test_search_all_sorted_by_distance()
    test_search_all_invalid_collection_ignored()
    # Count
    test_count_empty()
    test_count_after_add()
    # Structure
    test_search_result_structure()
    print("\nAll SemanticMemory tests passed!")
