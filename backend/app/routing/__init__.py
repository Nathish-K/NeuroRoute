"""Adaptive routing: model-selection policies and the routing orchestrator."""

from app.routing.router import DEFAULT_POLICY, RoutingResult, route_request
from app.routing.strategies import (
    COMPLEXITY_RANKS,
    COMPLEXITY_TOKEN_ESTIMATES,
    RoutingPolicy,
    TokenEstimate,
    estimate_cost,
    select_baseline,
    select_cost_optimised,
    select_quality_optimised,
)

__all__ = [
    "COMPLEXITY_RANKS",
    "COMPLEXITY_TOKEN_ESTIMATES",
    "DEFAULT_POLICY",
    "RoutingPolicy",
    "RoutingResult",
    "TokenEstimate",
    "estimate_cost",
    "route_request",
    "select_baseline",
    "select_cost_optimised",
    "select_quality_optimised",
]
