"""Deterministic key-fact extraction (no model): amounts, percentages, durations,
dates, deadlines, obligation sentences and definitions, each with its clause citation."""
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
_DIG = "zero one two three four five six seven eight nine".split()
_ONE_RX = "|".join(sorted(_ONES, key=len, reverse=True))
_SMALL = rf"(?:(?:{'|'.join(_TENS)})(?:[\s-](?:{'|'.join(_ONES[:9])}))?|{_ONE_RX}|zero)"
# "four hundred and fifty-six", "twenty four", "seven point five", "one point zero seven"
_INT = rf"(?:(?:{_ONE_RX})\s+hundred(?:\s+(?:and\s+)?{_SMALL})?|{_SMALL}|hundred)"
_DEC = rf"(?:{_INT}\s+point(?:\s+(?:{'|'.join(_DIG)})){{1,3}})"
WORDNUM = rf"(?:half\s+an?|(?:{_DEC}|{_INT})(?:\s+and\s+(?:one-half|a\s+half))?|one-half|half|a)"
NUM = rf"(?:{WORDNUM}\s*\(\d+(?:\.\d+)?\)|\(\d+(?:\.\d+)?\)|\d+(?:\.\d+)?|{WORDNUM})"
UNIT = r"(?:calendar\s+|working\s+|business\s+|consecutive\s+)?(?:minutes?|hours?|days?|weeks?|months?|years?|Working\s+Days?)"
DURATION = re.compile(rf"(?:\b|(?<![\w)])(?=\(\d)){NUM}\s+{UNIT}\b", re.I)
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
# no break after abbreviations: i.e. e.g. Art. No. s. Mr. Ms. Dr. Sec. para. ss.
SENT = re.compile(r"(?<=[.;])(?<!\bi\.e\.)(?<!\be\.g\.)(?<!\b[Aa]rt\.)(?<!\b[Nn]o\.)(?<!\bs\.)"
                  r"(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\b[Ss]ec\.)(?<!\b[Pp]ara\.)(?<!\b[Ss]s\.)"
                  r"\s+(?=[A-Z(])(?<!\d\.\s)|\s+(?=\((?:[a-z]{1,2}|[ivx]{1,5})\)\s)")
MAX_LEN = 160
# a leading cross-reference in a subject: "See Art. 5", "per Section 3.2", "Article 7"
REF = re.compile(r"^(?:(?:see|per|under|pursuant to)\s+)?(?:art(?:icle)?|section|s|clause|no)\.?\s*"
                 r"\d[\d.]*(?:\([a-z0-9]+\))*\.?\s*", re.I)
# a dot ending one of these abbreviations is not a clause break inside a subject
ABBR_DOT = r"(?<!\bi\.e)(?<!\be\.g)(?<!\b[Aa]rt)(?<!\b[Nn]o)(?<!\bs)(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\b[Ss]ec)(?<!\b[Pp]ara)(?<!\b[Ss]s)"
APPOSITIVE = re.compile(r"^(?:i\.e\.|e\.g\.|namely|including|being)\s", re.I)
LEAD_PHRASE = re.compile(r"^(?:pursuant to|subject to|under|in accordance with|notwithstanding|despite|"
                         r"per|according to|for the purposes? of)\b", re.I)
DETERMINER = re.compile(r"\b(?:the|an?|each|every|any|all|such|no)\s", re.I)
# "X shall mean ...", "X means ...": a definition, never an obligation of "X"
DEFINITION = re.compile(r"^(?:\(?[a-z0-9]{1,4}[.)]\s*)?(?P<term>[\"\u201c']?[A-Za-z][\w'\u2019 -]{0,60}?[\"\u201d']?)"
                        r"\s+(?:shall\s+mean|means|shall\s+include|includes|refers?\s+to|shall\s+refer\s+to|"
                        r"is\s+defined\s+as|shall\s+be\s+defined\s+as)\b")
# a second clause after a definition: ", and the ...", "; ", " and each ..."
DEF_TAIL = re.compile(r"(?:;\s*|,?\s+(?:and|but)\s+(?=(?:the|an?|each|every|any|all|no|neither|nothing)\s))", re.I)
# "... and shall be paid": a modal straight after "and" has no subject of its own
# "... and shall not include holidays": still the definition, not a duty of the term
DEF_CONT = re.compile(r"(?:shall|will|does|do|must)\s+(?:not\s+)?(?:include|exclude|mean|refer|cover|comprise|"
                      r"apply|be\s+deemed|be\s+construed|be\s+read|be\s+taken|have\s+the\s+meaning)\b", re.I)
DEF_BARE = re.compile(r",?\s+and\s+(?=(?:shall|must|will|may|is\s+required\s+to|are\s+required\s+to)\b)", re.I)
MAX_WHO_WORDS = 8
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
    # the subject is the last clause/noun phrase before the modal: cut at sentence or clause
    # breaks ("See Art. 5. The Union" -> "The Union"), but not inside i.e./e.g./Art./No.
    segs = [x.strip() for x in re.split(ABBR_DOT + r"\.\s+(?=[A-Z(])|[,;:]"
                                        r"|\b(?:if|when|where|unless|and|that|which)\b", before)]
    while len(segs) > 1 and APPOSITIVE.match(segs[-1]):
        segs.pop()  # "The Union, i.e. Local 1," -> "The Union"
    who = segs[-1]
    if LEAD_PHRASE.match(who) or REF.match(who):  # "Pursuant to s. 12 of the Act the Employer" -> "the Employer"
        dets = list(DETERMINER.finditer(who))
        if dets and dets[-1].start() > 0:
            who = who[dets[-1].start():]
    who = REF.sub("", who).strip()
    who = re.sub(r"^\((?:[a-z0-9]{1,4})\)\s*|^(?:[a-z0-9]{1,4})[.)](?!e\.|g\.)\s*", "", who).strip()
    after = sentence[m.end():]
    negsubj = re.match(r"^(?:nothing|neither|no(?:ne)?\b)", who, re.I)
    if negsubj and re.match(r"^(?:\s+be)?\s+(?:construed|interpreted|deemed|prevent|preclude|limit|restrict|"
                            r"affect|prejudice|bar)\w*", after, re.I):
        return None  # "Nothing shall prevent/limit ..." is a saving clause, not a duty of "Nothing"
    kind = "prohibition" if m["no"] or (negsubj and not m["right"]) else "right" if m["right"] else "obligation"
    words = who.split()
    if len(words) > MAX_WHO_WORDS:  # a subject is a short noun phrase: keep its last words
        who = " ".join(words[-MAX_WHO_WORDS:])
    return {"kind": kind, "who": who[-60:] or "—", "text": _short(sentence)}


def definition(sentence: str) -> dict | None:
    m = DEFINITION.match(sentence)
    if not m or len(m["term"].split()) > MAX_WHO_WORDS:
        return None
    term = m["term"].strip(" \"'\u201c\u201d")
    if re.match(r"^(?:the\s+)?(?:employer|union|employee|parties|party|company|this|it|he|she|they)$", term, re.I) \
            and "includes" in m.group(0).lower():
        return None  # "The Employer includes ..." is too ambiguous to call a definition
    return {"term": term, "text": _short(sentence)}


# word values for pairing "five (5)": the bracket counts only when it agrees
_VAL = {w: i + 1 for i, w in enumerate(_ONES)}
_VAL.update({w: 20 + 10 * i for i, w in enumerate(_TENS)})
_VAL.update({"zero": 0})
_DIGV = {w: i for i, w in enumerate(_DIG)}


def _int_value(toks: list[str]) -> float | None:
    total, cur = 0, 0
    for t in toks:
        if t == "and":
            continue
        if t == "hundred":
            cur = (cur or 1) * 100
        elif t in _VAL:
            cur += _VAL[t]
        else:
            return None
    return total + cur


PAIR = re.compile(rf"^(?P<w>{WORDNUM})\s*\((?P<n>\d+(?:\.\d+)?)\)", re.I)
# "1.07", "3.01": decimal with a zero-led fraction reads as a clause number, not a quantity
CLAUSE_NUM = re.compile(r"^\d{1,3}\.0\d")
REF_KW = (r"article|art|section|sub-?section|s|ss|clause|sub-?clause|paragraph|para|"
          r"subparagraph|item|schedule|appendix")
# a reference just before the bracket: "Article (10)", "§ (10)", "12.01 (10)", and a keyword
# with its number, "Clause 12 (10)", "in Article 7, (10)", "Appendix A (2)" (draft 14)
REF_BEFORE = re.compile(rf"(?:\b(?:{REF_KW})\.?(?:\s*(?:\d{{1,3}}[A-Za-z]?|(?-i:[A-Z]))(?:\.\d{{1,3}}){{0,4}}"
                        r"(?:\([a-z0-9]{1,4}\))*,?)?|§|\b\d{1,3}(?:\.\d{1,3}){1,4}(?:\([a-z0-9]{1,4}\))*,?)"
                        r"\s*\(?\s*$", re.I)


def _word_value(w: str) -> float | None:
    w = re.sub(r"\s+", " ", w.lower()).strip()
    if re.fullmatch(r"half an?", w):
        return 0.5
    if w in ("a", "one-half", "half"):
        return {"a": 1, "one-half": 0.5, "half": 0.5}[w]
    half = 0.5 if re.search(r" and (?:one-half|a half)$", w) else 0
    w = re.sub(r" and (?:one-half|a half)$", "", w)
    whole, _, frac = w.partition(" point ")
    v = _int_value(whole.replace("-", " ").split())
    if v is None:
        return None
    if frac:
        ds = [_DIGV.get(t) for t in frac.split()]
        if None in ds:
            return None
        v += float("0." + "".join(map(str, ds)))
    return v + half


def _quantity(snt: str, start: int, v: str) -> str | None:
    """Validate a duration/deadline match: "five (7.5) hours" -> "five hours" (the bracket is a
    clause reference); a clause-number-looking figure ("1.07 days", "Article 7 days") -> None."""
    lead = re.match(r"^(?:within|no\s+later\s+than|not\s+later\s+than|at\s+least|not\s+less\s+than|"
                    r"prior\s+to|before|after|by)\s+", v, re.I)
    off = lead.end() if lead else 0
    q = v[off:]
    pm = PAIR.match(q)
    if pm:
        wv = _word_value(pm["w"])
        if wv is None or abs(wv - float(pm["n"])) > 1e-9:
            if REF_BEFORE.search(snt[:start + off]):
                return None  # "Appendix A (2) days": the letter and bracket are a reference
            q = pm["w"] + q[pm.end():]  # disagreeing bracket: a reference, not the number
        return v[:off] + q
    bare = re.match(r"\((\d+(?:\.\d+)?)\)\s+", q)
    if bare:  # "(10) days" with no word before it: the figure is the quantity
        if REF_BEFORE.search(snt[:start + off]) or CLAUSE_NUM.match(bare[1]):
            return None
        return v[:off] + bare[1] + " " + q[bare.end():]
    nm = re.match(r"\d+(?:\.\d+)?", q)
    if nm and (CLAUSE_NUM.match(q) or REF_BEFORE.search(snt[:start + off])
               or (snt[start + off - 1:start + off] == "(" and snt[start + off + nm.end():][:1] == ")")):
        return None
    return v


def extract(parts: list[tuple[str, str]]) -> dict:
    """parts = [(clause number, text)]; every fact carries `cite` (e.g. '§3.03').

    Text is split into sentences first (one linear pass). Fact regexes run per sentence;
    a sentence longer than MAX_CHUNK is scanned in windows overlapping by OVERLAP chars,
    and matches are de-duplicated by position, so nothing is lost at a window edge."""
    out = {"amounts": [], "percentages": [], "durations": [], "dates": [], "deadlines": [], "obligations": [],
           "definitions": []}
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
            if key in ("durations", "deadlines"):
                v = _quantity(snt, st, v)
                if v is None:
                    continue
            keep.append(v); reach = max(reach, en)
        out[key] += [{field_: (_short(v) if field_ == "text" else v), "cite": cite} for v in keep]
    d = definition(snt)
    if d:
        out["definitions"].append({**d, "cite": cite})
        # keep scanning: "A day means a calendar day and the Employer shall pay." also obliges
        dend = DEFINITION.match(snt).end()
        bare = DEF_BARE.search(snt, dend)
        tail = DEF_TAIL.search(snt, dend)
        if bare and not (tail and tail.start() < bare.start()):
            # "Overtime means ... and shall be paid at 1.5 times": no subject of its own, so
            # the defined term is the subject
            if DEF_CONT.match(snt, bare.end()):
                return  # "... and shall not include holidays" scopes the definition
            ob = obligation(f"{d['term'].strip(chr(34) + chr(39) + '“”')} {snt[bare.end():]}")
            if ob:
                out["obligations"].append({**ob, "cite": cite})
            return
        snt = snt[tail.end():] if tail else ""
    ob = obligation(snt) if snt else None  # MODAL is a fixed-word alternation: linear even on long sentences
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
