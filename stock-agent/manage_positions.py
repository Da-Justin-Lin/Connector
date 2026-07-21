#!/usr/bin/env python3
"""
CLI for managing open positions.

  python manage_positions.py add ORCL 0.7474 132.53 119.15 187.27
  python manage_positions.py list
  python manage_positions.py show ORCL
  python manage_positions.py close ORCL 145.20
  python manage_positions.py stop ORCL 133.00      # manually override current stop
"""

import argparse
import sys
from datetime import date

from positions import (
    Position,
    load_positions,
    save_positions,
    evaluate_position,
    _fetch_since_entry,
    compute_trailing_stop,
)


def cmd_add(args):
    positions = load_positions()
    if any(p.ticker == args.ticker for p in positions):
        print(f"❌ Already have an open position in {args.ticker}. Close it first.")
        sys.exit(1)
    if args.stop >= args.entry:
        print(f"❌ Stop (${args.stop}) must be BELOW entry (${args.entry}) for a long.")
        sys.exit(1)
    if args.target <= args.entry:
        print(f"❌ Target (${args.target}) must be ABOVE entry (${args.entry}) for a long.")
        sys.exit(1)

    pos = Position(
        ticker=args.ticker.upper(),
        shares=args.shares,
        entry_price=args.entry,
        entry_date=args.date or str(date.today()),
        initial_stop=args.stop,
        target=args.target,
        notes=args.notes or "",
    )
    positions.append(pos)
    save_positions(positions)

    R = pos.initial_risk_per_share
    reward = args.target - args.entry
    print(f"✅ Added {pos.ticker}")
    print(f"   {pos.shares} shares @ ${pos.entry_price}  =  ${pos.shares * pos.entry_price:.2f}")
    print(f"   Stop:   ${pos.initial_stop}  (risk ${R:.2f}/share, ${pos.initial_risk_dollars:.2f} total)")
    print(f"   Target: ${pos.target}  (reward ${reward:.2f}/share, R:R = {reward/R:.2f})")
    print(f"   Entered {pos.entry_date}")


def cmd_close(args):
    positions = load_positions()
    match = [p for p in positions if p.ticker == args.ticker.upper()]
    if not match:
        print(f"❌ No open position in {args.ticker}")
        sys.exit(1)
    pos = match[0]
    pnl = (args.exit_price - pos.entry_price) * pos.shares
    pnl_pct = pnl / (pos.entry_price * pos.shares) * 100
    R_multiple = (args.exit_price - pos.entry_price) / pos.initial_risk_per_share

    remaining = [p for p in positions if p.ticker != args.ticker.upper()]
    save_positions(remaining)

    print(f"✅ Closed {pos.ticker}")
    print(f"   Entry ${pos.entry_price}  →  Exit ${args.exit_price}")
    print(f"   P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%)  |  {R_multiple:+.2f}R")


def cmd_stop(args):
    positions = load_positions()
    for p in positions:
        if p.ticker == args.ticker.upper():
            if args.new_stop >= p.entry_price and args.new_stop < p.entry_price + p.initial_risk_per_share:
                # Allowed to move to breakeven or below entry+1R
                pass
            elif args.new_stop < p.initial_stop:
                print(f"❌ Refusing to LOWER stop from ${p.initial_stop} to ${args.new_stop}. "
                      f"Stops should only move up.")
                sys.exit(1)
            p.initial_stop = args.new_stop
            save_positions(positions)
            print(f"✅ {p.ticker} stop set to ${args.new_stop}")
            return
    print(f"❌ No open position in {args.ticker}")
    sys.exit(1)


def cmd_list(_args):
    positions = load_positions()
    if not positions:
        print("(No open positions)")
        return

    print(f"{'TICKER':<8} {'SHARES':<10} {'ENTRY':<10} {'STOP':<10} {'TARGET':<10} {'ENTERED':<12} {'NOTES':<30}")
    for p in positions:
        shares_str = f"{p.shares:.4f}".rstrip("0").rstrip(".")
        print(f"{p.ticker:<8} {shares_str:<10} ${p.entry_price:<9.2f} ${p.initial_stop:<9.2f} "
              f"${p.target:<9.2f} {p.entry_date:<12} {p.notes[:30]:<30}")


def cmd_show(args):
    positions = load_positions()
    match = [p for p in positions if p.ticker == args.ticker.upper()]
    if not match:
        print(f"❌ No open position in {args.ticker}")
        sys.exit(1)
    pos = match[0]

    current, highest, days = _fetch_since_entry(pos.ticker, pos.entry_date)
    stop, milestone = compute_trailing_stop(pos, highest)
    pnl = (current - pos.entry_price) * pos.shares
    pnl_pct = pnl / (pos.entry_price * pos.shares) * 100
    R_now = (current - pos.entry_price) / pos.initial_risk_per_share
    R_high = (highest - pos.entry_price) / pos.initial_risk_per_share

    print(f"\n=== {pos.ticker} ===")
    print(f"  Position:        {pos.shares} shares @ ${pos.entry_price}  (entered {pos.entry_date}, {days} trading days ago)")
    print(f"  Current price:   ${current:.2f}  ({R_now:+.2f}R)")
    print(f"  Highest since:   ${highest:.2f}  ({R_high:+.2f}R)")
    print(f"  P&L:             ${pnl:+.2f}  ({pnl_pct:+.2f}%)")
    print(f"  Initial stop:    ${pos.initial_stop}")
    print(f"  Current stop:    ${stop}  {'← ' + milestone if milestone else '(unchanged)'}")
    print(f"  Target:          ${pos.target}  ({(pos.target - pos.entry_price) / pos.initial_risk_per_share:.2f}R)")

    print(f"\n=== Active alerts ===")
    alerts = evaluate_position(pos)
    if not alerts:
        print("  (none — position is healthy)")
    for a in alerts:
        print(f"  [{a.urgency}] {a.alert_type}: {a.message}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a new position")
    p_add.add_argument("ticker")
    p_add.add_argument("shares", type=float)
    p_add.add_argument("entry", type=float, help="Entry price")
    p_add.add_argument("stop", type=float, help="Initial stop-loss price")
    p_add.add_argument("target", type=float, help="Target/take-profit price")
    p_add.add_argument("--date", help="Entry date (default: today)")
    p_add.add_argument("--notes", default="")
    p_add.set_defaults(func=cmd_add)

    p_close = sub.add_parser("close", help="Close an open position")
    p_close.add_argument("ticker")
    p_close.add_argument("exit_price", type=float)
    p_close.set_defaults(func=cmd_close)

    p_stop = sub.add_parser("stop", help="Manually update the stop-loss")
    p_stop.add_argument("ticker")
    p_stop.add_argument("new_stop", type=float)
    p_stop.set_defaults(func=cmd_stop)

    p_list = sub.add_parser("list", help="List open positions")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show a position's live status + alerts")
    p_show.add_argument("ticker")
    p_show.set_defaults(func=cmd_show)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
