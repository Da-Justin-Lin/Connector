"""
Hybrid signal analyzer.

Flow:
  1. Regime filter — global stop (BEAR/PANIC → no longs, etc.)
  2. Rules engine  — deterministic multi-timeframe scoring, must pass score threshold
  3. Risk manager  — position sizing, R:R gate, stop-loss computation
  4. Claude LLM    — VETO ONLY: reads news/context and can downgrade to HOLD
                     never can UP-grade HOLD → BUY

This design makes the strategy debuggable, backtestable, and safe.
The LLM is the last line of defense, not the driver.
"""

import json
import os

import anthropic

from config import (
    CHANDELIER_ATR_MULT,
    MAX_TARGET_R_MULTIPLE,
    TIME_STOP_DAYS,
)
from market_regime import get_regime
from rules_engine import evaluate as rule_evaluate
from risk_manager import check_trade


def _build_exit_plan(entry: float, stop: float, target: float) -> str:
    """
    Turn the trailing rules into a plain-language plan the user can read at a
    glance. Mirrors positions.compute_trailing_stop (continuous Chandelier), so
    the entry alert and the later exit alerts tell the same story.
    """
    R = entry - stop
    if R <= 0:
        return ""
    return (
        f"Initial stop ${stop:.2f} (−1R, risk ${R:.2f}/sh). "
        f"Trailing stop = highest high since entry − {CHANDELIER_ATR_MULT:g}×ATR(14), "
        f"ratcheting up only (never loosens) — raise your Robinhood stop as it climbs. "
        f"Take profit at target ${target:.2f} (+{MAX_TARGET_R_MULTIPLE:g}R). "
        f"Time-exit after {TIME_STOP_DAYS} trading days if <50% to target."
    )

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


_VETO_SYSTEM = """You are a defensive risk reviewer for an automated trading agent.

You will be shown a technical trade setup that already passed:
- Market regime filter
- Multi-timeframe rules engine (with a numeric confidence score)
- Position sizing and risk-reward gates

Your job is NARROW: decide whether to VETO the trade based on qualitative context
the rules engine can't see. This includes:
- Imminent earnings (within 3 trading days) → veto, IV crush risk
- Recent major negative news, SEC investigation, guidance cut → veto
- Extraordinary macro event today (Fed decision, CPI print, war headline) → veto
- Company-specific event that invalidates trend read (CEO resigns, product recall) → veto

You may NEVER promote HOLD to BUY/SELL. You can only downgrade to HOLD.
You may NEVER expand position size, change stop-loss, or change target.

Respond with valid JSON only:
{
  "vetoed": true | false,
  "reason": "<one sentence — required if vetoed=true>"
}"""


def _llm_veto(ticker: str, signal: str, rule_reasons: list[str]) -> tuple[bool, str]:
    """Ask Claude if there's a qualitative reason to kill this trade."""
    if os.environ.get("SKIP_LLM_VETO", "").lower() == "true":
        return False, ""

    prompt = (
        f"Ticker: {ticker}\n"
        f"Rules-engine signal: {signal}\n"
        f"Rules that fired:\n" + "\n".join(f"  - {r}" for r in rule_reasons) + "\n\n"
        f"Should we veto this trade? Return JSON only."
    )
    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            system=_VETO_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # Strip common markdown fences the model might add
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json\n").strip()
        result = json.loads(raw)
        return bool(result.get("vetoed")), result.get("reason", "")
    except Exception as e:
        # If LLM fails, DON'T veto — the deterministic rules already cleared this.
        # Failing open here means an LLM outage doesn't halt trading.
        print(f"[analyzer] LLM veto call failed for {ticker}: {e}")
        return False, ""


def analyze(snapshot: dict) -> dict | None:
    """
    Full pipeline. Returns a signal dict compatible with the existing alerter/notifier,
    or None if the ticker was filtered out early with no useful info to report.
    """
    ticker = snapshot["ticker"]
    price = snapshot["price"]

    # ---------- 1. Regime filter ----------
    regime = get_regime()

    # ---------- 2. Rules engine ----------
    rule = rule_evaluate(snapshot)

    # Regime veto: don't take longs in BEAR/PANIC or shorts in BULL
    if rule.signal == "BUY" and not regime.allows_long():
        return {
            "ticker": ticker,
            "price": price,
            "signal": "HOLD",
            "confidence": "LOW",
            "reasoning": (
                f"Rules said BUY (score {rule.score}/{rule.max_score}) but "
                f"regime={regime.regime} blocks longs. {regime.reason}"
            ),
            "score": rule.score,
            "regime": regime.regime,
        }
    if rule.signal == "SELL" and not regime.allows_short():
        return {
            "ticker": ticker,
            "price": price,
            "signal": "HOLD",
            "confidence": "LOW",
            "reasoning": (
                f"Rules said SELL (score {rule.score}/{rule.max_score}) but "
                f"regime={regime.regime} blocks shorts. {regime.reason}"
            ),
            "score": rule.score,
            "regime": regime.regime,
        }

    if rule.signal == "HOLD":
        return {
            "ticker": ticker,
            "price": price,
            "signal": "HOLD",
            "confidence": "LOW",
            "reasoning": f"Score {rule.score}/{rule.max_score} below threshold. "
                        + " | ".join(rule.reasons[:3]),
            "score": rule.score,
            "regime": regime.regime,
        }

    # ---------- 3. Risk manager ----------
    decision = check_trade(
        ticker=ticker,
        signal=rule.signal,
        entry_price=rule.entry_price,
        atr=rule.atr,
        proposed_target=(
            rule.daily_bb_upper if rule.signal == "BUY" else rule.daily_bb_lower
        ),
    )
    if not decision.approved:
        return {
            "ticker": ticker,
            "price": price,
            "signal": "HOLD",
            "confidence": "LOW",
            "reasoning": f"Risk manager rejected: {decision.reason}",
            "score": rule.score,
            "regime": regime.regime,
        }

    # ---------- 4. LLM veto ----------
    vetoed, veto_reason = _llm_veto(ticker, rule.signal, rule.reasons)
    if vetoed:
        return {
            "ticker": ticker,
            "price": price,
            "signal": "HOLD",
            "confidence": "LOW",
            "reasoning": f"LLM veto: {veto_reason}",
            "score": rule.score,
            "regime": regime.regime,
        }

    # ---------- Approved trade ----------
    # Confidence = f(score, regime, R:R)
    confidence = "HIGH" if rule.score >= 9 and regime.regime == "BULL" else "MEDIUM"

    # Apply regime size multiplier (NEUTRAL regime → half size)
    from config import ALLOW_FRACTIONAL_SHARES, MIN_FRACTIONAL_SHARES
    raw_adjusted = decision.shares * regime.position_size_multiplier()
    adjusted_shares = round(raw_adjusted, 4) if ALLOW_FRACTIONAL_SHARES else int(raw_adjusted)
    min_shares = MIN_FRACTIONAL_SHARES if ALLOW_FRACTIONAL_SHARES else 1
    if adjusted_shares < min_shares:
        return {
            "ticker": ticker,
            "price": price,
            "signal": "HOLD",
            "confidence": "LOW",
            "reasoning": f"After regime scaling, position < {min_shares} shares ({regime.regime})",
            "score": rule.score,
            "regime": regime.regime,
        }

    return {
        "ticker": ticker,
        "price": price,
        "signal": rule.signal,
        "confidence": confidence,
        "entry_price": decision.entry_price,
        "target_price": decision.target_price,
        "stop_loss": decision.stop_loss,
        "shares": adjusted_shares,
        "position_value": round(adjusted_shares * decision.entry_price, 2),
        "risk_dollars": round(adjusted_shares * abs(decision.entry_price - decision.stop_loss), 2),
        "risk_reward_ratio": decision.risk_reward_ratio,
        "score": rule.score,
        "max_score": rule.max_score,
        "regime": regime.regime,
        "exit_plan": _build_exit_plan(
            decision.entry_price, decision.stop_loss, decision.target_price
        ),
        "reasoning": (
            f"Score {rule.score}/{rule.max_score} in {regime.regime} regime. "
            + " | ".join(rule.reasons[:4])
        ),
    }
