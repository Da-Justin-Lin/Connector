import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Position(Base):
    """
    A trade the user confirmed taking off a BUY signal.

    This is the lifecycle anchor that was missing: a BUY signal is a broadcast,
    but a Position is a specific trade with its own id. Every exit alert the
    agent later emits carries this position_id, so two BUYs on the same ticker
    are two independent positions each with their own SELL/stop/target.

    Positions are user-owned (whoever confirmed on the dashboard). The agent
    monitors all OPEN positions but never closes them — status only moves to
    CLOSED when the user confirms the sale.
    """

    __tablename__ = "positions"
    __table_args__ = (Index("ix_positions_user_status", "user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The BUY signal this trade was taken from (nullable — user may log a manual trade).
    source_signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_signals.id", ondelete="SET NULL"),
        nullable=True,
    )

    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    shares: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    initial_stop: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    target: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)

    status: Mapped[str] = mapped_column(String(8), nullable=False, default="OPEN")  # OPEN / CLOSED
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    exit_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
