from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.investment_account import InvestmentAccount
from app.models.user import User
from app.schemas.investment_account import (
    ConnectionUrlResponse,
    HoldingRead,
    HoldingsResponse,
    SyncAccountsResponse,
)
from app.services.snaptrade_service import (
    create_connection_portal_url,
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
        return HoldingsResponse(holdings=[], total_value=0.0, connected_accounts=0)

    all_holdings: list[HoldingRead] = []

    for account in accounts:
        try:
            data = fetch_account_positions(account.snaptrade_account_id)
        except Exception:
            continue

        positions = data.get("results") or data.get("positions") or []
        for pos in positions:
            symbol = pos.get("symbol") or {}
            inner = symbol.get("symbol") or {}
            ticker = inner.get("symbol") or symbol.get("description")
            name = inner.get("description") or symbol.get("description")
            sec_type_obj = inner.get("type") or {}
            security_type = (
                sec_type_obj.get("description")
                or sec_type_obj.get("code")
                or ""
            )

            quantity = float(pos.get("units") or 0)
            price = float(pos.get("price") or 0)
            cost_raw = pos.get("average_purchase_price")
            cost_basis = (
                round(float(cost_raw) * quantity, 2) if cost_raw is not None else None
            )

            all_holdings.append(
                HoldingRead(
                    ticker=ticker,
                    name=name,
                    security_type=str(security_type or ""),
                    quantity=quantity,
                    institution_price=price,
                    market_value=round(quantity * price, 2),
                    cost_basis=cost_basis,
                    account_name=account.account_name,
                    account_type=account.account_type,
                )
            )

    total = round(sum(h.market_value for h in all_holdings), 2)
    return HoldingsResponse(
        holdings=all_holdings,
        total_value=total,
        connected_accounts=len(accounts),
    )
