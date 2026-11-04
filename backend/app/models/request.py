from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column

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