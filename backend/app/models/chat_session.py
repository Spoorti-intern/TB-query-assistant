import uuid

from sqlalchemy import Column, String, DateTime, JSON, func

from app.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    title = Column(String(200), nullable=False, default="New Chat")
    connector_id = Column(String(36), nullable=True)
    user_id = Column(String(36), nullable=True, index=True)
    messages = Column(JSON, nullable=True, default=list)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
