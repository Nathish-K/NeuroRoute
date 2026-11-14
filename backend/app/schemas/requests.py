from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.evaluations import EvaluationResponse
from app.schemas.executions import ExecutionResponse
from app.schemas.feedback import FeedbackResponse
from app.schemas.routing import RoutingDecisionResponse


class RequestCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        # Reject whitespace-only prompts; return the original text unchanged.
        if not value.strip():
            raise ValueError("prompt must not be empty or whitespace-only")
        return value


class RequestResponse(BaseModel):
    id: int
    prompt: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class PipelineResponse(BaseModel):
    """The HTTP 200 body of a full pipeline run.

    ``status`` is ``"completed"`` when every step succeeded and ``"partial"``
    when a non-fatal step failed. ``evaluation`` is null on a partial run; the
    execution record and its response text are always preserved, so
    ``execution`` is present even when the provider call itself failed (the
    record then carries ``status="failed"`` or ``"timed_out"``).

    ``step_errors`` is empty on a clean run and otherwise holds one entry per
    failed step, e.g. ``{"step": "evaluation", "detail": "..."}``.
    """

    id: int
    prompt: str
    status: str
    complexity_class: str
    routing: RoutingDecisionResponse
    execution: ExecutionResponse
    evaluation: EvaluationResponse | None = None
    end_to_end_latency_ms: int
    step_errors: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DegradedResponse(BaseModel):
    """The HTTP 202 body returned when the Routing Engine is unavailable.

    The prompt is persisted with ``status="pending"`` and no execution or
    evaluation takes place.
    """

    id: int
    prompt: str
    status: str
    message: str

    model_config = ConfigDict(from_attributes=True)


class RequestSummaryResponse(BaseModel):
    """One row of the request list, flattened across the linked records.

    Rows created before the schema migration, and rows whose pipeline never
    reached a given step, carry null for the enriched fields.
    """

    id: int
    prompt: str
    status: str
    complexity_class: str | None = None
    selected_model_name: str | None = None
    routing_policy: str | None = None
    latency_ms: int | None = None
    estimated_cost: Decimal | None = None
    quality_score: float | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RequestDetailResponse(BaseModel):
    """Full detail for a single request, including every linked record.

    Each linked record is null until the corresponding pipeline step has run,
    and ``feedback`` stays null until the user submits a rating.
    """

    id: int
    prompt: str
    status: str
    complexity_class: str | None = None
    end_to_end_latency_ms: int | None = None
    created_at: datetime | None = None
    routing_decision: RoutingDecisionResponse | None = None
    execution: ExecutionResponse | None = None
    evaluation: EvaluationResponse | None = None
    feedback: FeedbackResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class AggregateMetricsResponse(BaseModel):
    """Dashboard aggregates over completed executions.

    Every mean is null when no completed execution contributes to it, which
    lets the frontend distinguish "no data yet" from a genuine zero. The
    adaptive and baseline means are split by ``RoutingDecision.policy``.
    """

    total_count: int
    mean_latency_ms: int | None = None
    mean_estimated_cost: Decimal | None = None
    mean_quality_score: float | None = None
    adaptive_mean_latency_ms: int | None = None
    adaptive_mean_cost: Decimal | None = None
    baseline_mean_latency_ms: int | None = None
    baseline_mean_cost: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)
