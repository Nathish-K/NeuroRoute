"""Execution Engine: dispatches a prompt to a provider and records the outcome.

Provider failures and timeouts are captured as ``Execution`` rows rather than
raised. Two application errors do propagate, because each needs an operator
response rather than a stored result: :class:`ConfigurationError` for an
unsupported provider or missing credentials, and :class:`PersistenceError` when
the record cannot be written.
"""

import os
import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.adapters.base import ExecutionResult, ProviderAdapter
from app.adapters.gemini_adapter import GeminiAdapter
from app.adapters.groq_adapter import GroqAdapter
from app.adapters.ollama_adapter import OllamaAdapter
from app.exceptions import ConfigurationError, PersistenceError
from app.models.execution import Execution
from app.models.model import Model

PROVIDER_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "gemini": GeminiAdapter,
    "ollama": OllamaAdapter,
    "groq": GroqAdapter,
}

_MAX_ERROR_MESSAGE_CHARS = 1_000


def resolve_adapter(provider_name: str) -> ProviderAdapter:
    """Return an adapter instance for a registered provider name.

    Raises :class:`ConfigurationError` for an unknown provider, and lets the
    adapter's own :class:`ConfigurationError` surface when its required
    environment variable is absent.
    """
    key = (provider_name or "").strip().casefold()
    adapter_class = PROVIDER_ADAPTERS.get(key)
    if adapter_class is None:
        supported = ", ".join(sorted(PROVIDER_ADAPTERS))
        raise ConfigurationError(
            f"Unsupported provider {provider_name!r}. "
            f"Supported providers: {supported}"
        )

    return adapter_class()


async def _attempt(model: Model, prompt: str) -> tuple[ExecutionResult, int]:
    """Dispatch to one model, returning its result and end-to-end latency."""
    start = time.monotonic()
    try:
        adapter = resolve_adapter(model.provider_name)
        result = await adapter.dispatch(
            prompt,
            model.model_name,
            model.cost_per_input_token,
            model.cost_per_output_token,
        )
    except ConfigurationError:
        # Misconfiguration needs an operator fix, so it is not stored as a run.
        raise
    except Exception:
        # Adapters contain their own errors; this guards against a defect there.
        result = ExecutionResult(
            response_text="",
            input_token_count=0,
            output_token_count=0,
            latency_ms=0,
            estimated_cost=Decimal("0"),
            status="failed",
            error_message=(
                f"Execution against model {model.identifier!r} failed "
                "unexpectedly"
            ),
        )

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return result, elapsed_ms


def _persist(
    db: Session,
    routing_decision_id: int,
    result: ExecutionResult,
    latency_ms: int,
) -> Execution:
    """Store one execution attempt against its routing decision."""
    error_message = result.error_message
    if error_message is not None:
        error_message = error_message[:_MAX_ERROR_MESSAGE_CHARS]

    execution = Execution(
        routing_decision_id=routing_decision_id,
        response_text=result.response_text,
        input_token_count=result.input_token_count,
        output_token_count=result.output_token_count,
        latency_ms=latency_ms,
        estimated_cost=result.estimated_cost,
        status=result.status,
        error_message=error_message,
        is_escalated=False,
    )

    try:
        db.add(execution)
        db.commit()
        db.refresh(execution)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(
            "Failed to persist the execution record"
        ) from exc

    return execution


def _resolve_fallback_model(db: Session, primary: Model) -> Model | None:
    """Look up the configured fallback model, or ``None`` if unusable.

    Returns ``None`` when ``FALLBACK_MODEL_ID`` is unset, names the model that
    just failed, or does not match an enabled registry entry. The primary
    failure is reported in that case rather than being masked by a config error.
    """
    fallback_identifier = os.environ.get("FALLBACK_MODEL_ID", "").strip()
    if not fallback_identifier or fallback_identifier == primary.identifier:
        return None

    return db.scalar(
        select(Model).where(
            Model.identifier == fallback_identifier,
            Model.enabled.is_(True),
        )
    )


async def execute_request(
    routing_decision_id: int, prompt: str, model: Model, db: Session
) -> Execution:
    """Execute a prompt against the selected model and record the attempt.

    On a provider failure or timeout, retries once with ``FALLBACK_MODEL_ID``
    when that names a different enabled model, persisting both attempts against
    the same routing decision. Returns the successful fallback attempt when
    there is one, otherwise the primary attempt.
    """
    result, latency_ms = await _attempt(model, prompt)
    primary = _persist(db, routing_decision_id, result, latency_ms)
    if primary.status == "completed":
        return primary

    fallback_model = _resolve_fallback_model(db, model)
    if fallback_model is None:
        return primary

    fallback_result, fallback_latency_ms = await _attempt(fallback_model, prompt)
    fallback = _persist(
        db, routing_decision_id, fallback_result, fallback_latency_ms
    )

    return fallback if fallback.status == "completed" else primary
