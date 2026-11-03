#!/usr/bin/env python3
"""contract-review helper CLI. Deterministic, offline. Outputs JSON or Markdown.

Subcommands:
  extract  FILE                      plain text
  sections FILE                      JSON list of sections
  outline  FILE [--library Y]        JSON scaffold (or --format md)
  diff     OLD NEW [--summaries J]   JSON changes (or --format md)
  evolve   V1 V2 ... --section NAME  JSON timeline (or --format md)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crlib import __version__  # noqa: E402
from crlib import boilerplate, report  # noqa: E402
from crlib.diffing import DEFAULT_MATCH, diff_documents  # noqa: E402
from crlib.evolution import evolve  # noqa: E402
from crlib.extract import ExtractionError, extract_text  # noqa: E402
from crlib.outline import build  # noqa: E402
from crlib.sections import split_sections  # noqa: E402


def _secs(path, backend):
    return split_sections(extract_text(path, backend))


MAX_SUMMARY_FILE = 1_000_000  # bytes
MAX_SUMMARY_CHARS = 2000      # per entry
_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|~])")


def _load_summaries(path, known_ids, what="id"):
    """Read model-written summaries: a JSON object {id: string}. Each value becomes one
    Markdown-escaped line. Unknown ids are reported on stderr and ignored."""
    if not path:
        return {}
    p = Path(path)
    if p.stat().st_size > MAX_SUMMARY_FILE:
        raise ValueError(f"{p.name}: summaries file larger than {MAX_SUMMARY_FILE // 1000} KB")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{p.name}: not valid JSON ({exc.msg})") from exc
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError(f"{p.name}: summaries must be a JSON object of {what} -> string")
    out = {}
    for k, v in data.items():
        if k not in known_ids:
            print(f"warning: {p.name}: unknown {what} {k!r} ignored", file=sys.stderr)
            continue
        line = " ".join(v.split())
        if len(line) > MAX_SUMMARY_CHARS:
            line = line[:MAX_SUMMARY_CHARS - 1] + "…"
        out[k] = _MD_SPECIAL.sub(r"\\\1", line)
    return out


def _emit(obj, fmt, md):
    if fmt == "md":
        sys.stdout.write(md() if callable(md) else md)
    else:
        json.dump(obj, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="contract_review.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--pdf-backend", choices=["auto", "pdftotext", "pypdf"], default="auto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract"); p.add_argument("file")
    p = sub.add_parser("sections"); p.add_argument("file")
    p = sub.add_parser("outline"); p.add_argument("file")
    p.add_argument("--library"); p.add_argument("--threshold", type=float)
    p.add_argument("--no-fold", action="store_true"); p.add_argument("--format", choices=["json", "md"], default="json")
    p.add_argument("--summaries", help="optional JSON {section_id: plain summary} written by the model (off by default)")
    p = sub.add_parser("diff"); p.add_argument("old"); p.add_argument("new")
    p.add_argument("--match-threshold", type=float, default=DEFAULT_MATCH)
    p.add_argument("--summaries", help="JSON {change_id: one-line summary} written by the model")
    p.add_argument("--format", choices=["json", "md"], default="json")
    p = sub.add_parser("evolve"); p.add_argument("files", nargs="+")
    p.add_argument("--section", required=True); p.add_argument("--match-threshold", type=float, default=DEFAULT_MATCH)
    p.add_argument("--summary-file", help="text file with the model's overall summary")
    p.add_argument("--notes", help="JSON {version: note} written by the model")
    p.add_argument("--format", choices=["json", "md"], default="json")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "extract":
            sys.stdout.write(extract_text(a.file, a.pdf_backend))
        elif a.cmd == "sections":
            _emit([s.to_dict() for s in _secs(a.file, a.pdf_backend)], "json", None)
        elif a.cmd == "outline":
            lib = None if a.no_fold else boilerplate.load_library(a.library)
            o = build(_secs(a.file, a.pdf_backend), lib, a.threshold)
            summ = _load_summaries(a.summaries, {x["id"] for x in o["sections"]}, "section id")
            _emit(o, a.format, lambda: report.outline_markdown(
                o, Path(a.file).name, summ))
        elif a.cmd == "diff":
            ch = diff_documents(_secs(a.old, a.pdf_backend), _secs(a.new, a.pdf_backend), a.match_threshold)
            summ = _load_summaries(a.summaries, {c["id"] for c in ch}, "change id")
            _emit(ch, a.format, lambda: report.diff_markdown(ch, Path(a.old).name, Path(a.new).name, summ))
        elif a.cmd == "evolve":
            if len(a.files) < 2:
                ap.error("evolve needs at least two versions")
            vs = [(Path(f).name, _secs(f, a.pdf_backend)) for f in a.files]
            r = evolve(vs, a.section, a.match_threshold)
            summ = Path(a.summary_file).read_text(encoding="utf-8").strip() if a.summary_file else None
            notes = _load_summaries(a.notes, {n for n, _ in vs}, "version")
            _emit(r, a.format, lambda: report.evolution_markdown(r, summ, notes))
    except (ExtractionError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
