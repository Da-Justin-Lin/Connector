import uuid
from datetime import datetime

from pydantic import BaseModel


class TradingSignalCreate(BaseModel):
    ticker: str
    signal: str
    confidence: str = "MEDIUM"
    price: float
    entry_price: float | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    shares: float | None = None
    score: int | None = None
    max_score: int | None = None
    risk_reward_ratio: float | None = None
    regime: str | None = None
    order_status: str | None = None
    reasoning: str | None = None


class TradingSignalRead(BaseModel):
    id: uuid.UUID
    ticker: str
    signal: str
    confidence: str
    price: float
    entry_price: float | None
    target_price: float | None
    stop_loss: float | None
    shares: float | None
    score: int | None
    max_score: int | None
    risk_reward_ratio: float | None
    regime: str | None
    order_status: str | None
    reasoning: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TradingSignalsResponse(BaseModel):
    signals: list[TradingSignalRead]
