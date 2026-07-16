#!/usr/bin/env python3
"""
Backtest the strategy on historical daily data.

We simulate the daily-timeframe portion of the rules engine (regime filter +
daily indicators) since intraday data is not freely available back to 2018.
This is a conservative approximation — the live system also uses hourly/15m
confirmations which reduce noise further, so a backtested strategy that
looks decent here should perform *at least as well* live.

Usage:
    python backtest.py --train 2018-01-01:2022-12-31 --test 2023-01-01:2025-12-31

Metrics computed (both train & test):
  - Total return
  - Sharpe ratio
  - Max drawdown
  - Win rate
  - Profit factor
  - Number of trades

Reject the strategy if TEST-set Sharpe < 1.0 or max drawdown > 20%.
"""

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    WATCHLIST,
    MAX_RISK_PER_TRADE_PCT,
    MAX_POSITION_PCT,
    MIN_RISK_REWARD_RATIO,
    ATR_STOP_MULTIPLIER,
    MIN_ADX_TRENDING,
)
from indicators import atr as compute_atr, adx as compute_adx


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    exit_reason: str


def _load_spy_regime(start: str, end: str) -> pd.DataFrame:
    spy = yf.download("SPY", start=start, end=end, progress=False, auto_adjust=True)
    vix = yf.download("^VIX", start=start, end=end, progress=False, auto_adjust=True)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
        vix.columns = vix.columns.get_level_values(0)
    spy["ma50"] = spy["Close"].rolling(50).mean()
    spy["ma200"] = spy["Close"].rolling(200).mean()
    spy["vix"] = vix["Close"].reindex(spy.index).ffill()

    def _classify(row):
        if pd.isna(row["ma200"]):
            return "NEUTRAL"
        if row["vix"] > 30:
            return "PANIC"
        if row["Close"] < row["ma200"]:
            return "BEAR"
        if row["Close"] > row["ma50"] > row["ma200"] and row["vix"] < 20:
            return "BULL"
        return "NEUTRAL"

    spy["regime"] = spy.apply(_classify, axis=1)
    return spy[["regime"]]


def _prepare_ticker(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df["sma_50"] = df["Close"].rolling(50).mean()
    df["sma_200"] = df["Close"].rolling(200).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(com=13, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - 100 / (1 + rs)

    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    df["macd_hist"] = macd_line - macd_line.ewm(span=9, adjust=False).mean()
    df["macd_bull_cross"] = (df["macd_hist"] > 0) & (df["macd_hist"].shift(1) <= 0)

    # Rolling ATR and ADX for stop-loss and trend strength
    df["atr"] = 0.0
    df["adx"] = 0.0
    for i in range(30, len(df)):
        window = df.iloc[i - 30 : i + 1]
        df.iloc[i, df.columns.get_loc("atr")] = compute_atr(window)
        df.iloc[i, df.columns.get_loc("adx")] = compute_adx(window)

    df["vol_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    return df.dropna(subset=["sma_200"])


def _signal_score(row: pd.Series) -> int:
    """Simplified daily-only version of rules_engine.evaluate."""
    score = 0
    if row["Close"] > row["sma_50"] > row["sma_200"]:
        score += 2
    if row["rsi"] < 40:
        score += 2
    if row["macd_bull_cross"]:
        score += 3
    if row["vol_ratio"] >= 1.5:
        score += 2
    if row["adx"] >= MIN_ADX_TRENDING:
        score += 1
    return score


def simulate(
    tickers: list[str],
    start: str,
    end: str,
    starting_capital: float = 1000.0,
    min_score: int = 6,
) -> tuple[list[Trade], pd.Series]:
    regime = _load_spy_regime(start, end)
    prepared = {t: _prepare_ticker(t, start, end) for t in tickers}
    prepared = {t: df for t, df in prepared.items() if df is not None}

    trades: list[Trade] = []
    capital = starting_capital
    equity_curve = {}
    open_positions: dict[str, dict] = {}

    # Build unified date index across all tickers + regime
    all_dates = sorted(
        set().union(*[df.index for df in prepared.values()]).intersection(regime.index)
    )

    for date in all_dates:
        try:
            current_regime = regime.loc[date, "regime"]
        except KeyError:
            current_regime = "NEUTRAL"
        allows_long = current_regime in ("BULL", "NEUTRAL")

        # ---- Check exits first ----
        for ticker in list(open_positions.keys()):
            pos = open_positions[ticker]
            if date not in prepared[ticker].index:
                continue
            bar = prepared[ticker].loc[date]
            exit_reason = None
            exit_price = None

            if bar["Low"] <= pos["stop"]:
                exit_reason = "stop_loss"
                exit_price = pos["stop"]
            elif bar["High"] >= pos["target"]:
                exit_reason = "target_hit"
                exit_price = pos["target"]

            if exit_reason:
                pnl = (exit_price - pos["entry"]) * pos["shares"]
                capital += exit_price * pos["shares"]
                trades.append(
                    Trade(
                        ticker=ticker,
                        entry_date=pos["entry_date"],
                        exit_date=date,
                        entry_price=pos["entry"],
                        exit_price=exit_price,
                        shares=pos["shares"],
                        pnl=pnl,
                        exit_reason=exit_reason,
                    )
                )
                del open_positions[ticker]

        # ---- Check entries ----
        if allows_long:
            for ticker, df in prepared.items():
                if ticker in open_positions:
                    continue
                if date not in df.index:
                    continue
                row = df.loc[date]
                if pd.isna(row["atr"]) or row["atr"] <= 0:
                    continue
                if _signal_score(row) < min_score:
                    continue

                entry = float(row["Close"])
                stop = round(entry - ATR_STOP_MULTIPLIER * row["atr"], 2)
                risk_per_share = entry - stop
                if risk_per_share <= 0:
                    continue

                # Regime size multiplier
                size_mult = 1.0 if current_regime == "BULL" else 0.5
                max_risk = capital * MAX_RISK_PER_TRADE_PCT * size_mult
                shares_by_risk = int(max_risk / risk_per_share)
                shares_by_size = int(capital * MAX_POSITION_PCT / entry)
                shares = min(shares_by_risk, shares_by_size)
                if shares < 1:
                    continue

                cost = shares * entry
                if cost > capital * 0.95:  # keep 5% cash
                    continue

                target = round(entry + MIN_RISK_REWARD_RATIO * risk_per_share, 2)
                capital -= cost
                open_positions[ticker] = {
                    "shares": shares,
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "entry_date": date,
                }

        # Mark-to-market equity
        open_value = sum(
            pos["shares"] * prepared[t].loc[date, "Close"]
            for t, pos in open_positions.items()
            if date in prepared[t].index
        )
        equity_curve[date] = capital + open_value

    return trades, pd.Series(equity_curve).sort_index()


def _metrics(trades: list[Trade], equity: pd.Series, starting: float) -> dict:
    if equity.empty:
        return {"error": "no equity curve"}

    total_return = (equity.iloc[-1] / starting - 1) * 100
    daily_returns = equity.pct_change().dropna()
    sharpe = (
        np.sqrt(252) * daily_returns.mean() / daily_returns.std()
        if daily_returns.std() > 0
        else 0
    )
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd = drawdown.min() * 100

    if not trades:
        return {
            "trades": 0,
            "total_return_pct": round(total_return, 2),
            "sharpe": round(float(sharpe), 2),
            "max_drawdown_pct": round(max_dd, 2),
        }

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    profit_factor = (
        sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")
    )

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2),
        "avg_win": round(np.mean(wins), 2) if wins else 0,
        "avg_loss": round(np.mean(losses), 2) if losses else 0,
        "profit_factor": round(float(profit_factor), 2),
        "total_return_pct": round(total_return, 2),
        "sharpe": round(float(sharpe), 2),
        "max_drawdown_pct": round(max_dd, 2),
        "final_equity": round(equity.iloc[-1], 2),
    }


def _run_split(name: str, tickers, start: str, end: str, capital: float, min_score: int):
    print(f"\n===== {name}: {start} → {end} =====")
    trades, equity = simulate(tickers, start, end, capital, min_score)
    metrics = _metrics(trades, equity, capital)
    for k, v in metrics.items():
        print(f"  {k:20} {v}")
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2018-01-01:2022-12-31")
    ap.add_argument("--test", default="2023-01-01:2025-12-31")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--min-score", type=int, default=6)
    ap.add_argument("--tickers", default=",".join(WATCHLIST))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    train_s, train_e = args.train.split(":")
    test_s, test_e = args.test.split(":")

    train_metrics = _run_split(
        "TRAIN (in-sample)", tickers, train_s, train_e, args.capital, args.min_score
    )
    test_metrics = _run_split(
        "TEST (out-of-sample)", tickers, test_s, test_e, args.capital, args.min_score
    )

    print("\n===== VERDICT =====")
    ok = (
        test_metrics.get("sharpe", 0) >= 1.0
        and abs(test_metrics.get("max_drawdown_pct", -100)) <= 20
        and test_metrics.get("profit_factor", 0) >= 1.3
    )
    if ok:
        print("  ✅ Strategy passes out-of-sample validation. Safe to paper-trade.")
    else:
        print("  ❌ Strategy fails one of: Sharpe≥1, MaxDD≤20%, ProfitFactor≥1.3")
        print("     Tune parameters or scrap. Do NOT go live.")


if __name__ == "__main__":
    main()
