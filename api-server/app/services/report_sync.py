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
    fetch_account_orders_async,
    fetch_account_positions_async,
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
    account: InvestmentAccount, days: int
) -> tuple[InvestmentAccount, list | None, object | None]:
    """Fetch orders + positions for one account (network only, no DB)."""
    snap_id = account.snaptrade_account_id
    orders: list | None = None
    try:
        orders = await _fetch_orders_with_fallback(snap_id, days)
    except Exception as exc:
        logger.warning("Order sync fetch failed for %s: %s", snap_id, exc)

    positions: object | None = None
    try:
        positions = await fetch_account_positions_async(snap_id)
    except Exception as exc:
        logger.warning("Holdings sync fetch failed for %s: %s", snap_id, exc)

    return account, orders, positions


async def _persist_account_data(
    session: AsyncSession,
    account: InvestmentAccount,
    orders: list | None,
    positions: object | None,
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

    session.add(account)


async def sync_accounts(
    session: AsyncSession, accounts: list[InvestmentAccount], *, days: int
) -> None:
    """Fetch (concurrently) then persist (sequentially) for the given accounts.

    Caller is responsible for committing.
    """
    if not accounts:
        return
    fetched = await asyncio.gather(
        *(_fetch_account_data(a, days) for a in accounts)
    )
    now = datetime.now(timezone.utc)
    for account, orders, positions in fetched:
        await _persist_account_data(session, account, orders, positions, now)


async def refresh_accounts_background(
    account_ids: list[uuid.UUID], days: int
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
            await sync_accounts(session, rows, days=days)
            await session.commit()
        logger.info("Background order refresh synced %d accounts", len(pending))
    except Exception as exc:
        logger.exception("Background order refresh failed: %s", exc)
    finally:
        for aid in pending:
            _syncing.discard(aid)
