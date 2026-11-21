# AI-First Query Optimizer — Revised Plan (v2)

## Core Philosophy Change

**Previous plan:** Build adaptor classes, service layers, optimizer services — then let AI call them.
**This plan:** Give AI raw database access via thin tools. AI writes SQL, AI analyzes plans, AI optimizes. Code only does what AI can't: execute queries and enforce safety.

The intelligence lives in the **system prompt**, not in Python classes.

---

## Architecture: Thin Tools + Smart Agent

```
┌──────────────────────────────────────────────────┐
│              Frontend (React)                     │
│  ChatPage.jsx — SSE stream, Markdown renderer    │
└─────────────────────┬────────────────────────────┘
                      │ POST /api/agent/chat (SSE)
                      ▼
┌──────────────────────────────────────────────────┐
│           Agent (agent.py)                        │
│                                                   │
│  Smart system prompt:                             │
│  "You are an expert DBA. You write SQL/MQL        │
│   directly. You read EXPLAIN output and suggest   │
│   optimizations. You format results as Markdown." │
│                                                   │
│  LLM decides what to call and when.               │
│  No hardcoded pipeline.                           │
└─────────────────────┬────────────────────────────┘
                      │ tool calls
                      ▼
┌──────────────────────────────────────────────────┐
│           6 Thin Tools (tools.py)                 │
│                                                   │
│  list_connectors  — list saved DBs                │
│  connect_database — add + test a new connection   │
│  get_schema       — tables, columns, FKs, indexes │
│  run_sql          — validate + execute SQL         │
│  run_mongodb      — execute MongoDB operation      │
│  explain_sql      — EXPLAIN (ANALYZE, BUFFERS)     │
└─────────────────────┬────────────────────────────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
     PostgreSQL    MySQL       MongoDB
   (via SQLAlchemy)          (via PyMongo)
```

**What's NOT here:** No adaptor ABC. No factory pattern. No QueryOptimizer class. No QueryGenerator service. No schema service with caching. The AI doesn't need wrapper classes — it needs raw database access with safety guardrails.

---

## The 6 Tools — What Changes

### Tool 1: `list_connectors` (exists — keep as-is)
No changes needed.

### Tool 2: `connect_database` (exists — minor tweak)
- Add: accept a friendly `name` parameter (already exists but underused)
- Keep: URI parsing, duplicate detection, encryption, test connection

### Tool 3: `get_schema` (replaces `discover_schema` — enhanced)
Current `discover_schema` is too thin. Enhance it:

**SQL databases:**
- Tables + views (currently missing views)
- Columns with types AND nullability
- Primary keys
- Foreign key relationships (table.col → ref_table.ref_col)
- Indexes (name, columns, unique flag)
- Row count estimates (pg_stat: `reltuples`, MySQL: `TABLE_ROWS`)

**MongoDB:**
- Collections with estimated doc counts
- Sampled field names + inferred types (already exists)
- Existing indexes per collection (`list_indexes()`)

This is the most important tool. The richer the schema info, the better the AI writes queries.

### Tool 4: `run_sql` (replaces `query_database` for SQL — major rewrite)
Current version: AI inside `tools.py` generates SQL from a natural language question.
New version: **AI writes the SQL directly in the tool call.**

```
# OLD: AI calls query_database(connector_id, question="how many orders?")
#      → tools.py internally calls another LLM to generate SQL
#      → double LLM call, no AI control over the SQL

# NEW: AI calls run_sql(connector_id, sql="SELECT COUNT(*) FROM orders")
#      → tools.py validates + executes
#      → AI wrote the SQL itself, can iterate on it
```

Why this matters:
- **AI sees the schema first** (via `get_schema`), then writes SQL with full context
- **AI can iterate**: if a query fails, it reads the error and fixes the SQL
- **AI can optimize**: run a query, then run `explain_sql`, then rewrite and re-run
- **No double LLM call**: the agent LLM IS the query generator
- **AI controls the dialect**: it knows if it's PostgreSQL (use ILIKE) or MySQL (use LOWER)

Safety:
- `sqlglot` AST validation from `queries.py` (the thorough one) — applied to every query
- Read-only transaction enforcement
- Statement timeout (10s)
- Automatic LIMIT 100 injection if missing
- Table allowlist check against discovered schema

### Tool 5: `run_mongodb` (replaces `query_database` for MongoDB — major rewrite)
Same philosophy: AI writes the MongoDB operation directly.

```
# AI calls: run_mongodb(connector_id, collection="orders",
#           operation="find", query={"status": "shipped"},
#           projection={"_id":0, "total":1}, limit=50)
```

Validation:
- Operation allowlist: `find`, `count`, `aggregate` only
- Pipeline inspection for aggregation: reject `$out`, `$merge`, `$addFields` with `$function`
- Result limit enforcement (max 500)

### Tool 6: `explain_sql` (NEW)
AI calls this when it wants to understand query performance.

```
# AI calls: explain_sql(connector_id, sql="SELECT * FROM orders WHERE ...")
```

- PostgreSQL: `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)`
- MySQL: `EXPLAIN FORMAT=TREE` (or `EXPLAIN ANALYZE` on 8.0.18+)
- Returns raw EXPLAIN output as text — the AI reads and interprets it
- Same sqlglot validation as `run_sql` (must be a valid SELECT)

No `OptimizedQuery` dataclass. No `ComparisonReport`. The AI reads the EXPLAIN text, understands it (LLMs are good at this), and tells the user what's wrong and how to fix it.

---

## The System Prompt — Where the Intelligence Lives

This is the most critical piece. The system prompt turns the LLM into a DBA:

```
You are an expert database administrator and query optimizer.
You have direct access to the user's databases through tools.

## Your workflow for answering questions:
1. If no connector is active, check list_connectors or ask the user
2. Call get_schema to understand the database structure
3. Write SQL/MongoDB queries YOURSELF — do not ask the user to write them
4. Execute via run_sql or run_mongodb
5. Present results as formatted Markdown tables

## Query optimization (use when asked about performance):
1. Write the query
2. Call explain_sql to get the execution plan
3. Read the plan — look for: sequential scans, high row estimates,
   missing indexes, nested loops on large tables, sort operations
   without indexes
4. Rewrite the query for better performance
5. Run explain_sql again on the optimized version
6. Present a before/after comparison to the user

## SQL rules by dialect:
- PostgreSQL/Supabase: Use ILIKE for case-insensitive. Use ::type for casts.
- MySQL: Use LOWER(col) LIKE LOWER(val). Use CAST(). No ILIKE.
- Always write read-only queries (SELECT/WITH only)
- Always include reasonable LIMITs

## Response format:
- Results as Markdown tables (align columns)
- SQL in ```sql fenced blocks
- Explain plans in ```text fenced blocks
- Use bold for key numbers and findings
- For optimization: show before/after with metrics
```

---

## Implementation Steps (8 steps, not 17)

### Step 1: Enhance `get_schema` in `tools.py`
Add to the existing `_tool_discover_schema`:
- Foreign keys via `inspector.get_foreign_keys(table)`
- Indexes via `inspector.get_indexes(table)`
- Primary keys via `inspector.get_pk_constraint(table)`
- Views via `inspector.get_view_names()`
- Row count estimates: `SELECT relname, reltuples FROM pg_class` (PG) or `information_schema.TABLES` (MySQL)
- MongoDB: add `collection.index_information()` to output

### Step 2: Rewrite `run_sql` tool in `tools.py`
Replace `_exec_sql` (which internally generates SQL via LLM) with:
- Accept `sql` parameter directly (AI writes the SQL)
- Port the thorough `sqlglot` validation from `queries.py` (`validate_read_only_sql`)
- Port the execution logic from `queries.py` (`run_read_only_query`) — read-only transaction, timeout, LIMIT injection
- Return `{sql, columns, rows, row_count}` or `{sql, error, hint}`
- Include `hint` on errors (e.g., "Column 'foo' not found — available columns: bar, baz")

### Step 3: Rewrite `run_mongodb` tool in `tools.py`
Replace `_exec_mongodb` (which internally generates MQL via LLM) with:
- Accept `collection`, `operation`, `query`, `projection`, `sort`, `limit` directly
- Add pipeline validation for aggregation (reject write stages)
- Keep existing execution logic from `mongodb_query_engine.py`
- Return `{operation, collection, rows, row_count}` or `{error, hint}`

### Step 4: Add `explain_sql` tool to `tools.py`
New tool function:
- Accept `connector_id` and `sql`
- Validate SQL via sqlglot (same as run_sql)
- PostgreSQL: execute `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {sql}`
- MySQL: execute `EXPLAIN ANALYZE {sql}` or `EXPLAIN FORMAT=TREE {sql}`
- Return `{sql, plan_text, execution_time_ms}`

### Step 5: Update tool schemas in `tools.py`
Redefine `TOOL_SCHEMAS` to match the 6 tools:
- `list_connectors`: no params (unchanged)
- `connect_database`: `connection_string` required, `name` optional (unchanged)
- `get_schema`: `connector_id` required (renamed from discover_schema)
- `run_sql`: `connector_id` + `sql` required
- `run_mongodb`: `connector_id` + `collection` + `operation` required, `query`/`projection`/`sort`/`limit` optional
- `explain_sql`: `connector_id` + `sql` required

### Step 6: Rewrite agent system prompt in `agent.py`
Replace `_build_system_prompt` with the DBA-focused prompt above. Key additions:
- Instruct AI to write SQL/MQL directly (not ask natural language questions to tools)
- Include optimization workflow instructions
- Dialect-specific rules
- Schema-first approach ("always call get_schema before writing queries")
- Error recovery ("if a query fails, read the error, fix the SQL, retry")

### Step 7: Increase agent loop capacity in `agent.py`
- Bump `max_rounds` from 6 → 12 (optimization chains: schema → query → explain → rewrite → explain → present)
- Add SSE event for `explain_plan` (optional — frontend can render it specially)
- Keep existing streaming architecture

### Step 8: Frontend — Markdown rendering enhancements in `ChatPage.jsx`
The AI returns everything as Markdown, so the frontend just needs better rendering:
- Syntax-highlighted SQL blocks (use a lightweight lib or CSS)
- Collapsible sections for large result tables (>20 rows)
- Monospace rendering for EXPLAIN plan text blocks
- No new components needed — just CSS + Markdown renderer config

---

## What We're NOT Building (and why)

| Skipped | Why |
|---|---|
| `DatabaseAdaptor` ABC | The AI handles DB differences via dialect awareness in the prompt. The thin tool functions handle the mechanical differences (3 `if` branches, not a class hierarchy). |
| `AdaptorFactory` | A factory for 3 `if/elif` branches is over-engineering. |
| `QueryOptimizer` service | The AI IS the optimizer. It reads EXPLAIN output and rewrites SQL. No Python class needed. |
| `QueryGenerator` service | The AI writes SQL directly. No intermediate generation service. |
| `SchemaService` with caching | Premature optimization. Schema discovery takes <500ms. If it becomes a bottleneck, add a dict cache later — not a service class. |
| `QueryPlanViewer.jsx` component | EXPLAIN output renders fine as a ```text block. The AI formats it readably. |
| `OptimizationCard.jsx` component | The AI writes before/after Markdown tables. No special component needed. |
| Supabase-specific adaptor | Supabase IS PostgreSQL. The connector manager already adds SSL for Supabase hosts. No separate class needed. |

---

## Example Flows

### Simple Question
```
User: "How many users signed up this month?"

AI thinks: I need the schema first.
→ get_schema(connector_id="abc")
→ Sees: users table with id, email, created_at columns
→ run_sql(connector_id="abc", sql="SELECT COUNT(*) AS signups FROM users WHERE created_at >= DATE_TRUNC('month', CURRENT_DATE)")
→ Gets: [{signups: 342}]

AI responds:
"**342 users** signed up this month (since Nov 1, 2026).

```sql
SELECT COUNT(*) AS signups
FROM users
WHERE created_at >= DATE_TRUNC('month', CURRENT_DATE)
```"
```

### Performance Investigation
```
User: "The orders page is really slow, can you check?"

AI thinks: Need schema, then a typical query, then EXPLAIN.
→ get_schema(connector_id="abc")
→ Sees: orders table, 2.3M rows, indexes on (id), no index on created_at
→ run_sql(sql="SELECT * FROM orders ORDER BY created_at DESC LIMIT 50")
→ Gets results (slow: 3.2s)
→ explain_sql(sql="SELECT * FROM orders ORDER BY created_at DESC LIMIT 50")
→ Sees: Sort (cost=543210), Seq Scan on orders (2,300,000 rows)

AI responds:
"### Performance Analysis

Your query is doing a **full table scan** on 2.3M rows, then sorting all of them just to get 50.

**The problem:** No index on `created_at`, so PostgreSQL must:
1. Read all 2,300,000 rows (Sequential Scan)
2. Sort them all by `created_at`
3. Return the top 50

**Fix — create this index:**
```sql
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);
```

This turns a 3.2s query into ~15ms by using an Index Scan that reads only 50 rows directly in order.

| Metric | Before | After (estimated) |
|--------|--------|--------------------|
| Scan | Seq Scan (2.3M rows) | Index Scan (50 rows) |
| Sort | In-memory sort | No sort needed |
| Time | ~3.2s | ~15ms |"
```

### MongoDB Query
```
User: "Show me the top 5 products by revenue"

AI thinks: MongoDB connector, need schema first.
→ get_schema(connector_id="xyz")
→ Sees: orders collection with fields: product_name, quantity, price
→ run_mongodb(connector_id="xyz", collection="orders", operation="aggregate",
    query=[
      {"$group": {"_id": "$product_name", "revenue": {"$sum": {"$multiply": ["$quantity", "$price"]}}}},
      {"$sort": {"revenue": -1}},
      {"$limit": 5}
    ])
→ Gets top 5 results

AI responds with Markdown table.
```

---

## Migration Path

The existing `/api/query/ask/` and `/api/mongodb/ask/` endpoints stay untouched. They continue to work for any non-agent callers. The agent path (`/api/agent/chat`) is the one being upgraded.

No database migrations. No new tables. No breaking changes.

---

## Summary: 8 Steps, ~400 Lines Changed

| Step | File | Effort |
|------|------|--------|
| 1 | `tools.py` — enhance get_schema | Add ~40 lines |
| 2 | `tools.py` — rewrite run_sql | Replace ~60 lines, port validation from queries.py |
| 3 | `tools.py` — rewrite run_mongodb | Replace ~40 lines |
| 4 | `tools.py` — add explain_sql | Add ~30 lines |
| 5 | `tools.py` — update TOOL_SCHEMAS | Rewrite schema definitions ~40 lines |
| 6 | `agent.py` — rewrite system prompt | Replace ~30 lines of prompt text |
| 7 | `agent.py` — bump max_rounds + minor tweaks | Change ~5 lines |
| 8 | `ChatPage.jsx` — Markdown rendering CSS | Add ~30 lines CSS |

Total: ~8 files touched, ~270 lines added/changed, 0 new files needed.
