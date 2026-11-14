from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    """An incoming rating, with an optional comment."""

    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    """A persisted feedback record, serialised from the ORM record."""

    id: int
    request_id: int
    rating: int
    comment: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackSummary(BaseModel):
    """Global aggregate over every feedback record.

    ``distribution`` always carries the keys "1" through "5", so a value of
    zero distinguishes an unused rating from a missing one. The counts always
    sum to ``total_count``.
    """

    mean_rating: float
    distribution: dict[str, int]
    total_count: int
