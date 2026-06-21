"""Unit tests for SnapTrade order -> trade-row parsing.

These exercise the pure helpers in app.services.trade_parsing, which have no
FastAPI/DB/network imports, so they run without app config or external deps.

Payload shapes below mirror SnapTrade's documented order schema for equities
and options. The key behaviours under test:
  * options carry their contract under `option_symbol`, not `universal_symbol`
  * option dollar amounts apply the 100-share contract multiplier
  * the human-readable contract label is built from structured fields, with an
    OCC-ticker fallback
"""

from app.services.trade_parsing import (
    build_holdings_map,
    classify_order_action,
    extract_option_contract,
    extract_order_symbol,
    format_option_contract,
    normalize_instrument_key,
    order_dedup_key,
    order_executed_date,
    parse_executed_datetime,
    parse_order,
    summarize_trades,
)


# --- Sample payloads -------------------------------------------------------

EQUITY_ORDER = {
    "action": "BUY",
    "state": "EXECUTED",
    "time_executed": "2026-06-18T14:30:00Z",
    "total_quantity": 10,
    "execution_price": 195.50,
    "universal_symbol": {
        "symbol": "AAPL",
        "description": "Apple Inc.",
    },
}

OPTION_ORDER = {
    "action": "BUY_TO_OPEN",
    "state": "EXECUTED",
    "time_executed": "2026-06-19T15:45:00Z",
    "total_quantity": 2,
    "execution_price": 3.25,
    "universal_symbol": None,
    "option_symbol": {
        "ticker": "AAPL  260116C00200000",
        "option_type": "CALL",
        "strike_price": 200,
        "expiration_date": "2026-01-16",
        "underlying_symbol": {"symbol": "AAPL", "description": "Apple Inc."},
    },
}

# Some SDK builds nest the contract under `symbol` and omit structured fields.
OPTION_ORDER_NESTED_RAW = {
    "side": "SELL_TO_CLOSE",
    "status": "FILLED",
    "filled_at": "2026-06-17T10:00:00Z",
    "filled_quantity": 1,
    "filled_price": 1.10,
    "symbol": {
        "option_symbol": {"ticker": "TSLA  260320P00150000"},
    },
}


# --- Equity ----------------------------------------------------------------

def test_equity_order_parses_with_no_multiplier():
    row = parse_order(EQUITY_ORDER)
    assert row is not None
    assert row["asset_type"] == "EQUITY"
    assert row["symbol"] == "AAPL"
    assert row["action"] == "BUY"
    assert row["units"] == 10
    assert row["price"] == 195.50
    # 10 shares * $195.50, no x100
    assert row["amount"] == 1955.00


def test_equity_order_is_not_detected_as_option():
    assert extract_option_contract(EQUITY_ORDER) is None


# --- Option ----------------------------------------------------------------

def test_option_order_applies_contract_multiplier():
    row = parse_order(OPTION_ORDER)
    assert row is not None
    assert row["asset_type"] == "OPTION"
    # 2 contracts * $3.25 * 100 shares/contract = $650, NOT $6.50
    assert row["amount"] == 650.00
    assert row["units"] == 2
    assert row["price"] == 3.25


def test_option_order_uses_underlying_ticker_and_builds_label():
    row = parse_order(OPTION_ORDER)
    assert row["symbol"] == "AAPL"
    assert row["description"] == "AAPL $200 CALL 1/16/26"


def test_option_action_to_open_close_maps_to_buy_sell():
    assert classify_order_action(OPTION_ORDER) == "BUY"
    assert classify_order_action(OPTION_ORDER_NESTED_RAW) == "SELL"


def test_option_contract_detected_when_nested_under_symbol():
    contract = extract_option_contract(OPTION_ORDER_NESTED_RAW)
    assert contract is not None
    assert contract["ticker"] == "TSLA  260320P00150000"


def test_option_label_falls_back_to_occ_ticker_underlying():
    # No structured strike/type/expiry -> ticker derived from OCC string head.
    ticker, label = format_option_contract({"ticker": "TSLA  260320P00150000"})
    assert ticker == "TSLA"
    assert label == "TSLA"


def test_nested_raw_option_order_full_parse():
    row = parse_order(OPTION_ORDER_NESTED_RAW)
    assert row is not None
    assert row["asset_type"] == "OPTION"
    assert row["symbol"] == "TSLA"
    assert row["action"] == "SELL"
    # 1 contract * $1.10 * 100 = $110
    assert row["amount"] == 110.00


# --- Edge cases ------------------------------------------------------------

def test_order_without_date_is_dropped():
    assert parse_order({"action": "BUY", "total_quantity": 1, "price": 5}) is None


def test_order_without_buy_or_sell_action_is_dropped():
    assert (
        parse_order(
            {"action": "DIVIDEND", "time_executed": "2026-06-18", "price": 5}
        )
        is None
    )


def test_non_dict_order_is_dropped():
    assert parse_order("not-an-order") is None  # type: ignore[arg-type]


def test_executed_date_truncates_to_yyyy_mm_dd():
    assert order_executed_date(OPTION_ORDER) == "2026-06-19"


def test_equity_symbol_extraction_handles_nested_symbol_dict():
    order = {
        "universal_symbol": {
            "symbol": {"symbol": "MSFT", "description": "Microsoft"},
        }
    }
    ticker, description = extract_order_symbol(order)
    assert ticker == "MSFT"
    assert description == "Microsoft"


# --- instrument keys -------------------------------------------------------

def test_normalize_key_strips_occ_padding_spaces():
    # Same contract, different padding across endpoints -> same key.
    assert normalize_instrument_key("AAPL  260116C00200000") == "AAPL260116C00200000"
    assert normalize_instrument_key("AAPL260116C00200000") == "AAPL260116C00200000"


def test_parse_order_sets_instrument_key():
    assert parse_order(EQUITY_ORDER)["instrument_key"] == "AAPL"
    assert parse_order(OPTION_ORDER)["instrument_key"] == "AAPL260116C00200000"


def test_parse_order_captures_timestamp_and_effect():
    eq = parse_order(EQUITY_ORDER)
    assert eq["executed_at"] == "2026-06-18T14:30:00Z"
    assert eq["effect"] is None  # plain BUY has no open/close intent

    op = parse_order(OPTION_ORDER)
    assert op["executed_at"] == "2026-06-19T15:45:00Z"
    assert op["effect"] == "OPEN"  # BUY_TO_OPEN

    assert parse_order(OPTION_ORDER_NESTED_RAW)["effect"] == "CLOSE"  # SELL_TO_CLOSE


# --- summarize_trades: realized round-trips --------------------------------

def _trade(
    key, action, units, price, asset_type="EQUITY", day="2026-06-18",
    ts=None, effect=None,
):
    return {
        "trade_date": day,
        "executed_at": ts or f"{day}T12:00:00Z",
        "symbol": key,
        "description": None,
        "action": action,
        "effect": effect,
        "units": units,
        "price": price,
        "asset_type": asset_type,
        "instrument_key": key,
    }


def test_equity_round_trip_realized():
    trades = [
        _trade("AAPL", "BUY", 10, 100, day="2026-06-16"),
        _trade("AAPL", "SELL", 10, 120, day="2026-06-18"),
    ]
    out = summarize_trades(trades)
    assert out["realized_pnl"] == 200.0  # 10 * (120 - 100)
    assert out["unrealized_pnl"] == 0.0
    assert out["by_instrument"][0]["status"] == "closed"


def test_option_round_trip_applies_multiplier():
    trades = [
        _trade("AAPL260116C00200000", "BUY", 2, 3.0, "OPTION", "2026-06-16"),
        _trade("AAPL260116C00200000", "SELL", 2, 5.0, "OPTION", "2026-06-18"),
    ]
    out = summarize_trades(trades)
    assert out["realized_pnl"] == 400.0  # 2 * (5 - 3) * 100


def test_same_day_option_daytrade_matches_regardless_of_input_order():
    # SnapTrade returns newest-first, so the closing SELL is listed before the
    # opening BUY even though it executed later. Time-ordering must still match
    # them into a realized round-trip (the bug this fixes).
    key = "AAPL260116C00200000"
    trades = [
        _trade(key, "SELL", 2, 5.0, "OPTION", ts="2026-06-18T15:30:00Z", effect="CLOSE"),
        _trade(key, "BUY", 2, 3.0, "OPTION", ts="2026-06-18T09:30:00Z", effect="OPEN"),
    ]
    out = summarize_trades(trades)
    inst = out["by_instrument"][0]
    assert inst["status"] == "closed"
    assert inst["needs_basis"] is False
    assert out["realized_pnl"] == 400.0  # 2 * (5 - 3) * 100
    assert out["unrealized_pnl"] == 0.0


def test_short_option_daytrade_sell_to_open_then_buy_to_close():
    # Sold premium to open, bought back cheaper to close — realized gain.
    key = "TSLA260320P00150000"
    trades = [
        _trade(key, "SELL", 1, 4.0, "OPTION", ts="2026-06-18T09:30:00Z", effect="OPEN"),
        _trade(key, "BUY", 1, 1.5, "OPTION", ts="2026-06-18T15:30:00Z", effect="CLOSE"),
    ]
    out = summarize_trades(trades)
    inst = out["by_instrument"][0]
    assert inst["status"] == "closed"
    assert out["realized_pnl"] == 250.0  # (4 - 1.5) * 1 * 100


def test_open_position_marked_to_current_price():
    trades = [_trade("AAPL", "BUY", 10, 100, day="2026-06-16")]
    out = summarize_trades(trades, {"AAPL": {"price": 110, "cost_per_share": 100}})
    inst = out["by_instrument"][0]
    assert out["realized_pnl"] == 0.0
    assert out["unrealized_pnl"] == 100.0  # 10 * (110 - 100)
    assert inst["status"] == "open"
    assert inst["net_units"] == 10


def test_partial_close_splits_realized_and_unrealized():
    trades = [
        _trade("AAPL", "BUY", 10, 100, day="2026-06-16"),
        _trade("AAPL", "SELL", 4, 120, day="2026-06-18"),
    ]
    out = summarize_trades(trades, {"AAPL": {"price": 110, "cost_per_share": 100}})
    inst = out["by_instrument"][0]
    assert inst["realized_pnl"] == 80.0     # 4 * (120 - 100)
    assert inst["unrealized_pnl"] == 60.0   # 6 * (110 - 100)
    assert inst["status"] == "partial"
    assert inst["net_units"] == 6


def test_prewindow_sell_uses_snaptrade_cost_basis():
    # Sold 5 with no in-window buy; basis comes from holdings.
    trades = [_trade("AAPL", "SELL", 5, 120, day="2026-06-18")]
    out = summarize_trades(trades, {"AAPL": {"price": 118, "cost_per_share": 90}})
    inst = out["by_instrument"][0]
    assert inst["realized_pnl"] == 150.0  # 5 * (120 - 90)
    assert inst["needs_basis"] is False


def test_prewindow_sell_without_basis_is_flagged():
    trades = [_trade("AAPL", "SELL", 5, 120, day="2026-06-18")]
    out = summarize_trades(trades, {})  # no holding -> no basis
    inst = out["by_instrument"][0]
    assert inst["realized_pnl"] == 0.0
    assert inst["needs_basis"] is True


def test_open_lot_without_price_is_flagged_not_marked():
    trades = [_trade("AAPL", "BUY", 10, 100, day="2026-06-16")]
    out = summarize_trades(trades, {})  # no current price
    inst = out["by_instrument"][0]
    assert inst["unrealized_pnl"] == 0.0
    assert inst["needs_price"] is True


def test_totals_aggregate_across_instruments():
    trades = [
        _trade("AAPL", "BUY", 10, 100, day="2026-06-16"),
        _trade("AAPL", "SELL", 10, 120, day="2026-06-18"),   # +200 realized
        _trade("MSFT", "BUY", 5, 200, day="2026-06-17"),     # open
    ]
    out = summarize_trades(trades, {"MSFT": {"price": 210, "cost_per_share": 200}})
    assert out["realized_pnl"] == 200.0
    assert out["unrealized_pnl"] == 50.0   # 5 * (210 - 200)
    assert out["trading_pnl"] == 250.0


# --- build_holdings_map ----------------------------------------------------

def test_build_holdings_map_equity_and_option():
    payload = {
        "results": [
            {
                "instrument": {"symbol": "AAPL"},
                "price": 110,
                "average_purchase_price": 100,
            }
        ],
        "option_positions": [
            {
                "symbol": {"option_symbol": {"ticker": "AAPL  260116C00200000"}},
                "price": 4.10,
                "average_purchase_price": 3.25,
            }
        ],
    }
    m = build_holdings_map(payload)
    assert m["AAPL"] == {"price": 110.0, "cost_per_share": 100.0}
    assert m["AAPL260116C00200000"] == {"price": 4.10, "cost_per_share": 3.25}


def test_build_holdings_map_tolerates_junk():
    assert build_holdings_map(None) == {}
    assert build_holdings_map({"results": ["bad", {"price": 1}]}) == {}


# --- cache helpers (order dedup key + executed_at parsing) ------------------

def test_order_dedup_key_prefers_broker_id():
    assert order_dedup_key({"brokerage_order_id": "abc123"}) == "abc123"
    assert order_dedup_key({"id": "xyz"}) == "xyz"


def test_order_dedup_key_is_stable_content_hash_without_id():
    order = {
        "action": "BUY",
        "units": 2,
        "execution_price": 3.25,
        "time_executed": "2026-06-19T15:45:00Z",
    }
    k1 = order_dedup_key(dict(order))
    k2 = order_dedup_key(dict(order))
    assert k1 == k2 and k1.startswith("syn_")
    # A different fill yields a different key.
    other = {**order, "units": 3}
    assert order_dedup_key(other) != k1


def test_parse_executed_datetime_handles_z_and_date_only():
    dt = parse_executed_datetime("2026-06-19T15:45:00Z")
    assert dt is not None and dt.tzinfo is not None
    assert dt.year == 2026 and dt.hour == 15

    date_only = parse_executed_datetime("2026-06-19")
    assert date_only is not None and date_only.tzinfo is not None

    assert parse_executed_datetime(None) is None
    assert parse_executed_datetime("garbage") is None
