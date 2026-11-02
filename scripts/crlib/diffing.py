"""Section alignment and word-level diff."""
from __future__ import annotations

import difflib
import re
from bisect import bisect_left

from .sections import Section
from .similarity import ratio, token_ratio

TITLE_W, CONTENT_W = 0.35, 0.65
DEFAULT_MATCH = 55.0
LOW_CONFIDENCE = 65.0     # pairs scoring below this are flagged for the reader
CONTENT_FALLBACK = 65.0   # match on content alone when the title was rewritten
SPLIT_MERGE_MIN = 80.0    # combined text must reach this similarity
SPLIT_MERGE_GAIN = 10.0   # ...and beat the single-section similarity by this much


def content_score(a: Section, b: Section) -> float:
    return max(ratio(a.text, b.text), token_ratio(a.text, b.text))


def pair_score(a: Section, b: Section) -> float:
    content = content_score(a, b)
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
    # Pass 2: content-dominant fallback for retitled sections the blend missed.
    fb = []
    for i, a in enumerate(old):
        if i in used_o:
            continue
        for j, b in enumerate(new):
            if j not in used_n:
                c = content_score(a, b)
                if c >= max(CONTENT_FALLBACK, threshold):
                    fb.append((c, -abs(i - j), i, j))
    for c, _, i, j in sorted(fb, reverse=True):
        if i in used_o or j in used_n:
            continue
        used_o.add(i); used_n.add(j); pairs[i] = (j, c)
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
    new_idx = {id(s): j for j, s in enumerate(new)}
    split_into, merged_from, absorbed = _split_merge(pairs, old_idx, new_idx)
    changes = []
    for a, b, score in pairs:
        if (a is not None and id(a) in absorbed) or (b is not None and id(b) in absorbed):
            continue
        if a and b:
            extra_new = split_into.get(id(a), [])
            extra_old = merged_from.get(id(b), [])
            a_text = " ".join([a.text] + [x.text for x in extra_old])
            b_text = " ".join([b.text] + [x.text for x in extra_new])
            ops = word_diff(a_text, b_text)
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
            if extra_new:
                kinds.append("split")
            if extra_old:
                kinds.append("merged")
            if not kinds and not include_unchanged:
                continue
            ch = {"kinds": kinds or ["unchanged"], "old": a.to_dict(), "new": b.to_dict(),
                  "score": round(score, 1), "low_confidence": score < LOW_CONFIDENCE,
                  "word_diff": ops if text_changed else []}
            if extra_new:
                ch["split_into"] = [x.to_dict() for x in extra_new]
            if extra_old:
                ch["merged_from"] = [x.to_dict() for x in extra_old]
            changes.append(ch)
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


def _split_merge(pairs, old_idx, new_idx):
    """Attach unmatched sections that are a piece of a matched one.

    Split: old A -> new B + new C (C unmatched, near B).
    Merge: old A + old C -> new B (C unmatched, near A).
    Accepted only when the combined text is clearly closer than the single one.
    """
    matched = [(a, b) for a, b, _ in pairs if a and b]
    un_new = [b for a, b, _ in pairs if a is None]
    un_old = [a for a, b, _ in pairs if b is None]
    split_into, merged_from, absorbed = {}, {}, set()
    for c in un_new:
        best = None
        for a, b in matched:
            if abs(new_idx[id(c)] - new_idx[id(b)]) > 2:
                continue
            parts = sorted([b, *split_into.get(id(a), [])], key=lambda x: new_idx[id(x)])
            base = ratio(a.text, " ".join(x.text for x in parts))
            parts = sorted(parts + [c], key=lambda x: new_idx[id(x)])
            comb = ratio(a.text, " ".join(x.text for x in parts))
            if comb >= SPLIT_MERGE_MIN and comb >= base + SPLIT_MERGE_GAIN and (best is None or comb > best[0]):
                best = (comb, a)
        if best:
            split_into.setdefault(id(best[1]), []).append(c); absorbed.add(id(c))
    for c in un_old:
        best = None
        for a, b in matched:
            if abs(old_idx[id(c)] - old_idx[id(a)]) > 2:
                continue
            parts = sorted([a, *merged_from.get(id(b), [])], key=lambda x: old_idx[id(x)])
            base = ratio(" ".join(x.text for x in parts), b.text)
            parts = sorted(parts + [c], key=lambda x: old_idx[id(x)])
            comb = ratio(" ".join(x.text for x in parts), b.text)
            if comb >= SPLIT_MERGE_MIN and comb >= base + SPLIT_MERGE_GAIN and (best is None or comb > best[0]):
                best = (comb, b)
        if best:
            merged_from.setdefault(id(best[1]), []).append(c); absorbed.add(id(c))
    return split_into, merged_from, absorbed
