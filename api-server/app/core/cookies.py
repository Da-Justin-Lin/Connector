"""Helpers for the refresh-token cookie.

Scoped to the auth routes (`/api/v1/auth`) so it's only ever sent to the refresh
and logout endpoints — never attached to ordinary API calls.

SameSite/Secure are configurable because the right values depend on topology:
- local http dev (same site): samesite=lax, secure=false
- cross-site prod (frontend and API on different domains): samesite=none, which
  browsers only honor together with secure=true (HTTPS).
"""
from typing import Literal

from fastapi import Response

from app.core.config import settings

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _cookie_params() -> tuple[Literal["lax", "strict", "none"], bool]:
    samesite = settings.cookie_samesite.lower()
    if samesite not in ("lax", "strict", "none"):
        samesite = "lax"
    # SameSite=None is meaningless (and dropped by browsers) without Secure.
    secure = settings.cookie_secure or samesite == "none"
    return samesite, secure  # type: ignore[return-value]


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    samesite, secure = _cookie_params()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )


def clear_refresh_cookie(response: Response) -> None:
    samesite, secure = _cookie_params()
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )
