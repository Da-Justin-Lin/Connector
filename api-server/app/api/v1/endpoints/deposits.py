import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.deposit import Deposit
from app.models.user import User
from app.schemas.deposit import DepositCreate, DepositRead, DepositsResponse

router = APIRouter()


@router.get("", response_model=DepositsResponse)
async def list_deposits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(Deposit)
        .where(Deposit.user_id == current_user.id)
        .order_by(Deposit.deposited_at.desc())
    )
    deposits = rows.scalars().all()
    total = round(sum(float(d.amount) for d in deposits), 2)
    return DepositsResponse(
        deposits=[DepositRead.model_validate(d) for d in deposits],
        total_principal=total,
    )


@router.post("", response_model=DepositRead, status_code=201)
async def create_deposit(
    payload: DepositCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deposit = Deposit(
        user_id=current_user.id,
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
