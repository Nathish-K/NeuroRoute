"""Tests for the deterministic prompt complexity classifier."""

import pytest
from hypothesis import given, settings, strategies as st

from app.intelligence.classifier import (
    DOMAIN_KEYWORDS,
    REASONING_CONNECTIVES,
    SYNTHESIS_INDICATORS,
    ClassificationResult,
    classify_prompt,
)
from app.intelligence.complexity import count_tokens, tokenise

VALID_CLASSES = {"simple", "moderate", "complex"}

# Every individual token used by any listed term. Excluding all of them keeps a
# generated prompt clear of single-word and multi-word matches alike.
LISTED_TOKENS = frozenset(
    token.casefold()
    for term in DOMAIN_KEYWORDS | REASONING_CONNECTIVES | SYNTHESIS_INDICATORS
    for token in tokenise(term)
)


def _plain_prompt(token_count: int) -> str:
    """Build a prompt of plain tokens that match no listed term."""
    return " ".join(["plainword"] * token_count)


def prompt_strategy() -> st.SearchStrategy[str]:
    """Non-empty prompts of at most 1000 tokens."""
    return st.text(min_size=1, max_size=400).filter(
        lambda text: bool(text.strip()) and count_tokens(text) <= 1_000
    )


def short_prompt_strategy() -> st.SearchStrategy[str]:
    """Prompts under 50 tokens containing no listed term (always simple)."""
    safe_word = (
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12)
        .filter(lambda word: word.casefold() not in LISTED_TOKENS)
    )
    return st.lists(safe_word, min_size=1, max_size=49).map(" ".join)


def test_short_arithmetic_prompt_is_simple() -> None:
    result = classify_prompt("What is 2+2?")

    assert result.complexity_class == "simple"


@pytest.mark.parametrize(
    ("token_count", "expected"),
    [
        (49, "simple"),
        (50, "moderate"),
        (199, "moderate"),
        (200, "complex"),
    ],
)
def test_token_count_boundaries(token_count: int, expected: str) -> None:
    result = classify_prompt(_plain_prompt(token_count))

    assert count_tokens(_plain_prompt(token_count)) == token_count
    assert result.complexity_class == expected


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("first then", "moderate"),
        ("first then therefore", "complex"),
    ],
)
def test_reasoning_connective_thresholds(prompt: str, expected: str) -> None:
    assert classify_prompt(prompt).complexity_class == expected


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("diagnosis", "moderate"),
        ("diagnosis tort", "moderate"),
        ("diagnosis tort quantum", "complex"),
    ],
)
def test_domain_term_thresholds(prompt: str, expected: str) -> None:
    assert classify_prompt(prompt).complexity_class == expected


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("compare", "moderate"),
        ("compare contrast", "complex"),
    ],
)
def test_synthesis_indicator_thresholds(prompt: str, expected: str) -> None:
    assert classify_prompt(prompt).complexity_class == expected


def test_repeated_term_counts_once() -> None:
    result = classify_prompt("because because because")

    assert result.complexity_class == "simple"
    assert "reasoning_steps=1" in result.explanation


def test_matching_is_case_insensitive() -> None:
    lowered = classify_prompt("first then therefore")
    uppered = classify_prompt("FIRST THEN THEREFORE")

    assert uppered.complexity_class == "complex"
    assert uppered.complexity_class == lowered.complexity_class


def test_multi_word_domain_term_matches_consecutive_tokens() -> None:
    result = classify_prompt("Explain habeas corpus briefly")

    assert result.complexity_class == "moderate"
    assert "domain_terms=1" in result.explanation


def test_listed_term_does_not_match_inside_a_longer_token() -> None:
    result = classify_prompt("researcher researching researched")

    assert result.complexity_class == "simple"
    assert "synthesis_indicators=0" in result.explanation


def test_short_prompt_with_three_connectives_is_complex() -> None:
    result = classify_prompt("first then therefore")

    assert count_tokens("first then therefore") == 3
    assert result.complexity_class == "complex"


def test_explanation_follows_the_fixed_template() -> None:
    result = classify_prompt(_plain_prompt(62) + " because")

    assert result.explanation == (
        "Classified as moderate (MEDIUM): fallback rule; tokens=63, "
        "domain_terms=0, reasoning_steps=1, synthesis_indicators=0."
    )


@pytest.mark.parametrize("prompt", ["", "   ", "\t\n"])
def test_empty_or_whitespace_prompt_raises_value_error(prompt: str) -> None:
    with pytest.raises(ValueError, match="^Prompt must not be empty$"):
        classify_prompt(prompt)


def test_prompt_above_token_limit_raises_value_error() -> None:
    with pytest.raises(
        ValueError, match="^Prompt exceeds the maximum allowed length$"
    ):
        classify_prompt(_plain_prompt(1_001))


def test_prompt_at_token_limit_is_accepted() -> None:
    result = classify_prompt(_plain_prompt(1_000))

    assert result.complexity_class == "complex"


# Feature: neuroroute-mvp, Property 4: Classification Returns Valid Output
# Validates: Requirements 2.1, 2.3, 2.4, 2.5
@given(prompt=prompt_strategy())
@settings(max_examples=100, deadline=None)
def test_classification_returns_valid_output(prompt: str) -> None:
    result = classify_prompt(prompt)

    assert isinstance(result, ClassificationResult)
    assert result.complexity_class in VALID_CLASSES
    assert 10 <= len(result.explanation) <= 300


# Feature: neuroroute-mvp, Property 5: Classification Idempotence
# Validates: Requirements 2.1
@given(prompt=prompt_strategy())
@settings(max_examples=100, deadline=None)
def test_classification_is_idempotent(prompt: str) -> None:
    assert classify_prompt(prompt) == classify_prompt(prompt)


# Feature: neuroroute-mvp, Property 4 (mutual exclusivity and exhaustiveness)
# Validates: Requirements 2.1, 2.3, 2.4, 2.5
@given(prompt=prompt_strategy())
@settings(max_examples=100, deadline=None)
def test_exactly_one_class_is_assigned(prompt: str) -> None:
    assigned = classify_prompt(prompt).complexity_class

    assert len([name for name in VALID_CLASSES if name == assigned]) == 1


# Feature: neuroroute-mvp, Property 4 (low-complexity exhaustiveness)
# Validates: Requirements 2.3
@given(prompt=short_prompt_strategy())
@settings(max_examples=100, deadline=None)
def test_short_prompts_without_listed_terms_are_simple(prompt: str) -> None:
    result = classify_prompt(prompt)

    assert count_tokens(prompt) < 50
    assert result.complexity_class == "simple"
