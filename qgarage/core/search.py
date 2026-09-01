"""Forgiving matching helpers for dashboard search fields."""

from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Iterable


def fuzzy_matches(query: str, values: Iterable[object]) -> bool:
    """Match a query regardless of case, separators, or small typing mistakes."""
    query_terms = _terms(query)
    if not query_terms:
        return True

    candidate_terms = _terms(" ".join(str(value) for value in values))
    candidate_text = "".join(candidate_terms)
    return all(
        term in candidate_text
        or any(_term_matches(term, candidate) for candidate in candidate_terms)
        for term in query_terms
    )


def _terms(value: str) -> list[str]:
    return re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE)


def _term_matches(query_term: str, candidate_term: str) -> bool:
    if query_term in candidate_term:
        return True
    if len(query_term) < 3 or len(candidate_term) < 3:
        return False
    if _is_subsequence(query_term, candidate_term):
        return True
    return SequenceMatcher(None, query_term, candidate_term).ratio() >= 0.75


def _is_subsequence(query_term: str, candidate_term: str) -> bool:
    characters = iter(candidate_term)
    return all(character in characters for character in query_term)