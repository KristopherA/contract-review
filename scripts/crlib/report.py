"""Markdown rendering. Model-written summaries are merged in by change id."""
from __future__ import annotations

from .diffing import render_word_diff

NOTE = "> _Generated locally by contract-review. Not legal advice; verify against the source documents._\n"


def _lbl(s):
    if not s:
        return "—"
    return f"§{s['number']} {s['title']}".strip() if s["number"] else (s["title"] or s["id"])


def diff_markdown(changes, old_name, new_name, summaries=None) -> str:
    summaries = summaries or {}
    lines = [f"# Contract diff: {old_name} → {new_name}", "", NOTE,
             f"{len(changes)} change(s).", "",
             "| # | Change | Old | New | Summary |", "|---|---|---|---|---|"]
    for c in changes:
        summ = summaries.get(c["id"], "_(summary pending)_").replace("|", "\\|").replace("\n", " ")
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
        lines += ["## Summary", "", summary, ""]
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


def outline_markdown(outline, name) -> str:
    lines = [f"# Outline scaffold: {name}", "", NOTE, "## Sections", ""]
    for s in outline["sections"]:
        hints = ", ".join(s["topic_hints"]) or "—"
        lines.append(f"- **{s['cite']}** — hints: {hints}")
    lines += ["", "## Folded boilerplate", ""]
    if outline["boilerplate_folded"]:
        for f in outline["boilerplate_folded"]:
            lines.append(f"- {f['section']} ≈ standard `{f['clause']}` ({f['score']}%)")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"
