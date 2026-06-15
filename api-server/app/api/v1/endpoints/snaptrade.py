from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.investment_account import InvestmentAccount
from app.models.user import User
from app.schemas.investment_account import (
    AccountSection,
    ConnectionUrlResponse,
    HoldingRead,
    HoldingsResponse,
    SyncAccountsResponse,
)
from app.services.snaptrade_service import (
    create_connection_portal_url,
    fetch_account_balance,
    fetch_account_positions,
    list_accounts,
)

router = APIRouter()


@router.post("/connection-url", response_model=ConnectionUrlResponse)
async def get_connection_url(
    current_user: User = Depends(get_current_user),
):
    try:
        url = create_connection_portal_url()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SnapTrade error: {exc}") from exc
    return ConnectionUrlResponse(redirect_uri=url)


@router.post("/sync-accounts", response_model=SyncAccountsResponse)
async def sync_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        remote_accounts = list_accounts()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SnapTrade error: {exc}") from exc

    existing_rows = await db.execute(
        select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    )
    existing_by_id = {
        a.snaptrade_account_id: a for a in existing_rows.scalars().all()
    }

    synced = 0
    for acct in remote_accounts:
        snap_id = acct.get("id")
        if not snap_id:
            continue

        institution = acct.get("institution_name") or acct.get("brokerage_authorization")
        name = acct.get("name")
        meta = acct.get("meta") or {}
        account_type = acct.get("raw_type") or meta.get("type")
        account_number = acct.get("number")

        row = existing_by_id.get(snap_id)
        if row:
            row.institution_name = institution if isinstance(institution, str) else row.institution_name
            row.account_name = name
            row.account_type = account_type
            row.account_number = account_number
        else:
            db.add(
                InvestmentAccount(
                    user_id=current_user.id,
                    snaptrade_account_id=snap_id,
                    institution_name=institution if isinstance(institution, str) else None,
                    account_name=name,
                    account_type=account_type,
                    account_number=account_number,
                )
            )
        synced += 1

    await db.commit()
    return SyncAccountsResponse(accounts_synced=synced)


def _extract_cash(balance_payload: dict | list) -> float:
    """SnapTrade balance responses come as either a list of currency entries
    (one per currency) or a dict with the same. Sum the USD-equivalent cash."""
    entries: list = []
    if isinstance(balance_payload, list):
        entries = balance_payload
    elif isinstance(balance_payload, dict):
        entries = balance_payload.get("results") or balance_payload.get("balances") or []

    total = 0.0
    for entry in entries:
        cash = entry.get("cash") if isinstance(entry, dict) else None
        if cash is None:
            continue
        try:
            total += float(cash)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


@router.get("/holdings", response_model=HoldingsResponse)
async def get_holdings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account_rows = await db.execute(
        select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    )
    accounts = account_rows.scalars().all()

    if not accounts:
        return HoldingsResponse(
            accounts=[], total_value=0.0, total_cash=0.0, connected_accounts=0
        )

    sections: list[AccountSection] = []

    for account in accounts:
        holdings: list[HoldingRead] = []

        try:
            positions_payload = fetch_account_positions(account.snaptrade_account_id)
            positions = positions_payload.get("results") or positions_payload.get("positions") or []
        except Exception:
            positions = []

        for pos in positions:
            instrument = pos.get("instrument") or {}
            ticker = instrument.get("symbol") or instrument.get("raw_symbol")
            name = instrument.get("description")
            security_type = instrument.get("kind") or ""

            quantity = float(pos.get("units") or 0)
            price = float(pos.get("price") or 0)
            cost_per_share = pos.get("cost_basis") or pos.get("average_purchase_price")
            cost_basis = (
                round(float(cost_per_share) * quantity, 2)
                if cost_per_share is not None
                else None
            )

            holdings.append(
                HoldingRead(
                    ticker=ticker,
                    name=name,
                    security_type=str(security_type or ""),
                    quantity=quantity,
                    institution_price=price,
                    market_value=round(quantity * price, 2),
                    cost_basis=cost_basis,
                )
            )

        try:
            balance_payload = fetch_account_balance(account.snaptrade_account_id)
            cash = _extract_cash(balance_payload)
        except Exception:
            cash = 0.0

        holdings_value = round(sum(h.market_value for h in holdings), 2)
        sections.append(
            AccountSection(
                snaptrade_account_id=account.snaptrade_account_id,
                institution_name=account.institution_name,
                account_name=account.account_name,
                account_type=account.account_type,
                cash=cash,
                holdings_value=holdings_value,
                total_value=round(holdings_value + cash, 2),
                holdings=holdings,
            )
        )

    total_value = round(sum(s.total_value for s in sections), 2)
    total_cash = round(sum(s.cash for s in sections), 2)

    return HoldingsResponse(
        accounts=sections,
        total_value=total_value,
        total_cash=total_cash,
        connected_accounts=len(accounts),
    )
