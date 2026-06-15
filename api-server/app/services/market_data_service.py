import logging
import time
from typing import Literal

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_FINNHUB_BASE = "https://finnhub.io/api/v1"

CandleRange = Literal["1D", "1W", "1M", "3M", "1Y"]


# Each range maps to (Finnhub resolution code, lookback seconds).
# Resolutions Finnhub supports: 1, 5, 15, 30, 60 (minutes), D, W, M.
_RANGE_CONFIG: dict[CandleRange, tuple[str, int]] = {
    "1D": ("5", 60 * 60 * 24),          # 5-min candles over 1 day
    "1W": ("30", 60 * 60 * 24 * 7),     # 30-min candles over 1 week
    "1M": ("D", 60 * 60 * 24 * 31),     # daily candles over 1 month
    "3M": ("D", 60 * 60 * 24 * 93),
    "1Y": ("D", 60 * 60 * 24 * 366),
}


def is_configured() -> bool:
    return bool(settings.finnhub_api_key)


async def fetch_candles(symbol: str, range_key: CandleRange) -> dict:
    """Fetch OHLC candles from Finnhub for the given symbol and range.

    Returns a dict with normalized keys: candles=[{t, o, h, l, c, v}], source="finnhub".
    Raises if the API key is missing or the upstream call fails — let the caller
    convert that into a graceful HTTP response.
    """
    if not is_configured():
        raise RuntimeError("FINNHUB_API_KEY not configured")

    resolution, lookback = _RANGE_CONFIG[range_key]
    now = int(time.time())
    params = {
        "symbol": symbol.upper(),
        "resolution": resolution,
        "from": now - lookback,
        "to": now,
        "token": settings.finnhub_api_key,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{_FINNHUB_BASE}/stock/candle", params=params)
        response.raise_for_status()
        payload = response.json()

    if payload.get("s") != "ok":
        # Finnhub returns s="no_data" for symbols / ranges with nothing in window
        return {"candles": [], "source": "finnhub", "status": payload.get("s")}

    closes = payload.get("c") or []
    highs = payload.get("h") or []
    lows = payload.get("l") or []
    opens = payload.get("o") or []
    times = payload.get("t") or []
    volumes = payload.get("v") or []

    candles = []
    for i, ts in enumerate(times):
        try:
            candles.append(
                {
                    "t": int(ts),
                    "o": float(opens[i]),
                    "h": float(highs[i]),
                    "l": float(lows[i]),
                    "c": float(closes[i]),
                    "v": float(volumes[i]) if i < len(volumes) else 0.0,
                }
            )
        except (TypeError, ValueError, IndexError):
            continue

    return {"candles": candles, "source": "finnhub", "status": "ok"}
