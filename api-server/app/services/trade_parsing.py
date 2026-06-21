"""Pure helpers for turning SnapTrade order payloads into report rows.

Kept free of FastAPI/DB/network imports so they can be unit-tested in
isolation. The weekly-trades endpoint composes these.
"""

# Each option contract controls this many shares; premiums are quoted per share.
OPTION_CONTRACT_MULTIPLIER = 100


def extract_order_symbol(order: dict) -> tuple[str | None, str | None]:
    """SnapTrade equity order payloads have `universal_symbol` (preferred) or
    `symbol`. `universal_symbol.symbol` can itself be a dict on some versions.

    Returns (ticker, description).
    """
    container = order.get("universal_symbol") or order.get("symbol") or {}
    if isinstance(container, str):
        return container, None
    if not isinstance(container, dict):
        return None, None

    inner_symbol = container.get("symbol")
    description = container.get("description") or container.get("name")

    if isinstance(inner_symbol, dict):
        ticker = (
            inner_symbol.get("symbol")
            or inner_symbol.get("raw_symbol")
            or inner_symbol.get("ticker")
        )
        if not description:
            description = inner_symbol.get("description")
        return ticker, description

    if isinstance(inner_symbol, str):
        return inner_symbol, description

    # Fallback: top-level raw_symbol / ticker fields on the container
    ticker = container.get("raw_symbol") or container.get("ticker")
    return ticker, description


def extract_option_contract(order: dict) -> dict | None:
    """Return the option contract object for an option order, or None if equity.

    SnapTrade puts option details under `option_symbol` (preferred) or
    `universal_symbol_option`. Some versions nest it inside `symbol`.
    """
    candidate = order.get("option_symbol") or order.get("universal_symbol_option")
    if not candidate:
        inner = order.get("symbol")
        if isinstance(inner, dict):
            candidate = inner.get("option_symbol")
    return candidate if isinstance(candidate, dict) else None


def format_option_contract(contract: dict) -> tuple[str | None, str | None]:
    """Return (underlying_ticker, human-readable contract label).

    Label looks like 'AAPL $200 CALL 1/16/26'; falls back to the raw OCC
    ticker when structured fields are missing.
    """
    underlying = contract.get("underlying_symbol")
    ticker: str | None = None
    if isinstance(underlying, dict):
        ticker = (
            underlying.get("symbol")
            or underlying.get("raw_symbol")
            or underlying.get("ticker")
        )
    elif isinstance(underlying, str):
        ticker = underlying

    opt_type = str(contract.get("option_type") or "").upper()
    strike = contract.get("strike_price")
    expiry = contract.get("expiration_date")
    raw_ticker = contract.get("ticker") or contract.get("raw_symbol")

    if not ticker and isinstance(raw_ticker, str):
        # OCC symbols start with the underlying, e.g. "AAPL  260116C00200000".
        ticker = raw_ticker.split()[0] or None

    parts: list[str] = []
    if ticker:
        parts.append(ticker)
    if strike is not None:
        try:
            parts.append(f"${float(strike):g}")
        except (TypeError, ValueError):
            pass
    if opt_type in ("CALL", "PUT"):
        parts.append(opt_type)
    if isinstance(expiry, str) and len(expiry) >= 10:
        y, m, d = expiry[:10].split("-")
        parts.append(f"{int(m)}/{int(d)}/{y[2:]}")

    label = " ".join(parts) if parts else (
        raw_ticker if isinstance(raw_ticker, str) else None
    )
    return ticker, label


def classify_order_action(order: dict) -> str | None:
    """Map a SnapTrade order action/side onto BUY / SELL (or None)."""
    raw = str(order.get("action") or order.get("side") or "").upper()
    if "BUY" in raw:
        return "BUY"
    if "SELL" in raw:
        return "SELL"
    return None


def order_executed_date(order: dict) -> str | None:
    """Best-effort YYYY-MM-DD date an order was executed/placed."""
    for key in (
        "time_executed",
        "executed_at",
        "filled_at",
        "time_placed",
        "created_at",
    ):
        value = order.get(key)
        if value:
            return str(value)[:10]
    return None


def parse_order(order: dict) -> dict | None:
    """Turn a single SnapTrade order dict into normalized trade fields.

    Returns a dict with keys: trade_date, symbol, description, action, units,
    price, amount, asset_type — or None if the order can't be parsed into a
    BUY/SELL with a usable date.
    """
    if not isinstance(order, dict):
        return None

    executed_date_str = order_executed_date(order)
    if not executed_date_str:
        return None

    action = classify_order_action(order)
    if action is None:
        return None

    contract = extract_option_contract(order)
    if contract is not None:
        asset_type = "OPTION"
        symbol, description = format_option_contract(contract)
    else:
        asset_type = "EQUITY"
        symbol, description = extract_order_symbol(order)

    try:
        units = float(
            order.get("total_quantity")
            or order.get("filled_quantity")
            or order.get("units")
            or 0
        )
        price = float(
            order.get("execution_price")
            or order.get("filled_price")
            or order.get("price")
            or 0
        )
    except (TypeError, ValueError):
        return None

    multiplier = OPTION_CONTRACT_MULTIPLIER if asset_type == "OPTION" else 1
    amount = round(units * price * multiplier, 2)

    return {
        "trade_date": executed_date_str,
        "symbol": symbol,
        "description": description,
        "action": action,
        "units": units,
        "price": price,
        "amount": amount,
        "asset_type": asset_type,
    }
