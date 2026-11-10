"""Tests for the Execution Engine orchestrator."""

import asyncio
import os
from collections.abc import Iterator
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401  (registers every table on Base)
from app.adapters.base import ExecutionResult
from app.adapters.engine import execute_request, resolve_adapter
from app.adapters.gemini_adapter import GeminiAdapter
from app.adapters.groq_adapter import GroqAdapter
from app.adapters.ollama_adapter import OllamaAdapter
from app.database.connection import Base
from app.exceptions import ConfigurationError, PersistenceError
from app.models.execution import Execution
from app.models.model import Model
from app.models.request import Request
from app.models.routing_decision import RoutingDecision

PROVIDER_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "GROQ_API_KEY": "test-groq-key",
}


def make_model(
    identifier: str,
    provider_name: str,
    *,
    enabled: bool = True,
) -> Model:
    return Model(
        identifier=identifier,
        provider_name=provider_name,
        model_name=f"{identifier}-model",
        max_context_length=8_192,
        cost_per_input_token=Decimal("0.0000010000"),
        cost_per_output_token=Decimal("0.0000020000"),
        capability_tier=2,
        enabled=enabled,
    )


def execution_result(
    status: str,
    *,
    response_text: str = "the answer",
    error_message: str | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        response_text=response_text,
        input_token_count=11,
        output_token_count=22,
        latency_ms=5,
        estimated_cost=Decimal("0.0000550000"),
        status=status,
        error_message=error_message,
    )


def seed(db: Session) -> RoutingDecision:
    """Insert a request, a primary/fallback/disabled model, and a decision."""
    request = Request(prompt="Explain adaptive routing", status="pending")
    db.add(request)
    primary = make_model("primary", "ollama")
    db.add_all(
        [
            primary,
            make_model("fallback", "gemini"),
            make_model("disabled-fallback", "groq", enabled=False),
        ]
    )
    db.commit()

    decision = RoutingDecision(
        request_id=request.id,
        model_id=primary.id,
        policy="cost_optimised",
        complexity_class="moderate",
        estimated_cost=Decimal("0.0001000000"),
        explanation="seeded for execution tests",
    )
    db.add(decision)
    db.commit()
    return decision


def model_by_identifier(db: Session, identifier: str) -> Model:
    return db.scalars(
        select(Model).where(Model.identifier == identifier)
    ).one()


def stub_dispatch(
    *,
    primary: ExecutionResult | Exception,
    fallback: ExecutionResult | Exception | None = None,
):
    """Patch the Ollama (primary) and Gemini (fallback) dispatch methods."""
    primary_mock = AsyncMock(
        side_effect=primary if isinstance(primary, Exception) else None,
        return_value=None if isinstance(primary, Exception) else primary,
    )
    fallback_result = (
        fallback if fallback is not None else execution_result("completed")
    )
    fallback_mock = AsyncMock(
        side_effect=fallback_result
        if isinstance(fallback_result, Exception)
        else None,
        return_value=None
        if isinstance(fallback_result, Exception)
        else fallback_result,
    )
    return (
        patch.object(OllamaAdapter, "dispatch", primary_mock),
        patch.object(GeminiAdapter, "dispatch", fallback_mock),
        primary_mock,
        fallback_mock,
    )


def _inline_session() -> Iterator[Session]:
    """Build a throwaway SQLite session (Hypothesis forbids fixtures)."""
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
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin provider credentials and clear any ambient fallback setting."""
    for key, value in PROVIDER_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("FALLBACK_MODEL_ID", raising=False)


@pytest.fixture()
def decision(db_session: Session) -> RoutingDecision:
    return seed(db_session)


@pytest.mark.parametrize(
    ("provider_name", "expected"),
    [
        ("gemini", GeminiAdapter),
        ("ollama", OllamaAdapter),
        ("groq", GroqAdapter),
        ("  GEMINI  ", GeminiAdapter),
        ("Ollama", OllamaAdapter),
    ],
)
def test_resolve_adapter_maps_registered_providers(
    provider_name: str, expected: type
) -> None:
    assert isinstance(resolve_adapter(provider_name), expected)


@pytest.mark.parametrize("provider_name", ["", "   ", "openai", "anthropic"])
def test_resolve_adapter_rejects_unknown_provider(provider_name: str) -> None:
    with pytest.raises(ConfigurationError, match="Unsupported provider"):
        resolve_adapter(provider_name)


def test_resolve_adapter_propagates_missing_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="^GEMINI_API_KEY is not set$"):
        resolve_adapter("gemini")


async def test_happy_path_persists_single_completed_execution(
    db_session: Session, decision: RoutingDecision
) -> None:
    primary_patch, fallback_patch, primary_mock, _ = stub_dispatch(
        primary=execution_result("completed")
    )
    model = model_by_identifier(db_session, "primary")

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id, "Explain adaptive routing", model, db_session
        )

    stored = db_session.scalars(select(Execution)).all()

    assert len(stored) == 1
    assert stored[0].id == execution.id
    assert execution.routing_decision_id == decision.id
    assert execution.status == "completed"
    assert execution.response_text == "the answer"
    assert execution.input_token_count == 11
    assert execution.output_token_count == 22
    assert execution.estimated_cost == Decimal("0.0000550000")
    assert execution.latency_ms >= 0
    assert execution.error_message is None
    assert execution.is_escalated is False
    assert execution.created_at is not None

    primary_mock.assert_awaited_once_with(
        "Explain adaptive routing",
        "primary-model",
        model.cost_per_input_token,
        model.cost_per_output_token,
    )


async def test_timeout_persists_timed_out_execution(
    db_session: Session, decision: RoutingDecision
) -> None:
    primary_patch, fallback_patch, _, fallback_mock = stub_dispatch(
        primary=execution_result(
            "timed_out",
            response_text="",
            error_message="Ollama request timed out after 30 seconds",
        )
    )

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    assert isinstance(execution, Execution)
    assert execution.status == "timed_out"
    assert execution.error_message == "Ollama request timed out after 30 seconds"
    assert execution.latency_ms >= 0
    assert len(db_session.scalars(select(Execution)).all()) == 1
    fallback_mock.assert_not_awaited()


async def test_provider_error_persists_failed_execution(
    db_session: Session, decision: RoutingDecision
) -> None:
    primary_patch, fallback_patch, _, _ = stub_dispatch(
        primary=execution_result(
            "failed", response_text="", error_message="HTTP 429"
        )
    )

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    assert isinstance(execution, Execution)
    assert execution.status == "failed"
    assert execution.error_message == "HTTP 429"
    assert execution.latency_ms >= 0


async def test_without_fallback_env_var_there_is_no_retry(
    db_session: Session, decision: RoutingDecision
) -> None:
    assert "FALLBACK_MODEL_ID" not in os.environ
    primary_patch, fallback_patch, primary_mock, fallback_mock = stub_dispatch(
        primary=execution_result("failed", response_text="", error_message="down")
    )

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    assert len(db_session.scalars(select(Execution)).all()) == 1
    assert execution.status == "failed"
    primary_mock.assert_awaited_once()
    fallback_mock.assert_not_awaited()


@pytest.mark.parametrize("primary_status", ["failed", "timed_out"])
async def test_fallback_creates_two_executions_for_same_decision(
    db_session: Session,
    decision: RoutingDecision,
    monkeypatch: pytest.MonkeyPatch,
    primary_status: str,
) -> None:
    monkeypatch.setenv("FALLBACK_MODEL_ID", "fallback")
    primary_patch, fallback_patch, _, fallback_mock = stub_dispatch(
        primary=execution_result(
            primary_status, response_text="", error_message="primary down"
        ),
        fallback=execution_result("completed", response_text="fallback answer"),
    )

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    stored = db_session.scalars(
        select(Execution).order_by(Execution.id)
    ).all()

    assert len(stored) == 2
    assert [row.status for row in stored] == [primary_status, "completed"]
    assert all(row.routing_decision_id == decision.id for row in stored)
    assert all(row.is_escalated is False for row in stored)
    assert execution.id == stored[1].id
    assert execution.response_text == "fallback answer"

    fallback_model = model_by_identifier(db_session, "fallback")
    fallback_mock.assert_awaited_once_with(
        "prompt",
        "fallback-model",
        fallback_model.cost_per_input_token,
        fallback_model.cost_per_output_token,
    )


async def test_when_fallback_also_fails_the_primary_record_is_returned(
    db_session: Session,
    decision: RoutingDecision,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FALLBACK_MODEL_ID", "fallback")
    primary_patch, fallback_patch, _, _ = stub_dispatch(
        primary=execution_result(
            "failed", response_text="", error_message="primary down"
        ),
        fallback=execution_result(
            "failed", response_text="", error_message="fallback down"
        ),
    )

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    stored = db_session.scalars(select(Execution).order_by(Execution.id)).all()

    assert len(stored) == 2
    assert execution.id == stored[0].id
    assert execution.error_message == "primary down"


@pytest.mark.parametrize(
    "fallback_identifier",
    ["primary", "disabled-fallback", "does-not-exist"],
)
async def test_unusable_fallback_setting_skips_the_retry(
    db_session: Session,
    decision: RoutingDecision,
    monkeypatch: pytest.MonkeyPatch,
    fallback_identifier: str,
) -> None:
    monkeypatch.setenv("FALLBACK_MODEL_ID", fallback_identifier)
    primary_patch, fallback_patch, primary_mock, fallback_mock = stub_dispatch(
        primary=execution_result("failed", response_text="", error_message="down")
    )

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    assert len(db_session.scalars(select(Execution)).all()) == 1
    assert execution.status == "failed"
    primary_mock.assert_awaited_once()
    fallback_mock.assert_not_awaited()


async def test_unsupported_provider_raises_configuration_error(
    db_session: Session, decision: RoutingDecision
) -> None:
    unsupported = make_model("unsupported", "openai")
    db_session.add(unsupported)
    db_session.commit()

    with pytest.raises(ConfigurationError, match="Unsupported provider"):
        await execute_request(decision.id, "prompt", unsupported, db_session)

    assert db_session.scalars(select(Execution)).all() == []


async def test_missing_provider_credential_raises_configuration_error(
    db_session: Session,
    decision: RoutingDecision,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    with pytest.raises(ConfigurationError, match="^OLLAMA_BASE_URL is not set$"):
        await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    assert db_session.scalars(select(Execution)).all() == []


async def test_adapter_raising_unexpectedly_is_contained(
    db_session: Session, decision: RoutingDecision
) -> None:
    primary_patch, fallback_patch, _, _ = stub_dispatch(
        primary=RuntimeError("adapter defect")
    )

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    assert isinstance(execution, Execution)
    assert execution.status == "failed"
    assert "failed unexpectedly" in execution.error_message
    assert execution.latency_ms >= 0


async def test_long_error_message_is_truncated_to_column_width(
    db_session: Session, decision: RoutingDecision
) -> None:
    primary_patch, fallback_patch, _, _ = stub_dispatch(
        primary=execution_result(
            "failed", response_text="", error_message="x" * 1_500
        )
    )

    with primary_patch, fallback_patch:
        execution = await execute_request(
            decision.id,
            "prompt",
            model_by_identifier(db_session, "primary"),
            db_session,
        )

    assert len(execution.error_message) == 1_000


async def test_persistence_failure_raises_persistence_error(
    db_session: Session,
    decision: RoutingDecision,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rolled_back: list[bool] = []

    def failing_commit() -> None:
        raise SQLAlchemyError("simulated write failure")

    primary_patch, fallback_patch, _, _ = stub_dispatch(
        primary=execution_result("completed")
    )
    model = model_by_identifier(db_session, "primary")
    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(
        db_session, "rollback", lambda: rolled_back.append(True)
    )

    with primary_patch, fallback_patch:
        with pytest.raises(
            PersistenceError, match="^Failed to persist the execution record$"
        ):
            await execute_request(decision.id, "prompt", model, db_session)

    assert rolled_back == [True]


# Feature: neuroroute-mvp, Property 11: Error Containment
# Validates: Requirements 4.6, 4.7, 4.9
@given(
    kind=st.sampled_from(["failed", "timed_out", "raise"]),
    message=st.text(max_size=200),
    exception_type=st.sampled_from([RuntimeError, ValueError, OSError]),
    with_fallback=st.booleans(),
)
@settings(max_examples=100, deadline=None)
def test_provider_errors_are_contained_as_execution_records(
    kind: str,
    message: str,
    exception_type: type[Exception],
    with_fallback: bool,
) -> None:
    sessions = _inline_session()
    db = next(sessions)
    try:
        decision_record = seed(db)
        model = model_by_identifier(db, "primary")

        if kind == "raise":
            primary: ExecutionResult | Exception = exception_type(message)
        else:
            primary = execution_result(
                kind, response_text="", error_message=message
            )

        primary_patch, fallback_patch, _, _ = stub_dispatch(
            primary=primary,
            fallback=execution_result(
                "failed", response_text="", error_message="fallback down"
            ),
        )

        previous = os.environ.get("FALLBACK_MODEL_ID")
        if with_fallback:
            os.environ["FALLBACK_MODEL_ID"] = "fallback"
        else:
            os.environ.pop("FALLBACK_MODEL_ID", None)

        try:
            with primary_patch, fallback_patch:
                execution = asyncio.run(
                    execute_request(
                        decision_record.id, "prompt", model, db
                    )
                )
        finally:
            if previous is None:
                os.environ.pop("FALLBACK_MODEL_ID", None)
            else:
                os.environ["FALLBACK_MODEL_ID"] = previous

        # Contained: an Execution row, never a propagated provider error.
        assert isinstance(execution, Execution)
        assert execution.id is not None
        assert execution.status in {"failed", "timed_out"}
        assert execution.latency_ms >= 0
        assert execution.routing_decision_id == decision_record.id
        assert execution.is_escalated is False
        if execution.error_message is not None:
            assert len(execution.error_message) <= 1_000

        expected_rows = 2 if with_fallback else 1
        assert (
            len(db.scalars(select(Execution)).all()) == expected_rows
        )
    finally:
        for _ in sessions:
            pass
