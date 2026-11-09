"""Abstract provider adapter interface and the shared execution result type.

Every concrete provider adapter (Gemini, Ollama, Groq) implements
:class:`ProviderAdapter` and returns an :class:`ExecutionResult`. Adapters must
never propagate unhandled exceptions; provider errors and timeouts are reported
through the ``status`` and ``error_message`` fields of the result.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ExecutionResult:
    """Normalised outcome of a single prompt dispatch to a provider."""

    response_text: str          # truncated to 1,000,000 characters
    input_token_count: int
    output_token_count: int
    latency_ms: int             # non-negative
    estimated_cost: Decimal     # rounded to 10 decimal places
    status: str                 # "completed" | "failed" | "timed_out"
    error_message: str | None


class ProviderAdapter(ABC):
    """Abstract base class for all LLM provider adapters."""

    @abstractmethod
    async def dispatch(self, prompt: str, model_name: str) -> ExecutionResult:
        """Dispatch prompt to provider. Must never raise unhandled exceptions."""
        raise NotImplementedError
