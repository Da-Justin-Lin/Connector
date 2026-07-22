"""
Central configuration.

All knobs live here. To adjust the strategy without touching code, override
via environment variables (see .env.example).
"""

import os


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


# ---------- Universe ----------
# 25-ticker basket balancing mega-cap tech, mid-vol growth, cybersecurity,
# fintech, and one healthcare blue-chip for defensiveness.
# Avoids meme-level volatility (no GME/AMC-style).
MAG7 = ["AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "NVDA"]
GROWTH_TECH = ["AMD", "AVGO", "MU", "ORCL", "CRM", "NOW", "PLTR", "SNOW", "NFLX"]
CYBERSEC = ["PANW", "CRWD"]
FINTECH_NEW = ["COIN", "HOOD", "CRCL"]
CONSUMER_NEW = ["SHOP", "UBER", "ABNB"]
DEFENSIVE = ["UNH"]
DEFAULT_WATCHLIST = MAG7 + GROWTH_TECH + CYBERSEC + FINTECH_NEW + CONSUMER_NEW + DEFENSIVE
WATCHLIST = os.environ.get("WATCHLIST", ",".join(DEFAULT_WATCHLIST)).split(",")

# ---------- Loop cadence ----------
CHECK_INTERVAL_SECONDS = _env_int("CHECK_INTERVAL_SECONDS", 300)

# ---------- Signal thresholds ----------
RSI_OVERSOLD = _env_int("RSI_OVERSOLD", 30)
RSI_OVERBOUGHT = _env_int("RSI_OVERBOUGHT", 70)
MIN_VOLUME_RATIO = _env_float("MIN_VOLUME_RATIO", 1.5)   # 15m volume vs 20-bar avg
MIN_ADX_TRENDING = _env_int("MIN_ADX_TRENDING", 20)
MIN_SIGNAL_SCORE = _env_int("MIN_SIGNAL_SCORE", 5)       # out of 13 (backtested sweet spot)
MIN_ALERT_CONFIDENCE = os.environ.get("MIN_ALERT_CONFIDENCE", "MEDIUM")

# ---------- Risk management ----------
ACCOUNT_CAPITAL = _env_float("ACCOUNT_CAPITAL", 1000.0)  # your Robinhood sub-account
# Exposure tuned by the 2018-2025 sweep (sweep_exposure.py): 3% risk/trade beats
# buy-and-hold QQQ on absolute return (+163% vs +138% OOS) while holding max
# drawdown to ~half the index (-11% vs SPY -18.8% / QQQ -22.8%). To reproduce
# the sweep's diversification live, the concurrent-position cap is raised to 6
# and the single-stock cap to 35% (both were binding at 3% risk).
MAX_RISK_PER_TRADE_PCT = _env_float("MAX_RISK_PER_TRADE_PCT", 0.03)  # 3%
MAX_POSITION_PCT = _env_float("MAX_POSITION_PCT", 0.35)              # single stock max 35%
MAX_DAILY_LOSS_PCT = _env_float("MAX_DAILY_LOSS_PCT", 0.02)          # 2% → stop day
MAX_DRAWDOWN_PCT = _env_float("MAX_DRAWDOWN_PCT", 0.10)              # 10% → stop trading
MIN_RISK_REWARD_RATIO = _env_float("MIN_RISK_REWARD_RATIO", 2.0)     # R:R ≥ 2:1
MAX_OPEN_POSITIONS = _env_int("MAX_OPEN_POSITIONS", 6)
ATR_STOP_MULTIPLIER = _env_float("ATR_STOP_MULTIPLIER", 2.0)         # stop = entry - 2×ATR

# Cap targets to keep short-swing trades snappy.
# Bollinger upper band can be 5-8R away, which turns a 3-day trade into 3-week.
MAX_TARGET_R_MULTIPLE = _env_float("MAX_TARGET_R_MULTIPLE", 3.0)

# Trailing stop: continuous Chandelier — highest high since entry − k×ATR(period),
# ratcheting up only (a stop never loosens). Replaced the discrete R-multiple
# milestone ladder after a 2018-2025 backtest (config "C"): swapping the ladder for
# k=3 ATR trailing, keeping the same +3R target and 4-day time stop, lifted OOS
# Sharpe 1.96→2.01 and return 168.8%→179.6% and improved the in-sample split too,
# at the same drawdown. Unlike a fixed R ladder it tightens as volatility contracts
# and gives room back as it expands.
CHANDELIER_ATR_MULT = _env_float("CHANDELIER_ATR_MULT", 3.0)
CHANDELIER_ATR_PERIOD = _env_int("CHANDELIER_ATR_PERIOD", 14)

# Force-close a position after this many trading days if it isn't making progress.
# Cut 6 → 4 to match the faster EMA20/50 backbone: backtested avg hold is ~3.7
# days, so 4 lets winners breathe one extra bar while still recycling capital
# fast for the next rotation (EMA20/50 + 4d gave the best OOS Sharpe, 2.11).
TIME_STOP_DAYS = _env_int("TIME_STOP_DAYS", 4)

# Robinhood supports fractional shares to 4 decimals; essential for small accounts
# trading $300+ stocks (NVDA, PANW, etc.) where a whole share exceeds the risk cap.
ALLOW_FRACTIONAL_SHARES = os.environ.get("ALLOW_FRACTIONAL_SHARES", "true").lower() == "true"
MIN_FRACTIONAL_SHARES = _env_float("MIN_FRACTIONAL_SHARES", 0.01)

# ---------- Broker (Robinhood Agentic Trading MCP) ----------
TRADE_MODE = os.environ.get("TRADE_MODE", "SIGNAL_ONLY").upper()
# Valid: SIGNAL_ONLY | PREVIEW_APPROVAL | FULL_AUTO
_VALID_MODES = {"SIGNAL_ONLY", "PREVIEW_APPROVAL", "FULL_AUTO"}
if TRADE_MODE not in _VALID_MODES:
    raise ValueError(f"TRADE_MODE={TRADE_MODE!r} must be one of {_VALID_MODES}")

ROBINHOOD_MCP_URL = os.environ.get(
    "ROBINHOOD_MCP_URL", "https://agent.robinhood.com/mcp/trading"
)
