import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.deposit import Deposit
from app.models.investment_account import InvestmentAccount
from app.models.user import User
from app.schemas.deposit import (
    AccountPrincipal,
    DepositCreate,
    DepositRead,
    DepositsResponse,
)

router = APIRouter()


@router.get("", response_model=DepositsResponse)
async def list_deposits(
    account_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Find which account UUIDs this user owns
    account_rows = await db.execute(
        select(InvestmentAccount).where(InvestmentAccount.user_id == current_user.id)
    )
    accounts = account_rows.scalars().all()
    accounts_by_uuid = {a.id: a for a in accounts}

    target_uuid: uuid.UUID | None = None
    if account_id:
        for a in accounts:
            if a.snaptrade_account_id == account_id:
                target_uuid = a.id
                break

    stmt = (
        select(Deposit)
        .where(Deposit.user_id == current_user.id)
        .order_by(Deposit.deposited_at.desc())
    )
    if target_uuid:
        stmt = stmt.where(Deposit.investment_account_id == target_uuid)

    deposit_rows = await db.execute(stmt)
    deposits = deposit_rows.scalars().all()

    per_account_totals: dict[uuid.UUID, float] = {}
    for d in deposits:
        per_account_totals[d.investment_account_id] = (
            per_account_totals.get(d.investment_account_id, 0.0) + float(d.amount)
        )

    per_account = []
    for uuid_, total in per_account_totals.items():
        acc = accounts_by_uuid.get(uuid_)
        if not acc:
            continue
        per_account.append(
            AccountPrincipal(
                investment_account_id=uuid_,
                snaptrade_account_id=acc.snaptrade_account_id,
                institution_name=acc.institution_name,
                account_name=acc.account_name,
                total_principal=round(total, 2),
            )
        )

    return DepositsResponse(
        deposits=[DepositRead.model_validate(d) for d in deposits],
        total_principal=round(sum(per_account_totals.values()), 2),
        per_account=per_account,
    )


@router.post("", response_model=DepositRead, status_code=201)
async def create_deposit(
    payload: DepositCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify the account belongs to this user
    account_row = await db.execute(
        select(InvestmentAccount).where(
            InvestmentAccount.id == payload.investment_account_id,
            InvestmentAccount.user_id == current_user.id,
        )
    )
    if account_row.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Account not found")

    deposit = Deposit(
        user_id=current_user.id,
        investment_account_id=payload.investment_account_id,
        amount=payload.amount,
        deposited_at=payload.deposited_at,
        note=payload.note,
    )
    db.add(deposit)
    await db.commit()
    await db.refresh(deposit)
    return DepositRead.model_validate(deposit)


@router.delete("/{deposit_id}", status_code=204)
async def delete_deposit(
    deposit_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(
        select(Deposit).where(
            Deposit.id == deposit_id,
            Deposit.user_id == current_user.id,
        )
    )
    deposit = row.scalar_one_or_none()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    await db.delete(deposit)
    await db.commit()
