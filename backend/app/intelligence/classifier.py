"""Deterministic, rule-based prompt complexity classification."""

from typing import Literal

from pydantic import BaseModel, Field

from app.intelligence.complexity import count_tokens, tokenise

ComplexityClass = Literal["simple", "moderate", "complex"]


class ClassificationResult(BaseModel):
    """The assigned complexity class and its human-readable rationale."""

    complexity_class: ComplexityClass
    explanation: str = Field(min_length=10, max_length=300)


DOMAIN_KEYWORDS: frozenset[str] = frozenset(
    {
        # Medical
        "diagnosis",
        "prognosis",
        "etiology",
        "pathology",
        "oncology",
        "cardiology",
        "epidemiology",
        "pharmacology",
        # Legal
        "tort",
        "habeas corpus",
        "jurisdiction",
        "litigation",
        "statute",
        "precedent",
        "negligence",
        "arbitration",
        # Financial
        "amortisation",
        "derivatives",
        "arbitrage",
        "liquidity",
        "portfolio",
        "valuation",
        "equity",
        "inflation",
        # Scientific
        "photosynthesis",
        "quantum",
        "thermodynamics",
        "hypothesis",
        "molecule",
        "genome",
        "relativity",
        "entropy",
        # Engineering
        "impedance",
        "tensile",
        "torque",
        "voltage",
        "circuit",
        "structural",
        "compression",
        "fluid dynamics",
    }
)

REASONING_CONNECTIVES: frozenset[str] = frozenset(
    {
        "first",
        "then",
        "therefore",
        "because",
        "however",
        "additionally",
        "finally",
        "consequently",
        "furthermore",
        "although",
        "whereas",
    }
)

SYNTHESIS_INDICATORS: frozenset[str] = frozenset(
    {
        "compare",
        "contrast",
        "versus",
        "synthesize",
        "synthesise",
        "critique",
        "evaluate",
        "literature",
        "sources",
        "research",
        "tradeoffs",
    }
)


def _contains_term(tokens: list[str], term: str) -> bool:
    """Return whether a term occurs as consecutive, complete tokens."""
    term_tokens = [token.casefold() for token in tokenise(term)]
    width = len(term_tokens)
    if width == 0 or width > len(tokens):
        return False

    return any(
        tokens[index : index + width] == term_tokens
        for index in range(len(tokens) - width + 1)
    )


def _count_distinct_terms(tokens: list[str], terms: frozenset[str]) -> int:
    """Count listed terms present at least once in normalized prompt tokens."""
    return sum(_contains_term(tokens, term) for term in terms)


def classify_prompt(prompt: str) -> ClassificationResult:
    """Classify a prompt as simple, moderate, or complex.

    The function is pure and deterministic. It raises ``ValueError`` for an
    empty/whitespace-only prompt or a prompt longer than 1,000 tokens.
    """
    if not prompt.strip():
        raise ValueError("Prompt must not be empty")

    token_count = count_tokens(prompt)
    if token_count > 1_000:
        raise ValueError("Prompt exceeds the maximum allowed length")

    normalized_tokens = [token.casefold() for token in tokenise(prompt)]
    domain_terms = _count_distinct_terms(normalized_tokens, DOMAIN_KEYWORDS)
    reasoning_steps = _count_distinct_terms(
        normalized_tokens, REASONING_CONNECTIVES
    )
    synthesis_indicators = _count_distinct_terms(
        normalized_tokens, SYNTHESIS_INDICATORS
    )

    if reasoning_steps >= 3:
        complexity_class: ComplexityClass = "complex"
        tier = "HIGH"
        matched_rule = "reasoning rule (R >= 3)"
    elif synthesis_indicators >= 2:
        complexity_class = "complex"
        tier = "HIGH"
        matched_rule = "synthesis rule (S >= 2)"
    elif domain_terms >= 3:
        complexity_class = "complex"
        tier = "HIGH"
        matched_rule = "domain rule (D >= 3)"
    elif token_count >= 200:
        complexity_class = "complex"
        tier = "HIGH"
        matched_rule = "token-count rule (N >= 200)"
    elif (
        token_count < 50
        and domain_terms == 0
        and reasoning_steps < 2
        and synthesis_indicators == 0
    ):
        complexity_class = "simple"
        tier = "LOW"
        matched_rule = "low-complexity rule"
    else:
        complexity_class = "moderate"
        tier = "MEDIUM"
        matched_rule = "fallback rule"

    explanation = (
        f"Classified as {complexity_class} ({tier}): {matched_rule}; "
        f"tokens={token_count}, domain_terms={domain_terms}, "
        f"reasoning_steps={reasoning_steps}, "
        f"synthesis_indicators={synthesis_indicators}."
    )
    return ClassificationResult(
        complexity_class=complexity_class,
        explanation=explanation,
    )
