from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.feedback.service import (
    create_feedback,
    get_feedback,
    get_feedback_summary,
)
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackResponse,
    FeedbackSummary,
)

router = APIRouter(
    prefix="/api",
    tags=["Feedback"]
)


# CREATE: Record a rating for one request (Requirements 6.1-6.4, 6.8)
# The service raises NotFoundError (404) for an unknown request and
# ConflictError (409) when feedback already exists; both are mapped in main.py.
@router.post(
    "/requests/{request_id}/feedback",
    response_model=FeedbackResponse,
    status_code=201,
)
def submit_feedback(
    request_id: int,
    data: FeedbackCreate,
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    feedback = create_feedback(request_id, data.rating, data.comment, db)
    return FeedbackResponse.model_validate(feedback)


# READ: Return the feedback for one request (Requirements 6.5, 6.6)
@router.get(
    "/requests/{request_id}/feedback",
    response_model=FeedbackResponse,
)
def read_feedback(
    request_id: int,
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    return FeedbackResponse.model_validate(get_feedback(request_id, db))


# READ: Global feedback aggregate, unfiltered (Requirement 6.9)
@router.get("/metrics/feedback-summary", response_model=FeedbackSummary)
def read_feedback_summary(db: Session = Depends(get_db)) -> FeedbackSummary:
    return get_feedback_summary(db)
