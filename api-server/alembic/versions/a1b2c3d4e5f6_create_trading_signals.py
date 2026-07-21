"""create trading_signals table

Revision ID: a1b2c3d4e5f6
Revises: c9d1e2f3a4b5
Create Date: 2026-07-20 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c9d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trading_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("signal", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("target_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("stop_loss", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("shares", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("max_score", sa.Integer(), nullable=True),
        sa.Column("risk_reward_ratio", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("regime", sa.String(length=16), nullable=True),
        sa.Column("order_status", sa.String(length=255), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trading_signals_created", "trading_signals", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_trading_signals_created", table_name="trading_signals")
    op.drop_table("trading_signals")
