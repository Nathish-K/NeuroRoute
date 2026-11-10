"""Tests for the Routing Engine model-selection strategies."""

from decimal import Decimal, ROUND_HALF_UP

import pytest
from hypothesis import given, settings, strategies as st

from app.exceptions import NoEligibleModelError, ServiceUnavailableError
from app.models.model import Model
from app.routing.strategies import (
    COMPLEXITY_RANKS,
    COMPLEXITY_TOKEN_ESTIMATES,
    RoutingPolicy,
    estimate_cost,
    select_baseline,
    select_cost_optimised,
    select_quality_optimised,
)

COST_QUANTUM = Decimal("0.0000000001")


def make_model(
    identifier: str,
    *,
    cost_in: str = "0.0000010000",
    cost_out: str = "0.0000020000",
    context_length: int = 8_000,
    capability_tier: int = 3,
    enabled: bool = True,
) -> Model:
    """Build an unsaved Model record for strategy tests."""
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


def expected_cost(model: Model, complexity: str) -> Decimal:
    """Independent cost oracle: priced from the published token estimates."""
    estimate = COMPLEXITY_TOKEN_ESTIMATES[complexity]
    total = (
        estimate.input_tokens * model.cost_per_input_token
        + estimate.output_tokens * model.cost_per_output_token
    )
    return total.quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)


def model_strategy() -> st.SearchStrategy[Model]:
    """Valid models with non-negative costs and a positive context length."""
    return st.builds(
        make_model,
        identifier=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=1,
            max_size=16,
        ),
        cost_in=st.decimals(
            min_value=Decimal("0"), max_value=Decimal("1"), places=10
        ).map(str),
        cost_out=st.decimals(
            min_value=Decimal("0"), max_value=Decimal("1"), places=10
        ).map(str),
        context_length=st.integers(min_value=1, max_value=2_000_000),
        capability_tier=st.integers(min_value=1, max_value=3),
        enabled=st.booleans(),
    )


def model_list_strategy(min_size: int = 1) -> st.SearchStrategy[list[Model]]:
    """Lists of models with distinct identifiers."""
    return st.lists(
        model_strategy(),
        min_size=min_size,
        max_size=8,
        unique_by=lambda model: model.identifier,
    )


def complexity_class_strategy() -> st.SearchStrategy[str]:
    return st.sampled_from(["simple", "moderate", "complex"])


def test_routing_policy_values() -> None:
    assert RoutingPolicy.COST_OPTIMISED.value == "cost_optimised"
    assert RoutingPolicy.QUALITY_OPTIMISED.value == "quality_optimised"
    assert RoutingPolicy.BASELINE.value == "baseline"


def test_cost_optimised_with_single_enabled_model_selects_it() -> None:
    only = make_model("only-model")

    assert select_cost_optimised([only], "moderate") is only


def test_cost_optimised_selects_cheapest_model() -> None:
    cheap = make_model("z-cheap", cost_in="0.0000001000", cost_out="0.0000002000")
    pricey = make_model("a-pricey", cost_in="0.0010000000", cost_out="0.0020000000")

    assert select_cost_optimised([pricey, cheap], "moderate") is cheap


def test_cost_optimised_tie_selects_lexicographically_first_identifier() -> None:
    first = make_model("alpha")
    second = make_model("beta")

    selected = select_cost_optimised([second, first], "moderate")

    assert expected_cost(first, "moderate") == expected_cost(second, "moderate")
    assert selected is first


def test_cost_optimised_ignores_disabled_models() -> None:
    disabled_cheap = make_model(
        "a-disabled", cost_in="0", cost_out="0", enabled=False
    )
    enabled = make_model("b-enabled")

    assert select_cost_optimised([disabled_cheap, enabled], "simple") is enabled


@pytest.mark.parametrize(
    "models",
    [
        [],
        [make_model("only-disabled", enabled=False)],
        [
            make_model("first-disabled", enabled=False),
            make_model("second-disabled", enabled=False),
        ],
    ],
)
def test_cost_optimised_without_enabled_models_raises(
    models: list[Model],
) -> None:
    with pytest.raises(NoEligibleModelError):
        select_cost_optimised(models, "moderate")


def test_quality_optimised_selects_highest_context_eligible_model() -> None:
    small = make_model("a-small", context_length=8_000, capability_tier=3)
    large = make_model("b-large", context_length=200_000, capability_tier=3)
    under_tier = make_model("c-huge", context_length=900_000, capability_tier=1)

    selected = select_quality_optimised([small, large, under_tier], "complex")

    assert selected is large


def test_quality_optimised_tie_selects_lexicographically_first_identifier() -> None:
    first = make_model("alpha", context_length=32_000)
    second = make_model("beta", context_length=32_000)

    assert select_quality_optimised([second, first], "simple") is first


@pytest.mark.parametrize(
    ("complexity", "tier", "eligible"),
    [
        ("simple", 1, True),
        ("moderate", 1, False),
        ("moderate", 2, True),
        ("complex", 2, False),
        ("complex", 3, True),
    ],
)
def test_quality_optimised_requires_capability_tier_at_least_rank(
    complexity: str, tier: int, eligible: bool
) -> None:
    model = make_model("candidate", capability_tier=tier)

    if eligible:
        assert select_quality_optimised([model], complexity) is model
    else:
        with pytest.raises(NoEligibleModelError):
            select_quality_optimised([model], complexity)


def test_quality_optimised_ignores_disabled_models() -> None:
    disabled = make_model("a-disabled", context_length=900_000, enabled=False)
    enabled = make_model("b-enabled", context_length=1_000)

    assert select_quality_optimised([disabled, enabled], "simple") is enabled


def test_baseline_selects_enabled_configured_model() -> None:
    target = make_model("baseline-model")
    other = make_model("other-model")

    assert select_baseline([other, target], "baseline-model") is target


def test_baseline_with_disabled_model_raises() -> None:
    disabled = make_model("baseline-model", enabled=False)

    with pytest.raises(
        NoEligibleModelError, match="^Baseline model unavailable$"
    ):
        select_baseline([disabled], "baseline-model")


def test_baseline_with_unknown_identifier_raises() -> None:
    with pytest.raises(
        NoEligibleModelError, match="^Baseline model unavailable$"
    ):
        select_baseline([make_model("some-other-model")], "baseline-model")


def test_no_eligible_model_error_maps_to_service_unavailable() -> None:
    assert issubclass(NoEligibleModelError, ServiceUnavailableError)


def test_estimate_cost_matches_published_token_estimates() -> None:
    model = make_model(
        "priced", cost_in="0.0000015000", cost_out="0.0000060000"
    )

    # moderate = 200 input tokens, 600 output tokens.
    assert estimate_cost(model, "moderate") == Decimal("0.0039000000")
    assert estimate_cost(model, "moderate") == expected_cost(model, "moderate")


# Feature: neuroroute-mvp, Property 3: Disabled Models Excluded from Routing
# Validates: Requirements 1.7, 3.3, 3.4
@given(models=model_list_strategy(), complexity=complexity_class_strategy())
@settings(max_examples=100, deadline=None)
def test_disabled_models_are_excluded_from_routing(
    models: list[Model], complexity: str
) -> None:
    has_enabled = any(model.enabled for model in models)

    for strategy in (select_cost_optimised, select_quality_optimised):
        try:
            selected = strategy(models, complexity)
        except NoEligibleModelError:
            continue
        assert selected.enabled is True
        assert selected in models

    if not has_enabled:
        with pytest.raises(NoEligibleModelError):
            select_cost_optimised(models, complexity)
        with pytest.raises(NoEligibleModelError):
            select_quality_optimised(models, complexity)


# Feature: neuroroute-mvp, Property 6: Cost-Optimised Selection Minimises Cost
# Validates: Requirements 3.3
@given(models=model_list_strategy(), complexity=complexity_class_strategy())
@settings(max_examples=100, deadline=None)
def test_cost_optimised_selection_minimises_cost(
    models: list[Model], complexity: str
) -> None:
    eligible = [model for model in models if model.enabled]
    if not eligible:
        with pytest.raises(NoEligibleModelError):
            select_cost_optimised(models, complexity)
        return

    selected = select_cost_optimised(models, complexity)
    selected_cost = expected_cost(selected, complexity)

    assert selected.enabled is True
    assert all(
        selected_cost <= expected_cost(candidate, complexity)
        for candidate in eligible
    )

    tied = [
        candidate
        for candidate in eligible
        if expected_cost(candidate, complexity) == selected_cost
    ]
    assert selected.identifier == min(
        candidate.identifier for candidate in tied
    )


# Feature: neuroroute-mvp, Property 6 (quality policy eligibility)
# Validates: Requirements 3.4
@given(models=model_list_strategy(), complexity=complexity_class_strategy())
@settings(max_examples=100, deadline=None)
def test_quality_optimised_selects_highest_context_among_eligible(
    models: list[Model], complexity: str
) -> None:
    required_rank = COMPLEXITY_RANKS[complexity]
    eligible = [
        model
        for model in models
        if model.enabled and model.capability_tier >= required_rank
    ]
    if not eligible:
        with pytest.raises(NoEligibleModelError):
            select_quality_optimised(models, complexity)
        return

    selected = select_quality_optimised(models, complexity)
    highest = max(candidate.max_context_length for candidate in eligible)

    assert selected.max_context_length == highest
    assert selected.capability_tier >= required_rank
    assert selected.identifier == min(
        candidate.identifier
        for candidate in eligible
        if candidate.max_context_length == highest
    )


# Feature: neuroroute-mvp, Property 8: Baseline Router Determinism
# Validates: Requirements 3.5
@given(models=model_list_strategy(), index=st.integers(min_value=0))
@settings(max_examples=100, deadline=None)
def test_baseline_router_is_deterministic(
    models: list[Model], index: int
) -> None:
    baseline_model_id = models[index % len(models)].identifier

    try:
        first = select_baseline(models, baseline_model_id)
    except NoEligibleModelError as exc:
        assert str(exc) == "Baseline model unavailable"
        with pytest.raises(NoEligibleModelError):
            select_baseline(models, baseline_model_id)
        return

    second = select_baseline(models, baseline_model_id)

    assert first is second
    assert first.identifier == baseline_model_id
    assert first.enabled is True
