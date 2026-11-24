"""
Chat session CRUD endpoints.
Stores conversation history for sidebar display and session persistence.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.chat_session import ChatSession
from app.models.user import User
from app.core.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = "New Chat"
    connector_id: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    connector_id: str | None = None
    messages: list | None = None


@router.get("/")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == str(current_user.id))
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
        .all()
    )
    return [_serialize(s) for s in sessions]


@router.post("/")
def create_session(
    data: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatSession(
        title=data.title,
        connector_id=data.connector_id,
        messages=[],
        user_id=str(current_user.id),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _serialize(session)


@router.get("/{session_id}")
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == str(current_user.id),
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize(session)


@router.put("/{session_id}")
def update_session(
    session_id: str,
    data: SessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == str(current_user.id),
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if data.title is not None:
        session.title = data.title
    if data.connector_id is not None:
        session.connector_id = data.connector_id
    if data.messages is not None:
        session.messages = data.messages

    db.commit()
    db.refresh(session)
    return _serialize(session)


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == str(current_user.id),
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(session)
    db.commit()
    return {"deleted": True}


class GenerateTitleRequest(BaseModel):
    messages: list


@router.post("/{session_id}/generate-title")
def generate_title(
    session_id: str,
    data: GenerateTitleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a short, descriptive title for a session based on its messages."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == str(current_user.id),
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Extract user messages for title generation
    user_msgs = [m.get("content", "") for m in (data.messages or []) if m.get("role") == "user" and m.get("content")]
    if not user_msgs:
        return _serialize(session)

    # Try LLM-based title generation
    title = _generate_title_llm(user_msgs)
    if not title:
        # Fallback: use first message, truncated
        title = user_msgs[0][:40] + ("..." if len(user_msgs[0]) > 40 else "")

    session.title = title
    db.commit()
    db.refresh(session)
    return _serialize(session)


def _generate_title_llm(user_messages: list[str]) -> str | None:
    """Use LLM to generate a concise session title."""
    try:
        from app.core.llm_client import get_llm_client
        client = get_llm_client(max_retries=0)

        combined = "\n".join(user_messages[:3])  # First 3 messages
        resp = client.chat.completions.create(
            model="openai/gpt-4.1-mini-fast",
            max_tokens=30,
            temperature=0,
            messages=[{
                "role": "user",
                "content": (
                    f"Generate a short title (3-6 words, no quotes) for this chat session:\n\n{combined}\n\n"
                    "Title:"
                ),
            }],
        )
        title = (resp.choices[0].message.content or "").strip()
        # Clean up: remove quotes, limit length
        title = re.sub(r"<think>[\s\S]*?</think>", "", title).strip()
        title = re.sub(r"<think>[\s\S]*$", "", title).strip()
        title = title.strip('"\'').strip()
        if len(title) > 60:
            title = title[:57] + "..."
        return title if title else None
    except Exception as e:
        logger.warning("Title generation failed: %s", e)
        return None


def _serialize(s: ChatSession) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "connector_id": s.connector_id,
        "messages": s.messages or [],
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
