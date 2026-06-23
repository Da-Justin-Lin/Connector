from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.services.user_service import (
    create_oauth_user,
    get_user_by_email,
    get_user_by_google_id,
)

router = APIRouter()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _google_redirect_uri() -> str:
    return f"{settings.backend_url}/api/v1/auth/google/callback"


@router.get("/google/login")
async def google_login():
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
    }
    return RedirectResponse(url=f"{_GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/google/callback")
async def google_callback(code: str, db: AsyncSession = Depends(get_db)):
    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "redirect_uri": _google_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
    token_data = token_res.json()

    if "error" in token_data:
        raise HTTPException(status_code=400, detail=token_data.get("error_description", token_data["error"]))

    # Decode the id_token (no signature verification needed — we just fetched it from Google)
    claims = jwt.get_unverified_claims(token_data["id_token"])
    google_id: str = claims["sub"]
    email: str = claims["email"]

    # Find or create user
    user = await get_user_by_google_id(db, google_id)
    if not user:
        user = await get_user_by_email(db, email)
        if user:
            # Link Google ID to existing email account
            user.google_id = google_id
            await db.commit()
            await db.refresh(user)
        else:
            user = await create_oauth_user(db, email, google_id)

    token = create_access_token(str(user.id))
    return RedirectResponse(url=f"{settings.frontend_url}/auth/callback?token={token}")
