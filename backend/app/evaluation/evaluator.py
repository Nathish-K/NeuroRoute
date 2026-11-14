"""Heuristic quality evaluation for completed executions.

``ESCALATION_CONFIDENCE_THRESHOLD`` is validated when this module is first
imported, so a missing or out-of-range setting stops the application before it
serves a request (Requirement 5.3).
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.exceptions import ConfigurationError
from app.intelligence.complexity import tokenise
from app.models.execution import Execution

# Resolved from this file rather than the working directory, so the import-time
# check behaves the same however pytest or uvicorn is launched.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_ROOT / ".env")

THRESHOLD_ENV_VAR = "ESCALATION_CONFIDENCE_THRESHOLD"

# Weights for the three quality components; they sum to 1.0.
_LENGTH_WEIGHT = 0.3
_COHERENCE_WEIGHT = 0.4
_OVERLAP_WEIGHT = 0.3

_LENGTH_CEILING = 500
_COHERENCE_CEILING = 4

COHERENCE_MARKERS: frozenset[str] = frozenset(
    {
        "therefore",
        "because",
        "however",
        "thus",
        "consequently",
        "furthermore",
        "additionally",
        "first",
        "finally",
        "in summary",
        "in conclusion",
        "as a result",
        "for example",
        "for instance",
        "on the other hand",
    }
)


class EvaluationResult(BaseModel):
    """Quality assessment of a single execution attempt."""

    quality_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    escalation_flag: bool


def load_threshold() -> float:
    """Read and validate the escalation threshold from the environment.

    Raises :class:`ConfigurationError` when the variable is absent, empty,
    non-numeric, or outside [0.0, 1.0].
    """
    raw_value = os.environ.get(THRESHOLD_ENV_VAR)
    if raw_value is None or not raw_value.strip():
        raise ConfigurationError(
            f"{THRESHOLD_ENV_VAR} is not set; it must be a number "
            "between 0.0 and 1.0"
        )

    try:
        threshold = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(
            f"{THRESHOLD_ENV_VAR} must be a number between 0.0 and 1.0, "
            f"got {raw_value!r}"
        ) from exc

    # Also rejects nan and infinities, which fail both comparisons.
    if not 0.0 <= threshold <= 1.0:
        raise ConfigurationError(
            f"{THRESHOLD_ENV_VAR} must be between 0.0 and 1.0, "
            f"got {raw_value!r}"
        )

    return threshold


# Validated once, at import time (Requirement 5.3).
ESCALATION_CONFIDENCE_THRESHOLD: float = load_threshold()


def _clamp(value: float) -> float:
    """Confine a score to [0.0, 1.0]."""
    return min(1.0, max(0.0, value))


def _prompt_for(execution_record: Execution) -> str:
    """Return the originating prompt, or an empty string if unreachable."""
    try:
        decision = execution_record.routing_decision
        if decision is None:
            return ""
        request = decision.request
        if request is None:
            return ""
        return request.prompt or ""
    except Exception:
        # A detached or partially loaded record simply scores no overlap.
        return ""


def _length_score(response_text: str) -> float:
    """Reward responses up to the length ceiling."""
    return _clamp(min(len(response_text), _LENGTH_CEILING) / _LENGTH_CEILING)


def _coherence_score(response_tokens: list[str]) -> float:
    """Fraction of the marker ceiling matched by distinct coherence markers."""
    matched = 0
    for marker in COHERENCE_MARKERS:
        marker_tokens = [token.casefold() for token in tokenise(marker)]
        width = len(marker_tokens)
        if width == 0 or width > len(response_tokens):
            continue
        if any(
            response_tokens[index : index + width] == marker_tokens
            for index in range(len(response_tokens) - width + 1)
        ):
            matched += 1

    return _clamp(matched / _COHERENCE_CEILING)


def _overlap_score(prompt_tokens: list[str], response_tokens: list[str]) -> float:
    """Jaccard similarity between the prompt and response token sets."""
    prompt_set = set(prompt_tokens)
    response_set = set(response_tokens)
    union = prompt_set | response_set
    if not union:
        return 0.0

    return _clamp(len(prompt_set & response_set) / len(union))


def evaluate_execution(
    execution_record: Execution, threshold: float
) -> EvaluationResult:
    """Score an execution and decide whether it should be escalated.

    Pure and deterministic: the same record and threshold always produce the
    same result. A failed or timed-out attempt scores zero on both measures.
    """
    if execution_record.status != "completed":
        return EvaluationResult(
            quality_score=0.0,
            confidence=0.0,
            escalation_flag=0.0 < threshold,
        )

    response_text = execution_record.response_text or ""
    response_tokens = [token.casefold() for token in tokenise(response_text)]
    prompt_tokens = [
        token.casefold() for token in tokenise(_prompt_for(execution_record))
    ]

    quality_score = _clamp(
        _LENGTH_WEIGHT * _length_score(response_text)
        + _COHERENCE_WEIGHT * _coherence_score(response_tokens)
        + _OVERLAP_WEIGHT * _overlap_score(prompt_tokens, response_tokens)
    )
    confidence = _clamp(0.5 * quality_score + 0.5)

    return EvaluationResult(
        quality_score=quality_score,
        confidence=confidence,
        escalation_flag=confidence < threshold,
    )
