"""Tests for the common provider adapter contract."""

from decimal import Decimal

import pytest

from app.adapters.base import ExecutionResult, ProviderAdapter


def test_provider_adapter_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError, match="abstract"):
        ProviderAdapter()


def test_execution_result_fields_are_accessible_by_name() -> None:
    result = ExecutionResult(
        response_text="response",
        input_token_count=12,
        output_token_count=34,
        latency_ms=56,
        estimated_cost=Decimal("0.0000007890"),
        status="completed",
        error_message=None,
    )

    assert result.response_text == "response"
    assert result.input_token_count == 12
    assert result.output_token_count == 34
    assert result.latency_ms == 56
    assert result.estimated_cost == Decimal("0.0000007890")
    assert result.status == "completed"
    assert result.error_message is None
