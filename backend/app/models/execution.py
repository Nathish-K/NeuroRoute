from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class Execution(Base):
    """One inference attempt. Several rows per request on escalation/fallback."""

    __tablename__ = "executions"
    __table_args__ = (Index("ix_executions_status", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    routing_decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routing_decisions.id"), nullable=False, index=True
    )
    # Text(4294967295) compiles to "TEXT(4294967295)" on MySQL (which the server
    # maps to LONGTEXT); the explicit variant makes the DDL say LONGTEXT.
    response_text: Mapped[str | None] = mapped_column(
        Text(4294967295).with_variant(LONGTEXT(), "mysql"), nullable=True
    )
    input_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 10), nullable=True
    )
    # "pending" | "completed" | "failed" | "timed_out"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    routing_decision: Mapped["RoutingDecision"] = relationship(
        back_populates="executions"
    )
    evaluation: Mapped["Evaluation | None"] = relationship(
        back_populates="execution", uselist=False
    )
