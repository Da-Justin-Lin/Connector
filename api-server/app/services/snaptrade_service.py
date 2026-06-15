from functools import lru_cache

from snaptrade_client import SnapTrade

from app.core.config import settings


@lru_cache(maxsize=1)
def _client() -> SnapTrade:
    return SnapTrade(
        consumer_key=settings.snaptrade_consumer_key,
        client_id=settings.snaptrade_client_id,
    )


def register_user(internal_user_id: str) -> tuple[str, str]:
    """Register a new user with SnapTrade. Returns (snaptrade_user_id, user_secret)."""
    response = _client().authentication.register_snap_trade_user(
        user_id=internal_user_id,
    )
    body = response.body
    return body["userId"], body["userSecret"]


def create_connection_portal_url(snaptrade_user_id: str, user_secret: str) -> str:
    """Generate a one-time Connection Portal URL the user opens to link a brokerage."""
    response = _client().authentication.login_snap_trade_user(
        user_id=snaptrade_user_id,
        user_secret=user_secret,
    )
    body = response.body
    return body["redirectURI"]


def list_accounts(snaptrade_user_id: str, user_secret: str) -> list[dict]:
    """List every brokerage account connected by this user."""
    response = _client().account_information.list_user_accounts(
        user_id=snaptrade_user_id,
        user_secret=user_secret,
    )
    return list(response.body or [])


def fetch_account_positions(
    snaptrade_user_id: str,
    user_secret: str,
    account_id: str,
) -> dict:
    """Fetch positions (holdings + cash) for a single brokerage account."""
    response = _client().account_information.get_all_account_positions(
        user_id=snaptrade_user_id,
        user_secret=user_secret,
        account_id=account_id,
    )
    return response.body
