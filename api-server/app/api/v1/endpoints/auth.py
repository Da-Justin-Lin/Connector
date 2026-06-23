from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.cookies import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    set_refresh_cookie,
)
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import TokenResponse
from app.services.refresh_token_service import (
    InvalidRefreshToken,
    issue_refresh_token,
    revoke_all_for_user,
    revoke_refresh_token,
    rotate_refresh_token,
)
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

    # Set the refresh cookie on the redirect; the frontend's /auth/callback then
    # exchanges it for an access token via /auth/refresh (no token in the URL).
    raw_refresh = await issue_refresh_token(db, user.id)
    redirect = RedirectResponse(url=f"{settings.frontend_url}/auth/callback")
    set_refresh_cookie(redirect, raw_refresh)
    return redirect


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    """Rotate the refresh cookie and mint a fresh access token."""
    try:
        user_id, new_raw = await rotate_refresh_token(db, refresh_token)
    except InvalidRefreshToken:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        )
    set_refresh_cookie(response, new_raw)
    return TokenResponse(access_token=create_access_token(str(user_id)))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    """Revoke this session's refresh token and clear the cookie."""
    await revoke_refresh_token(db, refresh_token)
    clear_refresh_cookie(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke every refresh token for the current user ("log out everywhere")."""
    await revoke_all_for_user(db, current_user.id)
    clear_refresh_cookie(response)
