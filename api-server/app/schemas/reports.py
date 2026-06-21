from pydantic import BaseModel


class PortfolioReturns(BaseModel):
    current_value: float
    total_principal: float
    all_time_return: float          # dollars
    all_time_return_pct: float      # fraction (0.12 = +12%)
    day_change: float | None
    day_change_pct: float | None
    ytd_change: float | None
    ytd_change_pct: float | None
    stale: bool = False
    last_synced_at: str | None = None


class BenchmarkPoint(BaseModel):
    date: str
    value: float


class BenchmarkResponse(BaseModel):
    symbol: str
    range: str
    series: list[BenchmarkPoint]
    available: bool
    message: str | None = None


class TradeRow(BaseModel):
    trade_date: str
    symbol: str | None
    description: str | None
    action: str
    units: float
    price: float
    amount: float
    asset_type: str = "EQUITY"  # "EQUITY" or "OPTION"
    instrument_key: str | None = None  # groups fills of the same instrument


class InstrumentPnL(BaseModel):
    symbol: str | None
    description: str | None
    asset_type: str
    buy_units: float
    sell_units: float
    realized_pnl: float
    unrealized_pnl: float
    net_units: float          # quantity still open at window end
    status: str               # "closed" | "open" | "partial"
    needs_basis: bool = False  # pre-window sell with no SnapTrade cost basis
    needs_price: bool = False  # open lot we couldn't mark (no current price)


class WeeklyReportResponse(BaseModel):
    week_start: str
    week_end: str
    trades: list[TradeRow]
    total_buys: float
    total_sells: float
    net_cash_flow: float
    week_start_value: float | None
    week_end_value: float | None
    week_deposits: float
    week_pnl: float | None
    week_pnl_pct: float | None
    # Trade-matched P/L (realized round-trips + unrealized on open lots)
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    trading_pnl: float | None = None
    pnl_by_instrument: list[InstrumentPnL] = []
    available: bool
    message: str | None = None
    # Cache state: data is served from the local store; `stale` means a
    # background refresh is in flight and newer data may follow.
    stale: bool = False
    last_synced_at: str | None = None
