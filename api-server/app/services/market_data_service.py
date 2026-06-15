import asyncio
import logging
from functools import partial
from typing import Literal

import yfinance as yf

logger = logging.getLogger(__name__)

CandleRange = Literal["1D", "1W", "1M", "3M", "1Y"]

# (yfinance period, yfinance interval)
_RANGE_CONFIG: dict[CandleRange, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "30m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "1Y": ("1y", "1d"),
}


def is_configured() -> bool:
    return True  # yfinance needs no API key


def _fetch_sync(symbol: str, period: str, interval: str) -> dict:
    ticker = yf.Ticker(symbol.upper())
    hist = ticker.history(period=period, interval=interval)

    if hist.empty:
        return {"candles": []}

    candles = []
    for idx, row in hist.iterrows():
        try:
            candles.append(
                {
                    "t": int(idx.timestamp()),
                    "o": float(row["Open"]),
                    "h": float(row["High"]),
                    "l": float(row["Low"]),
                    "c": float(row["Close"]),
                    "v": float(row["Volume"]),
                }
            )
        except (TypeError, ValueError, KeyError):
            continue

    return {"candles": candles}


async def fetch_candles(symbol: str, range_key: CandleRange) -> dict:
    period, interval = _RANGE_CONFIG[range_key]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_fetch_sync, symbol, period, interval))
