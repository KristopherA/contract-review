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


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


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
            _emit(o, a.format, lambda: report.outline_markdown(o, Path(a.file).name,
                                                                    _load_json(a.summaries)))
        elif a.cmd == "diff":
            ch = diff_documents(_secs(a.old, a.pdf_backend), _secs(a.new, a.pdf_backend), a.match_threshold)
            _emit(ch, a.format, lambda: report.diff_markdown(ch, Path(a.old).name, Path(a.new).name,
                                                             _load_json(a.summaries)))
        elif a.cmd == "evolve":
            if len(a.files) < 2:
                ap.error("evolve needs at least two versions")
            vs = [(Path(f).name, _secs(f, a.pdf_backend)) for f in a.files]
            r = evolve(vs, a.section, a.match_threshold)
            summ = Path(a.summary_file).read_text(encoding="utf-8").strip() if a.summary_file else None
            _emit(r, a.format, lambda: report.evolution_markdown(r, summ, _load_json(a.notes)))
    except (ExtractionError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
