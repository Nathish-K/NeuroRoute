"""Routing Engine orchestration.

Reads the active policy from the environment, selects a model through the
matching strategy, persists the decision, and returns the result to the caller.
"""

import os

from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.exceptions import ConfigurationError, PersistenceError
from app.intelligence.classifier import ComplexityClass
from app.models.model import Model
from app.models.routing_decision import RoutingDecision
from app.routing.strategies import (
    COMPLEXITY_RANKS,
    RoutingPolicy,
    estimate_cost,
    select_baseline,
    select_cost_optimised,
    select_quality_optimised,
)

DEFAULT_POLICY = RoutingPolicy.COST_OPTIMISED
_MAX_EXPLANATION_CHARS = 500


class RoutingResult(BaseModel):
    """The selected model and the rationale behind the selection."""

    model_id: str
    model_db_id: int
    policy: RoutingPolicy
    explanation: str = Field(max_length=_MAX_EXPLANATION_CHARS)
    estimated_cost: Decimal


def _active_policy() -> RoutingPolicy:
    """Resolve the active routing policy from ``ROUTING_POLICY``."""
    configured = os.environ.get("ROUTING_POLICY", "").strip()
    if not configured:
        return DEFAULT_POLICY

    try:
        return RoutingPolicy(configured)
    except ValueError as exc:
        allowed = ", ".join(policy.value for policy in RoutingPolicy)
        raise ConfigurationError(
            f"ROUTING_POLICY must be one of: {allowed}"
        ) from exc


def _baseline_model_id() -> str:
    """Resolve ``BASELINE_MODEL_ID``, required by the baseline policy."""
    baseline_model_id = os.environ.get("BASELINE_MODEL_ID", "").strip()
    if not baseline_model_id:
        raise ConfigurationError("BASELINE_MODEL_ID is not set")

    return baseline_model_id


def _build_explanation(
    policy: RoutingPolicy,
    complexity: ComplexityClass,
    model: Model,
    estimated_cost: Decimal,
    candidate_count: int,
) -> str:
    """Describe why this model was selected, within 500 characters."""
    if policy is RoutingPolicy.BASELINE:
        detail = (
            "fixed baseline configured by BASELINE_MODEL_ID, chosen regardless "
            "of complexity class"
        )
    elif policy is RoutingPolicy.QUALITY_OPTIMISED:
        detail = (
            f"highest context length ({model.max_context_length} tokens) among "
            f"{candidate_count} enabled model(s) with capability tier >= "
            f"{COMPLEXITY_RANKS[complexity]}"
        )
    else:
        detail = (
            f"lowest estimated cost ({estimated_cost}) among "
            f"{candidate_count} enabled model(s)"
        )

    explanation = (
        f"Policy {policy.value} selected model '{model.identifier}' "
        f"for a {complexity} prompt: {detail}."
    )
    return explanation[:_MAX_EXPLANATION_CHARS]


def route_request(
    request_id: int, complexity: ComplexityClass, db: Session
) -> RoutingResult:
    """Select a model for a request, persist the decision, and return it.

    Raises :class:`ConfigurationError` for invalid routing configuration,
    :class:`NoEligibleModelError` when no model qualifies, and
    :class:`PersistenceError` when the decision cannot be stored.
    """
    policy = _active_policy()
    models = list(db.scalars(select(Model)).all())

    if policy is RoutingPolicy.BASELINE:
        model = select_baseline(models, _baseline_model_id())
    elif policy is RoutingPolicy.QUALITY_OPTIMISED:
        model = select_quality_optimised(models, complexity)
    else:
        model = select_cost_optimised(models, complexity)

    estimated_cost = estimate_cost(model, complexity)
    explanation = _build_explanation(
        policy,
        complexity,
        model,
        estimated_cost,
        sum(candidate.enabled for candidate in models),
    )

    decision = RoutingDecision(
        request_id=request_id,
        model_id=model.id,
        policy=policy.value,
        complexity_class=complexity,
        estimated_cost=estimated_cost,
        explanation=explanation,
    )
    try:
        db.add(decision)
        db.commit()
        db.refresh(decision)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(
            "Failed to persist the routing decision"
        ) from exc

    return RoutingResult(
        model_id=model.identifier,
        model_db_id=model.id,
        policy=policy,
        explanation=explanation,
        estimated_cost=estimated_cost,
    )
