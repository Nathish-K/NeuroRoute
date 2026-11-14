"""User feedback capture and aggregation."""

from app.feedback.service import (
    MAX_COMMENT_CHARS,
    MAX_RATING,
    MIN_RATING,
    create_feedback,
    get_feedback,
    get_feedback_summary,
)

__all__ = [
    "MAX_COMMENT_CHARS",
    "MAX_RATING",
    "MIN_RATING",
    "create_feedback",
    "get_feedback",
    "get_feedback_summary",
]
