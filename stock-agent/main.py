#!/usr/bin/env python3
"""
Automated trading agent — main loop.

Pipeline per cycle:
  1. Skip if market closed
  2. Fetch snapshots (multi-timeframe indicators)
  3. Analyze (regime → rules → risk → LLM veto)
  4. If BUY/SELL passes all gates, send order via robinhood_broker
  5. Notify via GChat + email
"""

import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# Anthropic key is only required when LLM veto is enabled.
_skip_llm = os.environ.get("SKIP_LLM_VETO", "").lower() == "true"
if not _skip_llm and not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY is not set.")
    print("  Either add the key to .env, or set SKIP_LLM_VETO=true to disable")
    print("  the LLM review step (rules + risk gates will still run).")
    sys.exit(1)

from colorama import Fore, Style, init

from config import WATCHLIST, CHECK_INTERVAL_SECONDS, MIN_ALERT_CONFIDENCE, TRADE_MODE
from market_hours import is_market_open, seconds_until_market_open
from data_fetcher import fetch_all
from analyzer import analyze
from alerter import display, display_hold, display_scan_header, should_alert
from risk_manager import get_status as risk_status, record_entry
import robinhood_broker

init(autoreset=True)


def _place_order_if_needed(signal: dict) -> None:
    """
    If the signal was BUY/SELL and TRADE_MODE isn't SIGNAL_ONLY, submit the order
    and record the position with the risk manager. Any resulting status is added
    back into the signal dict so notifier can include it.
    """
    if signal["signal"] not in ("BUY", "SELL"):
        return

    if TRADE_MODE == "SIGNAL_ONLY":
        signal["order_status"] = "SIGNAL_ONLY mode — no order placed"
        return

    side = "buy" if signal["signal"] == "BUY" else "sell"
    result = robinhood_broker.place_order(
        ticker=signal["ticker"],
        side=side,
        shares=signal["shares"],
        limit_price=signal["entry_price"],
        stop_loss=signal["stop_loss"],
        target_price=signal["target_price"],
    )

    if result.ok:
        signal["order_status"] = (
            f"[{result.mode}] {result.message}"
            + (f" (id={result.order_id})" if result.order_id else "")
        )
        # Only record long entries in the local risk state for now.
        # Shorts / exits will be handled once we wire fill webhooks.
        if signal["signal"] == "BUY" and TRADE_MODE == "FULL_AUTO":
            from risk_manager import TradeDecision
            record_entry(
                signal["ticker"],
                TradeDecision(
                    approved=True,
                    reason="",
                    shares=signal["shares"],
                    entry_price=signal["entry_price"],
                    stop_loss=signal["stop_loss"],
                    target_price=signal["target_price"],
                    risk_reward_ratio=signal["risk_reward_ratio"],
                ),
            )
    else:
        signal["order_status"] = f"[{result.mode}] ORDER FAILED: {result.message}"


def run_scan(tickers: list[str]) -> None:
    display_scan_header(tickers)
    status = risk_status()
    print(
        f"  {Fore.MAGENTA}Capital: ${status['capital']:,.2f}  "
        f"|  Day P&L: ${status['daily_pnl']:+,.2f} ({status['daily_pnl_pct']:+.2f}%)  "
        f"|  Positions: {len(status['open_positions'])}/{status.get('max', 3)}  "
        f"|  Mode: {TRADE_MODE}{Style.RESET_ALL}"
    )

    if status["daily_loss_locked"]:
        print(f"  {Fore.RED}⛔ DAILY LOSS CIRCUIT BREAKER TRIPPED — no trades today{Style.RESET_ALL}")
        return
    if status["drawdown_locked"]:
        print(f"  {Fore.RED}⛔ MAX DRAWDOWN BREACHED — trading halted{Style.RESET_ALL}")
        return

    snapshots = fetch_all(tickers)
    for snap in snapshots:
        signal = analyze(snap)
        if signal is None:
            continue

        _place_order_if_needed(signal)

        if should_alert(signal, MIN_ALERT_CONFIDENCE):
            display(signal)
        else:
            display_hold(signal)


def main() -> None:
    tickers = [t.strip().upper() for t in WATCHLIST if t.strip()]
    print(f"\n{Fore.CYAN}Stock Signal Agent started")
    print(f"Watching: {', '.join(tickers)}")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS}s  |  Trade mode: {TRADE_MODE}")
    print(f"Min alert confidence: {MIN_ALERT_CONFIDENCE}")
    print(f"Alerts logged to: alerts.log{Style.RESET_ALL}\n")

    while True:
        if not is_market_open():
            wait = seconds_until_market_open()
            hours, rem = divmod(wait, 3600)
            mins = rem // 60
            print(
                f"{Fore.YELLOW}[{datetime.now().strftime('%H:%M:%S')}] "
                f"Market closed. Next open in {hours}h {mins}m. Sleeping...{Style.RESET_ALL}"
            )
            sleep_chunk = min(wait, 600)
            time.sleep(sleep_chunk)
            continue

        try:
            run_scan(tickers)
        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}Agent stopped.{Style.RESET_ALL}")
            sys.exit(0)
        except Exception as e:
            print(f"{Fore.RED}[ERROR] {e}{Style.RESET_ALL}")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
