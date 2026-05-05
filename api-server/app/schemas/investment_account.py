import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class InvestmentAccountRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    plaid_item_id: str
    institution_name: str | None
    account_name: str | None
    account_type: str | None
    current_balance: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeTokenRequest(BaseModel):
    public_token: str


class ExchangeTokenResponse(BaseModel):
    access_token: str
    item_id: str
