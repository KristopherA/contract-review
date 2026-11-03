"""Split contract text into real numbered sections.

Rules (deterministic, conservative):
  * A table of contents is skipped: a CONTENTS/INDEX block, dot-leader or
    page-number entries, and headings that appear with no body and repeat later.
  * Headings are real article/clause numbering only: "ARTICLE 12", "Section 5",
    "12. Title", "12 TITLE", "12.01 Title". Bare "N." headings must be title-like
    and continue the top-level sequence, so numbered lists ("1.", "2.") inside a
    clause stay body text. Lettered and roman items ("(a)", "(iv)", "b)") are
    always body text.
  * A decimal clause without its own title ("12.01 The Employer shall ...") is
    kept inside its article as a cited part, not as a separate untitled section.
  * Every section has a title and numbers are unique.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

KW = r"(?:article|section|clause|schedule|appendix|part)"
HEADING = re.compile(
    rf"^(?:(?P<kw>{KW})\s+)?"
    r"(?P<num>\d{1,3}(?:\.\d{1,3}){0,4}|[IVXLC]{1,6})"
    r"(?P<punct>[.):]?)(?:\s*[-–—:]\s*|\s+|$)(?P<rest>.*)$",
    re.IGNORECASE,
)
TOC_TITLE = re.compile(r"^(?:table\s+of\s+)?contents$|^index$|^table of contents$", re.I)
LEADER = re.compile(r"(?:\.{3,}|…{2,}|(?:\.\s){3,}|_{3,})\s*\d{1,4}\s*$")
TRAILING_PAGE = re.compile(r"\s{2,}\d{1,4}\s*$")
# a "- 1 -" footer glued onto the next line by some PDF extractors: "-1ARTICLE 1 ..."
GLUED_PAGE = re.compile(r"^[-–—]\s*\d{1,4}\s*[-–—]?\s*(?=(?:article|section|schedule|appendix|part)\b|\d+\.\d)", re.I)
PAGE_LINE = re.compile(r"^(?:page\s+)?[-–—]?\s*\d{1,4}\s*[-–—]?(?:\s+of\s+\d{1,4})?$", re.I)
LIST_ITEM = re.compile(r"^\(?(?:[a-z]{1,2}|[ivxlc]{1,6}|\d{1,2})\)\s")  # (a) a) (iv) 1)
UNIT_START = re.compile(r"^(?:days?|hours?|weeks?|months?|years?|%|percent|per\b|x\b)", re.I)
MODAL = re.compile(r"\b(?:shall|must|will|may|is|are|has|have|was|were)\b", re.I)
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


@dataclass
class Section:
    id: str
    number: str
    title: str
    level: int
    text: str
    order: int
    lines: list[str] = field(default_factory=list, repr=False)
    parts: list[tuple[str, str]] = field(default_factory=list, repr=False)  # (cite number, text)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("lines"); d.pop("parts")
        return d


def _roman(s: str) -> int | None:
    s = s.upper()
    if not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", s):
        return None
    total = 0
    for i, ch in enumerate(s):
        v = ROMAN[ch]
        total += -v if i + 1 < len(s) and ROMAN[s[i + 1]] > v else v
    return total


def title_like(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 90 or len(s.split()) > 12 or not (s[0].isupper() or s[0].isdigit()):
        return False
    if s.endswith((".", ";", ",")) and not s.isupper():
        return False
    words = s.split()
    if len(words) > 3 and MODAL.search(s) and not s.isupper():
        return False  # reads like a sentence
    return True


def _split_title(rest: str) -> tuple[str, str]:
    """'Title. Body text' -> (Title, Body); 'Long sentence ...' -> ('', sentence)."""
    rest = rest.strip()
    if not rest:
        return "", ""
    if rest.endswith(":"):
        return "", rest  # "In this Agreement:" is a lead-in, not a title
    m = re.match(r"^(.{1,80}?)[.:]\s+(\S.*)$", rest)
    if m and title_like(m[1]) and len(m[1].split()) <= 10:
        return m[1].strip(), m[2]
    if title_like(rest.rstrip(".:")):
        return rest.rstrip(".:").strip(), ""
    return "", rest


def _classify(line: str):
    """Return (kind, num, top, title, body, level) for heading candidates, else None."""
    if LIST_ITEM.match(line):
        return None
    m = HEADING.match(line)
    if not m:
        return None
    num, rest, kw, punct = m["num"], m["rest"], m["kw"], m["punct"]
    rest = LEADER.sub("", rest).strip()
    if punct == ")":
        return None  # "1)" list item
    is_roman = bool(re.fullmatch(r"[IVXLC]+", num, re.I)) and not num.isdigit()
    if is_roman:
        if not kw and not punct:
            return None
        top = _roman(num)
        if top is None:
            return None
        return ("kw" if kw else "top", num.upper(), top, *_split_title(rest), 1)
    if UNIT_START.match(rest):
        return None
    if kw:
        top = int(num.split(".")[0])
        return ("kw", num, top, *_split_title(rest), num.count(".") + 1)
    if "." in num.rstrip("."):
        num = num.rstrip(".")
        title, body = _split_title(rest)
        return ("clause", num, int(num.split(".")[0]), title, body, num.count(".") + 1)
    # bare top-level number: "12. Title" or "12 TITLE"; the title must look like one
    title, body = _split_title(rest)
    if not title:
        return None
    if not punct and not title.isupper() and len(title.split()) > 6:
        return None
    return ("top", num, int(num), title, body, 1)


def _is_toc_entry(line: str) -> bool:
    return bool(LEADER.search(line) or (TRAILING_PAGE.search(line) and _classify(TRAILING_PAGE.sub("", line))))


def _clean_lines(text: str) -> list[str]:
    out = []
    for raw in text.replace("\f", "\n").split("\n"):
        line = GLUED_PAGE.sub("", re.sub(r"[ \t]+", " ", raw).strip())
        if line and PAGE_LINE.match(line):
            continue
        out.append(line)
    return out


def _next_nonempty(lines, i):
    j = i + 1
    while j < len(lines) and not lines[j]:
        j += 1
    return j


def split_sections(text: str) -> list[Section]:
    lines = _clean_lines(text)
    heads: list[dict] = []   # raw headings in order, each with body lines and parts
    preamble: list[str] = []
    in_toc = False
    toc_numbers: set[str] = set()
    last_top = 0
    target = None  # heading dict that receives body lines
    style_kw = sum(1 for ln in lines if re.match(rf"^{KW}\s+(\d+|[IVXLC]+)\b", ln, re.I)) >= 2
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            if target is not None:
                target["lines"].append("")
            else:
                preamble.append("")
            i += 1; continue
        if TOC_TITLE.match(line):
            in_toc = True; i += 1; continue
        if _is_toc_entry(line):
            c = _classify(LEADER.sub("", TRAILING_PAGE.sub("", line)).strip())
            if c:
                toc_numbers.add(c[1])
            i += 1; continue
        c = _classify(line)
        if c and c[0] == "top" and style_kw:
            c = None  # documents using ARTICLE headings: bare "N." lines are lists
        if c and c[0] == "top" and not (last_top == 0 or last_top < c[2] <= last_top + 3 or (in_toc and c[1] in toc_numbers)):
            c = None  # breaks the top-level sequence: a numbered list item
        if c and c[0] == "clause" and last_top and c[2] != last_top and not in_toc:
            c = None  # "3.5 hours" inside Article 7 is not clause 3.5
        if in_toc:
            j = _next_nonempty(lines, i)
            if c is None and not title_like(line):
                in_toc = False  # body text: the TOC has ended
            elif c is not None:
                # a heading whose next line is body text starts the real document
                k = j
                if c[0] == "kw" and not c[3] and k < len(lines) and title_like(lines[k]) and not _classify(lines[k]):
                    k = _next_nonempty(lines, k)
                nxt = lines[k] if k < len(lines) else ""
                body_follows = bool(c[4]) or c[1] in toc_numbers or (nxt and not _classify(nxt) and not title_like(nxt)
                                              and not _is_toc_entry(nxt))
                if not body_follows:
                    toc_numbers.add(c[1]); i += 1; continue
                in_toc = False
            else:
                i += 1; continue
        if c is None:
            (target["lines"] if target is not None else preamble).append(line)
            i += 1; continue
        kind, num, top, title, body, level = c
        if kind == "kw" and not title:
            j = _next_nonempty(lines, i)
            if j < len(lines) and title_like(lines[j]) and not _classify(lines[j]):
                title = lines[j].rstrip(".:"); i = j
        if kind in ("kw", "top") and level == 1:
            last_top = top
        parent = next((h for h in reversed(heads) if h["level"] < level), None)
        if kind == "clause" and not title and parent is not None:
            parent["parts"].append([num, [body] if body else []])
            parent["lines"] += ["", f"{num} {body}".strip()]
            target = parent
            i += 1; continue
        target = {"num": num, "title": title, "level": level, "lines": [body] if body else [], "parts": []}
        heads.append(target)
        i += 1
    # attribute body lines after an untitled clause to that clause's part
    for h in heads:
        h["parts"] = _parts(h)
    heads = _dedupe(heads)
    sections: list[Section] = []
    for h in heads:
        text_ = _join(h["lines"])
        title = h["title"] or _derived_title(text_, h["num"])
        sections.append(Section(id=f"s{len(sections)+1}", number=h["num"], title=title,
                                level=h["level"], text=text_, order=len(sections),
                                parts=[(n, _join(t)) for n, t in h["parts"]]))
    pre = _join(preamble)
    if pre:
        sections.insert(0, Section(id="s0", number="", title="Preamble", level=0, text=pre, order=-1))
    return sections


def _parts(h) -> list:
    """Split a section's lines into cited parts: [(number, lines)], own text first."""
    parts, cur = [(h["num"], [])], None
    nums = {p[0] for p in h["parts"]}
    for ln in h["lines"]:
        m = re.match(r"^(\d{1,3}(?:\.\d{1,3}){1,4})\s", ln + " ")
        if m and m[1] in nums:
            cur = (m[1], [ln[len(m[1]):].strip()])
            parts.append(cur)
        else:
            parts[-1][1].append(ln)
    return [p for p in parts if _join(p[1])]


def _dedupe(heads: list[dict]) -> list[dict]:
    """Drop body-less headings repeated later (TOC without a CONTENTS title); merge true repeats."""
    out: list[dict] = []
    for k, h in enumerate(heads):
        empty = not _join(h["lines"])
        later = any(x["num"] == h["num"] for x in heads[k + 1:])
        if empty and later:
            continue
        prev = next((x for x in out if x["num"] == h["num"]), None)
        if prev is not None:
            if not empty:
                prev["lines"] += [""] + h["lines"]; prev["parts"] += h["parts"]
                prev["title"] = prev["title"] or h["title"]
            continue
        out.append(h)
    return out


def _derived_title(text: str, num: str) -> str:
    words = re.sub(r"\s+", " ", text).split()[:6]
    return (" ".join(words).rstrip(".,;:") + "…") if words else f"Clause {num}"


def _join(lines: list[str]) -> str:
    paras, buf = [], []
    for ln in lines:
        if ln:
            buf.append(ln)
        elif buf:
            paras.append(" ".join(buf)); buf = []
    if buf:
        paras.append(" ".join(buf))
    return "\n\n".join(paras).strip()


def label(s: Section) -> str:
    if not s.number:
        return s.title or s.id
    return f"§{s.number}" + (f" {s.title}" if s.title else "")
