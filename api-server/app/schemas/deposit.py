import uuid
from datetime import datetime

from pydantic import BaseModel


class DepositCreate(BaseModel):
    amount: float
    deposited_at: datetime
    note: str | None = None


class DepositRead(BaseModel):
    id: uuid.UUID
    amount: float
    deposited_at: datetime
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DepositsResponse(BaseModel):
    deposits: list[DepositRead]
    total_principal: float
