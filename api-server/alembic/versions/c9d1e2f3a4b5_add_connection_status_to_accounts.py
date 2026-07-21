"""add connection status to investment_accounts

Tracks each account's SnapTrade connection (brokerage_authorization) id and
whether that connection has been disabled, so the UI can prompt a reconnect.

Revision ID: c9d1e2f3a4b5
Revises: b7e2f9c4d1a3
Create Date: 2026-07-20 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "b7e2f9c4d1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "investment_accounts",
        sa.Column("brokerage_authorization_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "investment_accounts",
        sa.Column(
            "connection_disabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("investment_accounts", "connection_disabled")
    op.drop_column("investment_accounts", "brokerage_authorization_id")
