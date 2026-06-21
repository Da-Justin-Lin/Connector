from pydantic import BaseModel


class Candle(BaseModel):
    t: int  # unix epoch seconds
    o: float
    h: float
    l: float
    c: float
    v: float


class CandlesResponse(BaseModel):
    symbol: str
    range: str
    candles: list[Candle]
    available: bool
    message: str | None = None


class Snapshot(BaseModel):
    symbol: str
    candles: list[Candle]
    last_price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None


class SnapshotsResponse(BaseModel):
    snapshots: list[Snapshot]
    available: bool
    message: str | None = None


class FearGreedResponse(BaseModel):
    score: float | None = None
    rating: str | None = None
    updated_at: str | None = None
    prev_close: float | None = None
    prev_week: float | None = None
    prev_month: float | None = None
    prev_year: float | None = None
    available: bool = True
    message: str | None = None


class EarningsEvent(BaseModel):
    symbol: str
    date: str  # YYYY-MM-DD


class EarningsResponse(BaseModel):
    events: list[EarningsEvent]
    available: bool = True
    message: str | None = None


class SectorsResponse(BaseModel):
    # Map of ticker -> sector label (null when yfinance has no classification)
    sectors: dict[str, str | None]
