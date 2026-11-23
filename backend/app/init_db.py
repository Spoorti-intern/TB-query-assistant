from app.database import Base, engine
from app.models.connector import Connector
from app.models.chat_session import ChatSession
from app.models.schema_cache import SchemaCache
from app.models.user import User

print("Creating database tables...")

Base.metadata.create_all(bind=engine)

print("Database tables created successfully!")