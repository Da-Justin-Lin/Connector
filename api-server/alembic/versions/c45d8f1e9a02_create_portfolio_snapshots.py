"""create portfolio_snapshots table

Revision ID: c45d8f1e9a02
Revises: b3f5d1a72ce4
Create Date: 2026-06-14 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c45d8f1e9a02"
down_revision: Union[str, Sequence[str], None] = "b3f5d1a72ce4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_value", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("total_cash", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portfolio_snapshots_user_at",
        "portfolio_snapshots",
        ["user_id", "snapshot_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_snapshots_user_at",
        table_name="portfolio_snapshots",
    )
    op.drop_table("portfolio_snapshots")
