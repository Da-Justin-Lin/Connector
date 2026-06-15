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
    available: bool
    message: str | None = None
