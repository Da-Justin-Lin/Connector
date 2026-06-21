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
    # Served from the local cache; `stale` means a background refresh is running.
    stale: bool = False
    last_synced_at: str | None = None


class HistoryPoint(BaseModel):
    date: str
    total_value: float


class HistoryResponse(BaseModel):
    series: list[HistoryPoint]
    available: bool
    message: str | None = None


class ReturnsResponse(BaseModel):
    # Map of timeframe code (e.g. "YTD", "1Y", "1M") -> rate as a fraction (0.12 = +12%)
    rates: dict[str, float]
    available: bool
    message: str | None = None


class PositionTrade(BaseModel):
    trade_date: str
    action: str  # BUY / SELL
    units: float
    price: float
    amount: float
    asset_type: str
    description: str | None = None


class PositionDetailResponse(BaseModel):
    symbol: str
    name: str | None = None
    held: bool
    quantity: float
    avg_cost: float | None = None
    cost_basis: float | None = None
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    accounts: int = 0
    trades: list[PositionTrade] = []
