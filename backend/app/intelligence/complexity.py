"""Tokenization utilities used by the query complexity classifier."""

import re


def tokenise(text: str) -> list[str]:
    """Split text on whitespace and punctuation, omitting empty tokens."""
    return [token for token in re.split(r"[\s\W]+", text) if token]


def count_tokens(text: str) -> int:
    """Return the number of tokens produced by :func:`tokenise`."""
    return len(tokenise(text))
