"""Track one named section across N versions."""
from __future__ import annotations

from .diffing import align, word_diff, DEFAULT_MATCH
from .sections import Section
from .similarity import ratio


def find_section(sections: list[Section], query: str, min_score: float = 70.0):
    q = query.strip().lstrip("§").strip()
    for s in sections:
        if s.number and s.number == q:
            return s, 100.0
    best = None
    for s in sections:
        sc = ratio(s.title, q) if s.title else 0.0
        if best is None or sc > best[1]:
            best = (s, sc)
    return best if best and best[1] >= min_score else (None, 0.0)


def evolve(versions: list[tuple[str, list[Section]]], query: str,
           threshold: float = DEFAULT_MATCH) -> dict:
    timeline, prev = [], None
    for k, (name, secs) in enumerate(versions):
        cur = None
        if prev is not None:
            pairs, _ = align(versions[k - 1][1], secs, threshold)
            for a, b, _s in pairs:
                if a is prev and b is not None:
                    cur = b
                    break
        if cur is None:
            cur, _ = find_section(secs, query)
        entry = {"version": name, "index": k, "present": cur is not None}
        if cur is not None:
            entry["section"] = cur.to_dict()
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
    return {"query": query, "timeline": timeline}
