import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from app.core.config import settings

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def _get_client() -> plaid_api.PlaidApi:
    configuration = plaid.Configuration(
        host=_ENV_MAP.get(settings.plaid_env, plaid.Environment.Sandbox),
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


async def create_link_token(user_id: str) -> str:
    """Create a Plaid Link token for the given internal user ID."""
    client = _get_client()
    request = LinkTokenCreateRequest(
        products=[Products("investments")],
        client_name="My App",
        country_codes=[CountryCode("US")],
        language="en",
        institution_id="ins_109508",
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
    )
    response = client.link_token_create(request)
    return response["link_token"]


async def fetch_holdings(access_token: str):
    """Fetch investment holdings and securities for a given access token."""
    client = _get_client()
    request = InvestmentsHoldingsGetRequest(access_token=access_token)
    return client.investments_holdings_get(request)


async def exchange_public_token(public_token: str) -> dict:
    """Exchange a short-lived public token for a persistent access token + item ID."""
    client = _get_client()
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request)
    return {
        "access_token": response["access_token"],
        "item_id": response["item_id"],
    }
