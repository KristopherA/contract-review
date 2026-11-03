"""Deterministic key-fact extraction (no model): amounts, percentages, durations,
dates, deadlines and obligation sentences, each with its clause citation."""
from __future__ import annotations

import re

from .sections import cite as cite_of

MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December")
DATE = re.compile(rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}|(?:{MONTHS})\s+\d{{1,2}}(?:,\s+\d{{4}})?|\d{{1,2}}\s+(?:{MONTHS})(?:\s+\d{{4}})?)\b")
MONEY = re.compile(r"(?:[$€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:USD|CAD|EUR|GBP)\b)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|CAD|EUR|GBP|dollars)\b)")
PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s?(?:%|percent\b)")
# fixed vocabulary only (no open-ended [a-z]+ pieces): bounded, linear-time matching
_ONES = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
         "sixteen seventeen eighteen nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_WORDS = _ONES + _TENS + [f"{t}-{o}" for t in _TENS for o in _ONES[:9]] + ["hundred", "a", "one-half", "half"]
_BASE = "|".join(sorted(_WORDS, key=len, reverse=True))
WORDNUM = rf"(?:(?:{_BASE})(?:\s+and\s+(?:one-half|a\s+half))?)"
NUM = rf"(?:{WORDNUM}\s*\(\d+(?:\.\d+)?\)|\d+(?:\.\d+)?|{WORDNUM})"
UNIT = r"(?:calendar\s+|working\s+|business\s+|consecutive\s+)?(?:minutes?|hours?|days?|weeks?|months?|years?|Working\s+Days?)"
DURATION = re.compile(rf"\b{NUM}\s+{UNIT}\b", re.I)
DEADLINE = re.compile(rf"\b(?:within|no\s+later\s+than|not\s+later\s+than|at\s+least|not\s+less\s+than|"
                      rf"prior\s+to|before|after|by)\s+(?:{NUM}\s+{UNIT}|(?:{MONTHS})\s+\d{{1,2}}(?:,\s+\d{{4}})?)"
                      r"(?:\s+(?:of|after|before|from|following|prior\s+to)\s+[^.;,()]{1,50})?", re.I)
# prohibitions are listed first so "may not" / "will not" never read as a right / promise
PROHIBIT = (r"shall\s+not|must\s+not|may\s+not|will\s+not|cannot|can\s+not|shall\s+never|will\s+never|"
            r"is\s+not\s+(?:permitted|allowed|entitled)\s+to|are\s+not\s+(?:permitted|allowed|entitled)\s+to|"
            r"is\s+prohibited\s+from|are\s+prohibited\s+from")
RIGHT = r"shall\s+be\s+entitled\s+to|is\s+entitled\s+to|are\s+entitled\s+to|may"
DUTY = r"shall|must|will|is\s+required\s+to|are\s+required\s+to|agrees?\s+to"
MODAL = re.compile(rf"\b(?:(?P<no>{PROHIBIT})|(?P<right>{RIGHT})|(?P<duty>{DUTY}))\b", re.I)
SENT = re.compile(r"(?<=[.;])\s+(?=[A-Z(])(?<!\d\.\s)|\s+(?=\((?:[a-z]{1,2}|[ivx]{1,5})\)\s)")
MAX_LEN = 160
MAX_CHUNK = 2000
OVERLAP = 200  # windows of an over-long sentence overlap; _scan keeps one match per span


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
    after = sentence[m.end():]
    negsubj = re.match(r"^(?:nothing|neither|no(?:ne)?\b)", who, re.I)
    if negsubj and re.match(r"^(?:\s+be)?\s+(?:construed|interpreted|deemed|prevent|preclude|limit|restrict|"
                            r"affect|prejudice|bar)\w*", after, re.I):
        return None  # "Nothing shall prevent/limit ..." is a saving clause, not a duty of "Nothing"
    kind = "prohibition" if m["no"] or (negsubj and not m["right"]) else "right" if m["right"] else "obligation"
    return {"kind": kind, "who": who[-60:] or "—", "text": _short(sentence)}


def extract(parts: list[tuple[str, str]]) -> dict:
    """parts = [(clause number, text)]; every fact carries `cite` (e.g. '§3.03').

    Text is split into sentences first (one linear pass). Fact regexes run per sentence;
    a sentence longer than MAX_CHUNK is scanned in windows overlapping by OVERLAP chars,
    and matches are de-duplicated by position, so nothing is lost at a window edge."""
    out = {"amounts": [], "percentages": [], "durations": [], "dates": [], "deadlines": [], "obligations": []}
    for num, text in parts:
        cite = cite_of(num)
        flat = re.sub(r"\s+", " ", text)
        flat = re.sub(r"(?<=[a-z])- (?=[a-z])", "-", flat)  # re-join hyphens broken at line wraps (linear)
        for snt in sentences(flat):
            _scan(snt, cite, out)
    return _dedupe_facts(out)


def _windows(n: int) -> list[tuple[int, int]]:
    if n <= MAX_CHUNK:
        return [(0, n)]
    step = MAX_CHUNK - OVERLAP
    out, a = [], 0
    while True:
        out.append((a, min(a + MAX_CHUNK, n)))
        if a + MAX_CHUNK >= n:
            return out
        a += step


def _scan(snt: str, cite: str, out: dict) -> None:
    for key, rx, field_ in (("amounts", MONEY, "value"), ("percentages", PERCENT, "value"),
                            ("durations", DURATION, "value"), ("dates", DATE, "value"),
                            ("deadlines", DEADLINE, "text")):
        found: dict[int, str] = {}  # absolute start -> longest match there
        for a, b in _windows(len(snt)):
            for m in rx.finditer(snt, a, b):
                v = m.group(0).strip()
                if len(v) > len(found.get(m.start(), "")):
                    found[m.start()] = v
        # drop a shorter match that is the tail of a longer one found in an earlier window
        spans = sorted((st, st + len(v), v) for st, v in found.items())
        keep, reach = [], -1
        for st, en, v in spans:
            if en <= reach:
                continue
            keep.append(v); reach = max(reach, en)
        out[key] += [{field_: (_short(v) if field_ == "text" else v), "cite": cite} for v in keep]
    ob = obligation(snt)  # MODAL is a fixed-word alternation: linear even on long sentences
    if ob:
        out["obligations"].append({**ob, "cite": cite})


def _dedupe_facts(out: dict) -> dict:
    for k, v in out.items():  # de-duplicate per (value/text, cite)
        seen, keep = set(), []
        for f in v:
            key = ((f.get("value") or f.get("text")).lower(), f["cite"])
            if key not in seen:
                seen.add(key); keep.append(f)
        out[k] = keep
    return out
