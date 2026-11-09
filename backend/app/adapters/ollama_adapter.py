"""Ollama (local model) provider adapter.

Calls a local Ollama server's ``/api/generate`` endpoint with ``httpx`` (no
provider SDK). The base URL is read from the environment. Requests are made with
``stream: false`` so the server returns a single JSON object. The adapter never
propagates unhandled exceptions; provider errors and timeouts are reported
through the ``status`` and ``error_message`` fields of the result.
"""

import os
import time
from decimal import Decimal, ROUND_HALF_UP

import httpx

from app.adapters.base import ExecutionResult, ProviderAdapter
from app.exceptions import ConfigurationError

_TIMEOUT_SECONDS = 30.0
_MAX_RESPONSE_CHARS = 1_000_000
_COST_QUANTUM = Decimal("0.0000000001")  # 10 decimal places


class OllamaAdapter(ProviderAdapter):
    """Adapter for a local Ollama server's ``/api/generate`` API."""

    def __init__(self) -> None:
        base_url = os.environ.get("OLLAMA_BASE_URL", "")
        if not base_url:
            raise ConfigurationError("OLLAMA_BASE_URL is not set")
        self._base_url = base_url.rstrip("/")

    async def dispatch(
        self,
        prompt: str,
        model_name: str,
        cost_per_input_token: Decimal = Decimal(0),
        cost_per_output_token: Decimal = Decimal(0),
    ) -> ExecutionResult:
        """Dispatch ``prompt`` to Ollama. Never raises; errors map to status."""
        url = f"{self._base_url}/api/generate"
        body = {"model": model_name, "prompt": prompt, "stream": False}

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=body)
            latency_ms = int((time.monotonic() - start) * 1000)

            if response.status_code < 200 or response.status_code >= 300:
                return self._failure(
                    f"Ollama request failed with HTTP {response.status_code}",
                    latency_ms,
                )

            try:
                payload = response.json()
            except ValueError:
                return self._failure(
                    "Ollama returned a malformed (non-JSON) response", latency_ms
                )

            return self._build_result(
                payload,
                latency_ms,
                cost_per_input_token,
                cost_per_output_token,
            )
        except httpx.TimeoutException:
            latency_ms = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                response_text="",
                input_token_count=0,
                output_token_count=0,
                latency_ms=latency_ms,
                estimated_cost=Decimal("0"),
                status="timed_out",
                error_message="Ollama request timed out after 30 seconds",
            )
        except Exception:
            # Catch-all so no provider or network error escapes as unhandled.
            latency_ms = int((time.monotonic() - start) * 1000)
            return self._failure("Ollama request failed unexpectedly", latency_ms)

    def _build_result(
        self,
        payload: dict,
        latency_ms: int,
        cost_per_input_token: Decimal,
        cost_per_output_token: Decimal,
    ) -> ExecutionResult:
        """Map a 2xx Ollama payload into an ExecutionResult."""
        response_text = str(payload.get("response") or "")[:_MAX_RESPONSE_CHARS]
        input_tokens = int(payload.get("prompt_eval_count") or 0)
        output_tokens = int(payload.get("eval_count") or 0)

        estimated_cost = self._calculate_cost(
            input_tokens, output_tokens, cost_per_input_token, cost_per_output_token
        )

        return ExecutionResult(
            response_text=response_text,
            input_token_count=input_tokens,
            output_token_count=output_tokens,
            latency_ms=latency_ms,
            estimated_cost=estimated_cost,
            status="completed",
            error_message=None,
        )

    @staticmethod
    def _calculate_cost(
        input_tokens: int,
        output_tokens: int,
        cost_per_input_token: Decimal,
        cost_per_output_token: Decimal,
    ) -> Decimal:
        """(input × cost_in) + (output × cost_out), rounded to 10 dp."""
        total = (input_tokens * cost_per_input_token) + (
            output_tokens * cost_per_output_token
        )
        return total.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def _failure(message: str, latency_ms: int) -> ExecutionResult:
        """Build a failed ExecutionResult with zeroed metrics."""
        return ExecutionResult(
            response_text="",
            input_token_count=0,
            output_token_count=0,
            latency_ms=latency_ms,
            estimated_cost=Decimal("0"),
            status="failed",
            error_message=message,
        )
