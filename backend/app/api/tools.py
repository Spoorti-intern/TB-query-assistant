"""
Tool definitions and executors for the AI agent.
Each tool wraps an existing adapter (PostgreSQL, MySQL, MongoDB, Supabase)
so the LLM can decide which one to invoke at runtime.
"""

import json
import logging
import re
import ssl
import time
from urllib.parse import urlparse, unquote

from sqlalchemy import text, inspect, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.models.connector import Connector
from app.core.connector_manager import get_connector_engine
from app.core.crypto import encrypt_password, decrypt_password
from app.core.mongodb_adapter import get_mongodb_client
from app.core import nosql_adapters

logger = logging.getLogger(__name__)

# SQL databases that use SQLAlchemy engines
SQL_DATABASES = {"postgresql", "supabase", "mysql", "mssql", "sqlite", "oracle", "mariadb", "cockroachdb"}
# NoSQL databases with dedicated adapters
NOSQL_DATABASES = {"mongodb", "redis", "cassandra", "neo4j", "elasticsearch", "clickhouse", "influxdb", "couchdb"}


def _get_schema_name(connector_type: str):
    """Return the default schema name for a SQL database type."""
    if connector_type in ("postgresql", "supabase", "cockroachdb"):
        return "public"
    elif connector_type == "mssql":
        return "dbo"
    elif connector_type == "oracle":
        return None  # Oracle uses user schema by default
    else:
        return None  # MySQL, MariaDB, SQLite don't need schema qualifier


def _get_sql_dialect(connector_type: str) -> str:
    """Map connector type to SQL dialect name for query generation."""
    mapping = {
        "postgresql": "postgresql",
        "supabase": "postgresql",
        "cockroachdb": "postgresql",
        "mysql": "mysql",
        "mariadb": "mysql",
        "mssql": "mssql",
        "sqlite": "sqlite",
        "oracle": "oracle",
    }
    return mapping.get(connector_type, "postgresql")


def _get_connector(db: Session, connector_id) -> "Connector | None":
    """Fetch a connector by ID with fuzzy matching.

    The AI model sometimes:
    - Truncates UUIDs (prefix match)
    - Mutates 1-2 characters (fuzzy match)
    - Uses camelCase or strips dashes
    """
    cid = str(connector_id).strip()

    # Try exact match first
    result = db.query(Connector).filter(Connector.id == cid).first()
    if result:
        return result

    # Try prefix match (AI often truncates UUIDs)
    result = db.query(Connector).filter(Connector.id.like(f"{cid}%")).first()
    if result:
        return result

    # Fuzzy match — find closest UUID (tolerates 1-3 char mutations)
    all_connectors = db.query(Connector).all()
    if not all_connectors:
        return None

    best_match = None
    best_score = 0
    for c in all_connectors:
        # Count matching characters at same positions
        matches = sum(1 for a, b in zip(cid, c.id) if a == b)
        score = matches / max(len(cid), len(c.id)) if max(len(cid), len(c.id)) > 0 else 0
        if score > best_score:
            best_score = score
            best_match = c

    # Accept if >90% character match (allows ~3 mutations in a 36-char UUID)
    if best_match and best_score > 0.90:
        logger.info("Fuzzy matched connector_id '%s' → '%s' (%.0f%% match)", cid, best_match.id, best_score * 100)
        return best_match

    return None


def _groq_call_with_retry(groq_client, **kwargs):
    """Call Groq API with retry + model rotation on rate limit."""
    kwargs.pop("chat_template_kwargs", None)
    primary = kwargs.get("model", "openai/gpt-oss-20b")
    models = [primary] + [m for m in ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"] if m != primary]
    for model in models:
        kwargs["model"] = model
        for attempt in range(2):
            try:
                return groq_client.chat.completions.create(**kwargs)
            except Exception as exc:
                if "429" in str(exc) or "rate_limit" in str(exc):
                    if attempt == 0:
                        # Extract wait time from error — keep it short to avoid buffering
                        wm = re.search(r'try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s', str(exc))
                        if wm:
                            mins = int(wm.group(1) or 0)
                            secs = float(wm.group(2) or 5)
                            wait = min(int(mins * 60 + secs) + 1, 30)  # Cap at 30s
                        else:
                            wait = 10
                        time.sleep(wait)
                        continue
                    else:
                        logger.warning(f"Rate limit on {model}, trying next model")
                        break
                raise
    raise Exception("All models rate limited. Please wait a minute.")


# ──────────────────────────────────────────────
# TOOL SCHEMAS  (OpenAI-compatible function calling)
# ──────────────────────────────────────────────

def _make_tool(name: str, description: str, properties: dict, required: list) -> dict:
    """Helper to create a tool schema dict."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }

# Base tool definitions — MINIMAL to save tokens on free Groq tier
_TOOL_DEFS = [
    {
        "name": "query_database",
        "description": "Query a database. Prefer passing `sql` directly when you know the schema; fall back to `question` for natural language.",
        "properties": {
            "connector_id": {"type": "string", "description": "DB connector ID"},
            "sql": {"type": "string", "description": "Direct SQL SELECT query to execute (preferred when you know the schema)"},
            "question": {"type": "string", "description": "Natural language question (used when you don't know the schema yet)"},
        },
        "required": ["connector_id"],
    },
    {
        "name": "connect_database",
        "description": "Connect to a new database via URI.",
        "properties": {
            "connection_string": {"type": "string", "description": "Connection URI"},
            "name": {"type": "string", "description": "Friendly name"},
        },
        "required": ["connection_string"],
    },
    {
        "name": "discover_schema",
        "description": "List tables/columns in a database.",
        "properties": {
            "connector_id": {"type": "string", "description": "DB connector ID"},
        },
        "required": ["connector_id"],
    },
    # Extended tools — still registered but with minimal descriptions
    {
        "name": "list_connectors",
        "description": "List connected databases.",
        "properties": {},
        "required": [],
    },
    {
        "name": "search_tables",
        "description": "Search tables/columns by keyword.",
        "properties": {
            "connector_id": {"type": "string", "description": "DB connector ID"},
            "keyword": {"type": "string", "description": "Search term"},
        },
        "required": ["connector_id", "keyword"],
    },
    {
        "name": "explain_query",
        "description": "Get SQL execution plan.",
        "properties": {
            "connector_id": {"type": "string", "description": "DB connector ID"},
            "sql": {"type": "string", "description": "SQL query"},
        },
        "required": ["connector_id", "sql"],
    },
    {
        "name": "suggest_optimizations",
        "description": "Suggest query optimizations.",
        "properties": {
            "connector_id": {"type": "string", "description": "DB connector ID"},
            "sql": {"type": "string", "description": "The original SQL query"},
            "explain_plan": {"type": "string", "description": "The EXPLAIN ANALYZE output"},
        },
        "required": ["connector_id", "sql", "explain_plan"],
    },
]

def _snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])

def _build_tool_schemas():
    """Build tool schemas — snake_case only.
    Name normalization happens in the executor via _normalize_tool_name."""
    return [
        _make_tool(defn["name"], defn["description"], defn["properties"], defn["required"])
        for defn in _TOOL_DEFS
    ]

TOOL_SCHEMAS = _build_tool_schemas()

# Lightweight version — 6 core tools sent to LLM to save tokens
TOOL_SCHEMAS_LITE = [s for s in TOOL_SCHEMAS if s["function"]["name"] in (
    "query_database", "connect_database", "discover_schema", "search_tables",
    "explain_query", "suggest_optimizations",
)]


# ──────────────────────────────────────────────
# TOOL EXECUTORS
# ──────────────────────────────────────────────

def _normalize_args(args: dict) -> dict:
    """Convert camelCase param names to snake_case so tool functions always get expected keys."""
    normalized = {}
    for k, v in args.items():
        # camelCase → snake_case
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower()
        normalized[snake] = v
    return normalized


def execute_tool(tool_name: str, args: dict, db: Session) -> dict:
    """Dispatch a tool call to its executor and return the result dict."""
    logger.info("execute_tool: name=%r, raw_args=%r", tool_name, args)
    # Normalize both tool name and parameter names
    name = _snake_to_camel(tool_name)  # check if it's a camelCase alias
    # Map camelCase tool names back to snake_case
    _camel_to_snake_map = {
        "listConnectors": "list_connectors",
        "connectDatabase": "connect_database",
        "discoverSchema": "discover_schema",
        "queryDatabase": "query_database",
        "searchTables": "search_tables",
        "explainQuery": "explain_query",
        "suggestOptimizations": "suggest_optimizations",
    }
    canonical = _camel_to_snake_map.get(tool_name, tool_name)
    args = _normalize_args(args)
    logger.info("execute_tool: canonical=%r, normalized_args=%r", canonical, args)

    try:
        if canonical == "list_connectors":
            return _tool_list_connectors(db)
        elif canonical == "connect_database":
            return _tool_connect_database(db, **args)
        elif canonical == "discover_schema":
            return _tool_discover_schema(db, **args)
        elif canonical == "query_database":
            return _tool_query_database(db, **args)
        elif canonical == "search_tables":
            return _tool_search_tables(db, **args)
        elif canonical == "explain_query":
            return _tool_explain_query(db, **args)
        elif canonical == "suggest_optimizations":
            return _tool_suggest_optimizations(db, **args)
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as exc:
        logger.exception("Tool %s failed", tool_name)
        return {"error": str(exc)}


# ── list_connectors ──────────────────────────

def _tool_list_connectors(db: Session) -> dict:
    connectors = db.query(Connector).all()
    if not connectors:
        return {
            "connectors": [],
            "message": "No database connections found. Paste a connection string to connect a database.",
        }
    return {
        "connectors": [
            {
                "id": c.id,
                "name": c.name,
                "type": c.connector_type,
                "host": c.host,
                "database": c.database,
                "status": c.status,
            }
            for c in connectors
        ]
    }


# ── connect_database ─────────────────────────

_MSSQL_SYSTEM_TABLES = {
    "spt_fallback_db", "spt_fallback_dev", "spt_fallback_usd", "spt_fallback_usg",
    "spt_monitor", "spt_values",
    "MSreplication_options", "MSreplication_subscriptions",
    "sysdiagrams", "dtproperties", "sysconstraints", "syssegments",
    "trace_xe_action_map", "trace_xe_event_map",
}
_MSSQL_SYSTEM_DBS = {"master", "tempdb", "model", "msdb"}


def _tool_connect_database(db: Session, connection_string: str, name: str = None) -> dict:
    parsed = _parse_connection_string(connection_string)
    if not parsed:
        return {"success": False, "error": "Could not parse connection string. Supported: postgresql://, mysql://, mariadb://, mssql://, mongodb+srv://, redis://, bolt:// (Neo4j), cassandra://, elasticsearch://, clickhouse://, influxdb://, couchdb://, oracle://, cockroachdb://, sqlite:///path"}

    db_type = parsed["type"]
    host = parsed["host"]
    port = parsed["port"]
    database = parsed["database"]
    username = parsed["username"]
    password = parsed["password"]

    # ── MSSQL: if connected to system DB (master/tempdb), auto-discover real user DB ──
    if db_type == "mssql" and (not database or database.lower() in _MSSQL_SYSTEM_DBS):
        discovered_db = None

        # Method 1: Check if another connector on the same server has a user DB
        existing_good = (
            db.query(Connector)
            .filter(Connector.host == host, Connector.port == port)
            .all()
        )
        for eg in existing_good:
            if eg.database and eg.database.lower() not in _MSSQL_SYSTEM_DBS:
                discovered_db = eg.database
                logger.info(f"MSSQL: Found existing user database '{discovered_db}' from connector '{eg.name}'")
                break

        # Method 2: Query sys.databases via the existing connector's engine
        if not discovered_db:
            try:
                from urllib.parse import quote as url_quote
                discover_uri = f"mssql+pymssql://{url_quote(username, safe='')}:{url_quote(password, safe='')}@{host}:{port}/master"
                temp_engine = create_engine(discover_uri, connect_args={"login_timeout": 10})
                with temp_engine.connect() as conn:
                    rows = conn.execute(text(
                        "SELECT name FROM sys.databases "
                        "WHERE name NOT IN ('master','tempdb','model','msdb') "
                        "AND state_desc = 'ONLINE' "
                        "ORDER BY create_date DESC"
                    )).fetchall()
                temp_engine.dispose()
                user_dbs = [r[0] for r in rows]
                if user_dbs:
                    discovered_db = user_dbs[0]
                    logger.info(f"MSSQL: Discovered user databases: {user_dbs[:5]}, selected '{discovered_db}'")
            except Exception as e:
                logger.warning(f"MSSQL auto-discover databases failed: {e}")

        if discovered_db:
            database = discovered_db
            parsed["database"] = database
            # Rebuild the connection string with the real database
            connection_string = re.sub(
                r'(/)[^/?]*(\?|$)',
                rf'\g<1>{database}\2',
                connection_string
            )

    # Check duplicates
    existing = (
        db.query(Connector)
        .filter(Connector.host == host, Connector.port == port, Connector.database == database)
        .first()
    )

    # Also check if any connector on this host is stuck on a system DB — migrate it
    if db_type == "mssql" and database and database.lower() not in _MSSQL_SYSTEM_DBS:
        stuck_connectors = (
            db.query(Connector)
            .filter(Connector.host == host, Connector.port == port)
            .all()
        )
        for sc in stuck_connectors:
            if sc.database and sc.database.lower() in _MSSQL_SYSTEM_DBS:
                logger.info(f"Migrating connector '{sc.name}' from '{sc.database}' to '{database}'")
                sc.database = database
                sc.name = f"Mssql — {database}@{host}"
                db.commit()
                if not existing:
                    existing = sc

    if existing:
        return {
            "success": True,
            "connector_id": existing.id,
            "name": existing.name,
            "type": existing.connector_type,
            "already_exists": True,
            "message": f"Already connected as '{existing.name}' (ID {existing.id})",
        }

    auto_name = name or f"{db_type.title()} — {database}@{host}"
    encrypted_pw = encrypt_password(password) if password else ""

    connector = Connector(
        name=auto_name,
        connector_type=db_type,
        host=host,
        port=port,
        database=database,
        username=username,
        password=encrypted_pw,
        status="pending",
    )
    db.add(connector)
    db.commit()
    db.refresh(connector)

    # Test connection
    try:
        if db_type == "mongodb":
            client = get_mongodb_client(connector)
            client.admin.command("ping")
            client.close()
        else:
            engine = get_connector_engine(connector)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()

        connector.status = "connected"
        db.commit()
        return {
            "success": True,
            "connector_id": connector.id,
            "name": connector.name,
            "type": db_type,
            "message": f"Successfully connected to {auto_name}",
        }
    except Exception as exc:
        connector.status = "connection_failed"
        db.commit()
        return {"success": False, "connector_id": connector.id, "error": str(exc)}


# ── discover_schema ──────────────────────────

def _tool_discover_schema(db: Session, connector_id: str = None) -> dict:
    if not connector_id or connector_id in ("null", "None", "undefined", ""):
        return {"error": "No database connected. Please select a connector first."}
    connector = _get_connector(db, connector_id)
    if not connector:
        return {"error": f"Connector '{connector_id}' not found"}

    try:
        if connector.connector_type == "mongodb":
            client = get_mongodb_client(connector)
            mongo_db = client[connector.database]
            collections = mongo_db.list_collection_names()
            schema = {}
            for coll_name in collections[:20]:
                coll = mongo_db[coll_name]
                sample = coll.find_one()
                fields = list(sample.keys()) if sample else []
                schema[coll_name] = {
                    "fields": fields,
                    "count": coll.estimated_document_count(),
                }
            client.close()
            return {"type": "mongodb", "database": connector.database, "collections": schema}

        # NoSQL adapters
        nosql_discoverers = {
            "redis": nosql_adapters.discover_redis_schema,
            "cassandra": nosql_adapters.discover_cassandra_schema,
            "neo4j": nosql_adapters.discover_neo4j_schema,
            "elasticsearch": nosql_adapters.discover_elasticsearch_schema,
            "clickhouse": nosql_adapters.discover_clickhouse_schema,
            "influxdb": nosql_adapters.discover_influxdb_schema,
            "couchdb": nosql_adapters.discover_couchdb_schema,
        }
        if connector.connector_type in nosql_discoverers:
            return nosql_discoverers[connector.connector_type](connector)

        # SQL databases (PostgreSQL, MySQL, MSSQL, SQLite, Oracle, MariaDB, CockroachDB)
        else:
            engine = get_connector_engine(connector)
            inspector = inspect(engine)
            schema_name = _get_schema_name(connector.connector_type)
            table_names = inspector.get_table_names(schema=schema_name)

            # Filter out known system/internal tables and temp/migration tables
            if connector.connector_type == "mssql":
                table_names = [
                    t for t in table_names
                    if t not in _MSSQL_SYSTEM_TABLES
                    and not t.startswith("sys")
                    and not t.startswith("__")       # EF migrations
                    and not t.startswith("_Temp")    # temp tables
                    and not t.startswith("MSreplication")
                    and not t.startswith("spt_")
                    and not t.startswith("trace_xe_")
                ]

            # For large databases (>50 tables), return only table names to avoid token overflow
            if len(table_names) > 50:
                # For large DBs, sample a few tables to find ones with data
                tables_with_data = []
                try:
                    with engine.connect() as conn:
                        for tbl in table_names[:100]:  # Check up to 100 tables
                            try:
                                sq = f"SELECT TOP 1 1 FROM [{tbl}]" if connector.connector_type == "mssql" else f"SELECT 1 FROM \"{tbl}\" LIMIT 1"
                                row = conn.execute(text(sq)).fetchone()
                                if row:
                                    tables_with_data.append(tbl)
                                if len(tables_with_data) >= 20:
                                    break
                            except Exception:
                                continue
                except Exception:
                    pass

                engine.dispose()
                return {
                    "type": connector.connector_type,
                    "database": connector.database,
                    "table_count": len(table_names),
                    "table_names": table_names,
                    "tables_with_data": tables_with_data,
                    "note": f"Large database with {len(table_names)} tables. {len(tables_with_data)} tables confirmed to have data. Use search_tables to find relevant tables, then query_database for specific questions.",
                }

            # For small DBs, check which tables have data
            tables = {}
            tables_with_data = []
            for tbl in table_names:
                cols = inspector.get_columns(tbl, schema=schema_name)
                tables[tbl] = {
                    "columns": [{"name": c["name"], "type": str(c["type"])} for c in cols]
                }
            # Quick row count check for small DBs
            try:
                with engine.connect() as conn:
                    for tbl in table_names:
                        try:
                            sq = f"SELECT TOP 1 1 FROM [{tbl}]" if connector.connector_type == "mssql" else f"SELECT 1 FROM \"{tbl}\" LIMIT 1"
                            row = conn.execute(text(sq)).fetchone()
                            if row:
                                tables_with_data.append(tbl)
                        except Exception:
                            continue
            except Exception:
                pass

            engine.dispose()
            result = {"type": connector.connector_type, "database": connector.database, "tables": tables}
            if tables_with_data:
                result["tables_with_data"] = tables_with_data
            return result
    except Exception as exc:
        return {"error": str(exc)}


# ── query_database ───────────────────────────

def _tool_query_database(db: Session, connector_id: str = None, question: str = "", sql: str = "") -> dict:
    from app.core.llm_client import get_llm_client

    logger.info("query_database called with connector_id=%r, sql=%r, question=%r",
                connector_id, sql[:100] if sql else "", question[:100] if question else "")

    if not connector_id or connector_id in ("null", "None", "undefined", ""):
        return {"error": "No database connected. Please select a database connector first or paste a connection string to connect one."}

    # At least one of sql or question must be provided
    if (not sql or not sql.strip()) and (not question or not question.strip()):
        return {"error": "No question or SQL provided. Please type a question, table name, SQL query, or anything data-related."}

    connector = _get_connector(db, connector_id)
    if not connector:
        return {"error": f"Connector '{connector_id}' not found. Use list_connectors to see available databases."}

    ctype = connector.connector_type

    # ── DIRECT SQL MODE ──
    # When the agent passes `sql` directly, skip the internal LLM call and execute immediately.
    if sql and sql.strip():
        raw_sql = sql.strip().replace("```sql", "").replace("```", "").strip()
        # Validate it's a SELECT
        sql_upper = raw_sql.upper().lstrip()
        if not sql_upper.startswith(("SELECT", "WITH")):
            return {"error": f"Only SELECT queries allowed. Got: {raw_sql[:50]}..."}
        # Check for forbidden operations
        forbidden = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"}
        tokens = set(sql_upper.split())
        blocked = forbidden & tokens
        if blocked:
            return {"error": f"Blocked dangerous operation: {', '.join(blocked)}. Only SELECT allowed."}

        # Execute directly
        if ctype in ("mongodb",) or ctype in NOSQL_DATABASES:
            # NoSQL can't take raw SQL — fall through to question mode
            if not question or not question.strip():
                question = raw_sql
        else:
            engine = get_connector_engine(connector)
            dialect = _get_sql_dialect(ctype)
            try:
                with engine.connect() as conn:
                    if dialect == "postgresql":
                        conn.execute(text("SET statement_timeout = '30s'"))
                        conn.execute(text("SET TRANSACTION READ ONLY"))
                    elif dialect == "mysql":
                        conn.execute(text("SET SESSION MAX_EXECUTION_TIME=30000"))
                    elif dialect == "mssql":
                        conn.execute(text("SET LOCK_TIMEOUT 30000"))
                    result = conn.execute(text(raw_sql))
                    columns = list(result.keys())
                    rows = [list(r) for r in result.fetchmany(100)]
                    for i, row in enumerate(rows):
                        for j, val in enumerate(row):
                            if hasattr(val, "isoformat"):
                                rows[i][j] = val.isoformat()
                            elif not isinstance(val, (str, int, float, bool, type(None))):
                                rows[i][j] = str(val)
                engine.dispose()
                return {"sql": raw_sql, "columns": columns, "rows": rows, "row_count": len(rows), "direct_sql": True}
            except Exception as exc:
                engine.dispose()
                return {"sql": raw_sql, "execution_error": str(exc), "direct_sql": True}

    groq_client = get_llm_client(max_retries=0)

    if ctype == "mongodb":
        return _exec_mongodb(connector, question, groq_client)
    elif ctype in NOSQL_DATABASES:
        return _exec_nosql(connector, question, groq_client)
    else:
        return _exec_sql(connector, question, groq_client)


def _exec_sql(connector, question: str, groq) -> dict:
    engine = get_connector_engine(connector)

    # Schema discovery
    inspector = inspect(engine)
    schema_name = _get_schema_name(connector.connector_type)
    table_names = inspector.get_table_names(schema=schema_name)

    if not table_names:
        engine.dispose()
        return {"error": "Database has no tables yet. Create some tables first."}

    dialect = _get_sql_dialect(connector.connector_type)

    # ── MULTI-TABLE QUERY DETECTION ──
    # Detect "first N records from each/every/all table(s)" patterns
    q_lower = question.lower()
    multi_table_patterns = [
        r"(?:first|top)\s+(\d+)\s+(?:records?|rows?)\s+(?:from|of)\s+(?:each|every|all)\s+table",
        r"(?:display|show|get)\s+(?:first|top)?\s*(\d+)?\s*(?:records?|rows?)?\s*(?:from|of)\s+(?:each|every|all)\s+table",
        r"(?:each|every|all)\s+table.*?(?:first|top)\s+(\d+)",
        r"(?:first|top)\s+(\d+).*(?:each|every|all)\s+table",
        r"(?:records?|rows?|data)\s+from\s+(?:each|every|all)\s+table",
        r"count\s+(?:of|for|in|from|per)\s+(?:each|every|all)\s+table",
        r"(?:each|every|all)\s+table.*?count",
        r"how\s+many\s+(?:rows?|records?)\s+(?:in|from|per)\s+(?:each|every|all)\s+table",
        r"data\s+from\s+(?:each|every|all)\b",
        r"sample\s+data\s+from\s+(?:each|every|all)\b",
        r"(?:show|display|get)\s+.*?from\s+(?:each|every|all)\b",
    ]
    multi_match = None
    row_limit = 10  # default
    for pat in multi_table_patterns:
        m = re.search(pat, q_lower)
        if m:
            multi_match = m
            # Extract the number if captured
            for g in m.groups():
                if g and g.isdigit():
                    row_limit = int(g)
                    break
            break

    if multi_match:
        # Detect if this is a COUNT query vs data query
        is_count_query = bool(re.search(r"\bcount\b", q_lower))
        # Execute on each table (up to 20 for counts, 15 for data)
        max_tables = 20 if is_count_query else 15
        sample_tables = table_names[:max_tables] if len(table_names) > max_tables else table_names
        all_results = []
        for tbl in sample_tables:
            try:
                if is_count_query:
                    sql = f"SELECT COUNT(*) AS row_count FROM [{tbl}]" if dialect == "mssql" else f"SELECT COUNT(*) AS row_count FROM {tbl}"
                elif dialect == "mssql":
                    sql = f"SELECT TOP {row_limit} * FROM [{tbl}]"
                elif dialect == "oracle":
                    sql = f"SELECT * FROM {tbl} FETCH FIRST {row_limit} ROWS ONLY"
                else:
                    sql = f"SELECT * FROM {tbl} LIMIT {row_limit}"
                with engine.connect() as conn:
                    if dialect == "mssql":
                        conn.execute(text("SET LOCK_TIMEOUT 10000"))
                    result = conn.execute(text(sql))
                    columns = list(result.keys())
                    rows = [list(r) for r in result.fetchmany(row_limit)]
                    for i, row in enumerate(rows):
                        for j, val in enumerate(row):
                            if hasattr(val, "isoformat"):
                                rows[i][j] = val.isoformat()
                            elif not isinstance(val, (str, int, float, bool, type(None))):
                                rows[i][j] = str(val)
                    all_results.append({
                        "table": tbl,
                        "sql": sql,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                    })
            except Exception as exc:
                all_results.append({"table": tbl, "error": str(exc), "row_count": 0})
        engine.dispose()
        # Format multi-table results
        return {
            "multi_table": True,
            "tables_queried": len(all_results),
            "total_tables": len(table_names),
            "results": all_results,
            "row_count": sum(r.get("row_count", 0) for r in all_results),
        }

    # Fuzzy string similarity helper (handles typos like "acounts" → "Accounts")
    def _fuzzy_ratio(a: str, b: str) -> float:
        a, b = a.lower(), b.lower()
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.85
        i = j = matches = 0
        while i < len(a) and j < len(b):
            if a[i] == b[j]:
                matches += 1
                i += 1
                j += 1
            elif j + 1 < len(b) and a[i] == b[j + 1]:
                j += 1
            elif i + 1 < len(a) and a[i + 1] == b[j]:
                i += 1
            else:
                i += 1
                j += 1
        return matches / max(len(a), len(b))

    # For large databases, pre-filter tables by keyword matching from the question
    exact_table_match = None
    if len(table_names) > 50:
        # Step 1: Check if the input IS a table name (exact match)
        q_stripped = question.strip().strip('"').strip("'").strip('`').strip('[]')
        q_words_raw = [w.strip() for w in re.split(r'[,\s]+', q_stripped) if w.strip()]

        for tbl in table_names:
            tbl_lower = tbl.lower()
            if tbl_lower == q_stripped.lower():
                exact_table_match = tbl
                break
            for w in q_words_raw:
                if tbl_lower == w.lower():
                    exact_table_match = tbl
                    break
            if exact_table_match:
                break

        # Step 1b: Fuzzy match — handle typos (e.g. "acounts" → "Accounts")
        if not exact_table_match:
            best_score, best_match = 0, None
            for w in q_words_raw:
                if len(w) < 3:
                    continue
                for tbl in table_names:
                    score = _fuzzy_ratio(w, tbl)
                    if score > best_score and score >= 0.7:
                        best_score = score
                        best_match = tbl
            if best_match:
                exact_table_match = best_match

        if exact_table_match:
            # User typed an exact table name — use it directly
            target_tables = [exact_table_match]
        else:
            # Step 2: Keyword matching with synonyms
            q_words = set(w.lower() for w in re.findall(r'\w+', question) if len(w) > 2)
            synonym_map = {
                "sales": ["sales", "invoice", "order", "billing"],
                "invoice": ["invoice", "sales", "billing"],
                "purchase": ["purchase", "po", "supplier", "vendor"],
                "customer": ["customer", "party", "client"],
                "product": ["product", "item", "stock", "inventory"],
                "employee": ["employee", "hr", "salary", "staff"],
                "account": ["account", "voucher", "ledger", "journal"],
                "stock": ["stock", "inventory", "product", "warehouse"],
                "payment": ["payment", "cheque", "bank", "receipt"],
                "order": ["order", "sales", "purchase"],
            }
            expanded_words = set(q_words)
            for word in q_words:
                for key, synonyms in synonym_map.items():
                    if word in synonyms or key in word:
                        expanded_words.update(synonyms)
                    # Fuzzy match synonym keys (handle typos like "acounts" → "account")
                    elif len(word) >= 4 and _fuzzy_ratio(word, key) >= 0.7:
                        expanded_words.update(synonyms)

            # Filter tables that match any keyword
            matched_tables = [t for t in table_names if any(kw in t.lower() for kw in expanded_words)]

            # If no matches, try broader matching (any 3+ char substring)
            if not matched_tables:
                matched_tables = [t for t in table_names if any(kw in t.lower() for kw in q_words)]

            # Still no matches? Use common business tables
            if not matched_tables:
                common = ["Sales", "SalesInvoice", "Product", "Customer", "Accounts", "Party", "Stock"]
                matched_tables = [t for t in table_names if t in common]

            target_tables = matched_tables[:10]
    else:
        target_tables = table_names

    schema_parts = []
    for tbl in target_tables:
        cols = inspector.get_columns(tbl, schema=schema_name)
        if len(target_tables) > 5:
            # Compact format for large DBs: just column names
            col_names = ", ".join(c['name'] for c in cols)
            schema_parts.append(f"{tbl}({col_names})")
        else:
            col_lines = [f"  {c['name']} ({c['type']})" for c in cols]
            schema_parts.append(f"TABLE: {tbl}\n" + "\n".join(col_lines))
    schema_text = "\n".join(schema_parts)

    dialect = _get_sql_dialect(connector.connector_type)

    # Dialect-specific rules
    dialect_rules = {
        "postgresql": "- Use ILIKE for case-insensitive search\n- Use LIMIT for row limiting\n- Use NOW() for current time",
        "mysql": "- Use LOWER()+LIKE for case-insensitive\n- Use LIMIT for row limiting\n- Use NOW() for current time",
        "mssql": "- Use TOP instead of LIMIT\n- Use square brackets for reserved words\n- Use GETDATE() not NOW()\n- Use CONVERT for type casting",
        "sqlite": "- Use LIKE for case-insensitive (SQLite LIKE is case-insensitive by default)\n- Use LIMIT for row limiting\n- Use datetime('now') for current time",
        "oracle": "- Use FETCH FIRST N ROWS ONLY instead of LIMIT\n- Use SYSDATE for current time\n- Use UPPER()+LIKE for case-insensitive\n- Use NVL instead of COALESCE\n- Table names may be uppercase",
    }
    rules = dialect_rules.get(dialect, dialect_rules["postgresql"])

    # Generate SQL — handles ANY input type
    prompt = (
        f"You are a SQL expert. Given this database schema:\n\n{schema_text}\n\n"
        f"The user typed: {question}\n\n"
        f"Interpret the user's input and generate a valid {dialect.upper()} SQL query.\n\n"
        "The user's input could be ANY of these — handle ALL:\n"
        "- A natural language question: 'How many customers?' → SELECT COUNT(*) FROM customers\n"
        "- A table name: 'IPOS_SalesDetail' → SELECT TOP 50 * FROM IPOS_SalesDetail\n"
        "- Column names: 'Name, Price' → find the table with these columns and SELECT Name, Price FROM that_table\n"
        "- A single word: 'customers' → SELECT TOP 50 * FROM customers\n"
        "- Raw SQL: 'SELECT TOP 10 * FROM orders' → use as-is if valid\n"
        "- Vague reference: 'sales data', 'invoice table' → find the matching table and SELECT from it\n"
        "- Filter: 'orders where amount > 1000' → SELECT * FROM orders WHERE amount > 1000\n"
        "- Column + table: 'customer name from orders' → SELECT customer_name FROM orders\n\n"
        "Rules:\n"
        "- Return ONLY the SQL query, nothing else\n"
        "- Only SELECT statements (read-only)\n"
        "- Use tables and columns from the schema above\n"
        f"- Dialect: {dialect.upper()}\n"
        f"{rules}\n"
        "- Default to TOP 50 or LIMIT 50 if the user didn't specify a count\n"
        "- If the input looks like raw SQL, validate it uses tables from the schema and return it\n"
        "- If the input is just a table name, return SELECT * with a limit\n"
        "- Match table/column names case-insensitively against the schema\n"
    )
    resp = _groq_call_with_retry(groq,
        model="openai/gpt-4.1-mini-fast",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    sql = (resp.choices[0].message.content or "").strip()
    # Strip <think>...</think> tags from reasoning models (non-greedy)
    sql = re.sub(r"<think>[\s\S]*?</think>", "", sql).strip()
    # Also strip unclosed <think> tags (model didn't close it)
    sql = re.sub(r"<think>[\s\S]*$", "", sql).strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()
    # Strip any leading text before the actual SQL
    sql_match = re.search(r'(SELECT|WITH)\b', sql, re.IGNORECASE)
    if sql_match and sql_match.start() > 0:
        sql = sql[sql_match.start():].strip()

    if not sql or sql.lower().startswith(("i'm sorry", "i cannot", "i can't", "sorry", "unfortunately")):
        engine.dispose()
        return {"error": f"I couldn't understand that as a database query. Try rephrasing — for example: 'Show me all data from {target_tables[0] if target_tables else 'customers'}' or 'How many rows in {target_tables[1] if len(target_tables) > 1 else 'orders'}?'"}

    # Must start with SELECT or WITH (CTE)
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith(("SELECT", "WITH")):
        engine.dispose()
        return {"error": f"Invalid SQL generated (not a SELECT). Available tables: {', '.join(target_tables[:20])}"}

    # Validate read-only
    forbidden = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"}
    tokens = set(sql_upper.split())
    blocked = forbidden & tokens
    if blocked:
        engine.dispose()
        return {"error": f"Blocked dangerous operation: {', '.join(blocked)}. Only SELECT allowed."}

    # Execute with statement timeout
    try:
        with engine.connect() as conn:
            if dialect == "postgresql":
                conn.execute(text("SET statement_timeout = '30s'"))
                conn.execute(text("SET TRANSACTION READ ONLY"))
            elif dialect == "mysql":
                conn.execute(text("SET SESSION MAX_EXECUTION_TIME=30000"))
            elif dialect == "mssql":
                conn.execute(text("SET LOCK_TIMEOUT 30000"))
            elif dialect == "oracle":
                pass  # Oracle uses profile-based timeouts
            elif dialect == "sqlite":
                pass  # SQLite uses busy_timeout from connect_args
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [list(r) for r in result.fetchmany(100)]
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    if hasattr(val, "isoformat"):
                        rows[i][j] = val.isoformat()
                    elif not isinstance(val, (str, int, float, bool, type(None))):
                        rows[i][j] = str(val)
        engine.dispose()
        return {"sql": sql, "columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as exc:
        err_str = str(exc)
        # On column errors, find the actual columns and auto-retry with SELECT *
        if "Invalid column name" in err_str or "Unknown column" in err_str or "does not exist" in err_str:
            # Extract table name from the SQL (handle [brackets] and dbo.prefix)
            tbl_match = re.search(r'FROM\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?', sql, re.IGNORECASE)
            if tbl_match:
                tbl_name = tbl_match.group(1)
                try:
                    # Auto-retry with SELECT * from the same table
                    fallback_sql = f"SELECT TOP 50 * FROM [{tbl_name}]" if dialect == "mssql" else f"SELECT * FROM {tbl_name} LIMIT 50"
                    with engine.connect() as conn2:
                        if dialect == "mssql":
                            conn2.execute(text("SET LOCK_TIMEOUT 30000"))
                        result2 = conn2.execute(text(fallback_sql))
                        columns2 = list(result2.keys())
                        rows2 = [list(r) for r in result2.fetchmany(100)]
                        for i, row in enumerate(rows2):
                            for j, val in enumerate(row):
                                if hasattr(val, "isoformat"):
                                    rows2[i][j] = val.isoformat()
                                elif not isinstance(val, (str, int, float, bool, type(None))):
                                    rows2[i][j] = str(val)
                    engine.dispose()
                    return {
                        "sql": fallback_sql,
                        "columns": columns2,
                        "rows": rows2,
                        "row_count": len(rows2),
                        "note": f"Original query had invalid columns. Auto-corrected to SELECT *. Actual columns: {', '.join(columns2)}"
                    }
                except Exception:
                    pass
            # If auto-retry also fails, return error with column hints
            hint = ""
            try:
                insp = inspect(engine)
                all_tables = insp.get_table_names(schema=schema_name)
                for tbl in all_tables:
                    if tbl.lower() in sql.lower().replace("[", "").replace("]", ""):
                        cols = insp.get_columns(tbl, schema=schema_name)
                        col_names = [c["name"] for c in cols]
                        hint = f"\nACTUAL COLUMNS in {tbl}: {', '.join(col_names)}"
                        break
            except Exception:
                pass
            engine.dispose()
            return {"sql": sql, "execution_error": err_str + hint}
        engine.dispose()
        return {"sql": sql, "execution_error": err_str}


def _exec_mongodb(connector, question: str, groq) -> dict:
    from bson import ObjectId

    try:
        client = get_mongodb_client(connector)
        mongo_db = client[connector.database]
        collections = mongo_db.list_collection_names()
    except Exception as exc:
        try:
            client.close()
        except Exception:
            pass
        return {"error": f"MongoDB connection failed: {str(exc)[:200]}"}

    if not collections:
        client.close()
        return {"error": "Database has no collections."}

    # Schema from sampling
    schema_parts = []
    for coll_name in collections[:20]:
        coll = mongo_db[coll_name]
        sample = coll.find_one()
        count = coll.estimated_document_count()
        if sample:
            fields = [f"  {k}: {type(v).__name__}" for k, v in sample.items()]
            schema_parts.append(f"COLLECTION: {coll_name} ({count} docs)\n" + "\n".join(fields))
    schema_text = "\n\n".join(schema_parts)

    # Check if input is an exact collection name
    q_stripped = question.strip().strip('"').strip("'").strip('`')
    for coll_name in collections:
        if coll_name.lower() == q_stripped.lower():
            question = f"Show all data from the {coll_name} collection"
            break

    prompt = (
        f"You are a MongoDB expert. Schema:\n\n{schema_text}\n\n"
        f"The user typed: {question}\n\n"
        "Interpret the input (could be a question, collection name, field names, or any data reference) "
        "and generate a MongoDB query.\n\n"
        'Return ONLY valid JSON: {"collection":"name","operation":"find|count|aggregate","query":{},"projection":{},"sort":{},"limit":50}\n'
        'For aggregation: {"collection":"name","operation":"aggregate","query":[pipeline]}\n'
    )
    resp = _groq_call_with_retry(groq,
        model="openai/gpt-4.1-mini-fast",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    raw = re.sub(r"<think>[\s\S]*$", "", raw).strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    # Extract JSON if there's leading text
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        raw = json_match.group(0)
    try:
        qdata = json.loads(raw)
    except json.JSONDecodeError:
        client.close()
        return {"error": "Failed to generate a valid MongoDB query."}

    coll_name = qdata.get("collection", "")
    operation = qdata.get("operation", "find")
    query = qdata.get("query", {})
    projection = qdata.get("projection")
    sort = qdata.get("sort")
    limit = qdata.get("limit", 50)

    def serialize(val):
        if isinstance(val, ObjectId):
            return str(val)
        if hasattr(val, "isoformat"):
            return val.isoformat()
        if isinstance(val, bytes):
            return val.hex()
        return val

    try:
        coll = mongo_db[coll_name]
        if operation == "count":
            cnt = coll.count_documents(query if isinstance(query, dict) else {})
            client.close()
            return {"mongo_query": raw, "columns": ["count"], "rows": [[cnt]], "row_count": 1}
        elif operation == "aggregate":
            pipeline = query if isinstance(query, list) else [query]
            docs = list(coll.aggregate(pipeline))
        else:
            cursor = coll.find(query or {}, projection)
            if sort and isinstance(sort, dict):
                cursor = cursor.sort(list(sort.items()))
            cursor = cursor.limit(limit)
            docs = list(cursor)

        client.close()

        if docs:
            columns = list(docs[0].keys())
            rows = [[serialize(doc.get(c)) for c in columns] for doc in docs]
        else:
            columns, rows = [], []
        return {"mongo_query": raw, "columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as exc:
        client.close()
        return {"mongo_query": raw, "execution_error": str(exc)}


def _exec_nosql(connector, question: str, groq) -> dict:
    """AI-driven query execution for NoSQL databases (Redis, Cassandra, Neo4j, Elasticsearch, ClickHouse, InfluxDB, CouchDB)."""
    ctype = connector.connector_type

    # First, discover schema for context
    nosql_discoverers = {
        "redis": nosql_adapters.discover_redis_schema,
        "cassandra": nosql_adapters.discover_cassandra_schema,
        "neo4j": nosql_adapters.discover_neo4j_schema,
        "elasticsearch": nosql_adapters.discover_elasticsearch_schema,
        "clickhouse": nosql_adapters.discover_clickhouse_schema,
        "influxdb": nosql_adapters.discover_influxdb_schema,
        "couchdb": nosql_adapters.discover_couchdb_schema,
    }

    try:
        schema = nosql_discoverers[ctype](connector)
    except Exception as exc:
        return {"error": f"Schema discovery failed: {exc}"}

    schema_text = json.dumps(schema, default=str)
    # Truncate if too large
    if len(schema_text) > 4000:
        schema_text = schema_text[:4000] + "...(truncated)"

    # Build DB-specific prompt for query generation
    query_formats = {
        "redis": (
            'Return ONLY valid JSON: {"command": "GET|HGETALL|LRANGE|SMEMBERS|ZRANGE|KEYS|SCAN|TYPE|TTL", "args": ["arg1", "arg2"]}\n'
            'For LRANGE use args like ["key", "0", "-1"]. For ZRANGE use ["key", "0", "-1"]. For KEYS use ["pattern*"].\n'
            'Only read commands allowed (GET, HGETALL, LRANGE, SMEMBERS, ZRANGE, KEYS, SCAN, TYPE, TTL, STRLEN, SCARD, ZCARD, LLEN, EXISTS, DBSIZE).'
        ),
        "cassandra": (
            'Return ONLY the CQL SELECT query. Only SELECT statements allowed.\n'
            'CQL rules: no JOINs, use ALLOW FILTERING if needed, partition key required in WHERE.'
        ),
        "neo4j": (
            'Return ONLY the Cypher MATCH query. Only MATCH...RETURN queries allowed (read-only).\n'
            'Example: MATCH (n:Person)-[r:KNOWS]->(m) WHERE n.name = "Alice" RETURN n, r, m LIMIT 50'
        ),
        "elasticsearch": (
            'Return ONLY valid JSON: {"index": "index_name", "query": {"match": {"field": "value"}}, "size": 50}\n'
            'For aggregations: {"index": "...", "query": {"match_all": {}}, "aggs": {"name": {"terms": {"field": "field.keyword"}}}, "size": 0}\n'
            'For full-text: use "match" or "multi_match". For exact: use "term". For range: use "range".'
        ),
        "clickhouse": (
            'Return ONLY the ClickHouse SQL SELECT query.\n'
            'ClickHouse rules: use backticks for column names, supports LIMIT, use toDate()/toDateTime() for dates, use countIf/sumIf for conditional aggregates.'
        ),
        "influxdb": (
            'Return ONLY the Flux query.\n'
            'Flux example: from(bucket: "BUCKET") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "cpu") |> limit(n: 50)\n'
            f'The bucket name is: {connector.database}'
        ),
        "couchdb": (
            'Return ONLY valid JSON Mango query: {"selector": {"field": {"$gt": 0}}, "limit": 50, "fields": ["field1", "field2"]}\n'
            'Selector operators: $eq, $gt, $gte, $lt, $lte, $ne, $in, $nin, $exists, $regex, $and, $or, $not'
        ),
    }

    prompt = (
        f"You are a {ctype.upper()} expert. Database schema:\n\n{schema_text}\n\n"
        f"The user typed: {question}\n\n"
        "Interpret the input — it could be a question, collection/key/index name, field names, raw query, or any data reference. "
        f"Generate the appropriate {ctype.upper()} query.\n\n"
        f"{query_formats.get(ctype, 'Return the query.')}\n"
    )

    resp = _groq_call_with_retry(groq,
        model="openai/gpt-4.1-mini-fast",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    raw = re.sub(r"<think>[\s\S]*$", "", raw).strip()
    raw = raw.replace("```json", "").replace("```cql", "").replace("```cypher", "").replace("```flux", "").replace("```sql", "").replace("```", "").strip()

    # Execute based on database type
    nosql_executors = {
        "redis": lambda: nosql_adapters.execute_redis_query(connector, json.loads(raw)),
        "cassandra": lambda: nosql_adapters.execute_cassandra_query(connector, raw),
        "neo4j": lambda: nosql_adapters.execute_neo4j_query(connector, raw),
        "elasticsearch": lambda: nosql_adapters.execute_elasticsearch_query(connector, json.loads(raw)),
        "clickhouse": lambda: nosql_adapters.execute_clickhouse_sql(connector, raw),
        "influxdb": lambda: nosql_adapters.execute_influxdb_query(connector, raw),
        "couchdb": lambda: nosql_adapters.execute_couchdb_query(connector, json.loads(raw)),
    }

    try:
        result = nosql_executors[ctype]()
        result["generated_query"] = raw
        return result
    except json.JSONDecodeError:
        return {"error": f"AI generated invalid {ctype} query format", "raw_query": raw}
    except Exception as exc:
        return {"error": str(exc), "raw_query": raw}


# ── search_tables ────────────────────────────

def _tool_search_tables(db: Session, connector_id: str = None, keyword: str = "") -> dict:
    if not connector_id or connector_id in ("null", "None", "undefined", ""):
        return {"error": "No database connected. Please select a connector first."}
    connector = _get_connector(db, connector_id)
    if not connector:
        return {"error": f"Connector '{connector_id}' not found"}

    keyword_lower = keyword.lower()

    try:
        if connector.connector_type == "mongodb":
            client = get_mongodb_client(connector)
            mongo_db = client[connector.database]
            collections = mongo_db.list_collection_names()
            matches = []
            for coll_name in collections:
                if keyword_lower in coll_name.lower():
                    sample = mongo_db[coll_name].find_one()
                    fields = list(sample.keys()) if sample else []
                    matches.append({"collection": coll_name, "fields": fields, "match": "collection_name"})
                else:
                    sample = mongo_db[coll_name].find_one()
                    if sample:
                        matched_fields = [k for k in sample.keys() if keyword_lower in k.lower()]
                        if matched_fields:
                            matches.append({"collection": coll_name, "matched_fields": matched_fields, "match": "field_name"})
            client.close()
            return {"matches": matches, "keyword": keyword}

        # NoSQL adapters
        nosql_searchers = {
            "redis": nosql_adapters.search_redis,
            "cassandra": nosql_adapters.search_cassandra,
            "neo4j": nosql_adapters.search_neo4j,
            "elasticsearch": nosql_adapters.search_elasticsearch,
            "clickhouse": nosql_adapters.search_clickhouse,
            "influxdb": nosql_adapters.search_influxdb,
            "couchdb": nosql_adapters.search_couchdb,
        }
        if connector.connector_type in nosql_searchers:
            return nosql_searchers[connector.connector_type](connector, keyword)

        # SQL databases
        else:
            engine = get_connector_engine(connector)
            inspector = inspect(engine)
            schema_name = _get_schema_name(connector.connector_type)
            table_names = inspector.get_table_names(schema=schema_name)

            matches = []
            for tbl in table_names:
                cols = inspector.get_columns(tbl, schema=schema_name)

                if keyword_lower in tbl.lower():
                    matches.append({
                        "table": tbl,
                        "columns": [{"name": c["name"], "type": str(c["type"])} for c in cols],
                        "match": "table_name",
                    })
                else:
                    matched_cols = [c for c in cols if keyword_lower in c["name"].lower()]
                    if matched_cols:
                        matches.append({
                            "table": tbl,
                            "matched_columns": [{"name": c["name"], "type": str(c["type"])} for c in matched_cols],
                            "match": "column_name",
                        })

            engine.dispose()
            # Compact results for large match sets to prevent token overflow
            if len(matches) > 5:
                compact = []
                for m in matches[:8]:
                    tbl = m.get("table", "")
                    if m["match"] == "table_name":
                        col_names = [c["name"] for c in m.get("columns", [])]
                        compact.append({"table": tbl, "columns": col_names})
                    else:
                        matched = [c["name"] for c in m.get("matched_columns", [])]
                        compact.append({"table": tbl, "matched_columns": matched})
                return {"matches": compact, "keyword": keyword, "total_matches": len(matches)}
            return {"matches": matches, "keyword": keyword}
    except Exception as exc:
        return {"error": str(exc)}


# ── explain_query ────────────────────────────

def _tool_explain_query(db: Session, connector_id: str = None, sql: str = "") -> dict:
    if not connector_id or connector_id in ("null", "None", "undefined", ""):
        return {"error": "No database connected. Please select a connector first."}
    connector = _get_connector(db, connector_id)
    if not connector:
        return {"error": f"Connector '{connector_id}' not found"}

    if connector.connector_type in ("mongodb", "redis", "neo4j", "elasticsearch", "influxdb", "couchdb"):
        return {"error": f"EXPLAIN is not supported for {connector.connector_type} through this tool."}

    # Validate it's a SELECT
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return {"error": "Only SELECT queries can be explained."}

    try:
        # ClickHouse and Cassandra have their own EXPLAIN
        if connector.connector_type == "clickhouse":
            client = nosql_adapters.get_clickhouse_client(connector)
            result = client.query(f"EXPLAIN {sql}")
            plan = "\n".join(str(r[0]) for r in result.result_rows)
            client.close()
            return {"sql": sql, "plan": plan, "dialect": "clickhouse"}

        if connector.connector_type == "cassandra":
            return {"error": "EXPLAIN is not natively supported in Cassandra CQL. Use TRACING ON instead."}

        engine = get_connector_engine(connector)
        dialect = connector.connector_type

        if dialect in ("postgresql", "supabase", "cockroachdb"):
            explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {sql}"
        elif dialect in ("mysql", "mariadb"):
            explain_sql = f"EXPLAIN FORMAT=JSON {sql}"
        elif dialect == "mssql":
            explain_sql = None  # handled specially below
        elif dialect == "oracle":
            explain_sql = None  # handled specially below
        elif dialect == "sqlite":
            explain_sql = f"EXPLAIN QUERY PLAN {sql}"
        else:
            explain_sql = f"EXPLAIN {sql}"

        with engine.connect() as conn:
            if dialect == "mssql":
                conn.execute(text("SET SHOWPLAN_TEXT ON"))
                result = conn.execute(text(sql))
                plan_rows = [str(row[0]) if len(row) == 1 else str(row) for row in result.fetchall()]
                conn.execute(text("SET SHOWPLAN_TEXT OFF"))
            elif dialect == "oracle":
                conn.execute(text(f"EXPLAIN PLAN FOR {sql}"))
                result = conn.execute(text("SELECT PLAN_TABLE_OUTPUT FROM TABLE(DBMS_XPLAN.DISPLAY())"))
                plan_rows = [str(row[0]) for row in result.fetchall()]
            else:
                result = conn.execute(text(explain_sql))
                plan_rows = [str(row[0]) if len(row) == 1 else str(row) for row in result.fetchall()]

        engine.dispose()
        plan_text = "\n".join(plan_rows)
        return {"sql": sql, "plan": plan_text, "dialect": dialect}
    except Exception as exc:
        return {"sql": sql, "error": str(exc)}


# ── suggest_optimizations ────────────────────

def _tool_suggest_optimizations(db: Session, connector_id: str = None, sql: str = "", explain_plan: str = "") -> dict:
    from app.core.llm_client import get_llm_client

    if not connector_id or connector_id in ("null", "None", "undefined", ""):
        return {"error": "No database connected. Please select a connector first."}
    connector = _get_connector(db, connector_id)
    if not connector:
        return {"error": f"Connector '{connector_id}' not found"}

    groq_client = get_llm_client(max_retries=0)
    dialect = connector.connector_type

    prompt = f"""You are a database performance expert specializing in {dialect.upper()}.

Analyze this query and its execution plan, then suggest optimizations.

## SQL Query
```sql
{sql}
```

## Execution Plan
```
{explain_plan}
```

Provide your analysis in this format:
1. **Performance Issues** — What's slow and why (e.g., sequential scans, missing indexes, bad join order)
2. **Suggested Indexes** — CREATE INDEX statements that would help
3. **Optimized Query** — Rewritten SQL if applicable
4. **Expected Improvement** — Estimated performance gain

Be specific and actionable. Reference actual table/column names from the query."""

    try:
        resp = _groq_call_with_retry(groq_client,
            model="openai/gpt-4.1-mini-fast",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        analysis = (resp.choices[0].message.content or "").strip()
        # Strip think tags
        analysis = re.sub(r"<think>[\s\S]*?</think>", "", analysis).strip()
        analysis = re.sub(r"<think>[\s\S]*$", "", analysis).strip()
        return {"sql": sql, "analysis": analysis, "dialect": dialect}
    except Exception as exc:
        return {"sql": sql, "error": str(exc)}


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def _parse_connection_string(conn_str: str) -> dict | None:
    conn_str = conn_str.strip()

    # MongoDB
    if re.match(r"mongodb(\+srv)?://", conn_str):
        try:
            p = urlparse(conn_str)
            return {
                "type": "mongodb",
                "host": p.hostname or "",
                "port": p.port or 27017,
                "database": p.path.lstrip("/").split("?")[0] or "test",
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # MSSQL — mssql:// or mssql+pymssql://
    m_mssql = re.match(r"mssql(\+\w+)?://", conn_str)
    if m_mssql:
        try:
            norm = re.sub(r"mssql\+\w+", "mssql", conn_str)
            # Handle comma-port format: mssql://user:pass@host,1433/db → host:1433
            norm = re.sub(r"@([^/:]+),(\d+)", r"@\1:\2", norm)
            p = urlparse(norm)
            return {
                "type": "mssql",
                "host": p.hostname or "",
                "port": p.port or 1433,
                "database": p.path.lstrip("/") or "master",
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # Redis — redis:// or rediss://
    if re.match(r"rediss?://", conn_str):
        try:
            p = urlparse(conn_str)
            return {
                "type": "redis",
                "host": p.hostname or "localhost",
                "port": p.port or 6379,
                "database": p.path.lstrip("/") or "0",
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # Neo4j — bolt:// or neo4j://
    if re.match(r"(bolt|neo4j)(\+s?s?c?)?://", conn_str):
        try:
            p = urlparse(conn_str)
            return {
                "type": "neo4j",
                "host": p.hostname or "localhost",
                "port": p.port or 7687,
                "database": p.path.lstrip("/") or "neo4j",
                "username": unquote(p.username or "neo4j"),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # Cassandra — cassandra://
    if conn_str.startswith("cassandra://"):
        try:
            p = urlparse(conn_str)
            return {
                "type": "cassandra",
                "host": p.hostname or "localhost",
                "port": p.port or 9042,
                "database": p.path.lstrip("/") or "system",
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # Elasticsearch — http(s)://...:9200 or elasticsearch://
    if re.match(r"(elasticsearch|https?)://", conn_str) and ("9200" in conn_str or "elasticsearch" in conn_str.lower()):
        try:
            norm = re.sub(r"elasticsearch://", "http://", conn_str)
            p = urlparse(norm)
            return {
                "type": "elasticsearch",
                "host": p.hostname or "localhost",
                "port": p.port or 9200,
                "database": p.path.lstrip("/") or "default",
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # ClickHouse — clickhouse://
    if re.match(r"clickhouse(\+\w+)?://", conn_str):
        try:
            norm = re.sub(r"clickhouse\+\w+", "clickhouse", conn_str).replace("clickhouse://", "http://")
            p = urlparse(norm)
            return {
                "type": "clickhouse",
                "host": p.hostname or "localhost",
                "port": p.port or 8123,
                "database": p.path.lstrip("/") or "default",
                "username": unquote(p.username or "default"),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # InfluxDB — influxdb://
    if conn_str.startswith("influxdb://"):
        try:
            p = urlparse(conn_str.replace("influxdb://", "http://"))
            return {
                "type": "influxdb",
                "host": p.hostname or "localhost",
                "port": p.port or 8086,
                "database": p.path.lstrip("/") or "default",
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # CouchDB — couchdb://
    if conn_str.startswith("couchdb://"):
        try:
            p = urlparse(conn_str.replace("couchdb://", "http://"))
            return {
                "type": "couchdb",
                "host": p.hostname or "localhost",
                "port": p.port or 5984,
                "database": p.path.lstrip("/") or "default",
                "username": unquote(p.username or "admin"),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # Oracle — oracle://
    if re.match(r"oracle(\+\w+)?://", conn_str):
        try:
            norm = re.sub(r"oracle\+\w+", "oracle", conn_str).replace("oracle://", "http://")
            p = urlparse(norm)
            return {
                "type": "oracle",
                "host": p.hostname or "localhost",
                "port": p.port or 1521,
                "database": p.path.lstrip("/") or "ORCL",
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # SQLite — sqlite:///path
    if conn_str.startswith("sqlite:"):
        try:
            path = conn_str.replace("sqlite:///", "").replace("sqlite://", "")
            return {
                "type": "sqlite",
                "host": "local",
                "port": 0,
                "database": path or ":memory:",
                "username": "",
                "password": "",
            }
        except Exception:
            return None

    # MariaDB — mariadb://
    if re.match(r"mariadb(\+\w+)?://", conn_str):
        try:
            norm = re.sub(r"mariadb\+\w+", "mariadb", conn_str).replace("mariadb://", "http://")
            p = urlparse(norm)
            return {
                "type": "mariadb",
                "host": p.hostname or "localhost",
                "port": p.port or 3306,
                "database": p.path.lstrip("/") or "mysql",
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # CockroachDB — cockroachdb:// or cockroach://
    if re.match(r"cockroach(db)?://", conn_str):
        try:
            norm = re.sub(r"cockroach(db)?://", "http://", conn_str)
            p = urlparse(norm)
            return {
                "type": "cockroachdb",
                "host": p.hostname or "localhost",
                "port": p.port or 26257,
                "database": p.path.lstrip("/") or "defaultdb",
                "username": unquote(p.username or "root"),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    # PostgreSQL / MySQL (keep last as catch-all for common schemes)
    m = re.match(r"(postgresql|postgres|mysql)(\+\w+)?://", conn_str)
    if m:
        prefix = m.group(1)
        try:
            norm = conn_str
            if norm.startswith("postgres://"):
                norm = "postgresql://" + norm[len("postgres://"):]
            norm = re.sub(r"(postgresql|mysql)\+\w+", lambda x: x.group(1), norm)
            p = urlparse(norm)
            host = p.hostname or ""
            db_type = "mysql" if prefix == "mysql" else "postgresql"
            if "supabase" in host:
                db_type = "supabase"
            return {
                "type": db_type,
                "host": host,
                "port": p.port or (3306 if db_type == "mysql" else 5432),
                "database": p.path.lstrip("/") or ("defaultdb" if db_type == "mysql" else "postgres"),
                "username": unquote(p.username or ""),
                "password": unquote(p.password or ""),
            }
        except Exception:
            return None

    return None
