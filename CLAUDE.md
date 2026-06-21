# CLAUDE.md — repo navigation guide

Token-saving map of the codebase so you can jump straight to the right file
instead of searching. User/deploy docs live in [README.md](README.md); this
file is for *where code lives and where to change things*.

Monorepo: **`api-server/`** (FastAPI, async SQLAlchemy, Postgres) +
**`web-client/`** (Next.js 14 App Router, TypeScript, Tailwind).

---

## Backend — `api-server/app/`

Request flow: `main.py` → `api/v1/routes.py` mounts routers →
`api/v1/endpoints/*` (HTTP + validation) → `services/*` (logic, external calls,
DB) → `models/*` (ORM) / `schemas/*` (Pydantic I/O).

| Area | Endpoint (`endpoints/`) | Service(s) (`services/`) | Models |
|------|------------------------|--------------------------|--------|
| Auth (email+pw, Google OAuth, JWT) | `auth.py` | `user_service.py`, `core/security.py` | `user.py` |
| User profile + accounts list | `users.py` | `user_service.py` | `user.py`, `investment_account.py` |
| Brokerage connect + holdings/history | `snaptrade.py` (538 ln, biggest) | `snaptrade_service.py`, `snapshot_service.py` | `investment_account.py`, `portfolio_snapshot.py` |
| Market data (quotes, charts, sectors, fear&greed, earnings, market-map) | `market.py` | `market_data_service.py`, `market_universe.py` | — |
| Deposits (principal tracking) | `deposits.py` | — (inline) | `deposit.py` |
| Weekly P/L reports | `reports.py` | `report_sync.py`, `trade_parsing.py` | `broker_order.py` |

Cross-cutting:
- `core/config.py` — env/settings (Pydantic `Settings`). `core/database.py` — async session. `core/security.py` — JWT + bcrypt. `core/scheduler.py` — APScheduler (5-min portfolio snapshots in market hours, nightly prune).
- `api/deps.py` — FastAPI dependencies (`get_current_user`, DB session).
- `services/trade_parsing.py` — **pure** FIFO P/L helpers, no FastAPI/DB/network (unit-testable). `services/market_universe.py` — hardcoded ticker list driving the macro treemap.
- `main.py` — app factory, CORS (`ALLOWED_ORIGINS`), router mount, scheduler start.

## Frontend — `web-client/src/`

Pages (`app/`) compose components (`components/`); data via `services/api.ts`
(Axios, injects JWT) and the `useCachedResource` hook (stale-while-revalidate).

| Page | File | Key components | Calls |
|------|------|----------------|-------|
| Landing | `app/page.tsx` | — | — |
| Login / Register | `app/login`, `app/register` | — | `/auth/*` |
| Overview | `app/dashboard/page.tsx` | `PortfolioTrend`, `AllocationBreakdown`, `HoldingsSection`, `AccountFilter`, `ConnectAccountButton` | `/snaptrade/*`, `/reports/*`, `/deposits` |
| Position detail | `app/dashboard/positions/[symbol]/page.tsx` | `PriceChart` | `/market/candles`, `/snaptrade/*` |
| Reports | `app/dashboard/reports/page.tsx` | — | `/reports/*` |
| Deposits | `app/dashboard/deposits/page.tsx` | — | `/deposits`, `/users/me/accounts` |
| Macro | `app/dashboard/macro/page.tsx` | `MarketSnapshotCard`, `QuoteGrid`, `MarketMap`, `FearGreedGauge` | `/market/*` |

Shared:
- `app/layout.tsx` — root; injects no-flash theme script. `app/dashboard/layout.tsx` — auth gate + nav + per-route fade-in.
- `components/Navbar.tsx`, `components/ThemeToggle.tsx` (light/dark, persists to localStorage).
- `components/ui/` — design primitives: `Card`, `PageHeader`, `Skeleton`.
- `hooks/useCachedResource.ts` — fetch + cache + revalidate. `hooks/useSnapTradeConnect.ts` — SnapTrade portal.
- `services/api.ts` — Axios instance. `services/authService.ts` — login/logout/token.

---

## Where to change X

- **New API endpoint** → add `endpoints/<x>.py`, register in `api/v1/routes.py`, put logic in `services/`, I/O models in `schemas/`.
- **DB schema** → edit `models/`, then `cd api-server && alembic revision --autogenerate -m "..."` and review the migration in `alembic/`.
- **Macro treemap tickers** → `services/market_universe.py` (`UNIVERSE` list).
- **Market-data source/logic** → `services/market_data_service.py`; the allow-list for `/market/quotes` is `_QUOTE_ALLOWED` in `endpoints/market.py`.
- **P/L math** → `services/trade_parsing.py` (pure) + `endpoints/reports.py`.
- **Colors / theming / dark mode** → tokens in `app/globals.css` (`:root` + `.dark`) mapped in `tailwind.config.ts`. Use semantic classes (`bg-surface`, `text-content`, `text-muted`, `border-line`, `text-up/down`, `bg-brand`) — **not** raw `gray-*`/`indigo-*`, or dark mode breaks. Cards use the `.card` / `.card-hover` classes or `components/ui/Card.tsx`.
- **A dashboard chart/widget** → matching `components/*.tsx`; charts use `recharts` (lines/donuts) and `lightweight-charts` (candles).

## Conventions

- **Semantic Tailwind tokens only** for color (see theming above).
- Backend services stay thin-of-FastAPI where they can be pure (see `trade_parsing.py`).
- **Verify before shipping**: `cd web-client && npx tsc --noEmit` (and `npx next build` for bigger UI changes). No ESLint config is wired up — rely on tsc/build.
- Git workflow for this repo: branch → commit → merge `--no-ff` to `main` → push (done automatically per session preference).
