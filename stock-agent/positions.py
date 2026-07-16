"""
Position tracking + exit signal evaluation.

Positions are stored as a static list (positions.json or POSITIONS_JSON env var).
All dynamic state — highest price since entry, current trailing stop, days held —
is *re-derived from yfinance history* on each scan. This means the code is
stateless with respect to time: Railway container restarts, weekend gaps, or
you editing the JSON never desynchronize the computation.

R-multiple trailing stop rules (matches what I recommended in chat):
  Once price hits +1R (target/2 zone):  raise stop to entry (breakeven)
  Once price hits +2R:                   raise stop to entry + 1R
  Once price hits +3R:                   raise stop to entry + 2R
  Beyond +3R:                            keep last stop (don't cap unlimited upside)

Time-stop: after TIME_STOP_DAYS trading days with < 50% progress toward target, alert.
"""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from typing import Optional

import yfinance as yf

_POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "positions.json")

TIME_STOP_DAYS = 10


@dataclass
class Position:
    ticker: str
    shares: float
    entry_price: float
    entry_date: str  # ISO YYYY-MM-DD
    initial_stop: float
    target: float
    notes: str = ""

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


def load_positions() -> list[Position]:
    """
    Load from POSITIONS_JSON env var (preferred on Railway) or positions.json (local).
    Env var wins if both exist.
    """
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


def compute_trailing_stop(pos: Position, highest_price: float) -> tuple[float, Optional[str]]:
    """
    Return (current_stop, milestone_label_if_reached_new_level).
    Milestone label is None if we're still at initial stop.
    """
    R = pos.initial_risk_per_share
    if R <= 0:
        return pos.initial_stop, None

    highest_R = (highest_price - pos.entry_price) / R

    if highest_R >= 3:
        return round(pos.entry_price + 2 * R, 2), "3R milestone — stop locked at +2R"
    if highest_R >= 2:
        return round(pos.entry_price + 1 * R, 2), "2R milestone — stop locked at +1R"
    if highest_R >= 1:
        return round(pos.entry_price, 2), "1R milestone — stop moved to breakeven"
    return pos.initial_stop, None


# ---------- Data enrichment ----------


def _fetch_since_entry(ticker: str, entry_date: str) -> tuple[float, float, int]:
    """
    Return (current_price, highest_price_since_entry, days_held).
    days_held counts trading days (dropna handles weekends/holidays).
    """
    end = (datetime.utcnow().date()).isoformat()
    df = yf.Ticker(ticker).history(start=entry_date, end=end, interval="1d")
    if df.empty:
        # Fallback to a small recent window
        df = yf.Ticker(ticker).history(period="1mo", interval="1d")
    if df.empty:
        return 0.0, 0.0, 0

    current_price = float(df["Close"].iloc[-1])
    highest_price = float(df["High"].max())
    days_held = len(df)
    return current_price, highest_price, days_held


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
    Thesis is broken if the rules engine now emits SELL, or the score has
    collapsed (< 3 means most bullish conditions have unwound).
    """
    if rule_signal == "SELL" or rule_score < 3:
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

    current, highest, days = _fetch_since_entry(pos.ticker, pos.entry_date)
    if current <= 0:
        return []

    current_stop, milestone = compute_trailing_stop(pos, highest)

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
