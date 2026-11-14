"""Tests for the Feedback System, exercised through the API."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401  (registers every table on Base)
from app.database.connection import Base
from app.database.dependencies import get_db
from app.exceptions import ConflictError
from app.feedback.service import create_feedback
from app.main import app
from app.models.request import Request
from tests.conftest import seed_stub_model, stub_provider

FEEDBACK_FIELDS = {"id", "request_id", "rating", "comment", "created_at"}
EMPTY_DISTRIBUTION = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}

# Feedback is attached to a request, and the only way to create one through
# the API is to run the pipeline, so every test here needs a routable model
# and a stub provider.
pytestmark = pytest.mark.usefixtures("pipeline_ready")


def create_request(client: TestClient, prompt: str = "Explain routing") -> int:
    """Create a request through the API and return its identifier."""
    response = client.post("/api/requests/", json={"prompt": prompt})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def post_feedback(
    client: TestClient, request_id: int, rating: int, comment: str | None = None
):
    payload: dict[str, object] = {"rating": rating}
    if comment is not None:
        payload["comment"] = comment
    return client.post(f"/api/requests/{request_id}/feedback", json=payload)


def _inline_client() -> Iterator[TestClient]:
    """Build a throwaway app client (Hypothesis forbids fixtures)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as session:
        seed_stub_model(session)

    def override_get_db() -> Iterator:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with stub_provider():
            yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def rating_strategy() -> st.SearchStrategy[int]:
    return st.integers(min_value=1, max_value=5)


def invalid_rating_strategy() -> st.SearchStrategy[int]:
    return st.one_of(
        st.integers(min_value=-100, max_value=0),
        st.integers(min_value=6, max_value=100),
    )


def feedback_comment_strategy() -> st.SearchStrategy[str | None]:
    return st.one_of(st.none(), st.text(max_size=500))


# --------------------------------------------------------------------------
# Creating feedback
# --------------------------------------------------------------------------


def test_create_feedback_returns_201_with_correct_fields(
    test_client: TestClient,
) -> None:
    request_id = create_request(test_client)

    response = post_feedback(test_client, request_id, 4, "Clear and fast.")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == FEEDBACK_FIELDS
    assert body["request_id"] == request_id
    assert body["rating"] == 4
    assert body["comment"] == "Clear and fast."
    assert body["id"] is not None
    assert body["created_at"] is not None


def test_create_feedback_without_a_comment_is_allowed(
    test_client: TestClient,
) -> None:
    request_id = create_request(test_client)

    response = post_feedback(test_client, request_id, 5)

    assert response.status_code == 201, response.text
    assert response.json()["comment"] is None


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
def test_every_rating_in_range_is_accepted(
    test_client: TestClient, rating: int
) -> None:
    request_id = create_request(test_client)

    response = post_feedback(test_client, request_id, rating)

    assert response.status_code == 201, response.text
    assert response.json()["rating"] == rating


def test_create_feedback_for_unknown_request_returns_404(
    test_client: TestClient,
) -> None:
    response = post_feedback(test_client, 999_999, 3)

    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"].lower()


def test_duplicate_feedback_returns_409(test_client: TestClient) -> None:
    request_id = create_request(test_client)
    assert post_feedback(test_client, request_id, 4, "first").status_code == 201

    response = post_feedback(test_client, request_id, 1, "second")

    assert response.status_code == 409, response.text
    assert "already been submitted" in response.json()["detail"]


def test_duplicate_feedback_leaves_the_first_record_unchanged(
    test_client: TestClient,
) -> None:
    request_id = create_request(test_client)
    original = post_feedback(test_client, request_id, 4, "first").json()

    post_feedback(test_client, request_id, 1, "second")

    stored = test_client.get(f"/api/requests/{request_id}/feedback").json()
    assert stored == original


def test_concurrent_duplicate_is_reported_as_conflict_not_failure(
    db_session: Session,
) -> None:
    """A racing insert must surface as 409, not a persistence failure."""
    request = Request(prompt="Explain routing", status="pending")
    db_session.add(request)
    db_session.commit()

    # Simulate the UNIQUE constraint firing after the pre-check passed.
    def failing_commit() -> None:
        raise IntegrityError("INSERT", {}, Exception("duplicate request_id"))

    original_commit = db_session.commit
    db_session.commit = failing_commit
    try:
        with pytest.raises(ConflictError, match="already been submitted"):
            create_feedback(request.id, 4, None, db_session)
    finally:
        db_session.commit = original_commit


@pytest.mark.parametrize("rating", [0, 6, -1, 100, 3.5, "four", None])
def test_invalid_rating_returns_422(
    test_client: TestClient, rating: object
) -> None:
    request_id = create_request(test_client)

    response = test_client.post(
        f"/api/requests/{request_id}/feedback", json={"rating": rating}
    )

    assert response.status_code == 422, response.text


def test_missing_rating_returns_422(test_client: TestClient) -> None:
    request_id = create_request(test_client)

    response = test_client.post(
        f"/api/requests/{request_id}/feedback", json={}
    )

    assert response.status_code == 422, response.text


def test_comment_over_500_characters_returns_422(
    test_client: TestClient,
) -> None:
    request_id = create_request(test_client)

    response = post_feedback(test_client, request_id, 3, "x" * 501)

    assert response.status_code == 422, response.text


def test_comment_of_exactly_500_characters_is_accepted(
    test_client: TestClient,
) -> None:
    request_id = create_request(test_client)

    response = post_feedback(test_client, request_id, 3, "x" * 500)

    assert response.status_code == 201, response.text
    assert len(response.json()["comment"]) == 500


def test_rejected_feedback_is_not_persisted(test_client: TestClient) -> None:
    request_id = create_request(test_client)

    post_feedback(test_client, request_id, 0)
    post_feedback(test_client, request_id, 3, "x" * 501)

    assert test_client.get(
        f"/api/requests/{request_id}/feedback"
    ).status_code == 404
    summary = test_client.get("/api/metrics/feedback-summary").json()
    assert summary["total_count"] == 0


# --------------------------------------------------------------------------
# Reading feedback
# --------------------------------------------------------------------------


def test_get_feedback_returns_the_submitted_values(
    test_client: TestClient,
) -> None:
    request_id = create_request(test_client)
    created = post_feedback(test_client, request_id, 2, "Too slow.").json()

    response = test_client.get(f"/api/requests/{request_id}/feedback")

    assert response.status_code == 200, response.text
    assert response.json() == created


def test_get_feedback_without_a_record_returns_404(
    test_client: TestClient,
) -> None:
    request_id = create_request(test_client)

    response = test_client.get(f"/api/requests/{request_id}/feedback")

    assert response.status_code == 404, response.text
    assert "No feedback" in response.json()["detail"]


def test_get_feedback_for_unknown_request_returns_404(
    test_client: TestClient,
) -> None:
    response = test_client.get("/api/requests/999999/feedback")

    assert response.status_code == 404, response.text


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


def test_summary_with_no_records_is_all_zeros(
    test_client: TestClient,
) -> None:
    response = test_client.get("/api/metrics/feedback-summary")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "mean_rating": 0.0,
        "distribution": EMPTY_DISTRIBUTION,
        "total_count": 0,
    }


def test_summary_counts_and_mean_reflect_every_record(
    test_client: TestClient,
) -> None:
    for rating in (4, 5, 1, 5):
        post_feedback(test_client, create_request(test_client), rating)

    summary = test_client.get("/api/metrics/feedback-summary").json()

    assert summary["total_count"] == 4
    assert summary["distribution"] == {"1": 1, "2": 0, "3": 0, "4": 1, "5": 2}
    assert summary["mean_rating"] == 3.75


def test_summary_mean_is_rounded_to_two_decimal_places(
    test_client: TestClient,
) -> None:
    # 5 / 3 = 1.666... -> 1.67
    for rating in (1, 2, 2):
        post_feedback(test_client, create_request(test_client), rating)

    summary = test_client.get("/api/metrics/feedback-summary").json()

    assert summary["mean_rating"] == 1.67


def test_summary_is_global_and_unfiltered(test_client: TestClient) -> None:
    first = create_request(test_client, "first prompt")
    second = create_request(test_client, "second prompt")
    post_feedback(test_client, first, 1)
    post_feedback(test_client, second, 5)

    summary = test_client.get("/api/metrics/feedback-summary").json()

    assert summary["total_count"] == 2
    assert summary["mean_rating"] == 3.0


# --------------------------------------------------------------------------
# Properties
# --------------------------------------------------------------------------


# Feature: neuroroute-mvp, Property 15: Feedback Rating Bounds
# Validates: Requirements 6.1, 6.2
@given(
    valid_rating=rating_strategy(),
    invalid_rating=invalid_rating_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_persisted_rating_is_always_within_bounds(
    valid_rating: int, invalid_rating: int
) -> None:
    clients = _inline_client()
    client = next(clients)
    try:
        accepted_id = create_request(client)
        accepted = post_feedback(client, accepted_id, valid_rating)

        assert accepted.status_code == 201, accepted.text
        assert 1 <= accepted.json()["rating"] <= 5

        # An out-of-range rating is refused and stores nothing.
        rejected_id = create_request(client)
        rejected = post_feedback(client, rejected_id, invalid_rating)

        assert rejected.status_code == 422, rejected.text
        assert client.get(
            f"/api/requests/{rejected_id}/feedback"
        ).status_code == 404

        summary = client.get("/api/metrics/feedback-summary").json()
        assert summary["total_count"] == 1
        assert sum(summary["distribution"].values()) == 1
    finally:
        for _ in clients:
            pass


# Feature: neuroroute-mvp, Property 16: Feedback Round-Trip
# Validates: Requirements 6.1, 6.7
@given(rating=rating_strategy(), comment=feedback_comment_strategy())
@settings(max_examples=100, deadline=None)
def test_feedback_round_trips_unchanged(
    rating: int, comment: str | None
) -> None:
    clients = _inline_client()
    client = next(clients)
    try:
        request_id = create_request(client)

        created = post_feedback(client, request_id, rating, comment)
        assert created.status_code == 201, created.text

        fetched = client.get(f"/api/requests/{request_id}/feedback")
        assert fetched.status_code == 200, fetched.text

        body = fetched.json()
        assert body == created.json()
        assert body["rating"] == rating
        assert body["comment"] == comment
        assert body["request_id"] == request_id
    finally:
        for _ in clients:
            pass


# Feature: neuroroute-mvp, Property 17: Feedback Uniqueness
# Validates: Requirements 6.4
@given(
    first_rating=rating_strategy(),
    first_comment=feedback_comment_strategy(),
    second_rating=rating_strategy(),
    second_comment=feedback_comment_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_second_submission_is_always_rejected(
    first_rating: int,
    first_comment: str | None,
    second_rating: int,
    second_comment: str | None,
) -> None:
    clients = _inline_client()
    client = next(clients)
    try:
        request_id = create_request(client)
        first = post_feedback(client, request_id, first_rating, first_comment)
        assert first.status_code == 201, first.text

        second = post_feedback(
            client, request_id, second_rating, second_comment
        )

        assert second.status_code == 409, second.text
        # The original record survives the rejected submission untouched.
        assert client.get(
            f"/api/requests/{request_id}/feedback"
        ).json() == first.json()
        summary = client.get("/api/metrics/feedback-summary").json()
        assert summary["total_count"] == 1
    finally:
        for _ in clients:
            pass


# Feature: neuroroute-mvp, Property 18: Feedback Summary Correctness
# Validates: Requirements 6.9
@given(ratings=st.lists(rating_strategy(), min_size=0, max_size=12))
@settings(max_examples=100, deadline=None)
def test_summary_matches_the_submitted_ratings(ratings: list[int]) -> None:
    clients = _inline_client()
    client = next(clients)
    try:
        for rating in ratings:
            response = post_feedback(client, create_request(client), rating)
            assert response.status_code == 201, response.text

        summary = client.get("/api/metrics/feedback-summary").json()

        assert summary["total_count"] == len(ratings)
        assert sum(summary["distribution"].values()) == summary["total_count"]
        assert set(summary["distribution"]) == set(EMPTY_DISTRIBUTION)

        for value in range(1, 6):
            assert summary["distribution"][str(value)] == ratings.count(value)

        if ratings:
            assert summary["mean_rating"] == round(
                sum(ratings) / len(ratings), 2
            )
        else:
            assert summary["mean_rating"] == 0.0
            assert summary["distribution"] == EMPTY_DISTRIBUTION
    finally:
        for _ in clients:
            pass
