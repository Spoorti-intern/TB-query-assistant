# TB Query Assistant

AI-powered database query assistant. Users connect databases (PostgreSQL, MySQL, MongoDB), ask questions in natural language, and get SQL/results back.

## Tech Stack
- **Frontend**: React 19 + Vite, Axios, Lucide icons
- **Backend**: FastAPI + SQLAlchemy, Groq AI (gpt-oss-20b model)
- **Databases**: PostgreSQL (app metadata), supports PostgreSQL/MySQL/MongoDB connectors
- **Infra**: Docker Compose (Postgres)

## Key Files
- `backend/app/main.py` — FastAPI app setup, CORS, router registration
- `backend/app/api/queries.py` — NL-to-SQL pipeline (schema discovery → AI generation → validation → execution → explanation)
- `backend/app/api/connectors.py` — CRUD for database connectors
- `backend/app/api/mongodb_queries.py` — MongoDB query endpoint
- `backend/app/core/connector_manager.py` — SQLAlchemy engine factory
- `backend/app/core/crypto.py` — Fernet password encryption/decryption
- `backend/app/core/mongodb_adapter.py` — MongoDB client factory
- `frontend/src/App.jsx` — Main app shell with routing
- `frontend/src/pages/ChatPage.jsx` — Chat interface with AI queries
- `frontend/src/pages/ConnectorsPage.jsx` — Connector management UI
- `frontend/src/api.js` — Axios API client

## Development

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # fill in DATABASE_URL and GROQ_API_KEY
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Database (Docker)
docker-compose up -d
```

## Conventions
- Backend uses FastAPI routers under `app/api/`, models under `app/models/`, schemas under `app/schemas/`
- Frontend components in `src/components/`, pages in `src/pages/`
- CSS classes prefixed with `tb-` for component styles
- Passwords encrypted with Fernet before storage
- All SQL queries are validated as read-only before execution
- API URL configurable via `VITE_API_URL` env var
