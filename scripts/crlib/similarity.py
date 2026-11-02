"""Fuzzy similarity with rapidfuzz, falling back to difflib."""
from __future__ import annotations

import difflib
import re

try:
    from rapidfuzz import fuzz as _fuzz
except ImportError:  # pragma: no cover
    _fuzz = None


def norm(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b\d+(?:\.\d+)*\b", " ", text)  # clause refs change on renumber
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ratio(a: str, b: str) -> float:
    """0..100 similarity of normalised strings."""
    a, b = norm(a), norm(b)
    if not a and not b:
        return 100.0
    if not a or not b:
        return 0.0
    if _fuzz is not None:
        return float(_fuzz.ratio(a, b))
    return 100.0 * difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def token_ratio(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 100.0 if a == b else 0.0
    if _fuzz is not None:
        return float(_fuzz.token_sort_ratio(a, b))
    return 100.0 * difflib.SequenceMatcher(None, sorted(a.split()), sorted(b.split()),
                                           autojunk=False).ratio()
