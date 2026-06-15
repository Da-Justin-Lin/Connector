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
