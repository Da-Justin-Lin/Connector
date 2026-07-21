import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.broker_order import BrokerOrder
from app.models.investment_account import InvestmentAccount
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.user import User
from app.schemas.investment_account import (
    AccountSection,
    ConnectionUrlResponse,
    HistoryPoint,
    HistoryResponse,
    HoldingRead,
    HoldingsResponse,
    PositionContext,
    PositionDetailResponse,
    PositionTrade,
    ReturnsResponse,
    SyncAccountsResponse,
)
from app.services.market_data_service import fetch_candles, fetch_next_earnings, fetch_sectors
from app.services.position_analytics import (
    compute_concentration,
    compute_trend_stats,
    days_until,
)
from app.services.report_sync import ensure_holdings_cached, refresh_connection_status
from app.services.snaptrade_service import (
    create_connection_portal_url,
    create_reconnect_portal_url,
    fetch_account_balance,
    fetch_balance_history_async,
    fetch_return_rates,
    find_account_authorization,
    list_accounts,
    list_brokerage_authorizations,
    remove_brokerage_authorization,
)
from app.services.trade_parsing import normalize_instrument_key, parse_order

router = APIRouter()


@router.post("/connection-url", response_model=ConnectionUrlResponse)
async def get_connection_url(
    current_user: User = Depends(get_current_user),
):
    try:
        url = create_connection_portal_url()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SnapTrade error: {exc}") from exc
    return ConnectionUrlResponse(redirect_uri=url)


def _extract_auth_id(acct: dict) -> str | None:
    """Pull the brokerage_authorization (connection) id off an account payload,
    which SnapTrade returns as either a nested object or a bare id string."""
    ba = acct.get("brokerage_authorization")
    if isinstance(ba, dict):
        return ba.get("id")
    if isinstance(ba, str):
        return ba
    return None


@router.post("/sync-accounts", response_model=SyncAccountsResponse)
async def sync_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        remote_accounts = list_accounts()
        # Connection health lives on the authorizations endpoint, not on the
        # account payload — fetch it to know which accounts are disabled.
        authorizations = list_brokerage_authorizations()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SnapTrade error: {exc}") from exc

    disabled_by_auth = {
        a.get("id"): bool(a.get("disabled"))
        for a in authorizations
        if isinstance(a, dict) and a.get("id")
    }

    existing_rows = await db.execute(
        select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    )
    existing_by_id = {
        a.snaptrade_account_id: a for a in existing_rows.scalars().all()
    }

    synced = 0
    for acct in remote_accounts:
        snap_id = acct.get("id")
        if not snap_id:
            continue

        institution = acct.get("institution_name") or acct.get("brokerage_authorization")
        name = acct.get("name")
        meta = acct.get("meta") or {}
        account_type = acct.get("raw_type") or meta.get("type")
        account_number = acct.get("number")
        auth_id = _extract_auth_id(acct)
        disabled = disabled_by_auth.get(auth_id, False) if auth_id else False

        row = existing_by_id.get(snap_id)
        if row:
            row.institution_name = institution if isinstance(institution, str) else row.institution_name
            row.account_name = name
            row.account_type = account_type
            row.account_number = account_number
            row.brokerage_authorization_id = auth_id
            row.connection_disabled = disabled
        else:
            db.add(
                InvestmentAccount(
                    user_id=current_user.id,
                    snaptrade_account_id=snap_id,
                    institution_name=institution if isinstance(institution, str) else None,
                    account_name=name,
                    account_type=account_type,
                    account_number=account_number,
                    brokerage_authorization_id=auth_id,
                    connection_disabled=disabled,
                )
            )
        synced += 1

    await db.commit()
    return SyncAccountsResponse(accounts_synced=synced)


@router.post("/accounts/{account_id}/reconnect", response_model=ConnectionUrlResponse)
async def reconnect_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a Connection Portal URL that re-authorizes this account's existing
    (disabled) SnapTrade connection instead of creating a duplicate one."""
    row = (
        await db.execute(
            select(InvestmentAccount).where(
                InvestmentAccount.user_id == current_user.id,
                InvestmentAccount.snaptrade_account_id == account_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")

    # Prefer the stored authorization id; fall back to a live lookup for rows
    # synced before this field existed.
    authorization_id = row.brokerage_authorization_id
    if not authorization_id:
        authorization_id = await asyncio.to_thread(
            find_account_authorization, account_id
        )
    if not authorization_id:
        raise HTTPException(
            status_code=404, detail="No SnapTrade connection to reconnect"
        )

    try:
        url = await asyncio.to_thread(
            create_reconnect_portal_url, authorization_id
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SnapTrade error: {exc}") from exc

    return ConnectionUrlResponse(redirect_uri=url)


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently disconnect a brokerage account.

    Removes the SnapTrade connection so it can't re-sync, then deletes the local
    account and its cached data (orders + deposits cascade at the DB level).
    """
    row = (
        await db.execute(
            select(InvestmentAccount).where(
                InvestmentAccount.user_id == current_user.id,
                InvestmentAccount.snaptrade_account_id == account_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")

    # Drop the SnapTrade connection first. If this fails we keep the local row
    # so the account isn't silently re-added on the next sync. A missing
    # authorization (already disconnected) is fine — fall through to local delete.
    try:
        authorization_id = await asyncio.to_thread(
            find_account_authorization, account_id
        )
        if authorization_id:
            await asyncio.to_thread(
                remove_brokerage_authorization, authorization_id
            )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"SnapTrade error: {exc}"
        ) from exc

    await db.delete(row)
    await db.commit()


def _extract_cash(balance_payload: dict | list) -> float:
    """SnapTrade balance responses come as either a list of currency entries
    (one per currency) or a dict with the same. Sum the USD-equivalent cash."""
    entries: list = []
    if isinstance(balance_payload, list):
        entries = balance_payload
    elif isinstance(balance_payload, dict):
        entries = balance_payload.get("results") or balance_payload.get("balances") or []

    total = 0.0
    for entry in entries:
        cash = entry.get("cash") if isinstance(entry, dict) else None
        if cash is None:
            continue
        try:
            total += float(cash)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def _holdings_from_cache(positions_payload) -> list[HoldingRead]:
    """Parse a cached positions payload into HoldingRead rows."""
    if isinstance(positions_payload, dict):
        positions = (
            positions_payload.get("results")
            or positions_payload.get("positions")
            or []
        )
    elif isinstance(positions_payload, list):
        positions = positions_payload
    else:
        positions = []

    holdings: list[HoldingRead] = []
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        instrument = pos.get("instrument") or {}
        ticker = instrument.get("symbol") or instrument.get("raw_symbol")
        name = instrument.get("description")
        security_type = instrument.get("kind") or ""

        quantity = float(pos.get("units") or 0)
        price = float(pos.get("price") or 0)
        cost_per_share = pos.get("cost_basis") or pos.get("average_purchase_price")
        cost_basis = (
            round(float(cost_per_share) * quantity, 2)
            if cost_per_share is not None
            else None
        )

        holdings.append(
            HoldingRead(
                ticker=ticker,
                name=name,
                security_type=str(security_type or ""),
                quantity=quantity,
                institution_price=price,
                market_value=round(quantity * price, 2),
                cost_basis=cost_basis,
            )
        )
    return holdings


@router.get("/holdings", response_model=HoldingsResponse)
async def get_holdings(
    background: BackgroundTasks,
    account_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(InvestmentAccount.snaptrade_account_id == account_id)
    account_rows = await db.execute(stmt)
    accounts = account_rows.scalars().all()

    if not accounts:
        return HoldingsResponse(
            accounts=[], total_value=0.0, total_cash=0.0, connected_accounts=0
        )

    # Serve from the local cache; cold-sync misses inline, refresh stale ones
    # in the background.
    accounts, _sync_error, stale = await ensure_holdings_cached(
        db, accounts, background
    )
    # Piggyback on the holdings-refresh cadence to keep each account's
    # connection (disabled) status current, so a lost connection surfaces a
    # reconnect prompt without the user having to re-sync manually. Also fire on
    # first sight of an account (no authorization id yet) so it populates fast.
    if stale or any(a.brokerage_authorization_id is None for a in accounts):
        background.add_task(refresh_connection_status, current_user.id)

    sections: list[AccountSection] = []
    for account in accounts:
        holdings = _holdings_from_cache(account.holdings_cache)
        cash = _extract_cash(account.balance_cache or [])
        holdings_value = round(sum(h.market_value for h in holdings), 2)
        sections.append(
            AccountSection(
                snaptrade_account_id=account.snaptrade_account_id,
                institution_name=account.institution_name,
                account_name=account.account_name,
                account_type=account.account_type,
                cash=cash,
                holdings_value=holdings_value,
                total_value=round(holdings_value + cash, 2),
                holdings=holdings,
                connection_disabled=account.connection_disabled,
            )
        )

    total_value = round(sum(s.total_value for s in sections), 2)
    total_cash = round(sum(s.cash for s in sections), 2)
    synced_times = [a.holdings_synced_at for a in accounts if a.holdings_synced_at]
    last_synced_at = min(synced_times).isoformat() if synced_times else None

    return HoldingsResponse(
        accounts=sections,
        total_value=total_value,
        total_cash=total_cash,
        connected_accounts=len(accounts),
        stale=stale,
        last_synced_at=last_synced_at,
    )


@router.get("/positions/{symbol}", response_model=PositionDetailResponse)
async def get_position_detail(
    symbol: str,
    background: BackgroundTasks,
    account_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated position summary + this symbol's trade history.

    Everything is read from the local caches (holdings + stored broker orders),
    so this never blocks on a live SnapTrade call beyond the usual cold-sync.
    """
    target = normalize_instrument_key(symbol)

    stmt = select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(InvestmentAccount.snaptrade_account_id == account_id)
    accounts = (await db.execute(stmt)).scalars().all()

    if not accounts or not target:
        return PositionDetailResponse(symbol=symbol.upper(), held=False, quantity=0.0)

    accounts, _sync_error, _stale = await ensure_holdings_cached(db, accounts, background)
    account_uuids = [a.id for a in accounts]

    # Aggregate the current position across accounts from cached holdings.
    # Also build a whole-book picture (every ticker's market value + cash) so we
    # can size this position's concentration against the rest of the portfolio.
    qty = 0.0
    cost_basis = 0.0
    has_cost = False
    market_value = 0.0
    current_price: float | None = None
    name: str | None = None
    holding_accounts = 0
    portfolio_value = 0.0
    book_by_ticker: dict[str, float] = {}
    for account in accounts:
        portfolio_value += _extract_cash(account.balance_cache or [])
        held_here = False
        for h in _holdings_from_cache(account.holdings_cache):
            portfolio_value += h.market_value
            key = normalize_instrument_key(h.ticker)
            if key:
                book_by_ticker[key] = book_by_ticker.get(key, 0.0) + h.market_value
            if key != target:
                continue
            held_here = True
            qty += h.quantity
            market_value += h.market_value
            if h.institution_price:
                current_price = h.institution_price
            name = name or h.name
            if h.cost_basis is not None:
                cost_basis += h.cost_basis
                has_cost = True
        if held_here:
            holding_accounts += 1

    # Trade history for this symbol from the stored broker orders.
    trades: list[PositionTrade] = []
    if account_uuids:
        order_rows = await db.execute(
            select(BrokerOrder)
            .where(BrokerOrder.investment_account_id.in_(account_uuids))
            .order_by(BrokerOrder.executed_at.desc())
        )
        for bo in order_rows.scalars().all():
            order = bo.payload
            if not isinstance(order, dict):
                continue
            state = str(order.get("state") or order.get("status") or "").upper()
            if state and state not in ("EXECUTED", "FILLED", "COMPLETED"):
                continue
            parsed = parse_order(order)
            if parsed is None or normalize_instrument_key(parsed["symbol"]) != target:
                continue
            trades.append(
                PositionTrade(
                    trade_date=parsed["trade_date"],
                    action=parsed["action"],
                    units=parsed["units"],
                    price=parsed["price"],
                    amount=parsed["amount"],
                    asset_type=parsed["asset_type"],
                    description=parsed["description"],
                )
            )
            if len(trades) >= 200:
                break

    # --- Pre-trade context: 52-week range/trend, earnings, concentration -----
    # Market-data calls run concurrently and degrade to None on failure, so a
    # slow or down upstream never blocks the (cache-backed) position summary.
    sym = symbol.upper()
    book_tickers = list(book_by_ticker.keys())
    candles_res, earnings_res, sectors_res = await asyncio.gather(
        fetch_candles(sym, "1Y"),
        fetch_next_earnings(sym),
        fetch_sectors(book_tickers),
        return_exceptions=True,
    )

    context_data: dict = {}
    if isinstance(candles_res, dict):
        context_data.update(
            compute_trend_stats(candles_res.get("candles", []), current_price)
        )
    if isinstance(earnings_res, str):
        context_data["next_earnings_date"] = earnings_res
        context_data["days_to_earnings"] = days_until(earnings_res)
    if qty > 1e-9 and portfolio_value > 0:
        sectors = sectors_res if isinstance(sectors_res, dict) else {}
        target_sector = sectors.get(sym)
        sector_value = (
            sum(v for k, v in book_by_ticker.items() if sectors.get(k) == target_sector)
            if target_sector else 0.0
        )
        context_data.update(
            compute_concentration(
                market_value, portfolio_value, target_sector, sector_value
            )
        )
    context = PositionContext(**context_data) if context_data else None

    held = qty > 1e-9
    avg_cost = round(cost_basis / qty, 4) if has_cost and qty > 1e-9 else None
    unrealized = round(market_value - cost_basis, 2) if has_cost else None
    unrealized_pct = (
        round((market_value - cost_basis) / cost_basis, 6)
        if has_cost and cost_basis > 0
        else None
    )

    return PositionDetailResponse(
        symbol=symbol.upper(),
        name=name,
        held=held,
        quantity=round(qty, 4),
        avg_cost=avg_cost,
        cost_basis=round(cost_basis, 2) if has_cost else None,
        current_price=current_price,
        market_value=round(market_value, 2) if held else None,
        unrealized_pnl=unrealized,
        unrealized_pnl_pct=unrealized_pct,
        accounts=holding_accounts,
        trades=trades,
        context=context,
    )


_RANGE_TO_DAYS = {
    "1m": 31,
    "3m": 92,
    "6m": 183,
    "ytd": None,  # filter applied separately
    "1y": 366,
}
_INTRADAY_RANGE = "1d"


def _normalize_history_entry(entry: dict) -> tuple[str, float] | None:
    """Pull (date_str, value) from a SnapTrade balance-history row.
    Returns None if shape is unrecognized."""
    if not isinstance(entry, dict):
        return None
    date_val = entry.get("date") or entry.get("as_of") or entry.get("timestamp")
    value_val = (
        entry.get("total_value")
        or entry.get("value")
        or entry.get("balance")
        or entry.get("equity")
    )
    if date_val is None or value_val is None:
        return None
    try:
        return str(date_val), float(value_val)
    except (TypeError, ValueError):
        return None


async def _get_intraday_history(
    db: AsyncSession, user_id
) -> HistoryResponse:
    """Serve the 1D range from our portfolio_snapshots table."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = await db.execute(
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.snapshot_at >= since,
        )
        .order_by(PortfolioSnapshot.snapshot_at.asc())
    )
    snapshots = rows.scalars().all()
    if not snapshots:
        return HistoryResponse(
            series=[],
            available=True,
            message="Intraday data starts appearing during the next US market session.",
        )
    series = [
        HistoryPoint(date=s.snapshot_at.isoformat(), total_value=float(s.total_value))
        for s in snapshots
    ]
    return HistoryResponse(series=series, available=True, message=None)


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    range: str = "1y",
    account_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    range_key = (range or "1y").lower()

    if range_key == _INTRADAY_RANGE:
        return await _get_intraday_history(db, current_user.id)

    if range_key not in _RANGE_TO_DAYS:
        range_key = "1y"

    stmt = select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(InvestmentAccount.snaptrade_account_id == account_id)
    account_rows = await db.execute(stmt)
    accounts = account_rows.scalars().all()

    if not accounts:
        return HistoryResponse(series=[], available=True, message=None)

    any_success = False
    last_error: str | None = None

    # Fetch every account's balance history concurrently (offloaded to threads).
    payloads = await asyncio.gather(
        *(
            fetch_balance_history_async(account.snaptrade_account_id)
            for account in accounts
        ),
        return_exceptions=True,
    )
    # Build a per-account {date: value} series first. Accounts post their daily
    # balance at different times, so on the most recent date(s) some accounts have
    # no row yet — summing by raw date would drop them and understate the total.
    per_account_series: list[dict[str, float]] = []
    for payload in payloads:
        if isinstance(payload, Exception):
            last_error = str(payload)
            continue

        any_success = True
        rows: list = []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("results") or payload.get("history") or []

        series: dict[str, float] = {}
        for row in rows:
            parsed = _normalize_history_entry(row)
            if parsed is None:
                continue
            date_str, value = parsed
            series[date_str] = value
        if series:
            per_account_series.append(series)

    # Sum across accounts on the union of dates, carrying each account's
    # last-known value forward so a missing latest row never zeroes an account
    # out of the total ("All accounts" stays the true sum of its accounts).
    all_dates = sorted({d for s in per_account_series for d in s})
    aggregated: dict[str, float] = {}
    for series in per_account_series:
        last_val: float | None = None
        for d in all_dates:
            if d in series:
                last_val = series[d]
            if last_val is not None:
                aggregated[d] = aggregated.get(d, 0.0) + last_val

    if not any_success and last_error:
        return HistoryResponse(
            series=[],
            available=False,
            message="Historical balance data is not enabled on your SnapTrade plan yet.",
        )

    sorted_dates = sorted(aggregated.keys())

    if range_key == "ytd":
        year_prefix = sorted_dates[-1][:4] if sorted_dates else ""
        filtered_dates = [d for d in sorted_dates if d.startswith(year_prefix)]
    else:
        days = _RANGE_TO_DAYS[range_key]
        filtered_dates = sorted_dates[-days:] if days else sorted_dates

    series = [
        HistoryPoint(date=d, total_value=round(aggregated[d], 2)) for d in filtered_dates
    ]
    return HistoryResponse(series=series, available=True, message=None)


@router.get("/returns", response_model=ReturnsResponse)
async def get_returns(
    account_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(InvestmentAccount.snaptrade_account_id == account_id)
    account_rows = await db.execute(stmt)
    accounts = account_rows.scalars().all()

    if not accounts:
        return ReturnsResponse(rates={}, available=True, message=None)

    # Weight each account's rate by its current total value when there are
    # multiple. For one account this is just the account's own rates.
    weighted_sums: dict[str, float] = {}
    weight_totals: dict[str, float] = {}
    any_success = False

    for account in accounts:
        try:
            rate_payload = fetch_return_rates(account.snaptrade_account_id)
            balance_payload = fetch_account_balance(account.snaptrade_account_id)
        except Exception:
            continue

        any_success = True
        cash = _extract_cash(balance_payload)
        # Use cash as a weighting fallback so a single connected account always wins.
        weight = max(cash, 1.0)

        entries: list = []
        if isinstance(rate_payload, list):
            entries = rate_payload
        elif isinstance(rate_payload, dict):
            entries = (
                rate_payload.get("return_rates")
                or rate_payload.get("rates")
                or rate_payload.get("results")
                or []
            )

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            tf = entry.get("timeframe") or entry.get("range") or entry.get("period")
            rate = entry.get("rate_of_return") or entry.get("rate") or entry.get("return")
            if tf is None or rate is None:
                continue
            try:
                rate_val = float(rate)
            except (TypeError, ValueError):
                continue
            key = str(tf).upper()
            weighted_sums[key] = weighted_sums.get(key, 0.0) + rate_val * weight
            weight_totals[key] = weight_totals.get(key, 0.0) + weight

    if not any_success:
        return ReturnsResponse(
            rates={},
            available=False,
            message="Rate-of-return data is not enabled on your SnapTrade plan yet.",
        )

    rates = {
        tf: round(weighted_sums[tf] / weight_totals[tf], 6)
        for tf in weighted_sums
        if weight_totals.get(tf)
    }
    return ReturnsResponse(rates=rates, available=True, message=None)
