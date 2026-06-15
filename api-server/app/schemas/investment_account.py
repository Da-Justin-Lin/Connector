import uuid
from datetime import datetime

from pydantic import BaseModel


class InvestmentAccountRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    snaptrade_account_id: str
    institution_name: str | None
    account_name: str | None
    account_type: str | None
    account_number: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConnectionUrlResponse(BaseModel):
    redirect_uri: str


class SyncAccountsResponse(BaseModel):
    accounts_synced: int


class HoldingRead(BaseModel):
    ticker: str | None
    name: str | None
    security_type: str | None
    quantity: float
    institution_price: float
    market_value: float
    cost_basis: float | None


class AccountSection(BaseModel):
    snaptrade_account_id: str
    institution_name: str | None
    account_name: str | None
    account_type: str | None
    cash: float
    holdings_value: float
    total_value: float
    holdings: list[HoldingRead]


class HoldingsResponse(BaseModel):
    accounts: list[AccountSection]
    total_value: float
    total_cash: float
    connected_accounts: int
