import logging

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.market_data import (
    Candle,
    CandlesResponse,
    EarningsEvent,
    EarningsResponse,
    FearGreedResponse,
    SectorsResponse,
    Snapshot,
    SnapshotsResponse,
)
from app.services.market_data_service import (
    CandleRange,
    fetch_candles,
    fetch_earnings,
    fetch_fear_greed,
    fetch_sectors,
    fetch_snapshots,
    is_configured,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_RANGES: tuple[CandleRange, ...] = ("1D", "1W", "1M", "3M", "1Y")

# Symbols offered on the macro tab; capped to keep upstream fan-out small.
_MACRO_SYMBOLS = ("SPY", "QQQ", "DIA", "IWM", "BTC-USD", "ETH-USD", "GLD", "^VIX")


@router.get("/candles", response_model=CandlesResponse)
async def get_candles(
    symbol: str = Query(..., min_length=1, max_length=12),
    range: str = "1M",
    _: User = Depends(get_current_user),
):
    range_key = range.upper()
    if range_key not in _ALLOWED_RANGES:
        range_key = "1M"

    if not is_configured():
        return CandlesResponse(
            symbol=symbol.upper(),
            range=range_key,
            candles=[],
            available=False,
            message="Market data is not available.",
        )

    try:
        payload = await fetch_candles(symbol, range_key)  # type: ignore[arg-type]
    except Exception as exc:
        logger.warning("Candle fetch failed for %s/%s: %s", symbol, range_key, exc)
        return CandlesResponse(
            symbol=symbol.upper(),
            range=range_key,
            candles=[],
            available=False,
            message="Failed to fetch market data right now. Try again in a minute.",
        )

    candles = [Candle(**c) for c in payload.get("candles", [])]
    if not candles:
        return CandlesResponse(
            symbol=symbol.upper(),
            range=range_key,
            candles=[],
            available=True,
            message="No candles available for this symbol in the selected range.",
        )

    return CandlesResponse(
        symbol=symbol.upper(),
        range=range_key,
        candles=candles,
        available=True,
        message=None,
    )


@router.get("/snapshots", response_model=SnapshotsResponse)
async def get_snapshots(
    symbols: str = Query("SPY,QQQ,BTC-USD", max_length=120),
    _: User = Depends(get_current_user),
):
    """Intraday day chart + last price / day change for a set of symbols."""
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    # Only serve from the curated allow-list, preserving the caller's order.
    wanted = [s for s in requested if s in _MACRO_SYMBOLS] or list(("SPY", "QQQ", "BTC-USD"))

    try:
        raw = await fetch_snapshots(wanted)
    except Exception as exc:
        logger.warning("Snapshot fetch failed: %s", exc)
        return SnapshotsResponse(
            snapshots=[],
            available=False,
            message="Failed to fetch market data right now. Try again in a minute.",
        )

    snapshots = [
        Snapshot(
            symbol=s["symbol"],
            candles=[Candle(**c) for c in s["candles"]],
            last_price=s["last_price"],
            previous_close=s["previous_close"],
            change=s["change"],
            change_pct=s["change_pct"],
        )
        for s in raw
    ]
    return SnapshotsResponse(snapshots=snapshots, available=True, message=None)


@router.get("/fear-greed", response_model=FearGreedResponse)
async def get_fear_greed(_: User = Depends(get_current_user)):
    data = await fetch_fear_greed()
    if not data:
        return FearGreedResponse(
            available=False, message="Fear & Greed index is unavailable right now."
        )
    return FearGreedResponse(
        score=data.get("score"),
        rating=data.get("rating"),
        updated_at=data.get("updated_at"),
        prev_close=data.get("prev_close"),
        prev_week=data.get("prev_week"),
        prev_month=data.get("prev_month"),
        prev_year=data.get("prev_year"),
        available=True,
    )


@router.get("/sectors", response_model=SectorsResponse)
async def get_sectors(
    symbols: str = Query(..., max_length=600),
    _: User = Depends(get_current_user),
):
    """Sector classification per ticker, for the allocation breakdown."""
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    # De-dupe while preserving order; cap fan-out to keep upstream calls bounded.
    seen: set[str] = set()
    wanted: list[str] = []
    for s in requested:
        if s not in seen:
            seen.add(s)
            wanted.append(s)
        if len(wanted) >= 60:
            break

    if not wanted:
        return SectorsResponse(sectors={})

    try:
        sectors = await fetch_sectors(wanted)
    except Exception as exc:
        logger.warning("Sector fetch failed: %s", exc)
        return SectorsResponse(sectors={})
    return SectorsResponse(sectors=sectors)


@router.get("/earnings", response_model=EarningsResponse)
async def get_earnings(
    days: int = Query(14, ge=1, le=60),
    _: User = Depends(get_current_user),
):
    try:
        events = await fetch_earnings(days=days)
    except Exception as exc:
        logger.warning("Earnings fetch failed: %s", exc)
        return EarningsResponse(
            events=[], available=False, message="Earnings calendar is unavailable right now."
        )
    return EarningsResponse(
        events=[EarningsEvent(**e) for e in events], available=True
    )
