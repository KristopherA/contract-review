"""Track one named section across N versions."""
from __future__ import annotations

import re

from .diffing import align, word_diff, DEFAULT_MATCH
from .sections import Section
from .similarity import norm, ratio

NUM_PREFIX = re.compile(r"^(?:article|art\.?|section|sec\.?|clause|cl\.?|s\.)\s*(?=\d|§)", re.I)
ALIASES = {"lou": "letter of understanding", "loa": "letter of agreement", "mou": "memorandum of understanding"}
FAMILIES = ("appendix", "schedule", "annex", "exhibit", "letter of understanding", "letter of agreement",
            "memorandum of understanding")
MIN_FUZZY = 70.0
MAX_QUERY = 200  # characters


class AmbiguousQuery(ValueError):
    """Two or more sections match equally well; the CLI exits 2 and lists them."""

    def __init__(self, msg, candidates=()):
        super().__init__(msg)
        self.candidates = list(candidates)


def _num_key(q: str) -> tuple[str, str | None]:
    """(normalised number, note). '§12.01' -> '12.01'; '12,01' -> '12.01';
    '12.01(a)' -> '12.01' (sub-items are not sections); 'LOU 3' -> 'letter of understanding 3'."""
    q = q.strip().lstrip("§").strip()
    q = NUM_PREFIX.sub("", q).lstrip("§").strip()
    note = None
    if re.fullmatch(r"\d{1,3},\d{1,3}", q):
        q = q.replace(",", ".")
    m = re.fullmatch(r"(.*?\d)\s*((?:\([a-z0-9]{1,4}\))+)", q, re.I)
    if m:
        q, note = m[1], f"sub-item {m[2]} is inside §{m[1]}; following §{m[1]}"
    q = re.sub(r"\s+", " ", q.replace(",", " ")).strip().casefold()
    first, _, rest = q.partition(" ")
    if first in ALIASES:
        q = (ALIASES[first] + " " + rest).strip()
    return q, note


def _label(s: Section) -> str:
    return " ".join(x for x in (f"§{s.number}" if s.number else "", s.title) if x) or s.id


def _hit(s, how, score, part=None, others=(), note=None):
    return {"section": s, "how": how, "score": score, "part": part, "others": list(others), "note": note}


def match_section(sections: list[Section], query: str, min_score: float = MIN_FUZZY) -> dict | None:
    """Find one section for `query` in one version, in this order: exact section id,
    clause number (a heading's number, or a cite inside a section, which returns that
    section), then title: equal, whole-word substring, fuzzy (rapidfuzz).
    Returns {"section", "how", "score", "part", "others", "note"} or None. Raises
    AmbiguousQuery (with .candidates) when the best candidates tie exactly."""
    q = query.strip()
    if not q:
        return None
    if len(q) > MAX_QUERY:
        raise ValueError(f"--section is {len(q)} characters; use at most {MAX_QUERY} (a number or a title)")
    for s in sections:
        if s.id == q:
            return _hit(s, "id", 100.0)
    key, note = _num_key(q)
    if key and (re.search(r"\d", key) or key.startswith(FAMILIES)):
        for s in sections:
            if s.number and s.number.casefold() == key:
                return _hit(s, "number", 100.0, note=note)
        for s in sections:
            for cite, _t in s.parts:
                if cite.casefold() == key:
                    return _hit(s, "number", 99.0, part=cite, note=note)
        if key in FAMILIES:  # bare "LOU" / "Appendix": one of that family, or say which
            fam = [s for s in sections if s.level == 1 and s.number.casefold().startswith(key)]
            if len(fam) == 1:
                return _hit(fam[0], "number", 95.0)
            if fam:
                raise AmbiguousQuery(f"--section {query!r} names a family with {len(fam)} sections: "
                                     + "; ".join(_label(s) for s in fam) + ". Add its number (e.g. 'LOU 3').", fam)
    nq = norm(q, keep_numbers=True)
    cands = []
    for s in sections:
        if not s.title:
            continue
        nt = norm(s.title, keep_numbers=True)
        if nq and nt == nq:
            cands.append((3, 100.0, s, "title"))
        elif len(nq) >= 3 and re.search(rf"(?<!\w){re.escape(nq)}(?!\w)", nt):
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
                             + "; ".join(_label(c[2]) for c in ties) + ". Use a clause number or a longer title.",
                             [c[2] for c in ties])
    return _hit(top[2], top[3], round(top[1], 1), others=[_label(c[2]) for c in cands[1:6]])


def find_section(sections: list[Section], query: str, min_score: float = MIN_FUZZY):
    m = match_section(sections, query, min_score)
    return (m["section"], m["score"]) if m else (None, 0.0)


def evolve(versions: list[tuple[str, list[Section]]], query: str,
           threshold: float = DEFAULT_MATCH) -> dict:
    """Find the query in the first version that has it; after that, follow the clause by
    alignment from the previous version's section. A direct match (number or title) in a
    later version is used only when alignment finds nothing, or when it agrees with
    alignment; a disagreeing direct match is reported in `warnings`. A tie in a later
    version is broken by alignment; a tie with nothing to follow raises AmbiguousQuery."""
    if len(query.strip()) > MAX_QUERY:
        raise ValueError(f"--section is {len(query.strip())} characters; use at most {MAX_QUERY} (a number or a title)")
    timeline, prev, warnings = [], None, []
    for k, (name, secs) in enumerate(versions):
        aligned = None
        if prev is not None:
            pairs, _ = align(versions[k - 1][1], secs, threshold)
            aligned = next((b for a, b, _s in pairs if a is prev and b is not None), None)
        try:
            m = match_section(secs, query)
        except AmbiguousQuery as exc:
            if aligned is None:
                raise
            m = None
            if aligned not in exc.candidates:
                warnings.append(f"{name}: {exc}; following the aligned {_label(aligned)}")
        if aligned is not None:
            cur, how = aligned, "aligned"
            if m and m["section"] is aligned:
                how = f"aligned+{m['how']}"
            elif m:
                warnings.append(f"{name}: --section {query!r} also matches {_label(m['section'])} ({m['how']}); "
                                f"following the aligned {_label(aligned)} from {versions[k - 1][0]}")
        else:
            cur, how = (m["section"], m["how"]) if m else (None, None)
            if m and m["others"]:
                warnings.append(f"{name}: --section {query!r} matched {_label(cur)} ({how}); "
                                f"also close: {'; '.join(m['others'])}")
        if m and m["note"]:
            warnings.append(f"{name}: {m['note']}")
        if m and m["how"] == "id" and len(versions) > 1:
            warnings.append(f"{name}: section ids are positional ({query!r} is the {query[1:]}th section of this "
                            "version and can name a different clause in another); prefer a number or title")
        entry = {"version": name, "index": k, "present": cur is not None}
        if cur is not None:
            entry["section"] = cur.to_dict()
            entry["matched_by"] = how
            if m and m["part"] and m["section"] is cur:
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
    if not any(e["present"] for e in timeline):
        warnings.append(f"no version has a section matching {query!r}; try a clause number ('12', '12.01', "
                        "'Appendix A 1.02', 'LOU 3') or a whole word from the title (run `sections` to list them)")
    return {"query": query, "timeline": timeline, "warnings": list(dict.fromkeys(warnings))}
