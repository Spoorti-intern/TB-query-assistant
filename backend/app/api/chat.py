import os
import re
import json
import logging
from urllib.parse import urlparse, parse_qs, unquote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from dotenv import load_dotenv
from pathlib import Path
from app.core.llm_client import get_llm_client

from app.database import get_db
from app.models.connector import Connector
from app.core.connector_manager import get_connector_engine
from app.core.crypto import encrypt_password

logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_PATH)

router = APIRouter(
    prefix="/api/chat",
    tags=["Smart Chat"]
)

AI_MODEL = "openai/gpt-oss-20b"

# --------------------------------------------------
# CONNECTION STRING PATTERNS
# --------------------------------------------------

CONNECTION_STRING_PATTERNS = [
    # postgresql://user:pass@host:port/db
    r"^postgres(?:ql)?(?:\+\w+)?://",
    # mysql://user:pass@host:port/db
    r"^mysql(?:\+\w+)?://",
    # mongodb://user:pass@host:port/db or mongodb+srv://
    r"^mongodb(?:\+srv)?://",
    # supabase URLs (pooler or direct)
    r"^postgres(?:ql)?(?:\+\w+)?://postgres\.\w+.*supabase",
]


class ChatRequest(BaseModel):
    message: str
    connector_id: Optional[str] = None


# --------------------------------------------------
# DETECT INPUT TYPE
# --------------------------------------------------

def detect_input_type(message: str) -> str:
    """Classify user input as: connection_string, db_question, or general_chat."""
    stripped = message.strip()

    # Check for connection string
    for pattern in CONNECTION_STRING_PATTERNS:
        if re.match(pattern, stripped, re.IGNORECASE):
            return "connection_string"

    # Also catch partial connection-like strings
    if re.match(r"^(postgres|mysql|mongodb|supabase)(\+\w+)?://", stripped, re.IGNORECASE):
        return "connection_string"

    return "unknown"  # Will be classified by AI


def classify_with_ai(message: str, has_connector: bool) -> str:
    """Use AI to classify ambiguous messages."""
    client = get_llm_client()

    prompt = f"""Classify the following user message into exactly one category.
Reply with ONLY the category name, nothing else.

Categories:
- "db_question" — the user is asking about data in a database (e.g. "show all users", "how many orders", "list tables", "what columns does X have", "count records", "show me the sales data")
- "general_chat" — anything else: greetings, general knowledge questions, personal questions, off-topic chat (e.g. "hello", "who are you", "what is AI", "tell me a joke", "who is Elon Musk")

User message: "{message}"
Has database selected: {has_connector}

Category:"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4.1-mini-fast",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20
        )
        result = response.choices[0].message.content.strip().lower().strip('"\'')
        if "db" in result or "database" in result or "query" in result:
            return "db_question"
        return "general_chat"
    except Exception:
        # Default: if connector is selected, assume DB question
        return "db_question" if has_connector else "general_chat"


# --------------------------------------------------
# PARSE CONNECTION STRING
# --------------------------------------------------

def parse_connection_string(conn_str: str) -> dict:
    """Parse a database connection string into components."""
    conn_str = conn_str.strip()

    # Detect type
    if re.match(r"^mongodb(\+srv)?://", conn_str, re.IGNORECASE):
        db_type = "mongodb"
    elif "supabase" in conn_str.lower():
        db_type = "supabase"
    elif re.match(r"^mysql", conn_str, re.IGNORECASE):
        db_type = "mysql"
    else:
        db_type = "postgresql"

    # Normalize driver prefix for URL parsing
    normalized = re.sub(
        r"^(postgres(?:ql)?|mysql|mongodb)(\+\w+)?://",
        "scheme://",
        conn_str,
        flags=re.IGNORECASE
    )

    try:
        parsed = urlparse(normalized)
        host = parsed.hostname or ""
        port = parsed.port
        username = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        database = parsed.path.lstrip("/") or "postgres"

        # Handle query params (like sslmode)
        params = parse_qs(parsed.query)

        # Default ports
        if not port:
            if db_type == "mongodb":
                port = 27017
            elif db_type == "mysql":
                port = 3306
            else:
                port = 5432

        return {
            "connector_type": db_type,
            "host": host,
            "port": port,
            "database": database,
            "username": username,
            "password": password,
            "params": params
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse connection string: {str(e)}"
        )


# --------------------------------------------------
# AUTO-CONNECT FROM CONNECTION STRING
# --------------------------------------------------

def auto_connect(parsed: dict, db: Session) -> dict:
    """Create a connector from parsed connection string, test it, and return info."""
    # Generate a name from host
    host_short = parsed["host"].split(".")[0] if parsed["host"] else "database"
    name = f"{parsed['connector_type'].title()} - {host_short}"

    # Check if a connector with same host+port+database already exists
    existing = db.query(Connector).filter(
        Connector.host == parsed["host"],
        Connector.port == parsed["port"],
        Connector.database == parsed["database"]
    ).first()

    if existing:
        return {
            "action": "existing_connector",
            "connector_id": existing.id,
            "connector_name": existing.name,
            "connector_type": existing.connector_type,
            "status": existing.status,
            "message": f"This database is already connected as '{existing.name}'."
        }

    # Create new connector
    encrypted_pw = encrypt_password(parsed["password"]) if parsed["password"] else None

    new_connector = Connector(
        name=name,
        connector_type=parsed["connector_type"],
        host=parsed["host"],
        port=parsed["port"],
        database=parsed["database"],
        username=parsed["username"],
        password=encrypted_pw,
        status="configured"
    )

    try:
        db.add(new_connector)
        db.commit()
        db.refresh(new_connector)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save connector.")

    # Try to test the connection
    test_result = None
    try:
        if parsed["connector_type"] == "mongodb":
            from app.core.mongodb_adapter import test_mongodb_connection
            test_result = test_mongodb_connection(new_connector)
            new_connector.status = "connected"
        else:
            from sqlalchemy import text as sql_text
            engine = get_connector_engine(new_connector)
            try:
                with engine.connect() as conn:
                    if parsed["connector_type"] in ("postgresql", "supabase"):
                        result = conn.execute(sql_text("SELECT current_database(), current_user")).fetchone()
                    else:
                        result = conn.execute(sql_text("SELECT DATABASE(), CURRENT_USER()")).fetchone()
                    test_result = {"database": result[0], "user": result[1]}
                    new_connector.status = "connected"
            finally:
                engine.dispose()

        db.commit()

    except Exception as e:
        new_connector.status = "connection_failed"
        db.commit()
        return {
            "action": "connection_failed",
            "connector_id": new_connector.id,
            "connector_name": name,
            "error": str(e),
            "message": f"Connector '{name}' was saved but connection failed: {str(e)}. Check your credentials and try testing it from the Connectors page."
        }

    # Skip schema discovery here — it's slow and causes timeouts.
    # Users can discover schema from the Connectors page or by asking questions.
    return {
        "action": "connected",
        "connector_id": new_connector.id,
        "connector_name": name,
        "connector_type": parsed["connector_type"],
        "status": "connected",
        "database": parsed["database"],
        "table_count": 0,
        "tables": [],
        "message": (
            f"Connected to {parsed['connector_type'].upper()} database '{parsed['database']}' "
            f"on {parsed['host']}. Select this database and ask questions about your data!"
        )
    }


# --------------------------------------------------
# GENERAL AI CHAT (NO DATABASE)
# --------------------------------------------------

def general_chat_response(message: str) -> str:
    """Generate a conversational AI response for non-database questions."""
    client = get_llm_client()

    system_prompt = """You are Query Ops, an AI-powered database query assistant.
You help users connect databases (PostgreSQL, MySQL, MongoDB, Supabase) and query them using natural language.

When users ask general questions (not about databases), respond helpfully and naturally.
Keep responses concise and friendly.

If the question is about you, explain that you're a database query assistant that can:
- Connect to PostgreSQL, MySQL, MongoDB, and Supabase databases
- Convert natural language questions into SQL/MongoDB queries
- Execute queries and explain results in plain English
- Auto-detect database connection strings pasted in the chat

If the user seems to want to work with data, guide them to:
1. Add a database connector on the Connectors page
2. Or paste a connection string directly in the chat
3. Then ask questions about their data

Always be helpful and conversational."""

    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.7,
            max_tokens=500
        )
        answer = response.choices[0].message.content
        return answer.strip() if answer else "I'm here to help you query your databases! Try asking a question about your data."
    except Exception:
        return "I'm Query Ops — I help you query databases. Connect a database and ask me anything about your data!"


# --------------------------------------------------
# SMART CHAT ENDPOINT
# --------------------------------------------------

@router.post("/")
def smart_chat(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Step 1: Detect input type
    input_type = detect_input_type(message)

    # Step 2: Handle connection strings
    if input_type == "connection_string":
        parsed = parse_connection_string(message)
        result = auto_connect(parsed, db)
        return {
            "type": "connection",
            "response": result["message"],
            **result
        }

    # Step 3: Classify ambiguous input with AI
    has_connector = bool(request.connector_id)
    if input_type == "unknown":
        input_type = classify_with_ai(message, has_connector)

    # Step 4: Handle general chat
    if input_type == "general_chat" or not has_connector:
        if not has_connector and input_type == "db_question":
            return {
                "type": "general",
                "response": "Please select a connected database first, or paste a connection string to auto-connect. You can add databases from the Connectors page."
            }
        response = general_chat_response(message)
        return {
            "type": "general",
            "response": response
        }

    # Step 5: Database question — route to existing pipeline
    # We return a signal so the frontend knows to call the existing ask endpoint
    return {
        "type": "db_question",
        "response": None,
        "connector_id": request.connector_id
    }
