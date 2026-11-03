"""Deterministic outline: real sections with key facts, boilerplate folded.

No model is involved. An optional plain-language summary per section can be
written by the model and merged in with `--summaries` (off by default).
"""
from __future__ import annotations

from . import boilerplate as bp
from . import facts as fx
from .sections import Section, cite, label

FACT_KEYS = ("amounts", "percentages", "durations", "dates", "deadlines", "obligations", "definitions")


def build(sections: list[Section], library: dict | None, threshold: float | None = None) -> dict:
    kept, folded = [], []
    for s in sections:
        m = bp.match(s.text, s.title, library, threshold, number=s.number) if library and s.text else None
        if m:
            folded.append({"section": label(s), "id": s.id, "clause": m[0], "score": m[1]})
            continue
        parts = s.parts or ([(s.number, s.text)] if s.text else [])
        f = fx.extract(parts)
        short = cite(s.number) or s.title
        for v in f.values():
            for item in v:
                item["cite"] = item["cite"] or short
        kept.append({**s.to_dict(), "cite": label(s), "key_facts": f,
                     "clauses": [n for n, _ in s.parts if n != s.number]})
    return {"sections": kept, "boilerplate_folded": folded, "section_count": len(sections)}
