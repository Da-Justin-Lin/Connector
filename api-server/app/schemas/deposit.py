import uuid
from datetime import datetime

from pydantic import BaseModel


class DepositCreate(BaseModel):
    investment_account_id: uuid.UUID
    amount: float
    deposited_at: datetime
    note: str | None = None


class DepositRead(BaseModel):
    id: uuid.UUID
    investment_account_id: uuid.UUID
    amount: float
    deposited_at: datetime
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountPrincipal(BaseModel):
    investment_account_id: uuid.UUID
    snaptrade_account_id: str
    institution_name: str | None
    account_name: str | None
    total_principal: float


class DepositsResponse(BaseModel):
    deposits: list[DepositRead]
    total_principal: float
    per_account: list[AccountPrincipal]
