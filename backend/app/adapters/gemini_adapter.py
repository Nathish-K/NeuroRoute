"""Google Gemini provider adapter.

Calls the Gemini ``generateContent`` REST endpoint with ``httpx`` (no provider
SDK). The API key is read from the environment and sent only in the
``x-goog-api-key`` header, never as a ``?key=`` query parameter, because httpx
errors and logs include the request URL. The adapter never propagates unhandled
exceptions and never leaks the API key into logs, errors, responses, or URLs.
"""

import os
import time
from decimal import Decimal, ROUND_HALF_UP
from dotenv import load_dotenv

load_dotenv()

import httpx

from app.adapters.base import ExecutionResult, ProviderAdapter
from app.exceptions import ConfigurationError

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT_SECONDS = 30.0
_MAX_RESPONSE_CHARS = 1_000_000
_COST_QUANTUM = Decimal("0.0000000001")  # 10 decimal places


class GeminiAdapter(ProviderAdapter):
    """Adapter for the Google Gemini ``generateContent`` API."""

    def __init__(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ConfigurationError("GEMINI_API_KEY is not set")
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
        """Dispatch ``prompt`` to Gemini. Never raises; errors map to status."""
        url = f"{_GEMINI_BASE_URL}/{model_name}:generateContent"
        headers = {"x-goog-api-key": self._api_key}
        body = {"contents": [{"parts": [{"text": prompt}]}]}

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=body, headers=headers)
            latency_ms = int((time.monotonic() - start) * 1000)

            if response.status_code < 200 or response.status_code >= 300:
                return self._failure(
                    f"Gemini request failed with HTTP {response.status_code}",
                    latency_ms,
                )

            try:
                payload = response.json()
            except ValueError:
                return self._failure(
                    "Gemini returned a malformed (non-JSON) response", latency_ms
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
                error_message="Gemini request timed out after 30 seconds",
            )
        except Exception:
            # Catch-all so no provider or network error escapes as unhandled.
            latency_ms = int((time.monotonic() - start) * 1000)
            return self._failure("Gemini request failed unexpectedly", latency_ms)

    def _build_result(
        self,
        payload: dict,
        latency_ms: int,
        cost_per_input_token: Decimal,
        cost_per_output_token: Decimal,
    ) -> ExecutionResult:
        """Map a 2xx Gemini payload into an ExecutionResult."""
        # A blocked prompt has no usable candidates.
        block_reason = (payload.get("promptFeedback") or {}).get("blockReason")
        candidates = payload.get("candidates") or []
        if block_reason or not candidates:
            usage = payload.get("usageMetadata") or {}
            reason = (
                f"Prompt blocked by Gemini: {block_reason}"
                if block_reason
                else "Gemini returned no candidates"
            )
            return ExecutionResult(
                response_text="",
                input_token_count=int(usage.get("promptTokenCount") or 0),
                output_token_count=0,
                latency_ms=latency_ms,
                estimated_cost=Decimal("0"),
                status="failed",
                error_message=reason,
            )

        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        response_text = "".join(
            part.get("text", "") for part in parts if isinstance(part, dict)
        )[:_MAX_RESPONSE_CHARS]

        usage = payload.get("usageMetadata") or {}
        input_tokens = int(usage.get("promptTokenCount") or 0)
        output_tokens = int(usage.get("candidatesTokenCount") or 0) + int(
            usage.get("thoughtsTokenCount") or 0
        )

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
