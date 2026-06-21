"""create broker_orders + account report cache columns

Revision ID: f3b6a7c2d9e1
Revises: e1a3c2d4f567
Create Date: 2026-06-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3b6a7c2d9e1"
down_revision: Union[str, Sequence[str], None] = "e1a3c2d4f567"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("investment_account_id", sa.UUID(), nullable=False),
        sa.Column("broker_order_id", sa.String(length=255), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["investment_account_id"],
            ["investment_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "investment_account_id",
            "broker_order_id",
            name="uq_broker_orders_account_order",
        ),
    )
    op.create_index(
        "ix_broker_orders_account_executed",
        "broker_orders",
        ["investment_account_id", "executed_at"],
    )

    op.add_column(
        "investment_accounts",
        sa.Column("orders_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "investment_accounts",
        sa.Column(
            "holdings_cache",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "investment_accounts",
        sa.Column("holdings_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("investment_accounts", "holdings_synced_at")
    op.drop_column("investment_accounts", "holdings_cache")
    op.drop_column("investment_accounts", "orders_synced_at")
    op.drop_index(
        "ix_broker_orders_account_executed", table_name="broker_orders"
    )
    op.drop_table("broker_orders")
