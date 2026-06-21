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
    classify_order_action,
    extract_option_contract,
    extract_order_symbol,
    format_option_contract,
    order_executed_date,
    parse_order,
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
