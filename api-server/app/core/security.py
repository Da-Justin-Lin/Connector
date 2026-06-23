import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_refresh_token() -> str:
    """A high-entropy, opaque refresh token (URL-safe so it's cookie-friendly)."""
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    """SHA-256 of a refresh token. We store only the hash; the raw value lives
    in the client's httpOnly cookie. SHA-256 (not bcrypt) is fine here because
    the token is already 48 random bytes — there's nothing to brute-force."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_access_token(subject: Any, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    return jwt.encode(
        {"exp": expire, "sub": str(subject)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
