"""Model selection strategies for the Routing Engine.

Each strategy is pure: it receives the candidate models plus the request's
complexity class and returns exactly one model, or raises
:class:`NoEligibleModelError` when nothing qualifies.
"""

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import NamedTuple

from app.exceptions import NoEligibleModelError
from app.intelligence.classifier import ComplexityClass
from app.models.model import Model

_COST_QUANTUM = Decimal("0.0000000001")  # 10 decimal places

# Capability ranks for the ordered tiers LOW < MEDIUM < HIGH.
COMPLEXITY_RANKS: dict[ComplexityClass, int] = {
    "simple": 1,
    "moderate": 2,
    "complex": 3,
}


class RoutingPolicy(str, Enum):
    """The supported model-selection policies."""

    COST_OPTIMISED = "cost_optimised"
    QUALITY_OPTIMISED = "quality_optimised"
    BASELINE = "baseline"


class TokenEstimate(NamedTuple):
    """Expected input/output token workload for a complexity class."""

    input_tokens: int
    output_tokens: int


# Representative workload per complexity class, used only to rank models by
# cost before execution. The input figures track the classifier's own token
# thresholds (simple < 50, moderate 50-199, complex >= 200). Every model is
# priced against the same estimate, so the ranking reflects pricing alone.
COMPLEXITY_TOKEN_ESTIMATES: dict[ComplexityClass, TokenEstimate] = {
    "simple": TokenEstimate(input_tokens=50, output_tokens=150),
    "moderate": TokenEstimate(input_tokens=200, output_tokens=600),
    "complex": TokenEstimate(input_tokens=1_000, output_tokens=2_000),
}


def estimate_cost(model: Model, complexity: ComplexityClass) -> Decimal:
    """Estimate the total cost of serving a request of this complexity.

    ``(input_tokens x cost_per_input_token) + (output_tokens x
    cost_per_output_token)``, rounded to 10 decimal places.
    """
    estimate = COMPLEXITY_TOKEN_ESTIMATES[complexity]
    total = (
        estimate.input_tokens * model.cost_per_input_token
        + estimate.output_tokens * model.cost_per_output_token
    )
    return Decimal(total).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)


def _enabled_models(models: list[Model]) -> list[Model]:
    """Keep only models that are enabled for routing."""
    return [model for model in models if model.enabled]


def select_cost_optimised(
    models: list[Model], complexity: ComplexityClass
) -> Model:
    """Select the enabled model with the lowest estimated cost.

    Ties on cost are broken by the lexicographically first identifier.
    """
    eligible = _enabled_models(models)
    if not eligible:
        raise NoEligibleModelError(
            "No suitable model is available for the cost_optimised policy"
        )

    return min(
        eligible,
        key=lambda model: (estimate_cost(model, complexity), model.identifier),
    )


def select_quality_optimised(
    models: list[Model], complexity: ComplexityClass
) -> Model:
    """Select the highest-context enabled model that can serve the complexity.

    Only models whose ``capability_tier`` is at least the complexity rank are
    eligible. Ties on context length are broken by the lexicographically first
    identifier.
    """
    required_rank = COMPLEXITY_RANKS[complexity]
    eligible = [
        model
        for model in _enabled_models(models)
        if model.capability_tier >= required_rank
    ]
    if not eligible:
        raise NoEligibleModelError(
            "No suitable model is available for the quality_optimised policy"
        )

    return min(
        eligible,
        key=lambda model: (-model.max_context_length, model.identifier),
    )


def select_baseline(models: list[Model], baseline_model_id: str) -> Model:
    """Select the configured baseline model, ignoring complexity and policy."""
    for model in models:
        if model.identifier == baseline_model_id and model.enabled:
            return model

    raise NoEligibleModelError("Baseline model unavailable")
