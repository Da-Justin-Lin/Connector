# Connector — Personal Investment Aggregator

A monorepo containing a FastAPI backend (`api-server`) and a Next.js 14 frontend (`web-client`) that syncs investment data from Plaid-connected institutions (Chase, Robinhood, etc.) into a unified dashboard.

---

## Repository Structure

```
connector/
├── api-server/          # FastAPI backend
│   ├── app/
│   │   ├── api/v1/      # Versioned REST routes
│   │   ├── core/        # Config, JWT, DB session
│   │   ├── models/      # SQLAlchemy ORM entities
│   │   ├── schemas/     # Pydantic request/response models
│   │   └── services/    # Plaid integration logic
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
└── web-client/          # Next.js 14 frontend
    └── src/
        ├── app/         # App Router pages & layouts
        ├── components/  # Navbar, PlaidLinkButton
        ├── hooks/       # usePlaidLink
        └── services/    # Axios API client
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 15+ (local or Docker)
- A [Plaid](https://dashboard.plaid.com) account (sandbox keys are free)

---

## Backend — API Server

### 1. Create and activate a virtual environment

```bash
cd api-server

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env: fill in PLAID_CLIENT_ID, PLAID_SECRET, and DATABASE_URL
```

### 4. Run database migrations

> Alembic is included. Initialize once per fresh clone:

```bash
alembic init alembic
# Configure alembic/env.py to import app.models.Base and use settings.database_url
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 5. Start the development server

```bash
uvicorn main:app --reload --port 8000
```

| URL | Purpose |
|-----|---------|
| `http://localhost:8000/health` | Health check |
| `http://localhost:8000/docs` | Interactive OpenAPI docs |
| `http://localhost:8000/api/v1/...` | Versioned API |

---

## Frontend — Web Client

### 1. Install dependencies

```bash
cd web-client
npm install
```

### 2. Configure environment variables

```bash
cp .env.local.example .env.local
# NEXT_PUBLIC_API_URL defaults to http://localhost:8000 — change only if needed
```

### 3. Start the development server

```bash
npm run dev
```

The app will be available at `http://localhost:3000`.

> **Note:** `next.config.mjs` proxies `/api/*` → `http://localhost:8000/api/*`, so the API server must be running for Plaid flows to work.

---

## Plaid Sandbox Testing

1. Sign up at [dashboard.plaid.com](https://dashboard.plaid.com) and create an app.
2. Copy your **Sandbox** `client_id` and `secret` into `api-server/.env`.
3. Click **Connect Account** in the dashboard — Plaid's sandbox UI accepts test credentials:
   - Username: `user_good`
   - Password: `pass_good`

---

## Key Technologies

| Layer    | Technology |
|----------|------------|
| Backend  | FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Auth     | JWT via `python-jose`, bcrypt via `passlib` |
| Plaid    | `plaid-python` SDK |
| Database | PostgreSQL + `asyncpg` |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| HTTP     | Axios with JWT interceptor |
| Plaid UI | `react-plaid-link` |
