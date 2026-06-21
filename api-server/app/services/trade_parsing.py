"""Pure helpers for turning SnapTrade order payloads into report rows.

Kept free of FastAPI/DB/network imports so they can be unit-tested in
isolation. The weekly-trades endpoint composes these.
"""

import hashlib
from collections import defaultdict, deque
from datetime import datetime, timezone

# Each option contract controls this many shares; premiums are quoted per share.
OPTION_CONTRACT_MULTIPLIER = 100

# Quantities below this are treated as zero (float fill rounding).
_QTY_EPS = 1e-9


def _to_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_instrument_key(value) -> str | None:
    """Collapse a ticker / OCC option symbol into a stable matching key.

    SnapTrade renders OCC symbols with padding spaces (``"AAPL  260116C..."``)
    that vary by endpoint, so we strip all whitespace and upper-case.
    """
    if not isinstance(value, str):
        return None
    key = "".join(value.split()).upper()
    return key or None


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


def order_executed_timestamp(order: dict) -> str | None:
    """Best-effort full execution/placement timestamp, as a sortable string."""
    for key in (
        "time_executed",
        "executed_at",
        "filled_at",
        "time_placed",
        "created_at",
    ):
        value = order.get(key)
        if value:
            return str(value)
    return None


def order_executed_date(order: dict) -> str | None:
    """Best-effort YYYY-MM-DD date an order was executed/placed."""
    ts = order_executed_timestamp(order)
    return ts[:10] if ts else None


def parse_executed_datetime(value) -> datetime | None:
    """Parse a SnapTrade timestamp string into an aware datetime, or None.

    Used to store an order's executed_at for SQL window filtering.
    """
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    for candidate in (s, s[:10]):
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def order_dedup_key(order: dict) -> str:
    """Stable per-account key for upserting an order into the local cache.

    Prefers the broker's order id; falls back to a content hash so repeated
    syncs of the same fill collapse onto one row.
    """
    for field in ("brokerage_order_id", "id", "order_id"):
        value = order.get(field)
        if value:
            return str(value)[:255]
    basis = "|".join(
        str(order.get(f))
        for f in (
            "action",
            "side",
            "units",
            "total_quantity",
            "price",
            "execution_price",
        )
    )
    digest = hashlib.sha1(
        f"{basis}|{order_executed_timestamp(order)}".encode()
    ).hexdigest()
    return f"syn_{digest[:32]}"


def order_effect(order: dict) -> str | None:
    """Open/close intent of an order, when the broker reports it.

    Option orders carry it in the action (BUY_TO_OPEN / SELL_TO_CLOSE / ...);
    plain equity BUY/SELL has no effect.
    """
    raw = str(order.get("action") or order.get("side") or "").upper()
    if "OPEN" in raw:
        return "OPEN"
    if "CLOSE" in raw:
        return "CLOSE"
    return None


def parse_order(order: dict) -> dict | None:
    """Turn a single SnapTrade order dict into normalized trade fields.

    Returns a dict with keys: trade_date, symbol, description, action, units,
    price, amount, asset_type — or None if the order can't be parsed into a
    BUY/SELL with a usable date.
    """
    if not isinstance(order, dict):
        return None

    executed_at = order_executed_timestamp(order)
    if not executed_at:
        return None
    executed_date_str = executed_at[:10]

    action = classify_order_action(order)
    if action is None:
        return None

    contract = extract_option_contract(order)
    if contract is not None:
        asset_type = "OPTION"
        symbol, description = format_option_contract(contract)
        # Match option fills/holdings on the unique OCC contract symbol.
        occ = contract.get("ticker") or contract.get("raw_symbol")
        instrument_key = normalize_instrument_key(occ) or normalize_instrument_key(description)
    else:
        asset_type = "EQUITY"
        symbol, description = extract_order_symbol(order)
        instrument_key = normalize_instrument_key(symbol)

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
        "executed_at": executed_at,
        "symbol": symbol,
        "description": description,
        "action": action,
        "effect": order_effect(order),
        "units": units,
        "price": price,
        "amount": amount,
        "asset_type": asset_type,
        "instrument_key": instrument_key,
    }


def build_holdings_map(positions_payload) -> dict[str, dict]:
    """Map instrument_key -> {price, cost_per_share} from a positions payload.

    Handles SnapTrade's equity `positions`/`results` array and, when present,
    the `option_positions` array. Prices and cost basis are per share (option
    premiums are per-share too); callers apply the contract multiplier.
    """
    out: dict[str, dict] = {}
    if isinstance(positions_payload, dict):
        equity = positions_payload.get("results") or positions_payload.get("positions") or []
        options = positions_payload.get("option_positions") or []
    elif isinstance(positions_payload, list):
        equity, options = positions_payload, []
    else:
        return out

    for pos in equity:
        if not isinstance(pos, dict):
            continue
        instrument = pos.get("instrument") or {}
        ticker = instrument.get("symbol") or instrument.get("raw_symbol") or pos.get("symbol")
        if isinstance(ticker, dict):
            ticker = ticker.get("symbol") or ticker.get("raw_symbol")
        key = normalize_instrument_key(ticker)
        if not key:
            continue
        out[key] = {
            "price": _to_float(pos.get("price")),
            "cost_per_share": _to_float(
                pos.get("cost_basis") or pos.get("average_purchase_price")
            ),
        }

    for pos in options:
        if not isinstance(pos, dict):
            continue
        sym = pos.get("symbol")
        option_symbol = sym.get("option_symbol") if isinstance(sym, dict) else None
        option_symbol = option_symbol or pos.get("option_symbol") or {}
        occ = None
        if isinstance(option_symbol, dict):
            occ = option_symbol.get("ticker") or option_symbol.get("raw_symbol")
        key = normalize_instrument_key(occ)
        if not key:
            continue
        out[key] = {
            "price": _to_float(pos.get("price")),
            "cost_per_share": _to_float(
                pos.get("average_purchase_price") or pos.get("cost_basis")
            ),
        }

    return out


def _is_opening(trade: dict) -> bool:
    """Whether a fill opens a position (vs closes one).

    Uses the broker's explicit open/close effect when present; otherwise a
    BUY is treated as opening and a SELL as closing (long-biased default that
    matches typical equity activity).
    """
    effect = trade.get("effect")
    if effect == "OPEN":
        return True
    if effect == "CLOSE":
        return False
    return trade["action"] == "BUY"


def _trade_sort_key(trade: dict) -> tuple:
    # Order by execution time; on ties, opens before closes so a same-instant
    # round trip still matches.
    return (
        trade.get("executed_at") or trade.get("trade_date") or "",
        0 if _is_opening(trade) else 1,
    )


def summarize_trades(
    trades: list[dict], holdings: dict[str, dict] | None = None
) -> dict:
    """Match window trades into realized + unrealized P/L.

    Fills are processed in execution-time order. A signed FIFO inventory lets
    same-day round trips (including short option trades opened by selling)
    match regardless of the order SnapTrade returns them in:

    * Round-trips inside the window -> realized P/L from matched lots.
    * Open lots still held at window end -> unrealized vs current price
      (long: price-cost; short: cost-price).
    * Closes with no in-window opening fill (closed a pre-window position) ->
      realized against SnapTrade cost basis when available, else `needs_basis`.

    `holdings` maps instrument_key -> {price, cost_per_share} (per share).
    Returns totals plus a per-instrument breakdown.
    """
    holdings = holdings or {}

    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        key = t.get("instrument_key")
        if key:
            groups[key].append(t)

    by_instrument: list[dict] = []
    total_realized = 0.0
    total_unrealized = 0.0

    for key, items in groups.items():
        items_sorted = sorted(items, key=_trade_sort_key)
        mult = (
            OPTION_CONTRACT_MULTIPLIER
            if items_sorted[0]["asset_type"] == "OPTION"
            else 1
        )
        holding = holdings.get(key) or {}
        current_price = holding.get("price")
        cost_per_share = holding.get("cost_per_share")

        # Lots carry a signed qty: positive = long, negative = short. At any
        # time all open lots share one sign (the current position side).
        position: deque[list[float]] = deque()  # [signed_qty, price]
        realized = 0.0
        buy_units = sell_units = 0.0
        needs_basis = False

        for t in items_sorted:
            is_buy = t["action"] == "BUY"
            q = _to_float(t.get("units")) or 0.0
            p = _to_float(t.get("price")) or 0.0
            if is_buy:
                buy_units += q
            else:
                sell_units += q

            remaining = q
            # Close opposing lots first (buy closes shorts; sell closes longs).
            while remaining > _QTY_EPS and position and (position[0][0] > 0) == (not is_buy):
                lot = position[0]
                matched = min(remaining, abs(lot[0]))
                if lot[0] > 0:          # closing a long by selling
                    realized += (p - lot[1]) * matched * mult
                    lot[0] -= matched
                else:                   # closing a short by buying
                    realized += (lot[1] - p) * matched * mult
                    lot[0] += matched
                remaining -= matched
                if abs(lot[0]) <= _QTY_EPS:
                    position.popleft()

            if remaining > _QTY_EPS:
                if _is_opening(t):
                    position.append([(remaining if is_buy else -remaining), p])
                elif cost_per_share is not None:
                    # Closed a position opened before the window.
                    realized += (
                        (p - cost_per_share) if not is_buy
                        else (cost_per_share - p)
                    ) * remaining * mult
                else:
                    needs_basis = True

        # Remaining open lots: mark to current price.
        net_units = sum(lot[0] for lot in position)
        unrealized = 0.0
        needs_price = False
        if abs(net_units) > _QTY_EPS:
            if current_price is not None:
                for lot in position:
                    if lot[0] > 0:
                        unrealized += (current_price - lot[1]) * lot[0] * mult
                    else:
                        unrealized += (lot[1] - current_price) * (-lot[0]) * mult
            else:
                needs_price = True

        if abs(net_units) <= _QTY_EPS:
            status = "closed"
        elif buy_units > _QTY_EPS and sell_units > _QTY_EPS:
            status = "partial"
        else:
            status = "open"

        total_realized += realized
        total_unrealized += unrealized
        sample = items_sorted[0]
        by_instrument.append(
            {
                "symbol": sample["symbol"],
                "description": sample["description"],
                "asset_type": sample["asset_type"],
                "buy_units": round(buy_units, 4),
                "sell_units": round(sell_units, 4),
                "realized_pnl": round(realized, 2),
                "unrealized_pnl": round(unrealized, 2),
                "net_units": round(net_units, 4),
                "status": status,
                "needs_basis": needs_basis,
                "needs_price": needs_price,
            }
        )

    by_instrument.sort(
        key=lambda x: x["realized_pnl"] + x["unrealized_pnl"], reverse=True
    )
    return {
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(total_unrealized, 2),
        "trading_pnl": round(total_realized + total_unrealized, 2),
        "by_instrument": by_instrument,
    }
