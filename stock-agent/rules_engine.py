"""
Rule-based signal generator — the deterministic layer.

Nothing goes to the LLM (or the broker) unless it clears this file first.
The rules are strict on purpose: we'd rather miss 10 trades than take 1 bad one.

Signal is a scored consensus across three timeframes (daily/hourly/15m).
A minimum score is required to even emit BUY/SELL — otherwise HOLD.
"""

from dataclasses import dataclass, field
from typing import Literal

from config import (
    RSI_OVERSOLD,
    MIN_VOLUME_RATIO,
    MIN_ADX_TRENDING,
    MIN_SIGNAL_SCORE,
    BLOCK_DOWNTREND_ENTRY,
    REQUIRE_RELATIVE_STRENGTH,
)

# HOLD/BUY only — the agent is long-only (see evaluate). SELL remains in the
# type for exit-side code (selling to close a long) but is never emitted here.
Signal = Literal["BUY", "SELL", "HOLD"]


@dataclass
class RuleSignal:
    signal: Signal
    score: int
    max_score: int
    reasons: list[str] = field(default_factory=list)
    entry_price: float = 0.0
    atr: float = 0.0
    # Reference bands for target/stop hints (final values computed by risk_manager)
    daily_bb_upper: float = 0.0
    daily_bb_lower: float = 0.0


def _has_uptrend(daily: dict) -> bool:
    """
    Long only when the stock itself is in a daily uptrend.

    Uses fast EMA20/50 rather than SMA50/200: in fast-rotating markets the
    200-day backbone confirms weeks after the move has already run. Backtested
    2018-2025, EMA20/50 catches the rotation ~3.7 days in and lifts the
    out-of-sample Sharpe from 1.73 to 2.11 (see backtest_fastdaily.py).
    """
    ema_20 = daily.get("ema_20") or 0
    ema_50 = daily.get("ema_50") or 0
    price = daily.get("price") or 0
    return ema_50 > 0 and price > ema_20 > ema_50


def _has_downtrend(daily: dict) -> bool:
    ema_20 = daily.get("ema_20") or 0
    ema_50 = daily.get("ema_50") or 0
    price = daily.get("price") or 0
    return ema_50 > 0 and price < ema_20 < ema_50


def evaluate(snapshot: dict, spy_return: float | None = None) -> RuleSignal:
    """
    Score the LONG setup and emit BUY or HOLD.

    Long-only by design — this mirrors the validated backtest, which has no
    short side. A prior short-scoring path only ever *suppressed* longs (via a
    buy>sell tie-break) and, in a BULL/NEUTRAL regime where shorts are blocked
    anyway, its main effect was to penalise the RSI>60 momentum leaders that the
    relative-strength gate is meant to buy. Position management (positions.py)
    is also long-only, so a short could never be tracked or exited safely.

    `spy_return` is SPY's trailing return over the same window as the stock's
    `daily["rs_return"]` (see market_regime / config.RS_LOOKBACK_DAYS). When
    provided and REQUIRE_RELATIVE_STRENGTH is on, a BUY is gated on the stock
    beating SPY. Callers without a benchmark (e.g. the position thesis re-check)
    pass None to skip the RS gate.
    """
    daily = snapshot["daily"]
    hourly = snapshot["hourly"]
    intraday = snapshot["intraday"]

    price = float(snapshot["price"])
    atr_val = float(daily.get("atr_14") or 0)

    bb = daily.get("bollinger", {})
    bb_upper = float(bb.get("upper") or 0)
    bb_lower = float(bb.get("lower") or 0)

    buy_score = 0
    reasons: list[str] = []

    # None-aware defaults: a valid extreme (RSI 0, no volume) must not be
    # clobbered to neutral the way `x or default` would.
    d_rsi = daily.get("rsi_14")
    d_rsi = 50.0 if d_rsi is None else d_rsi
    i_rsi = intraday.get("rsi_14")
    i_rsi = 50.0 if i_rsi is None else i_rsi
    vol_ratio = intraday.get("volume_ratio")
    vol_ratio = 1.0 if vol_ratio is None else vol_ratio

    if _has_uptrend(daily):
        buy_score += 2
        reasons.append("[+2] daily uptrend: price > EMA20 > EMA50")

    if d_rsi < RSI_OVERSOLD + 10:  # RSI < 40 on daily = pullback in trend
        buy_score += 2
        reasons.append(f"[+2] daily RSI={round(d_rsi, 1)} (pullback zone)")

    h_macd = hourly.get("macd", {})
    if h_macd.get("fresh_bull_cross"):
        buy_score += 3
        reasons.append("[+3] hourly MACD fresh bullish cross")
    elif h_macd.get("histogram", 0) > 0:
        buy_score += 1
        reasons.append("[+1] hourly MACD histogram positive")

    i_macd = intraday.get("macd", {})
    if i_macd.get("fresh_bull_cross"):
        buy_score += 2
        reasons.append("[+2] 15m MACD fresh bullish cross (entry trigger)")

    if i_rsi < RSI_OVERSOLD:
        buy_score += 1
        reasons.append(f"[+1] 15m RSI oversold ({round(i_rsi, 1)})")

    if vol_ratio >= MIN_VOLUME_RATIO:
        buy_score += 2
        reasons.append(f"[+2] 15m volume {vol_ratio}x avg (confirmation)")

    d_adx = daily.get("adx_14") or 0
    if d_adx >= MIN_ADX_TRENDING:
        buy_score += 1
        reasons.append(f"[+1] daily ADX={d_adx} (trending market)")

    # ----- Verdict (long-only; matches the validated backtest) -----
    max_score = 13
    buy_ok = buy_score >= MIN_SIGNAL_SCORE

    # BUY admission gates the score alone can't express (see config for the
    # backtest that motivated these).
    if buy_ok and BLOCK_DOWNTREND_ENTRY and _has_downtrend(daily):
        buy_ok = False
        reasons.append(
            "[gate] BUY blocked: stock in confirmed daily downtrend (price < EMA20 < EMA50)"
        )
    if buy_ok and REQUIRE_RELATIVE_STRENGTH and spy_return is not None:
        stock_return = daily.get("rs_return")
        # Unknown RS (too little history) is treated as a fail — conservative,
        # and matches the backtest (NaN return → no entry).
        if stock_return is None or stock_return <= spy_return:
            buy_ok = False
            reasons.append(
                f"[gate] BUY blocked: relative weakness "
                f"(stock {stock_return} ≤ SPY {round(spy_return, 4)})"
            )

    if buy_ok:
        return RuleSignal(
            signal="BUY",
            score=buy_score,
            max_score=max_score,
            reasons=reasons,
            entry_price=price,
            atr=atr_val,
            daily_bb_upper=bb_upper,
            daily_bb_lower=bb_lower,
        )
    return RuleSignal(
        signal="HOLD",
        score=buy_score,
        max_score=max_score,
        reasons=reasons or ["No indicators aligned"],
        entry_price=price,
        atr=atr_val,
    )
