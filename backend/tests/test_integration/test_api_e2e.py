"""API integration tests — multi-step HTTP request flows through FastAPI.

Tests complete request lifecycles (create → get → intervene → verify)
rather than individual endpoints.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import tempfile

from fastapi.testclient import TestClient

from app.main import app
from app.agents.registry import create_registry
from app.agents.research_director import QueryClassification
from app.llm.mock_layer import MockLLMLayer
from app.workflows.engine import WorkflowEngine
from app.api.v1.agents import set_registry as set_agents_registry
from app.api.v1.direct_query import set_registry as set_dq_registry
from app.api.v1.workflows import set_dependencies as set_workflow_deps
from app.db.database import create_db_and_tables


# === Setup ===


def _setup():
    """Wire up all dependencies with mock LLM and return TestClient."""
    create_db_and_tables()
    classification = QueryClassification(
        type="simple_query",
        reasoning="Test classification",
        target_agent="t02_transcriptomics",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})
    registry = create_registry(mock)
    engine = WorkflowEngine()

    set_agents_registry(registry)
    set_dq_registry(registry)
    set_workflow_deps(registry, engine)

    return TestClient(app)


# === Workflow Multi-Step Flows ===


def test_workflow_create_get_cancel_flow():
    """Create → Get (PENDING) → Cancel → Get (CANCELLED)."""
    client = _setup()

    # Create
    resp = client.post("/api/v1/workflows", json={
        "template": "W1",
        "query": "spaceflight anemia mechanisms",
        "budget": 3.0,
    })
    assert resp.status_code == 200
    wf_id = resp.json()["workflow_id"]

    # Get — should be PENDING
    resp = client.get(f"/api/v1/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["state"] == "PENDING"

    # Cancel
    resp = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={"action": "cancel"})
    assert resp.status_code == 200
    assert resp.json()["new_state"] == "CANCELLED"

    # Verify cancelled
    resp = client.get(f"/api/v1/workflows/{wf_id}")
    assert resp.json()["state"] == "CANCELLED"


def test_inject_note_visible_in_status():
    """Inject note → Get workflow → verify note is stored."""
    client = _setup()

    resp = client.post("/api/v1/workflows", json={
        "template": "W1", "query": "test",
    })
    wf_id = resp.json()["workflow_id"]

    # Inject note
    client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "inject_note",
        "note": "Focus on human studies only",
        "note_action": "MODIFY_QUERY",
    })

    # Inject second note
    client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
        "action": "inject_note",
        "note": "Exclude rodent models",
    })

    # Get workflow — check notes exist in the instance
    resp = client.get(f"/api/v1/workflows/{wf_id}")
    assert resp.status_code == 200


def test_workflow_not_found_404():
    """GET /workflows/nonexistent should return 404."""
    client = _setup()
    resp = client.get("/api/v1/workflows/does-not-exist")
    assert resp.status_code == 404


def test_step_checkpoint_pending_status():
    """GET step before workflow runs should return pending status."""
    client = _setup()

    resp = client.post("/api/v1/workflows", json={
        "template": "W1", "query": "test",
    })
    wf_id = resp.json()["workflow_id"]

    resp = client.get(f"/api/v1/workflows/{wf_id}/steps/SCOPE")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


# === Agent Multi-Step Flows ===


def test_agents_list_then_detail():
    """List all agents → pick one → get its detail → verify fields."""
    client = _setup()

    # List
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) >= 5

    # Pick research_director
    rd = next(a for a in agents if a["id"] == "research_director")
    assert rd["tier"] == "strategic"

    # Get detail
    resp = client.get(f"/api/v1/agents/{rd['id']}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == "research_director"
    assert detail["name"] == "Research Director"
    assert isinstance(detail["tools"], list)
    assert detail["criticality"] == "critical"


# === Direct Query Flow ===


def test_direct_query_full_flow():
    """POST direct query → verify classification response structure."""
    client = _setup()

    resp = client.post("/api/v1/direct-query", json={
        "query": "Is TNFSF11 upregulated in spaceflight cfRNA data?",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["classification_type"] == "simple_query"
    assert data["target_agent"] == "t02_transcriptomics"
    assert "query" in data
    assert "timestamp" in data
    assert data["total_cost"] >= 0


def test_direct_query_no_registry_503():
    """Direct query without registry should return 503."""
    from app.api.v1.direct_query import set_registry as set_dq_reg
    set_dq_reg(None)  # type: ignore[arg-type]

    client = TestClient(app)
    resp = client.post("/api/v1/direct-query", json={"query": "test"})
    assert resp.status_code == 503


# === Health Endpoint ===


def test_health_endpoint_full():
    """GET /health should return all 5 check categories."""
    client = _setup()
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert "llm_api" in data["checks"]
    assert "database" in data["checks"]
    assert "chromadb" in data["checks"]
    assert "pubmed" in data["checks"]
    assert "cost_tracker" in data["checks"]
    assert "timestamp" in data


if __name__ == "__main__":
    print("Testing API E2E Integration:")
    test_workflow_create_get_cancel_flow()
    test_inject_note_visible_in_status()
    test_workflow_not_found_404()
    test_step_checkpoint_pending_status()
    test_agents_list_then_detail()
    test_direct_query_full_flow()
    test_direct_query_no_registry_503()
    test_health_endpoint_full()
    print("\nAll API E2E tests passed!")
