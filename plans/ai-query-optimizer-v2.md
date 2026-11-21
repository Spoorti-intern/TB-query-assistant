# AI-First Query Optimizer v2 — Revised Implementation Plan

## What Changed from v1

The previous plan was **over-engineered** — it proposed an abstract adaptor pattern with 10 new files, service layers, and factory classes before we even had the basics working well. Here's the revised approach:

**v1 problems:**
- Too many abstraction layers (Adaptor ABC → Factory → Service → Tool → Agent)
- Duplicate effort: creating "shared services" that just wrap what already exists
- Over-designed optimizer (EXPLAIN ANALYZE → AI rewrite → re-execute) for a chat-first product
- Frontend changes were an afterthought bolted onto the existing UI

**v2 philosophy: AI-first means the LLM IS the orchestrator — keep the code thin.**

---

## Architecture: Thin Tools, Smart Agent

```
┌──────────────────────────────────────────────────────────────┐
│                    Grok-Style Frontend                        │
│                                                              │
│  ┌─────────┐  ┌──────────────────────────────────────────┐   │
│  │ Sidebar  │  │            Chat Canvas                   │   │
│  │          │  │                                          │   │
│  │ History  │  │  Centered reading column                 │   │
│  │ Conns    │  │  Markdown + SQL + Tables + Plans         │   │
│  │          │  │                                          │   │
│  │          │  │  ┌──────────────────────────────────┐    │   │
│  │          │  │  │   Pill Input Bar                  │    │   │
│  │          │  │  │  [+] [Ask anything...] [⚡] [→]  │    │   │
│  │          │  │  └──────────────────────────────────┘    │   │
│  └─────────┘  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                           │ SSE stream
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   Agent (agent.py)                            │
│   Model: llama-3.3-70b-versatile (tool calling)              │
│   System prompt: Expert DB analyst + optimizer               │
│   Loop: think → pick tool → execute → feed back → repeat    │
└──────────────────────┬───────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌────────────┐ ┌──────────┐ ┌──────────────┐
   │ Connection  │ │ Schema   │ │ Query Tools  │
   │ Tools       │ │ Tools    │ │              │
   │             │ │          │ │ execute_sql  │
   │ list_conns  │ │ discover │ │ execute_mql  │
   │ connect_db  │ │ search   │ │ explain_plan │
   │ test_conn   │ │          │ │ suggest_idx  │
   └──────┬──────┘ └────┬─────┘ └──────┬───────┘
          │              │              │
          ▼              ▼              ▼
   ┌───────────────────────────────────────────┐
   │  Existing Core Modules (enhanced)          │
   │  connector_manager / schema_manager /      │
   │  mongodb_adapter / crypto                  │
   └───────────────────────────────────────────┘
```

**Key difference:** No adaptor classes, no factory, no service layer. Each tool function directly calls the existing core modules. The AI decides the workflow — the code just provides the tools.

---

## Part A: Backend — Enhanced Tools + Agent

### Step 1: Expand tools.py with 3 new tools

**File:** `backend/app/api/tools.py`

Add to the existing 4 tools:

| # | Tool | What it does | Implementation |
|---|---|---|---|
| 5 | `search_tables` | Fuzzy search tables/columns by keyword | `information_schema` query (SQL) or collection listing (MongoDB) |
| 6 | `explain_query` | Get execution plan for a SQL query | `EXPLAIN (ANALYZE, FORMAT JSON)` for PG, `EXPLAIN FORMAT=JSON` for MySQL, `.explain()` for MongoDB |
| 7 | `suggest_optimizations` | Analyze a query + its plan, suggest improvements | AI-powered: feed plan to LLM, get back index suggestions + rewritten SQL |

**No new files.** These 3 functions go in the existing `tools.py` alongside the existing 4.

### Step 2: Upgrade agent.py system prompt

**File:** `backend/app/api/agent.py`

Changes:
- Rewrite the system prompt to position the AI as a **database performance expert**
- Include instructions: "When asked about slow queries, automatically use `explain_query` then `suggest_optimizations`"
- Include instructions: "When exploring a database, use `search_tables` to find relevant tables before querying"
- Increase `max_rounds` from 6 → 12 (optimization chains need more tool calls)
- Add SSE event types: `query_plan` and `optimization` alongside existing `status`, `content`, `tool_result`
- Stream partial markdown as it generates (progressive rendering)

### Step 3: Harden query validation

**File:** `backend/app/api/queries.py` (reuse existing `validate_read_only_sql`)

- Extract `validate_read_only_sql()` to be importable by tools.py
- Currently tools.py has a weak token-based validator; replace it with the sqlglot-based one from queries.py
- Single validation function used everywhere

### Step 4: Add schema caching

**File:** `backend/app/core/schema_manager.py` (modify existing)

- Add a simple in-memory TTL cache (dict + timestamps)
- `get_cached_schema(connector_id)` → returns cached if < 5 min old, else rediscovers
- Prevents the agent from calling `discover_schema` on every single turn

---

## Part B: Grok-Style UI Redesign

### Design Tokens (extracted from Grok's design system)

```css
:root {
  /* Surfaces — warm dark elevation ladder */
  --bg-page:        #050505;          /* near-black page */
  --bg-sidebar:     #0a0a0a;          /* sidebar, one step up */
  --bg-surface-1:   #141414;          /* cards, panels */
  --bg-surface-2:   #1a1a1a;          /* elevated: composer, menus */
  --bg-surface-3:   #222222;          /* tooltips, popovers */

  /* Text */
  --text-primary:   #f5f5f5;          /* main text */
  --text-secondary: #9e9e9e;          /* muted labels */
  --text-tertiary:  #666666;          /* disabled/placeholder */

  /* Accents */
  --accent-blue:    #2563eb;          /* interactive, user bubbles */
  --accent-orange:  #ff6b35;          /* selective highlight */
  --accent-green:   #22c55e;          /* success states */
  --accent-red:     #ef4444;          /* errors, destructive */

  /* Bubbles */
  --bubble-user:    #2563eb;          /* user message */
  --bubble-assistant: #17345a;        /* assistant message */

  /* Spacing — 8px grid */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  /* Radius */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  --radius-pill: 9999px;

  /* Borders */
  --border-hairline: 1px solid rgba(255,255,255,0.08);
  --border-strong:   2px solid rgba(255,255,255,0.15);

  /* Typography — system font stack */
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", monospace;
}
```

### Step 5: Complete CSS rewrite — `App.css` + `index.css`

Replace the entire CSS with the Grok-inspired design system:

**Layout:**
- Near-black `#050505` page background
- Collapsible sidebar (260px expanded, 0px collapsed) with conversation history
- Centered reading column (max-width 720px) for chat content
- Bottom-anchored pill-shaped composer
- No shadows anywhere — surface-color elevation only

**Sidebar:**
- Near-black background, hairline border on the right
- "New Chat" button at top (pill shape, subtle border)
- Conversation history list with hover states
- Connector list section with status indicators
- Collapse/expand toggle
- Active conversation highlighted with surface-2

**Chat Area:**
- Centered column (720px max) with generous vertical padding
- Empty state: centered brand + tagline + capability cards
- Messages: no traditional bubbles — clean left-aligned blocks
- User messages: subtle blue-tinted background, right-aligned text label
- Assistant messages: no background, just text with markdown
- Tool execution: inline status pills (subtle, not flashy)

**Composer (Input Bar):**
- Fixed to bottom, pill shape (radius-pill on outer, radius-lg on inner)
- Background: `--bg-surface-2`
- Left: "+" button for connector picker / attachments
- Center: auto-expanding textarea
- Right: model indicator badge + send button (arrow icon)
- Grows vertically with content, max 200px

**Markdown Rendering:**
- Tables: clean hairline borders, alternating row tints
- Code blocks: `--bg-surface-2` background, rounded corners, copy button
- SQL highlighting with syntax colors
- Execution plans: indented tree with color-coded nodes

### Step 6: Rewrite `Sidebar.jsx`

Replace current sidebar with Grok-style layout:

```
┌──────────────────────┐
│  ☰  TB Query         │  ← collapse toggle + brand
│                      │
│  [+ New Chat]        │  ← pill button
│                      │
│  ─── Today ───       │  ← date group label
│  Orders last month   │  ← conversation item
│  Schema exploration  │
│                      │
│  ─── Yesterday ───   │
│  Slow query debug    │
│                      │
│  ─── Connections ─── │  ← connectors section
│  🟢 staging-pg       │
│  🟡 prod-mysql       │
│  ⚫ local-mongo      │
│  [+ Add connection]  │
│                      │
│  ─────────────────   │
│  ⚙ Settings          │  ← bottom
└──────────────────────┘
```

- Conversation history (new feature — requires storing chat sessions)
- Inline connector list with status dots
- Collapsible with smooth animation
- Mobile: overlay drawer with backdrop

### Step 7: Rewrite `ChatPage.jsx`

**Empty state (no conversation):**
```
                 ┌─────────────────┐
                 │   TB Query      │
                 │   Assistant     │
                 └─────────────────┘
          What can I help you with today?

   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ 📊 Query │  │ 🔍 Explore│  │ ⚡ Optimize│
   │ your data│  │ schemas  │  │ queries  │
   └──────────┘  └──────────┘  └──────────┘

   ┌──────────────────────────────────────┐
   │ [+]  Ask anything about your data... │ [→]
   └──────────────────────────────────────┘
```

**Active conversation:**
- Messages in a centered reading column
- User messages: right-aligned, blue pill
- Assistant messages: left-aligned, plain text with markdown
- Tool calls: compact inline pills showing "Discovering schema...", "Running query..."
- SQL results: rendered as clean tables
- Execution plans: collapsible tree view
- Streaming: progressive text reveal with cursor

### Step 8: Rewrite `ConnectorsPage.jsx`

Remove the separate connectors page. Connectors are now managed:
1. **In the sidebar** — list with status dots, click to manage
2. **In chat** — paste a connection string, the AI creates the connector
3. **Via "+" menu** — in the composer, "Add connection" opens an inline modal

The connector form becomes a **modal/drawer** rather than a separate page:
- Slide-in from right
- Same fields but styled with Grok tokens
- Test connection inline with animated status
- Schema preview collapsible within the modal

### Step 9: New component — `Topbar.jsx` replacement

Replace the current top bar with a minimal Grok-style header:
```
┌──────────────────────────────────────────────────┐
│  ☰  │  TB Query Assistant  │      ⚡ Fast │ ···  │
└──────────────────────────────────────────────────┘
```
- Left: sidebar toggle (hamburger)
- Center: conversation title (editable) or "New Chat"
- Right: model tier badge + settings overflow menu

### Step 10: New component — `ConnectorModal.jsx`

Inline modal for adding/editing connectors:
- Triggered from sidebar "+ Add connection" or composer "+" menu
- Overlay modal with form fields
- Quick-connect: paste a full URI and auto-detect type
- Manual: type selector → fields auto-populate defaults
- Test button with inline result

### Step 11: Update `App.jsx` routing

- Remove page-based routing (no more `activePage` state switching)
- Single-page layout: Sidebar + Chat canvas always visible
- Connectors modal overlays on top
- Settings drawer overlays on top
- Chat history managed via conversation ID in state

---

## Part C: Chat History (New Feature Required by Sidebar)

### Step 12: Backend — Chat session model + endpoints

**New file:** `backend/app/models/chat_session.py`
```python
class ChatSession(Base):
    id: str (UUID)
    title: str           # auto-generated from first message
    connector_id: str    # which DB this chat is about (nullable)
    messages: JSON       # full message history
    created_at: datetime
    updated_at: datetime
```

**New file:** `backend/app/api/chat_sessions.py`
- `POST /api/sessions/` — create new session
- `GET /api/sessions/` — list sessions (paginated, newest first)
- `GET /api/sessions/{id}` — get session with messages
- `PUT /api/sessions/{id}` — update (rename, add messages)
- `DELETE /api/sessions/{id}` — delete session

**Modify:** `backend/app/api/agent.py`
- Accept optional `session_id` in request
- Auto-save messages to session after each turn
- Auto-generate title from first user message (use AI: "Summarize this question in 4 words")

### Step 13: Frontend — Chat history state management

- `App.jsx` manages `currentSessionId` and `sessions[]` state
- On load: fetch recent sessions for sidebar
- On new chat: create session, switch to it
- On send message: include `session_id` in agent request
- On session click (sidebar): load that session's messages
- Optimistic updates: show message immediately, persist in background

---

## Implementation Order

| Phase | Steps | What you get |
|---|---|---|
| **Phase 1: UI Shell** | 5, 6, 7, 8, 9, 10, 11 | Grok-style UI with existing backend |
| **Phase 2: Chat History** | 12, 13 | Persistent conversations in sidebar |
| **Phase 3: Smart Tools** | 1, 2, 3, 4 | Explain plans, optimization suggestions, search |

Each phase is independently deployable. Phase 1 is purely cosmetic — same backend, new face. Phase 2 adds persistence. Phase 3 makes the AI smarter.

---

## Files Changed Summary

### New Files (5)
| # | File | Purpose |
|---|---|---|
| 1 | `backend/app/models/chat_session.py` | Chat session ORM model |
| 2 | `backend/app/api/chat_sessions.py` | Session CRUD endpoints |
| 3 | `frontend/src/components/ConnectorModal.jsx` | Inline connector form modal |
| 4 | `frontend/src/components/EmptyState.jsx` | Grok-style empty chat state |
| 5 | `frontend/src/components/MessageBubble.jsx` | Unified message rendering component |

### Modified Files (10)
| # | File | Changes |
|---|---|---|
| 6 | `frontend/src/App.css` | Complete rewrite — Grok design tokens + all styles |
| 7 | `frontend/src/index.css` | Reset + base styles update |
| 8 | `frontend/src/App.jsx` | Single-page layout, session state management |
| 9 | `frontend/src/components/Sidebar.jsx` | Full rewrite — history + connectors |
| 10 | `frontend/src/components/Topbar.jsx` | Minimal header bar |
| 11 | `frontend/src/pages/ChatPage.jsx` | Grok-style chat + composer |
| 12 | `frontend/src/api.js` | Add session endpoints |
| 13 | `backend/app/api/tools.py` | Add 3 new tools |
| 14 | `backend/app/api/agent.py` | Enhanced system prompt + SSE events + session persistence |
| 15 | `backend/app/core/schema_manager.py` | Add TTL cache |

### Removed/Deprecated
- `frontend/src/pages/ConnectorsPage.jsx` — replaced by `ConnectorModal.jsx`
- `frontend/src/pages/ProjectsPage.jsx` — removed (was placeholder)
- `frontend/src/pages/SettingsPage.jsx` — replaced by settings drawer (later)

---

## Why This is Better Than v1

| Aspect | v1 | v2 |
|---|---|---|
| **New files** | 10 backend files | 2 backend + 3 frontend |
| **Abstraction** | Adaptor ABC + Factory + Services | Direct tool functions |
| **UI** | Bolt-on components to existing UI | Complete Grok-style redesign |
| **Chat history** | Not addressed | Full implementation |
| **Complexity** | High (many layers to debug) | Low (flat tool functions) |
| **Time to value** | Backend-heavy, UI last | UI-first, smart tools last |
| **Extensibility** | Add new Adaptor class | Add new tool function |

The AI is the abstraction layer. We don't need adaptors — we need tools.
