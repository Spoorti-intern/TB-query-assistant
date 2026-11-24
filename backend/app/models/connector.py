
import uuid

from sqlalchemy import Column, String, Integer, DateTime, func

from app.database import Base


class Connector(Base):
    __tablename__ = "connectors"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    name = Column(String(100), nullable=False)
    connector_type = Column(String(50), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=True)
    database = Column(String(255), nullable=False)
    username = Column(String(255), nullable=True)
    password = Column(String(500), nullable=True)
    status = Column(String(50), default="configured")
    user_id = Column(String(36), nullable=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
