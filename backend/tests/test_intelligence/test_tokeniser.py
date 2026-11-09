"""Tests for the query-intelligence tokeniser."""

from app.intelligence.complexity import count_tokens, tokenise


def test_empty_string_returns_empty_list() -> None:
    assert tokenise("") == []


def test_punctuation_only_string_returns_empty_list() -> None:
    assert tokenise("...!?-;:()") == []


def test_simple_sentence_splits_on_punctuation_and_whitespace() -> None:
    assert tokenise("Hello, world!") == ["Hello", "world"]


def test_whitespace_normalisation_is_consistent() -> None:
    expected = ["one", "two", "three"]

    assert tokenise("one two three") == expected
    assert tokenise("  one   two \t three  ") == expected
    assert tokenise("one\ntwo\r\nthree") == expected


def test_tokenise_preserves_original_case() -> None:
    assert tokenise("Alpha BETA gamma") == ["Alpha", "BETA", "gamma"]


def test_count_tokens_matches_tokenise_length() -> None:
    text = "Hello, world! This is a prompt."

    assert count_tokens(text) == len(tokenise(text))
    assert count_tokens(text) == 6


def test_count_tokens_of_empty_and_punctuation_only_text_is_zero() -> None:
    assert count_tokens("") == 0
    assert count_tokens("   ") == 0
    assert count_tokens("!!!") == 0
