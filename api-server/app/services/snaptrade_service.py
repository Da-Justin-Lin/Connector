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


def list_accounts() -> list[dict]:
    """List every brokerage account connected by the SnapTrade user."""
    user_id, user_secret = _creds()
    response = _client().account_information.list_user_accounts(
        user_id=user_id,
        user_secret=user_secret,
    )
    return list(response.body or [])


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
