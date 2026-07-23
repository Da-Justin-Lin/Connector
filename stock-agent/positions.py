"""
Position tracking + exit signal evaluation.

Positions are stored as a static list (positions.json or POSITIONS_JSON env var).
All dynamic state — highest price since entry, current trailing stop, days held —
is *re-derived from yfinance history* on each scan. This means the code is
stateless with respect to time: Railway container restarts, weekend gaps, or
you editing the JSON never desynchronize the computation.

Trailing stop: continuous Chandelier — highest high since entry − k×ATR(14),
ratcheting up only (never loosens), floored at the initial hard stop. The whole
trail is re-derived from history each scan, so it stays stateless: stop_i =
max(initial_stop, running_max(high_water_i − k×ATR_i)).

Time-stop: after TIME_STOP_DAYS trading days with < 50% progress toward target, alert.
"""

import json
import math
import os
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

from config import (
    TIME_STOP_DAYS,
    CHANDELIER_ATR_MULT,
    CHANDELIER_ATR_PERIOD,
)

_POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "positions.json")


@dataclass
class Position:
    ticker: str
    shares: float
    entry_price: float
    entry_date: str  # ISO YYYY-MM-DD
    initial_stop: float
    target: float
    notes: str = ""
    id: str = ""  # Connector position id (empty for local positions.json entries)

    @property
    def initial_risk_per_share(self) -> float:
        return self.entry_price - self.initial_stop

    @property
    def initial_risk_dollars(self) -> float:
        return self.shares * self.initial_risk_per_share


@dataclass
class ExitAlert:
    ticker: str
    alert_type: str        # HARD_STOP / TARGET_HIT / TRAIL_RAISED / THESIS_BROKEN / TIME_STOP / REGIME_SHIFT
    urgency: str           # IMMEDIATE / IMPORTANT / ADVISORY
    message: str
    current_price: float
    entry_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    days_held: int
    current_stop: float
    target: float
    shares: float
    detail: dict = field(default_factory=dict)


# ---------- Persistence ----------


def _load_from_connector() -> Optional[list[Position]]:
    """
    Pull OPEN positions the user confirmed on the Connector dashboard.

    This is now the source of truth for what we monitor: the user clicks
    "I bought this" on a BUY signal, which creates a position with an id, and
    we return exit alerts tagged with that id. Returns None (not []) when
    Connector isn't configured so the caller can fall back to local files.
    """
    base = os.environ.get("CONNECTOR_API_URL", "").strip().rstrip("/")
    key = os.environ.get("CONNECTOR_AGENT_KEY", "").strip()
    if not base or not key:
        return None
    try:
        resp = requests.get(
            f"{base}/api/v1/positions/monitor",
            headers={"X-Agent-Key": key},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[positions] Connector monitor error {resp.status_code}: {resp.text[:200]}")
            return None
        out = []
        for p in resp.json().get("positions", []):
            out.append(
                Position(
                    id=str(p["id"]),
                    ticker=p["ticker"],
                    shares=float(p["shares"]),
                    entry_price=float(p["entry_price"]),
                    entry_date=str(p["entry_date"])[:10],  # yfinance wants YYYY-MM-DD
                    initial_stop=float(p["initial_stop"]),
                    target=float(p["target"]),
                )
            )
        return out
    except Exception as e:
        print(f"[positions] Connector monitor fetch failed: {e}")
        return None


def load_positions() -> list[Position]:
    """
    Source order: Connector dashboard (if configured) → POSITIONS_JSON env var →
    local positions.json.
    """
    from_connector = _load_from_connector()
    if from_connector is not None:
        return from_connector

    raw = os.environ.get("POSITIONS_JSON", "").strip()
    if raw:
        data = json.loads(raw)
    elif os.path.exists(_POSITIONS_FILE):
        with open(_POSITIONS_FILE) as f:
            data = json.load(f)
    else:
        return []

    return [Position(**p) for p in data]


def save_positions(positions: list[Position]) -> None:
    with open(_POSITIONS_FILE, "w") as f:
        json.dump([asdict(p) for p in positions], f, indent=2)


# ---------- Trailing stop ----------


def compute_trailing_stop(
    pos: Position, held_highs: Optional[pd.Series], held_atrs: Optional[pd.Series]
) -> tuple[float, Optional[str]]:
    """
    Continuous Chandelier trailing stop, reconstructed statelessly from the
    holding-window daily bars:

        stop_i = high_water_i − k×ATR_i,  ratcheted up (never loosens),
                 floored at the initial hard stop

    where high_water_i is the running max High since entry and ATR_i is the
    14-bar ATR at bar i. `held_highs` and `held_atrs` are aligned per-bar Series
    over entry_date..today (see _fetch_since_entry). Returns
    (current_stop, label_if_raised_above_initial_stop).
    """
    if held_highs is None or held_atrs is None or len(held_highs) == 0:
        return round(pos.initial_stop, 2), None

    chandelier = (held_highs.cummax() - CHANDELIER_ATR_MULT * held_atrs).cummax()
    last = float(chandelier.iloc[-1])
    if math.isnan(last):
        return round(pos.initial_stop, 2), None

    stop = round(max(pos.initial_stop, last), 2)
    if stop <= round(pos.initial_stop, 2):
        return stop, None

    R = pos.initial_risk_per_share
    locked_R = (stop - pos.entry_price) / R if R > 0 else 0.0
    if stop >= pos.entry_price:
        label = f"trailing stop now protects +{locked_R:.1f}R"
    else:
        label = "trailing stop tightened toward breakeven"
    return stop, label


# ---------- Data enrichment ----------


def _atr_series(df: pd.DataFrame, period: int = CHANDELIER_ATR_PERIOD) -> pd.Series:
    """Rolling-mean ATR series (matches indicators.atr / the backtests)."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev).abs(), (low - prev).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period).mean()


def _fetch_since_entry(ticker: str, entry_date: str):
    """
    Return (current_price, highest_price, days_held, held_highs, held_atrs).

    Pulls ~45 calendar days of lookback before entry so ATR-14 is valid across
    the whole holding window; highest_price, days_held and the trailing series
    are measured over the holding window (entry_date..today) only.
    """
    entry_dt = date.fromisoformat(str(entry_date)[:10])
    start = (entry_dt - timedelta(days=45)).isoformat()
    end = datetime.utcnow().date().isoformat()
    df = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
    if df.empty:
        # Fallback to a small recent window
        df = yf.Ticker(ticker).history(period="3mo", interval="1d")
    if df.empty:
        return 0.0, 0.0, 0, None, None

    atr = _atr_series(df)
    held = df.index.date >= entry_dt
    if not held.any():
        # Position dated in the future / no bars yet — fall back to the last bar.
        held = df.index == df.index[-1]

    current_price = float(df["Close"].iloc[-1])
    highest_price = float(df["High"][held].max())
    days_held = int(held.sum())
    return current_price, highest_price, days_held, df["High"][held], atr[held]


# ---------- Exit signal evaluators ----------


def _check_hard_stop(pos: Position, current: float, stop: float, days: int) -> Optional[ExitAlert]:
    if current <= stop:
        pnl = (current - pos.entry_price) * pos.shares
        return ExitAlert(
            ticker=pos.ticker,
            alert_type="HARD_STOP",
            urgency="IMMEDIATE",
            message=f"🚨 SELL {pos.ticker} — price ${current:.2f} hit stop ${stop:.2f}",
            current_price=current,
            entry_price=pos.entry_price,
            unrealized_pnl=round(pnl, 2),
            unrealized_pnl_pct=round(pnl / (pos.entry_price * pos.shares) * 100, 2),
            days_held=days,
            current_stop=stop,
            target=pos.target,
            shares=pos.shares,
        )
    return None


def _check_target(pos: Position, current: float, stop: float, days: int) -> Optional[ExitAlert]:
    if current >= pos.target:
        pnl = (current - pos.entry_price) * pos.shares
        return ExitAlert(
            ticker=pos.ticker,
            alert_type="TARGET_HIT",
            urgency="IMPORTANT",
            message=f"✅ TARGET HIT {pos.ticker} @ ${current:.2f} — take profit or sell half + trail",
            current_price=current,
            entry_price=pos.entry_price,
            unrealized_pnl=round(pnl, 2),
            unrealized_pnl_pct=round(pnl / (pos.entry_price * pos.shares) * 100, 2),
            days_held=days,
            current_stop=stop,
            target=pos.target,
            shares=pos.shares,
        )
    return None


def _check_trail(pos: Position, current: float, stop: float, days: int, milestone: Optional[str]) -> Optional[ExitAlert]:
    if milestone is None:
        return None
    pnl = (current - pos.entry_price) * pos.shares
    return ExitAlert(
        ticker=pos.ticker,
        alert_type="TRAIL_RAISED",
        urgency="ADVISORY",
        message=f"💡 {pos.ticker} — {milestone}. Update your Robinhood stop to ${stop:.2f}",
        current_price=current,
        entry_price=pos.entry_price,
        unrealized_pnl=round(pnl, 2),
        unrealized_pnl_pct=round(pnl / (pos.entry_price * pos.shares) * 100, 2),
        days_held=days,
        current_stop=stop,
        target=pos.target,
        shares=pos.shares,
        detail={"milestone": milestone},
    )


def _check_thesis(pos: Position, current: float, stop: float, days: int, rule_signal, rule_score: int) -> Optional[ExitAlert]:
    """
    Thesis is broken when the long score has collapsed (< 3 means most bullish
    conditions that justified the entry have unwound). The agent is long-only,
    so `rule_signal` here is only ever BUY or HOLD.
    """
    if rule_score < 3:
        pnl = (current - pos.entry_price) * pos.shares
        return ExitAlert(
            ticker=pos.ticker,
            alert_type="THESIS_BROKEN",
            urgency="IMPORTANT",
            message=(
                f"⚠️ {pos.ticker} — original BUY thesis has weakened "
                f"(rules now: {rule_signal}, score {rule_score}/13). Consider exiting."
            ),
            current_price=current,
            entry_price=pos.entry_price,
            unrealized_pnl=round(pnl, 2),
            unrealized_pnl_pct=round(pnl / (pos.entry_price * pos.shares) * 100, 2),
            days_held=days,
            current_stop=stop,
            target=pos.target,
            shares=pos.shares,
            detail={"current_rule_signal": rule_signal, "current_score": rule_score},
        )
    return None


def _check_time_stop(pos: Position, current: float, stop: float, days: int) -> Optional[ExitAlert]:
    if days < TIME_STOP_DAYS:
        return None
    progress_pct = (current - pos.entry_price) / (pos.target - pos.entry_price) * 100
    if progress_pct >= 50:
        return None
    pnl = (current - pos.entry_price) * pos.shares
    return ExitAlert(
        ticker=pos.ticker,
        alert_type="TIME_STOP",
        urgency="ADVISORY",
        message=(
            f"⏰ {pos.ticker} — held {days} days, only {progress_pct:.0f}% of the way to target. "
            f"Consider closing to free capital."
        ),
        current_price=current,
        entry_price=pos.entry_price,
        unrealized_pnl=round(pnl, 2),
        unrealized_pnl_pct=round(pnl / (pos.entry_price * pos.shares) * 100, 2),
        days_held=days,
        current_stop=stop,
        target=pos.target,
        shares=pos.shares,
        detail={"progress_pct": round(progress_pct, 1)},
    )


def _check_regime_shift(pos: Position, current: float, stop: float, days: int, regime) -> Optional[ExitAlert]:
    if regime.regime in ("BEAR", "PANIC"):
        pnl = (current - pos.entry_price) * pos.shares
        return ExitAlert(
            ticker=pos.ticker,
            alert_type="REGIME_SHIFT",
            urgency="IMPORTANT",
            message=(
                f"⚠️ {pos.ticker} — market regime shifted to {regime.regime}. "
                f"Long positions have elevated risk. {regime.reason}"
            ),
            current_price=current,
            entry_price=pos.entry_price,
            unrealized_pnl=round(pnl, 2),
            unrealized_pnl_pct=round(pnl / (pos.entry_price * pos.shares) * 100, 2),
            days_held=days,
            current_stop=stop,
            target=pos.target,
            shares=pos.shares,
            detail={"regime": regime.regime},
        )
    return None


# ---------- Public entrypoint ----------


def evaluate_position(pos: Position) -> list[ExitAlert]:
    """
    Run all exit checks for a single position.
    Imports done lazily to avoid circular imports and to keep this module fast.
    """
    from market_regime import get_regime
    from data_fetcher import fetch_stock_snapshot
    from rules_engine import evaluate as rule_evaluate

    current, highest, days, highs, atrs = _fetch_since_entry(pos.ticker, pos.entry_date)
    if current <= 0:
        return []

    current_stop, milestone = compute_trailing_stop(pos, highs, atrs)

    alerts: list[ExitAlert] = []

    # Hard stop must be checked first — if hit, other advisory signals are noise
    hs = _check_hard_stop(pos, current, current_stop, days)
    if hs:
        return [hs]

    tgt = _check_target(pos, current, current_stop, days)
    if tgt:
        alerts.append(tgt)

    trail = _check_trail(pos, current, current_stop, days, milestone)
    if trail:
        alerts.append(trail)

    # Regime shift — cheap, cached
    regime = get_regime()
    rs = _check_regime_shift(pos, current, current_stop, days, regime)
    if rs:
        alerts.append(rs)

    # Thesis check requires full snapshot (multi-timeframe) — do it last
    snap = fetch_stock_snapshot(pos.ticker)
    if snap:
        rule = rule_evaluate(snap)
        th = _check_thesis(pos, current, current_stop, days, rule.signal, rule.score)
        if th:
            alerts.append(th)

    # Time stop — advisory only, and only if nothing more urgent already fired
    if not alerts:
        ts = _check_time_stop(pos, current, current_stop, days)
        if ts:
            alerts.append(ts)

    return alerts


def evaluate_all() -> list[ExitAlert]:
    all_alerts = []
    for pos in load_positions():
        all_alerts.extend(evaluate_position(pos))
    return all_alerts
