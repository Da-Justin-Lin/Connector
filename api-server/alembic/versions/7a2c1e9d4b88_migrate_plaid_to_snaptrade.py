"""migrate plaid to snaptrade

Revision ID: 7a2c1e9d4b88
Revises: 455ee9479e33
Create Date: 2026-06-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a2c1e9d4b88"
down_revision: Union[str, Sequence[str], None] = "455ee9479e33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_investment_accounts_plaid_item_id", table_name="investment_accounts")
    op.drop_table("investment_accounts")

    op.create_table(
        "snaptrade_users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("snaptrade_user_id", sa.String(length=255), nullable=False),
        sa.Column("snaptrade_user_secret", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("snaptrade_user_id"),
    )

    op.create_table(
        "investment_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("snaptrade_account_id", sa.String(length=255), nullable=False),
        sa.Column("institution_name", sa.String(length=255), nullable=True),
        sa.Column("account_name", sa.String(length=255), nullable=True),
        sa.Column("account_type", sa.String(length=100), nullable=True),
        sa.Column("account_number", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snaptrade_account_id"),
    )
    op.create_index(
        op.f("ix_investment_accounts_snaptrade_account_id"),
        "investment_accounts",
        ["snaptrade_account_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_investment_accounts_snaptrade_account_id"),
        table_name="investment_accounts",
    )
    op.drop_table("investment_accounts")
    op.drop_table("snaptrade_users")

    op.create_table(
        "investment_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("plaid_item_id", sa.String(length=255), nullable=False),
        sa.Column("plaid_access_token", sa.String(length=500), nullable=False),
        sa.Column("institution_name", sa.String(length=255), nullable=True),
        sa.Column("account_name", sa.String(length=255), nullable=True),
        sa.Column("account_type", sa.String(length=100), nullable=True),
        sa.Column("current_balance", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_investment_accounts_plaid_item_id"),
        "investment_accounts",
        ["plaid_item_id"],
        unique=False,
    )
