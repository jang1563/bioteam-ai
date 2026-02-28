"""Tests for /api/v1/analytics endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.v1.analytics import router
from app.db.database import get_session

# Import ALL SQLModel tables so metadata is fully populated before create_all
from app.models.cost import CostRecord  # noqa: F401
from app.models.digest import DigestEntry, DigestReport, TopicProfile  # noqa: F401
from app.models.evidence import ContradictionEntry, DataRegistry, Evidence  # noqa: F401
from app.models.integrity import AuditFinding, AuditRun  # noqa: F401
from app.models.memory import EpisodicEvent  # noqa: F401
from app.models.messages import AgentMessage, Conversation, ConversationTurn  # noqa: F401
from app.models.negative_result import NegativeResult  # noqa: F401
from app.models.session_checkpoint import SessionCheckpoint  # noqa: F401
from app.models.task import Project, Task  # noqa: F401
from app.models.workflow import StepCheckpoint, WorkflowInstance  # noqa: F401

# In-memory SQLite DB for tests — StaticPool keeps the same connection so
# create_all and test sessions share the same in-memory database.
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine)


def override_get_session():
    with Session(_engine) as session:
        yield session


_app = FastAPI()
_app.include_router(router)
_app.dependency_overrides[get_session] = override_get_session


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe tables before each test."""
    with Session(_engine) as session:
        session.execute(CostRecord.__table__.delete())  # type: ignore[attr-defined]
        session.execute(WorkflowInstance.__table__.delete())  # type: ignore[attr-defined]
        session.commit()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app)


def _add_workflow(session: Session, template: str = "W1", state: str = "COMPLETED") -> WorkflowInstance:
    w = WorkflowInstance(template=template, query="test", state=state)
    session.add(w)
    session.commit()
    session.refresh(w)
    return w


def _add_cost(session: Session, workflow_id: str, agent_id: str = "t01", cost: float = 0.5) -> CostRecord:
    r = CostRecord(
        workflow_id=workflow_id,
        agent_id=agent_id,
        model_tier="sonnet",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=cost,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(r)
    session.commit()
    return r


# === /summary ===


class TestSummaryEndpoint:
    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/v1/analytics/summary")
        assert resp.status_code == 200

    def test_empty_db_returns_zeros(self, client: TestClient):
        resp = client.get("/api/v1/analytics/summary")
        data = resp.json()
        assert data["total_workflows"] == 0
        assert data["total_cost_usd"] == 0.0

    def test_counts_workflows(self, client: TestClient):
        with Session(_engine) as session:
            _add_workflow(session, "W1", "COMPLETED")
            _add_workflow(session, "W2", "FAILED")
            _add_workflow(session, "W3", "RUNNING")
        resp = client.get("/api/v1/analytics/summary")
        data = resp.json()
        assert data["total_workflows"] == 3
        assert data["completed_workflows"] == 1
        assert data["failed_workflows"] == 1
        assert data["running_workflows"] == 1

    def test_sums_cost_records(self, client: TestClient):
        with Session(_engine) as session:
            w = _add_workflow(session)
            _add_cost(session, w.id, cost=1.0)
            _add_cost(session, w.id, cost=0.5)
        resp = client.get("/api/v1/analytics/summary")
        data = resp.json()
        assert abs(data["total_cost_usd"] - 1.5) < 0.001

    def test_avg_cost_per_workflow(self, client: TestClient):
        with Session(_engine) as session:
            w = _add_workflow(session, state="COMPLETED")
            _add_cost(session, w.id, cost=2.0)
        resp = client.get("/api/v1/analytics/summary")
        data = resp.json()
        assert abs(data["avg_cost_per_workflow"] - 2.0) < 0.001

    def test_token_counts(self, client: TestClient):
        with Session(_engine) as session:
            w = _add_workflow(session)
            _add_cost(session, w.id)  # 1000 input, 200 output
        resp = client.get("/api/v1/analytics/summary")
        data = resp.json()
        assert data["total_input_tokens"] == 1000
        assert data["total_output_tokens"] == 200


# === /workflows ===


class TestWorkflowBreakdown:
    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/v1/analytics/workflows")
        assert resp.status_code == 200

    def test_by_template_groups_correctly(self, client: TestClient):
        with Session(_engine) as session:
            _add_workflow(session, "W1", "COMPLETED")
            _add_workflow(session, "W1", "FAILED")
            _add_workflow(session, "W2", "COMPLETED")
        resp = client.get("/api/v1/analytics/workflows")
        data = resp.json()
        templates = {t["template"]: t for t in data["by_template"]}
        assert templates["W1"]["total"] == 2
        assert templates["W1"]["completed"] == 1
        assert templates["W1"]["failed"] == 1
        assert templates["W2"]["total"] == 1

    def test_by_state_counts(self, client: TestClient):
        with Session(_engine) as session:
            _add_workflow(session, state="COMPLETED")
            _add_workflow(session, state="RUNNING")
        resp = client.get("/api/v1/analytics/workflows")
        data = resp.json()
        assert data["by_state"]["COMPLETED"] == 1
        assert data["by_state"]["RUNNING"] == 1


# === /cost-by-day ===


class TestCostByDay:
    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/v1/analytics/cost-by-day")
        assert resp.status_code == 200

    def test_default_30_days(self, client: TestClient):
        resp = client.get("/api/v1/analytics/cost-by-day")
        data = resp.json()
        assert data["days"] == 30
        assert len(data["entries"]) == 30

    def test_custom_days_param(self, client: TestClient):
        resp = client.get("/api/v1/analytics/cost-by-day?days=7")
        data = resp.json()
        assert data["days"] == 7
        assert len(data["entries"]) == 7

    def test_entries_have_required_fields(self, client: TestClient):
        resp = client.get("/api/v1/analytics/cost-by-day")
        data = resp.json()
        for entry in data["entries"]:
            assert "date" in entry
            assert "cost_usd" in entry
            assert "workflow_count" in entry

    def test_total_matches_sum_of_entries(self, client: TestClient):
        with Session(_engine) as session:
            w = _add_workflow(session)
            _add_cost(session, w.id, cost=1.0)
        resp = client.get("/api/v1/analytics/cost-by-day?days=30")
        data = resp.json()
        total = round(sum(e["cost_usd"] for e in data["entries"]), 4)
        assert abs(total - data["total_cost_usd"]) < 0.001


# === /agents ===


class TestAgentStats:
    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/v1/analytics/agents")
        assert resp.status_code == 200

    def test_empty_when_no_records(self, client: TestClient):
        resp = client.get("/api/v1/analytics/agents")
        data = resp.json()
        assert data["agents"] == []
        assert data["total_agents_used"] == 0

    def test_aggregates_per_agent(self, client: TestClient):
        with Session(_engine) as session:
            w = _add_workflow(session)
            _add_cost(session, w.id, agent_id="t01", cost=1.0)
            _add_cost(session, w.id, agent_id="t01", cost=0.5)
            _add_cost(session, w.id, agent_id="t02", cost=0.2)
        resp = client.get("/api/v1/analytics/agents")
        data = resp.json()
        agents = {a["agent_id"]: a for a in data["agents"]}
        assert agents["t01"]["call_count"] == 2
        assert abs(agents["t01"]["total_cost_usd"] - 1.5) < 0.001
        assert agents["t02"]["call_count"] == 1
        assert data["total_agents_used"] == 2

    def test_sorted_by_cost_descending(self, client: TestClient):
        with Session(_engine) as session:
            w = _add_workflow(session)
            _add_cost(session, w.id, agent_id="cheap_agent", cost=0.1)
            _add_cost(session, w.id, agent_id="expensive_agent", cost=5.0)
        resp = client.get("/api/v1/analytics/agents")
        data = resp.json()
        costs = [a["total_cost_usd"] for a in data["agents"]]
        assert costs == sorted(costs, reverse=True)
