import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.broker_order import BrokerOrder
from app.models.deposit import Deposit
from app.models.investment_account import InvestmentAccount
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.user import User
from app.schemas.reports import (
    BenchmarkPoint,
    BenchmarkResponse,
    InstrumentPnL,
    PortfolioReturns,
    TradeRow,
    WeeklyReportResponse,
)
from app.services.market_data_service import CandleRange, fetch_candles
from app.services.report_sync import (
    COLD_BACKFILL_DAYS,
    INCREMENTAL_DAYS,
    REFRESH_TTL,
    ensure_holdings_cached,
    refresh_accounts_background,
    sync_accounts,
)
from app.services.trade_parsing import (
    build_holdings_map,
    parse_order,
    summarize_trades,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_cash(payload) -> float:
    entries: list = []
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = payload.get("results") or payload.get("balances") or []
    total = 0.0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            total += float(entry.get("cash") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _current_portfolio_value_from_cache(accounts) -> float:
    """Sum holdings market value + cash from each account's cached payloads."""
    total = 0.0
    for account in accounts:
        payload = account.holdings_cache
        if isinstance(payload, dict):
            positions = payload.get("results") or payload.get("positions") or []
        elif isinstance(payload, list):
            positions = payload
        else:
            positions = []
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            try:
                qty = float(pos.get("units") or 0)
                price = float(pos.get("price") or 0)
                total += qty * price
            except (TypeError, ValueError):
                continue
        total += _extract_cash(account.balance_cache or [])
    return round(total, 2)


# A gap larger than this between consecutive snapshots marks a session boundary
# (snapshots only fire during market hours, so overnight/weekend gaps are hours
# long while intraday snapshots are 5 min apart).
_SESSION_GAP = timedelta(hours=2)


def _previous_close_value(snapshots) -> float | None:
    """Baseline for the 1D change: the portfolio value at the previous session's
    close.

    `snapshots` is an ascending list of PortfolioSnapshot rows. We find where the
    current session begins (the last large time-gap) and take the snapshot right
    before it. With only one session present (e.g. the very first trading day),
    we fall back to that session's opening value.
    """
    snaps = [(s.snapshot_at, float(s.total_value)) for s in snapshots]
    if not snaps:
        return None

    session_start = 0
    for i in range(len(snaps) - 1, 0, -1):
        if snaps[i][0] - snaps[i - 1][0] > _SESSION_GAP:
            session_start = i
            break

    if session_start == 0:
        # No prior session captured yet — anchor to today's open.
        return snaps[0][1]
    return snaps[session_start - 1][1]


@router.get("/portfolio-returns", response_model=PortfolioReturns)
async def get_portfolio_returns(
    background: BackgroundTasks,
    account_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Portfolio value from the cached holdings/balance (filtered if set).
    stmt = select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(InvestmentAccount.snaptrade_account_id == account_id)
    account_rows = await db.execute(stmt)
    accounts = account_rows.scalars().all()

    accounts, _sync_error, stale = await ensure_holdings_cached(
        db, accounts, background
    )
    account_uuids = [a.id for a in accounts]

    current_value = _current_portfolio_value_from_cache(accounts) if accounts else 0.0

    # 2. Total principal = sum of deposits to the matching accounts
    if account_uuids:
        deposit_rows = await db.execute(
            select(Deposit).where(
                Deposit.user_id == current_user.id,
                Deposit.investment_account_id.in_(account_uuids),
            )
        )
        deposits = deposit_rows.scalars().all()
    else:
        deposits = []
    total_principal = round(sum(float(d.amount) for d in deposits), 2)

    all_time_return = round(current_value - total_principal, 2)
    all_time_return_pct = (
        round(all_time_return / total_principal, 6) if total_principal > 0 else 0.0
    )

    # 3. 1D change — current value vs the previous session's close.
    # Snapshots are aggregated across all accounts (we don't snapshot per-account),
    # so the 1D number is only shown for the unfiltered "All accounts" view.
    now = datetime.now(timezone.utc)
    day_change: float | None = None
    day_change_pct: float | None = None
    snap_rows = await db.execute(
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.user_id == current_user.id,
            PortfolioSnapshot.snapshot_at >= now - timedelta(days=6),
        )
        .order_by(PortfolioSnapshot.snapshot_at.asc())
    )
    prev_close = _previous_close_value(snap_rows.scalars().all())
    if prev_close and current_value and not account_id:
        day_change = round(current_value - prev_close, 2)
        day_change_pct = round(day_change / prev_close, 6) if prev_close else None

    # 4. YTD — deposits-adjusted
    year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    ytd_deposits = round(
        sum(float(d.amount) for d in deposits if d.deposited_at >= year_start), 2
    )
    ytd_change: float | None = None
    ytd_change_pct: float | None = None
    pre_year_principal = round(total_principal - ytd_deposits, 2)
    if pre_year_principal > 0:
        invested_basis = pre_year_principal + ytd_deposits
        ytd_change = round(current_value - invested_basis, 2)
        ytd_change_pct = (
            round(ytd_change / invested_basis, 6) if invested_basis else None
        )

    synced_times = [a.holdings_synced_at for a in accounts if a.holdings_synced_at]
    last_synced_at = min(synced_times).isoformat() if synced_times else None

    return PortfolioReturns(
        current_value=current_value,
        total_principal=total_principal,
        all_time_return=all_time_return,
        all_time_return_pct=all_time_return_pct,
        day_change=day_change,
        day_change_pct=day_change_pct,
        ytd_change=ytd_change,
        ytd_change_pct=ytd_change_pct,
        stale=stale,
        last_synced_at=last_synced_at,
    )


_BENCHMARK_RANGES: dict[str, CandleRange] = {
    "1m": "1M",
    "3m": "3M",
    "6m": "1Y",
    "ytd": "1Y",
    "1y": "1Y",
    "1d": "1D",
    "1w": "1W",
}


@router.get("/benchmark", response_model=BenchmarkResponse)
async def get_benchmark(
    range: str = "1y",
    symbol: str = "SPY",
    _: User = Depends(get_current_user),
):
    range_key = range.lower()
    yf_range = _BENCHMARK_RANGES.get(range_key, "1Y")

    try:
        payload = await fetch_candles(symbol, yf_range)
    except Exception as exc:
        logger.warning("Benchmark fetch failed: %s", exc)
        return BenchmarkResponse(
            symbol=symbol.upper(),
            range=range_key,
            series=[],
            available=False,
            message="Failed to load benchmark data.",
        )

    candles = payload.get("candles", [])
    if not candles:
        return BenchmarkResponse(
            symbol=symbol.upper(),
            range=range_key,
            series=[],
            available=True,
            message="No benchmark data in this range.",
        )

    is_intraday = yf_range in ("1D", "1W")
    series = []
    for c in candles:
        ts = datetime.fromtimestamp(c["t"], tz=timezone.utc)
        date_str = ts.isoformat() if is_intraday else ts.date().isoformat()
        series.append(BenchmarkPoint(date=date_str, value=float(c["c"])))

    if range_key == "ytd":
        year_prefix = str(datetime.now(timezone.utc).year)
        series = [p for p in series if p.date.startswith(year_prefix)]
    elif range_key == "6m":
        cutoff = (datetime.now(timezone.utc) - timedelta(days=183)).date().isoformat()
        series = [p for p in series if p.date >= cutoff]

    return BenchmarkResponse(
        symbol=symbol.upper(),
        range=range_key,
        series=series,
        available=True,
        message=None,
    )


def _account_is_stale(
    account: InvestmentAccount,
    now: datetime,
    is_current_window: bool,
    window_end_dt: datetime,
) -> bool:
    """Whether an account's cached orders need a background refresh.

    Current week: stale once the cache is older than the TTL. Past weeks are
    immutable once settled, so they're fresh as long as we synced after the
    window ended.
    """
    if account.orders_synced_at is None:
        return True
    if is_current_window:
        return account.orders_synced_at < now - REFRESH_TTL
    return account.orders_synced_at <= window_end_dt


@router.get("/weekly-trades", response_model=WeeklyReportResponse)
async def get_weekly_trades(
    background: BackgroundTasks,
    days: int = 7,
    start_date: str | None = None,
    end_date: str | None = None,
    account_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Explicit start/end dates take precedence over `days`.
    if start_date and end_date:
        try:
            window_start = date.fromisoformat(start_date)
            window_end = date.fromisoformat(end_date)
        except ValueError:
            window_end = date.today()
            window_start = window_end - timedelta(days=7)
    else:
        days = max(1, min(days, 90))
        window_end = date.today()
        window_start = window_end - timedelta(days=days)

    today = window_end

    acct_stmt = select(InvestmentAccount).where(
        InvestmentAccount.user_id == current_user.id
    )
    if account_id:
        acct_stmt = acct_stmt.where(
            InvestmentAccount.snaptrade_account_id == account_id
        )
    account_rows = await db.execute(acct_stmt)
    accounts = account_rows.scalars().all()
    account_uuids = [a.id for a in accounts]

    # Window datetime bounds. End-of-day inclusive matters for past weeks so we
    # don't truncate the final day or grab today's snapshot value.
    window_start_dt = datetime.combine(
        window_start, datetime.min.time(), tzinfo=timezone.utc
    )
    window_end_dt = datetime.combine(
        window_end, datetime.max.time(), tzinfo=timezone.utc
    )
    now = datetime.now(timezone.utc)
    is_current_window = window_end >= date.today()

    # Serve from the local cache; only call SnapTrade for cold accounts (never
    # synced) inline, and refresh stale ones in the background.
    sync_error: str | None = None
    stale_account_ids: list = []
    if accounts:
        cold = [a for a in accounts if a.orders_synced_at is None]
        if cold:
            try:
                await sync_accounts(db, cold, days=COLD_BACKFILL_DAYS)
                await db.commit()
            except Exception as exc:
                logger.warning("Cold order sync failed: %s", exc)
                sync_error = f"{type(exc).__name__}: {exc}"
                # rollback expires the ORM instances; reload them so the rest
                # of the request can read their (still-empty) cache fields.
                await db.rollback()
                accounts = (await db.execute(acct_stmt)).scalars().all()
                account_uuids = [a.id for a in accounts]

        # Background-refresh accounts that are already cached but stale. Cold
        # accounts that just synced are fresh; ones that failed to sync stay
        # None and are skipped here (retried inline on the next request).
        stale_account_ids = [
            a.id
            for a in accounts
            if a.orders_synced_at is not None
            and _account_is_stale(a, now, is_current_window, window_end_dt)
        ]
        if stale_account_ids:
            background.add_task(
                refresh_accounts_background,
                stale_account_ids,
                INCREMENTAL_DAYS if is_current_window else COLD_BACKFILL_DAYS,
            )

    # Read stored orders for the window from the local cache.
    trades: list[TradeRow] = []
    total_buys = 0.0
    total_sells = 0.0
    raw_order_count = 0
    skipped_states: dict[str, int] = {}
    window_trades: list[dict] = []  # parsed dicts feeding trade-matched P/L

    if account_uuids:
        stored_rows = await db.execute(
            select(BrokerOrder).where(
                BrokerOrder.investment_account_id.in_(account_uuids),
                BrokerOrder.executed_at >= window_start_dt,
                BrokerOrder.executed_at <= window_end_dt,
            )
        )
        stored_orders = stored_rows.scalars().all()
        raw_order_count = len(stored_orders)
        for bo in stored_orders:
            order = bo.payload
            if not isinstance(order, dict):
                continue

            # Only count executed/filled trades
            state = str(order.get("state") or order.get("status") or "").upper()
            if state and state not in ("EXECUTED", "FILLED", "COMPLETED"):
                skipped_states[state] = skipped_states.get(state, 0) + 1
                continue

            parsed = parse_order(order)
            if parsed is None:
                continue

            try:
                executed_date = date.fromisoformat(parsed["trade_date"])
            except ValueError:
                continue
            if not (window_start <= executed_date <= window_end):
                continue

            window_trades.append(parsed)
            row = TradeRow(**parsed)
            trades.append(row)
            if row.action == "BUY":
                total_buys += row.amount
            else:
                total_sells += row.amount

    trades.sort(key=lambda t: t.trade_date, reverse=True)

    debug_msg: str | None = None
    if not trades and raw_order_count > 0:
        top_states = sorted(
            skipped_states.items(), key=lambda x: x[1], reverse=True
        )[:3]
        debug_msg = (
            f"Stored {raw_order_count} orders, none matched window "
            f"{window_start}–{window_end}. Skipped states: "
            f"{', '.join(s or 'UNKNOWN' for s, _ in top_states) or 'none'}."
        )

    # Trade-matched P/L: FIFO-match round-trips, mark open lots to current
    # price using each account's cached holdings.
    holdings: dict[str, dict] = {}
    for account in accounts:
        if account.holdings_cache:
            holdings.update(build_holdings_map(account.holdings_cache))

    pnl = summarize_trades(window_trades, holdings)
    pnl_by_instrument = [InstrumentPnL(**row) for row in pnl["by_instrument"]]
    realized_pnl = pnl["realized_pnl"] if window_trades else None
    unrealized_pnl = pnl["unrealized_pnl"] if window_trades else None
    trading_pnl = pnl["trading_pnl"] if window_trades else None
    # Portfolio snapshots are stored per-user (not per-account), so the
    # snapshot-based portfolio P/L only applies to the all-accounts view.
    # When filtered to one account we leave it blank and rely on the
    # trade-matched P/L, which is naturally per-account.
    window_start_value: float | None = None
    window_end_value: float | None = None
    if not account_id:
        snap_start_row = await db.execute(
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.user_id == current_user.id,
                PortfolioSnapshot.snapshot_at >= window_start_dt,
            )
            .order_by(PortfolioSnapshot.snapshot_at.asc())
            .limit(1)
        )
        snap_end_row = await db.execute(
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.user_id == current_user.id,
                PortfolioSnapshot.snapshot_at <= window_end_dt,
            )
            .order_by(PortfolioSnapshot.snapshot_at.desc())
            .limit(1)
        )
        first_snap = snap_start_row.scalar_one_or_none()
        last_snap = snap_end_row.scalar_one_or_none()
        window_start_value = float(first_snap.total_value) if first_snap else None
        window_end_value = float(last_snap.total_value) if last_snap else None

    dep_stmt = select(Deposit).where(
        Deposit.user_id == current_user.id,
        Deposit.deposited_at >= window_start_dt,
    )
    if account_id and account_uuids:
        dep_stmt = dep_stmt.where(Deposit.investment_account_id.in_(account_uuids))
    deposit_rows = await db.execute(dep_stmt)
    window_deposits = round(
        sum(float(d.amount) for d in deposit_rows.scalars().all()), 2
    )

    week_pnl: float | None = None
    week_pnl_pct: float | None = None
    if window_start_value is not None and window_end_value is not None:
        week_pnl = round(window_end_value - window_start_value - window_deposits, 2)
        denom = window_start_value + window_deposits
        if denom > 0:
            week_pnl_pct = round(week_pnl / denom, 6)

    # We serve cached data; only a cold sync failure with nothing stored is a
    # hard failure. A pending background refresh is surfaced via `stale`.
    available = True
    message = debug_msg
    if sync_error and not trades:
        available = False
        message = f"Couldn't reach SnapTrade and no cached trades yet: {sync_error}"

    synced_times = [a.orders_synced_at for a in accounts if a.orders_synced_at]
    last_synced_at = min(synced_times).isoformat() if synced_times else None

    return WeeklyReportResponse(
        week_start=window_start.isoformat(),
        week_end=today.isoformat(),
        trades=trades,
        total_buys=round(total_buys, 2),
        total_sells=round(total_sells, 2),
        net_cash_flow=round(total_sells - total_buys, 2),
        week_start_value=window_start_value,
        week_end_value=window_end_value,
        week_deposits=window_deposits,
        week_pnl=week_pnl,
        week_pnl_pct=week_pnl_pct,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        trading_pnl=trading_pnl,
        pnl_by_instrument=pnl_by_instrument,
        available=available,
        message=message,
        stale=bool(stale_account_ids),
        last_synced_at=last_synced_at,
    )
