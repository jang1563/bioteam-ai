"""Conversations CRUD API for Direct Query persistence.

GET    /api/v1/conversations          — List conversations (newest first)
GET    /api/v1/conversations/{id}     — Get conversation with turns
PATCH  /api/v1/conversations/{id}     — Rename conversation
DELETE /api/v1/conversations/{id}     — Delete conversation + turns
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.database import get_session
from app.models.messages import Conversation, ConversationTurn

router = APIRouter(prefix="/api/v1", tags=["conversations"])


# === Response models ===


class ConversationSummary(BaseModel):
    """Lightweight conversation entry for list view."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    total_cost: float
    turn_count: int


class ConversationDetail(BaseModel):
    """Full conversation with all turns."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    total_cost: float
    turn_count: int
    turns: list[TurnDetail]


class TurnDetail(BaseModel):
    """Single turn in a conversation."""

    id: str
    turn_number: int
    query: str
    classification_type: str
    routed_agent: str | None
    answer: str | None
    sources: list[dict] = Field(default_factory=list)
    cost: float
    duration_ms: int
    created_at: datetime


# Fix forward reference
ConversationDetail.model_rebuild()


class ConversationRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


# === Endpoints ===


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> list[ConversationSummary]:
    """List conversations, newest first."""
    stmt = (
        select(Conversation)
        .order_by(Conversation.updated_at.desc())  # type: ignore[union-attr]
        .offset(offset)
        .limit(min(limit, 100))
    )
    conversations = session.exec(stmt).all()
    return [
        ConversationSummary(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            total_cost=c.total_cost,
            turn_count=c.turn_count,
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
) -> ConversationDetail:
    """Get conversation with all turns."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    stmt = (
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.turn_number)  # type: ignore[union-attr]
    )
    turns = session.exec(stmt).all()

    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        total_cost=conversation.total_cost,
        turn_count=conversation.turn_count,
        turns=[
            TurnDetail(
                id=t.id,
                turn_number=t.turn_number,
                query=t.query,
                classification_type=t.classification_type,
                routed_agent=t.routed_agent,
                answer=t.answer,
                sources=t.sources,
                cost=t.cost,
                duration_ms=t.duration_ms,
                created_at=t.created_at,
            )
            for t in turns
        ],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(
    conversation_id: str,
    body: ConversationRenameRequest,
    session: Session = Depends(get_session),
) -> ConversationSummary:
    """Rename a conversation."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.title = body.title
    conversation.updated_at = datetime.now(timezone.utc)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)

    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        total_cost=conversation.total_cost,
        turn_count=conversation.turn_count,
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
) -> None:
    """Delete conversation and all its turns."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Delete turns
    stmt = select(ConversationTurn).where(
        ConversationTurn.conversation_id == conversation_id
    )
    turns = session.exec(stmt).all()
    for turn in turns:
        session.delete(turn)

    session.delete(conversation)
    session.commit()
