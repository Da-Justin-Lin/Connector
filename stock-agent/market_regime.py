"""
Market regime filter — the "master switch" for the strategy.

Regime is determined from broad-market context (SPY trend + VIX level).
No matter how good a stock-level signal looks, if the regime is hostile,
we don't take longs. This is the single biggest driver of drawdown avoidance
in retail algo systems.

Regime is cached for CACHE_MINUTES because SPY/VIX don't change that fast
and this saves yfinance API calls when scanning many tickers per cycle.
"""

import time
from dataclasses import dataclass
from typing import Literal

import yfinance as yf

Regime = Literal["BULL", "NEUTRAL", "BEAR", "PANIC"]

_CACHE: dict = {"regime": None, "ts": 0, "detail": None}
_CACHE_MINUTES = 15


@dataclass
class RegimeInfo:
    regime: Regime
    spy_price: float
    spy_ma50: float
    spy_ma200: float
    vix: float
    reason: str

    def allows_long(self) -> bool:
        return self.regime in ("BULL", "NEUTRAL")

    def allows_short(self) -> bool:
        return self.regime in ("BEAR", "PANIC")

    def position_size_multiplier(self) -> float:
        """
        Scale position size by regime confidence.
        BULL: full size. NEUTRAL: half. BEAR/PANIC: no long positions.
        """
        return {"BULL": 1.0, "NEUTRAL": 0.5, "BEAR": 0.0, "PANIC": 0.0}[self.regime]


def _fetch_regime() -> RegimeInfo:
    spy = yf.Ticker("SPY").history(period="1y", interval="1d")
    vix_hist = yf.Ticker("^VIX").history(period="1mo", interval="1d")

    if spy.empty or vix_hist.empty:
        # Fail safe: if we can't determine regime, don't take new trades
        return RegimeInfo(
            regime="PANIC",
            spy_price=0,
            spy_ma50=0,
            spy_ma200=0,
            vix=0,
            reason="Failed to fetch SPY/VIX — defensive default",
        )

    spy_price = float(spy["Close"].iloc[-1])
    spy_ma50 = float(spy["Close"].rolling(50).mean().iloc[-1])
    spy_ma200 = float(spy["Close"].rolling(200).mean().iloc[-1])
    vix = float(vix_hist["Close"].iloc[-1])

    if vix > 30:
        regime: Regime = "PANIC"
        reason = f"VIX={vix:.1f} > 30 (fear regime)"
    elif spy_price < spy_ma200:
        regime = "BEAR"
        reason = f"SPY ${spy_price:.2f} below 200MA ${spy_ma200:.2f}"
    elif spy_price > spy_ma50 > spy_ma200 and vix < 20:
        regime = "BULL"
        reason = f"SPY above 50MA above 200MA, VIX={vix:.1f} < 20"
    else:
        regime = "NEUTRAL"
        reason = f"Mixed: SPY=${spy_price:.2f}, 50MA=${spy_ma50:.2f}, VIX={vix:.1f}"

    return RegimeInfo(
        regime=regime,
        spy_price=round(spy_price, 2),
        spy_ma50=round(spy_ma50, 2),
        spy_ma200=round(spy_ma200, 2),
        vix=round(vix, 2),
        reason=reason,
    )


def get_regime() -> RegimeInfo:
    """Cached wrapper — SPY/VIX barely move in 15 minutes."""
    now = time.time()
    if _CACHE["regime"] and (now - _CACHE["ts"]) < _CACHE_MINUTES * 60:
        return _CACHE["detail"]

    info = _fetch_regime()
    _CACHE["regime"] = info.regime
    _CACHE["ts"] = now
    _CACHE["detail"] = info
    return info
