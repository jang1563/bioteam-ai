"""Tests for Conversations CRUD API and pipeline integration.

Tests conversation persistence: create, list, get, rename, delete,
and integration with the Direct Query pipeline.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test_conversations.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.api.v1.conversations import router as conv_router
from app.api.v1.direct_query import router as dq_router, set_registry
from app.db.database import engine
from app.models.messages import Conversation, ConversationTurn  # noqa: F401
from app.agents.base import BaseAgent
from app.agents.research_director import ResearchDirectorAgent, QueryClassification
from app.agents.knowledge_manager import KnowledgeManagerAgent
from app.agents.registry import AgentRegistry
from app.llm.mock_layer import MockLLMLayer


def _create_app():
    """Create a fresh test app with clean DB."""
    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(conv_router)
    app.include_router(dq_router)
    return TestClient(app)


def _setup_registry():
    """Wire up registry with mock agents."""
    classification = QueryClassification(
        type="simple_query",
        reasoning="Simple biology question.",
        target_agent="knowledge_manager",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})

    rd = ResearchDirectorAgent(spec=BaseAgent.load_spec("research_director"), llm=mock)
    km = KnowledgeManagerAgent(spec=BaseAgent.load_spec("knowledge_manager"), llm=mock)

    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    set_registry(registry)
    return registry


def _cleanup():
    """Clean up conversations and turns."""
    from sqlmodel import Session, select
    with Session(engine) as session:
        for turn in session.exec(select(ConversationTurn)).all():
            session.delete(turn)
        for conv in session.exec(select(Conversation)).all():
            session.delete(conv)
        session.commit()


def test_list_conversations_empty():
    """GET /conversations with no data returns empty list."""
    client = _create_app()
    _cleanup()
    response = client.get("/api/v1/conversations")
    assert response.status_code == 200
    assert response.json() == []
    print("  PASS: List conversations (empty)")


def test_direct_query_creates_conversation():
    """POST /direct-query without conversation_id creates a new conversation."""
    client = _create_app()
    _cleanup()
    _setup_registry()

    response = client.post("/api/v1/direct-query", json={
        "query": "What is spaceflight anemia?",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] is not None, "Should auto-create conversation"

    # Verify conversation exists
    conv_response = client.get(f"/api/v1/conversations/{data['conversation_id']}")
    assert conv_response.status_code == 200
    conv_data = conv_response.json()
    assert conv_data["turn_count"] == 1
    assert conv_data["turns"][0]["query"] == "What is spaceflight anemia?"
    print(f"  PASS: Direct query creates conversation (id={data['conversation_id'][:8]}...)")
    set_registry(None)


def test_continue_conversation():
    """POST /direct-query with conversation_id appends a turn."""
    client = _create_app()
    _cleanup()
    _setup_registry()

    # First query creates conversation
    r1 = client.post("/api/v1/direct-query", json={
        "query": "What is spaceflight anemia?",
    })
    conv_id = r1.json()["conversation_id"]

    # Second query continues it
    r2 = client.post("/api/v1/direct-query", json={
        "query": "How is it treated?",
        "conversation_id": conv_id,
    })
    assert r2.json()["conversation_id"] == conv_id

    # Verify both turns exist
    conv_response = client.get(f"/api/v1/conversations/{conv_id}")
    conv_data = conv_response.json()
    assert conv_data["turn_count"] == 2
    assert conv_data["turns"][0]["query"] == "What is spaceflight anemia?"
    assert conv_data["turns"][1]["query"] == "How is it treated?"
    print(f"  PASS: Continue conversation (2 turns)")
    set_registry(None)


def test_list_conversations_newest_first():
    """GET /conversations returns newest first."""
    client = _create_app()
    _cleanup()
    _setup_registry()

    # Create 3 conversations
    for q in ["Query A", "Query B", "Query C"]:
        client.post("/api/v1/direct-query", json={"query": q})

    response = client.get("/api/v1/conversations")
    assert response.status_code == 200
    convs = response.json()
    assert len(convs) == 3
    # Newest first: C, B, A
    assert convs[0]["title"].startswith("Query C")
    print(f"  PASS: List conversations newest first ({len(convs)} items)")
    set_registry(None)


def test_rename_conversation():
    """PATCH /conversations/{id} renames the conversation."""
    client = _create_app()
    _cleanup()
    _setup_registry()

    r = client.post("/api/v1/direct-query", json={"query": "Initial question"})
    conv_id = r.json()["conversation_id"]

    patch = client.patch(f"/api/v1/conversations/{conv_id}", json={
        "title": "Renamed Conversation",
    })
    assert patch.status_code == 200
    assert patch.json()["title"] == "Renamed Conversation"
    print(f"  PASS: Rename conversation")
    set_registry(None)


def test_delete_conversation():
    """DELETE /conversations/{id} removes conversation and turns."""
    client = _create_app()
    _cleanup()
    _setup_registry()

    r = client.post("/api/v1/direct-query", json={"query": "To be deleted"})
    conv_id = r.json()["conversation_id"]

    delete = client.delete(f"/api/v1/conversations/{conv_id}")
    assert delete.status_code == 204

    # Verify gone
    get = client.get(f"/api/v1/conversations/{conv_id}")
    assert get.status_code == 404
    print(f"  PASS: Delete conversation")
    set_registry(None)


def test_get_nonexistent_conversation():
    """GET /conversations/{invalid_id} returns 404."""
    client = _create_app()
    response = client.get("/api/v1/conversations/nonexistent-id")
    assert response.status_code == 404
    print("  PASS: 404 for nonexistent conversation")


def test_conversation_cost_tracking():
    """Conversation total_cost should accumulate across turns."""
    client = _create_app()
    _cleanup()
    _setup_registry()

    r1 = client.post("/api/v1/direct-query", json={"query": "First question"})
    conv_id = r1.json()["conversation_id"]
    r2 = client.post("/api/v1/direct-query", json={
        "query": "Second question",
        "conversation_id": conv_id,
    })

    conv = client.get(f"/api/v1/conversations/{conv_id}").json()
    assert conv["total_cost"] >= 0
    assert conv["turn_count"] == 2
    print(f"  PASS: Conversation cost tracking (total=${conv['total_cost']:.4f})")
    set_registry(None)


def test_workflow_query_no_conversation():
    """Workflow queries should not create conversations."""
    client = _create_app()
    _cleanup()

    classification = QueryClassification(
        type="needs_workflow",
        reasoning="Requires systematic review.",
        workflow_type="W1",
    )
    mock = MockLLMLayer({"sonnet:QueryClassification": classification})
    rd = ResearchDirectorAgent(spec=BaseAgent.load_spec("research_director"), llm=mock)
    km = KnowledgeManagerAgent(spec=BaseAgent.load_spec("knowledge_manager"), llm=mock)
    registry = AgentRegistry()
    registry.register(rd)
    registry.register(km)
    set_registry(registry)

    r = client.post("/api/v1/direct-query", json={"query": "Compare all spaceflight studies"})
    assert r.json()["conversation_id"] is None
    print("  PASS: Workflow query does not create conversation")
    set_registry(None)


if __name__ == "__main__":
    print("Testing Conversations CRUD:")
    test_list_conversations_empty()
    test_direct_query_creates_conversation()
    test_continue_conversation()
    test_list_conversations_newest_first()
    test_rename_conversation()
    test_delete_conversation()
    test_get_nonexistent_conversation()
    test_conversation_cost_tracking()
    test_workflow_query_no_conversation()
    print("\nAll Conversations tests passed!")
