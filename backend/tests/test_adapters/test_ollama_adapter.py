"""Tests for the local Ollama provider adapter."""

import asyncio
import os
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from hypothesis import given, settings, strategies as st

from app.adapters.base import ExecutionResult
from app.adapters.ollama_adapter import OllamaAdapter
from app.exceptions import ConfigurationError

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
COST_QUANTUM = Decimal("0.0000000001")


def _http_mocks(
    *,
    payload: dict | None = None,
    status_code: int = 200,
    post_error: Exception | None = None,
    json_error: Exception | None = None,
) -> tuple[MagicMock, AsyncMock]:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    if json_error is not None:
        response.json.side_effect = json_error
    else:
        response.json.return_value = payload or {}

    post = AsyncMock(side_effect=post_error)
    if post_error is None:
        post.return_value = response

    client = MagicMock(spec=httpx.AsyncClient)
    client.post = post
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=client)
    context_manager.__aexit__ = AsyncMock(return_value=False)
    constructor = MagicMock(return_value=context_manager)
    return constructor, post


def _success_payload(
    input_tokens: int = 11,
    output_tokens: int = 18,
    text: str = "Ollama response",
) -> dict:
    return {
        "response": text,
        "prompt_eval_count": input_tokens,
        "eval_count": output_tokens,
    }


@pytest.mark.parametrize("value", [None, ""])
def test_missing_or_empty_base_url_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_BASE_URL", value)

    with pytest.raises(ConfigurationError, match="OLLAMA_BASE_URL is not set"):
        OllamaAdapter()


async def test_happy_path_maps_response_cost_and_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", f"{OLLAMA_BASE_URL}/")
    constructor, post = _http_mocks(payload=_success_payload())

    with patch("app.adapters.ollama_adapter.httpx.AsyncClient", constructor):
        result = await OllamaAdapter().dispatch(
            "Explain routing",
            "qwen2.5:3b",
            Decimal("0.001"),
            Decimal("0.002"),
        )

    assert result == ExecutionResult(
        response_text="Ollama response",
        input_token_count=11,
        output_token_count=18,
        latency_ms=result.latency_ms,
        estimated_cost=Decimal("0.0470000000"),
        status="completed",
        error_message=None,
    )
    assert result.latency_ms >= 0
    constructor.assert_called_once_with(timeout=30.0)
    post.assert_awaited_once_with(
        OLLAMA_URL,
        json={
            "model": "qwen2.5:3b",
            "prompt": "Explain routing",
            "stream": False,
        },
    )


@pytest.mark.parametrize("status_code", [400, 429, 500])
async def test_non_2xx_response_returns_failed_result(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
    constructor, _ = _http_mocks(status_code=status_code)

    with patch("app.adapters.ollama_adapter.httpx.AsyncClient", constructor):
        result = await OllamaAdapter().dispatch("prompt", "qwen2.5:3b")

    assert isinstance(result, ExecutionResult)
    assert result.status == "failed"
    assert str(status_code) in (result.error_message or "")
    assert result.latency_ms >= 0


async def test_timeout_returns_timed_out_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
    constructor, _ = _http_mocks(
        post_error=httpx.TimeoutException(
            "request timed out", request=httpx.Request("POST", OLLAMA_URL)
        )
    )

    with patch("app.adapters.ollama_adapter.httpx.AsyncClient", constructor):
        result = await OllamaAdapter().dispatch("prompt", "qwen2.5:3b")

    assert isinstance(result, ExecutionResult)
    assert result.status == "timed_out"
    assert "timed out" in (result.error_message or "").lower()
    assert result.latency_ms >= 0


async def test_malformed_response_is_contained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
    constructor, _ = _http_mocks(json_error=ValueError("invalid JSON"))

    with patch("app.adapters.ollama_adapter.httpx.AsyncClient", constructor):
        result = await OllamaAdapter().dispatch("prompt", "qwen2.5:3b")

    assert result.status == "failed"
    assert "malformed" in (result.error_message or "").lower()


async def test_response_text_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
    constructor, _ = _http_mocks(payload=_success_payload(text="x" * 1_000_001))

    with patch("app.adapters.ollama_adapter.httpx.AsyncClient", constructor):
        result = await OllamaAdapter().dispatch("prompt", "qwen2.5:3b")

    assert len(result.response_text) == 1_000_000


# Feature: neuroroute-mvp, Property 9: Cost Calculation Invariant
# Validates: Requirements 4.2
@given(
    input_tokens=st.integers(min_value=0, max_value=1_000_000),
    output_tokens=st.integers(min_value=0, max_value=1_000_000),
    input_price=st.decimals(
        min_value=Decimal("0"), max_value=Decimal("1"), places=10
    ),
    output_price=st.decimals(
        min_value=Decimal("0"), max_value=Decimal("1"), places=10
    ),
)
@settings(max_examples=100, deadline=None)
def test_cost_calculation_invariant(
    input_tokens: int,
    output_tokens: int,
    input_price: Decimal,
    output_price: Decimal,
) -> None:
    expected = (
        input_tokens * input_price + output_tokens * output_price
    ).quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)

    actual = OllamaAdapter._calculate_cost(
        input_tokens, output_tokens, input_price, output_price
    )

    assert actual == expected
    assert actual.as_tuple().exponent == -10


# Feature: neuroroute-mvp, Property 10: Execution Latency Non-Negativity
# Validates: Requirements 4.2
@given(status_code=st.sampled_from([200, 400, 429, 500]))
@settings(max_examples=100, deadline=None)
def test_dispatch_latency_is_non_negative(status_code: int) -> None:
    constructor, _ = _http_mocks(
        status_code=status_code,
        payload=_success_payload(),
    )
    with patch.dict(os.environ, {"OLLAMA_BASE_URL": OLLAMA_BASE_URL}), patch(
        "app.adapters.ollama_adapter.httpx.AsyncClient", constructor
    ):
        result = asyncio.run(OllamaAdapter().dispatch("prompt", "qwen2.5:3b"))

    assert isinstance(result.latency_ms, int)
    assert result.latency_ms >= 0


# Feature: neuroroute-mvp, Property 11: Error Containment
# Validates: Requirements 4.6, 4.7, 4.9
@given(error_kind=st.sampled_from(["http", "timeout", "provider", "malformed"]))
@settings(max_examples=100, deadline=None)
def test_provider_errors_are_contained(error_kind: str) -> None:
    if error_kind == "http":
        constructor, _ = _http_mocks(status_code=503)
        expected_status = "failed"
    elif error_kind == "timeout":
        constructor, _ = _http_mocks(
            post_error=httpx.TimeoutException(
                "timeout", request=httpx.Request("POST", OLLAMA_URL)
            )
        )
        expected_status = "timed_out"
    elif error_kind == "malformed":
        constructor, _ = _http_mocks(json_error=ValueError("invalid JSON"))
        expected_status = "failed"
    else:
        constructor, _ = _http_mocks(post_error=RuntimeError("provider failed"))
        expected_status = "failed"

    with patch.dict(os.environ, {"OLLAMA_BASE_URL": OLLAMA_BASE_URL}), patch(
        "app.adapters.ollama_adapter.httpx.AsyncClient", constructor
    ):
        result = asyncio.run(OllamaAdapter().dispatch("prompt", "qwen2.5:3b"))

    assert isinstance(result, ExecutionResult)
    assert result.status == expected_status
