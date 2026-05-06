from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.investment_account import InvestmentAccount
from app.models.user import User
from app.schemas.investment_account import (
    ExchangeTokenRequest,
    ExchangeTokenResponse,
    HoldingRead,
    HoldingsResponse,
    LinkTokenResponse,
)
from app.services.plaid_service import (
    create_link_token,
    exchange_public_token,
    fetch_holdings,
)

router = APIRouter()


@router.post("/link-token", response_model=LinkTokenResponse)
async def get_link_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        token = await create_link_token(str(current_user.id))
        return {"link_token": token}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Plaid error: {exc}") from exc


@router.post("/exchange-token", response_model=ExchangeTokenResponse)
async def exchange_token(
    body: ExchangeTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await exchange_public_token(body.public_token)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Plaid error: {exc}") from exc

    account = InvestmentAccount(
        user_id=current_user.id,
        plaid_item_id=result["item_id"],
        plaid_access_token=result["access_token"],
    )
    db.add(account)
    await db.commit()

    return ExchangeTokenResponse(item_id=result["item_id"])


@router.get("/holdings", response_model=HoldingsResponse)
async def get_holdings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    )
    accounts = rows.scalars().all()

    all_holdings: list[HoldingRead] = []

    for account in accounts:
        try:
            data = await fetch_holdings(account.plaid_access_token)
        except Exception:
            continue

        securities = {s.security_id: s for s in (data.securities or [])}
        account_map = {a.account_id: a for a in (data.accounts or [])}

        for h in data.holdings or []:
            sec = securities.get(h.security_id)
            acct = account_map.get(h.account_id)

            quantity = float(h.quantity or 0)
            price = float(h.institution_price or 0)
            cost = float(h.cost_basis) if h.cost_basis is not None else None

            all_holdings.append(
                HoldingRead(
                    ticker=getattr(sec, "ticker_symbol", None),
                    name=getattr(sec, "name", None),
                    security_type=str(getattr(sec, "type", None) or ""),
                    quantity=quantity,
                    institution_price=price,
                    market_value=round(quantity * price, 2),
                    cost_basis=cost,
                    account_name=getattr(acct, "name", None),
                    account_type=str(getattr(acct, "type", None) or ""),
                )
            )

    total = round(sum(h.market_value for h in all_holdings), 2)
    return HoldingsResponse(
        holdings=all_holdings,
        total_value=total,
        connected_accounts=len(accounts),
    )
