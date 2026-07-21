import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.trading_signal import TradingSignalRead


class PositionCreate(BaseModel):
    ticker: str
    shares: float
    entry_price: float
    initial_stop: float
    target: float
    entry_date: datetime | None = None  # defaults to now on the server
    source_signal_id: uuid.UUID | None = None
    notes: str | None = None


class PositionClose(BaseModel):
    exit_price: float
    exit_reason: str | None = "manual"


class PositionRead(BaseModel):
    id: uuid.UUID
    ticker: str
    shares: float
    entry_price: float
    entry_date: datetime
    initial_stop: float
    target: float
    status: str
    notes: str | None
    source_signal_id: uuid.UUID | None
    exit_price: float | None
    exit_reason: str | None
    opened_at: datetime
    closed_at: datetime | None
    # Exit alerts (HARD_STOP / TARGET_HIT / TRAIL_RAISED / ...) tied to this position.
    alerts: list[TradingSignalRead] = []

    model_config = {"from_attributes": True}


class PositionsResponse(BaseModel):
    positions: list[PositionRead]


class MonitorPosition(BaseModel):
    """Shape the agent needs to run exit checks against an open position."""

    id: uuid.UUID
    ticker: str
    shares: float
    entry_price: float
    entry_date: datetime
    initial_stop: float
    target: float

    model_config = {"from_attributes": True}


class MonitorResponse(BaseModel):
    positions: list[MonitorPosition]
