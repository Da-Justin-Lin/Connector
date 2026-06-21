import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BrokerOrder(Base):
    """Local cache of a brokerage order, keyed for incremental upsert.

    The raw SnapTrade payload is kept verbatim so the weekly report can
    re-parse it with the same logic as a live fetch, without hitting the API.
    """

    __tablename__ = "broker_orders"
    __table_args__ = (
        UniqueConstraint(
            "investment_account_id",
            "broker_order_id",
            name="uq_broker_orders_account_order",
        ),
        Index(
            "ix_broker_orders_account_executed",
            "investment_account_id",
            "executed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    investment_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investment_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    broker_order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
