"""Section alignment and word-level diff."""
from __future__ import annotations

import difflib
import re
from bisect import bisect_left

from .sections import Section
from .similarity import ratio, token_ratio

TITLE_W, CONTENT_W = 0.35, 0.65
DEFAULT_MATCH = 55.0


def pair_score(a: Section, b: Section) -> float:
    content = max(ratio(a.text, b.text), token_ratio(a.text, b.text))
    if a.title and b.title:
        return TITLE_W * ratio(a.title, b.title) + CONTENT_W * content
    return content


def align(old: list[Section], new: list[Section], threshold: float = DEFAULT_MATCH):
    """Greedy best-first matching. Returns list of (old|None, new|None, score)."""
    cands = []
    for i, a in enumerate(old):
        for j, b in enumerate(new):
            s = pair_score(a, b)
            if s >= threshold:
                cands.append((s, -abs(i - j), i, j))
    cands.sort(reverse=True)
    used_o, used_n, pairs = set(), set(), {}
    for s, _, i, j in cands:
        if i in used_o or j in used_n:
            continue
        used_o.add(i); used_n.add(j); pairs[i] = (j, s)
    result = [(old[i], new[j], s) for i, (j, s) in pairs.items()]
    result += [(a, None, 0.0) for i, a in enumerate(old) if i not in used_o]
    result += [(None, b, 0.0) for j, b in enumerate(new) if j not in used_n]
    return result, _moved(pairs)


def _moved(pairs: dict) -> set[int]:
    """Old indices whose relative order changed (not on the longest increasing run)."""
    seq = sorted((i, j) for i, (j, _) in pairs.items())
    js = [j for _, j in seq]
    tails, tails_idx, prev = [], [], [-1] * len(js)
    for k, j in enumerate(js):
        p = bisect_left(tails, j)
        if p == len(tails):
            tails.append(j); tails_idx.append(k)
        else:
            tails[p] = j; tails_idx[p] = k
        prev[k] = tails_idx[p - 1] if p else -1
    keep, k = set(), tails_idx[-1] if tails_idx else -1
    while k != -1:
        keep.add(k); k = prev[k]
    return {seq[k][0] for k in range(len(seq)) if k not in keep}


TOKEN = re.compile(r"\s+|[^\s]+")


def word_diff(a: str, b: str) -> list[dict]:
    ta, tb = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    ops = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.append({"op": "equal", "text": " ".join(ta[i1:i2])})
        else:
            if i2 > i1:
                ops.append({"op": "delete", "text": " ".join(ta[i1:i2])})
            if j2 > j1:
                ops.append({"op": "insert", "text": " ".join(tb[j1:j2])})
    return ops


def render_word_diff(ops: list[dict], context: int = 8) -> str:
    out = []
    for k, o in enumerate(ops):
        t = o["text"]
        if o["op"] == "delete":
            out.append(f"~~{t}~~")
        elif o["op"] == "insert":
            out.append(f"**{t}**")
        else:
            words = t.split()
            if len(words) > 2 * context:
                head = words[:context] if k > 0 else []
                tail = words[-context:] if k < len(ops) - 1 else []
                t = " ".join(head + ["…"] + tail) if (head or tail) else "…"
            out.append(t)
    return " ".join(x for x in out if x)


def diff_documents(old: list[Section], new: list[Section], threshold: float = DEFAULT_MATCH,
                   include_unchanged: bool = False) -> list[dict]:
    pairs, moved = align(old, new, threshold)
    old_idx = {id(s): i for i, s in enumerate(old)}
    changes = []
    for a, b, score in pairs:
        if a and b:
            ops = word_diff(a.text, b.text)
            text_changed = any(o["op"] != "equal" for o in ops)
            kinds = []
            if text_changed:
                kinds.append("modified")
            if a.title != b.title:
                kinds.append("retitled")
            if a.number != b.number:
                kinds.append("renumbered")
            if old_idx[id(a)] in moved:
                kinds.append("moved")
            if not kinds and not include_unchanged:
                continue
            changes.append({"kinds": kinds or ["unchanged"], "old": a.to_dict(), "new": b.to_dict(),
                            "score": round(score, 1), "word_diff": ops if text_changed else []})
        elif a:
            changes.append({"kinds": ["removed"], "old": a.to_dict(), "new": None, "score": 0.0,
                            "word_diff": [{"op": "delete", "text": a.text}]})
        else:
            changes.append({"kinds": ["added"], "old": None, "new": b.to_dict(), "score": 0.0,
                            "word_diff": [{"op": "insert", "text": b.text}]})
    def key(c):
        s = c["new"] or c["old"]
        return (c["new"] is None, s["order"])
    changes.sort(key=key)
    for n, c in enumerate(changes, 1):
        c["id"] = f"c{n}"
    return changes
