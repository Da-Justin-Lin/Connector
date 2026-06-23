"""Issue, rotate, and revoke long-lived refresh tokens.

A refresh token is an opaque random string handed to the client in an httpOnly
cookie; only its SHA-256 hash is stored. On every refresh the presented token is
rotated (the old row revoked, a new one issued). Presenting an already-revoked
token is treated as theft and revokes the user's entire session family.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_refresh_token, hash_token
from app.models.refresh_token import RefreshToken


class InvalidRefreshToken(Exception):
    """Raised when a refresh token is missing, unknown, expired, or reused."""


async def issue_refresh_token(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Create and persist a new refresh token; returns the raw value."""
    raw = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()
    return raw


async def revoke_all_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    await db.commit()


async def revoke_refresh_token(db: AsyncSession, raw: str | None) -> None:
    """Revoke a single token (logout). No-op if it's missing/unknown."""
    if not raw:
        return
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw))
        .values(revoked=True)
    )
    await db.commit()


async def rotate_refresh_token(
    db: AsyncSession, raw: str | None
) -> tuple[uuid.UUID, str]:
    """Validate `raw`, rotate it, and return (user_id, new_raw_token).

    Raises InvalidRefreshToken if the token is absent, unknown, expired, or has
    already been used (the latter triggers a full revoke of that user's tokens).
    """
    if not raw:
        raise InvalidRefreshToken()

    row = (
        await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()

    if row is None:
        raise InvalidRefreshToken()

    # Reuse of an already-revoked token implies the cookie leaked — burn every
    # session for this user so the attacker's stolen token is useless too.
    if row.revoked:
        await revoke_all_for_user(db, row.user_id)
        raise InvalidRefreshToken()

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise InvalidRefreshToken()

    # Rotate: revoke the presented token and mint a fresh one.
    row.revoked = True
    new_raw = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=row.user_id,
            token_hash=hash_token(new_raw),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()
    return row.user_id, new_raw
