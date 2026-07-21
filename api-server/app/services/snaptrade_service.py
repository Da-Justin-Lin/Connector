import asyncio
from functools import lru_cache

from snaptrade_client import SnapTrade

from app.core.config import settings


@lru_cache(maxsize=1)
def _client() -> SnapTrade:
    return SnapTrade(
        consumer_key=settings.snaptrade_consumer_key,
        client_id=settings.snaptrade_client_id,
    )


def _creds() -> tuple[str, str]:
    return settings.snaptrade_user_id, settings.snaptrade_user_secret


def create_connection_portal_url() -> str:
    """Generate a one-time Connection Portal URL to link a brokerage."""
    user_id, user_secret = _creds()
    response = _client().authentication.login_snap_trade_user(
        user_id=user_id,
        user_secret=user_secret,
    )
    return response.body["redirectURI"]


def create_reconnect_portal_url(authorization_id: str) -> str:
    """One-time Connection Portal URL that RE-AUTHORIZES an existing connection.

    Passing `reconnect=<authorization_id>` repairs a disabled connection in place
    instead of creating a new (duplicate) one. Use this when a brokerage session
    has expired and SnapTrade marked the authorization disabled.
    """
    user_id, user_secret = _creds()
    response = _client().authentication.login_snap_trade_user(
        user_id=user_id,
        user_secret=user_secret,
        reconnect=authorization_id,
    )
    return response.body["redirectURI"]


def list_brokerage_authorizations() -> list[dict]:
    """List every brokerage connection, including its `disabled` status."""
    user_id, user_secret = _creds()
    response = _client().connections.list_brokerage_authorizations(
        user_id=user_id,
        user_secret=user_secret,
    )
    return list(response.body or [])


def list_accounts() -> list[dict]:
    """List every brokerage account connected by the SnapTrade user."""
    user_id, user_secret = _creds()
    response = _client().account_information.list_user_accounts(
        user_id=user_id,
        user_secret=user_secret,
    )
    return list(response.body or [])


def find_account_authorization(account_id: str) -> str | None:
    """Return the brokerage-authorization (connection) id for a given account,
    or None if SnapTrade no longer reports the account (already disconnected)."""
    for acct in list_accounts():
        if acct.get("id") != account_id:
            continue
        ba = acct.get("brokerage_authorization")
        if isinstance(ba, dict):
            return ba.get("id")
        if isinstance(ba, str):
            return ba
        return None
    return None


def remove_brokerage_authorization(authorization_id: str) -> None:
    """Permanently remove a brokerage connection from SnapTrade.

    After this the account stops appearing in `list_accounts()`, so a later
    sync won't re-create it. Note: every account under this authorization is
    disconnected together.
    """
    user_id, user_secret = _creds()
    _client().connections.remove_brokerage_authorization(
        authorization_id=authorization_id,
        user_id=user_id,
        user_secret=user_secret,
    )


def fetch_account_positions(account_id: str) -> dict:
    """Fetch positions (holdings + cash) for a single brokerage account."""
    user_id, user_secret = _creds()
    response = _client().account_information.get_all_account_positions(
        user_id=user_id,
        user_secret=user_secret,
        account_id=account_id,
    )
    return response.body


def fetch_account_balance(account_id: str) -> dict | list:
    """Fetch cash + buying power per currency for a single brokerage account."""
    user_id, user_secret = _creds()
    response = _client().account_information.get_user_account_balance(
        user_id=user_id,
        user_secret=user_secret,
        account_id=account_id,
    )
    return response.body


def fetch_balance_history(account_id: str) -> dict | list:
    """Fetch daily account value over the past (up to 1y).

    This endpoint is experimental in SnapTrade and disabled by default;
    callers must tolerate 403/404 from SnapTrade. Returns empty list if so.
    """
    user_id, user_secret = _creds()
    response = _client().account_information.get_account_balance_history(
        user_id=user_id,
        user_secret=user_secret,
        account_id=account_id,
    )
    return response.body


def fetch_return_rates(account_id: str, timeframes: str = "ALL,1Y,YTD,1M,1W,1D") -> dict:
    """Fetch rate-of-return percentages over the given timeframes."""
    user_id, user_secret = _creds()
    response = _client().account_information.get_user_account_return_rates(
        user_id=user_id,
        user_secret=user_secret,
        account_id=account_id,
        timeframes=timeframes,
    )
    return response.body


def fetch_account_orders(account_id: str, state: str | None = None, days: int | None = None) -> list:
    """Fetch recent orders for a single brokerage account.

    `state` filters to e.g. EXECUTED / FILLED / CANCELLED; omit to get all.
    `days` is a lookback window the SDK supports for limiting results.
    """
    user_id, user_secret = _creds()
    kwargs = {
        "user_id": user_id,
        "user_secret": user_secret,
        "account_id": account_id,
    }
    if state:
        kwargs["state"] = state
    if days is not None:
        kwargs["days"] = days

    try:
        response = _client().account_information.get_user_account_orders(**kwargs)
    except TypeError:
        # Some SDK builds dropped `state`/`days` — try minimal kwargs.
        response = _client().account_information.get_user_account_orders(
            user_id=user_id,
            user_secret=user_secret,
            account_id=account_id,
        )

    body = response.body
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        return body.get("results") or body.get("orders") or []
    return []


async def fetch_account_orders_async(
    account_id: str, state: str | None = None, days: int | None = None
) -> list:
    """Async wrapper: run the blocking orders call in a worker thread.

    The SnapTrade SDK is synchronous; calling it directly in an async handler
    blocks the event loop. Offloading lets callers `gather` across accounts.
    """
    return await asyncio.to_thread(fetch_account_orders, account_id, state, days)


async def fetch_account_positions_async(account_id: str) -> dict:
    """Async wrapper: run the blocking positions call in a worker thread."""
    return await asyncio.to_thread(fetch_account_positions, account_id)


async def fetch_account_balance_async(account_id: str) -> dict | list:
    """Async wrapper: run the blocking balance call in a worker thread."""
    return await asyncio.to_thread(fetch_account_balance, account_id)


async def fetch_balance_history_async(account_id: str) -> dict | list:
    """Async wrapper: run the blocking balance-history call in a worker thread."""
    return await asyncio.to_thread(fetch_balance_history, account_id)


def fetch_activities(start_date: str, end_date: str, account_ids: list[str] | None = None) -> list:
    """Fetch trade/dividend/fee activities across the given date window.

    Dates are inclusive YYYY-MM-DD strings. SnapTrade returns a flat list of
    activity entries; callers can filter by type/symbol.

    The SDK has shifted parameter names between versions (`accounts` vs
    `account_id`/`account_ids`, and `start_date` vs `startDate`); we try a
    few shapes and raise the first non-recoverable error.
    """
    user_id, user_secret = _creds()
    client = _client()

    base = {
        "user_id": user_id,
        "user_secret": user_secret,
        "start_date": start_date,
        "end_date": end_date,
    }

    # Try shapes in order: with comma-joined accounts, with list accounts,
    # without accounts filter at all.
    attempts: list[dict] = []
    if account_ids:
        attempts.append({**base, "accounts": ",".join(account_ids)})
        attempts.append({**base, "accounts": list(account_ids)})
    attempts.append(base)

    last_exc: Exception | None = None
    for kwargs in attempts:
        try:
            response = client.transactions_and_reporting.get_activities(**kwargs)
            body = response.body
            if isinstance(body, list):
                return body
            if isinstance(body, dict):
                return body.get("results") or body.get("activities") or []
            return []
        except TypeError as exc:
            # Almost certainly a wrong kwarg name — try the next shape.
            last_exc = exc
            continue
        except Exception as exc:
            # Real API error — bubble up.
            raise exc

    if last_exc:
        raise last_exc
    return []
