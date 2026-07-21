"""
Risk management: position sizing, hard stop-loss enforcement, daily loss circuit breaker.

Every trade must pass check_trade() before it can be sent to the broker.
State persists across restarts via risk_state.json so restarting the agent
does not accidentally reset a triggered circuit breaker.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Optional

from config import (
    ACCOUNT_CAPITAL,
    MAX_RISK_PER_TRADE_PCT,
    MAX_POSITION_PCT,
    MAX_DAILY_LOSS_PCT,
    MAX_DRAWDOWN_PCT,
    MIN_RISK_REWARD_RATIO,
    MAX_OPEN_POSITIONS,
    ATR_STOP_MULTIPLIER,
    ALLOW_FRACTIONAL_SHARES,
    MIN_FRACTIONAL_SHARES,
    MAX_TARGET_R_MULTIPLE,
)

_STATE_FILE = os.path.join(os.path.dirname(__file__), "risk_state.json")


@dataclass
class RiskState:
    trading_date: str
    starting_capital: float
    current_capital: float
    peak_capital: float
    daily_pnl: float
    daily_loss_locked: bool
    drawdown_locked: bool
    open_positions: dict  # ticker -> {shares, entry, stop, target}

    @classmethod
    def fresh(cls, capital: float) -> "RiskState":
        return cls(
            trading_date=str(date.today()),
            starting_capital=capital,
            current_capital=capital,
            peak_capital=capital,
            daily_pnl=0.0,
            daily_loss_locked=False,
            drawdown_locked=False,
            open_positions={},
        )


def _load_state() -> RiskState:
    if not os.path.exists(_STATE_FILE):
        return RiskState.fresh(ACCOUNT_CAPITAL)
    with open(_STATE_FILE) as f:
        raw = json.load(f)
    state = RiskState(**raw)
    # New trading day → reset daily counters but keep drawdown state
    if state.trading_date != str(date.today()):
        state.trading_date = str(date.today())
        state.daily_pnl = 0.0
        state.daily_loss_locked = False
        state.starting_capital = state.current_capital
    return state


def _save_state(state: RiskState) -> None:
    with open(_STATE_FILE, "w") as f:
        json.dump(asdict(state), f, indent=2)


@dataclass
class TradeDecision:
    approved: bool
    reason: str
    shares: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_reward_ratio: float = 0.0
    risk_dollars: float = 0.0
    position_value: float = 0.0


def _atr_stop(entry: float, atr: float, direction: str = "long") -> float:
    """ATR-based dynamic stop-loss."""
    if direction == "long":
        return round(entry - ATR_STOP_MULTIPLIER * atr, 2)
    return round(entry + ATR_STOP_MULTIPLIER * atr, 2)


def check_trade(
    ticker: str,
    signal: str,
    entry_price: float,
    atr: float,
    proposed_target: Optional[float] = None,
) -> TradeDecision:
    """
    Gate a proposed trade through all risk checks.

    Returns TradeDecision(approved=True, ...) with computed shares/stop/target
    if the trade passes, otherwise approved=False with the reason.
    """
    state = _load_state()

    if signal not in ("BUY", "SELL"):
        return TradeDecision(False, f"Signal must be BUY or SELL, got {signal}")

    if state.daily_loss_locked:
        return TradeDecision(
            False, f"Daily loss circuit breaker tripped (pnl={state.daily_pnl:.2f})"
        )

    if state.drawdown_locked:
        return TradeDecision(
            False,
            f"Max drawdown breached (peak=${state.peak_capital:.2f} "
            f"now=${state.current_capital:.2f})",
        )

    if len(state.open_positions) >= MAX_OPEN_POSITIONS:
        return TradeDecision(
            False, f"Max open positions ({MAX_OPEN_POSITIONS}) already reached"
        )

    if ticker in state.open_positions:
        return TradeDecision(False, f"Already have an open position in {ticker}")

    if atr <= 0:
        return TradeDecision(False, "ATR is zero — cannot compute stop-loss")

    direction = "long" if signal == "BUY" else "short"
    stop = _atr_stop(entry_price, atr, direction)
    risk_per_share = abs(entry_price - stop)

    if risk_per_share <= 0:
        return TradeDecision(False, "Computed risk per share is zero")

    # Position sizing: risk = capital * MAX_RISK_PER_TRADE_PCT
    max_risk = state.current_capital * MAX_RISK_PER_TRADE_PCT
    max_position_value = state.current_capital * MAX_POSITION_PCT

    if ALLOW_FRACTIONAL_SHARES:
        # Robinhood accepts 4-decimal fractional shares.
        shares_by_risk = round(max_risk / risk_per_share, 4)
        shares_by_size = round(max_position_value / entry_price, 4)
        shares = min(shares_by_risk, shares_by_size)
        min_shares = MIN_FRACTIONAL_SHARES
    else:
        shares_by_risk = int(max_risk / risk_per_share)
        shares_by_size = int(max_position_value / entry_price)
        shares = float(min(shares_by_risk, shares_by_size))
        min_shares = 1.0

    if shares < min_shares:
        return TradeDecision(
            False,
            f"Position size < {min_shares} shares (risk-cap: {shares_by_risk}, "
            f"size-cap: {shares_by_size}, capital: ${state.current_capital:.2f})",
        )

    # Target: 2x the risk if not provided
    if proposed_target is None or proposed_target <= 0:
        if direction == "long":
            target = round(entry_price + MIN_RISK_REWARD_RATIO * risk_per_share, 2)
        else:
            target = round(entry_price - MIN_RISK_REWARD_RATIO * risk_per_share, 2)
    else:
        target = proposed_target

    # Cap target R-multiple so short-swing trades don't chase a distant
    # Bollinger upper band that would take weeks to reach.
    max_cap = MAX_TARGET_R_MULTIPLE * risk_per_share
    if direction == "long":
        target = min(target, round(entry_price + max_cap, 2))
    else:
        target = max(target, round(entry_price - max_cap, 2))

    reward_per_share = abs(target - entry_price)
    rr_ratio = reward_per_share / risk_per_share

    if rr_ratio < MIN_RISK_REWARD_RATIO:
        return TradeDecision(
            False,
            f"Risk:Reward too low ({rr_ratio:.2f} < {MIN_RISK_REWARD_RATIO})",
        )

    return TradeDecision(
        approved=True,
        reason="All risk checks passed",
        shares=shares,
        entry_price=entry_price,
        stop_loss=stop,
        target_price=target,
        risk_reward_ratio=round(rr_ratio, 2),
        risk_dollars=round(shares * risk_per_share, 2),
        position_value=round(shares * entry_price, 2),
    )


def record_entry(ticker: str, decision: TradeDecision) -> None:
    """Register an opened position."""
    state = _load_state()
    state.open_positions[ticker] = {
        "shares": decision.shares,
        "entry": decision.entry_price,
        "stop": decision.stop_loss,
        "target": decision.target_price,
        "opened_at": datetime.now().isoformat(),
    }
    _save_state(state)


def record_exit(ticker: str, exit_price: float) -> dict:
    """
    Register a closed position and update P&L / circuit breakers.
    Returns a summary of the closed trade.
    """
    state = _load_state()
    if ticker not in state.open_positions:
        return {"error": f"No open position for {ticker}"}

    pos = state.open_positions.pop(ticker)
    pnl = (exit_price - pos["entry"]) * pos["shares"]

    state.daily_pnl += pnl
    state.current_capital += pnl
    state.peak_capital = max(state.peak_capital, state.current_capital)

    # Daily loss circuit breaker
    if state.daily_pnl < -state.starting_capital * MAX_DAILY_LOSS_PCT:
        state.daily_loss_locked = True

    # Max drawdown circuit breaker
    drawdown = (state.peak_capital - state.current_capital) / state.peak_capital
    if drawdown > MAX_DRAWDOWN_PCT:
        state.drawdown_locked = True

    _save_state(state)

    return {
        "ticker": ticker,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl / (pos["entry"] * pos["shares"]) * 100, 2),
        "daily_pnl": round(state.daily_pnl, 2),
        "capital_after": round(state.current_capital, 2),
        "daily_loss_locked": state.daily_loss_locked,
        "drawdown_locked": state.drawdown_locked,
    }


def get_status() -> dict:
    state = _load_state()
    drawdown_pct = (
        (state.peak_capital - state.current_capital) / state.peak_capital * 100
        if state.peak_capital > 0
        else 0
    )
    return {
        "trading_date": state.trading_date,
        "capital": round(state.current_capital, 2),
        "daily_pnl": round(state.daily_pnl, 2),
        "daily_pnl_pct": round(state.daily_pnl / state.starting_capital * 100, 2),
        "peak_capital": round(state.peak_capital, 2),
        "drawdown_pct": round(drawdown_pct, 2),
        "open_positions": list(state.open_positions.keys()),
        "daily_loss_locked": state.daily_loss_locked,
        "drawdown_locked": state.drawdown_locked,
    }


def reset_circuit_breakers() -> None:
    """Manual override — use with care."""
    state = _load_state()
    state.daily_loss_locked = False
    state.drawdown_locked = False
    _save_state(state)
