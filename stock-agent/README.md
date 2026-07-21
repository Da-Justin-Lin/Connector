# Stock Trading Agent

Multi-timeframe automated trading agent for US equities, integrated with Robinhood's
official **Agentic Trading MCP** for order execution.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ main.py — every N seconds during market hours                │
└──────────────────────────────────────────────────────────────┘
                             │
                             ▼
      ┌──────────────────────────────────────────┐
      │ 1. data_fetcher (yfinance)               │
      │    daily + 1h + 15m bars per ticker      │
      └──────────────────────────────────────────┘
                             │
                             ▼
      ┌──────────────────────────────────────────┐
      │ 2. market_regime (SPY + VIX)             │
      │    BULL / NEUTRAL / BEAR / PANIC         │
      │    hard gate: no longs in BEAR/PANIC     │
      └──────────────────────────────────────────┘
                             │
                             ▼
      ┌──────────────────────────────────────────┐
      │ 3. rules_engine (deterministic scoring)  │
      │    multi-timeframe confluence, 0–13 pts  │
      │    must clear MIN_SIGNAL_SCORE           │
      └──────────────────────────────────────────┘
                             │
                             ▼
      ┌──────────────────────────────────────────┐
      │ 4. risk_manager                          │
      │    position size (Kelly-lite, ATR stop)  │
      │    R:R ≥ 2:1, daily/DD circuit breakers  │
      └──────────────────────────────────────────┘
                             │
                             ▼
      ┌──────────────────────────────────────────┐
      │ 5. Claude LLM veto                       │
      │    reviews qualitative context           │
      │    can ONLY downgrade BUY → HOLD         │
      └──────────────────────────────────────────┘
                             │
                             ▼
      ┌────────────────────┬─────────────────────┐
      │ robinhood_broker   │ notifier            │
      │ (Agentic MCP)      │ (GChat / email)     │
      └────────────────────┴─────────────────────┘
```

## Trade modes

Set `TRADE_MODE` in `.env`:

| Mode | What it does |
|------|--------------|
| `SIGNAL_ONLY` | Never places orders. Only push notifications. **Start here for 2-4 weeks.** |
| `PREVIEW_APPROVAL` | Submits as preview; you tap approve in the Robinhood app. |
| `FULL_AUTO` | Executes without approval. **Only after backtest + paper validation.** |

## Getting started

### 1. Install

```bash
cd stock-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your keys
```

### 2. Get your keys

- **Anthropic**: https://console.anthropic.com
- **Robinhood Agentic**: Open Robinhood app → Agentic Trading tab →
  Connect an agent → Copy the access token → paste as `ROBINHOOD_ACCESS_TOKEN`

### 3. Backtest (mandatory before FULL_AUTO)

```bash
python backtest.py --train 2018-01-01:2022-12-31 --test 2023-01-01:2025-12-31
```

The strategy must clear these bars on the **test set**:
- Sharpe ratio ≥ 1.0
- Max drawdown ≤ 20%
- Profit factor ≥ 1.3

If it doesn't, tune `MIN_SIGNAL_SCORE`, `MIN_ADX_TRENDING`, or reject the strategy.

### 4. Run locally

```bash
python main.py
```

You'll get notifications, no orders placed (SIGNAL_ONLY mode).

### 5. Deploy to Railway

The project already has a `Procfile`. From your monorepo root:

```bash
railway login
railway link            # link to your existing Railway project
railway up --service stock-agent  # or create a new service
```

Set these environment variables in the Railway dashboard:

- `ANTHROPIC_API_KEY`
- `ROBINHOOD_ACCESS_TOKEN` (only if TRADE_MODE ≠ SIGNAL_ONLY)
- `GCHAT_WEBHOOK_URL` (highly recommended)
- `TRADE_MODE=SIGNAL_ONLY` (until you're ready)
- `ACCOUNT_CAPITAL=1000` (or your real number)

## Recommended rollout plan

1. **Week 1-2**: `SIGNAL_ONLY`. Watch the notifications. Get a feel for how many
   signals fire and whether they look reasonable. Zero risk.
2. **Week 3-4**: Run `backtest.py`. Iterate on parameters. Do not proceed unless
   the strategy passes the out-of-sample bar.
3. **Month 2-3**: `PREVIEW_APPROVAL`. Small capital ($500). You approve every trade.
4. **Month 4+**: `FULL_AUTO` — only after 30+ approved trades with real P&L
   matching backtest expectations.

## Position tracking (exit alerts)

Once you take a signal and buy on Robinhood, register the position so the
agent starts monitoring exit conditions:

```bash
python manage_positions.py add ORCL 0.7474 132.53 119.15 187.27
#                              ticker shares  entry  stop   target
```

Each scan cycle then checks every open position for:

| Alert | Trigger |
|-------|---------|
| `HARD_STOP` | Price ≤ current stop |
| `TARGET_HIT` | Price ≥ target |
| `TRAIL_RAISED` | Reached +1R/+2R/+3R — new suggested stop level |
| `THESIS_BROKEN` | Rules engine no longer says BUY for this ticker |
| `TIME_STOP` | Held ≥ 10 trading days with < 50% target progress |
| `REGIME_SHIFT` | Market flipped to BEAR/PANIC |

Other CLI commands:

```bash
python manage_positions.py list                # show all open
python manage_positions.py show ORCL           # detailed status + active alerts
python manage_positions.py close ORCL 145.20   # record exit
python manage_positions.py stop ORCL 133.00    # override current stop
```

On Railway, set `POSITIONS_JSON` env var to the JSON array of positions
(overrides the local file — same schema as `positions.json`).

## Safety rails baked in

- **Regime filter**: no new longs in BEAR/PANIC market
- **Daily circuit breaker**: −2% day → automatic halt
- **Max drawdown breaker**: 10% peak-to-trough → complete stop
- **Per-trade risk cap**: never risk more than 1% of capital per trade
- **Position cap**: no single stock > 20% of capital, max 3 concurrent positions
- **Robinhood-side isolation**: funds live in a dedicated Agentic sub-account —
  the agent cannot touch your main portfolio.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Loop and orchestration |
| `data_fetcher.py` | yfinance multi-timeframe pull |
| `indicators.py` | RSI, MACD, Bollinger, ATR, ADX |
| `market_regime.py` | SPY/VIX regime classifier |
| `rules_engine.py` | Deterministic signal scoring |
| `risk_manager.py` | Position sizing + circuit breakers, state in `risk_state.json` |
| `analyzer.py` | Regime → rules → risk → LLM veto pipeline |
| `robinhood_broker.py` | Robinhood Agentic MCP client |
| `positions.py` | Position tracking + 6 types of exit alerts |
| `manage_positions.py` | CLI to add/close/list/show positions |
| `notifier.py` | GChat + email push |
| `alerter.py` | Console output + log file |
| `backtest.py` | Historical simulation with metrics |
| `config.py` | All tunable knobs, env-driven |
