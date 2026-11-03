"""Draft-6 regressions: linear-time regexes (B1), page furniture and annex splitting (B2),
negated modals (B3), --summaries validation, and a pdftotext run over a multi-page CBA.
All text here is synthetic."""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from crlib import facts
from crlib.extract import extract_text
from crlib.sections import _strip_leader, split_sections
from conftest import make_pdf

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "contract_review.py"


def run(*args):
    r = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def timed(fn, *a):
    t0 = time.perf_counter()
    out = fn(*a)
    return out, time.perf_counter() - t0


# ---------- B1: no super-linear regex paths ----------
@pytest.mark.parametrize("text", [
    "thirty-" * 20000,
    "a-" * 20000 + " and one-half days",
    "ab- " * 20000,
    "1. Title" + ". " * 20000,
    "1. Title" + "." * 40000,
])
def test_pathological_lines_are_fast(text):
    _, t1 = timed(facts.extract, [("1", text)])
    _, t2 = timed(split_sections, text)
    assert t1 < 1.0 and t2 < 1.0, (t1, t2)


def test_strip_leader_is_linear_without_line_cap():
    _, t = timed(_strip_leader, "Wages" + " ." * 100000 + " 12")
    assert t < 1.0


def test_wordnum_still_matches_after_fixed_list():
    f = facts.extract([("1", "Notice of twenty-one (21) days and two and one-half days leave.")])
    vals = [d["value"] for d in f["durations"]]
    assert any("twenty-one (21) days" in v for v in vals)
    assert any("two and one-half days" in v for v in vals)


# ---------- B2: splitter keeps content and separates annexes ----------
def _body(secs):
    return "\n".join(s.text for s in secs)


def test_lone_number_line_is_kept():
    secs = split_sections("ARTICLE 1: RATES\n1.01 The rate shall be:\n1500\nper month.\n")
    assert "1500" in _body(secs)


def test_page_furniture_forms_are_dropped():
    txt = ("ARTICLE 1: RATES\n1.01 Body one.\n- 2 -\n\f\n1.02 Body two.\nPage 3 of 9\n")
    body = _body(split_sections(txt))
    assert "- 2 -" not in body and "Page 3" not in body and "Body two" in body


def test_repeated_running_header_and_sequential_page_numbers_dropped():
    names = ["PURPOSE", "WAGES", "HOURS", "LEAVE"]
    pages = [f"SAMPLE HEADER 2030\nARTICLE {n}: {names[n - 1]}\n{n}.01 Text of clause {n}.\n{n + 10}"
             for n in range(1, 5)]
    body = _body(split_sections("\n\f\n".join(pages)))
    assert "SAMPLE HEADER" not in body
    assert not any(str(n + 10) in body.split() for n in range(1, 5))
    assert "Text of clause 3" in body
    assert [s.number for s in split_sections("\n\f\n".join(pages))] == ["1", "2", "3", "4"]


def test_lou_and_appendix_are_top_level_with_scoped_numbers():
    txt = ("ARTICLE 1: PURPOSE\n1.01 Purpose text.\n1.02 More purpose.\n"
           "LETTER OF UNDERSTANDING\nRe: Remote Work\n1.01 Letter text.\n1.02 More letter.\n"
           "APPENDIX A\nWage Grid\n1.01 Grid text.\n1.02 More grid.\n")
    secs = split_sections(txt)
    tops = [s.number for s in secs if s.level == 1]
    assert tops == ["1", "Letter of Understanding", "Appendix A"]
    lou = next(s for s in secs if s.number == "Letter of Understanding")
    assert lou.title == "Remote Work"
    nums = [p[0] for s in secs for p in s.parts]
    assert {"1.01", "Letter of Understanding 1.01", "Appendix A 1.01"} <= set(nums)
    body = _body(secs)
    assert all(t in body for t in ("Purpose text", "Letter text", "Grid text"))


def test_cross_reference_line_is_not_a_heading():
    txt = "ARTICLE 2: WAGES\n2.01 Pay is set out in\nArticle 2.03 (a) of this Agreement.\n2.03 Rates.\n"
    assert [s.number for s in split_sections(txt) if s.level == 1] == ["2"]


def test_upper_case_article_heading_with_colon():
    secs = split_sections("ARTICLE 8: HOURS OF WORK\n8.01 Hours text.\n")
    assert secs[0].number == "8" and secs[0].title == "HOURS OF WORK"


# ---------- B3: negated modals ----------
@pytest.mark.parametrize("sentence,kind", [
    ("The Employer may not dismiss an Employee without cause.", "prohibition"),
    ("The Union will not strike during the term.", "prohibition"),
    ("The Employer cannot assign split shifts.", "prohibition"),
    ("The Employer shall not deduct fees.", "prohibition"),
    ("An Employee must not disclose records.", "prohibition"),
    ("The Employer will pay the premium.", "obligation"),
    ("An Employee may request leave.", "right"),
])
def test_modal_polarity(sentence, kind):
    assert facts.obligation(sentence)["kind"] == kind


# ---------- --summaries validation ----------
@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("ARTICLE 1: PURPOSE\n1.01 Purpose text.\nARTICLE 2: WAGES\n2.01 Wage text.\n")
    return p


@pytest.mark.parametrize("payload", ['["x"]', '{"s1": 5}', '{"s1": {"a": 1}}', "not json"])
def test_summaries_bad_shape_exits_2(doc, tmp_path, payload):
    j = tmp_path / "s.json"
    j.write_text(payload)
    code, _, err = run("outline", doc, "--format", "md", "--summaries", j)
    assert code == 2 and "Traceback" not in err


def test_summaries_too_large_exits_2(doc, tmp_path):
    j = tmp_path / "s.json"
    j.write_text(json.dumps({"s1": "x" * 1_100_000}))
    code, _, err = run("outline", doc, "--format", "md", "--summaries", j)
    assert code == 2 and "larger" in err


def test_summaries_one_line_escaped_and_unknown_warned(doc, tmp_path):
    out = json.loads(run("outline", doc)[1])
    sid = out["sections"][0]["id"]
    j = tmp_path / "s.json"
    j.write_text(json.dumps({sid: "Line one\n# not a heading | *bold*", "zz9": "stray"}))
    code, md, err = run("outline", doc, "--format", "md", "--summaries", j)
    assert code == 0
    assert "unknown section id 'zz9'" in err and "stray" not in md
    assert "Line one \\# not a heading \\| \\*bold\\*" in md
    assert "\n# not a heading" not in md


def test_diff_summary_pipe_not_double_escaped(doc, tmp_path):
    b = tmp_path / "b.txt"
    b.write_text(doc.read_text().replace("Wage text", "Revised wage text"))
    ch = json.loads(run("diff", doc, b)[1])
    j = tmp_path / "s.json"
    j.write_text(json.dumps({ch[0]["id"]: "a | b"}))
    code, md, _ = run("diff", doc, b, "--format", "md", "--summaries", j)
    assert code == 0 and "a \\| b" in md and "\\\\|" not in md


# ---------- pdftotext end-to-end on a synthetic multi-page CBA ----------
@pytest.mark.skipif(not shutil.which("pdftotext"), reason="pdftotext not installed")
def test_pdftotext_multipage_cba(fixtures, tmp_path):
    raw = (fixtures / "cba_annex.txt").read_text(encoding="utf-8").splitlines()
    lines = ["\f" if ln == "\\f" else ln for ln in raw]
    pdf = make_pdf(tmp_path / "cba.pdf", lines)
    secs = split_sections(extract_text(pdf, pdf_backend="pdftotext"))
    tops = [s.number for s in secs if s.level == 1]
    assert tops == ["1", "2", "3", "Letter of Understanding", "Appendix A"]  # TOC skipped
    body = _body(secs)
    assert "1500" in body                                   # lone number kept
    assert "SAMPLE AGREEMENT" not in body and "- 3 -" not in body and "Page 1 of" not in body
    assert "twenty-one (21)" in body
    f = facts.extract([p for s in secs for p in s.parts])
    kinds = {o["text"][:30]: o["kind"] for o in f["obligations"]}
    assert kinds["The Association will not strike"[:30]] == "prohibition"
    assert any(a["cite"] == "Appendix A, §1.01" for a in f["amounts"])
    assert any(d["value"] == "June 30, 2032" for d in f["dates"])
