"""Pure pre-trade context math: trend/range stats and concentration.

Kept free of FastAPI/DB/network imports so it can be unit-tested in isolation
(see also `trade_parsing.py`). The position endpoint feeds it candles and a
holdings breakdown and serializes the result.
"""

from datetime import datetime, timezone


def compute_trend_stats(candles: list[dict], current_price: float | None) -> dict:
    """Derive 52-week range and moving-average trend from daily candles.

    `candles` are the 1Y daily OHLC dicts from `fetch_candles` (keys o/h/l/c).
    `current_price` is the live holdings price; falls back to the last close.
    Any field that can't be computed (too few candles, no price) comes back
    None so the UI can hide it rather than show a wrong number.
    """
    closes = [c["c"] for c in candles if isinstance(c.get("c"), (int, float))]
    highs = [c["h"] for c in candles if isinstance(c.get("h"), (int, float))]
    lows = [c["l"] for c in candles if isinstance(c.get("l"), (int, float))]

    price = current_price if current_price else (closes[-1] if closes else None)

    week52_high = max(highs) if highs else None
    week52_low = min(lows) if lows else None

    def _pct(frm: float | None) -> float | None:
        if price is None or not frm:
            return None
        return round((price - frm) / frm, 4)

    def _ma(n: int) -> float | None:
        if len(closes) < n:
            return None
        return round(sum(closes[-n:]) / n, 4)

    ma50 = _ma(50)
    ma200 = _ma(200)

    return {
        "week52_high": round(week52_high, 4) if week52_high is not None else None,
        "week52_low": round(week52_low, 4) if week52_low is not None else None,
        "pct_from_high": _pct(week52_high),
        "pct_from_low": _pct(week52_low),
        "ma50": ma50,
        "ma200": ma200,
        "above_ma50": (price > ma50) if (price is not None and ma50 is not None) else None,
        "above_ma200": (price > ma200) if (price is not None and ma200 is not None) else None,
    }


def compute_concentration(
    target_value: float,
    portfolio_value: float,
    sector: str | None,
    sector_value: float,
) -> dict:
    """Position weight and its sector's weight as fractions of the whole book.

    `portfolio_value` is total holdings + cash; `sector_value` is the summed
    market value of every holding sharing `sector`. Returns None weights when
    the denominator is zero.
    """
    weight = (
        round(target_value / portfolio_value, 4)
        if portfolio_value > 0 else None
    )
    sector_weight = (
        round(sector_value / portfolio_value, 4)
        if (sector and portfolio_value > 0) else None
    )
    return {
        "portfolio_value": round(portfolio_value, 2) if portfolio_value else None,
        "weight_pct": weight,
        "sector": sector,
        "sector_weight_pct": sector_weight,
    }


def days_until(date_str: str, today: datetime | None = None) -> int | None:
    """Whole days from today (UTC) to a YYYY-MM-DD date; None if unparseable."""
    try:
        target = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    now = today or datetime.now(timezone.utc)
    return (target.date() - now.date()).days
