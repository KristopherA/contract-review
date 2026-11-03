"""Match sections against a user-editable library of standard clauses.

Folding hides text, so a fold must be safe: fuzzy similarity alone is not
enough (a single "not" or a changed amount barely moves the ratio). A section
folds only if, compared with the library clause:
  * similarity (numbers kept) >= threshold (default 95), and
  * the sets of numbers/amounts are identical, and
  * the sets of negation/exception words are identical, and
  * clause labels at line starts ("12.01 ") are removed first; numbers inside the
    text still count, and
  * the word sequences, compared in order with only "hereby" ignored, are
    identical. So only whitespace, punctuation, case and "hereby" may differ
    ("a" -> "the" does not fold); "or"->"and", "all"->"any" or swapping who
    does what ("A indemnifies B" vs "B indemnifies A") never folds.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import yaml

from .similarity import ratio

DEFAULT_LIBRARY = Path(__file__).resolve().parents[2] / "assets" / "boilerplate.yaml"
DEFAULT_THRESHOLD = 95.0

NUMBER = re.compile(r"[$€£]?\d[\d,]*(?:\.\d+)?%?")
WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
NEGATION_EXCEPTION = ("shall not", "must not", "may not", "will not", "does not", "do not",
                      "provided that", "subject to", "not", "no", "never", "none", "nor",
                      "without", "except", "excluding", "unless", "notwithstanding", "save",
                      "only", "cannot")
# Deliberately tiny. Quantifiers (all, any, each, every, either, neither, both),
# connectives (and, or, nor), modals (may, must, will, shall), prepositions and
# pronouns/determiners (this, that, its, their, such) all carry meaning.
FILLER = frozenset({"hereby"})


def numbers(text: str) -> frozenset:
    return frozenset(n.replace(",", "").rstrip(".") for n in NUMBER.findall(text))


def guard_words(text: str) -> frozenset:
    t = " " + re.sub(r"[^a-z]+", " ", text.lower()) + " "
    found = set()
    for w in NEGATION_EXCEPTION:  # multi-word phrases first, then consume them
        if f" {w} " in t:
            found.add(w)
            t = t.replace(f" {w} ", " ")
    return frozenset(found)


def content_delta(a: str, b: str) -> Counter:
    ca = Counter(w for w in WORD.findall(a.lower()) if w not in FILLER)
    cb = Counter(w for w in WORD.findall(b.lower()) if w not in FILLER)
    return (ca - cb) + (cb - ca)


def word_sequence(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in FILLER]


def sequence_changes(a: str, b: str) -> list[str]:
    """Order-aware word diff ignoring filler; returns the changed words, if any."""
    from difflib import SequenceMatcher
    sa, sb = word_sequence(a), word_sequence(b)
    out = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, sa, sb, autojunk=False).get_opcodes():
        if op != "equal":
            out.append(f"{' '.join(sa[i1:i2]) or '∅'}→{' '.join(sb[j1:j2]) or '∅'}")
    return out


def safe_to_fold(section_text: str, clause_text: str) -> tuple[bool, str]:
    if numbers(section_text) != numbers(clause_text):
        return False, "numbers or amounts differ"
    if guard_words(section_text) != guard_words(clause_text):
        return False, "negation or exception wording differs"
    delta = content_delta(section_text, clause_text)
    if delta:
        return False, "content words added or dropped: " + ", ".join(sorted(delta)[:8])
    seq = sequence_changes(section_text, clause_text)
    if seq:
        return False, "word order or wording differs: " + "; ".join(seq[:5])
    return True, ""


def load_library(path: str | Path | None = None) -> dict:
    path = Path(path).expanduser() if path else DEFAULT_LIBRARY
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path.name}: invalid YAML ({exc.__class__.__name__}: {str(exc).splitlines()[0]})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: top level must be a mapping with 'clauses'")
    clauses = data.get("clauses") or []
    if not isinstance(clauses, list):
        raise ValueError(f"{path.name}: 'clauses' must be a list")
    for c in clauses:
        if not isinstance(c, dict) or not c.get("id") or not isinstance(c.get("text"), str):
            raise ValueError(f"{path.name}: every clause needs id and text")
    try:
        thr = float(data.get("threshold", DEFAULT_THRESHOLD))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path.name}: threshold must be a number") from exc
    return {"threshold": thr, "clauses": clauses}


# a "12.01 " clause label is numbering, not content: without stripping it the numbers
# guard refused every real section. Only at the start of the section or of a paragraph
# (after a blank line) and only before a capital letter, so a "30.5 hours" line added
# mid-paragraph keeps its number and still blocks the fold.
CLAUSE_LABEL = re.compile(r"(\A|\n[ \t]*\n)[ \t]*\(?\d{1,3}(?:\.\d{1,3}){1,4}\)?[.:]?[ \t]+(?=[A-Z])")


def match(section_text: str, title: str, library: dict, threshold: float | None = None):
    """Return (clause_id, score) of the best safe match at/above threshold, else None."""
    section_text = CLAUSE_LABEL.sub(r"\1", section_text)
    best = None
    for c in library["clauses"]:
        thr = float(c.get("threshold", threshold if threshold is not None else library["threshold"]))
        score = ratio(section_text, c["text"], keep_numbers=True)
        if score < thr or not safe_to_fold(section_text, c["text"])[0]:
            continue
        if best is None or score > best[1]:
            best = (c["id"], round(score, 1))
    return best
