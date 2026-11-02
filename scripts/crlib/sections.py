"""Split contract text into numbered sections."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

HEADING = re.compile(
    r"^(?:(?P<kw>section|article|clause|schedule)\s+)?"
    r"(?P<num>\d{1,3}(?:\.\d{1,3}){0,4}|[IVXLC]{1,6})"
    r"(?P<punct>[.):]?)\s+(?P<rest>\S.*)$",
    re.IGNORECASE,
)


@dataclass
class Section:
    id: str
    number: str
    title: str
    level: int
    text: str
    order: int
    lines: list[str] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("lines")
        return d


def _parse_heading(line: str):
    m = HEADING.match(line)
    if not m:
        return None
    num, rest, kw, punct = m["num"], m["rest"].strip(), m["kw"], m["punct"]
    if re.fullmatch(r"[IVXLC]+", num) and not kw and not punct:
        return None  # avoid "I agree ..." style false positives
    if not kw and "." not in num and not punct:
        return None  # bare "3 days" is not a heading
    if re.match(r"^(days?|months?|years?|%|percent)\b", rest, re.IGNORECASE):
        return None
    title, body = rest, ""
    m2 = re.match(r"^(.{1,80}?)[.:]\s+(.*)$", rest)
    if m2 and len(m2[1].split()) <= 10:
        title, body = m2[1], m2[2]
    elif len(rest) > 80 or len(rest.split()) > 10:
        title, body = "", rest
    title = title.rstrip(".:").strip()
    level = num.count(".") + 1 if not re.fullmatch(r"[IVXLC]+", num) else 1
    return num.rstrip("."), title, body, level


def split_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    preamble: list[str] = []
    current: Section | None = None
    for raw in text.split("\n"):
        line = raw.strip()
        parsed = _parse_heading(line) if line else None
        if parsed:
            num, title, body, level = parsed
            current = Section(id=f"s{len(sections)+1}", number=num, title=title,
                              level=level, text="", order=len(sections))
            if body:
                current.lines.append(body)
            sections.append(current)
        elif current is None:
            preamble.append(line)
        else:
            current.lines.append(line)
    for s in sections:
        s.text = _join(s.lines)
    pre = _join(preamble)
    if pre:
        sections.insert(0, Section(id="s0", number="", title="Preamble", level=0,
                                   text=pre, order=-1))
    return sections


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
