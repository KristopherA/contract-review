"""Markdown rendering. Model-written summaries are merged in by change id."""
from __future__ import annotations

import re

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|~&!])")
_AUTOLINK = re.compile(r"(?:https?://|ftp://|www\.)\S+|\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.I)


def md_escape(text: str) -> str:
    """One line of model-written text, safe inside Markdown and tables: whitespace
    collapsed, specials (incl. & and |) backslash-escaped, and URLs/emails shown as
    code spans so they never become live links."""
    text = " ".join(text.split())
    out, pos = [], 0
    for m in _AUTOLINK.finditer(text):
        out.append(_MD_SPECIAL.sub(r"\\\1", text[pos:m.start()]))
        url = m.group(0)
        tail = len(url) - len(url.rstrip(").,;:!?'\"]>"))
        if tail:  # "(see https://x.org)." -> the ")." stays outside the span
            url = url[:-tail]
        # GFM splits table cells on "|" even inside code spans, so escape it there too
        out.append("`" + url.replace("`", "'").replace("|", "\\|") + "`")
        pos = m.start() + len(url)
    out.append(_MD_SPECIAL.sub(r"\\\1", text[pos:]))
    return "".join(out)

from .diffing import render_word_diff
from .sections import cite

NOTE = "> _Generated locally by contract-review. Not legal advice; verify against the source documents._\n"


def _lbl(s):
    if not s:
        return "—"
    return f"{cite(s['number'])} {s['title']}".strip() if s["number"] else (s["title"] or s["id"])


def diff_markdown(changes, old_name, new_name, summaries=None) -> str:
    summaries = summaries or {}
    lines = [f"# Contract diff: {old_name} → {new_name}", "", NOTE,
             f"{len(changes)} change(s).", "",
             "| # | Change | Old | New | Summary |", "|---|---|---|---|---|"]
    for c in changes:
        summ = re.sub(r"(?<!\\)\|", r"\\|", summaries.get(c["id"], "_(summary pending)_")).replace("\n", " ")
        kinds = ", ".join(c["kinds"]) + (" ⚠ low-confidence match" if c.get("low_confidence") else "")
        lines.append(f"| {c['id']} | {kinds} | {_lbl(c['old'])} | {_lbl(c['new'])} | {summ} |")
    lines.append("")
    for c in changes:
        lines += [f"## {c['id']}: {_lbl(c['new'] or c['old'])} ({', '.join(c['kinds'])})", ""]
        if c.get("low_confidence"):
            lines += [f"> ⚠ Low-confidence pairing (score {c['score']}): check these really are the same clause.", ""]
        if c["id"] in summaries:
            lines += [f"**Summary:** {summaries[c['id']]}", ""]
        if c["word_diff"]:
            lines += [render_word_diff(c["word_diff"]), ""]
    return "\n".join(lines)


def evolution_markdown(result, summary=None, notes=None) -> str:
    notes = notes or {}
    lines = [f"# Evolution of “{result['query']}”", "", NOTE]
    if summary:
        lines += ["## Summary", "", md_escape(summary), ""]
    lines += ["## Timeline", "", "| Version | Clause | Status | Note |", "|---|---|---|---|"]
    for e in result["timeline"]:
        cl = _lbl(e.get("section")) if e["present"] else "—"
        st = e["status"] + (f" (was §{e['renumbered_from']})" if e.get("renumbered_from") else "")
        lines.append(f"| {e['version']} | {cl} | {st} | {notes.get(e['version'], '')} |")
    lines.append("")
    for e in result["timeline"]:
        if e.get("word_diff"):
            lines += [f"### {e['version']}", "", render_word_diff(e["word_diff"]), ""]
    return "\n".join(lines)


def outline_markdown(outline, name, summaries=None) -> str:
    """Key facts per real section; optional model summaries ({section id: text})."""
    summaries = summaries or {}
    lines = [f"# Outline: {name}", "", NOTE,
             f"{len(outline['sections'])} section(s); {len(outline['boilerplate_folded'])} folded as boilerplate.", ""]
    for s in outline["sections"]:
        lines += [f"## {s['cite']}", ""]
        if s["id"] in summaries:
            lines += [f"**Summary:** {summaries[s['id']]}", ""]
        f = s["key_facts"]
        vals = []
        for key, lbl in (("amounts", "Amounts"), ("percentages", "Percentages"), ("durations", "Time periods"),
                         ("dates", "Dates")):
            if f[key]:
                vals.append(f"- **{lbl}:** " + "; ".join(f"{x['value']} ({x['cite']})" for x in f[key]))
        vals += [f"- **Deadline:** {x['text']} ({x['cite']})" for x in f["deadlines"]]
        vals += [f"- **{x['kind'].capitalize()}:** {x['text']} ({x['cite']})" for x in f["obligations"]]
        vals += [f"- **Definition:** {x['text']} ({x['cite']})" for x in f.get("definitions", [])]
        lines += (vals or ["- No numeric facts or obligations found."]) + [""]
    lines += ["## Folded boilerplate", ""]
    if outline["boilerplate_folded"]:
        for f in outline["boilerplate_folded"]:
            lines.append(f"- {f['section']} ≈ standard `{f['clause']}` ({f['score']}%)")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"
