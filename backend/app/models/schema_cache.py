import uuid

from sqlalchemy import Column, String, DateTime, JSON, func

from app.database import Base


class SchemaCache(Base):
    __tablename__ = "schema_cache"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    connector_id = Column(String(36), nullable=False, unique=True, index=True)
    table_names = Column(JSON, nullable=True, default=list)
    table_columns = Column(JSON, nullable=True, default=dict)
    tables_with_data = Column(JSON, nullable=True, default=list)
    empty_tables = Column(JSON, nullable=True, default=list)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
