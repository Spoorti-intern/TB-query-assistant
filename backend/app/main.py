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

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

app = FastAPI(
    title="TB Query Assistant API",
    description="Backend API for the TB Query Assistant",
    version="1.2.0"
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
        "message": "Welcome to TB Query Assistant API"
    }


# HEALTH CHECK
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "application": "TB Query Assistant"
    }