"""Groq provider adapter.

Calls Groq's OpenAI-compatible chat-completions API with ``httpx`` (no provider
SDK). The API key is read from the environment and sent only in the
``Authorization: Bearer`` header, never in the request URL. The adapter never
propagates unhandled exceptions; provider errors and timeouts are reported
through the ``status`` and ``error_message`` fields of the result.
"""

import os
import time
from decimal import Decimal, ROUND_HALF_UP

import httpx

from app.adapters.base import ExecutionResult, ProviderAdapter
from app.exceptions import ConfigurationError
from dotenv import load_dotenv
load_dotenv(".env", override=True)
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT_SECONDS = 30.0
_MAX_RESPONSE_CHARS = 1_000_000
_COST_QUANTUM = Decimal("0.0000000001")  # 10 decimal places


class GroqAdapter(ProviderAdapter):
    """Adapter for Groq's OpenAI-compatible chat-completions API."""

    def __init__(self) -> None:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ConfigurationError("GROQ_API_KEY is not set")
        # Stored privately; the default object repr does not expose attributes,
        # so the key never appears in repr(), logs, or tracebacks.
        self._api_key = api_key

    async def dispatch(
        self,
        prompt: str,
        model_name: str,
        cost_per_input_token: Decimal = Decimal(0),
        cost_per_output_token: Decimal = Decimal(0),
    ) -> ExecutionResult:
        """Dispatch ``prompt`` to Groq. Never raises; errors map to status."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(_GROQ_URL, json=body, headers=headers)
            latency_ms = int((time.monotonic() - start) * 1000)

            if response.status_code < 200 or response.status_code >= 300:
                return self._failure(
                    f"Groq request failed with HTTP {response.status_code}",
                    latency_ms,
                )

            try:
                payload = response.json()
            except ValueError:
                return self._failure(
                    "Groq returned a malformed (non-JSON) response", latency_ms
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
                error_message="Groq request timed out after 30 seconds",
            )
        except Exception:
            # Catch-all so no provider or network error escapes as unhandled.
            latency_ms = int((time.monotonic() - start) * 1000)
            return self._failure("Groq request failed unexpectedly", latency_ms)

    def _build_result(
        self,
        payload: dict,
        latency_ms: int,
        cost_per_input_token: Decimal,
        cost_per_output_token: Decimal,
    ) -> ExecutionResult:
        """Map a 2xx Groq payload into an ExecutionResult."""
        choices = payload.get("choices") or []
        if not choices:
            return self._failure("Groq returned no choices", latency_ms)

        message = (choices[0].get("message") or {}) if isinstance(
            choices[0], dict
        ) else {}
        response_text = str(message.get("content") or "")[:_MAX_RESPONSE_CHARS]

        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)

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
