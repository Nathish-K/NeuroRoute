"""Feedback capture and aggregation.

Arguments are validated before the database is touched, so a malformed rating
or comment is rejected without a query. The router layer also validates the
same bounds through ``FeedbackCreate``; these checks cover direct calls.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.exceptions import (
    ConflictError,
    NotFoundError,
    PersistenceError,
    ValidationError,
)
from app.models.feedback import Feedback
from app.models.request import Request
from app.schemas.feedback import FeedbackSummary

MIN_RATING = 1
MAX_RATING = 5
MAX_COMMENT_CHARS = 500
RATING_KEYS = tuple(str(value) for value in range(MIN_RATING, MAX_RATING + 1))


def _duplicate_feedback_error() -> ConflictError:
    return ConflictError(
        "Feedback has already been submitted for this request",
        field="request_id",
    )


def _validate_rating(rating: int) -> None:
    """Reject anything that is not an integer within [1, 5]."""
    # bool is a subclass of int, so True would otherwise pass as a rating of 1.
    if isinstance(rating, bool) or not isinstance(rating, int):
        raise ValidationError(
            "rating must be an integer between 1 and 5 inclusive"
        )
    if not MIN_RATING <= rating <= MAX_RATING:
        raise ValidationError(
            "rating must be an integer between 1 and 5 inclusive"
        )


def _validate_comment(comment: str | None) -> None:
    """Reject a comment longer than the column allows."""
    if comment is not None and len(comment) > MAX_COMMENT_CHARS:
        raise ValidationError("comment must not exceed 500 characters")


def create_feedback(
    request_id: int, rating: int, comment: str | None, db: Session
) -> Feedback:
    """Record a user's rating of one request.

    Raises :class:`ValidationError` for an out-of-range rating or an overlong
    comment, :class:`NotFoundError` when the request does not exist, and
    :class:`ConflictError` when that request already has feedback.
    """
    _validate_rating(rating)
    _validate_comment(comment)

    if db.get(Request, request_id) is None:
        raise NotFoundError(f"Request {request_id} was not found")

    existing = db.scalar(
        select(Feedback).where(Feedback.request_id == request_id)
    )
    if existing is not None:
        raise _duplicate_feedback_error()

    feedback = Feedback(
        request_id=request_id,
        rating=rating,
        comment=comment,
    )
    try:
        db.add(feedback)
        db.commit()
    except IntegrityError as exc:
        # A concurrent insert won the race past the check above; the UNIQUE
        # constraint on request_id is the final guard. Report it as a conflict
        # rather than letting it surface as a persistence failure.
        db.rollback()
        raise _duplicate_feedback_error() from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Failed to persist the feedback record") from exc
    db.refresh(feedback)

    return feedback


def get_feedback(request_id: int, db: Session) -> Feedback:
    """Return the feedback for one request.

    Raises :class:`NotFoundError` when that request has no feedback.
    """
    feedback = db.scalar(
        select(Feedback).where(Feedback.request_id == request_id)
    )
    if feedback is None:
        raise NotFoundError(
            "No feedback has been submitted for this request"
        )

    return feedback


def get_feedback_summary(db: Session) -> FeedbackSummary:
    """Aggregate every feedback record, with no filtering.

    Returns a mean rounded to two decimal places, a count per rating value,
    and the total. With no records the mean is 0.0 and every count is zero.
    The mean is computed from integer sums, so it does not inherit any
    floating-point error from the database.
    """
    rows = db.execute(
        select(Feedback.rating, func.count(Feedback.id)).group_by(
            Feedback.rating
        )
    ).all()

    distribution = {key: 0 for key in RATING_KEYS}
    for rating, count in rows:
        key = str(rating)
        if key in distribution:
            distribution[key] = count

    # Derived from the distribution so the counts always sum to the total.
    total_count = sum(distribution.values())
    weighted_total = sum(
        int(key) * count for key, count in distribution.items()
    )
    mean_rating = round(weighted_total / total_count, 2) if total_count else 0.0

    return FeedbackSummary(
        mean_rating=mean_rating,
        distribution=distribution,
        total_count=total_count,
    )
