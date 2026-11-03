"""Deterministic key-fact extraction (no model): amounts, percentages, durations,
dates, deadlines and obligation sentences, each with its clause citation."""
from __future__ import annotations

import re

MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December")
DATE = re.compile(rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}|(?:{MONTHS})\s+\d{{1,2}}(?:,\s+\d{{4}})?|\d{{1,2}}\s+(?:{MONTHS})(?:\s+\d{{4}})?)\b")
MONEY = re.compile(r"(?:[$€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:USD|CAD|EUR|GBP)\b)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|CAD|EUR|GBP|dollars)\b)")
PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s?(?:%|percent\b)")
WORDNUM = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen|fifteen|"
           r"twenty|twenty-one|thirty|forty|forty-five|sixty|ninety|[a-z]+(?:-[a-z]+)*\s+and\s+one-half)")
NUM = rf"(?:{WORDNUM}\s*\(\d+(?:\.\d+)?\)|\d+(?:\.\d+)?|{WORDNUM})"
UNIT = r"(?:calendar\s+|working\s+|business\s+|consecutive\s+)?(?:minutes?|hours?|days?|weeks?|months?|years?|Working\s+Days?)"
DURATION = re.compile(rf"\b{NUM}\s+{UNIT}\b", re.I)
DEADLINE = re.compile(rf"\b(?:within|no\s+later\s+than|not\s+later\s+than|at\s+least|not\s+less\s+than|"
                      rf"prior\s+to|before|after|by)\s+(?:{NUM}\s+{UNIT}|(?:{MONTHS})\s+\d{{1,2}}(?:,\s+\d{{4}})?)"
                      r"(?:\s+(?:of|after|before|from|following|prior\s+to)\s+[^.;,()]{1,50})?", re.I)
MODAL = re.compile(r"\b(shall\s+not|must\s+not|shall|must|is\s+required\s+to|are\s+required\s+to|agrees?\s+to|"
                   r"is\s+entitled\s+to|are\s+entitled\s+to|shall\s+be\s+entitled\s+to|may)\b", re.I)
# sentence ends, and lettered/roman items "(a)" "(iv)"; numbered lists stay with their lead-in
SENT = re.compile(r"(?<=[.;])\s+(?=[A-Z(])(?<!\d\.\s)|\s+(?=\((?:[a-z]{1,2}|[ivx]{1,5})\)\s)")
MAX_LEN = 160


def _short(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= MAX_LEN else s[: MAX_LEN - 1].rsplit(" ", 1)[0] + "…"


def sentences(text: str) -> list[str]:
    return [x.strip() for x in SENT.split(text.replace("\n", " ")) if x and x.strip()]


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        k = x.lower()
        if k not in seen:
            seen.add(k); out.append(x)
    return out


def obligation(sentence: str) -> dict | None:
    m = MODAL.search(sentence)
    if not m:
        return None
    before = sentence[: m.start()].strip(" ,")
    who = re.split(r"[,;:]|\b(?:if|when|where|unless|and)\b", before)[-1].strip()
    who = re.sub(r"^\(?[a-z0-9ivx]{1,4}[.)]\s*", "", who).strip()
    modal = re.sub(r"\s+", " ", m[1].lower())
    kind = ("prohibition" if "not" in modal else "right" if modal in ("may",) or "entitled" in modal
            else "obligation")
    return {"kind": kind, "who": who[-60:] or "—", "text": _short(sentence)}


def extract(parts: list[tuple[str, str]]) -> dict:
    """parts = [(clause number, text)]; every fact carries `cite` (e.g. '§3.03')."""
    out = {"amounts": [], "percentages": [], "durations": [], "dates": [], "deadlines": [], "obligations": []}
    for num, text in parts:
        cite = f"§{num}" if num else ""
        flat = re.sub(r"\s+", " ", text)
        flat = re.sub(r"\b([a-z]+)- (?=[a-z])", r"\1-", flat)  # re-join hyphens broken at line wraps
        for key, rx in (("amounts", MONEY), ("percentages", PERCENT), ("durations", DURATION), ("dates", DATE)):
            out[key] += [{"value": v.group(0).strip(), "cite": cite} for v in rx.finditer(flat)]
        out["deadlines"] += [{"text": _short(d.group(0)), "cite": cite} for d in DEADLINE.finditer(flat)]
        for snt in sentences(flat):
            ob = obligation(snt)
            if ob:
                out["obligations"].append({**ob, "cite": cite})
    for k, v in out.items():  # de-duplicate per (value/text, cite)
        seen, keep = set(), []
        for f in v:
            key = ((f.get("value") or f.get("text")).lower(), f["cite"])
            if key not in seen:
                seen.add(key); keep.append(f)
        out[k] = keep
    return out
