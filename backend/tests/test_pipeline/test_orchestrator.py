"""End-to-end tests for the adaptive request pipeline (Task 9.3)."""
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.base import ExecutionResult, ProviderAdapter
from app.database.connection import Base
from app.database.dependencies import get_db
from app.exceptions import ServiceUnavailableError
from app.main import app
from app.models.evaluation import Evaluation
from app.models.execution import Execution
from app.models.request import Request
from app.models.routing_decision import RoutingDecision
from tests.conftest import (
    STUB_RESPONSE_TEXT,
    seed_stub_model,
    stub_provider,
)

PIPELINE_RESPONSE_FIELDS = {
    "id",
    "prompt",
    "status",
    "complexity_class",
    "routing",
    "execution",
    "evaluation",
    "end_to_end_latency_ms",
    "step_errors",
}
VALID_PROMPTS = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=1,
    max_size=1_000,
).filter(str.strip)


def _count(db_session: Session, model: type) -> int:
    """Return the current persisted row count, including client-side writes."""
    db_session.expire_all()
    return db_session.scalar(select(func.count()).select_from(model)) or 0


def _pipeline_response(test_client: TestClient, prompt: str = "Explain routing") -> dict:
    """Submit a prompt and return a verified successful pipeline body."""
    response = test_client.post("/api/requests/", json={"prompt": prompt})
    assert response.status_code == 200, response.text
    return response.json()


class FailingAdapter(ProviderAdapter):
    """A deterministic provider error returned through the normal engine path."""

    async def dispatch(
        self,
        prompt: str,
        model_name: str,
        cost_per_input_token: Decimal,
        cost_per_output_token: Decimal,
    ) -> ExecutionResult:
        return ExecutionResult(
            response_text="",
            input_token_count=0,
            output_token_count=0,
            latency_ms=0,
            estimated_cost=Decimal("0"),
            status="failed",
            error_message="The provider could not complete the request",
        )


# --------------------------------------------------------------------------
# POST /api/requests/
# --------------------------------------------------------------------------


def test_full_pipeline_returns_all_required_data(
    test_client: TestClient, db_session: Session, pipeline_ready
) -> None:
    body = _pipeline_response(test_client, "Explain adaptive routing")

    assert set(body) == PIPELINE_RESPONSE_FIELDS
    assert body["status"] == "completed"
    assert body["complexity_class"] in {"simple", "moderate", "complex"}
    assert body["routing"]["id"] > 0
    assert body["routing"]["request_id"] == body["id"]
    assert body["execution"]["id"] > 0
    assert body["execution"]["routing_decision_id"] == body["routing"]["id"]
    assert body["execution"]["status"] == "completed"
    assert body["execution"]["response_text"] == STUB_RESPONSE_TEXT
    assert body["evaluation"] is not None
    assert body["evaluation"]["execution_id"] == body["execution"]["id"]
    assert body["end_to_end_latency_ms"] >= body["execution"]["latency_ms"]
    assert body["step_errors"] == []

    request_row = db_session.get(Request, body["id"])
    assert request_row is not None
    assert request_row.status == "completed"
    assert request_row.complexity_class == body["complexity_class"]


def test_routing_outage_returns_pending_degraded_response(
    test_client: TestClient, db_session: Session, pipeline_ready
) -> None:
    with patch(
        "app.routers.requests.route_request",
        side_effect=ServiceUnavailableError("Routing Engine unavailable"),
    ):
        response = test_client.post(
            "/api/requests/", json={"prompt": "Explain routing"}
        )

    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body) == {"id", "prompt", "status", "message"}
    assert body["status"] == "pending"
    assert "partially unavailable" in body["message"]
    assert db_session.get(Request, body["id"]).status == "pending"
    assert _count(db_session, RoutingDecision) == 0
    assert _count(db_session, Execution) == 0
    assert _count(db_session, Evaluation) == 0


def test_intelligence_outage_falls_back_to_moderate_and_continues(
    test_client: TestClient, db_session: Session, pipeline_ready
) -> None:
    with patch(
        "app.routers.requests.classify_prompt",
        side_effect=ServiceUnavailableError("Intelligence Service unavailable"),
    ):
        body = _pipeline_response(test_client)

    assert body["complexity_class"] == "moderate"
    assert body["status"] == "partial"
    assert any(error["step"] == "intelligence" for error in body["step_errors"])
    assert body["execution"]["status"] == "completed"
    assert db_session.get(Request, body["id"]).status != "pending"


def test_execution_failure_is_persisted_and_reported(
    test_client: TestClient, db_session: Session, pipeline_ready
) -> None:
    with patch(
        "app.adapters.engine.resolve_adapter",
        side_effect=lambda provider_name: FailingAdapter(),
    ):
        body = _pipeline_response(test_client)

    assert body["status"] == "partial"
    assert body["execution"]["status"] == "failed"
    assert body["execution"]["error_message"] == (
        "The provider could not complete the request"
    )
    assert any(error["step"] == "execution" for error in body["step_errors"])

    execution = db_session.get(Execution, body["execution"]["id"])
    assert execution is not None
    assert execution.status == "failed"


def test_evaluation_failure_preserves_completed_execution_and_response(
    test_client: TestClient, db_session: Session, pipeline_ready
) -> None:
    with patch(
        "app.routers.requests.evaluate_execution",
        side_effect=RuntimeError("Evaluator unavailable"),
    ):
        body = _pipeline_response(test_client)

    assert body["status"] == "partial"
    assert body["evaluation"] is None
    assert body["execution"]["status"] == "completed"
    assert body["execution"]["response_text"] == STUB_RESPONSE_TEXT
    assert any(error["step"] == "evaluation" for error in body["step_errors"])

    execution = db_session.get(Execution, body["execution"]["id"])
    assert execution is not None
    assert execution.response_text == STUB_RESPONSE_TEXT
    assert execution.status == "completed"
    assert _count(db_session, Evaluation) == 0
    assert db_session.get(Request, body["id"]).status == "partial"


# --------------------------------------------------------------------------
# GET /api/requests/ and GET /api/requests/{id}
# --------------------------------------------------------------------------


def test_request_list_is_ordered_by_created_at_then_id_for_legacy_rows(
    test_client: TestClient, db_session: Session
) -> None:
    shared_time = datetime(2025, 1, 1, 12, 0, 0)
    db_session.add_all(
        [
            Request(prompt="oldest", status="pending", created_at=datetime(2024, 1, 1)),
            Request(prompt="same timestamp one", status="pending", created_at=shared_time),
            Request(prompt="same timestamp two", status="pending", created_at=shared_time),
        ]
    )
    db_session.commit()

    response = test_client.get("/api/requests/")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["prompt"] for row in body] == [
        "same timestamp two",
        "same timestamp one",
        "oldest",
    ]
    for row in body:
        assert row["selected_model_name"] is None
        assert row["routing_policy"] is None
        assert row["latency_ms"] is None
        assert row["estimated_cost"] is None
        assert row["quality_score"] is None


def test_request_detail_returns_all_linked_records(
    test_client: TestClient, pipeline_ready
) -> None:
    created = _pipeline_response(test_client)

    response = test_client.get(f"/api/requests/{created['id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == created["id"]
    assert body["prompt"] == created["prompt"]
    assert body["routing_decision"]["id"] == created["routing"]["id"]
    assert body["execution"]["id"] == created["execution"]["id"]
    assert body["evaluation"]["id"] == created["evaluation"]["id"]
    assert body["feedback"] is None


def test_request_detail_returns_404_for_unknown_request(test_client: TestClient) -> None:
    response = test_client.get("/api/requests/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Request 999999 was not found"}


# --------------------------------------------------------------------------
# Properties 19 and 20
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def property_client() -> Iterator[TestClient]:
    """Persistent isolated client for Hypothesis HTTP examples.

    Hypothesis disallows function-scoped fixtures for generated tests. This
    client keeps all examples inside an in-memory SQLite database and uses the
    shared provider stub, so no test can contact a real provider or database.
    """
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

    def _override_get_db() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with stub_provider():
            yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


# Feature: neuroroute-mvp, Property 19: Pipeline Latency Composition
# Validates: Requirement 8.5
@settings(max_examples=100, deadline=None)
@given(prompt=VALID_PROMPTS)
def test_pipeline_latency_includes_execution_latency(
    property_client: TestClient, prompt: str
) -> None:
    response = property_client.post("/api/requests/", json={"prompt": prompt})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["end_to_end_latency_ms"] >= body["execution"]["latency_ms"]


# Feature: neuroroute-mvp, Property 20: Pipeline Response Completeness
# Validates: Requirement 8.2
@settings(max_examples=100, deadline=None)
@given(prompt=VALID_PROMPTS)
def test_successful_pipeline_response_has_all_required_fields(
    property_client: TestClient, prompt: str
) -> None:
    response = property_client.post("/api/requests/", json={"prompt": prompt})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert set(body) == PIPELINE_RESPONSE_FIELDS
    assert body["routing"] is not None
    assert body["execution"] is not None
    assert body["evaluation"] is not None
    assert isinstance(body["step_errors"], list)
