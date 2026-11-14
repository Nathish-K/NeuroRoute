"""Request endpoints: the end-to-end adaptive inference pipeline.

``POST /`` drives every subsystem in order (classify, route, execute, evaluate)
and degrades one step at a time rather than failing outright: a subsystem that
is unavailable either contributes a fallback value or is reported in
``step_errors``, so a request that produced an answer always returns that
answer. Only the Routing Engine is load-bearing — without a model selection
there is nothing to execute, so that outage alone leaves the request
``pending`` and returns HTTP 202.
"""

import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.adapters.engine import execute_request
from app.database.dependencies import get_db
from app.evaluation.escalation import handle_escalation
from app.evaluation.evaluator import (
    ESCALATION_CONFIDENCE_THRESHOLD,
    evaluate_execution,
)
from app.exceptions import (
    NoEligibleModelError,
    NotFoundError,
    PersistenceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.intelligence.classifier import ComplexityClass, classify_prompt
from app.models.evaluation import Evaluation
from app.models.execution import Execution
from app.models.model import Model
from app.models.request import Request
from app.models.routing_decision import RoutingDecision
from app.routing.router import route_request
from app.routing.strategies import RoutingPolicy
from app.schemas.evaluations import EvaluationResponse
from app.schemas.executions import ExecutionResponse
from app.schemas.feedback import FeedbackResponse
from app.schemas.requests import (
    AggregateMetricsResponse,
    DegradedResponse,
    PipelineResponse,
    RequestCreate,
    RequestDetailResponse,
    RequestSummaryResponse,
)
from app.schemas.routing import RoutingDecisionResponse

router = APIRouter(
    prefix="/api/requests",
    tags=["Requests"]
)

# Returned with HTTP 202 when the Routing Engine cannot select a model.
DEGRADED_MESSAGE = (
    "Service partially unavailable \u2014 your prompt has been saved and will "
    "be processed when services recover"
)

# Complexity used when the Intelligence Service fails (MEDIUM fallback).
FALLBACK_COMPLEXITY: ComplexityClass = "moderate"

LIST_LIMIT = 50
_COST_QUANTUM = Decimal("0.0000000001")  # matches Numeric(20, 10)
_MAX_STEP_DETAIL_CHARS = 500


# --- Helpers ---------------------------------------------------------------


def _step_error(step: str, detail: str | None) -> dict[str, Any]:
    """Describe a failed pipeline step without exposing internals."""
    text = (detail or "").strip() or f"The {step} step failed"
    return {"step": step, "detail": text[:_MAX_STEP_DETAIL_CHARS]}


def _commit(db: Session, message: str) -> None:
    """Commit, converting a database failure into PersistenceError."""
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(message) from exc


def _discard(db: Session, request_row: Request) -> None:
    """Drop a just-persisted request so a 422 leaves nothing behind."""
    try:
        db.delete(request_row)
        db.commit()
    except SQLAlchemyError:
        db.rollback()


def _latest_decision(request_row: Request) -> RoutingDecision | None:
    """The most recent routing decision for a request, if any."""
    return max(request_row.routing_decisions, key=lambda row: row.id, default=None)


def _served_execution(decision: RoutingDecision | None) -> Execution | None:
    """The execution whose answer was served for a routing decision.

    A decision can own several attempts, because the Execution Engine retries
    once on ``FALLBACK_MODEL_ID``. The answer that was served is the most
    recent completed attempt, falling back to the most recent attempt overall
    when every one of them failed.
    """
    if decision is None:
        return None

    attempts = list(decision.executions)
    if not attempts:
        return None

    completed = [row for row in attempts if row.status == "completed"]
    return max(completed or attempts, key=lambda row: row.id)


def _persist_evaluation(
    db: Session, execution: Execution, threshold: float
) -> Evaluation:
    """Score an execution and store the result against it."""
    result = evaluate_execution(execution, threshold)
    record = Evaluation(
        execution_id=execution.id,
        quality_score=result.quality_score,
        confidence=result.confidence,
        escalation_flag=result.escalation_flag,
    )
    db.add(record)
    _commit(db, "Failed to persist the evaluation")
    db.refresh(record)
    return record


# --- POST / : the pipeline -------------------------------------------------


@router.post(
    "/",
    response_model=PipelineResponse | DegradedResponse,
    responses={202: {"model": DegradedResponse}},
)
async def create_request(
    request: RequestCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    """Run a prompt through the full adaptive inference pipeline."""
    # 1. The prompt is already validated by RequestCreate; an invalid one is
    #    rejected with HTTP 422 before this handler runs, so nothing is stored.
    # 2. Persist the request up front, so a later outage still leaves a record.
    request_row = Request(prompt=request.prompt, status="pending")
    db.add(request_row)
    _commit(db, "Failed to persist the request")
    db.refresh(request_row)

    # 3. Everything from here on is inside the end-to-end latency window.
    started_at = time.monotonic()
    step_errors: list[dict[str, Any]] = []

    # 4. Classification. An unavailable classifier is not fatal: the request
    #    continues on the MEDIUM fallback with the failure reported.
    try:
        complexity: ComplexityClass = classify_prompt(
            request_row.prompt
        ).complexity_class
    except ValueError as exc:
        # Unreachable in practice (RequestCreate already bounds the prompt),
        # but an invalid prompt must still leave nothing persisted.
        _discard(db, request_row)
        raise ValidationError(str(exc)) from exc
    except Exception as exc:
        complexity = FALLBACK_COMPLEXITY
        step_errors.append(_step_error("intelligence", str(exc)))

    # 5. Routing. PersistenceError (500) and ConfigurationError (500) reach
    #    their app-level handlers untouched.
    try:
        routing_result = route_request(request_row.id, complexity, db)
    except NoEligibleModelError:
        # Caught before its parent below: no model qualifies, which is a 503,
        # not the degraded retry path.
        raise
    except ServiceUnavailableError:
        # The one load-bearing outage. Without a selected model there is
        # nothing to execute, so the request stays pending for a later retry.
        response.status_code = 202
        return DegradedResponse(
            id=request_row.id,
            prompt=request_row.prompt,
            status=request_row.status,
            message=DEGRADED_MESSAGE,
        )

    # RoutingResult names the chosen model but not the stored decision, and
    # the execution has to be attached to that decision, so read it back.
    decision = db.scalars(
        select(RoutingDecision)
        .where(RoutingDecision.request_id == request_row.id)
        .order_by(RoutingDecision.id.desc())
        .limit(1)
    ).first()
    if decision is None:
        raise PersistenceError("The routing decision could not be retrieved")

    model = db.get(Model, routing_result.model_db_id)
    if model is None:
        raise PersistenceError("The selected model could not be retrieved")

    # 6. Execution. Provider errors and timeouts come back as a stored
    #    Execution row rather than an exception, so they are reported and the
    #    pipeline carries on. ConfigurationError and PersistenceError do
    #    propagate (HTTP 500): both need an operator fix, not a stored result.
    execution = await execute_request(decision.id, request_row.prompt, model, db)
    if execution.status != "completed":
        step_errors.append(
            _step_error(
                "execution",
                execution.error_message
                or f"The execution {execution.status.replace('_', ' ')}",
            )
        )

    # 7. Evaluation, guarded: once an execution exists, its answer is served
    #    whatever the evaluator does. A failure here never downgrades the
    #    request to pending and never discards the response text.
    evaluation: Evaluation | None = None
    try:
        evaluation = _persist_evaluation(
            db, execution, ESCALATION_CONFIDENCE_THRESHOLD
        )
    except Exception as exc:
        db.rollback()
        evaluation = None
        step_errors.append(_step_error("evaluation", str(exc)))

    if evaluation is not None and evaluation.escalation_flag:
        try:
            escalated = await handle_escalation(request_row, evaluation, db)
            if escalated is not None:
                # handle_escalation returns whichever attempt scored higher.
                execution = escalated
                if escalated.evaluation is not None:
                    evaluation = escalated.evaluation
        except Exception as exc:
            db.rollback()
            step_errors.append(_step_error("escalation", str(exc)))

    # 8. Close out the request. "partial" records that an answer was produced
    #    but at least one step degraded.
    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    request_row.complexity_class = complexity
    request_row.end_to_end_latency_ms = elapsed_ms
    request_row.status = "partial" if step_errors else "completed"
    _commit(db, "Failed to update the request")
    db.refresh(request_row)

    # 9. Report the decision that produced the served answer, which is the
    #    escalated decision when escalation improved on the original.
    served_decision = execution.routing_decision or decision

    return PipelineResponse(
        id=request_row.id,
        prompt=request_row.prompt,
        status=request_row.status,
        complexity_class=complexity,
        routing=RoutingDecisionResponse.model_validate(served_decision),
        execution=ExecutionResponse.model_validate(execution),
        evaluation=(
            EvaluationResponse.model_validate(evaluation)
            if evaluation is not None
            else None
        ),
        end_to_end_latency_ms=elapsed_ms,
        step_errors=step_errors,
    )


# --- GET / : recent requests ----------------------------------------------


@router.get("/", response_model=list[RequestSummaryResponse])
def get_requests(db: Session = Depends(get_db)):
    """List the most recent requests, enriched with routing and quality data.

    Ordered by ``created_at`` then ``id``, both descending, so rows that share
    the migration timestamp still read newest-first. Rows whose pipeline never
    reached a step carry null for that step's fields.
    """
    rows = db.scalars(
        select(Request)
        .options(
            selectinload(Request.routing_decisions).selectinload(
                RoutingDecision.model
            ),
            selectinload(Request.routing_decisions)
            .selectinload(RoutingDecision.executions)
            .selectinload(Execution.evaluation),
        )
        .order_by(Request.created_at.desc(), Request.id.desc())
        .limit(LIST_LIMIT)
    ).all()

    summaries: list[RequestSummaryResponse] = []
    for row in rows:
        decision = _latest_decision(row)
        execution = _served_execution(decision)
        evaluation = execution.evaluation if execution is not None else None
        model = decision.model if decision is not None else None

        summaries.append(
            RequestSummaryResponse(
                id=row.id,
                prompt=row.prompt,
                status=row.status,
                complexity_class=row.complexity_class,
                selected_model_name=model.model_name if model else None,
                routing_policy=decision.policy if decision else None,
                latency_ms=execution.latency_ms if execution else None,
                estimated_cost=execution.estimated_cost if execution else None,
                quality_score=evaluation.quality_score if evaluation else None,
                created_at=row.created_at,
            )
        )

    return summaries


# --- GET /metrics ----------------------------------------------------------
# Declared before GET /{request_id}: FastAPI matches in declaration order, so
# the reverse would read "metrics" as a request id and answer HTTP 422.


def _mean_row(db: Session, policy_filter: ColumnElement[bool] | None = None):
    """Mean latency, cost, and quality over completed executions."""
    statement = (
        select(
            func.avg(Execution.latency_ms),
            func.avg(Execution.estimated_cost),
            func.avg(Evaluation.quality_score),
        )
        .select_from(Execution)
        .join(RoutingDecision, RoutingDecision.id == Execution.routing_decision_id)
        .outerjoin(Evaluation, Evaluation.execution_id == Execution.id)
        .where(Execution.status == "completed")
    )
    if policy_filter is not None:
        statement = statement.where(policy_filter)

    return db.execute(statement).one()


def _as_int(value: Any) -> int | None:
    """Round a SQL mean to the nearest whole millisecond."""
    return None if value is None else int(round(float(value)))


def _as_cost(value: Any) -> Decimal | None:
    """Normalise a SQL mean to the stored cost precision."""
    if value is None:
        return None

    return Decimal(str(value)).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)


def _as_score(value: Any) -> float | None:
    return None if value is None else float(value)


@router.get("/metrics", response_model=AggregateMetricsResponse)
def get_aggregate_metrics(db: Session = Depends(get_db)):
    """Aggregate dashboard metrics over completed executions.

    Incomplete attempts are excluded from every mean, and a mean with nothing
    to average over is null rather than zero, so the dashboard can tell "no
    data yet" from a genuine zero. Adaptive and baseline figures are split by
    the policy recorded on the routing decision.
    """
    is_baseline = RoutingDecision.policy == RoutingPolicy.BASELINE.value

    overall = _mean_row(db)
    adaptive = _mean_row(db, ~is_baseline)
    baseline = _mean_row(db, is_baseline)

    return AggregateMetricsResponse(
        total_count=db.scalar(select(func.count()).select_from(Request)) or 0,
        mean_latency_ms=_as_int(overall[0]),
        mean_estimated_cost=_as_cost(overall[1]),
        mean_quality_score=_as_score(overall[2]),
        adaptive_mean_latency_ms=_as_int(adaptive[0]),
        adaptive_mean_cost=_as_cost(adaptive[1]),
        baseline_mean_latency_ms=_as_int(baseline[0]),
        baseline_mean_cost=_as_cost(baseline[1]),
    )


# --- GET /{request_id} ----------------------------------------------------


@router.get("/{request_id}", response_model=RequestDetailResponse)
def get_request_detail(request_id: int, db: Session = Depends(get_db)):
    """Return one request with every record the pipeline linked to it."""
    row = db.get(Request, request_id)
    if row is None:
        raise NotFoundError(f"Request {request_id} was not found")

    decision = _latest_decision(row)
    execution = _served_execution(decision)
    evaluation = execution.evaluation if execution is not None else None

    return RequestDetailResponse(
        id=row.id,
        prompt=row.prompt,
        status=row.status,
        complexity_class=row.complexity_class,
        end_to_end_latency_ms=row.end_to_end_latency_ms,
        created_at=row.created_at,
        routing_decision=(
            RoutingDecisionResponse.model_validate(decision)
            if decision is not None
            else None
        ),
        execution=(
            ExecutionResponse.model_validate(execution)
            if execution is not None
            else None
        ),
        evaluation=(
            EvaluationResponse.model_validate(evaluation)
            if evaluation is not None
            else None
        ),
        feedback=(
            FeedbackResponse.model_validate(row.feedback)
            if row.feedback is not None
            else None
        ),
    )
