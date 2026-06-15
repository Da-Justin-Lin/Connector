"""drop snaptrade_users table

Revision ID: b3f5d1a72ce4
Revises: 7a2c1e9d4b88
Create Date: 2026-06-14 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3f5d1a72ce4"
down_revision: Union[str, Sequence[str], None] = "7a2c1e9d4b88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("snaptrade_users")


def downgrade() -> None:
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
