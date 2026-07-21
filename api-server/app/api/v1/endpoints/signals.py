"""
Trading-signal ingest + read.

The external stock-agent POSTs signals here (authenticated by a shared secret
header) instead of emailing them — Gmail SMTP times out from the agent's host.
The dashboard reads them back with the normal user JWT.

Two kinds of rows land here:
  - entry signals (BUY/SELL/HOLD), broadcast for the whole watchlist
  - exit alerts (HARD_STOP/TARGET_HIT/TRAIL_RAISED/...), each tagged with the
    position_id it belongs to
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_agent_key
from app.core.database import get_db
from app.models.trading_signal import TradingSignal
from app.models.user import User
from app.schemas.trading_signal import (
    TradingSignalCreate,
    TradingSignalRead,
    TradingSignalsResponse,
)

router = APIRouter()


@router.post("", status_code=201, dependencies=[Depends(require_agent_key)])
async def ingest_signal(
    payload: TradingSignalCreate,
    db: AsyncSession = Depends(get_db),
):
    # HOLD means "do nothing" — never store it, so the feed stays actionable-only.
    if payload.signal.upper() == "HOLD":
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    signal = TradingSignal(**payload.model_dump())
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return TradingSignalRead.model_validate(signal)


@router.get("", response_model=TradingSignalsResponse)
async def list_signals(
    limit: int = Query(default=50, ge=1, le=200),
    signal: str | None = Query(default=None, description="Filter BUY/SELL/HOLD"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TradingSignal).order_by(TradingSignal.created_at.desc()).limit(limit)
    if signal:
        stmt = stmt.where(TradingSignal.signal == signal.upper())

    rows = await db.execute(stmt)
    signals = rows.scalars().all()
    return TradingSignalsResponse(
        signals=[TradingSignalRead.model_validate(s) for s in signals]
    )


@router.delete(
    "/{signal_id}", status_code=204, dependencies=[Depends(require_agent_key)]
)
async def delete_signal(
    signal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Remove a signal (cleanup for test/stale rows). Agent-key gated."""
    row = await db.execute(select(TradingSignal).where(TradingSignal.id == signal_id))
    sig = row.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    await db.delete(sig)
    await db.commit()
