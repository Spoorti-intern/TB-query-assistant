import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.api.connectors import router as connectors_router
from app.api.queries import router as queries_router
from app.api.mongodb_queries import router as mongodb_queries_router
from app.api.chat import router as chat_router
from app.api.agent import router as agent_router
from app.api.chat_sessions import router as sessions_router
from app.api.auth import router as auth_router
from app.api.payments import router as payments_router
from app.api.admin import router as admin_router
from app.database import Base, engine
from app.models.user import User, Payment, OTPCode  # noqa: F401
from sqlalchemy import text, inspect as sa_inspect

load_dotenv()

# Auto-create tables on startup
Base.metadata.create_all(bind=engine)

# Migrate: add user_id column to existing tables if missing
def _run_migrations():
    inspector = sa_inspect(engine)
    migrations = [
        ("connectors", "user_id", "VARCHAR(36)"),
        ("chat_sessions", "user_id", "VARCHAR(36)"),
    ]
    with engine.begin() as conn:
        for table, col, col_type in migrations:
            if table in inspector.get_table_names():
                existing_cols = [c["name"] for c in inspector.get_columns(table)]
                if col not in existing_cols:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}'))
                    logging.info("Migration: added %s to %s", col, table)

try:
    _run_migrations()
except Exception as e:
    logging.warning("Migration skipped: %s", e)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

app = FastAPI(
    title="Query Ops API",
    description="Backend API for Query Ops",
    version="1.3.0"
)

# CORS CONFIGURATION
cors_origins = os.getenv("CORS_ORIGINS", "").split(",")
cors_origins = [o.strip() for o in cors_origins if o.strip()]

if not cors_origins:
    cors_origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# REGISTER API ROUTERS
app.include_router(auth_router)
app.include_router(payments_router)
app.include_router(admin_router)
app.include_router(connectors_router)
app.include_router(queries_router)
app.include_router(mongodb_queries_router)
app.include_router(chat_router)
app.include_router(agent_router)
app.include_router(sessions_router)


# ROOT ENDPOINT
@app.get("/")
async def root():
    return {
        "message": "Welcome to Query Ops API"
    }


# HEALTH CHECK
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "application": "Query Ops"
    }