import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.investment_account import InvestmentAccount
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.user import User
from app.services.snaptrade_service import (
    fetch_account_balance,
    fetch_account_positions,
)

logger = logging.getLogger(__name__)

SNAPSHOT_RETENTION_DAYS = 7


def _extract_cash(balance_payload) -> float:
    entries: list = []
    if isinstance(balance_payload, list):
        entries = balance_payload
    elif isinstance(balance_payload, dict):
        entries = balance_payload.get("results") or balance_payload.get("balances") or []
    total = 0.0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            total += float(entry.get("cash") or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def _compute_account_totals(account_id: str) -> tuple[float, float]:
    """Returns (holdings_value, cash) for a single brokerage account."""
    holdings_value = 0.0
    try:
        payload = fetch_account_positions(account_id)
        positions = payload.get("results") or payload.get("positions") or []
        for pos in positions:
            try:
                quantity = float(pos.get("units") or 0)
                price = float(pos.get("price") or 0)
                holdings_value += quantity * price
            except (TypeError, ValueError):
                continue
    except Exception as exc:
        logger.warning("Snapshot: positions fetch failed for %s: %s", account_id, exc)

    try:
        balance_payload = fetch_account_balance(account_id)
        cash = _extract_cash(balance_payload)
    except Exception as exc:
        logger.warning("Snapshot: balance fetch failed for %s: %s", account_id, exc)
        cash = 0.0

    return round(holdings_value, 2), cash


async def _snapshot_one_user(session: AsyncSession, user_id) -> None:
    account_rows = await session.execute(
        select(InvestmentAccount).where(InvestmentAccount.user_id == user_id)
    )
    accounts = account_rows.scalars().all()
    if not accounts:
        return

    total_value = 0.0
    total_cash = 0.0
    for account in accounts:
        holdings, cash = _compute_account_totals(account.snaptrade_account_id)
        total_value += holdings + cash
        total_cash += cash

    snapshot = PortfolioSnapshot(
        user_id=user_id,
        snapshot_at=datetime.now(timezone.utc),
        total_value=round(total_value, 2),
        total_cash=round(total_cash, 2),
    )
    session.add(snapshot)


async def snapshot_all_users() -> None:
    """Take a snapshot for every user with at least one connected account."""
    async with AsyncSessionLocal() as session:
        user_ids = (
            await session.execute(
                select(InvestmentAccount.user_id).distinct()
            )
        ).scalars().all()
        if not user_ids:
            return

        for user_id in user_ids:
            try:
                await _snapshot_one_user(session, user_id)
            except Exception as exc:
                logger.exception("Snapshot failed for user %s: %s", user_id, exc)

        await session.commit()
    logger.info("Portfolio snapshot completed for %d users", len(user_ids))


async def prune_old_snapshots() -> None:
    """Delete snapshots older than the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(PortfolioSnapshot).where(PortfolioSnapshot.snapshot_at < cutoff)
        )
        await session.commit()
    logger.info("Pruned portfolio_snapshots older than %s", cutoff.isoformat())
