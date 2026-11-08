from datetime import datetime

from sqlalchemy import DateTime, String, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    prompt: Mapped[str] = mapped_column(
        String(1000),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="pending"
    )

    # Columns added by Task 1.4 (live table upgraded by Task 1.4a migration)
    complexity_class: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    end_to_end_latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    routing_decisions: Mapped[list["RoutingDecision"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan"
    )

    feedback: Mapped["Feedback | None"] = relationship(
        back_populates="request",
        uselist=False
    )
