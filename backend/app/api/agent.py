"""
Unified AI Agent endpoint.

Every user message enters here. The LLM decides what to do:
  • general conversation  → reply directly
  • connection string     → call connect_database tool
  • schema question       → call discover_schema tool
  • data question         → call query_database tool
  • multi-step            → chain multiple tools

Responses are streamed as Server-Sent Events (SSE).
Uses async generator with keepalive heartbeats to prevent
browser timeouts during long tool calls.
"""

import asyncio
import json
import logging
import os
import re
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.core.llm_client import get_llm_client
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.connector import Connector

# ──────────────────────────────────────────────
# PERSISTENT SCHEMA CACHE  (survives restarts)
# ──────────────────────────────────────────────
# L1 = in-memory dict (fast), L2 = PostgreSQL (persistent).
# On startup, L1 is empty; first access per connector loads from DB.
# Every update writes to both L1 and L2.
_SCHEMA_CACHE: dict[str, dict] = {}


def _load_cache_from_db(connector_id: str) -> dict:
    """Load schema cache from database into memory."""
    try:
        from app.database import SessionLocal
        from app.models.schema_cache import SchemaCache
        db = SessionLocal()
        try:
            row = db.query(SchemaCache).filter(SchemaCache.connector_id == connector_id).first()
            if row:
                return {
                    "table_names": row.table_names or [],
                    "table_columns": row.table_columns or {},
                    "tables_with_data": set(row.tables_with_data or []),
                    "empty_tables": set(row.empty_tables or []),
                }
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to load schema cache from DB: %s", e)
    return None


def _save_cache_to_db(connector_id: str, cache: dict):
    """Persist schema cache to database (non-blocking best-effort)."""
    try:
        from app.database import SessionLocal
        from app.models.schema_cache import SchemaCache
        db = SessionLocal()
        try:
            row = db.query(SchemaCache).filter(SchemaCache.connector_id == connector_id).first()
            data = {
                "table_names": cache.get("table_names", []),
                "table_columns": cache.get("table_columns", {}),
                "tables_with_data": list(cache.get("tables_with_data", set())),
                "empty_tables": list(cache.get("empty_tables", set())),
            }
            if row:
                row.table_names = data["table_names"]
                row.table_columns = data["table_columns"]
                row.tables_with_data = data["tables_with_data"]
                row.empty_tables = data["empty_tables"]
            else:
                row = SchemaCache(connector_id=connector_id, **data)
                db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to save schema cache to DB: %s", e)


def _get_cache(connector_id: str) -> dict:
    """Get cache for a connector — loads from DB on first access."""
    if connector_id not in _SCHEMA_CACHE:
        db_cache = _load_cache_from_db(connector_id)
        if db_cache:
            _SCHEMA_CACHE[connector_id] = db_cache
        else:
            _SCHEMA_CACHE[connector_id] = {
                "table_names": [],
                "table_columns": {},
                "tables_with_data": set(),
                "empty_tables": set(),
            }
    return _SCHEMA_CACHE[connector_id]


def _update_schema_cache(connector_id: str, result: dict):
    """Update the schema cache from a discover_schema or query_database result."""
    if not connector_id:
        return
    cache = _get_cache(connector_id)

    # From discover_schema
    if "table_names" in result:
        cache["table_names"] = result["table_names"]
    elif "tables" in result and isinstance(result["tables"], dict):
        cache["table_names"] = list(result["tables"].keys())
        for tbl, info in result["tables"].items():
            if isinstance(info, dict) and "columns" in info:
                cache["table_columns"][tbl] = [
                    c.get("name", c) if isinstance(c, dict) else str(c)
                    for c in info["columns"]
                ]
    elif "tables" in result and isinstance(result["tables"], list):
        cache["table_names"] = result["tables"]

    # Store tables confirmed to have data (from discover_schema pre-check)
    if "tables_with_data" in result and isinstance(result["tables_with_data"], list):
        for tbl in result["tables_with_data"]:
            cache["tables_with_data"].add(tbl)

    # From query_database (single table)
    if result.get("sql"):
        sql_upper = result["sql"].upper()
        matched_tbl = None
        for tbl in cache.get("table_names", []):
            if tbl.upper() in sql_upper or f"[{tbl.upper()}]" in sql_upper:
                matched_tbl = tbl
                break
        if not matched_tbl:
            m = re.search(r'FROM\s+\[?(\w+)\]?', result["sql"], re.IGNORECASE)
            if m:
                matched_tbl = m.group(1)
                if matched_tbl not in cache["table_names"]:
                    cache["table_names"].append(matched_tbl)
        if matched_tbl:
            if result.get("columns"):
                cache["table_columns"][matched_tbl] = result["columns"]
            if result.get("row_count", 0) > 0:
                cache["tables_with_data"].add(matched_tbl)
                cache["empty_tables"].discard(matched_tbl)
            elif "error" not in result and "execution_error" not in result:
                cache["empty_tables"].add(matched_tbl)
                cache["tables_with_data"].discard(matched_tbl)

    # From multi-table results
    if result.get("multi_table") and result.get("results"):
        for tr in result["results"]:
            tbl = tr.get("table", "")
            if tr.get("columns"):
                cache["table_columns"][tbl] = tr["columns"]
            if tr.get("row_count", 0) > 0:
                cache["tables_with_data"].add(tbl)
                cache["empty_tables"].discard(tbl)
            elif "error" not in tr:
                cache["empty_tables"].add(tbl)
                cache["tables_with_data"].discard(tbl)

    # Persist to database
    _save_cache_to_db(connector_id, cache)


def _get_schema_context(connector_id: str) -> str:
    """Build a schema context block for the system prompt from cache."""
    if not connector_id:
        return ""
    cache = _get_cache(connector_id)
    if not cache.get("table_names"):
        return ""

    parts = [f"\n## Cached Schema for Active Connector ({len(cache['table_names'])} tables)"]

    with_data = sorted(cache.get("tables_with_data", set()))
    empty = sorted(cache.get("empty_tables", set()))

    if with_data:
        parts.append(f"\n**Tables with data** ({len(with_data)}):")
        for tbl in with_data[:30]:
            cols = cache.get("table_columns", {}).get(tbl, [])
            if cols:
                parts.append(f"  - `{tbl}` → columns: {', '.join(str(c) for c in cols[:10])}")
            else:
                parts.append(f"  - `{tbl}`")

    if empty:
        parts.append(f"\n**Empty tables** ({len(empty)}): {', '.join(f'`{t}`' for t in empty[:20])}")

    all_tables = cache["table_names"]
    remaining = [t for t in all_tables if t not in with_data and t not in empty]
    if remaining:
        display = remaining[:50]
        parts.append(f"\n**Other tables** ({len(remaining)}): {', '.join(f'`{t}`' for t in display)}")
        if len(remaining) > 50:
            parts.append(f"  ...and {len(remaining) - 50} more")

    known_cols = {t: c for t, c in cache.get("table_columns", {}).items()
                  if t not in with_data}
    if known_cols:
        parts.append("\n**Known columns**:")
        for tbl, cols in list(known_cols.items())[:20]:
            parts.append(f"  - `{tbl}`: {', '.join(str(c) for c in cols[:10])}")

    parts.append("\n**USE THIS CONTEXT**: When the user asks about tables, use the cached info above. "
                 "If a table is marked empty, tell the user. Suggest tables WITH data as alternatives.")

    return "\n".join(parts)
from app.api.tools import TOOL_SCHEMAS, TOOL_SCHEMAS_LITE, execute_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])

AGENT_MODEL = "openai/gpt-4.1-mini-fast"
AGENT_FALLBACK_MODELS = ["google/gemini-2.5-flash", "meta/llama-3.3-70b", "deepseek/deepseek-v4.1-flash-fast"]


class ChatRequest(BaseModel):
    message: str
    connector_id: str | None = None
    history: list[dict] | None = None


# ──────────────────────────────────────────────
# CONNECTION STRING PRE-DETECTION
# ──────────────────────────────────────────────

_CONN_STRING_PATTERNS = [
    r"postgresql://",
    r"postgres://",
    r"mysql://",
    r"mysql\+pymysql://",
    r"mariadb://",
    r"mssql://",
    r"mssql\+pyodbc://",
    r"mongodb\+srv://",
    r"mongodb://",
    r"redis://",
    r"rediss://",
    r"bolt://",
    r"neo4j://",
    r"cassandra://",
    r"elasticsearch://",
    r"clickhouse://",
    r"influxdb://",
    r"couchdb://",
    r"oracle://",
    r"cockroachdb://",
    r"sqlite:///",
]
_CONN_STRING_RE = re.compile("|".join(_CONN_STRING_PATTERNS), re.IGNORECASE)


def _detect_connection_string(message: str) -> str | None:
    """Extract a connection string from user message, if present."""
    # 1. Standard URI format (mssql://, postgresql://, etc.)
    m = _CONN_STRING_RE.search(message)
    if m:
        start = m.start()
        rest = message[start:]
        uri_match = re.match(r'\S+', rest)
        return uri_match.group(0).strip("'\"`,;") if uri_match else None

    # 2. Natural language / key-value format
    #    e.g. "Server summitdev.dyndns.info,1433 Login sa Password SQL2019"
    #    e.g. "Host: mydb.com Port: 5432 User: admin Password: secret Database: mydb"
    #    e.g. "MSSQL host.com 1433 user password dbname"
    nl_uri = _parse_natural_language_connection(message)
    if nl_uri:
        return nl_uri

    return None


# ── DB type keywords for NL detection ──
_NL_DB_KEYWORDS = {
    "sql server": "mssql", "sqlserver": "mssql", "mssql": "mssql",
    "field value": "mssql", "field value server": "mssql",
    "postgresql": "postgresql", "postgres": "postgresql", "pg": "postgresql",
    "mysql": "mysql", "mariadb": "mariadb",
    "mongodb": "mongodb", "mongo": "mongodb",
    "supabase": "postgresql", "neon": "postgresql",
    "oracle": "oracle", "redis": "redis", "sqlite": "sqlite",
    "cockroachdb": "cockroachdb", "clickhouse": "clickhouse",
}

# Default ports per DB type
_DEFAULT_PORTS = {
    "mssql": 1433, "postgresql": 5432, "mysql": 3306, "mariadb": 3306,
    "mongodb": 27017, "oracle": 1521, "redis": 6379, "clickhouse": 8123,
    "cockroachdb": 26257, "sqlite": 0,
}


def _parse_natural_language_connection(message: str) -> str | None:
    """Parse natural language connection details into a URI.

    Handles formats like:
      - "Server host,1433 Login sa Password pass123 Encryption Disable"
      - "Host: mydb.com Port: 5432 Username: admin Password: secret Database: myapp"
      - "MSSQL summitdev.dyndns.info 1433 sa SQL2019"
      - "connect to postgresql host mydb.com user admin password secret db myapp"
    """
    msg = message.strip()
    lower = msg.lower()

    # Detect DB type from keywords
    db_type = None
    for kw, dtype in sorted(_NL_DB_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if kw in lower:
            db_type = dtype
            break

    # Must have at least a host-like pattern (domain or IP) to be a connection string
    host_pattern = re.compile(
        r'(?:(?:[\w-]+\.)+[a-zA-Z]{2,}|(?:\d{1,3}\.){3}\d{1,3}|localhost)'
    )
    if not host_pattern.search(msg):
        return None

    # Extract fields using key-value patterns (case-insensitive)
    def _extract(keys, text):
        for key in keys:
            # "Key: value" or "Key value" (value = next non-space token or quoted string)
            pat = re.compile(
                rf'\b{re.escape(key)}[\s:=]+["\']?([^\s"\']+)["\']?',
                re.IGNORECASE
            )
            m = pat.search(text)
            if m:
                return m.group(1).strip(",;")
        return None

    host = _extract(["server", "host", "hostname", "address", "addr", "endpoint"], msg)
    port = _extract(["port"], msg)
    user = _extract(["login", "user", "username", "uid", "user id"], msg)
    password = _extract(["password", "pass", "pwd", "secret"], msg)
    database = _extract(["database", "db", "dbname", "catalog", "initial catalog"], msg)
    encryption = _extract(["encryption", "encrypt", "ssl", "tls", "trust"], msg)

    # Handle "host,port" format (common in MSSQL)
    if host and not port and "," in host:
        parts = host.split(",")
        host = parts[0]
        port_candidate = parts[1].strip()
        if port_candidate.isdigit():
            port = port_candidate

    # If no explicit host found, try to find a domain/IP directly in the text
    if not host:
        m = host_pattern.search(msg)
        if m:
            host = m.group(0)
            # Check if next token is a port number
            after = msg[m.end():].strip().lstrip(",").strip()
            port_m = re.match(r'^(\d{2,5})\b', after)
            if port_m:
                port = port_m.group(1)

    if not host:
        return None

    # Infer DB type from port if not detected from keywords
    if not db_type and port:
        port_int = int(port)
        port_to_type = {v: k for k, v in _DEFAULT_PORTS.items()}
        db_type = port_to_type.get(port_int)

    # Default to mssql if "Server" keyword is present (common MSSQL pattern)
    if not db_type and re.search(r'\bserver\b', lower):
        db_type = "mssql"

    # Still no type — can't build URI
    if not db_type:
        return None

    # Build URI
    default_port = _DEFAULT_PORTS.get(db_type, 5432)
    port_int = int(port) if port else default_port
    user = user or ""
    password = password or ""
    database = database or ("master" if db_type == "mssql" else "")

    # URL-encode user/password
    from urllib.parse import quote
    user_enc = quote(user, safe="")
    pass_enc = quote(password, safe="")

    if user_enc and pass_enc:
        auth = f"{user_enc}:{pass_enc}@"
    elif user_enc:
        auth = f"{user_enc}@"
    else:
        auth = ""

    # Build query params
    params = []
    if encryption and encryption.lower() in ("disable", "no", "false", "off", "0"):
        if db_type == "mssql":
            params.append("encrypt=no")
            params.append("TrustServerCertificate=yes")
    elif encryption and encryption.lower() in ("enable", "yes", "true", "on", "1"):
        if db_type == "mssql":
            params.append("encrypt=yes")

    scheme = db_type
    if db_type == "mssql":
        scheme = "mssql+pymssql"
    elif db_type == "postgresql":
        scheme = "postgresql"
    elif db_type == "mongodb":
        scheme = "mongodb+srv"

    uri = f"{scheme}://{auth}{host}:{port_int}/{database}"
    if params:
        uri += "?" + "&".join(params)

    return uri


# ──────────────────────────────────────────────
# SYSTEM PROMPT BUILDER
# ──────────────────────────────────────────────

def _build_system_prompt(db: Session, connector_id: str | None = None) -> str:
    connectors = db.query(Connector).all()

    if connectors:
        lines = []
        for c in connectors:
            active = " ← ACTIVE" if connector_id and str(c.id) == str(connector_id) else ""
            lines.append(
                f"  • \"{c.name}\" ({c.connector_type}) [{c.status}]{active}"
            )
        conn_block = "\n".join(lines)
        if connector_id:
            conn_block += f"\n\n  **Active connector_id**: `{connector_id}`"
    else:
        conn_block = "  (none — user has not connected any database yet)"

    cid = connector_id or "null"
    schema_ctx = _get_schema_context(connector_id) if connector_id else ""

    return f"""You are TB Query Assistant — a fast, action-oriented database expert and general assistant.

## Databases
{conn_block}
Active connector_id: `{cid}`

## GOLDEN RULE: NEVER ASK CLARIFYING QUESTIONS
You MUST always EXECUTE, never ask. If the user says something, DO IT immediately.
- "Display first 10 records from each table" → call query_database(question="Display first 10 records from each table")
- "show me all tables" → call discover_schema
- "customers" → call query_database(question="Show all data from customers")
- "reply" or any vague input → call query_database with the user's exact text
- NEVER respond with "Could you tell me which table?" or "Which tables would you like?"
- NEVER ask the user to clarify. ALWAYS attempt to execute with what you have.
- If a query is ambiguous, make your BEST GUESS and execute it. The user can refine later.

## Rules

### RULE 1: query_database — DIRECT SQL PREFERRED
Call `query_database` for ANY data-related input.
- **If you know the schema** (from cached schema below or from discover_schema results), write the SQL yourself and pass it via the `sql` parameter. This is FASTER because it skips the internal SQL generation step.
  Example: query_database(connector_id="...", sql="SELECT TOP 10 * FROM [Accounts]")
- **If you don't know the schema yet**, pass the user's message via the `question` parameter. The tool will discover the schema and generate SQL internally.
  Example: query_database(connector_id="...", question="how many customers?")
- ALWAYS prefer `sql` when you have table/column info. Only use `question` as a fallback.

### RULE 1b: explain_query and suggest_optimizations — CRITICAL
- When user says **"optimize"**, **"suggest optimization"**, **"improve performance"**, **"make faster"**, **"index suggestions"** → call `suggest_optimizations(connector_id, sql)`. Do NOT call query_database for these.
- When user says **"explain query"**, **"show execution plan"**, **"why is this slow"**, **"analyze plan"** → call `explain_query(connector_id, sql)`.
- You may chain both: first `explain_query` then `suggest_optimizations`.
- Always pass the actual SQL string, not a description.
- **NEVER use query_database when the user explicitly asks to optimize or explain a query.**

### RULE 2: discover_schema — ONLY for explicit schema requests
ONLY when user literally says: "what tables exist", "show schema", "describe database", "list all tables", "show me all tables"

### RULE 3: DATABASE ONLY — reject non-database questions
You are EXCLUSIVELY a database query assistant. You ONLY answer questions related to:
- Database queries (SQL, NoSQL, aggregations)
- Tables, columns, rows, schemas, indexes
- Database connections and connectors
- Query optimization and execution plans
- Data analysis on connected databases

If the user asks about ANYTHING else (coding, math, general knowledge, programming languages, advice, chat, etc.), respond with:
"I'm TB Query Assistant — I only help with database queries, tables, columns, and data questions. Please ask me something about your database!"

NEVER answer general questions, write code in programming languages, do math, or engage in casual conversation.

### RULE 4: Connection strings → connect_database
Any URI (postgresql://, mssql://, etc.) → call connect_database.

### RULE 5: ALWAYS execute
- 0 rows = empty table, say so and STOP.
- Success = present results and STOP.
- Error = explain and suggest alternatives. Do NOT ask the user to rephrase.
- Max 2 tool calls per request.
- Be concise. Markdown tables for data. Code blocks for SQL.
- NEVER output <think> tags.

### RULE 6: USE CONVERSATION MEMORY
- You have FULL conversation history. ALWAYS reference previous messages.
- If the user previously connected a database or discovered schema, you KNOW what tables exist.
- If a table was previously shown as empty, tell the user instead of re-querying.
- If the user says "show me that table" or "try another one" — use context from prior messages.
- NEVER say "I don't know which table" if tables were discussed earlier.
- When a table is empty, suggest tables that HAVE data (from the cached schema below).
{schema_ctx}"""


# ──────────────────────────────────────────────
# STATUS LABELS  (structured steps for the UI)
# ──────────────────────────────────────────────

# Each tool maps to (step_label, step_description)
_TOOL_STATUS = {
    "list_connectors":        ("Looking up databases",        "Fetching your connected databases"),
    "connect_database":       ("Connecting to database",      "Establishing a secure connection"),
    "discover_schema":        ("Reading database structure",  "Scanning tables, columns and relationships"),
    "query_database":         ("Running your query",          "Generating SQL and fetching results"),
    "search_tables":          ("Searching tables",            "Finding tables that match your question"),
    "explain_query":          ("Analyzing query plan",        "Breaking down how the query executes"),
    "suggest_optimizations":  ("Optimizing query",            "Generating performance suggestions"),
}

def _step_event(step_num: int, tool_name: str, phase: str = "running") -> dict:
    """Build a structured status event for the frontend progress block.

    phase: "running" | "done" | "error"
    """
    label, description = _TOOL_STATUS.get(tool_name, (f"Running {tool_name}", "Processing…"))
    return {
        "type": "status",
        "step": step_num,
        "label": label,
        "description": description,
        "phase": phase,
        "tool": tool_name,
    }


# ──────────────────────────────────────────────
# LOCAL MARKDOWN FORMATTERS (avoid 2nd LLM call)
# ──────────────────────────────────────────────

def _format_query_result_markdown(result: dict) -> str:
    """Format query_database result as markdown without LLM."""

    # ── Multi-table results ──
    if result.get("multi_table"):
        parts = [f"**Queried {result.get('tables_queried', 0)} of {result.get('total_tables', 0)} tables:**\n"]
        for tbl_result in result.get("results", []):
            tbl_name = tbl_result.get("table", "Unknown")
            if tbl_result.get("error"):
                parts.append(f"\n### {tbl_name}\n> Error: {tbl_result['error']}\n")
                continue
            columns = tbl_result.get("columns", [])
            rows = tbl_result.get("rows", [])
            row_count = tbl_result.get("row_count", 0)
            sql = tbl_result.get("sql", "")
            parts.append(f"\n### {tbl_name}")
            if sql:
                parts.append(f"```sql\n{sql}\n```")
            if row_count == 0:
                parts.append("*Empty table — no rows.*\n")
            elif columns and rows:
                parts.append(f"**{row_count} row{'s' if row_count != 1 else ''}:**\n")
                header = "| " + " | ".join(str(c) for c in columns) + " |"
                sep = "| " + " | ".join("---" for _ in columns) + " |"
                parts.append(header)
                parts.append(sep)
                for row in rows[:10]:
                    cells = " | ".join(str(v) if v is not None else "NULL" for v in row)
                    parts.append(f"| {cells} |")
                parts.append("")
        return "\n".join(parts)

    # ── Single-table results ──
    sql = result.get("sql", "")
    mongo_query = result.get("mongo_query", "")
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    row_count = result.get("row_count", 0)
    note = result.get("note", "")

    parts = []
    if sql:
        parts.append(f"```sql\n{sql}\n```\n")
    elif mongo_query:
        parts.append(f"```json\n{mongo_query}\n```\n")

    if note:
        parts.append(f"> {note}\n")

    if row_count == 0:
        parts.append("**No rows returned.** The table exists but is empty or the filter matched nothing.")
        # Show columns even when empty (so user knows the table structure)
        if columns:
            parts.append(f"\n**Table structure** ({len(columns)} columns): {', '.join(str(c) for c in columns)}")
        # Suggest tables with data from the cache
        connector_id = result.get("_connector_id")
        if connector_id:
            cache = _get_cache(connector_id)
            with_data = sorted(cache.get("tables_with_data", set()))
            if with_data:
                suggestions = with_data[:5]
                parts.append(f"\n**Tables with data you can try**: {', '.join(f'`{t}`' for t in suggestions)}")
            else:
                # Even without confirmed data tables, suggest any known tables
                known = cache.get("table_names", [])
                if known:
                    import random
                    sample = random.sample(known, min(5, len(known)))
                    parts.append(f"\n**Other tables to try**: {', '.join(f'`{t}`' for t in sample)}")
        elif not connector_id:
            logger.info("No _connector_id in result, cannot suggest alternatives")
    elif columns and rows:
        # Build markdown table
        parts.append(f"**{row_count} row{'s' if row_count != 1 else ''}** returned:\n")
        header = "| " + " | ".join(str(c) for c in columns) + " |"
        sep = "| " + " | ".join("---" for _ in columns) + " |"
        parts.append(header)
        parts.append(sep)
        for row in rows[:30]:  # Limit to 30 rows in display
            cells = " | ".join(str(v) if v is not None else "NULL" for v in row)
            parts.append(f"| {cells} |")
        if row_count > 30:
            parts.append(f"\n*...and {row_count - 30} more rows*")
    return "\n".join(parts)


def _format_schema_result_markdown(result: dict) -> str:
    """Format discover_schema result as markdown."""
    tables = result.get("tables", result.get("table_names", result.get("names", [])))
    table_count = result.get("table_count", len(tables))
    if not tables:
        return f"**{table_count} tables** found but no details available."
    parts = [f"**{table_count} tables** in this database:\n"]
    for t in tables[:50]:
        if isinstance(t, dict):
            name = t.get("name", t.get("table_name", str(t)))
            cols = t.get("columns", [])
            if cols:
                col_str = ", ".join(str(c) for c in cols[:10])
                parts.append(f"- **{name}** — {col_str}")
            else:
                parts.append(f"- **{name}**")
        else:
            parts.append(f"- **{t}**")
    if table_count > 50:
        parts.append(f"\n*...and {table_count - 50} more tables*")
    note = result.get("note")
    if note:
        parts.append(f"\n> {note}")
    return "\n".join(parts)


def _format_search_result_markdown(result: dict) -> str:
    """Format search_tables result as markdown."""
    matches = result.get("matches", result.get("results", []))
    if not matches:
        return "**No matching tables or columns found.**"
    parts = [f"**{len(matches)} match{'es' if len(matches) != 1 else ''}** found:\n"]
    for m in matches[:15]:
        if isinstance(m, dict):
            name = m.get("table", m.get("name", str(m)))
            cols = m.get("columns", m.get("matched_columns", []))
            if cols:
                parts.append(f"- **{name}** — columns: {', '.join(str(c) for c in cols[:8])}")
            else:
                parts.append(f"- **{name}**")
        else:
            parts.append(f"- **{m}**")
    return "\n".join(parts)


def _format_connectors_markdown(result: dict) -> str:
    """Format list_connectors result as markdown."""
    connectors = result.get("connectors", [])
    if not connectors:
        return "**No databases connected.** Paste a connection string to get started."
    parts = [f"**{len(connectors)} database{'s' if len(connectors) != 1 else ''}** connected:\n"]
    for c in connectors:
        if isinstance(c, dict):
            name = c.get("name", "Unnamed")
            db_type = c.get("type", c.get("connector_type", ""))
            status = c.get("status", "")
            cid = c.get("id", "")
            parts.append(f"- **{name}** ({db_type}) [{status}] `{cid}`")
        else:
            parts.append(f"- {c}")
    return "\n".join(parts)


def _format_explain_result_markdown(result: dict) -> str:
    """Format explain_query result as markdown."""
    if result.get("error"):
        return f"**Error explaining query:** {result['error']}"
    sql = result.get("sql", "")
    plan = result.get("plan", "")
    dialect = result.get("dialect", "")
    parts = [f"**Execution Plan** ({dialect.upper()})"]
    if sql:
        parts.append(f"\n```sql\n{sql}\n```")
    if plan:
        parts.append(f"\n```\n{plan}\n```")
    return "\n".join(parts)


def _format_optimization_result_markdown(result: dict) -> str:
    """Format suggest_optimizations result as markdown."""
    if result.get("error"):
        return f"**Error generating optimization suggestions:** {result['error']}"
    analysis = result.get("analysis", "")
    sql = result.get("sql", "")
    parts = []
    if sql:
        parts.append(f"**Original Query:**\n```sql\n{sql}\n```\n")
    if analysis:
        parts.append(analysis)
    return "\n".join(parts) if parts else "No optimization suggestions available."


# ──────────────────────────────────────────────
# ASYNC TOOL EXECUTION WITH HEARTBEAT
# ──────────────────────────────────────────────

async def _execute_tool_with_heartbeat(name, args, db, heartbeat_queue: asyncio.Queue):
    """Run tool in a thread and push heartbeats every 3s while it runs."""
    loop = asyncio.get_event_loop()

    # Start the actual tool execution in a thread
    tool_future = loop.run_in_executor(None, execute_tool, name, args, db)

    # Send heartbeats while waiting
    while True:
        try:
            result = await asyncio.wait_for(asyncio.shield(tool_future), timeout=3.0)
            return result
        except asyncio.TimeoutError:
            await heartbeat_queue.put({"type": "heartbeat"})
            continue


# ──────────────────────────────────────────────
# AGENT LOOP  (async generator + SSE)
# ──────────────────────────────────────────────

def _is_database_question(message: str) -> bool:
    """Check if a message is related to databases/queries. Returns False for non-DB questions."""
    msg_lower = message.strip().lower()

    # Connection strings are always valid
    if _detect_connection_string(message):
        return True

    # Explicit non-DB questions — reject immediately
    non_db_patterns = [
        r"\b(write|code|program|script)\b.+\b(java|python|javascript|c\+\+|rust|go|ruby|php|swift|kotlin)\b",
        r"\b(in|using|with)\s+(java|python|javascript|c\+\+|rust|go|ruby|php|swift|kotlin)\b",
        r"\b(java|python|javascript|c\+\+|rust|go|ruby|php|swift|kotlin)\s+(code|program|script|function|class)\b",
        r"\bhow\s+to\s+(learn|start|begin|code|program)\b",
        r"\b(recipe|weather|joke|poem|story|translate|essay|summarize|news)\b",
        r"\b(what is|who is|when was|where is)\b(?!.*\b(table|column|row|schema|database|query|sql|index)\b)",
    ]
    for pattern in non_db_patterns:
        if re.search(pattern, msg_lower):
            return False

    # Database keywords — if any of these appear, it's a DB question
    db_keywords = [
        # SQL keywords
        "select", "insert", "update", "delete", "drop", "alter",
        "table", "tables", "column", "columns", "row", "rows", "record", "records",
        "schema", "index", "indexes", "query", "queries", "sql", "nosql",
        "join", "where", "group by", "order by", "having", "limit", "offset",
        "count", "sum", "avg", "min", "max", "distinct",
        # Database types
        "database", "databases", "postgresql", "postgres", "mysql", "mongodb",
        "mssql", "sql server", "sqlite", "oracle", "mariadb", "redis",
        "cassandra", "neo4j", "elasticsearch", "supabase", "cockroachdb",
        # Database operations
        "connect", "connection", "connector", "fetch", "retrieve",
        "aggregate", "aggregation", "pipeline", "collection", "collections",
        "foreign key", "primary key", "constraint", "relationship",
        "optimize", "optimization", "execution plan", "explain",
        "stored procedure", "view", "views", "trigger", "triggers",
        # Common data questions
        "how many", "show me", "list all", "find all", "get all",
        "first 10", "top 10", "top 5", "last 10",
        "describe", "structure", "fields",
    ]

    for kw in db_keywords:
        if kw in msg_lower:
            return True

    # Check if the message looks like a SQL query
    sql_patterns = [
        r"^\s*select\s", r"^\s*with\s", r"^\s*show\s+\w+",
        r"^\s*describe\s", r"^\s*explain\s",
    ]
    for pattern in sql_patterns:
        if re.search(pattern, msg_lower):
            return True

    return False


def _auto_detect_connector(message: str, connectors: list, current_connector_id: str | None = None) -> tuple[str | None, str | None]:
    """Auto-detect which database connector to use based on the user's query.

    Returns (connector_id, reason) — reason explains why this DB was chosen.
    """
    if not connectors:
        return None, None

    msg_lower = message.strip().lower()

    # Connected connectors only
    connected = [c for c in connectors if c.status == "connected"]
    if not connected:
        connected = connectors  # fallback to all if none connected

    # 1. Check if user explicitly mentions a database type
    type_keywords = {
        "mssql": ["mssql", "sql server", "sqlserver", "microsoft sql"],
        "postgresql": ["postgresql", "postgres", "psql"],
        "mysql": ["mysql"],
        "mongodb": ["mongodb", "mongo", "nosql", "collection", "document"],
        "supabase": ["supabase"],
        "sqlite": ["sqlite"],
        "oracle": ["oracle"],
        "mariadb": ["mariadb"],
        "redis": ["redis"],
        "cassandra": ["cassandra"],
        "neo4j": ["neo4j", "graph database", "cypher"],
        "elasticsearch": ["elasticsearch", "elastic"],
        "cockroachdb": ["cockroachdb", "cockroach"],
        "clickhouse": ["clickhouse"],
        "influxdb": ["influxdb", "influx"],
        "couchdb": ["couchdb", "couch"],
    }

    for db_type, keywords in type_keywords.items():
        for kw in keywords:
            if kw in msg_lower:
                # Find a connector of this type
                match = next((c for c in connected if c.connector_type.lower() == db_type), None)
                if match:
                    return str(match.id), f"Detected {db_type.upper()} from your query"

    # 2. Check if user mentions a specific database/connector name
    for c in connected:
        if c.name.lower() in msg_lower or (c.database and c.database.lower() in msg_lower):
            return str(c.id), f"Matched database name: {c.name}"

    # 3. Check cached table names — match against known tables in each connector
    for c in connected:
        cache = _get_cache(str(c.id))
        table_names = cache.get("table_names", [])
        for tname in table_names:
            if tname.lower() in msg_lower:
                return str(c.id), f"Found table '{tname}' in {c.name}"

    # 4. Check for SQL dialect-specific syntax
    mssql_patterns = [r"\bTOP\s+\d+\b", r"\[[\w]+\]", r"GETDATE\(\)", r"ISNULL\(", r"NEWID\(\)"]
    pg_patterns = [r"\bILIKE\b", r"::\w+", r"NOW\(\)", r"COALESCE\("]
    mysql_patterns = [r"IFNULL\(", r"CONCAT\(", r"LIMIT\s+\d+\s*,\s*\d+"]
    mongo_patterns = [r"\bfind\(", r"\baggregate\(", r"\$match", r"\$group", r"\$project"]

    for pattern in mssql_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            match = next((c for c in connected if c.connector_type.lower() == "mssql"), None)
            if match:
                return str(match.id), "Detected MSSQL syntax"

    for pattern in pg_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            match = next((c for c in connected if c.connector_type.lower() in ("postgresql", "supabase")), None)
            if match:
                return str(match.id), "Detected PostgreSQL syntax"

    for pattern in mysql_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            match = next((c for c in connected if c.connector_type.lower() == "mysql"), None)
            if match:
                return str(match.id), "Detected MySQL syntax"

    for pattern in mongo_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            match = next((c for c in connected if c.connector_type.lower() == "mongodb"), None)
            if match:
                return str(match.id), "Detected MongoDB syntax"

    # 5. If current connector is set and connected, keep using it
    if current_connector_id:
        current = next((c for c in connected if str(c.id) == str(current_connector_id)), None)
        if current:
            return str(current.id), f"Using current database: {current.name}"

    # 6. Default to MySQL if available, otherwise first connected
    mysql_match = next((c for c in connected if c.connector_type.lower() == "mysql"), None)
    if mysql_match:
        return str(mysql_match.id), f"Default: {mysql_match.name} (MySQL)"

    return str(connected[0].id), f"Auto-selected: {connected[0].name} ({connected[0].connector_type})"


async def _agent_stream(request: ChatRequest, db: Session) -> AsyncGenerator[str, None]:
    groq = get_llm_client(max_retries=0)

    # ── PRE-FILTER: Reject non-database questions immediately ──
    detected_uri = _detect_connection_string(request.message)
    if not detected_uri and not _is_database_question(request.message):
        yield _sse({"type": "content", "content": "I'm **TB Query Assistant** — I only help with database queries, tables, columns, rows, schemas, and data questions.\n\nPlease ask me something about your database! For example:\n- \"Show me all tables\"\n- \"How many rows in customers?\"\n- \"Find orders from last month\""})
        yield _sse({"type": "done"})
        return

    # ── AUTO-DETECT: Pick the right database based on query content ──
    connectors = db.query(Connector).all()
    if connectors:
        detected_id, detect_reason = _auto_detect_connector(
            request.message, connectors, request.connector_id
        )
        if detected_id:
            request.connector_id = detected_id
            detected_connector = next((c for c in connectors if str(c.id) == detected_id), None)
            if detected_connector:
                yield _sse({
                    "type": "connector_detected",
                    "connector_id": detected_id,
                    "connector_name": detected_connector.name,
                    "connector_type": detected_connector.connector_type,
                    "reason": detect_reason,
                })
                logger.info("Auto-detected connector: %s (%s) — %s", detected_connector.name, detected_id, detect_reason)

    messages = [{"role": "system", "content": _build_system_prompt(db, request.connector_id)}]

    # Append recent history for context
    if request.history:
        for h in request.history[-10:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": request.message})

    max_rounds = 4
    tool_call_history = []
    heartbeat_queue = asyncio.Queue()
    step_counter = 0  # tracks progress steps for UI

    # ── PRE-DETECTION: connection strings bypass LLM entirely ──
    detected_uri = _detect_connection_string(request.message)
    if detected_uri:
        step_counter += 1
        yield _sse({"type": "status", "step": step_counter, "label": "Detected connection string", "description": "Parsing your database URI", "phase": "done", "tool": "_thinking"})

        step_counter += 1
        yield _sse(_step_event(step_counter, "connect_database", "running"))

        try:
            result = await _execute_tool_with_heartbeat(
                "connect_database", {"connection_string": detected_uri}, db, heartbeat_queue
            )
            yield _sse(_step_event(step_counter, "connect_database", "done"))
        except Exception as exc:
            yield _sse(_step_event(step_counter, "connect_database", "error"))
            yield _sse({"type": "error", "content": f"Connection failed: {exc}"})
            yield _sse({"type": "done"})
            return

        while not heartbeat_queue.empty():
            yield _sse(await heartbeat_queue.get())

        if result.get("success"):
            new_id = str(result.get("connector_id", ""))
            name = result.get("name", "Database")
            already = result.get("already_exists", False)

            if already:
                md = f"**Already connected** as **{name}** — ready to query!"
            else:
                md = f"**Connected to {name}!** You can now ask questions about this database."

            # Auto-discover schema for the new connector
            step_counter += 1
            yield _sse(_step_event(step_counter, "discover_schema", "running"))
            try:
                schema_result = await _execute_tool_with_heartbeat(
                    "discover_schema", {"connector_id": new_id}, db, heartbeat_queue
                )
                yield _sse(_step_event(step_counter, "discover_schema", "done"))
                # Cache schema for future queries
                _update_schema_cache(new_id, schema_result)
                table_count = schema_result.get("table_count", len(schema_result.get("tables", {})))
                md += f"\n\n**{table_count} tables** found."

                # Prefer tables confirmed to have data for suggestions
                data_tables = schema_result.get("tables_with_data", [])
                if not data_tables:
                    # Fallback to any table names
                    tables = schema_result.get("tables", schema_result.get("table_names", []))
                    if isinstance(tables, dict):
                        data_tables = list(tables.keys())
                    elif isinstance(tables, list):
                        data_tables = [t.get("name", str(t)) if isinstance(t, dict) else str(t) for t in tables]

                # Filter out internal/system-looking tables from suggestions
                _skip_prefixes = ("__", "_Temp", "sys", "spt_", "MS", "trace_xe_")
                clean_tables = [t for t in data_tables if not any(t.startswith(p) for p in _skip_prefixes)]
                if not clean_tables:
                    clean_tables = data_tables  # fallback to unfiltered

                if clean_tables:
                    md += " Try asking a question like:\n"
                    md += f'- "Show me data from {clean_tables[0]}"\n'
                    if len(clean_tables) > 1:
                        md += f'- "How many rows in {clean_tables[1]}?"\n'
                else:
                    md += " The database appears to be empty — no tables with data found."
            except Exception:
                pass  # Schema discovery is optional — connection still succeeded

            while not heartbeat_queue.empty():
                yield _sse(await heartbeat_queue.get())

            yield _sse({"type": "content", "content": md})
            yield _sse({"type": "done"})
            return
        else:
            error = result.get("error", "Unknown error")
            yield _sse({"type": "content", "content": f"**Connection failed:** {error}"})
            yield _sse({"type": "done"})
            return

    # ── PRE-DETECTION: multi-table / "each table" / "all tables" queries ──
    # Route directly to query_database without LLM deciding
    _multi_table_re = re.compile(
        r"(first|top|display|show|get)\s.*?(each|every|all)\s+table|"
        r"(each|every|all)\s+table.*?(first|top|record|row|data|count)|"
        r"records?\s+from\s+(each|every|all)\s+table|"
        r"count\s+(of|for|in|from|per)\s+(each|every|all)\s+table|"
        r"(each|every|all)\s+table.*?count|"
        r"how\s+many\s+rows?\s+in\s+(each|every|all)\s+table|"
        r"data\s+from\s+(each|every|all)\b|"
        r"sample\s+data\s+from\s+(each|every|all)\b|"
        r"(show|display|get)\s+.*?from\s+(each|every|all)\b",
        re.IGNORECASE
    )
    if _multi_table_re.search(request.message) and request.connector_id:
        step_counter += 1
        yield _sse({"type": "status", "step": step_counter, "label": "Querying all tables", "description": "Fetching sample data from each table", "phase": "running", "tool": "query_database"})
        try:
            result = await _execute_tool_with_heartbeat(
                "query_database",
                {"connector_id": request.connector_id, "question": request.message},
                db, heartbeat_queue
            )
            yield _sse({"type": "status", "step": step_counter, "label": "Querying all tables", "description": "Fetching sample data from each table", "phase": "done", "tool": "query_database"})
            # Cache schema from multi-table results
            _update_schema_cache(request.connector_id, result)
        except Exception as exc:
            yield _sse({"type": "status", "step": step_counter, "label": "Querying all tables", "description": str(exc), "phase": "error", "tool": "query_database"})
            yield _sse({"type": "error", "content": f"Query failed: {exc}"})
            yield _sse({"type": "done"})
            return

        while not heartbeat_queue.empty():
            yield _sse(await heartbeat_queue.get())

        result["_connector_id"] = request.connector_id
        md = _format_query_result_markdown(result)
        yield _sse({"type": "content", "content": md})
        yield _sse({"type": "done"})
        return

    # ── PRE-DETECTION: explain / optimize queries ──
    _explain_re = re.compile(
        r"(?:explain|execution\s+plan|show\s+plan|analyze\s+plan)\s+(?:this\s+)?(?:query|sql)?\s*[:;]?\s*(.+)",
        re.IGNORECASE | re.DOTALL,
    )
    _optimize_re = re.compile(
        r"(?:optimize|suggest\s+optimiz|improve\s+performance|make\s+(?:this\s+)?(?:query\s+)?faster|index\s+suggest)\w*\s+(?:for\s+)?(?:this\s+)?(?:query|sql)?\s*[:;]?\s*(.+)",
        re.IGNORECASE | re.DOTALL,
    )
    _sql_extract_re = re.compile(r"(SELECT\s.+)", re.IGNORECASE | re.DOTALL)

    if request.connector_id:
        _opt_m = _optimize_re.search(request.message)
        _exp_m = _explain_re.search(request.message)
        _forced_tool = None
        _forced_sql = None

        if _opt_m:
            _forced_tool = "suggest_optimizations"
            _raw = _opt_m.group(1).strip()
            _sql_m = _sql_extract_re.search(_raw) or _sql_extract_re.search(request.message)
            _forced_sql = _sql_m.group(1).strip().rstrip(".") if _sql_m else _raw
        elif _exp_m:
            _forced_tool = "explain_query"
            _raw = _exp_m.group(1).strip()
            _sql_m = _sql_extract_re.search(_raw) or _sql_extract_re.search(request.message)
            _forced_sql = _sql_m.group(1).strip().rstrip(".") if _sql_m else _raw

        if _forced_tool and _forced_sql:
            step_counter += 1
            yield _sse(_step_event(step_counter, _forced_tool, "running"))
            try:
                result = await _execute_tool_with_heartbeat(
                    _forced_tool,
                    {"connector_id": request.connector_id, "sql": _forced_sql},
                    db, heartbeat_queue,
                )
                yield _sse(_step_event(step_counter, _forced_tool, "done"))
            except Exception as exc:
                yield _sse(_step_event(step_counter, _forced_tool, "error"))
                yield _sse({"type": "error", "content": f"Tool failed: {exc}"})
                yield _sse({"type": "done"})
                return

            while not heartbeat_queue.empty():
                yield _sse(await heartbeat_queue.get())

            if _forced_tool == "explain_query":
                md = _format_explain_result_markdown(result)
            else:
                md = _format_optimization_result_markdown(result)

            yield _sse({"type": "tool_result", "tool": _forced_tool, "data": {
                "sql": _forced_sql,
                "error": result.get("error"),
            }})
            yield _sse({"type": "content", "content": md})
            yield _sse({"type": "done"})
            return

    # Step 0: always show "Analyzing your question"
    step_counter += 1
    yield _sse({
        "type": "status",
        "step": step_counter,
        "label": "Analyzing your question",
        "description": "Understanding what you need",
        "phase": "running",
        "tool": "_thinking",
    })

    for round_num in range(max_rounds):
        is_last_round = round_num >= max_rounds - 1
        force_text = is_last_round

        # Force text after 2 tool calls to prevent loops (allows search→query flow)
        if len(tool_call_history) >= 2:
            logger.info("Tool already called (%d calls), forcing text-only response", len(tool_call_history))
            force_text = True

        try:
            call_kwargs = dict(
                model=AGENT_MODEL,
                messages=messages,
                temperature=0.6,
                max_tokens=1024,
            )
            if not force_text:
                call_kwargs["tools"] = TOOL_SCHEMAS_LITE
                call_kwargs["tool_choice"] = "auto"

            # Run Groq API call with model rotation on rate limit
            response = None
            models_to_try = [AGENT_MODEL] + AGENT_FALLBACK_MODELS
            for model_id in models_to_try:
                call_kwargs["model"] = model_id
                try:
                    response = await asyncio.to_thread(groq.chat.completions.create, **call_kwargs)
                    break
                except Exception as api_exc:
                    exc_msg = str(api_exc)

                    # Handle "Tool choice is none, but model called a tool"
                    if "Tool choice is none" in exc_msg and "model called a tool" in exc_msg:
                        parsed = _parse_failed_tool_call(exc_msg)
                        if parsed and not force_text:
                            raise api_exc
                        call_kwargs.pop("tools", None)
                        call_kwargs.pop("tool_choice", None)
                        response = await asyncio.to_thread(groq.chat.completions.create, **call_kwargs)
                        break

                    if "429" in exc_msg or "rate_limit" in exc_msg:
                        logger.warning("Rate limited on %s, trying next model", model_id)
                        # Silent retry — never expose model internals to user
                        continue
                    raise api_exc
            if response is None:
                # Fallback: format tool results locally if we have any
                if tool_call_history:
                    direct = _format_tool_results_directly(messages)
                    if direct:
                        yield _sse({"type": "content", "content": direct})
                        yield _sse({"type": "done"})
                        return
                raise Exception("Rate limited. Please wait a minute and try again.")
        except Exception as exc:
            exc_str = str(exc)
            # When force_text, NEVER recover tool calls — just retry without tools
            if force_text and ("tool_use_failed" in exc_str or "Tool choice is none" in exc_str):
                logger.warning("Model tried to call tool during force_text, ignoring")
                # Add a nudge to the conversation to force text output
                messages.append({"role": "user", "content": "Please respond with text only. Summarize the results you have so far."})
                continue
            # Check if this is a tool_use_failed error with a recoverable XML tool call
            parsed = _parse_failed_tool_call(exc_str)
            if parsed and not force_text:
                tool_name, tool_args = parsed
                tool_name = _normalize_tool_name(tool_name)
                # ALWAYS inject the request's connector_id for recovered calls
                if request.connector_id and tool_name not in ("list_connectors", "connect_database"):
                    tool_args["connector_id"] = request.connector_id
                logger.info("Recovered tool call from failed_generation: %s(%s)", tool_name, tool_args)

                tool_call_history.append(f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}")
                step_counter += 1
                yield _sse(_step_event(step_counter, tool_name, "running"))

                try:
                    result = await _execute_tool_with_heartbeat(tool_name, tool_args, db, heartbeat_queue)
                    yield _sse(_step_event(step_counter, tool_name, "done"))
                    # Update schema cache with new knowledge
                    _update_schema_cache(request.connector_id, result)
                except Exception as texc:
                    result = {"error": f"Tool execution failed: {texc}"}
                    yield _sse(_step_event(step_counter, tool_name, "error"))

                while not heartbeat_queue.empty():
                    hb = await heartbeat_queue.get()
                    yield _sse(hb)

                yield _sse({
                    "type": "tool_result",
                    "tool": tool_name,
                    "data": _summarize_tool_result(tool_name, result),
                })

                # Early exit for recovered tool calls (same logic as normal path)
                if tool_name == "query_database" and not result.get("execution_error") and not result.get("error"):
                    result["_connector_id"] = request.connector_id  # for empty result suggestions
                    md = _format_query_result_markdown(result)
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return
                elif tool_name == "discover_schema" and not result.get("error"):
                    user_msg = request.message.lower()
                    is_schema_question = any(kw in user_msg for kw in [
                        "schema", "what tables", "show tables", "list tables",
                        "describe", "structure", "what columns",
                    ])
                    is_large_db = result.get("table_count", 0) > 50 or "table_names" in result
                    if is_schema_question and not is_large_db:
                        md = _format_schema_result_markdown(result)
                        yield _sse({"type": "content", "content": md})
                        yield _sse({"type": "done"})
                        return
                    elif not is_schema_question and not is_large_db and request.connector_id:
                        # Auto-follow-up with query_database for data questions
                        step_counter += 1
                        yield _sse(_step_event(step_counter, "query_database", "running"))
                        try:
                            q_result = await _execute_tool_with_heartbeat(
                                "query_database",
                                {"connector_id": request.connector_id, "question": request.message},
                                db, heartbeat_queue,
                            )
                            yield _sse(_step_event(step_counter, "query_database", "done"))
                        except Exception as qexc:
                            yield _sse(_step_event(step_counter, "query_database", "error"))
                            yield _sse({"type": "error", "content": f"Query failed: {qexc}"})
                            yield _sse({"type": "done"})
                            return
                        while not heartbeat_queue.empty():
                            yield _sse(await heartbeat_queue.get())
                        md = _format_query_result_markdown(q_result)
                        yield _sse({"type": "content", "content": md})
                        yield _sse({"type": "done"})
                        return
                elif tool_name == "list_connectors":
                    md = _format_connectors_markdown(result)
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return
                elif tool_name == "explain_query":
                    md = _format_explain_result_markdown(result)
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return
                elif tool_name == "suggest_optimizations":
                    md = _format_optimization_result_markdown(result)
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return

                # Add assistant message + tool result to conversation for follow-up
                fake_tc_id = f"recovered_{round_num}"
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": fake_tc_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(tool_args)},
                    }],
                })
                recovered_json = json.dumps(result, default=str)
                if len(recovered_json) > 3000:
                    recovered_json = recovered_json[:3000] + '... [truncated]"}'
                messages.append({
                    "role": "tool",
                    "tool_call_id": fake_tc_id,
                    "content": recovered_json,
                })
                continue

            logger.exception("Groq API call failed")
            # If we have tool results but LLM is down, format directly
            if tool_call_history and "rate limit" in str(exc).lower():
                direct = _format_tool_results_directly(messages)
                if direct:
                    yield _sse({"type": "content", "content": direct})
                    yield _sse({"type": "done"})
                    return
            yield _sse({"type": "error", "content": f"AI service error: {exc}"})
            yield _sse({"type": "done"})
            return

        choice = response.choices[0]
        msg = choice.message

        # Mark "Analyzing" step as done (step 1) on the first round
        if round_num == 0:
            yield _sse({
                "type": "status",
                "step": 1,
                "label": "Analyzing your question",
                "description": "Understanding what you need",
                "phase": "done",
                "tool": "_thinking",
            })

        # ── tool calls → execute each, feed result back ──
        if msg.tool_calls and not force_text:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Track which tool types already have a step number (to avoid 10x "Running your query")
            tool_step_map = {}  # tool_name → step_number

            for tc in msg.tool_calls:
                name = tc.function.name
                name = _normalize_tool_name(name)
                try:
                    raw_args = tc.function.arguments or "{}"
                    # Strip <think> tags from qwen model arguments
                    raw_args = re.sub(r"<think>.*?</think>", "", raw_args, flags=re.DOTALL).strip()
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}

                # ALWAYS inject the request's connector_id — the model often passes wrong values
                if request.connector_id and name not in ("list_connectors", "connect_database"):
                    args["connector_id"] = request.connector_id
                logger.warning("TOOL CALL: name=%s, args=%s, request.connector_id=%s", name, args, request.connector_id)

                tool_call_history.append(f"{name}:{json.dumps(args, sort_keys=True)}")

                # Reuse the same step number for same tool type (avoids 10x "Running your query")
                if name in tool_step_map:
                    cur_step = tool_step_map[name]
                    # Update the existing step (don't create a new one)
                    yield _sse(_step_event(cur_step, name, "running"))
                else:
                    step_counter += 1
                    tool_step_map[name] = step_counter
                    cur_step = step_counter
                    yield _sse(_step_event(cur_step, name, "running"))

                # Execute tool with heartbeat keepalive
                try:
                    result = await _execute_tool_with_heartbeat(name, args, db, heartbeat_queue)
                    yield _sse(_step_event(cur_step, name, "done"))
                    # Update schema cache with new knowledge
                    _update_schema_cache(request.connector_id, result)
                except Exception as exc:
                    logger.exception("Tool %s crashed", name)
                    result = {"error": f"Tool execution failed: {exc}"}
                    yield _sse(_step_event(cur_step, name, "error"))

                # Drain and yield any queued heartbeats
                while not heartbeat_queue.empty():
                    hb = await heartbeat_queue.get()
                    yield _sse(hb)

                summary = _summarize_tool_result(name, result)
                yield _sse({
                    "type": "tool_result",
                    "tool": name,
                    "data": summary,
                })

                # After a successful tool call, decide: exit early or let LLM continue
                if name == "query_database" and not result.get("execution_error") and not result.get("error") and (result.get("multi_table") or result.get("sql") or result.get("rows") is not None):
                    result["_connector_id"] = request.connector_id  # for empty result suggestions
                    step_counter += 1
                    yield _sse({"type": "status", "step": step_counter, "label": "Formatting results", "description": "Building your response", "phase": "done", "tool": "_format"})
                    md = _format_query_result_markdown(result)
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return
                elif name == "discover_schema" and not result.get("error"):
                    # Check if original question is a DATA query (not schema query)
                    user_msg = request.message.lower()
                    is_schema_question = any(kw in user_msg for kw in [
                        "schema", "what tables", "show tables", "list tables",
                        "describe", "structure", "what columns",
                    ])
                    is_large_db = result.get("table_count", 0) > 50 or "table_names" in result
                    if is_schema_question and not is_large_db:
                        # Pure schema question on small DB → format and return
                        md = _format_schema_result_markdown(result)
                        yield _sse({"type": "content", "content": md})
                        yield _sse({"type": "done"})
                        return
                    else:
                        # Data query OR large DB:
                        # For data questions on small DBs, auto-call query_database instead of waiting for LLM
                        table_count = result.get("table_count", 0)
                        if not is_schema_question and table_count <= 50 and request.connector_id:
                            # User wants DATA, not schema — auto-execute query_database
                            step_counter += 1
                            yield _sse(_step_event(step_counter, "query_database", "running"))
                            try:
                                q_result = await _execute_tool_with_heartbeat(
                                    "query_database",
                                    {"connector_id": request.connector_id, "question": request.message},
                                    db, heartbeat_queue,
                                )
                                yield _sse(_step_event(step_counter, "query_database", "done"))
                            except Exception as qexc:
                                yield _sse(_step_event(step_counter, "query_database", "error"))
                                yield _sse({"type": "error", "content": f"Query failed: {qexc}"})
                                yield _sse({"type": "done"})
                                return
                            while not heartbeat_queue.empty():
                                yield _sse(await heartbeat_queue.get())
                            step_counter += 1
                            yield _sse({"type": "status", "step": step_counter, "label": "Formatting results", "description": "Building your response", "phase": "done", "tool": "_format"})
                            md = _format_query_result_markdown(q_result)
                            yield _sse({"type": "content", "content": md})
                            yield _sse({"type": "done"})
                            return

                        # Large DB → feed schema back, let LLM call query_database/search_tables
                        result_json = json.dumps(result, default=str)
                        if len(result_json) > 4000:
                            result_json = json.dumps({
                                "table_count": result.get("table_count", 0),
                                "table_names": result.get("table_names", list(result.get("tables", {}).keys()))[:100],
                                "note": "Use search_tables to find relevant tables, then query_database to run SQL.",
                            }, default=str)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_json,
                        })
                        continue
                elif name == "search_tables" and not result.get("error"):
                    # Don't exit early — let the LLM use the results
                    # to decide on a follow-up query_database call
                    result_json = json.dumps(result, default=str)
                    if len(result_json) > 3000:
                        result_json = result_json[:3000] + '... [truncated]"}'
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_json,
                    })
                    continue
                elif name == "list_connectors":
                    md = _format_connectors_markdown(result)
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return
                elif name == "connect_database":
                    if result.get("success"):
                        cname = result.get("name", "Database")
                        already = result.get("already_exists", False)
                        md = f"**{'Already connected' if already else 'Connected'} to {cname}!** You can now ask questions about this database."
                    else:
                        md = f"**Connection failed:** {result.get('error', 'Unknown error')}"
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return
                elif name == "explain_query":
                    md = _format_explain_result_markdown(result)
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return
                elif name == "suggest_optimizations":
                    md = _format_optimization_result_markdown(result)
                    yield _sse({"type": "content", "content": md})
                    yield _sse({"type": "done"})
                    return

                # For errors or other tools, fall through to LLM for text response
                result_json = json.dumps(result, default=str)
                if len(result_json) > 3000:
                    result_json = result_json[:3000] + '... [truncated]"}'
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_json,
                })

            continue

        # ── no tool calls → final text response ──
        content = msg.content or ""
        # Strip <think>...</think> tags from reasoning models (handle unclosed too)
        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        content = re.sub(r"<think>[\s\S]*$", "", content).strip()
        if content:
            # If we had tool calls before, add a "Preparing response" step
            if tool_call_history:
                step_counter += 1
                yield _sse({
                    "type": "status",
                    "step": step_counter,
                    "label": "Preparing response",
                    "description": "Formatting your results",
                    "phase": "done",
                    "tool": "_format",
                })
            yield _sse({"type": "content", "content": content})
        yield _sse({"type": "done"})
        return

    yield _sse({"type": "content", "content": "Reached maximum processing steps."})
    yield _sse({"type": "done"})


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

_TOOL_NAME_ALIASES = {
    # space variants (models sometimes use spaces)
    "search tables": "search_tables",
    "query database": "query_database",
    "connect database": "connect_database",
    "discover schema": "discover_schema",
    "list connectors": "list_connectors",
    "explain query": "explain_query",
    # snake_case variants
    "query_db": "query_database",
    "querydb": "query_database",
    "query": "query_database",
    "connect_db": "connect_database",
    "connectdb": "connect_database",
    "schema": "discover_schema",
    "get_schema": "discover_schema",
    "list_tables": "search_tables",
    "find_tables": "search_tables",
    "explain": "explain_query",
    "optimize": "suggest_optimizations",
    "suggest_optimization": "suggest_optimizations",
    # camelCase variants (gpt-oss models use these)
    "queryDatabase": "query_database",
    "connectDatabase": "connect_database",
    "discoverSchema": "discover_schema",
    "searchTables": "search_tables",
    "listConnectors": "list_connectors",
    "explainQuery": "explain_query",
    "suggestOptimizations": "suggest_optimizations",
}

_VALID_TOOL_NAMES = [
    "list_connectors", "connect_database", "discover_schema",
    "search_tables", "query_database", "explain_query",
    "suggest_optimizations", "validate_query",
]

def _normalize_tool_name(name: str) -> str:
    """Normalize tool name — exact match first, then fuzzy match."""
    if name in _VALID_TOOL_NAMES:
        return name
    if name in _TOOL_NAME_ALIASES:
        return _TOOL_NAME_ALIASES[name]
    # Fuzzy match: find the valid tool name with the most character overlap
    name_lower = name.lower().replace("-", "_").replace(" ", "_")
    if name_lower in _VALID_TOOL_NAMES:
        return name_lower
    if name_lower in _TOOL_NAME_ALIASES:
        return _TOOL_NAME_ALIASES[name_lower]
    # Substring match — if the garbled name contains a keyword
    keyword_map = {
        "query": "query_database", "connect": "connect_database",
        "schema": "discover_schema", "search": "search_tables",
        "table": "search_tables", "list": "list_connectors",
        "explain": "explain_query", "optim": "suggest_optimizations",
        "valid": "validate_query",
    }
    for kw, tool in keyword_map.items():
        if kw in name_lower:
            return tool
    logger.warning("Unknown tool name '%s', defaulting to query_database", name)
    return "query_database"


def _parse_failed_tool_call(error_str: str):
    """Parse a Groq tool_use_failed error to extract the intended tool call.

    Models sometimes output XML-style tool calls with wrong names.
    Groq rejects these at the API level. We parse the failed_generation
    to recover the intended tool name and arguments.

    Returns (tool_name, args_dict) or None if not parseable.
    """
    if "tool_use_failed" not in error_str and "tool call validation failed" not in error_str:
        return None

    # Extract failed_generation content
    fg_match = re.search(r"'failed_generation':\s*[\"'](.*?)[\"']\s*\}", error_str, re.DOTALL)
    if not fg_match:
        return None

    fg = fg_match.group(1).replace("\\n", "\n").replace('\\"', '"')

    # Try JSON format first: {"name": "toolName", "arguments": {...}}
    try:
        fg_json = json.loads(fg)
        if isinstance(fg_json, dict) and "name" in fg_json:
            raw_name = fg_json["name"]
            raw_args = fg_json.get("arguments", {})
            if isinstance(raw_args, str):
                raw_args = json.loads(raw_args)
            # Normalize param names to snake_case
            args = {}
            for k, v in raw_args.items():
                snake_key = re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower()
                args[snake_key] = v
            return (raw_name, args)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Fallback: Parse <function=toolName> XML pattern
    func_match = re.search(r"<function=(\w+)>", fg)
    if not func_match:
        return None

    raw_name = func_match.group(1)

    # Parse <parameter=key>\nvalue\n</parameter> patterns
    args = {}
    for pm in re.finditer(r"<parameter=(\w+)>\s*(.*?)\s*</parameter>", fg, re.DOTALL):
        key = pm.group(1)
        val = pm.group(2).strip()
        snake_key = re.sub(r'(?<!^)(?=[A-Z])', '_', key).lower()
        if val.lower() in ("null", "none", ""):
            args[snake_key] = None
        else:
            args[snake_key] = val

    return (raw_name, args)


def _format_tool_results_directly(messages: list) -> str:
    """Format tool results as Markdown without needing an LLM call.

    When all models are rate-limited after a successful tool call,
    this function extracts the tool result from the conversation
    and formats it into a readable Markdown response.
    """
    # Find the last tool result in messages
    for msg in reversed(messages):
        if msg.get("role") == "tool":
            try:
                result = json.loads(msg["content"])
            except (json.JSONDecodeError, TypeError):
                result = {"raw": msg.get("content", "")}

            # Format based on the result content
            error = result.get("error") or result.get("execution_error")
            if error:
                return f"**Error:** {error}"

            # Query results with rows
            rows = result.get("rows")
            sql = result.get("sql") or result.get("generated_sql", "")
            if rows and isinstance(rows, list) and len(rows) > 0:
                md = ""
                if sql:
                    md += f"```sql\n{sql}\n```\n\n"
                # Build markdown table
                if isinstance(rows[0], dict):
                    headers = list(rows[0].keys())
                    md += "| " + " | ".join(str(h) for h in headers) + " |\n"
                    md += "| " + " | ".join("---" for _ in headers) + " |\n"
                    for row in rows[:50]:
                        md += "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |\n"
                    row_count = result.get("row_count", len(rows))
                    md += f"\n*{row_count} row(s) returned.*"
                else:
                    md += str(rows)
                return md

            # Schema discovery results
            tables = result.get("tables") or result.get("collections")
            if tables and isinstance(tables, dict):
                md = f"**Found {len(tables)} tables:**\n\n"
                for tname, cols in list(tables.items())[:30]:
                    if isinstance(cols, list):
                        col_names = ", ".join(c.get("name", str(c)) if isinstance(c, dict) else str(c) for c in cols[:10])
                        md += f"- **{tname}**: {col_names}\n"
                    else:
                        md += f"- **{tname}**: {cols}\n"
                return md

            # Search results
            matches = result.get("matches")
            if matches and isinstance(matches, list):
                md = f"**Found {len(matches)} matching tables:**\n\n"
                for m in matches[:10]:
                    if isinstance(m, dict):
                        md += f"- **{m.get('table', m.get('name', str(m)))}**"
                        cols = m.get("columns") or m.get("matched_columns")
                        if cols:
                            md += f": {', '.join(str(c) for c in cols[:8])}"
                        md += "\n"
                    else:
                        md += f"- {m}\n"
                return md

            # Connector list
            connectors = result.get("connectors")
            if connectors and isinstance(connectors, list):
                md = f"**{len(connectors)} connected databases:**\n\n"
                for c in connectors:
                    if isinstance(c, dict):
                        md += f"- **{c.get('name', 'Unknown')}** ({c.get('type', c.get('connector_type', ''))}) — {c.get('status', 'unknown')}\n"
                return md

            # Connection success
            if result.get("success"):
                name = result.get("name", "Database")
                return f"**Connected to {name} successfully!**"

            # Explain plan
            plan = result.get("plan")
            if plan:
                return f"**Execution Plan:**\n\n```\n{plan[:2000]}\n```"

            # Fallback — just dump what we have
            row_count = result.get("row_count")
            if row_count is not None:
                if sql:
                    return f"```sql\n{sql}\n```\n\n*Query returned {row_count} row(s).*"
                return f"*Query returned {row_count} row(s).*"

            # Raw content
            raw = result.get("raw", "")
            if raw:
                return str(raw)[:2000]

    return ""


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


def _summarize_tool_result(tool_name: str, result: dict) -> dict:
    if tool_name == "query_database":
        if result.get("multi_table"):
            return {
                "multi_table": True,
                "tables_queried": result.get("tables_queried", 0),
                "total_rows": result.get("row_count", 0),
                "error": None,
            }
        return {
            "sql": result.get("sql") or result.get("mongo_query", ""),
            "row_count": result.get("row_count", 0),
            "error": result.get("error") or result.get("execution_error"),
        }
    if tool_name == "connect_database":
        return {
            "success": result.get("success", False),
            "name": result.get("name", ""),
            "error": result.get("error"),
        }
    if tool_name == "discover_schema":
        tables = result.get("tables", {})
        collections = result.get("collections", {})
        table_names = result.get("table_names", [])
        # tables can be a dict (small DB) or missing (large DB uses table_names list)
        if isinstance(tables, dict):
            names = list(tables.keys())
        elif isinstance(tables, list):
            names = tables
        else:
            names = []
        names += list(collections.keys()) if isinstance(collections, dict) else []
        names += table_names
        return {
            "table_count": result.get("table_count", len(names)),
            "names": names[:50],
            "note": result.get("note", ""),
            "error": result.get("error"),
        }
    if tool_name == "list_connectors":
        return {"count": len(result.get("connectors", []))}
    if tool_name == "search_tables":
        return {
            "match_count": len(result.get("matches", [])),
            "keyword": result.get("keyword", ""),
            "error": result.get("error"),
        }
    if tool_name == "explain_query":
        plan = result.get("plan", "")
        return {
            "sql": result.get("sql", ""),
            "plan_preview": plan[:200] + "..." if len(plan) > 200 else plan,
            "error": result.get("error"),
        }
    if tool_name == "suggest_optimizations":
        return {
            "sql": result.get("sql", ""),
            "has_suggestions": bool(result.get("analysis", "")),
            "error": result.get("error"),
        }
    return {}


# ──────────────────────────────────────────────
# ENDPOINT
# ──────────────────────────────────────────────

@router.post("/chat")
async def agent_chat(request: ChatRequest, db: Session = Depends(get_db)):
    """Main agent chat — streams SSE events."""
    return StreamingResponse(
        _agent_stream(request, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
