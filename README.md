# Connector — Personal Investment Dashboard

Connector is a self-hostable web app that connects your brokerage accounts (via
[SnapTrade](https://snaptrade.com)) and turns them into a single, fast
dashboard: portfolio value over time, allocation, per-position detail, weekly
trade reports with realized/unrealized P/L, and a market overview tab. Market
data (charts, indices, sentiment) comes from free sources — no paid data
provider required.

It's a monorepo with a **FastAPI** backend (`api-server`) and a **Next.js 14**
frontend (`web-client`).

---

## What it can do

### 📊 Overview
- **Portfolio summary** — total value, total cash, and number of connected accounts.
- **Value-over-time chart** — portfolio balance across `1D / 1M / 3M / 6M / YTD / 1Y`, with an optional benchmark (e.g. SPY) overlay.
- **Allocation breakdown** — a donut chart you can flip between three views:
  - **Asset class** (stocks / ETFs / crypto / options / cash)
  - **Sector** (classified via market data, cached daily)
  - **Holdings** (top positions, with the long tail collapsed into "Other")
  - Plus a **concentration warning** when any single position exceeds 25% of the book.
- **Holdings table** — every position per account (quantity, price, market value, cost basis). Click any holding to open its detail page.

### 🔎 Position detail (`/dashboard/positions/<symbol>`)
- Interactive **price chart** with `1D / 1W / 1M / 3M / 1Y` ranges and live polling.
- **Your position** — quantity, average cost, market value, and unrealized P/L (with %).
- **Trade history** — every filled buy/sell for that symbol across your accounts (including options on the underlying), served from a local cache.

### 🧾 Reports (weekly)
- **Weekly trade report** with week-by-week navigation and a per-account filter.
- **P/L breakdown** — trading P/L for the week's trades, split into realized and unrealized, plus portfolio-level P/L.
- **P/L by position** — buys and sells matched per instrument using FIFO, with open lots marked to current price (handles equities and options).
- Stale-while-revalidate caching so revisiting a week renders instantly.

### 💵 Deposits
- Record your **principal / cash deposits** per account.
- Deposits feed the true-return math: "all-time return" and weekly P/L are **deposit-adjusted**, so growth is separated from money you added.

### 🌐 Macro
- **Day charts** for major indices and assets (SPY, QQQ, DIA, IWM, BTC-USD, ETH-USD, GLD, VIX) with live price and day change, refreshing every 60s.
- **CNN Fear & Greed index** gauge with historical comparisons (close / week / month / year).
- **Upcoming earnings** for a curated mega-cap watchlist (next 14 days).

### 🔐 Accounts & auth
- Sign in with **email + password** or **Google OAuth**.
- Connect brokerages through SnapTrade's hosted connection portal (Robinhood, Schwab, Fidelity, and many more).
- A background scheduler snapshots portfolio value every 5 minutes during US market hours to power the intraday trend and P/L.

---

## Repository structure

```
Connector/
├── api-server/                # FastAPI backend
│   ├── app/
│   │   ├── api/v1/endpoints/   # auth, users, snaptrade, market, deposits, reports
│   │   ├── core/              # config, DB session, security (JWT), scheduler
│   │   ├── models/            # SQLAlchemy ORM entities
│   │   ├── schemas/           # Pydantic request/response models
│   │   └── services/          # SnapTrade, market data, trade parsing, sync, snapshots
│   ├── alembic/              # Database migrations (pre-configured)
│   ├── main.py               # App entrypoint
│   ├── Procfile              # Production start command
│   ├── requirements.txt
│   └── .env.example
└── web-client/               # Next.js 14 frontend (App Router)
    └── src/
        ├── app/dashboard/    # overview, positions/[symbol], reports, deposits, macro
        ├── components/       # charts, allocation, holdings, navbar, etc.
        ├── hooks/            # cached-resource + SnapTrade connect hooks
        └── services/         # Axios API client + auth
```

---

## Tech stack

| Layer       | Technology |
|-------------|------------|
| Backend     | FastAPI, SQLAlchemy 2.0 (async), Alembic, APScheduler |
| Auth        | JWT (`python-jose`), bcrypt (`passlib`), Google OAuth |
| Brokerage   | `snaptrade-python-sdk` (backend) + `snaptrade-react` (connection portal) |
| Market data | `yfinance` (charts/quotes/sectors/earnings) + CNN Fear & Greed (via `httpx`) — **no API key required** |
| Database    | PostgreSQL + `asyncpg` |
| Frontend    | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Charts      | `lightweight-charts` (candles), `recharts` (lines/donuts) |

---

## Prerequisites

- **Python** 3.10+
- **Node.js** 18+
- **PostgreSQL** 14+ (local install or Docker)
- A **SnapTrade** account — see below
- *(Optional)* **Google OAuth** credentials, only if you want Google sign-in

### Getting SnapTrade credentials

1. Sign up at [dashboard.snaptrade.com](https://dashboard.snaptrade.com).
2. From the dashboard, grab your **Client ID** and **Consumer Key**.
3. On the personal/developer plan, SnapTrade pre-provisions a **User ID** and
   **User Secret** for you — copy those too. All four values are required.

### (Optional) Google OAuth credentials

1. In [Google Cloud Console](https://console.cloud.google.com) create an OAuth
   2.0 **Web application** client.
2. Add an **Authorized redirect URI**:
   `http://localhost:8000/api/v1/auth/google/callback`
   (and your production equivalent, `https://<your-api-host>/api/v1/auth/google/callback`).
3. Copy the **Client ID** and **Client Secret** into the backend `.env`.

> If you skip Google OAuth, email/password sign-up still works.

---

## Local development

### 1. Database

Create a Postgres database named `connector` (or anything — just match `DATABASE_URL`):

```bash
createdb connector
# or with Docker:
# docker run --name connector-db -e POSTGRES_PASSWORD=password -e POSTGRES_DB=connector -p 5432:5432 -d postgres:16
```

### 2. Backend — API server

```bash
cd api-server

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — see the "Environment variables" table below

# Apply database migrations (Alembic is already configured)
alembic upgrade head

# Run the dev server
uvicorn main:app --reload --port 8000
```

| URL | Purpose |
|-----|---------|
| `http://localhost:8000/health` | Health check |
| `http://localhost:8000/docs`   | Interactive OpenAPI docs |
| `http://localhost:8000/api/v1` | Versioned API root |

### 3. Frontend — web client

```bash
cd web-client

npm install

cp .env.local.example .env.local
# NEXT_PUBLIC_API_URL defaults to http://localhost:8000 — fine for local dev

npm run dev
```

Open **http://localhost:3000**.

> The backend must be running for sign-in, account syncing, and market data to
> work. In local dev the frontend calls the API directly via
> `NEXT_PUBLIC_API_URL`; in production it can instead proxy `/api/*` to the
> backend (see deployment below).

---

## Environment variables

### Backend (`api-server/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `SNAPTRADE_CLIENT_ID` | ✅ | SnapTrade Client ID |
| `SNAPTRADE_CONSUMER_KEY` | ✅ | SnapTrade Consumer Key |
| `SNAPTRADE_USER_ID` | ✅ | SnapTrade pre-provisioned User ID |
| `SNAPTRADE_USER_SECRET` | ✅ | SnapTrade pre-provisioned User Secret |
| `DATABASE_URL` | ✅ | Postgres URL, **asyncpg** driver: `postgresql+asyncpg://user:pass@host:5432/connector` |
| `SECRET_KEY` | ✅ | Long random string used to sign JWTs |
| `ALGORITHM` | – | JWT algorithm (default `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | – | Token lifetime (default `30`) |
| `ALLOWED_ORIGINS` | ✅ | Comma-separated CORS origins, e.g. `http://localhost:3000,https://app.example.com` |
| `BACKEND_URL` | ✅* | Public backend URL (no trailing slash) — builds the Google OAuth redirect |
| `FRONTEND_URL` | ✅* | Public frontend URL (no trailing slash) — post-login redirect target |
| `GOOGLE_CLIENT_ID` | ⛅ | Only for Google sign-in |
| `GOOGLE_CLIENT_SECRET` | ⛅ | Only for Google sign-in |
| `FINNHUB_API_KEY` | – | **Legacy / unused** — market data now uses yfinance. Leave blank. |

<sub>*Required if you use Google OAuth; otherwise the defaults are fine for local dev.*</sub>

### Frontend (`web-client/.env.local`)

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Base URL the browser uses for API calls. Local: `http://localhost:8000`. In production, set to your API's public URL, **or** leave unset and use the `/api/*` proxy below. |
| `API_URL` | Used by `next.config.mjs` to proxy `/api/*` → backend. Set this (e.g. to your internal backend URL) if you prefer same-origin requests over `NEXT_PUBLIC_API_URL`. |

---

## How to use it

1. **Create an account** at `/register` (email + password) or click **Sign in with Google**.
2. On the **Overview** tab, click **Connect Account**. SnapTrade's portal opens —
   choose your brokerage and authorize. Your holdings sync automatically.
3. **Record deposits** on the **Deposits** tab so returns are measured against the
   principal you actually contributed.
4. Explore:
   - **Overview** → allocation + holdings; click a holding for its **position page**.
   - **Reports** → weekly trades and P/L; use the arrows to move between weeks.
   - **Macro** → indices, Fear & Greed, and upcoming earnings.

> First sync of a new account does a cold backfill of orders and holdings, so the
> Reports tab may take a few extra seconds the very first time. After that,
> everything is served from a local cache and refreshed in the background.

---

## Self-hosting / production deployment

The repo is set up to deploy the two apps independently (e.g. on Railway,
Render, Fly.io, or your own VM).

### Backend

- **Start command** (already in `api-server/Procfile`):
  ```
  web: alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT
  ```
  Migrations run on every boot, so deploys stay schema-current.
- Provision a **PostgreSQL** instance and set `DATABASE_URL` (keep the
  `+asyncpg` driver suffix).
- Set all required env vars from the table above. In particular:
  - `ALLOWED_ORIGINS` must include your frontend's public origin.
  - `BACKEND_URL` / `FRONTEND_URL` must be your real public URLs if you use
    Google OAuth, and the same `BACKEND_URL` must be registered as an authorized
    redirect URI in Google Cloud.
- Pick a strong, unique `SECRET_KEY`.

### Frontend

- Build and run with Next.js:
  ```bash
  npm install
  npm run build
  npm run start        # serves on $PORT
  ```
- Point the browser at your API using **one** of:
  - `NEXT_PUBLIC_API_URL=https://your-api-host` (direct calls — requires CORS, which the backend already handles via `ALLOWED_ORIGINS`), **or**
  - `API_URL=https://your-api-host` and leave `NEXT_PUBLIC_API_URL` unset, so the
    built-in `/api/*` rewrite proxies requests same-origin.

### Background jobs

The backend runs an in-process **APScheduler** (started on app boot) that:
- snapshots every user's portfolio value every 5 minutes, 9:30 AM–4:00 PM ET on weekdays, and
- prunes old snapshots nightly.

No extra worker is needed for a single instance. If you scale to multiple
backend instances, run the scheduler on only one to avoid duplicate snapshots.

---

## Data & privacy

Connector is **self-hosted**: your brokerage data, holdings, orders, and
deposits live entirely in **your** Postgres database. SnapTrade brokers the
read-only brokerage connection; market data is fetched from public endpoints
(Yahoo Finance via `yfinance`, and CNN for the Fear & Greed index). No portfolio
data is sent anywhere else.

---

## Troubleshooting

- **`ModuleNotFoundError: yfinance` / `snaptrade_client`** — dependencies aren't
  installed in the active venv. Re-run `pip install -r requirements.txt`.
- **Holdings/Reports are empty after connecting** — the first sync runs in the
  background; refresh after a few seconds. Check the API logs for SnapTrade errors.
- **CORS errors in the browser** — add your frontend origin to `ALLOWED_ORIGINS`
  and restart the backend.
- **Google sign-in fails / redirect mismatch** — `BACKEND_URL` must exactly match
  the redirect URI registered in Google Cloud
  (`<BACKEND_URL>/api/v1/auth/google/callback`).
- **Market data unavailable** — Yahoo Finance occasionally rate-limits; the app
  caches and retries. Try again in a minute.

---

## License

Personal project — use at your own risk. Not affiliated with SnapTrade, CNN, or
Yahoo. This is not financial advice.
