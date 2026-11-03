"""Track one named section across N versions."""
from __future__ import annotations

import re

from .diffing import align, word_diff, DEFAULT_MATCH
from .sections import Section
from .similarity import norm, ratio


NUM_PREFIX = re.compile(r"^(?:article|art\.?|section|sec\.?|clause|cl\.?|s\.)\s*", re.I)
MIN_FUZZY = 70.0


class AmbiguousQuery(ValueError):
    """Two or more sections match equally well; the CLI exits 2 and lists them."""


def _num_key(q: str) -> str:
    q = q.strip().lstrip("§").strip()
    q = NUM_PREFIX.sub("", q)
    return re.sub(r"\s+", " ", q.replace(",", " ")).strip().casefold()


def _label(s: Section) -> str:
    return " ".join(x for x in (f"§{s.number}" if s.number else "", s.title) if x) or s.id


def match_section(sections: list[Section], query: str, min_score: float = MIN_FUZZY) -> dict | None:
    """Find one section for `query` in one version, in this order: exact section id,
    clause number (a heading's number, or a cite inside a section, which returns that
    section), then title: equal, case-insensitive substring, fuzzy (rapidfuzz).
    Returns {"section", "how", "score", "part", "others"} or None. Raises
    AmbiguousQuery when the best candidates tie exactly."""
    q = query.strip()
    if not q:
        return None
    for s in sections:
        if s.id == q:
            return {"section": s, "how": "id", "score": 100.0, "part": None, "others": []}
    key = _num_key(q)
    if key and re.search(r"\d|^appendix|^schedule|^annex|^exhibit|^lou|^letter", key):
        for s in sections:
            if s.number and s.number.casefold() == key:
                return {"section": s, "how": "number", "score": 100.0, "part": None, "others": []}
        for s in sections:
            for cite, _t in s.parts:
                if cite.casefold() == key:
                    return {"section": s, "how": "number", "score": 99.0, "part": cite, "others": []}
    nq = norm(q, keep_numbers=True)
    cands = []
    for s in sections:
        if not s.title:
            continue
        nt = norm(s.title, keep_numbers=True)
        if nq and nt == nq:
            cands.append((3, 100.0, s, "title"))
        elif len(nq) >= 3 and nq in nt:
            cands.append((2, 90.0 + 10.0 * len(nq) / len(nt), s, "title-substring"))
        else:
            sc = ratio(s.title, q)
            if sc >= min_score:
                cands.append((1, sc, s, "title-fuzzy"))
    if not cands:
        return None
    cands.sort(key=lambda c: (-c[0], -c[1], c[2].order))
    top = cands[0]
    ties = [c for c in cands if c[0] == top[0] and abs(c[1] - top[1]) < 1e-9]
    if len(ties) > 1:
        raise AmbiguousQuery(f"--section {query!r} matches several sections equally well: "
                             + "; ".join(_label(c[2]) for c in ties) + ". Use a clause number or a longer title.")
    return {"section": top[2], "how": top[3], "score": round(top[1], 1), "part": None,
            "others": [_label(c[2]) for c in cands[1:6]]}


def find_section(sections: list[Section], query: str, min_score: float = MIN_FUZZY):
    m = match_section(sections, query, min_score)
    return (m["section"], m["score"]) if m else (None, 0.0)


def evolve(versions: list[tuple[str, list[Section]]], query: str,
           threshold: float = DEFAULT_MATCH) -> dict:
    """Each version is matched on its own (match_section), so a renumbered clause is
    still found by title. Only when a version has no match is the previous version's
    section followed by alignment (catches a retitled clause)."""
    timeline, prev, warnings = [], None, []
    for k, (name, secs) in enumerate(versions):
        m = match_section(secs, query)
        cur, how = (m["section"], m["how"]) if m else (None, None)
        if cur is None and prev is not None:
            pairs, _ = align(versions[k - 1][1], secs, threshold)
            for a, b, _s in pairs:
                if a is prev and b is not None:
                    cur, how = b, "aligned"
                    break
        if m and m["others"]:
            warnings.append(f"{name}: --section {query!r} matched {_label(cur)} ({how}); "
                            f"also close: {'; '.join(m['others'])}")
        entry = {"version": name, "index": k, "present": cur is not None}
        if cur is not None:
            entry["section"] = cur.to_dict()
            entry["matched_by"] = how
            if m and m["part"]:
                entry["matched_part"] = m["part"]
            if prev is None:
                seen = any(t["present"] for t in timeline)
                entry["status"] = "reappeared" if seen else ("first-seen" if k else "baseline")
            else:
                ops = word_diff(prev.text, cur.text)
                changed = any(o["op"] != "equal" for o in ops)
                entry["status"] = "changed" if changed else "unchanged"
                if prev.number != cur.number:
                    entry["renumbered_from"] = prev.number
                if changed:
                    entry["word_diff"] = ops
        else:
            entry["status"] = "absent" if prev is None else "removed"
        timeline.append(entry)
        prev = cur
    return {"query": query, "timeline": timeline, "warnings": warnings}
