"""Diagnose why some brokerage accounts stopped updating.

For every account SnapTrade reports for our user, print:
  - the brokerage / account name
  - the connection (brokerage_authorization) status: disabled? last sync? error?
  - whether a live positions + balance fetch currently succeeds or throws

Then cross-check against the local DB: for each investment_account row show how
stale its cached holdings are (holdings_synced_at).

Run from the api-server dir with the venv active:
    python -m scripts.diagnose_connections
"""

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.investment_account import InvestmentAccount
from app.services.snaptrade_service import (
    fetch_account_balance,
    fetch_account_positions,
    list_accounts,
)


def _fmt_age(ts: datetime | None) -> str:
    if ts is None:
        return "never synced"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    mins = delta.total_seconds() / 60
    if mins < 60:
        return f"{mins:.0f} min ago"
    if mins < 60 * 24:
        return f"{mins / 60:.1f} h ago"
    return f"{mins / 60 / 24:.1f} days ago"


def _probe(account_id: str) -> tuple[str, str]:
    """Live-fetch positions + balance; return (positions_result, balance_result)."""
    try:
        fetch_account_positions(account_id)
        pos = "OK"
    except Exception as exc:
        pos = f"FAIL: {type(exc).__name__}: {exc}"
    try:
        fetch_account_balance(account_id)
        bal = "OK"
    except Exception as exc:
        bal = f"FAIL: {type(exc).__name__}: {exc}"
    return pos, bal


async def main() -> None:
    print("=" * 72)
    print("SnapTrade accounts reported for our user")
    print("=" * 72)

    try:
        accounts = list_accounts()
    except Exception as exc:
        print(f"list_accounts() failed entirely: {type(exc).__name__}: {exc}")
        return

    if not accounts:
        print("SnapTrade returned no accounts.")
        return

    for acct in accounts:
        acct_id = acct.get("id")
        name = acct.get("name") or "(no name)"
        institution = acct.get("institution_name")
        ba = acct.get("brokerage_authorization")

        print(f"\n▸ {institution or '?'} — {name}")
        print(f"    account_id : {acct_id}")

        if isinstance(ba, dict):
            # Surface the connection health fields SnapTrade exposes.
            print(f"    connection : id={ba.get('id')}")
            print(f"    disabled   : {ba.get('disabled')}")
            if ba.get("disabled_date"):
                print(f"    disabled_at: {ba.get('disabled_date')}")
            broker = ba.get("brokerage")
            if isinstance(broker, dict):
                print(f"    brokerage  : {broker.get('name') or broker.get('slug')}")
            # Some SnapTrade payloads nest a sync/meta status; dump anything useful.
            for key in ("type", "created_date", "updated_date"):
                if ba.get(key) is not None:
                    print(f"    {key:<11}: {ba.get(key)}")
        else:
            print(f"    connection : {ba!r}")

        # Also show sync_status if SnapTrade attached one at the account level.
        sync_status = acct.get("sync_status") or (acct.get("meta") or {}).get("sync_status")
        if sync_status:
            print(f"    sync_status: {json.dumps(sync_status, default=str)}")

        pos, bal = _probe(acct_id)
        print(f"    live fetch : positions={pos}")
        print(f"                 balance={bal}")

    print("\n" + "=" * 72)
    print("Local DB cache freshness (investment_accounts)")
    print("=" * 72)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(InvestmentAccount))
        ).scalars().all()
        if not rows:
            print("No investment_accounts rows.")
        for r in rows:
            print(
                f"\n▸ {r.institution_name or '?'} — {r.account_name or '(no name)'}"
                f"\n    account_id     : {r.snaptrade_account_id}"
                f"\n    holdings_synced: {_fmt_age(r.holdings_synced_at)}"
                f"\n    orders_synced  : {_fmt_age(r.orders_synced_at)}"
            )


if __name__ == "__main__":
    asyncio.run(main())
