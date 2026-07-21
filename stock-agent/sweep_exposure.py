#!/usr/bin/env python3
"""
Exposure sweep: how far can we push per-trade risk before max drawdown reaches
the index? Reuses the fast-daily (EMA20/50, 4d) engine but downloads once and
replays the portfolio sim at several MAX_RISK_PER_TRADE_PCT levels.

Goal: highest return whose max drawdown stays BELOW the same-period index
(SPY test maxDD -18.8%, QQQ -22.8%).
"""
import warnings
import numpy as np
import pandas as pd

import backtest_fastdaily as bt
from backtest_fastdaily import Trade

warnings.filterwarnings("ignore")

EMA_FAST, EMA_SLOW, TIME_STOP = 20, 50, 4
TR_M1, TR_M2, TR_M3 = bt.TRAIL_MILESTONE_1, bt.TRAIL_MILESTONE_2, bt.TRAIL_MILESTONE_3


def build(tickers, start, end):
    regime = bt._regime(start, end)
    prepared = {t: bt._prepare(t, start, end, EMA_FAST, EMA_SLOW) for t in tickers}
    prepared = {t: d for t, d in prepared.items() if d is not None}
    return prepared, regime


def run_sim(prepared, regime, risk_pct, position_pct, capital=1000.0, min_score=5):
    trades, cash, equity, open_pos = [], capital, {}, {}
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
            R = pos["entry"] - pos["init_stop"]
            if R > 0:
                hi = (pos["highest"] - pos["entry"]) / R
                if hi >= TR_M3:
                    pos["stop"] = round(pos["entry"] + (TR_M3 - TR_M2) * R, 2)
                elif hi >= TR_M2:
                    pos["stop"] = round(pos["entry"] + (TR_M2 - TR_M1) * R, 2)
                elif hi >= TR_M1:
                    pos["stop"] = pos["entry"]
            reason = price = None
            if float(bar["Low"]) <= pos["stop"]:
                reason = "stop" if pos["stop"] == pos["init_stop"] else "trail"
                price = pos["stop"]
            elif float(bar["High"]) >= pos["target"]:
                reason, price = "target", pos["target"]
            elif pos["days"] >= TIME_STOP:
                reason, price = "time", float(bar["Close"])
            if reason:
                cash += price * pos["shares"]
                trades.append(Trade(t, pos["entry_date"], date, pos["entry"], price,
                                    pos["shares"], (price - pos["entry"]) * pos["shares"],
                                    reason, pos["days"]))
                del open_pos[t]
        if allows_long:
            for t, df in prepared.items():
                if t in open_pos or date not in df.index:
                    continue
                row = df.loc[date]
                if pd.isna(row["atr"]) or row["atr"] <= 0 or bt._score(row) < min_score:
                    continue
                entry = float(row["Close"])
                stop = round(entry - bt.ATR_STOP_MULTIPLIER * float(row["atr"]), 2)
                risk = entry - stop
                if risk <= 0:
                    continue
                mult = 1.0 if reg == "BULL" else 0.5
                shares = round(min(cash * risk_pct * mult / risk,
                                   cash * position_pct / entry), 4)
                if shares < 0.01:
                    continue
                cost = shares * entry
                if cost > cash * 0.95:
                    continue
                cash -= cost
                open_pos[t] = {"shares": shares, "entry": entry, "init_stop": stop,
                               "stop": stop, "target": round(entry + bt.MAX_TARGET_R_MULTIPLE * risk, 2),
                               "entry_date": date, "highest": entry, "days": 0}
        open_val = sum(pos["shares"] * float(prepared[t].loc[date, "Close"])
                       for t, pos in open_pos.items() if date in prepared[t].index)
        equity[date] = cash + open_val
    return trades, pd.Series(equity).sort_index()


def metrics(trades, equity, starting=1000.0):
    total = (equity.iloc[-1] / starting - 1) * 100
    r = equity.pct_change().dropna()
    sharpe = np.sqrt(252) * r.mean() / r.std() if r.std() > 0 else 0
    dd = ((equity - equity.cummax()) / equity.cummax()).min() * 100
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else float("inf")
    return total, float(sharpe), dd, len(trades), (len(wins) / len(trades) * 100 if trades else 0), float(pf)


TK = "AAPL,MSFT,AMZN,META,GOOGL,TSLA,NVDA,AMD,AVGO,MU,ORCL,CRM,NOW,NFLX,PANW,CRWD,SHOP,UBER".split(",")
PERIODS = {"TRAIN 2018-2022": ("2018-01-01", "2022-12-31"),
           "TEST 2023-2025": ("2023-01-01", "2025-12-31")}
RISK_LEVELS = [0.01, 0.02, 0.03, 0.04, 0.05]
POSITION_PCT = 0.35  # raise single-stock cap so higher risk actually deploys

for label, (s, e) in PERIODS.items():
    print(f"\n===== {label} =====")
    print(f"  {'risk/trade':>10} {'return':>9} {'Sharpe':>7} {'maxDD':>8} {'trades':>7} {'win%':>6} {'PF':>5}")
    prepared, regime = build(TK, s, e)
    for rp in RISK_LEVELS:
        tr, eq = run_sim(prepared, regime, rp, POSITION_PCT)
        ret, sh, dd, n, wr, pf = metrics(tr, eq)
        print(f"  {rp*100:>9.0f}% {ret:>+8.1f}% {sh:>7.2f} {dd:>7.1f}% {n:>7} {wr:>5.0f}% {pf:>5.2f}")
