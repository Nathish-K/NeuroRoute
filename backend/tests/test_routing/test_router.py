"""Tests for the Routing Engine orchestrator."""

import os
from collections.abc import Iterator
from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401  (registers every table on Base)
from app.database.connection import Base
from app.exceptions import (
    ConfigurationError,
    NoEligibleModelError,
    PersistenceError,
)
from app.models.model import Model
from app.models.request import Request
from app.models.routing_decision import RoutingDecision
from app.routing.router import DEFAULT_POLICY, RoutingResult, route_request
from app.routing.strategies import RoutingPolicy, estimate_cost

ROUTING_ENV_KEYS = ("ROUTING_POLICY", "BASELINE_MODEL_ID")


def make_model(
    identifier: str,
    *,
    cost_in: str = "0.0000010000",
    cost_out: str = "0.0000020000",
    context_length: int = 8_000,
    capability_tier: int = 3,
    enabled: bool = True,
) -> Model:
    return Model(
        identifier=identifier,
        provider_name="provider",
        model_name="model",
        max_context_length=context_length,
        cost_per_input_token=Decimal(cost_in),
        cost_per_output_token=Decimal(cost_out),
        capability_tier=capability_tier,
        enabled=enabled,
    )


def seed_registry(db: Session) -> Request:
    """Insert a request plus a cheap model and a high-context model."""
    request = Request(prompt="Explain adaptive routing", status="pending")
    db.add(request)
    db.add_all(
        [
            make_model(
                "b-cheap",
                cost_in="0.0000001000",
                cost_out="0.0000002000",
                context_length=8_000,
            ),
            make_model(
                "a-capable",
                cost_in="0.0010000000",
                cost_out="0.0020000000",
                context_length=200_000,
            ),
        ]
    )
    db.commit()
    return request


@pytest.fixture(autouse=True)
def clear_routing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from ambient routing configuration."""
    for key in ROUTING_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def seeded_request(db_session: Session) -> Request:
    return seed_registry(db_session)


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


def test_route_request_persists_decision_with_correct_fields(
    db_session: Session, seeded_request: Request
) -> None:
    result = route_request(seeded_request.id, "moderate", db_session)

    stored = db_session.scalars(select(RoutingDecision)).one()
    selected = db_session.scalars(
        select(Model).where(Model.identifier == result.model_id)
    ).one()

    assert isinstance(result, RoutingResult)
    assert stored.request_id == seeded_request.id
    assert stored.model_id == selected.id == result.model_db_id
    assert stored.policy == result.policy.value == "cost_optimised"
    assert stored.complexity_class == "moderate"
    assert stored.estimated_cost == result.estimated_cost
    assert stored.explanation == result.explanation
    assert stored.created_at is not None


def test_route_request_returns_expected_cost_and_explanation(
    db_session: Session, seeded_request: Request
) -> None:
    result = route_request(seeded_request.id, "moderate", db_session)
    cheapest = db_session.scalars(
        select(Model).where(Model.identifier == "b-cheap")
    ).one()

    assert result.model_id == "b-cheap"
    assert result.estimated_cost == estimate_cost(cheapest, "moderate")
    assert "cost_optimised" in result.explanation
    assert "b-cheap" in result.explanation
    assert len(result.explanation) <= 500


def test_unset_routing_policy_uses_cost_optimised_default(
    db_session: Session, seeded_request: Request
) -> None:
    assert "ROUTING_POLICY" not in os.environ

    result = route_request(seeded_request.id, "complex", db_session)

    assert result.policy is DEFAULT_POLICY is RoutingPolicy.COST_OPTIMISED
    assert result.model_id == "b-cheap"


@pytest.mark.parametrize(
    ("policy", "expected_model"),
    [
        ("cost_optimised", "b-cheap"),
        ("quality_optimised", "a-capable"),
    ],
)
def test_routing_policy_env_var_is_respected(
    db_session: Session,
    seeded_request: Request,
    monkeypatch: pytest.MonkeyPatch,
    policy: str,
    expected_model: str,
) -> None:
    monkeypatch.setenv("ROUTING_POLICY", policy)

    result = route_request(seeded_request.id, "complex", db_session)

    assert result.policy.value == policy
    assert result.model_id == expected_model

    stored = db_session.scalars(select(RoutingDecision)).one()
    assert stored.policy == policy


def test_baseline_policy_selects_configured_model(
    db_session: Session,
    seeded_request: Request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTING_POLICY", "baseline")
    monkeypatch.setenv("BASELINE_MODEL_ID", "a-capable")

    result = route_request(seeded_request.id, "simple", db_session)

    assert result.policy is RoutingPolicy.BASELINE
    assert result.model_id == "a-capable"


def test_baseline_policy_is_deterministic_across_calls(
    db_session: Session,
    seeded_request: Request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTING_POLICY", "baseline")
    monkeypatch.setenv("BASELINE_MODEL_ID", "a-capable")

    first = route_request(seeded_request.id, "simple", db_session)
    second = route_request(seeded_request.id, "complex", db_session)

    assert first.model_id == second.model_id == "a-capable"
    assert first.model_db_id == second.model_db_id


def test_baseline_policy_without_configured_id_raises_configuration_error(
    db_session: Session,
    seeded_request: Request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTING_POLICY", "baseline")

    with pytest.raises(
        ConfigurationError, match="^BASELINE_MODEL_ID is not set$"
    ):
        route_request(seeded_request.id, "simple", db_session)


def test_baseline_policy_with_disabled_model_raises_no_eligible_model(
    db_session: Session,
    seeded_request: Request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.add(make_model("c-disabled", enabled=False))
    db_session.commit()
    monkeypatch.setenv("ROUTING_POLICY", "baseline")
    monkeypatch.setenv("BASELINE_MODEL_ID", "c-disabled")

    with pytest.raises(
        NoEligibleModelError, match="^Baseline model unavailable$"
    ):
        route_request(seeded_request.id, "simple", db_session)


def test_unknown_routing_policy_raises_configuration_error(
    db_session: Session,
    seeded_request: Request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTING_POLICY", "cheapest-please")

    with pytest.raises(ConfigurationError, match="ROUTING_POLICY must be one of"):
        route_request(seeded_request.id, "simple", db_session)


def test_empty_registry_raises_no_eligible_model(db_session: Session) -> None:
    request = Request(prompt="No models registered", status="pending")
    db_session.add(request)
    db_session.commit()

    with pytest.raises(NoEligibleModelError):
        route_request(request.id, "simple", db_session)


def test_database_write_failure_raises_persistence_error(
    db_session: Session,
    seeded_request: Request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rolled_back: list[bool] = []

    def failing_commit() -> None:
        raise SQLAlchemyError("simulated write failure")

    def tracking_rollback() -> None:
        rolled_back.append(True)

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracking_rollback)

    with pytest.raises(
        PersistenceError, match="^Failed to persist the routing decision$"
    ):
        route_request(seeded_request.id, "moderate", db_session)

    assert rolled_back == [True]


def test_no_decision_is_visible_after_a_write_failure(
    db_session: Session,
    seeded_request: Request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_commit() -> None:
        raise SQLAlchemyError("simulated write failure")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(PersistenceError):
        route_request(seeded_request.id, "moderate", db_session)

    monkeypatch.undo()
    db_session.rollback()

    assert db_session.scalars(select(RoutingDecision)).all() == []


def model_spec_strategy() -> st.SearchStrategy[dict]:
    """Model field values, built into ORM objects inside each example."""
    return st.fixed_dictionaries(
        {
            "identifier": st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
                min_size=1,
                max_size=16,
            ),
            "cost_in": st.decimals(
                min_value=Decimal("0"), max_value=Decimal("1"), places=10
            ).map(str),
            "cost_out": st.decimals(
                min_value=Decimal("0"), max_value=Decimal("1"), places=10
            ).map(str),
            "context_length": st.integers(min_value=1, max_value=2_000_000),
            "capability_tier": st.integers(min_value=1, max_value=3),
            "enabled": st.booleans(),
        }
    )


# Feature: neuroroute-mvp, Property 7: Routing Decision Round-Trip
# Validates: Requirements 3.8
@given(
    specs=st.lists(
        model_spec_strategy(),
        min_size=1,
        max_size=6,
        unique_by=lambda spec: spec["identifier"],
    ),
    complexity=st.sampled_from(["simple", "moderate", "complex"]),
    policy=st.sampled_from(["cost_optimised", "quality_optimised"]),
)
@settings(max_examples=100, deadline=None)
def test_routing_decision_round_trip(
    specs: list[dict], complexity: str, policy: str
) -> None:
    sessions = _inline_session()
    db = next(sessions)
    try:
        request = Request(prompt="Round-trip prompt", status="pending")
        db.add(request)
        db.add_all([make_model(**spec) for spec in specs])
        db.commit()

        previous_policy = os.environ.get("ROUTING_POLICY")
        os.environ["ROUTING_POLICY"] = policy
        try:
            result = route_request(request.id, complexity, db)
        except NoEligibleModelError:
            # No model qualified, so nothing may be persisted.
            assert db.scalars(select(RoutingDecision)).all() == []
            return
        finally:
            if previous_policy is None:
                os.environ.pop("ROUTING_POLICY", None)
            else:
                os.environ["ROUTING_POLICY"] = previous_policy

        stored = db.scalars(
            select(RoutingDecision).where(
                RoutingDecision.request_id == request.id
            )
        ).one()
        selected = db.scalars(
            select(Model).where(Model.id == stored.model_id)
        ).one()

        assert stored.model_id == result.model_db_id
        assert selected.identifier == result.model_id
        assert selected.enabled is True
        assert stored.policy == result.policy.value == policy
        assert stored.complexity_class == complexity
        assert stored.estimated_cost == result.estimated_cost
        assert stored.explanation == result.explanation
    finally:
        for _ in sessions:
            pass
