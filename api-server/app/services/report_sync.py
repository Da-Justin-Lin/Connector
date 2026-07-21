"""Sync brokerage orders + holdings from SnapTrade into the local cache.

The weekly report reads from `broker_orders` and `investment_accounts`'
holdings cache so the request path never blocks on SnapTrade. This module
does the actual fetching/upserting, both for the cold (blocking) first load
and for background revalidation.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.broker_order import BrokerOrder
from app.models.investment_account import InvestmentAccount
from app.services.snaptrade_service import (
    fetch_account_balance_async,
    fetch_account_orders_async,
    fetch_account_positions_async,
    list_accounts,
    list_brokerage_authorizations,
)
from app.services.trade_parsing import (
    order_dedup_key,
    order_executed_timestamp,
    parse_executed_datetime,
)

logger = logging.getLogger(__name__)

# Lookback windows passed to SnapTrade's orders endpoint.
COLD_BACKFILL_DAYS = 90
INCREMENTAL_DAYS = 30

# How old the current-week cache may get before a background refresh fires.
REFRESH_TTL = timedelta(minutes=3)

# Accounts currently being synced in the background, to avoid duplicate work
# when several requests land at once.
_syncing: set[uuid.UUID] = set()


async def _fetch_orders_with_fallback(snaptrade_account_id: str, days: int) -> list:
    try:
        return await fetch_account_orders_async(
            snaptrade_account_id, state="EXECUTED", days=days
        )
    except Exception as exc:
        logger.warning(
            "Order sync: EXECUTED fetch failed for %s, retrying without state: %s",
            snaptrade_account_id,
            exc,
        )
        return await fetch_account_orders_async(snaptrade_account_id)


async def _fetch_account_data(
    account: InvestmentAccount, days: int, include_orders: bool
) -> tuple[InvestmentAccount, list | None, object | None, object | None]:
    """Fetch orders (optional) + positions + balance for one account.

    Network only, no DB. `include_orders=False` skips the orders call for
    callers (the overview) that only need holdings + cash.
    """
    snap_id = account.snaptrade_account_id
    orders: list | None = None
    if include_orders:
        try:
            orders = await _fetch_orders_with_fallback(snap_id, days)
        except Exception as exc:
            logger.warning("Order sync fetch failed for %s: %s", snap_id, exc)

    positions: object | None = None
    try:
        positions = await fetch_account_positions_async(snap_id)
    except Exception as exc:
        logger.warning("Holdings sync fetch failed for %s: %s", snap_id, exc)

    balance: object | None = None
    try:
        balance = await fetch_account_balance_async(snap_id)
    except Exception as exc:
        logger.warning("Balance sync fetch failed for %s: %s", snap_id, exc)

    return account, orders, positions, balance


async def _persist_account_data(
    session: AsyncSession,
    account: InvestmentAccount,
    orders: list | None,
    positions: object | None,
    balance: object | None,
    now: datetime,
) -> None:
    """Upsert one account's fetched data. Run sequentially per session."""
    if orders is not None:
        rows = []
        for order in orders:
            if not isinstance(order, dict):
                continue
            rows.append(
                {
                    "investment_account_id": account.id,
                    "broker_order_id": order_dedup_key(order),
                    "executed_at": parse_executed_datetime(
                        order_executed_timestamp(order)
                    ),
                    "state": (
                        str(order.get("state") or order.get("status") or "")[:64]
                        or None
                    ),
                    "payload": order,
                }
            )
        if rows:
            # Dedup within this batch (broker can repeat a synthetic key).
            unique: dict[tuple, dict] = {}
            for r in rows:
                unique[(r["investment_account_id"], r["broker_order_id"])] = r
            stmt = pg_insert(BrokerOrder).values(list(unique.values()))
            stmt = stmt.on_conflict_do_update(
                index_elements=["investment_account_id", "broker_order_id"],
                set_={
                    "executed_at": stmt.excluded.executed_at,
                    "state": stmt.excluded.state,
                    "payload": stmt.excluded.payload,
                    "updated_at": func.now(),
                },
            )
            await session.execute(stmt)
        account.orders_synced_at = now

    if positions is not None:
        account.holdings_cache = positions
        account.holdings_synced_at = now
    if balance is not None:
        account.balance_cache = balance
        account.holdings_synced_at = now

    session.add(account)


async def sync_accounts(
    session: AsyncSession,
    accounts: list[InvestmentAccount],
    *,
    days: int,
    include_orders: bool = True,
) -> None:
    """Fetch (concurrently) then persist (sequentially) for the given accounts.

    Caller is responsible for committing.
    """
    if not accounts:
        return
    fetched = await asyncio.gather(
        *(_fetch_account_data(a, days, include_orders) for a in accounts)
    )
    now = datetime.now(timezone.utc)
    for account, orders, positions, balance in fetched:
        await _persist_account_data(
            session, account, orders, positions, balance, now
        )


async def refresh_accounts_background(
    account_ids: list[uuid.UUID], days: int, include_orders: bool = True
) -> None:
    """Background revalidation: sync the given accounts in a fresh session."""
    pending = [aid for aid in account_ids if aid not in _syncing]
    if not pending:
        return
    _syncing.update(pending)
    try:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(InvestmentAccount).where(
                        InvestmentAccount.id.in_(pending)
                    )
                )
            ).scalars().all()
            await sync_accounts(
                session, rows, days=days, include_orders=include_orders
            )
            await session.commit()
        logger.info("Background account refresh synced %d accounts", len(pending))
    except Exception as exc:
        logger.exception("Background account refresh failed: %s", exc)
    finally:
        for aid in pending:
            _syncing.discard(aid)


def _extract_auth_id(acct: dict) -> str | None:
    ba = acct.get("brokerage_authorization")
    if isinstance(ba, dict):
        return ba.get("id")
    if isinstance(ba, str):
        return ba
    return None


async def refresh_connection_status(user_id: uuid.UUID) -> None:
    """Refresh each account's disabled flag from SnapTrade in the background.

    A disabled connection keeps serving its last-good snapshot, so without this
    an account would silently freeze with no way for the UI to prompt a
    reconnect. Runs off the holdings-refresh cadence, so it stays current
    without an extra client round-trip.
    """
    try:
        accounts, auths = await asyncio.gather(
            asyncio.to_thread(list_accounts),
            asyncio.to_thread(list_brokerage_authorizations),
        )
    except Exception as exc:
        logger.warning("Connection status refresh: fetch failed: %s", exc)
        return

    disabled_by_auth = {
        a.get("id"): bool(a.get("disabled"))
        for a in auths
        if isinstance(a, dict) and a.get("id")
    }
    auth_by_account = {
        acct.get("id"): _extract_auth_id(acct)
        for acct in accounts
        if isinstance(acct, dict) and acct.get("id")
    }

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(InvestmentAccount).where(
                    InvestmentAccount.user_id == user_id
                )
            )
        ).scalars().all()
        changed = False
        for r in rows:
            auth = auth_by_account.get(r.snaptrade_account_id)
            disabled = disabled_by_auth.get(auth, False) if auth else False
            if r.brokerage_authorization_id != auth or r.connection_disabled != disabled:
                r.brokerage_authorization_id = auth
                r.connection_disabled = disabled
                changed = True
        if changed:
            await session.commit()


def holdings_is_stale(account: InvestmentAccount, now: datetime) -> bool:
    """Whether an account's cached holdings/balance need a background refresh."""
    if account.holdings_synced_at is None:
        return True
    return account.holdings_synced_at < now - REFRESH_TTL


async def ensure_holdings_cached(session, accounts, background):
    """Serve overview data from cache; cold-sync misses, refresh stale ones.

    Returns (accounts, sync_error, stale): `accounts` is reloaded after a
    failed cold sync (rollback expires the ORM instances), so callers should
    use the returned list. `stale` is True when a background refresh fired.
    """
    if not accounts:
        return accounts, None, False

    now = datetime.now(timezone.utc)
    sync_error: str | None = None
    # Capture ids up front: a rollback expires the ORM instances, after which
    # attribute access would trigger an illegal async lazy-load.
    account_ids = [a.id for a in accounts]

    cold = [a for a in accounts if a.holdings_synced_at is None]
    if cold:
        try:
            await sync_accounts(
                session, cold, days=INCREMENTAL_DAYS, include_orders=False
            )
            await session.commit()
        except Exception as exc:
            logger.warning("Cold holdings sync failed: %s", exc)
            sync_error = f"{type(exc).__name__}: {exc}"
            await session.rollback()
            stmt = select(InvestmentAccount).where(
                InvestmentAccount.id.in_(account_ids)
            )
            accounts = (await session.execute(stmt)).scalars().all()

    stale_ids = [
        a.id
        for a in accounts
        if a.holdings_synced_at is not None and holdings_is_stale(a, now)
    ]
    if stale_ids:
        background.add_task(
            refresh_accounts_background, stale_ids, INCREMENTAL_DAYS, False
        )

    return accounts, sync_error, bool(stale_ids)
