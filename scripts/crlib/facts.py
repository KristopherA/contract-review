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
OVERLAP = 200  # chunks overlap; _dedupe_facts drops the repeats


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
    if re.match(r"^(?:nothing|no\s+(?:provision|term|clause|article)|neither)\b", who, re.I):
        return None  # "Nothing shall prevent ..." is a saving clause, not an obligation of "Nothing"
    kind = "prohibition" if m["no"] else "right" if m["right"] else "obligation"
    return {"kind": kind, "who": who[-60:] or "—", "text": _short(sentence)}


def extract(parts: list[tuple[str, str]]) -> dict:
    """parts = [(clause number, text)]; every fact carries `cite` (e.g. '§3.03')."""
    out = {"amounts": [], "percentages": [], "durations": [], "dates": [], "deadlines": [], "obligations": []}
    for num, text in parts:
        cite = cite_of(num)
        flat = re.sub(r"\s+", " ", text)
        flat = re.sub(r"(?<=[a-z])- (?=[a-z])", "-", flat)  # re-join hyphens broken at line wraps (linear)
        prev_end = 0
        for start, end, last in _chunks(flat):
            # a fact is taken from the chunk where it ends past the previous cut (no repeats);
            # a sentence running into a cut is left to the next, overlapping chunk
            head_cut = start > 0 and flat[:start].rstrip()[-1:] not in ".;:"
            _scan(flat[start:end], cite, out, prev_end - start, None if last else end - start, head_cut)
            prev_end = end
    return _dedupe_facts(out)


def _chunks(flat: str) -> list[tuple[int, int, bool]]:
    """(start, end, is_last) windows of <= MAX_CHUNK chars, cut at sentence or word
    boundaries, each starting ~OVERLAP chars before the previous cut."""
    out, start = [], 0
    while len(flat) - start > MAX_CHUNK:
        win = flat[start:start + MAX_CHUNK]
        cut = max(win.rfind(". "), win.rfind("; "))
        if cut < MAX_CHUNK // 2:
            cut = win.rfind(" ")
        cut = start + (cut + 1 if cut >= MAX_CHUNK // 2 else MAX_CHUNK)
        out.append((start, cut, False))
        back = flat.rfind(" ", cut - OVERLAP, cut)
        start = back + 1 if back > start else cut
    return out + [(start, len(flat), True)]


def _scan(flat: str, cite: str, out: dict, keep_from: int = 0, tail: int | None = None,
          head_cut: bool = False) -> None:
    """Scan one chunk. Only matches ending at/after `keep_from` (the previous cut) and before
    `tail` (this chunk's cut) are kept, so overlapping chunks report each fact once."""
    def ok(a, b):  # match span [a, b) in this chunk
        return b >= keep_from and (tail is None or b < tail)
    for key, rx in (("amounts", MONEY), ("percentages", PERCENT), ("durations", DURATION), ("dates", DATE)):
        out[key] += [{"value": v.group(0).strip(), "cite": cite} for v in rx.finditer(flat) if ok(*v.span())]
    out["deadlines"] += [{"text": _short(d.group(0)), "cite": cite} for d in DEADLINE.finditer(flat) if ok(*d.span())]
    pos = 0
    for n, snt in enumerate(sentences(flat)):
        a = flat.find(snt, pos); a = pos if a < 0 else a; b = a + len(snt); pos = b
        if b <= keep_from or (n == 0 and head_cut):
            continue  # seen in the previous chunk, or a fragment cut at its start
        if tail is not None and b >= tail - 1 and snt.rstrip()[-1:] not in ".;:":
            continue  # runs into the cut; the next chunk sees it whole
        ob = obligation(snt)
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
