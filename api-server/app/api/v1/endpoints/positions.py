"""
Position lifecycle: the user confirms a BUY signal -> an OPEN position with its
own id. Every exit alert the agent emits carries that position_id, so two BUYs
on the same ticker stay distinct. The agent monitors OPEN positions but never
closes them — status moves to CLOSED only when the user confirms the sale.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_agent_key
from app.core.database import get_db
from app.models.position import Position
from app.models.trading_signal import TradingSignal
from app.models.user import User
from app.schemas.position import (
    MonitorPosition,
    MonitorResponse,
    PositionClose,
    PositionCreate,
    PositionRead,
    PositionsResponse,
)
from app.schemas.trading_signal import TradingSignalRead

router = APIRouter()


@router.post("", response_model=PositionRead, status_code=201)
async def create_position(
    payload: PositionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    position = Position(
        user_id=current_user.id,
        ticker=payload.ticker.upper(),
        shares=payload.shares,
        entry_price=payload.entry_price,
        entry_date=payload.entry_date or datetime.now(timezone.utc),
        initial_stop=payload.initial_stop,
        target=payload.target,
        source_signal_id=payload.source_signal_id,
        notes=payload.notes,
        status="OPEN",
    )
    db.add(position)
    await db.commit()
    await db.refresh(position)
    return PositionRead.model_validate(position)


@router.get("", response_model=PositionsResponse)
async def list_positions(
    status: str | None = Query(default=None, description="Filter OPEN/CLOSED"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Position)
        .where(Position.user_id == current_user.id)
        .order_by(Position.opened_at.desc())
    )
    if status:
        stmt = stmt.where(Position.status == status.upper())
    rows = await db.execute(stmt)
    positions = rows.scalars().all()

    # Attach exit alerts per position in one query.
    pos_ids = [p.id for p in positions]
    alerts_by_pos: dict[uuid.UUID, list[TradingSignalRead]] = {pid: [] for pid in pos_ids}
    if pos_ids:
        alert_rows = await db.execute(
            select(TradingSignal)
            .where(TradingSignal.position_id.in_(pos_ids))
            .order_by(TradingSignal.created_at.desc())
        )
        for a in alert_rows.scalars().all():
            alerts_by_pos.setdefault(a.position_id, []).append(
                TradingSignalRead.model_validate(a)
            )

    result = []
    for p in positions:
        pr = PositionRead.model_validate(p)
        pr.alerts = alerts_by_pos.get(p.id, [])
        result.append(pr)
    return PositionsResponse(positions=result)


@router.post("/{position_id}/close", response_model=PositionRead)
async def close_position(
    position_id: uuid.UUID,
    payload: PositionClose,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(
        select(Position).where(
            Position.id == position_id, Position.user_id == current_user.id
        )
    )
    position = row.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    if position.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Position already closed")

    position.status = "CLOSED"
    position.exit_price = payload.exit_price
    position.exit_reason = payload.exit_reason
    position.closed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(position)
    return PositionRead.model_validate(position)


@router.get(
    "/monitor", response_model=MonitorResponse, dependencies=[Depends(require_agent_key)]
)
async def monitor_positions(db: AsyncSession = Depends(get_db)):
    """All OPEN positions across users, for the agent's exit-scan loop."""
    rows = await db.execute(select(Position).where(Position.status == "OPEN"))
    positions = rows.scalars().all()
    return MonitorResponse(
        positions=[MonitorPosition.model_validate(p) for p in positions]
    )
