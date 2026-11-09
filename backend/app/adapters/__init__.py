"""Provider adapters for dispatching prompts to LLM providers.

Each adapter implements the :class:`ProviderAdapter` interface defined in
``base.py`` and returns a common :class:`ExecutionResult`.
"""

from app.adapters.base import ExecutionResult, ProviderAdapter

__all__ = ["ExecutionResult", "ProviderAdapter"]
