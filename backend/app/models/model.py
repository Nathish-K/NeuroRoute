from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        Index("ix_models_provider_name_model_name", "provider_name", "model_name"),
        Index("ix_models_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    identifier: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(256), nullable=False)
    max_context_length: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_per_input_token: Mapped[Decimal] = mapped_column(
        Numeric(20, 10), nullable=False
    )
    cost_per_output_token: Mapped[Decimal] = mapped_column(
        Numeric(20, 10), nullable=False
    )
    # 1 = LOW (simple), 2 = MEDIUM (moderate), 3 = HIGH (complex)
    capability_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    routing_decisions: Mapped[list["RoutingDecision"]] = relationship(
        back_populates="model"
    )
