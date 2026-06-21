import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
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
from app.services.snaptrade_service import (
    fetch_account_balance,
    fetch_account_orders,
    fetch_account_positions,
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


def _current_portfolio_value(account_ids: list[str]) -> float:
    total = 0.0
    for acct_id in account_ids:
        try:
            pos_payload = fetch_account_positions(acct_id)
            positions = pos_payload.get("results") or pos_payload.get("positions") or []
            for pos in positions:
                try:
                    qty = float(pos.get("units") or 0)
                    price = float(pos.get("price") or 0)
                    total += qty * price
                except (TypeError, ValueError):
                    continue
        except Exception as exc:
            logger.warning("Returns: position fetch failed for %s: %s", acct_id, exc)
        try:
            bal_payload = fetch_account_balance(acct_id)
            total += _extract_cash(bal_payload)
        except Exception as exc:
            logger.warning("Returns: balance fetch failed for %s: %s", acct_id, exc)
    return round(total, 2)


@router.get("/portfolio-returns", response_model=PortfolioReturns)
async def get_portfolio_returns(
    account_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Live portfolio value (filtered if account_id is set)
    stmt = select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(InvestmentAccount.snaptrade_account_id == account_id)
    account_rows = await db.execute(stmt)
    accounts = account_rows.scalars().all()
    account_uuids = [a.id for a in accounts]
    snaptrade_ids = [a.snaptrade_account_id for a in accounts]

    current_value = _current_portfolio_value(snaptrade_ids) if snaptrade_ids else 0.0

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

    # 3. 1D change — compares to earliest snapshot in last 24h.
    # Snapshots are aggregated across all accounts (we don't snapshot per-account),
    # so the 1D number for a filtered view is approximate.
    now = datetime.now(timezone.utc)
    day_change: float | None = None
    day_change_pct: float | None = None
    snap_row = await db.execute(
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.user_id == current_user.id,
            PortfolioSnapshot.snapshot_at >= now - timedelta(hours=24),
        )
        .order_by(PortfolioSnapshot.snapshot_at.asc())
        .limit(1)
    )
    earliest_today = snap_row.scalar_one_or_none()
    if earliest_today and current_value and not account_id:
        start_val = float(earliest_today.total_value)
        day_change = round(current_value - start_val, 2)
        day_change_pct = round(day_change / start_val, 6) if start_val else None

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

    return PortfolioReturns(
        current_value=current_value,
        total_principal=total_principal,
        all_time_return=all_time_return,
        all_time_return_pct=all_time_return_pct,
        day_change=day_change,
        day_change_pct=day_change_pct,
        ytd_change=ytd_change,
        ytd_change_pct=ytd_change_pct,
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


@router.get("/weekly-trades", response_model=WeeklyReportResponse)
async def get_weekly_trades(
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
    account_ids = [a.snaptrade_account_id for a in accounts]
    account_uuids = [a.id for a in accounts]

    trades: list[TradeRow] = []
    total_buys = 0.0
    total_sells = 0.0
    fetch_failed = False
    debug_msg: str | None = None
    fetch_error_detail: str | None = None
    raw_order_count = 0
    skipped_states: dict[str, int] = {}
    window_trades: list[dict] = []  # parsed dicts feeding trade-matched P/L

    if account_ids:
        any_account_succeeded = False
        for acct_id in account_ids:
            try:
                orders = fetch_account_orders(acct_id, state="EXECUTED")
                any_account_succeeded = True
            except Exception as exc:
                logger.warning(
                    "Orders fetch failed for account %s: %s", acct_id, exc
                )
                fetch_error_detail = f"{type(exc).__name__}: {exc}"
                # Try without the state filter — some SDKs reject it.
                try:
                    orders = fetch_account_orders(acct_id)
                    any_account_succeeded = True
                    fetch_error_detail = None
                except Exception as exc2:
                    logger.warning(
                        "Orders retry without state failed for %s: %s", acct_id, exc2
                    )
                    fetch_error_detail = f"{type(exc2).__name__}: {exc2}"
                    continue

            raw_order_count += len(orders)
            for order in orders:
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

        if not any_account_succeeded:
            fetch_failed = True

        if not trades and raw_order_count > 0:
            top_states = sorted(
                skipped_states.items(), key=lambda x: x[1], reverse=True
            )[:3]
            debug_msg = (
                f"Pulled {raw_order_count} orders, none matched window "
                f"{window_start}–{window_end}. Skipped states: "
                f"{', '.join(s or 'UNKNOWN' for s, _ in top_states) or 'none'}."
            )

    trades.sort(key=lambda t: t.trade_date, reverse=True)

    # Trade-matched P/L: FIFO-match round-trips, mark open lots to current price.
    # Needs current holdings (price + cost basis) to value open lots and to
    # cost pre-window sells.
    holdings: dict[str, dict] = {}
    for acct_id in account_ids:
        try:
            holdings.update(build_holdings_map(fetch_account_positions(acct_id)))
        except Exception as exc:
            logger.warning("Holdings fetch failed for %s: %s", acct_id, exc)

    pnl = summarize_trades(window_trades, holdings)
    pnl_by_instrument = [InstrumentPnL(**row) for row in pnl["by_instrument"]]
    realized_pnl = pnl["realized_pnl"] if window_trades else None
    unrealized_pnl = pnl["unrealized_pnl"] if window_trades else None
    trading_pnl = pnl["trading_pnl"] if window_trades else None

    # Compute window P/L using snapshots + deposits in the same window
    window_start_dt = datetime.combine(
        window_start, datetime.min.time(), tzinfo=timezone.utc
    )
    # End of the selected window (inclusive of the whole end day) — important
    # for past weeks, so we don't grab today's value as the window-end value.
    window_end_dt = datetime.combine(
        window_end, datetime.max.time(), tzinfo=timezone.utc
    )
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

    message = debug_msg
    if fetch_failed:
        # Surface the actual exception so we can diagnose from the browser.
        message = (
            f"Could not fetch trade history from SnapTrade: {fetch_error_detail}"
            if fetch_error_detail
            else "Could not fetch trade history from SnapTrade."
        )

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
        available=not fetch_failed,
        message=message,
    )
