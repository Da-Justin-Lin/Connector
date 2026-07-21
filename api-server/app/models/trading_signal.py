import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TradingSignal(Base):
    """
    A signal emitted by the external stock-agent service.

    These are agent-wide (not per-user): the agent watches one fixed watchlist
    and broadcasts. Ingested over HTTP so the agent no longer depends on SMTP
    (Gmail SMTP times out from the agent's container).
    """

    __tablename__ = "trading_signals"
    __table_args__ = (Index("ix_trading_signals_created", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    # Entry signals: BUY/SELL/HOLD. Exit alerts reuse this with the alert type
    # (TRAIL_RAISED, THESIS_BROKEN, ...), so it must hold longer values.
    signal: Mapped[str] = mapped_column(String(20), nullable=False)
    # LOW/MEDIUM/HIGH for entries; IMMEDIATE/IMPORTANT/ADVISORY for exit alerts.
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")

    price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    target_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    shares: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)

    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_reward_ratio: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    order_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Concrete stop/target/trailing plan for an entry signal (empty for exit alerts).
    exit_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    # For exit alerts (HARD_STOP / TARGET_HIT / ...): which position they belong to.
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("positions.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
