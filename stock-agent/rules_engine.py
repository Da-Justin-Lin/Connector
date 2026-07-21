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
    RSI_OVERBOUGHT,
    MIN_VOLUME_RATIO,
    MIN_ADX_TRENDING,
    MIN_SIGNAL_SCORE,
)

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


def evaluate(snapshot: dict) -> RuleSignal:
    daily = snapshot["daily"]
    hourly = snapshot["hourly"]
    intraday = snapshot["intraday"]

    price = float(snapshot["price"])
    atr_val = float(daily.get("atr_14") or 0)

    bb = daily.get("bollinger", {})
    bb_upper = float(bb.get("upper") or 0)
    bb_lower = float(bb.get("lower") or 0)

    buy_score = 0
    sell_score = 0
    reasons: list[str] = []

    # ----- LONG-side scoring -----
    if _has_uptrend(daily):
        buy_score += 2
        reasons.append("[+2 long] daily uptrend: price > EMA20 > EMA50")

    d_rsi = daily.get("rsi_14") or 50
    if d_rsi < RSI_OVERSOLD + 10:  # RSI < 40 on daily = pullback in trend
        buy_score += 2
        reasons.append(f"[+2 long] daily RSI={d_rsi} (pullback zone)")

    h_macd = hourly.get("macd", {})
    if h_macd.get("fresh_bull_cross"):
        buy_score += 3
        reasons.append("[+3 long] hourly MACD fresh bullish cross")
    elif h_macd.get("histogram", 0) > 0:
        buy_score += 1
        reasons.append("[+1 long] hourly MACD histogram positive")

    i_macd = intraday.get("macd", {})
    if i_macd.get("fresh_bull_cross"):
        buy_score += 2
        reasons.append("[+2 long] 15m MACD fresh bullish cross (entry trigger)")

    i_rsi = intraday.get("rsi_14") or 50
    if i_rsi < RSI_OVERSOLD:
        buy_score += 1
        reasons.append(f"[+1 long] 15m RSI oversold ({i_rsi})")

    vol_ratio = intraday.get("volume_ratio") or 1.0
    if vol_ratio >= MIN_VOLUME_RATIO:
        buy_score += 2
        reasons.append(f"[+2 both] 15m volume {vol_ratio}x avg (confirmation)")
        sell_score += 2  # volume confirms in either direction

    d_adx = daily.get("adx_14") or 0
    if d_adx >= MIN_ADX_TRENDING:
        buy_score += 1
        sell_score += 1
        reasons.append(f"[+1 both] daily ADX={d_adx} (trending market)")

    # ----- SHORT-side scoring -----
    if _has_downtrend(daily):
        sell_score += 2
        reasons.append("[+2 short] daily downtrend: price < EMA20 < EMA50")

    if d_rsi > RSI_OVERBOUGHT - 10:  # RSI > 60 on daily = overextended
        sell_score += 2
        reasons.append(f"[+2 short] daily RSI={d_rsi} (overbought zone)")

    if h_macd.get("fresh_bear_cross"):
        sell_score += 3
        reasons.append("[+3 short] hourly MACD fresh bearish cross")

    if i_macd.get("fresh_bear_cross"):
        sell_score += 2
        reasons.append("[+2 short] 15m MACD fresh bearish cross")

    if i_rsi > RSI_OVERBOUGHT:
        sell_score += 1
        reasons.append(f"[+1 short] 15m RSI overbought ({i_rsi})")

    # ----- Verdict -----
    max_score = 13
    if buy_score >= MIN_SIGNAL_SCORE and buy_score > sell_score:
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
    if sell_score >= MIN_SIGNAL_SCORE and sell_score > buy_score:
        return RuleSignal(
            signal="SELL",
            score=sell_score,
            max_score=max_score,
            reasons=reasons,
            entry_price=price,
            atr=atr_val,
            daily_bb_upper=bb_upper,
            daily_bb_lower=bb_lower,
        )
    return RuleSignal(
        signal="HOLD",
        score=max(buy_score, sell_score),
        max_score=max_score,
        reasons=reasons or ["No indicators aligned"],
        entry_price=price,
        atr=atr_val,
    )
