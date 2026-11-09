"""Tests for the Google Gemini provider adapter."""

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
from app.adapters.gemini_adapter import GeminiAdapter
from app.exceptions import ConfigurationError

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-test:generateContent"
)
TEST_KEY = "test-gemini-key-7f91d3"
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
    input_tokens: int = 10,
    candidate_tokens: int = 5,
    thought_tokens: int | None = 3,
    text: str = "Gemini response",
) -> dict:
    usage = {
        "promptTokenCount": input_tokens,
        "candidatesTokenCount": candidate_tokens,
    }
    if thought_tokens is not None:
        usage["thoughtsTokenCount"] = thought_tokens
    return {
        "candidates": [
            {"content": {"parts": [{"text": text[: len(text) // 2]}, {"text": text[len(text) // 2 :]}]}}
        ],
        "usageMetadata": usage,
    }


@pytest.mark.parametrize("value", [None, ""])
def test_missing_or_empty_api_key_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GEMINI_API_KEY", value)

    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is not set"):
        GeminiAdapter()


async def test_happy_path_maps_response_cost_and_secure_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    constructor, post = _http_mocks(payload=_success_payload())

    with patch("app.adapters.gemini_adapter.httpx.AsyncClient", constructor):
        result = await GeminiAdapter().dispatch(
            "Explain routing",
            "gemini-test",
            Decimal("0.001"),
            Decimal("0.002"),
        )

    assert result == ExecutionResult(
        response_text="Gemini response",
        input_token_count=10,
        output_token_count=8,
        latency_ms=result.latency_ms,
        estimated_cost=Decimal("0.0260000000"),
        status="completed",
        error_message=None,
    )
    assert result.latency_ms >= 0
    constructor.assert_called_once_with(timeout=30.0)
    post.assert_awaited_once_with(
        GEMINI_URL,
        json={"contents": [{"parts": [{"text": "Explain routing"}]}]},
        headers={"x-goog-api-key": TEST_KEY},
    )
    request_url = post.await_args.args[0]
    assert "key=" not in request_url
    assert TEST_KEY not in request_url


@pytest.mark.parametrize(
    ("thought_tokens", "expected_output_tokens"),
    [(7, 18), (None, 11)],
)
async def test_token_mapping_includes_optional_thought_tokens(
    monkeypatch: pytest.MonkeyPatch,
    thought_tokens: int | None,
    expected_output_tokens: int,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(
        payload=_success_payload(13, 11, thought_tokens)
    )

    with patch("app.adapters.gemini_adapter.httpx.AsyncClient", constructor):
        result = await GeminiAdapter().dispatch("prompt", "gemini-test")

    assert result.input_token_count == 13
    assert result.output_token_count == expected_output_tokens


@pytest.mark.parametrize("status_code", [400, 500])
async def test_non_2xx_response_returns_failed_result(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(status_code=status_code)

    with patch("app.adapters.gemini_adapter.httpx.AsyncClient", constructor):
        result = await GeminiAdapter().dispatch("prompt", "gemini-test")

    assert isinstance(result, ExecutionResult)
    assert result.status == "failed"
    assert str(status_code) in (result.error_message or "")
    assert result.latency_ms >= 0


async def test_timeout_returns_timed_out_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    timeout = httpx.TimeoutException(
        "request timed out", request=httpx.Request("POST", GEMINI_URL)
    )
    constructor, _ = _http_mocks(post_error=timeout)

    with patch("app.adapters.gemini_adapter.httpx.AsyncClient", constructor):
        result = await GeminiAdapter().dispatch("prompt", "gemini-test")

    assert isinstance(result, ExecutionResult)
    assert result.status == "timed_out"
    assert "timed out" in (result.error_message or "").lower()
    assert result.latency_ms >= 0


async def test_http_429_returns_plain_language_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(status_code=429)

    with patch("app.adapters.gemini_adapter.httpx.AsyncClient", constructor):
        result = await GeminiAdapter().dispatch("prompt", "gemini-test")

    assert result.status == "failed"
    assert result.error_message == "Gemini request failed with HTTP 429"


@pytest.mark.parametrize(
    ("payload", "message_fragment"),
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "blocked"),
        ({"usageMetadata": {"promptTokenCount": 4}}, "no candidates"),
    ],
)
async def test_blocked_or_candidate_less_prompt_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict,
    message_fragment: str,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(payload=payload)

    with patch("app.adapters.gemini_adapter.httpx.AsyncClient", constructor):
        result = await GeminiAdapter().dispatch("prompt", "gemini-test")

    assert result.status == "failed"
    assert message_fragment in (result.error_message or "").lower()


async def test_malformed_response_is_contained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(json_error=ValueError("invalid JSON"))

    with patch("app.adapters.gemini_adapter.httpx.AsyncClient", constructor):
        result = await GeminiAdapter().dispatch("prompt", "gemini-test")

    assert result.status == "failed"
    assert "malformed" in (result.error_message or "").lower()


async def test_response_text_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)
    constructor, _ = _http_mocks(payload=_success_payload(text="x" * 1_000_001))

    with patch("app.adapters.gemini_adapter.httpx.AsyncClient", constructor):
        result = await GeminiAdapter().dispatch("prompt", "gemini-test")

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

    actual = GeminiAdapter._calculate_cost(
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
    with patch.dict(os.environ, {"GEMINI_API_KEY": TEST_KEY}), patch(
        "app.adapters.gemini_adapter.httpx.AsyncClient", constructor
    ):
        result = asyncio.run(GeminiAdapter().dispatch("prompt", "gemini-test"))

    assert isinstance(result.latency_ms, int)
    assert result.latency_ms >= 0


# Feature: neuroroute-mvp, Property 11: Error Containment
# Validates: Requirements 4.6, 4.7, 4.9
@given(error_kind=st.sampled_from(["http", "timeout", "provider"]))
@settings(max_examples=100, deadline=None)
def test_provider_errors_are_contained(error_kind: str) -> None:
    if error_kind == "http":
        constructor, _ = _http_mocks(status_code=503)
        expected_status = "failed"
    elif error_kind == "timeout":
        constructor, _ = _http_mocks(
            post_error=httpx.TimeoutException(
                "timeout", request=httpx.Request("POST", GEMINI_URL)
            )
        )
        expected_status = "timed_out"
    else:
        constructor, _ = _http_mocks(post_error=RuntimeError("provider failed"))
        expected_status = "failed"

    with patch.dict(os.environ, {"GEMINI_API_KEY": TEST_KEY}), patch(
        "app.adapters.gemini_adapter.httpx.AsyncClient", constructor
    ):
        result = asyncio.run(GeminiAdapter().dispatch("prompt", "gemini-test"))

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
                "timeout", request=httpx.Request("POST", GEMINI_URL)
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
        with patch.dict(os.environ, {"GEMINI_API_KEY": TEST_KEY}), patch(
            "app.adapters.gemini_adapter.httpx.AsyncClient", constructor
        ):
            result = asyncio.run(
                GeminiAdapter().dispatch("prompt", "gemini-test")
            )
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
    assert "key=" not in request_url
