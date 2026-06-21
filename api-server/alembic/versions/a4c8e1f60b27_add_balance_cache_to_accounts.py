"""add balance_cache to investment_accounts

Revision ID: a4c8e1f60b27
Revises: f3b6a7c2d9e1
Create Date: 2026-06-20 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4c8e1f60b27"
down_revision: Union[str, Sequence[str], None] = "f3b6a7c2d9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "investment_accounts",
        sa.Column(
            "balance_cache",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("investment_accounts", "balance_cache")
