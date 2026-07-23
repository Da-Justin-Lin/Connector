"""
Multi-timeframe data fetcher.

For each ticker we compute indicators on three timeframes:
  - daily (trend & regime for the stock itself)
  - 1h (setup / retracement identification)
  - 15m (entry trigger)

The confluence engine uses these together — see analyzer.py.
"""

import yfinance as yf

from config import RS_LOOKBACK_DAYS
from indicators import compute_all


def _trailing_return(closes, lookback: int) -> float | None:
    """Simple lookback-day return (close/close_lookback_ago − 1) for RS vs SPY."""
    if len(closes) < lookback + 1:
        return None
    return round(float(closes.iloc[-1] / closes.iloc[-(lookback + 1)] - 1), 4)


def _safe_history(tk: yf.Ticker, period: str, interval: str):
    try:
        return tk.history(period=period, interval=interval)
    except Exception as e:
        print(f"[data_fetcher] history error {period}/{interval}: {e}")
        return None


def fetch_stock_snapshot(ticker: str) -> dict | None:
    try:
        tk = yf.Ticker(ticker)

        df_daily = _safe_history(tk, period="1y", interval="1d")
        df_1h = _safe_history(tk, period="1mo", interval="60m")
        df_15m = _safe_history(tk, period="5d", interval="15m")

        if df_daily is None or df_daily.empty:
            return None
        if df_1h is None or df_1h.empty:
            return None
        if df_15m is None or df_15m.empty:
            return None

        current_price = float(df_15m["Close"].iloc[-1])
        prev_close = (
            float(df_daily["Close"].iloc[-2])
            if len(df_daily) >= 2
            else current_price
        )
        day_change_pct = round((current_price - prev_close) / prev_close * 100, 2)

        daily_ind = compute_all(df_daily)
        # Trailing return for relative-strength gating vs SPY (see rules_engine).
        daily_ind["rs_return"] = _trailing_return(df_daily["Close"], RS_LOOKBACK_DAYS)

        return {
            "ticker": ticker,
            "price": round(current_price, 4),
            "prev_close": round(prev_close, 4),
            "day_change_pct": day_change_pct,
            "day_high": round(float(df_15m["High"].max()), 4),
            "day_low": round(float(df_15m["Low"].min()), 4),
            "daily": daily_ind,
            "hourly": compute_all(df_1h),
            "intraday": compute_all(df_15m),
        }
    except Exception as e:
        print(f"[data_fetcher] Error fetching {ticker}: {e}")
        return None


def fetch_all(tickers: list[str]) -> list[dict]:
    results = []
    for t in tickers:
        snap = fetch_stock_snapshot(t)
        if snap:
            results.append(snap)
    return results
