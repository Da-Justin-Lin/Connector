import logging

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.market_data import Candle, CandlesResponse
from app.services.market_data_service import (
    CandleRange,
    fetch_candles,
    is_configured,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_RANGES: tuple[CandleRange, ...] = ("1D", "1W", "1M", "3M", "1Y")


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
