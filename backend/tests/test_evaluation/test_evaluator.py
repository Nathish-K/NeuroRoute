"""Tests for the Evaluation Service and the escalation handler."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import ExecutionResult
from app.adapters.ollama_adapter import OllamaAdapter
from app.evaluation.escalation import handle_escalation
from app.evaluation.evaluator import (
    THRESHOLD_ENV_VAR,
    EvaluationResult,
    evaluate_execution,
    load_threshold,
)
from app.exceptions import ConfigurationError
from app.models.evaluation import Evaluation
from app.models.execution import Execution
from app.models.model import Model
from app.models.request import Request
from app.models.routing_decision import RoutingDecision

PROMPT = "Explain adaptive routing"
LOW_QUALITY = "no."
HIGH_QUALITY = (
    "Routing works because the engine compares cost and capability. "
    "Therefore the cheapest eligible model is selected. "
    "In summary, routing explains its choice clearly and completely."
)
TERMINAL_STATUSES = ["completed", "failed", "timed_out", "pending"]


def build_execution(
    *,
    status: str = "completed",
    response_text: str | None = HIGH_QUALITY,
    prompt: str = PROMPT,
    is_escalated: bool = False,
) -> Execution:
    """An Execution wired to a request, without touching a database."""
    decision = RoutingDecision(
        request_id=1,
        model_id=1,
        policy="cost_optimised",
        complexity_class="moderate",
        estimated_cost=Decimal("0"),
        explanation="original",
    )
    decision.request = Request(prompt=prompt, status="pending")

    execution = Execution(
        routing_decision_id=1,
        response_text=response_text,
        input_token_count=5,
        output_token_count=5,
        latency_ms=10,
        estimated_cost=Decimal("0"),
        status=status,
        error_message=None if status == "completed" else "provider error",
        is_escalated=is_escalated,
    )
    execution.routing_decision = decision
    return execution


def make_model(
    identifier: str,
    capability_tier: int,
    *,
    provider_name: str = "ollama",
    enabled: bool = True,
) -> Model:
    return Model(
        identifier=identifier,
        provider_name=provider_name,
        model_name=f"{identifier}-model",
        max_context_length=8_192,
        cost_per_input_token=Decimal("0.0000010000"),
        cost_per_output_token=Decimal("0.0000020000"),
        capability_tier=capability_tier,
        enabled=enabled,
    )


def seed_escalation_case(
    db: Session,
    tiers: list[tuple[str, int, bool]],
    *,
    response_text: str = LOW_QUALITY,
    is_escalated: bool = False,
    escalation_flag: bool = True,
) -> tuple[Request, Execution, Evaluation]:
    """Persist a request, a model registry, and a scored first attempt."""
    request = Request(prompt=PROMPT, status="pending")
    db.add(request)
    models = [
        make_model(identifier, tier, enabled=enabled)
        for identifier, tier, enabled in tiers
    ]
    db.add_all(models)
    db.commit()

    decision = RoutingDecision(
        request_id=request.id,
        model_id=models[0].id,
        policy="cost_optimised",
        complexity_class="moderate",
        estimated_cost=Decimal("0.0001000000"),
        explanation="original",
    )
    db.add(decision)
    db.commit()

    execution = Execution(
        routing_decision_id=decision.id,
        response_text=response_text,
        input_token_count=5,
        output_token_count=5,
        latency_ms=10,
        estimated_cost=Decimal("0.0000100000"),
        status="completed",
        error_message=None,
        is_escalated=is_escalated,
    )
    db.add(execution)
    db.commit()

    scored = evaluate_execution(execution, 0.9)
    evaluation = Evaluation(
        execution_id=execution.id,
        quality_score=scored.quality_score,
        confidence=scored.confidence,
        escalation_flag=escalation_flag,
    )
    db.add(evaluation)
    db.commit()
    return request, execution, evaluation


def stub_dispatch(
    *, response_text: str = HIGH_QUALITY, status: str = "completed"
):
    """Patch the Ollama adapter used by the escalated execution."""
    return patch.object(
        OllamaAdapter,
        "dispatch",
        AsyncMock(
            return_value=ExecutionResult(
                response_text=response_text,
                input_token_count=9,
                output_token_count=19,
                latency_ms=7,
                estimated_cost=Decimal("0.0000470000"),
                status=status,
                error_message=None if status == "completed" else "provider error",
            )
        ),
    )


@pytest.fixture(autouse=True)
def escalation_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the Ollama base URL and clear any ambient fallback setting."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.delenv("FALLBACK_MODEL_ID", raising=False)


# --------------------------------------------------------------------------
# Threshold configuration (Requirement 5.3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_value",
    ["abc", "-0.1", "1.1", "nan", "inf", "-inf", "", "   "],
)
def test_invalid_threshold_is_rejected(
    monkeypatch: pytest.MonkeyPatch, raw_value: str
) -> None:
    monkeypatch.setenv(THRESHOLD_ENV_VAR, raw_value)

    with pytest.raises(ConfigurationError, match=THRESHOLD_ENV_VAR):
        load_threshold()


def test_absent_threshold_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(THRESHOLD_ENV_VAR, raising=False)

    with pytest.raises(ConfigurationError, match="is not set"):
        load_threshold()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("0", 0.0), ("0.0", 0.0), ("0.5", 0.5), ("1", 1.0), ("1.0", 1.0)],
)
def test_valid_threshold_is_accepted(
    monkeypatch: pytest.MonkeyPatch, raw_value: str, expected: float
) -> None:
    monkeypatch.setenv(THRESHOLD_ENV_VAR, raw_value)

    assert load_threshold() == expected


# --------------------------------------------------------------------------
# evaluate_execution
# --------------------------------------------------------------------------


def test_completed_execution_scores_within_bounds() -> None:
    result = evaluate_execution(build_execution(), 0.5)

    assert isinstance(result, EvaluationResult)
    assert 0.0 <= result.quality_score <= 1.0
    assert 0.0 <= result.confidence <= 1.0


def test_completed_execution_confidence_includes_status_credit() -> None:
    result = evaluate_execution(build_execution(), 0.5)

    # confidence = 0.5 * quality + 0.5 for a completed attempt.
    assert result.confidence == pytest.approx(0.5 * result.quality_score + 0.5)
    assert result.confidence >= 0.5


def test_richer_response_scores_higher_than_a_terse_one() -> None:
    terse = evaluate_execution(build_execution(response_text=LOW_QUALITY), 0.5)
    rich = evaluate_execution(build_execution(response_text=HIGH_QUALITY), 0.5)

    assert rich.quality_score > terse.quality_score


def test_evaluation_is_idempotent() -> None:
    execution = build_execution()

    assert evaluate_execution(execution, 0.5) == evaluate_execution(
        execution, 0.5
    )


@pytest.mark.parametrize("status", ["failed", "timed_out", "pending"])
def test_unsuccessful_execution_scores_zero_and_flags_escalation(
    status: str,
) -> None:
    result = evaluate_execution(
        build_execution(status=status, response_text=HIGH_QUALITY), 0.5
    )

    assert result.quality_score == 0.0
    assert result.confidence == 0.0
    assert result.escalation_flag is True


def test_failed_execution_with_zero_threshold_is_not_flagged() -> None:
    # The rule is a strict comparison, so 0.0 < 0.0 is False.
    result = evaluate_execution(build_execution(status="failed"), 0.0)

    assert result.quality_score == 0.0
    assert result.escalation_flag is False


def test_escalation_flag_is_set_when_confidence_is_below_threshold() -> None:
    result = evaluate_execution(build_execution(), 1.0)

    assert result.confidence < 1.0
    assert result.escalation_flag is True


def test_escalation_flag_is_clear_when_confidence_meets_threshold() -> None:
    result = evaluate_execution(build_execution(), 0.0)

    assert result.confidence >= 0.0
    assert result.escalation_flag is False


def test_empty_response_scores_zero_quality_but_keeps_status_credit() -> None:
    result = evaluate_execution(build_execution(response_text=""), 0.5)

    assert result.quality_score == 0.0
    assert result.confidence == 0.5
    assert result.escalation_flag is False


def test_missing_response_text_is_tolerated() -> None:
    result = evaluate_execution(build_execution(response_text=None), 0.5)

    assert result.quality_score == 0.0


def test_unreachable_prompt_scores_no_overlap() -> None:
    orphan = Execution(
        routing_decision_id=99,
        response_text="A standalone answer, therefore coherent.",
        input_token_count=1,
        output_token_count=1,
        latency_ms=1,
        estimated_cost=Decimal("0"),
        status="completed",
        error_message=None,
        is_escalated=False,
    )

    result = evaluate_execution(orphan, 0.5)

    assert 0.0 <= result.quality_score <= 1.0


# --------------------------------------------------------------------------
# handle_escalation
# --------------------------------------------------------------------------


async def test_escalation_skipped_when_flag_is_clear(
    db_session: Session,
) -> None:
    request, _, evaluation = seed_escalation_case(
        db_session,
        [("tier1", 1, True), ("tier3", 3, True)],
        escalation_flag=False,
    )

    with stub_dispatch():
        assert await handle_escalation(request, evaluation, db_session) is None

    assert len(db_session.scalars(select(Execution)).all()) == 1
    assert len(db_session.scalars(select(RoutingDecision)).all()) == 1


async def test_escalation_skipped_when_no_higher_tier_exists(
    db_session: Session,
) -> None:
    request, _, evaluation = seed_escalation_case(
        db_session, [("tier3", 3, True), ("other-tier3", 3, True)]
    )

    with stub_dispatch():
        assert await handle_escalation(request, evaluation, db_session) is None

    db_session.refresh(evaluation)
    assert evaluation.escalation_flag is False
    assert len(db_session.scalars(select(Execution)).all()) == 1


async def test_escalation_skipped_when_higher_tier_is_disabled(
    db_session: Session,
) -> None:
    request, _, evaluation = seed_escalation_case(
        db_session, [("tier1", 1, True), ("tier3", 3, False)]
    )

    with stub_dispatch():
        assert await handle_escalation(request, evaluation, db_session) is None

    db_session.refresh(evaluation)
    assert evaluation.escalation_flag is False


async def test_escalation_skipped_when_execution_is_already_escalated(
    db_session: Session,
) -> None:
    request, _, evaluation = seed_escalation_case(
        db_session,
        [("tier1", 1, True), ("tier3", 3, True)],
        is_escalated=True,
    )

    with stub_dispatch():
        assert await handle_escalation(request, evaluation, db_session) is None

    # Depth cap must not clear the flag, which records that it was triggered.
    db_session.refresh(evaluation)
    assert evaluation.escalation_flag is True
    assert len(db_session.scalars(select(Execution)).all()) == 1


async def test_escalation_selects_the_next_higher_tier(
    db_session: Session,
) -> None:
    request, _, evaluation = seed_escalation_case(
        db_session,
        [("tier1", 1, True), ("tier2", 2, True), ("tier3", 3, True)],
    )

    with stub_dispatch():
        await handle_escalation(request, evaluation, db_session)

    decisions = db_session.scalars(
        select(RoutingDecision).order_by(RoutingDecision.id)
    ).all()
    escalated_model = db_session.get(Model, decisions[1].model_id)

    assert len(decisions) == 2
    assert escalated_model.identifier == "tier2"
    assert decisions[1].policy == "quality_optimised"
    assert decisions[1].request_id == request.id
    assert len(decisions[1].explanation) <= 500


async def test_escalation_records_attempt_and_returns_better_execution(
    db_session: Session,
) -> None:
    request, original, evaluation = seed_escalation_case(
        db_session, [("tier1", 1, True), ("tier3", 3, True)]
    )
    original_quality = evaluation.quality_score

    with stub_dispatch(response_text=HIGH_QUALITY):
        returned = await handle_escalation(request, evaluation, db_session)

    executions = db_session.scalars(
        select(Execution).order_by(Execution.id)
    ).all()
    evaluations = db_session.scalars(
        select(Evaluation).order_by(Evaluation.id)
    ).all()

    assert len(executions) == 2
    assert len(evaluations) == 2
    assert executions[1].is_escalated is True
    assert evaluations[1].execution_id == executions[1].id
    assert evaluations[1].quality_score > original_quality
    # Depth cap: the escalated evaluation is never flagged for escalation.
    assert evaluations[1].escalation_flag is False
    assert returned is not None
    assert returned.id == executions[1].id
    assert returned.id != original.id


async def test_escalation_returns_original_when_quality_does_not_improve(
    db_session: Session,
) -> None:
    request, original, evaluation = seed_escalation_case(
        db_session,
        [("tier1", 1, True), ("tier3", 3, True)],
        response_text=HIGH_QUALITY,
    )
    original_quality = evaluation.quality_score

    with stub_dispatch(response_text=LOW_QUALITY):
        returned = await handle_escalation(request, evaluation, db_session)

    evaluations = db_session.scalars(
        select(Evaluation).order_by(Evaluation.id)
    ).all()

    # The escalated attempt is still recorded, even though it lost.
    assert len(db_session.scalars(select(Execution)).all()) == 2
    assert evaluations[1].quality_score <= original_quality
    assert returned is not None
    assert returned.id == original.id


async def test_failed_escalated_attempt_is_scored_zero(
    db_session: Session,
) -> None:
    request, original, evaluation = seed_escalation_case(
        db_session, [("tier1", 1, True), ("tier3", 3, True)]
    )

    with stub_dispatch(response_text="", status="failed"):
        returned = await handle_escalation(request, evaluation, db_session)

    evaluations = db_session.scalars(
        select(Evaluation).order_by(Evaluation.id)
    ).all()

    assert evaluations[1].quality_score == 0.0
    assert evaluations[1].escalation_flag is False
    assert returned is not None
    assert returned.id == original.id


async def test_misconfigured_escalation_target_preserves_original(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _, evaluation = seed_escalation_case(
        db_session, [("tier1", 1, True), ("tier3", 3, True)]
    )
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    returned = await handle_escalation(request, evaluation, db_session)

    assert returned is None
    assert len(db_session.scalars(select(Execution)).all()) == 1


# --------------------------------------------------------------------------
# Properties
# --------------------------------------------------------------------------


# Feature: neuroroute-mvp, Property 13: Evaluation Score Bounds
# Validates: Requirements 5.1
@given(
    status=st.sampled_from(TERMINAL_STATUSES),
    response_text=st.one_of(st.none(), st.text(max_size=800)),
    prompt=st.text(min_size=1, max_size=200),
    threshold=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=100, deadline=None)
def test_evaluation_scores_stay_within_bounds(
    status: str,
    response_text: str | None,
    prompt: str,
    threshold: float,
) -> None:
    result = evaluate_execution(
        build_execution(
            status=status, response_text=response_text, prompt=prompt
        ),
        threshold,
    )

    assert isinstance(result, EvaluationResult)
    assert 0.0 <= result.quality_score <= 1.0
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.escalation_flag, bool)


# Feature: neuroroute-mvp, Property 14: Escalation Flag Rule
# Validates: Requirements 5.4
@given(
    status=st.sampled_from(TERMINAL_STATUSES),
    response_text=st.one_of(st.none(), st.text(max_size=800)),
    threshold=st.one_of(
        # Exact boundary values, where a strict and non-strict comparison differ.
        st.sampled_from([0.0, 0.5, 1.0]),
        st.floats(min_value=0.0, max_value=1.0),
    ),
)
@settings(max_examples=100, deadline=None)
def test_escalation_flag_equals_confidence_below_threshold(
    status: str, response_text: str | None, threshold: float
) -> None:
    execution = build_execution(status=status, response_text=response_text)
    result = evaluate_execution(execution, threshold)

    assert result.escalation_flag == (result.confidence < threshold)

    # Pin the equality case: the comparison is strict, so a threshold equal to
    # the confidence must never flag for escalation.
    at_boundary = evaluate_execution(execution, result.confidence)
    assert at_boundary.escalation_flag is False


# Feature: neuroroute-mvp, Property 13 (idempotence invariant)
# Validates: Requirements 5.1
@given(
    status=st.sampled_from(TERMINAL_STATUSES),
    response_text=st.one_of(st.none(), st.text(max_size=800)),
    threshold=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=100, deadline=None)
def test_evaluation_is_deterministic(
    status: str, response_text: str | None, threshold: float
) -> None:
    execution = build_execution(status=status, response_text=response_text)

    assert evaluate_execution(execution, threshold) == evaluate_execution(
        execution, threshold
    )
