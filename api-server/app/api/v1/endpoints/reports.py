import logging
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
    PortfolioReturns,
    TradeRow,
    WeeklyReportResponse,
)
from app.services.market_data_service import CandleRange, fetch_candles
from app.services.snaptrade_service import (
    fetch_account_balance,
    fetch_account_positions,
    fetch_activities,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Live portfolio value across all connected accounts
    account_rows = await db.execute(
        select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    )
    accounts = account_rows.scalars().all()
    account_ids = [a.snaptrade_account_id for a in accounts]
    current_value = _current_portfolio_value(account_ids) if account_ids else 0.0

    # 2. Total principal = sum of all deposits
    deposit_rows = await db.execute(
        select(Deposit).where(Deposit.user_id == current_user.id)
    )
    deposits = deposit_rows.scalars().all()
    total_principal = round(sum(float(d.amount) for d in deposits), 2)

    all_time_return = round(current_value - total_principal, 2)
    all_time_return_pct = (
        round(all_time_return / total_principal, 6) if total_principal > 0 else 0.0
    )

    # 3. 1D change — earliest snapshot in the last 24h
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
    if earliest_today and current_value:
        start_val = float(earliest_today.total_value)
        day_change = round(current_value - start_val, 2)
        day_change_pct = round(day_change / start_val, 6) if start_val else None

    # 4. YTD — deposits-adjusted change since Jan 1.
    # Without daily snapshots stretching back, we approximate by:
    # YTD return = (current_value - YTD_deposits) / YTD_deposits ... but principal
    # is what we paid in. Cleaner: compare current_value to (start_of_year_value +
    # deposits_made_this_year). If we have no snapshot before Jan 1, fall back to
    # all-time principal.
    year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    ytd_deposits = round(
        sum(float(d.amount) for d in deposits if d.deposited_at >= year_start), 2
    )
    ytd_change: float | None = None
    ytd_change_pct: float | None = None
    pre_year_principal = round(total_principal - ytd_deposits, 2)
    if pre_year_principal > 0:
        # Return relative to what was invested at start of year + new money added
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
    "6m": "1Y",   # yfinance has no 6M preset; use 1Y and trim client-side
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

    series = [
        BenchmarkPoint(
            date=datetime.fromtimestamp(c["t"], tz=timezone.utc)
            .date()
            .isoformat()
            if yf_range not in ("1D", "1W")
            else datetime.fromtimestamp(c["t"], tz=timezone.utc).isoformat(),
            value=float(c["c"]),
        )
        for c in candles
    ]

    # Trim for YTD / 6M which don't have native yfinance presets
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


def _classify_action(activity: dict) -> str:
    raw = (
        activity.get("type")
        or activity.get("action")
        or activity.get("activity_type")
        or ""
    )
    return str(raw).upper()


@router.get("/weekly-trades", response_model=WeeklyReportResponse)
async def get_weekly_trades(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    week_start = today - timedelta(days=7)

    # Fetch live trade activities
    account_rows = await db.execute(
        select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    )
    accounts = account_rows.scalars().all()
    account_ids = [a.snaptrade_account_id for a in accounts]

    trades: list[TradeRow] = []
    total_buys = 0.0
    total_sells = 0.0
    fetch_failed = False

    if account_ids:
        try:
            activities = fetch_activities(
                start_date=week_start.isoformat(),
                end_date=today.isoformat(),
                account_ids=account_ids,
            )
        except Exception as exc:
            logger.warning("Weekly trades fetch failed: %s", exc)
            activities = []
            fetch_failed = True

        for act in activities:
            if not isinstance(act, dict):
                continue
            action = _classify_action(act)
            if action not in ("BUY", "SELL"):
                continue

            instrument = act.get("symbol") or act.get("instrument") or {}
            if isinstance(instrument, dict):
                symbol = (
                    instrument.get("symbol")
                    or instrument.get("raw_symbol")
                    or instrument.get("ticker")
                )
                description = instrument.get("description")
            else:
                symbol = str(instrument)
                description = None

            try:
                units = float(act.get("units") or 0)
                price = float(act.get("price") or 0)
                amount = float(act.get("amount") or 0)
            except (TypeError, ValueError):
                continue

            trade_date_raw = (
                act.get("trade_date")
                or act.get("settlement_date")
                or act.get("date")
                or ""
            )
            trade_date_str = str(trade_date_raw)[:10]

            trades.append(
                TradeRow(
                    trade_date=trade_date_str,
                    symbol=symbol,
                    description=description,
                    action=action,
                    units=units,
                    price=price,
                    amount=round(amount, 2),
                )
            )
            notional = abs(amount) if amount else round(units * price, 2)
            if action == "BUY":
                total_buys += notional
            else:
                total_sells += notional

    trades.sort(key=lambda t: t.trade_date, reverse=True)

    # Compute week P/L using snapshots + deposits
    week_start_dt = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    snap_start_row = await db.execute(
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.user_id == current_user.id,
            PortfolioSnapshot.snapshot_at >= week_start_dt,
        )
        .order_by(PortfolioSnapshot.snapshot_at.asc())
        .limit(1)
    )
    snap_end_row = await db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.user_id == current_user.id)
        .order_by(PortfolioSnapshot.snapshot_at.desc())
        .limit(1)
    )
    first_snap = snap_start_row.scalar_one_or_none()
    last_snap = snap_end_row.scalar_one_or_none()

    week_start_value = float(first_snap.total_value) if first_snap else None
    week_end_value = float(last_snap.total_value) if last_snap else None

    deposit_rows = await db.execute(
        select(Deposit).where(
            Deposit.user_id == current_user.id,
            Deposit.deposited_at >= week_start_dt,
        )
    )
    week_deposits = round(
        sum(float(d.amount) for d in deposit_rows.scalars().all()), 2
    )

    week_pnl: float | None = None
    week_pnl_pct: float | None = None
    if week_start_value is not None and week_end_value is not None:
        week_pnl = round(week_end_value - week_start_value - week_deposits, 2)
        denom = week_start_value + week_deposits
        if denom > 0:
            week_pnl_pct = round(week_pnl / denom, 6)

    return WeeklyReportResponse(
        week_start=week_start.isoformat(),
        week_end=today.isoformat(),
        trades=trades,
        total_buys=round(total_buys, 2),
        total_sells=round(total_sells, 2),
        net_cash_flow=round(total_sells - total_buys, 2),
        week_start_value=week_start_value,
        week_end_value=week_end_value,
        week_deposits=week_deposits,
        week_pnl=week_pnl,
        week_pnl_pct=week_pnl_pct,
        available=not fetch_failed,
        message=(
            "Could not fetch trade history from SnapTrade."
            if fetch_failed
            else None
        ),
    )
