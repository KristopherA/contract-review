"""Match sections against a user-editable library of standard clauses."""
from __future__ import annotations

from pathlib import Path

import yaml

from .similarity import ratio

DEFAULT_LIBRARY = Path(__file__).resolve().parents[2] / "assets" / "boilerplate.yaml"
DEFAULT_THRESHOLD = 85.0


def load_library(path: str | Path | None = None) -> dict:
    path = Path(path) if path else DEFAULT_LIBRARY
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    clauses = data.get("clauses") or []
    for c in clauses:
        if not c.get("id") or not c.get("text"):
            raise ValueError(f"{path}: every clause needs id and text")
    return {"threshold": float(data.get("threshold", DEFAULT_THRESHOLD)), "clauses": clauses}


def match(section_text: str, title: str, library: dict, threshold: float | None = None):
    """Return (clause_id, score) of best match at/above threshold, else None."""
    best = None
    for c in library["clauses"]:
        thr = float(c.get("threshold", threshold if threshold is not None else library["threshold"]))
        score = ratio(section_text, c["text"])
        if score >= thr and (best is None or score > best[1]):
            best = (c["id"], round(score, 1))
    return best
