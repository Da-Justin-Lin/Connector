"""
Trading-signal ingest + read.

The external stock-agent POSTs signals here (authenticated by a shared secret
header) instead of emailing them — Gmail SMTP times out from the agent's host.
The dashboard reads them back with the normal user JWT.
"""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.trading_signal import TradingSignal
from app.models.user import User
from app.schemas.trading_signal import (
    TradingSignalCreate,
    TradingSignalRead,
    TradingSignalsResponse,
)

router = APIRouter()


def _verify_agent_key(x_agent_key: str | None) -> None:
    expected = settings.agent_ingest_key
    if not expected:
        # Fail closed: if no key is configured, ingest is disabled entirely
        # rather than silently accepting anonymous writes.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signal ingest is not configured",
        )
    if not x_agent_key or not secrets.compare_digest(x_agent_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent key"
        )


@router.post("", response_model=TradingSignalRead, status_code=201)
async def ingest_signal(
    payload: TradingSignalCreate,
    x_agent_key: str | None = Header(default=None, alias="X-Agent-Key"),
    db: AsyncSession = Depends(get_db),
):
    _verify_agent_key(x_agent_key)

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
