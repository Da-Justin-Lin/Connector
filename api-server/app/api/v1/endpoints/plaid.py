from fastapi import APIRouter, HTTPException

from app.schemas.investment_account import (
    ExchangeTokenRequest,
    ExchangeTokenResponse,
    LinkTokenResponse,
)
from app.services.plaid_service import create_link_token, exchange_public_token

router = APIRouter()


@router.post("/link-token", response_model=LinkTokenResponse)
async def get_link_token(user_id: str = "demo-user"):
    """Create a Plaid Link token to initialize the Link flow in the browser."""
    try:
        token = await create_link_token(user_id)
        return {"link_token": token}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Plaid error: {exc}") from exc


@router.post("/exchange-token", response_model=ExchangeTokenResponse)
async def exchange_token(body: ExchangeTokenRequest):
    """Exchange a short-lived public token for a persistent access token."""
    try:
        result = await exchange_public_token(body.public_token)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Plaid error: {exc}") from exc
