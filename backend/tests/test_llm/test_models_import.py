"""Test that all models import correctly and SQL tables can be created."""

import os
import sys
import tempfile

# Set up paths and env
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["ANTHROPIC_API_KEY"] = "test"


def test_all_imports():
    print("All model imports OK")


def test_create_tables():
    from app.db.database import create_db_and_tables

    # Import all SQL models so SQLModel metadata knows about them

    create_db_and_tables()
    print("All SQL tables created OK")


def test_rcmxt_composite():
    from app.models.evidence import RCMXTScore

    # With X
    score = RCMXTScore(claim="test", R=0.8, C=0.7, M=0.9, X=0.6, T=0.75)
    score.compute_composite()
    assert score.composite is not None
    assert abs(score.composite - 0.75) < 0.01

    # Without X (NULL)
    score2 = RCMXTScore(claim="test", R=0.8, C=0.7, M=0.9, T=0.75)
    score2.compute_composite()
    assert score2.composite is not None
    assert abs(score2.composite - 0.7875) < 0.01
    print("RCMXT composite OK")


if __name__ == "__main__":
    test_all_imports()
    test_create_tables()
    test_rcmxt_composite()
    print("\nAll tests passed!")
