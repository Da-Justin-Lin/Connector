"""create positions table and link exit alerts

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-20 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source_signal_id", sa.UUID(), nullable=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("shares", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("entry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initial_stop", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("target", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("exit_reason", sa.String(length=32), nullable=True),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_signal_id"], ["trading_signals.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_positions_user_status", "positions", ["user_id", "status"])

    op.add_column(
        "trading_signals", sa.Column("position_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_trading_signals_position",
        "trading_signals",
        "positions",
        ["position_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_trading_signals_position", "trading_signals", type_="foreignkey"
    )
    op.drop_column("trading_signals", "position_id")
    op.drop_index("ix_positions_user_status", table_name="positions")
    op.drop_table("positions")
