#!/usr/bin/env python3
"""
Intraday (hourly) backtest — the "smaller timeframe" variant.

The original backtest.py anchors the whole strategy on the DAILY 50/200 SMA
trend. In fast-rotating markets that backbone is too slow: by the time
price > SMA50 > SMA200 confirms on the daily, the rotation is often over.

This harness moves the trend backbone and every trigger down to the 60-minute
bar. yfinance gives ~2 years of free 60m history (vs. 60 days for 15m), which
is enough for a train/test split. Everything else — ATR stops, R-multiple
trailing, regime gate — mirrors backtest.py so the two are directly comparable.

Usage:
    python backtest_intraday.py \
        --train 2023-09-01:2025-03-31 --test 2025-04-01:2026-07-31

Reject the strategy if TEST-set Sharpe < 1.0, max drawdown > 20%,
or profit factor < 1.3 (same bar as the daily backtest).
"""

import argparse
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    WATCHLIST,
    MAX_RISK_PER_TRADE_PCT,
    MAX_POSITION_PCT,
    MAX_TARGET_R_MULTIPLE,
    CHANDELIER_ATR_MULT,
)

warnings.filterwarnings("ignore")

# ---------- Hourly-specific knobs ----------
# Trend backbone: fast EMAs on 60m instead of daily SMA50/200.
# EMA20 on 60m ≈ ~3 trading days of trend; EMA50 ≈ ~1.5 weeks.
EMA_FAST = 20
EMA_SLOW = 50
# ATR stop multiplier — tighter than the daily 2.0 because hourly ATR is smaller
# and we want snappy trades that match the fast-rotation thesis.
ATR_STOP_MULT = 1.5
# Time stop in *bars* (60m). US session ≈ 6.5 bars/day → 21 bars ≈ 3 trading days.
TIME_STOP_BARS = 21
# Volume/ADX/RSI gates for the hourly score.
VOL_RATIO_MIN = 1.5
ADX_MIN = 20
RSI_PULLBACK = 45


@dataclass
class Trade:
    ticker: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    exit_reason: str
    bars_held: int


def _download(ticker: str, period: str = "730d") -> pd.DataFrame | None:
    df = yf.download(
        ticker, period=period, interval="60m", progress=False, auto_adjust=True
    )
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _wilder_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev).abs(), (low - prev).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev).abs(), (low - prev).abs()], axis=1
    ).max(axis=1)
    atr_ = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr_)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr_)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period).mean()


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    df["ema_fast"] = close.ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=EMA_SLOW, adjust=False).mean()

    # RSI (Wilder-ish, matches indicators.py)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(com=13, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - 100 / (1 + rs)

    # MACD histogram + fresh bull cross
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    hist = macd_line - macd_line.ewm(span=9, adjust=False).mean()
    df["macd_hist"] = hist
    df["macd_bull_cross"] = (hist > 0) & (hist.shift(1) <= 0)

    df["atr"] = _wilder_atr(df)
    df["adx"] = _adx(df)
    df["vol_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    return df.dropna(subset=["ema_slow", "atr"])


def _score(row: pd.Series) -> int:
    """Hourly analogue of rules_engine.evaluate (long side)."""
    score = 0
    if row["Close"] > row["ema_fast"] > row["ema_slow"]:
        score += 2  # hourly uptrend
    if row["rsi"] < RSI_PULLBACK:
        score += 2  # pullback within trend
    if row["macd_bull_cross"]:
        score += 3  # fresh momentum trigger
    if row["vol_ratio"] >= VOL_RATIO_MIN:
        score += 2  # volume confirmation
    if row["adx"] >= ADX_MIN:
        score += 1  # trending, not chopping
    return score


def _spy_regime(start, end) -> pd.Series:
    """Risk-on when SPY (60m) is above its EMA50. Returned aligned to 60m bars."""
    spy = _download("SPY")
    if spy is None:
        return pd.Series(dtype=bool)
    spy["ema"] = spy["Close"].ewm(span=EMA_SLOW, adjust=False).mean()
    risk_on = (spy["Close"] > spy["ema"]).rename("risk_on")
    return risk_on


def simulate(tickers, start, end, capital=1000.0, min_score=5):
    prepared = {}
    for t in tickers:
        raw = _download(t)
        if raw is None:
            continue
        df = _prepare(raw)
        df = df[(df.index >= start) & (df.index <= end)]
        if len(df) > 50:
            prepared[t] = df
    if not prepared:
        return [], pd.Series(dtype=float)

    regime = _spy_regime(start, end)

    trades: list[Trade] = []
    cash = capital
    equity_curve = {}
    open_pos: dict[str, dict] = {}

    all_ts = sorted(set().union(*[df.index for df in prepared.values()]))

    for ts in all_ts:
        risk_on = True
        if not regime.empty:
            hit = regime.reindex([ts], method="ffill").iloc[0]
            risk_on = bool(hit) if pd.notna(hit) else True

        # ---- exits ----
        for t in list(open_pos.keys()):
            pos = open_pos[t]
            df = prepared[t]
            if ts not in df.index:
                continue
            bar = df.loc[ts]
            pos["highest"] = max(pos["highest"], float(bar["High"]))
            pos["bars"] += 1

            # Continuous Chandelier trailing stop: highest high since entry −
            # k×ATR, ratcheted up only (never loosens).
            atr_now = float(bar["atr"])
            if atr_now > 0:
                pos["stop"] = max(pos["stop"], round(pos["highest"] - CHANDELIER_ATR_MULT * atr_now, 2))

            reason = price = None
            if float(bar["Low"]) <= pos["stop"]:
                reason = "stop_loss" if pos["stop"] == pos["init_stop"] else "trail_stop"
                price = pos["stop"]
            elif float(bar["High"]) >= pos["target"]:
                reason = "target_hit"
                price = pos["target"]
            elif pos["bars"] >= TIME_STOP_BARS:
                reason = "time_stop"
                price = float(bar["Close"])

            if reason:
                pnl = (price - pos["entry"]) * pos["shares"]
                cash += price * pos["shares"]
                trades.append(Trade(t, pos["entry_ts"], ts, pos["entry"], price,
                                    pos["shares"], pnl, reason, pos["bars"]))
                del open_pos[t]

        # ---- entries ----
        if risk_on:
            for t, df in prepared.items():
                if t in open_pos or ts not in df.index:
                    continue
                row = df.loc[ts]
                if pd.isna(row["atr"]) or row["atr"] <= 0:
                    continue
                if _score(row) < min_score:
                    continue
                entry = float(row["Close"])
                stop = round(entry - ATR_STOP_MULT * float(row["atr"]), 2)
                risk_ps = entry - stop
                if risk_ps <= 0:
                    continue
                max_risk = cash * MAX_RISK_PER_TRADE_PCT
                shares = min(max_risk / risk_ps, cash * MAX_POSITION_PCT / entry)
                shares = round(shares, 4)
                if shares < 0.01:
                    continue
                cost = shares * entry
                if cost > cash * 0.95:
                    continue
                target = round(entry + MAX_TARGET_R_MULTIPLE * risk_ps, 2)
                cash -= cost
                open_pos[t] = {
                    "shares": shares, "entry": entry, "init_stop": stop,
                    "stop": stop, "target": target, "entry_ts": ts,
                    "highest": entry, "bars": 0,
                }

        open_val = sum(
            pos["shares"] * float(prepared[t].loc[ts, "Close"])
            for t, pos in open_pos.items() if ts in prepared[t].index
        )
        equity_curve[ts] = cash + open_val

    return trades, pd.Series(equity_curve).sort_index()


def _metrics(trades, equity, starting):
    if equity.empty:
        return {"error": "no equity"}
    total_return = (equity.iloc[-1] / starting - 1) * 100
    # Resample hourly equity to daily so Sharpe is comparable to the daily backtest.
    daily = equity.resample("1D").last().dropna()
    rets = daily.pct_change().dropna()
    sharpe = np.sqrt(252) * rets.mean() / rets.std() if rets.std() > 0 else 0
    dd = ((equity - equity.cummax()) / equity.cummax()).min() * 100

    if not trades:
        return {"trades": 0, "total_return_pct": round(total_return, 2),
                "sharpe": round(float(sharpe), 2), "max_drawdown_pct": round(dd, 2)}

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")
    return {
        "trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2),
        "avg_bars_held": round(np.mean([t.bars_held for t in trades]), 1),
        "avg_win": round(np.mean(wins), 2) if wins else 0,
        "avg_loss": round(np.mean(losses), 2) if losses else 0,
        "profit_factor": round(float(pf), 2),
        "total_return_pct": round(total_return, 2),
        "sharpe": round(float(sharpe), 2),
        "max_drawdown_pct": round(dd, 2),
        "final_equity": round(equity.iloc[-1], 2),
    }


def _run(name, tickers, start, end, capital, min_score):
    print(f"\n===== {name}: {start.date()} → {end.date()} =====")
    trades, equity = simulate(tickers, start, end, capital, min_score)
    m = _metrics(trades, equity, capital)
    for k, v in m.items():
        print(f"  {k:20} {v}")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2023-09-01:2025-03-31")
    ap.add_argument("--test", default="2025-04-01:2026-07-31")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--min-score", type=int, default=5)
    ap.add_argument("--tickers", default=",".join(WATCHLIST))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    ts, te = (pd.Timestamp(x, tz="America/New_York") for x in args.train.split(":"))
    vs, ve = (pd.Timestamp(x, tz="America/New_York") for x in args.test.split(":"))

    _run("TRAIN (in-sample)", tickers, ts, te, args.capital, args.min_score)
    test_m = _run("TEST (out-of-sample)", tickers, vs, ve, args.capital, args.min_score)

    print("\n===== VERDICT =====")
    ok = (test_m.get("sharpe", 0) >= 1.0
          and abs(test_m.get("max_drawdown_pct", -100)) <= 20
          and test_m.get("profit_factor", 0) >= 1.3)
    print("  ✅ Passes out-of-sample bar." if ok
          else "  ❌ Fails Sharpe≥1 / MaxDD≤20% / PF≥1.3 — tune or reject.")


if __name__ == "__main__":
    main()
