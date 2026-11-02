"""Deterministic outline scaffold: sections, folded boilerplate, keyword hints.

The model does the judgment; these hints only point it at candidate clauses.
"""
from __future__ import annotations

import re

from . import boilerplate as bp
from .sections import Section, label

TOPICS = {
    "parties": r"\b(between|by and between|party|parties|hereinafter)\b",
    "dates": r"\b(effective date|commencement|dated|as of)\b",
    "term_renewal": r"\b(term|renew\w*|extension|expire\w*|expiry)\b",
    "termination": r"\b(terminat\w+|cancel\w*|for convenience|material breach)\b",
    "money_rates": r"(\$|€|£|\bUSD\b|\bCAD\b|\bEUR\b|\bfees?\b|\bprice\b|\brates?\b|\binvoice\w*|\bpayment\b|\binterest\b)",
    "liability_indemnity": r"\b(liabilit\w+|indemn\w+|hold harmless|consequential|cap)\b",
    "confidentiality": r"\b(confidential\w*|non-disclosure|proprietary information)\b",
}
DATE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|(?:January|February|March|April|May|June|July|August|"
                  r"September|October|November|December)\s+\d{1,2},\s+\d{4}|\d{1,2}\s+(?:January|"
                  r"February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b")
MONEY = re.compile(r"(?:[$€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:USD|CAD|EUR|GBP)\b)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|CAD|EUR|GBP)\b|\b\d+(?:\.\d+)?\s?%)")
DURATION = re.compile(r"\b\d+\s*\(?\w*\)?\s*(?:days?|months?|years?)\b|\b(?:one|two|three|four|five|six|"
                      r"twelve|thirty|sixty|ninety)\s+(?:\(\d+\)\s+)?(?:days?|months?|years?)\b", re.I)


def build(sections: list[Section], library: dict | None, threshold: float | None = None) -> dict:
    kept, folded = [], []
    for s in sections:
        m = bp.match(s.text, s.title, library, threshold) if library and s.text else None
        if m:
            folded.append({"section": label(s), "id": s.id, "clause": m[0], "score": m[1]})
            continue
        hits = [t for t, rx in TOPICS.items() if re.search(rx, s.title + " " + s.text, re.I)]
        kept.append({**s.to_dict(), "cite": label(s), "topic_hints": hits,
                     "dates": DATE.findall(s.text), "amounts": MONEY.findall(s.text),
                     "durations": [d.strip() for d in DURATION.findall(s.text)]})
    return {"sections": kept, "boilerplate_folded": folded,
            "topics": list(TOPICS), "section_count": len(sections)}
