#!/usr/bin/env python3
"""
"Faster daily" backtest — react to rotation quicker WITHOUT dropping to the
hourly noise floor.

Findings so far:
  - The stock daily backbone (SMA50>SMA200) backtests well (Sharpe ~1.7 OOS)
    but is *slow* to flip when leadership rotates.
  - A naive move to 60m makes everything worse (Sharpe ~0.4, PF ~1.0): too many
    low-quality signals.

This variant keeps the *daily* timeframe (low noise) but swaps the trend
backbone to fast EMAs and shortens the time stop, so it catches a rotation in
days instead of weeks. Trend spans and time stop are CLI-tunable so we can
sweep them.

Entry-quality filters (config.BLOCK_DOWNTREND_ENTRY / REQUIRE_RELATIVE_STRENGTH,
default on): never open a long in a confirmed daily downtrend, and require the
stock to out-return SPY over RS_LOOKBACK_DAYS. Over 2018-2025 these cut OOS max
drawdown -16.1%→-12.0% and lifted profit factor 1.48→1.59 at ~flat return, and
roughly halved the train/test Sharpe gap (0.78→2.01 without vs 1.25→1.96 with).
Set both env flags to false to reproduce the earlier score-only baseline.

Usage:
    python backtest_fastdaily.py --ema-fast 20 --ema-slow 50 --time-stop 4
    BLOCK_DOWNTREND_ENTRY=false REQUIRE_RELATIVE_STRENGTH=false python backtest_fastdaily.py
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
    ATR_STOP_MULTIPLIER,
    MIN_ADX_TRENDING,
    MAX_TARGET_R_MULTIPLE,
    CHANDELIER_ATR_MULT,
    BLOCK_DOWNTREND_ENTRY,
    REQUIRE_RELATIVE_STRENGTH,
    RS_LOOKBACK_DAYS,
)

warnings.filterwarnings("ignore")


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    exit_reason: str
    days_held: int


def _download(ticker, start, end):
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _wilder(series_high, series_low, close, period=14):
    prev = close.shift(1)
    tr = pd.concat(
        [(series_high - series_low), (series_high - prev).abs(), (series_low - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def _regime(start, end):
    spy = _download("SPY", start, end)
    vix = _download("^VIX", start, end)
    if spy is None:
        return pd.DataFrame()
    spy["ma50"] = spy["Close"].rolling(50).mean()
    spy["ma200"] = spy["Close"].rolling(200).mean()
    spy["vix"] = vix["Close"].reindex(spy.index).ffill() if vix is not None else 15

    def classify(r):
        if pd.isna(r["ma200"]):
            return "NEUTRAL"
        if r["vix"] > 30:
            return "PANIC"
        if r["Close"] < r["ma200"]:
            return "BEAR"
        if r["Close"] > r["ma50"] > r["ma200"] and r["vix"] < 20:
            return "BULL"
        return "NEUTRAL"

    spy["regime"] = spy.apply(classify, axis=1)
    return spy[["regime"]]


def _prepare(ticker, start, end, ema_fast, ema_slow):
    df = _download(ticker, start, end)
    if df is None:
        return None
    close = df["Close"]

    # FAST trend backbone: EMA fast/slow instead of SMA50/200.
    df["ema_fast"] = close.ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=ema_slow, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(com=13, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - 100 / (1 + rs)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    hist = macd_line - macd_line.ewm(span=9, adjust=False).mean()
    df["macd_hist"] = hist
    df["macd_bull_cross"] = (hist > 0) & (hist.shift(1) <= 0)

    tr = _wilder(df["High"], df["Low"], close)
    df["atr"] = tr.rolling(14).mean()

    up = df["High"].diff()
    down = -df["Low"].diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    atr_ = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.rolling(14).mean()

    df["vol_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    return df.dropna(subset=["ema_slow", "atr"])


def _score(row):
    score = 0
    if row["Close"] > row["ema_fast"] > row["ema_slow"]:
        score += 2
    if row["rsi"] < 45:
        score += 2
    if row["macd_bull_cross"]:
        score += 3
    if row["vol_ratio"] >= 1.5:
        score += 2
    if row["adx"] >= MIN_ADX_TRENDING:
        score += 1
    return score


def simulate(tickers, start, end, capital, min_score, ema_fast, ema_slow, time_stop):
    regime = _regime(start, end)
    prepared = {t: _prepare(t, start, end, ema_fast, ema_slow) for t in tickers}
    prepared = {t: d for t, d in prepared.items() if d is not None}

    # Relative-strength benchmark: SPY's own RS_LOOKBACK-day return, and each
    # stock's. Mirrors the live gate in rules_engine (config knobs shared).
    spy = _download("SPY", start, end) if REQUIRE_RELATIVE_STRENGTH else None
    spy_ret = spy["Close"].pct_change(RS_LOOKBACK_DAYS) if spy is not None else None
    stock_ret = {t: d["Close"].pct_change(RS_LOOKBACK_DAYS) for t, d in prepared.items()}

    trades, cash = [], capital
    equity, open_pos = {}, {}
    all_dates = sorted(
        set().union(*[d.index for d in prepared.values()]).intersection(regime.index)
    )

    for date in all_dates:
        reg = regime.loc[date, "regime"] if date in regime.index else "NEUTRAL"
        allows_long = reg in ("BULL", "NEUTRAL")

        for t in list(open_pos.keys()):
            pos = open_pos[t]
            if date not in prepared[t].index:
                continue
            bar = prepared[t].loc[date]
            pos["highest"] = max(pos["highest"], float(bar["High"]))
            pos["days"] += 1
            # Continuous Chandelier trailing stop: highest high since entry −
            # k×ATR, ratcheted up only (never loosens).
            atr_now = float(bar["atr"])
            if atr_now > 0:
                pos["stop"] = max(pos["stop"], round(pos["highest"] - CHANDELIER_ATR_MULT * atr_now, 2))
            reason = price = None
            if float(bar["Low"]) <= pos["stop"]:
                reason = "stop" if pos["stop"] == pos["init_stop"] else "trail"
                price = pos["stop"]
            elif float(bar["High"]) >= pos["target"]:
                reason, price = "target", pos["target"]
            elif pos["days"] >= time_stop:
                reason, price = "time", float(bar["Close"])
            if reason:
                pnl = (price - pos["entry"]) * pos["shares"]
                cash += price * pos["shares"]
                trades.append(Trade(t, pos["entry_date"], date, pos["entry"], price,
                                    pos["shares"], pnl, reason, pos["days"]))
                del open_pos[t]

        if allows_long:
            for t, df in prepared.items():
                if t in open_pos or date not in df.index:
                    continue
                row = df.loc[date]
                if pd.isna(row["atr"]) or row["atr"] <= 0 or _score(row) < min_score:
                    continue
                # Entry-quality gates (shared with live rules_engine):
                if BLOCK_DOWNTREND_ENTRY and (
                    row["Close"] < row["ema_fast"] < row["ema_slow"]
                ):
                    continue
                if REQUIRE_RELATIVE_STRENGTH and spy_ret is not None:
                    sr = spy_ret.get(date, np.nan)
                    tr = stock_ret[t].get(date, np.nan)
                    if pd.isna(sr) or pd.isna(tr) or tr <= sr:
                        continue
                entry = float(row["Close"])
                stop = round(entry - ATR_STOP_MULTIPLIER * float(row["atr"]), 2)
                risk = entry - stop
                if risk <= 0:
                    continue
                mult = 1.0 if reg == "BULL" else 0.5
                shares = min(cash * MAX_RISK_PER_TRADE_PCT * mult / risk,
                             cash * MAX_POSITION_PCT / entry)
                shares = round(shares, 4)
                if shares < 0.01:
                    continue
                cost = shares * entry
                if cost > cash * 0.95:
                    continue
                cash -= cost
                open_pos[t] = {"shares": shares, "entry": entry, "init_stop": stop,
                               "stop": stop, "target": round(entry + MAX_TARGET_R_MULTIPLE * risk, 2),
                               "entry_date": date, "highest": entry, "days": 0}

        open_val = sum(pos["shares"] * float(prepared[t].loc[date, "Close"])
                       for t, pos in open_pos.items() if date in prepared[t].index)
        equity[date] = cash + open_val

    return trades, pd.Series(equity).sort_index()


def _metrics(trades, equity, starting):
    if equity.empty:
        return {"error": "no equity"}
    total = (equity.iloc[-1] / starting - 1) * 100
    rets = equity.pct_change().dropna()
    sharpe = np.sqrt(252) * rets.mean() / rets.std() if rets.std() > 0 else 0
    dd = ((equity - equity.cummax()) / equity.cummax()).min() * 100
    if not trades:
        return {"trades": 0, "total_return_pct": round(total, 2),
                "sharpe": round(float(sharpe), 2), "max_drawdown_pct": round(dd, 2)}
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else float("inf")
    return {"trades": len(trades), "win_rate_pct": round(len(wins) / len(trades) * 100, 2),
            "avg_days_held": round(np.mean([t.days_held for t in trades]), 1),
            "profit_factor": round(float(pf), 2), "total_return_pct": round(total, 2),
            "sharpe": round(float(sharpe), 2), "max_drawdown_pct": round(dd, 2),
            "final_equity": round(equity.iloc[-1], 2)}


def _run(name, tickers, s, e, cap, ms, ef, es, ts):
    print(f"\n===== {name}: {s} → {e}  (EMA{ef}/{es}, timestop {ts}d) =====")
    trades, eq = simulate(tickers, s, e, cap, ms, ef, es, ts)
    m = _metrics(trades, eq, cap)
    for k, v in m.items():
        print(f"  {k:20} {v}")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2018-01-01:2022-12-31")
    ap.add_argument("--test", default="2023-01-01:2025-12-31")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--min-score", type=int, default=5)
    ap.add_argument("--ema-fast", type=int, default=20)
    ap.add_argument("--ema-slow", type=int, default=50)
    ap.add_argument("--time-stop", type=int, default=4)
    ap.add_argument("--tickers", default=",".join(WATCHLIST))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    ts, te = args.train.split(":")
    vs, ve = args.test.split(":")
    _run("TRAIN", tickers, ts, te, args.capital, args.min_score, args.ema_fast, args.ema_slow, args.time_stop)
    m = _run("TEST", tickers, vs, ve, args.capital, args.min_score, args.ema_fast, args.ema_slow, args.time_stop)
    ok = (m.get("sharpe", 0) >= 1.0 and abs(m.get("max_drawdown_pct", -100)) <= 20
          and m.get("profit_factor", 0) >= 1.3)
    print("\n  ✅ Passes." if ok else "\n  ❌ Fails Sharpe≥1 / MaxDD≤20% / PF≥1.3.")


if __name__ == "__main__":
    main()
