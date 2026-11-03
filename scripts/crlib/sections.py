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

import math
import re
from dataclasses import asdict, dataclass, field

KW = r"(?:article|section|clause|part)"
# Heading numbers are limited to \d{1,3} per level (articles 1-999, clauses up to 999.999...)
# and roman numerals up to 6 letters; a 4+ digit number is never read as a heading.
HEADING = re.compile(
    rf"^(?:(?P<kw>{KW})\s+)?"
    r"(?P<num>\d{1,3}(?:\.\d{1,3}){0,4}|[IVXLC]{1,6})"
    r"(?P<punct>[.):]?)(?:\s*[-–—:]\s*|\s+|$)(?P<rest>.*)$",
    re.IGNORECASE,
)
# annexes start their own top-level block: "LETTER OF UNDERSTANDING #2 - Title", "APPENDIX A"
ANNEX = re.compile(
    r"^(?P<kw>letter\s+of\s+understanding|letter\s+of\s+intent|memorandum\s+of\s+(?:agreement|understanding)"
    r"|appendix|schedule|addendum|annex)\b(?:\s+(?:no\.?\s*|#\s*)?[\x22\x27\u201c]?(?P<id>(?-i:[A-Z0-9]{1,3}|[IVX]{1,5}))[\x22\x27\u201d]?(?=[\s\-–—:.]|$))?"
    r"\s*(?:[-–—:.]\s*)?(?P<rest>.{0,200})$", re.I)
MAX_LINE = 2000  # longer lines are cut into chunks before any regex runs (bounded runtime)
TOC_TITLE = re.compile(r"^(?:table\s+of\s+)?contents$|^(?:numerical\s+|alphabetical\s+|subject\s+)?index$", re.I)
EDGE = 3  # header/footer candidates: first and last EDGE non-empty lines of each page
# a "- 1 -" footer glued onto the next line by some PDF extractors: "-1ARTICLE 1 ..."
GLUED_PAGE = re.compile(r"^[-–—]\s*\d{1,4}\s*[-–—]?\s*(?=(?:article|section|schedule|appendix|part)\b|\d+\.\d)", re.I)
# only explicit page-number forms are dropped anywhere: "- 7 -", "Page 7", "Page 7 of 40"
PAGE_LINE = re.compile(r"^(?:[-–—]\s*\d{1,4}\s*[-–—]|page\s+\d{1,4}(?:\s+of\s+\d{1,4})?)$", re.I)
LONE_NUM = re.compile(r"^(?P<n>\d{1,4})$")
PAGE_NUM = re.compile(r"^(?:[-–—]\s*(?P<n>\d{1,4})\s*[-–—]|page\s+(?P<m>\d{1,4})(?:\s+of\s+\d{1,4})?)$", re.I)
MAX_PAGE_OFFSET = 6  # printed page number may differ from the PDF page index by this much
DIGITS = re.compile(r"\d{1,4}")
HAS_DIGIT = re.compile(r"\d")
# share of pages on which an identical edge line is always page furniture
ALWAYS_SHARE = 0.8
# ...and at least this many pages: in a 2-3 page file "identical on every page" is weak
# evidence (a clause per page can repeat), so those fall back to the majority rule
ALWAYS_MIN = 4
# a bottom-edge line repeated on fewer pages that ends like a sentence or cites a clause is body text
KEEP_LINE = re.compile(r"[.;:?!][\"'\u201d)]?$|\b(?:article|section|clause)\s+\d", re.I)
BODY_MARK = re.compile(r"[$%€£]|\b(?:shall|must|may|will|agrees?)\b", re.I)
LIST_ITEM = re.compile(r"^\(?(?:[a-z]{1,2}|[ivxlc]{1,6}|\d{1,2})\)\s")  # (a) a) (iv) 1)
# "3 days", "7.5 hours": a number followed by a lowercase unit is not a heading ("8 HOURS OF WORK" can be)
UNIT_START = re.compile(r"^(?:[Dd]ays?|[Hh]ours?|[Ww]eeks?|[Mm]onths?|[Yy]ears?|%|percent|per\b|x\b)")
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


def _strip_page_ref(s: str) -> tuple[str, bool]:
    """Remove a trailing TOC page reference without backtracking regexes.

    Returns (text without the reference, True if it had a dot/underscore leader)."""
    t = s.rstrip()
    k = len(t)
    while k > 0 and t[k - 1].isdigit() and len(t) - k < 4:
        k -= 1
    if k == len(t) or (k > 0 and t[k - 1].isdigit()):
        return s, False
    head = t[:k].rstrip()
    j = len(head)
    while j > 0 and head[j - 1] in ". …_":
        j -= 1
    run = head[j:]
    if run.count(".") + 2 * run.count("…") + run.count("_") >= 3 and run.strip(". ") in ("", "…" * len(run.strip(". "))) or "___" in run:
        return head[:j].rstrip(), True
    return s, False


def _strip_leader(s: str) -> str:
    """'TITLE ........ 12' -> 'TITLE'; also a bare dot run at the end."""
    out, had = _strip_page_ref(s)
    if had:
        return out
    t = s.rstrip()
    j = len(t)
    while j > 0 and t[j - 1] in ". …_":
        j -= 1
    return t[:j].rstrip() if len(t) - j >= 3 and t[j:].count(".") + t[j:].count("_") + t[j:].count("…") >= 3 else s


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


def _annex(line: str):
    m = ANNEX.match(line)
    if not m:
        return None
    kw = re.sub(r"\s+", " ", m["kw"]).title().replace(" Of ", " of ")
    rest = _strip_leader(m["rest"]).strip()
    # "Appendix A sets out the rates..." in body text is not a heading
    if not (m["kw"].isupper() or m["id"]) or (rest and not title_like(rest.rstrip(".:"))):
        return None
    num = f"{kw} {m['id'].upper()}" if m["id"] else kw
    return ("annex", num, None, rest.rstrip(".:"), "", 1)


def _classify(line: str):
    """Return (kind, num, top, title, body, level) for heading candidates, else None."""
    if LIST_ITEM.match(line):
        return None
    a = _annex(line)
    if a:
        return a
    m = HEADING.match(line)
    if not m:
        return None
    num, rest, kw, punct = m["num"], m["rest"], m["kw"], m["punct"]
    rest = _strip_leader(rest).strip()
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
    if UNIT_START.match(rest) and not rest.isupper():
        return None
    if kw:
        if "." in num.strip(".") and not title_like(_split_title(rest)[0] or "x"):
            return None  # "Article 14.03 (a) shall ..." is a cross-reference in wrapped body text
        if rest[:1].islower() or rest[:1] == "(":
            return None  # "Article 12 of this Agreement ..." / "Article 9 (b) ..."
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
    out, had = _strip_page_ref(line)
    if had:
        return True
    # "ARTICLE 3 HOURS OF WORK 4": a heading followed by a bare page number
    m = re.match(r"^(.*\S)\s+(\d{1,4})$", line)
    c = _classify(m[1]) if m else None
    return bool(c and c[3] and (c[0] in ("kw", "annex") or c[3].isupper()))


def _toc_key(line: str) -> str:
    out, had = _strip_page_ref(line)
    if not had:
        out = re.sub(r"\s+\d{1,4}$", "", line)
    return out.strip()


def _chunks(line: str) -> list[str]:
    if len(line) <= MAX_LINE:
        return [line]
    out = []
    while len(line) > MAX_LINE:
        cut = line.rfind(" ", 0, MAX_LINE)
        cut = cut if cut > MAX_LINE // 2 else MAX_LINE
        out.append(line[:cut].strip()); line = line[cut:].strip()
    return out + ([line] if line else [])


def _page_variants(p: int, t: str):
    """Keys for comparing an edge line across pages: the exact text, plus one variant per
    number that could be this page's number (page index + small offset), masked."""
    yield (t, None)
    if not HAS_DIGIT.search(t):
        return
    for m in DIGITS.finditer(t):
        k = int(m.group(0)) - (p + 1)
        if abs(k) <= MAX_PAGE_OFFSET:
            yield (t[:m.start()] + "#" + t[m.end():], k)


def _clean_lines(text: str) -> list[str]:
    """Normalise lines, drop page furniture, keep everything else.

    1. Running headers/footers: an edge line (one of the first/last EDGE non-empty lines)
       identical, except for the page-number position, in the same edge slot on >=3 pages
       and on at least ALWAYS_SHARE (80%) of the pages, minimum ALWAYS_MIN (4) pages, is
       always dropped. Below that, a
       repeat on >=3 pages and at least half the pages is dropped even with modal words or
       $, unless it is a heading or a bottom-edge line that ends like a sentence (. ; : ? !)
       or cites Article/Section/Clause N (so 3 of 5 pages: kept at the bottom, dropped at
       the top). Repeats on a minority of pages (>=3) are dropped unless they carry $, %
       or a modal verb, or are a bottom-edge sentence/citation line.
    2. Page numbers: "- 7 -" / "Page 7 of 40" anywhere; a bare number at a page edge equal
       to the page index plus a constant offset (<= MAX_PAGE_OFFSET) on >=3 pages, with the
       explicit forms counting toward the run. Other numbers ("1500") are body text."""
    pages = [[_squash(x) for x in pg.split("\n")] for pg in text.split("\f")]
    drop: set[tuple[int, int]] = set()
    edges = []  # (page, line index, slot, text); slot = ("top", rank) or ("bottom", rank)
    for p, pg in enumerate(pages):
        idx = [i for i, x in enumerate(pg) if x]
        for r, i in enumerate(idx[:EDGE]):
            edges.append((p, i, ("top", r), pg[i]))
        for r, i in enumerate(reversed(idx[-EDGE:])):
            edges.append((p, i, ("bottom", r), pg[i]))
    n_pages = len(pages)
    # 1) repeated headers/footers (checked first)
    if n_pages >= 2:
        need = min(3, n_pages)
        where: dict[tuple, int] = {}
        cand = []  # (page, line, [keys]) computed once per edge line
        var: dict[tuple[int, int], list | None] = {}
        for p, i, slot, t in edges:
            if (p, i) not in var:  # a short page's line sits in both edges: compute once
                var[(p, i)] = None if LONE_NUM.match(t) or PAGE_NUM.match(t) else list(_page_variants(p, t))
            vs = var[(p, i)]
            if vs is None:
                continue
            keys = [(slot, v) for v in vs]
            cand.append((p, i, t, keys))
            for key in keys:  # one edge slot per page, so a count is a page count
                where[key] = where.get(key, 0) + 1
        bottom = {(p, i) for p, i, slot, _ in edges if slot[0] == "bottom"}
        always = max(ALWAYS_MIN, math.ceil(ALWAYS_SHARE * n_pages))
        for p, i, t, keys in cand:
            best = max(where[k] for k in keys)
            if best < 3 and best < need or (p, i) in drop:
                continue  # not repeated: the common case, decided without regexes
            if best >= always:
                drop.add((p, i)); continue  # same slot on (nearly) every page: always furniture
            top = (p, i) not in bottom  # on a short page a line can sit in both edges
            if _classify(t) or (not top and KEEP_LINE.search(t)):
                continue  # a heading, or a bottom-edge "Subject to Article 12." on some pages
            if best >= need and best * 2 >= n_pages:
                drop.add((p, i))  # running header/footer on most pages
            elif best >= 3 and not BODY_MARK.search(t):
                drop.add((p, i))  # minority repeat: dropped only without $, % or a modal
    # 2) page numbers
    pn = []
    for p, i, _, t in edges:
        m = LONE_NUM.match(t) or PAGE_NUM.match(t)
        if m and (p, i) not in drop:
            pn.append((p, i, int(m.group("n") or m.groupdict().get("m"))))
    by_off: dict[int, set] = {}
    for p, i, n in pn:
        if abs(n - (p + 1)) <= MAX_PAGE_OFFSET:
            by_off.setdefault(n - (p + 1), set()).add(p)
    offs = {k for k, ps in by_off.items() if len(ps) >= 3}
    for p, i, n in pn:
        if n - (p + 1) in offs:
            drop.add((p, i))
    out = []
    for p, pg in enumerate(pages):
        for i, line in enumerate(pg):
            if (p, i) in drop or (line and PAGE_LINE.match(line)):
                continue
            out += _chunks(GLUED_PAGE.sub("", line))
        out.append("")
    return out


def _squash(raw: str) -> str:
    return re.sub(r"[ \t]+", " ", raw).strip()


SENTENCE_START = re.compile(r"^(?:the|a|an|where|when|if|within|following|except|effective|all|any|each|no|"
                            r"in|on|upon|subject|notwithstanding|this|these|that|those|there|it|nothing|every|"
                            r"an?\s+employee)\b", re.I)
VERBISH = re.compile(r"\b(?:shall|will|may|must|is|are|was|were|has|have|expires?|applies|means)\b", re.I)


def _real_title(title: str, lines: list[str], i: int) -> bool:
    """A clause title must not continue as a sentence on the next line and should read as a
    heading: upper case, or most longer words capitalised, not opening like a sentence."""
    if re.search(r"[$%€£]", title):
        return False  # "1.01 Grade 1 $1,500.00": a wage row, not a title
    j = _next_nonempty(lines, i)
    if j < len(lines) and lines[j][:1].islower():
        return False
    if lines[i].rstrip().endswith(".") and len(title.split()) >= 2 and (j >= len(lines) or _classify(lines[j])):
        return False  # a one-sentence clause with no body is body text, not a title
    if title.isupper():
        return True
    if len(title.split()) > 3 and (SENTENCE_START.match(title) or VERBISH.search(title)):
        return False
    words = [w for w in re.findall(r"[A-Za-z][\w'’-]*", title) if len(w) >= 4]
    return not words or sum(w[0].isupper() for w in words) * 2 >= len(words)


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
    block, block_is_annex = "", False
    last_main = 0  # last main-body article number (outside annexes)
    in_annex = False  # inside an appendix / schedule / letter block
    seen_annex: dict[str, int] = {}  # current top-level block (article or annex)
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
            c = _classify(_toc_key(line))
            if c:
                toc_numbers.add(c[1])
            i += 1; continue
        c = _classify(line)
        if c and c[0] == "top" and in_annex and not in_toc and last_main and c[2] == last_main + 1 \
                and not style_kw:
            in_annex = False; last_top = last_main  # "3. TITLE" after Article 2's annex: body resumes
        if c and c[0] == "top" and in_annex and not in_toc:
            # "1. DENTAL" inside Schedule C is a clause of that schedule, never a document
            # article: number and dedupe it within the annex block.
            c = ("clause", c[1], 0, c[3], c[4], 2)
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
        if kind in ("clause", "top") and title and not body and not _real_title(title, lines, i):
            title, body = "", title  # "4.01 The Employer recognizes the" + wrapped lowercase line
        if kind == "annex" and not title:
            for k in range(i + 1, min(i + 15, len(lines))):  # "LETTER OF UNDERSTANDING ... Re: Subject"
                rm = re.match(r"^re\s*:\s*(.{3,90})$", lines[k], re.I)
                if rm:
                    title = rm[1].rstrip(".:"); break
                if _classify(lines[k]):
                    break
            j = _next_nonempty(lines, i)
            if not title and j < len(lines) and lines[j].isupper() and title_like(lines[j]) \
                    and not _classify(lines[j]) and not re.search(r"[$%]", lines[j]) \
                    and not re.match(r"^(?:between|and|by|of|among|re)\b", lines[j], re.I):
                title = lines[j].rstrip(".:"); lines[j] = ""  # "APPENDIX A" / "WAGE GRID"
        if kind == "annex":
            seen_annex[num] = seen_annex.get(num, 0) + 1
            if seen_annex[num] > 1 or any(h["num"] == num for h in heads):
                num = f"{num} ({seen_annex[num]})"
        if kind == "kw" and not title:
            j = _next_nonempty(lines, i)
            if j < len(lines) and title_like(lines[j]) and not _classify(lines[j]):
                title = lines[j].rstrip(".:"); i = j
        if kind in ("kw", "top") and level == 1:
            last_top = top
            if not in_annex or kind == "kw":
                last_main = top
        elif kind == "annex":
            last_top = 0  # clause numbering restarts inside an appendix / letter
        parent = next((h for h in reversed(heads) if h["level"] < level), None)
        if kind == "clause" and not title and parent is not None:
            parent["parts"].append([num, [body] if body else []])
            parent["lines"] += ["", f"{num} {body}".strip()]
            target = parent
            i += 1; continue
        if kind == "annex":
            in_annex = True
        elif kind == "kw" and level == 1:
            in_annex = False  # "ARTICLE 9" after an annex resumes the body
        if kind == "annex":
            block = num
        elif level == 1:
            block = num
        target = {"num": num, "title": title, "level": level, "lines": [body] if body else [], "parts": [],
                  "block": block, "annex": kind == "annex" or (level > 1 and block_is_annex)}
        block_is_annex = kind == "annex" or (level > 1 and block_is_annex)
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
    """Drop body-less headings repeated later (a TOC without a CONTENTS title) and merge
    true repeats. Top-level numbers are compared document-wide; clause numbers only
    within their own top-level block, so "1.01" in Article 1 and in Appendix A differ."""
    def key(h):
        return (h["num"],) if h["level"] == 1 else (h["block"], h["num"])
    out: list[dict] = []
    for k, h in enumerate(heads):
        empty = not _join(h["lines"])
        later = any(key(x) == key(h) for x in heads[k + 1:])
        if empty and later:
            continue
        prev = next((x for x in out if key(x) == key(h)), None)
        if prev is not None:
            if not empty:
                prev["lines"] += [""] + h["lines"]; prev["parts"] += h["parts"]
                prev["title"] = prev["title"] or h["title"]
            continue
        out.append(h)
    for h in out:  # qualify clause numbers inside annexes so numbers stay unique
        if h["annex"]:
            b = h["block"]
            h["parts"] = [(n if n.startswith(b) else f"{b} {n}", t) for n, t in h["parts"]]
            if not h["num"].startswith(b):
                h["num"] = f"{b} {h['num']}"
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


def cite(number: str) -> str:
    """'3.01' -> '§3.01'; 'Appendix A 1.01' -> 'Appendix A, §1.01'; 'Appendix A' -> 'Appendix A'."""
    if not number:
        return ""
    if number[0].isdigit() or re.fullmatch(r"[IVXLC]+(?:\.\d+)*", number):
        return f"§{number}"
    head, _, last = number.rpartition(" ")
    if head and "." in last and last[0].isdigit():
        return f"{head}, §{last}"
    return number


def label(s: Section) -> str:
    if not s.number:
        return s.title or s.id
    return cite(s.number) + (f" {s.title}" if s.title else "")
