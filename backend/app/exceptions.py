"""Custom exception hierarchy for NeuroRoute.

Every application error inherits from NeuroRouteError. FastAPI exception
handlers registered in main.py map each class to an HTTP status code.
"""


class NeuroRouteError(Exception):
    """Base class for all NeuroRoute errors.

    Not raised directly. Handlers may treat an unmapped subclass as HTTP 500.
    """


class ServiceUnavailableError(NeuroRouteError):
    """A pipeline subsystem is unavailable. Maps to HTTP 503.

    The request orchestrator maps a Routing Engine outage to HTTP 202
    (pending) instead (Requirement 8.4). Intelligence and Evaluation
    failures do not produce an HTTP error.
    """


class NoEligibleModelError(ServiceUnavailableError):
    """No enabled or eligible model is available for routing. Maps to HTTP 503.

    Subclasses ServiceUnavailableError, so handlers and the orchestrator
    must catch it first (Requirements 3.6, 3.7).
    """


class PersistenceError(NeuroRouteError):
    """A database write failed. Maps to HTTP 500 (Requirement 3.9)."""


class ConfigurationError(NeuroRouteError):
    """Environment configuration is missing or invalid. Maps to HTTP 500.

    Examples: ESCALATION_CONFIDENCE_THRESHOLD, GEMINI_API_KEY,
    OLLAMA_BASE_URL (Requirements 4.9, 5.3).
    """


class ValidationError(NeuroRouteError):
    """Application-level input validation failed. Maps to HTTP 422.

    Distinct from pydantic.ValidationError (Requirements 6.2, 6.8).
    """


class NotFoundError(NeuroRouteError):
    """The requested resource does not exist. Maps to HTTP 404.

    Requirements 5.9, 6.3, 6.6.
    """


class ConflictError(NeuroRouteError):
    """The operation conflicts with existing data. Maps to HTTP 409.

    Requirements 1.4, 6.4.
    """
