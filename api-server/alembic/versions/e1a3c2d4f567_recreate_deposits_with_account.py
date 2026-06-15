"""recreate deposits with investment_account_id

Revision ID: e1a3c2d4f567
Revises: d8f2e4c1ab90
Create Date: 2026-06-14 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1a3c2d4f567"
down_revision: Union[str, Sequence[str], None] = "d8f2e4c1ab90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop and recreate — schema change is incompatible and any existing rows
    # don't have an investment_account_id.
    op.drop_index("ix_deposits_user_at", table_name="deposits")
    op.drop_table("deposits")
    op.create_table(
        "deposits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("investment_account_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("deposited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["investment_account_id"],
            ["investment_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deposits_user_at", "deposits", ["user_id", "deposited_at"])
    op.create_index("ix_deposits_account", "deposits", ["investment_account_id"])


def downgrade() -> None:
    op.drop_index("ix_deposits_account", table_name="deposits")
    op.drop_index("ix_deposits_user_at", table_name="deposits")
    op.drop_table("deposits")
