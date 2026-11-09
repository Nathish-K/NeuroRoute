"""Tests for the Groq provider adapter."""

import asyncio
import io
import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from hypothesis import given, settings, strategies as st

from app.adapters.base import ExecutionResult
from app.adapters.groq_adapter import GroqAdapter
from app.exceptions import ConfigurationError

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TEST_KEY = "test-groq-key-28e4a9"
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
    input_tokens: int = 12,
    output_tokens: int = 20,
    text: str = "Groq response",
) -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
        },
    }


@pytest.mark.parametrize("value", [None, ""])
def test_missing_or_empty_api_key_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GROQ_API_KEY", value)

    with pytest.raises(ConfigurationError, match="GROQ_API_KEY is not set"):
        GroqAdapter()


async def test_happy_path_maps_response_cost_and_secure_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    constructor, post = _http_mocks(payload=_success_payload())

    with patch("app.adapters.groq_adapter.httpx.AsyncClient", constructor):
        result = await GroqAdapter().dispatch(
            "Explain routing",
            "llama-test",
            Decimal("0.001"),
            Decimal("0.002"),
        )

    assert result == ExecutionResult(
        response_text="Groq response",
        input_token_count=12,
        output_token_count=20,
        latency_ms=result.latency_ms,
        estimated_cost=Decimal("0.0520000000"),
        status="completed",
        error_message=None,
    )
    assert result.latency_ms >= 0
    constructor.assert_called_once_with(timeout=30.0)
    post.assert_awaited_once_with(
        GROQ_URL,
        json={
            "model": "llama-test",
            "messages": [{"role": "user", "content": "Explain routing"}],
        },
        headers={"Authorization": f"Bearer {TEST_KEY}"},
    )
    request_url = post.await_args.args[0]
    assert TEST_KEY not in request_url


@pytest.mark.parametrize("status_code", [400, 429, 500])
async def test_http_error_returns_contained_failure(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(status_code=status_code)

    with patch("app.adapters.groq_adapter.httpx.AsyncClient", constructor):
        result = await GroqAdapter().dispatch("prompt", "llama-test")

    assert isinstance(result, ExecutionResult)
    assert result.status == "failed"
    assert result.error_message == f"Groq request failed with HTTP {status_code}"
    assert result.latency_ms >= 0


async def test_timeout_returns_timed_out_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(
        post_error=httpx.TimeoutException(
            "request timed out", request=httpx.Request("POST", GROQ_URL)
        )
    )

    with patch("app.adapters.groq_adapter.httpx.AsyncClient", constructor):
        result = await GroqAdapter().dispatch("prompt", "llama-test")

    assert isinstance(result, ExecutionResult)
    assert result.status == "timed_out"
    assert "timed out" in (result.error_message or "").lower()
    assert result.latency_ms >= 0


async def test_malformed_response_returns_contained_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(json_error=ValueError("invalid JSON"))

    with patch("app.adapters.groq_adapter.httpx.AsyncClient", constructor):
        result = await GroqAdapter().dispatch("prompt", "llama-test")

    assert isinstance(result, ExecutionResult)
    assert result.status == "failed"
    assert "malformed" in (result.error_message or "").lower()


async def test_missing_choices_returns_contained_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(payload={"usage": {}})

    with patch("app.adapters.groq_adapter.httpx.AsyncClient", constructor):
        result = await GroqAdapter().dispatch("prompt", "llama-test")

    assert result.status == "failed"
    assert result.error_message == "Groq returned no choices"


async def test_unexpected_provider_failure_is_contained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(post_error=RuntimeError("provider failed"))

    with patch("app.adapters.groq_adapter.httpx.AsyncClient", constructor):
        result = await GroqAdapter().dispatch("prompt", "llama-test")

    assert isinstance(result, ExecutionResult)
    assert result.status == "failed"
    assert result.error_message == "Groq request failed unexpectedly"


async def test_response_text_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(payload=_success_payload(text="x" * 1_000_001))

    with patch("app.adapters.groq_adapter.httpx.AsyncClient", constructor):
        result = await GroqAdapter().dispatch("prompt", "llama-test")

    assert len(result.response_text) == 1_000_000


async def test_api_key_is_absent_from_url_logs_errors_and_result(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    constructor, post = _http_mocks(status_code=429)

    with caplog.at_level(logging.DEBUG), patch(
        "app.adapters.groq_adapter.httpx.AsyncClient", constructor
    ):
        result = await GroqAdapter().dispatch("prompt", "llama-test")

    request_url = post.await_args.args[0]
    exposed_fields = " ".join(
        [result.response_text, result.error_message or "", request_url, caplog.text]
    )
    assert TEST_KEY not in exposed_fields


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

    actual = GroqAdapter._calculate_cost(
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
    with patch.dict(os.environ, {"GROQ_API_KEY": TEST_KEY}), patch(
        "app.adapters.groq_adapter.httpx.AsyncClient", constructor
    ):
        result = asyncio.run(GroqAdapter().dispatch("prompt", "llama-test"))

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
                "timeout", request=httpx.Request("POST", GROQ_URL)
            )
        )
        expected_status = "timed_out"
    elif error_kind == "malformed":
        constructor, _ = _http_mocks(json_error=ValueError("invalid JSON"))
        expected_status = "failed"
    else:
        constructor, _ = _http_mocks(post_error=RuntimeError("provider failed"))
        expected_status = "failed"

    with patch.dict(os.environ, {"GROQ_API_KEY": TEST_KEY}), patch(
        "app.adapters.groq_adapter.httpx.AsyncClient", constructor
    ):
        result = asyncio.run(GroqAdapter().dispatch("prompt", "llama-test"))

    assert isinstance(result, ExecutionResult)
    assert result.status == expected_status


# Feature: neuroroute-mvp, Property 12: No API Key Exposure
# Validates: Requirements 4.10
@given(error_kind=st.sampled_from(["http", "timeout", "provider", "malformed"]))
@settings(max_examples=100, deadline=None)
def test_api_key_is_not_exposed(error_kind: str) -> None:
    if error_kind == "http":
        constructor, post = _http_mocks(status_code=429)
    elif error_kind == "timeout":
        constructor, post = _http_mocks(
            post_error=httpx.TimeoutException(
                "timeout", request=httpx.Request("POST", GROQ_URL)
            )
        )
    elif error_kind == "malformed":
        constructor, post = _http_mocks(json_error=ValueError("invalid JSON"))
    else:
        constructor, post = _http_mocks(post_error=RuntimeError("provider failed"))

    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    try:
        with patch.dict(os.environ, {"GROQ_API_KEY": TEST_KEY}), patch(
            "app.adapters.groq_adapter.httpx.AsyncClient", constructor
        ):
            result = asyncio.run(GroqAdapter().dispatch("prompt", "llama-test"))
    finally:
        root_logger.removeHandler(log_handler)

    request_url = post.await_args.args[0]
    exposed_fields = " ".join(
        [
            result.response_text,
            result.error_message or "",
            request_url,
            log_stream.getvalue(),
        ]
    )
    assert TEST_KEY not in exposed_fields
