"""Shared pytest fixtures for the NeuroRoute backend suite.

Every test runs against in-memory SQLite. An autouse guard blocks the live
MySQL engine/session so a test can never touch the real ``neuroroute`` data.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401  (registers every table on Base)
from app.adapters.base import ExecutionResult, ProviderAdapter
from app.database import connection as _connection
from app.database import dependencies as _dependencies
from app.database.connection import Base
from app.database.dependencies import get_db
from app.main import app
from app.models.model import Model

LIVE_DB_MESSAGE = "Tests must not use the live MySQL session"

# Any test that drives POST /api/requests/ needs a registered model and a
# provider that answers in-process. The text carries coherence markers and
# words from the seeded prompts so the evaluator scores it above zero.
STUB_RESPONSE_TEXT = (
    "Routing depends on prompt complexity, and therefore the adaptive layer "
    "first measures the prompt and then selects a model that fits it."
)
STUB_MODEL_IDENTIFIER = "stub-model"


def _blocked(*_args, **_kwargs):
    raise RuntimeError(LIVE_DB_MESSAGE)


@pytest.fixture(autouse=True)
def block_live_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any use of the live MySQL session or engine raise RuntimeError."""
    monkeypatch.setattr(_connection, "SessionLocal", _blocked)
    monkeypatch.setattr(_dependencies, "SessionLocal", _blocked)
    # Engine is a plain object (no __slots__), so instance attributes can be patched.
    monkeypatch.setattr(_connection.engine, "connect", _blocked)
    monkeypatch.setattr(_connection.engine, "begin", _blocked)


@pytest.fixture()
def engine() -> Iterator[Engine]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture()
def db_session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def test_client(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --- Pipeline test doubles -------------------------------------------------


class StubAdapter(ProviderAdapter):
    """In-process provider that always answers, so no HTTP call is made."""

    async def dispatch(
        self,
        prompt: str,
        model_name: str,
        cost_per_input_token: Decimal = Decimal("0"),
        cost_per_output_token: Decimal = Decimal("0"),
    ) -> ExecutionResult:
        return ExecutionResult(
            response_text=STUB_RESPONSE_TEXT,
            input_token_count=12,
            output_token_count=24,
            latency_ms=1,
            estimated_cost=Decimal("0.0000600000"),
            status="completed",
            error_message=None,
        )


def seed_stub_model(session: Session) -> Model:
    """Register the single model the pipeline routes to in tests.

    Capability tier 3 is the top tier, so escalation never finds a higher-tier
    model and the pipeline stays on one deterministic path.
    """
    model = Model(
        identifier=STUB_MODEL_IDENTIFIER,
        provider_name="stub",
        model_name="stub-model-v1",
        max_context_length=8_192,
        cost_per_input_token=Decimal("0.0000010000"),
        cost_per_output_token=Decimal("0.0000020000"),
        capability_tier=3,
        enabled=True,
    )
    session.add(model)
    session.commit()
    return model


@contextmanager
def stub_provider() -> Iterator[None]:
    """Route every provider lookup to :class:`StubAdapter`."""
    with patch(
        "app.adapters.engine.resolve_adapter",
        side_effect=lambda provider_name: StubAdapter(),
    ):
        yield


@pytest.fixture()
def pipeline_ready(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Make POST /api/requests/ complete: one model, one stub provider.

    Routing configuration is pinned rather than inherited from ``.env``, so the
    pipeline follows the same path on every machine.
    """
    monkeypatch.setenv("ROUTING_POLICY", "cost_optimised")
    monkeypatch.delenv("FALLBACK_MODEL_ID", raising=False)

    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as session:
        seed_stub_model(session)

    with stub_provider():
        yield
