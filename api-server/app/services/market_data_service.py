import asyncio
import logging
import time
from datetime import datetime, timezone
from functools import partial
from typing import Literal

import httpx
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


# --------------------------------------------------------------------------- #
# Macro snapshot: intraday day chart + last price / day change per symbol
# --------------------------------------------------------------------------- #


def _snapshot_sync(symbol: str) -> dict:
    """Today's intraday candles plus last price and change vs. previous close."""
    ticker = yf.Ticker(symbol.upper())

    hist = ticker.history(period="1d", interval="5m")
    candles: list[dict] = []
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

    last_price: float | None = None
    previous_close: float | None = None
    try:
        fast = ticker.fast_info
        last_price = float(fast["last_price"]) if fast.get("last_price") else None
        previous_close = (
            float(fast["previous_close"]) if fast.get("previous_close") else None
        )
    except Exception:  # fast_info can raise on flaky upstream responses
        pass

    # Fall back to candle data when fast_info is unavailable.
    if last_price is None and candles:
        last_price = candles[-1]["c"]

    change = None
    change_pct = None
    if last_price is not None and previous_close:
        change = last_price - previous_close
        change_pct = change / previous_close

    return {
        "symbol": symbol.upper(),
        "candles": candles,
        "last_price": last_price,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
    }


async def fetch_snapshots(symbols: list[str]) -> list[dict]:
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, partial(_snapshot_sync, s)) for s in symbols
    ]
    results = []
    for sym, res in zip(symbols, await asyncio.gather(*tasks, return_exceptions=True)):
        if isinstance(res, Exception):
            logger.warning("Snapshot fetch failed for %s: %s", sym, res)
            results.append(
                {
                    "symbol": sym.upper(),
                    "candles": [],
                    "last_price": None,
                    "previous_close": None,
                    "change": None,
                    "change_pct": None,
                }
            )
        else:
            results.append(res)
    return results


# --------------------------------------------------------------------------- #
# Sector enrichment for the allocation breakdown
# --------------------------------------------------------------------------- #

# Per-symbol sector, cached for a day — sector classification rarely changes
# and yfinance's .info call is heavy/rate-limited.
_SECTOR_CACHE: dict[str, tuple[float, str | None]] = {}
_SECTOR_TTL = 86400  # seconds

# yfinance reports ETFs/crypto with a quoteType but no sector; map those to a
# readable bucket so they still show up in the breakdown.
_QUOTE_TYPE_LABELS = {
    "ETF": "ETF",
    "MUTUALFUND": "Fund",
    "CRYPTOCURRENCY": "Crypto",
    "CURRENCY": "Currency",
}


def _sector_sync(symbol: str) -> str | None:
    try:
        info = yf.Ticker(symbol).info
    except Exception:
        return None
    if not isinstance(info, dict):
        return None
    sector = info.get("sector")
    if sector:
        return str(sector)
    quote_type = str(info.get("quoteType") or "").upper()
    return _QUOTE_TYPE_LABELS.get(quote_type)


async def fetch_sectors(symbols: list[str]) -> dict[str, str | None]:
    now = time.time()
    out: dict[str, str | None] = {}
    to_fetch: list[str] = []
    for raw in symbols:
        sym = raw.upper()
        cached = _SECTOR_CACHE.get(sym)
        if cached and now - cached[0] < _SECTOR_TTL:
            out[sym] = cached[1]
        else:
            to_fetch.append(sym)

    if to_fetch:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, partial(_sector_sync, s)) for s in to_fetch]
        for sym, res in zip(to_fetch, await asyncio.gather(*tasks, return_exceptions=True)):
            sector = None if isinstance(res, Exception) else res
            _SECTOR_CACHE[sym] = (now, sector)
            out[sym] = sector

    return out


# --------------------------------------------------------------------------- #
# CNN Fear & Greed index (cached briefly to avoid hammering upstream)
# --------------------------------------------------------------------------- #

_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_FG_CACHE: dict[str, object] = {"data": None, "at": 0.0}
_FG_TTL = 300  # seconds


async def fetch_fear_greed() -> dict | None:
    now = time.time()
    cached = _FG_CACHE.get("data")
    if cached is not None and now - float(_FG_CACHE["at"]) < _FG_TTL:  # type: ignore[arg-type]
        return cached  # type: ignore[return-value]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_FEAR_GREED_URL, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning("Fear & Greed fetch failed: %s", exc)
        return cached  # type: ignore[return-value]

    fg = payload.get("fear_and_greed", {})

    def _val(node: object) -> float | None:
        if isinstance(node, dict) and node.get("score") is not None:
            try:
                return round(float(node["score"]), 1)
            except (TypeError, ValueError):
                return None
        return None

    data = {
        "score": _val(fg),
        "rating": fg.get("rating"),
        "updated_at": fg.get("timestamp"),
        "prev_close": fg.get("previous_close"),
        "prev_week": fg.get("previous_1_week"),
        "prev_month": fg.get("previous_1_month"),
        "prev_year": fg.get("previous_1_year"),
    }
    _FG_CACHE["data"] = data
    _FG_CACHE["at"] = now
    return data


# --------------------------------------------------------------------------- #
# Upcoming earnings for a curated mega-cap watchlist
# --------------------------------------------------------------------------- #

_EARNINGS_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "JPM", "V", "WMT", "NFLX", "AMD", "COST", "PEP", "DIS", "CRM", "ORCL",
]
_EARN_CACHE: dict[str, object] = {"data": None, "at": 0.0}
_EARN_TTL = 3600  # seconds


def _earnings_sync(symbol: str) -> dict | None:
    try:
        cal = yf.Ticker(symbol).calendar
    except Exception:
        return None
    if not cal:
        return None

    raw = cal.get("Earnings Date") if isinstance(cal, dict) else None
    if not raw:
        return None
    dates = raw if isinstance(raw, list) else [raw]
    parsed = []
    for d in dates:
        try:
            parsed.append(datetime(d.year, d.month, d.day, tzinfo=timezone.utc))
        except (AttributeError, TypeError, ValueError):
            continue
    if not parsed:
        return None
    return {"symbol": symbol, "date": min(parsed).strftime("%Y-%m-%d")}


async def fetch_earnings(days: int = 14) -> list[dict]:
    now = time.time()
    cached = _EARN_CACHE.get("data")
    if cached is not None and now - float(_EARN_CACHE["at"]) < _EARN_TTL:  # type: ignore[arg-type]
        upcoming = cached
    else:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, partial(_earnings_sync, s))
            for s in _EARNINGS_WATCHLIST
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        upcoming = [
            r for r in results if isinstance(r, dict) and r is not None
        ]
        _EARN_CACHE["data"] = upcoming
        _EARN_CACHE["at"] = now

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    horizon = datetime.now(timezone.utc).timestamp() + days * 86400
    out = []
    for r in upcoming:  # type: ignore[union-attr]
        d = r["date"]
        if d < today:
            continue
        ts = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        if ts <= horizon:
            out.append(r)
    out.sort(key=lambda r: r["date"])
    return out
