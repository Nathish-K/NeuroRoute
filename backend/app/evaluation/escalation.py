"""Escalation: retry a low-confidence answer on a higher-capability model.

Escalation depth is capped at one, so an execution that is itself the product of
an escalation is never escalated again (Requirement 5.7 depth limit).
"""

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.adapters.engine import execute_request
from app.evaluation.evaluator import (
    ESCALATION_CONFIDENCE_THRESHOLD,
    evaluate_execution,
)
from app.exceptions import ConfigurationError, PersistenceError
from app.models.evaluation import Evaluation
from app.models.execution import Execution
from app.models.model import Model
from app.models.request import Request
from app.models.routing_decision import RoutingDecision
from app.routing.strategies import (
    COMPLEXITY_TOKEN_ESTIMATES,
    RoutingPolicy,
    estimate_cost,
)

_MAX_EXPLANATION_CHARS = 500
_DEFAULT_COMPLEXITY = "moderate"


def _commit(db: Session, message: str) -> None:
    """Commit, converting a database failure into PersistenceError."""
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(message) from exc


def _next_higher_tier_model(db: Session, current_model: Model) -> Model | None:
    """Find the enabled model on the next capability tier above the current one."""
    return db.scalars(
        select(Model)
        .where(
            Model.enabled.is_(True),
            Model.capability_tier > current_model.capability_tier,
        )
        .order_by(Model.capability_tier.asc(), Model.id.asc())
    ).first()


def _escalation_explanation(
    current_model: Model, higher_model: Model, confidence: float
) -> str:
    explanation = (
        f"Escalated from '{current_model.identifier}' "
        f"(tier {current_model.capability_tier}) to "
        f"'{higher_model.identifier}' (tier {higher_model.capability_tier}): "
        f"confidence {confidence:.4f} fell below the escalation threshold "
        f"{ESCALATION_CONFIDENCE_THRESHOLD}."
    )
    return explanation[:_MAX_EXPLANATION_CHARS]


async def handle_escalation(
    original_request: Request,
    evaluation_record: Evaluation,
    db: Session,
) -> Execution | None:
    """Re-run a flagged request on a higher-tier model, if one exists.

    Returns ``None`` when escalation does not apply: the flag is clear, the
    execution is already an escalated attempt, or no higher tier is registered.
    Otherwise returns whichever execution scored higher, the original or the
    escalated one, having persisted the escalated attempt and its evaluation.
    """
    if not evaluation_record.escalation_flag:
        return None

    original_execution = evaluation_record.execution
    if original_execution is None:
        return None

    # Depth cap: an escalated attempt is never escalated again.
    if original_execution.is_escalated:
        return None

    original_decision = original_execution.routing_decision
    if original_decision is None:
        return None

    current_model = original_decision.model
    if current_model is None:
        return None

    higher_model = _next_higher_tier_model(db, current_model)
    if higher_model is None:
        # Nothing better available, so the original response stands.
        evaluation_record.escalation_flag = False
        _commit(db, "Failed to clear the escalation flag")
        return None

    complexity = original_decision.complexity_class
    if complexity not in COMPLEXITY_TOKEN_ESTIMATES:
        complexity = _DEFAULT_COMPLEXITY

    escalated_decision = RoutingDecision(
        request_id=original_request.id,
        model_id=higher_model.id,
        policy=RoutingPolicy.QUALITY_OPTIMISED.value,
        complexity_class=original_decision.complexity_class,
        estimated_cost=estimate_cost(higher_model, complexity),
        explanation=_escalation_explanation(
            current_model, higher_model, evaluation_record.confidence
        ),
    )
    db.add(escalated_decision)
    _commit(db, "Failed to persist the escalated routing decision")
    db.refresh(escalated_decision)

    try:
        escalated_execution = await execute_request(
            escalated_decision.id,
            original_request.prompt,
            higher_model,
            db,
        )
    except ConfigurationError:
        # The escalation target is misconfigured; keep the original response
        # rather than failing a request that already produced an answer.
        return None

    escalated_execution.is_escalated = True
    _commit(db, "Failed to flag the escalated execution")

    escalated_result = evaluate_execution(
        escalated_execution, ESCALATION_CONFIDENCE_THRESHOLD
    )
    db.add(
        Evaluation(
            execution_id=escalated_execution.id,
            quality_score=escalated_result.quality_score,
            confidence=escalated_result.confidence,
            # Forced off: the depth cap forbids a second escalation.
            escalation_flag=False,
        )
    )
    _commit(db, "Failed to persist the escalated evaluation")

    if escalated_result.quality_score > evaluation_record.quality_score:
        return escalated_execution

    # No improvement, so the original answer is the one to serve.
    return original_execution
