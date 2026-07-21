"""widen signal/confidence for exit alert types

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-20 23:30:00.000000

Exit alerts reuse trading_signals.signal for the alert type (TRAIL_RAISED,
THESIS_BROKEN, ...) and .confidence for urgency (IMMEDIATE/IMPORTANT), both of
which exceed the original varchar(8). Widen them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "trading_signals", "signal",
        existing_type=sa.String(length=8), type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "trading_signals", "confidence",
        existing_type=sa.String(length=8), type_=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "trading_signals", "confidence",
        existing_type=sa.String(length=16), type_=sa.String(length=8),
        existing_nullable=False,
    )
    op.alter_column(
        "trading_signals", "signal",
        existing_type=sa.String(length=20), type_=sa.String(length=8),
        existing_nullable=False,
    )
