"""Draft-7 regressions (synthetic text only): body lines at page edges, page-number runs,
quoted annex ids, chunk overlap, wage-row titles, JSON depth, Markdown escaping."""
import json
import re
import subprocess
import sys
from pathlib import Path

from crlib import facts
from crlib.report import md_escape
from crlib.sections import MAX_LINE, split_sections

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "contract_review.py"


def run(*args):
    r = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def body(secs):
    return "\n".join(s.text for s in secs)


def pages(*pgs):
    return "\n\f\n".join(pgs)


# ---- blocker 1: a repeated-looking clause at the page bottom is body text ----
def test_similar_clause_lines_at_page_bottoms_are_kept():
    txt = pages(*(f"ARTICLE {n}: TOPIC\n{n}.01 Intro text.\nThe Employer shall pay ${8 + 2 * n} per hour."
                  for n in (1, 2, 3)))
    b = body(split_sections(txt))
    for amt in ("$10", "$12", "$14"):
        assert amt in b


def test_header_with_page_number_still_dropped_but_other_digits_must_match():
    txt = pages(*(f"Sample Agreement 2030 - page {n}\nARTICLE {n}: TOPIC\n{n}.01 Clause {n} text."
                  for n in (1, 2, 3)))
    assert "Sample Agreement" not in body(split_sections(txt))
    txt2 = pages(*(f"Sample Agreement {2030 + n}\nARTICLE {n}: TOPIC\n{n}.01 Clause {n} text."
                   for n in (1, 2, 3)))  # year differs, not the page number: not a header
    assert body(split_sections(txt2)).count("Sample Agreement") == 3


def test_percent_line_repeated_at_edges_is_kept():
    txt = pages(*(f"ARTICLE {n}: TOPIC\n{n}.01 Intro.\nIncrease of 2% applies." for n in (1, 2, 3)))
    assert body(split_sections(txt)).count("2%") == 3


# ---- blocker 2: numbers that don't track the page index stay ----
def test_non_page_numbers_on_last_lines_are_kept():
    txt = pages(*(f"ARTICLE {n}: RATES\n{n}.01 The monthly rate is:\n{1499 + n}" for n in (1, 2, 3)))
    b = body(split_sections(txt))
    assert all(str(1499 + n) in b for n in (1, 2, 3))


def test_two_matching_pages_are_not_enough():
    txt = pages("ARTICLE 1: A\n1.01 Rate is:\n1", "ARTICLE 2: B\n2.01 Rate is:\n2", "ARTICLE 3: C\n3.01 Text.")
    b = body(split_sections(txt))
    assert "Rate is: 1" in b and "Rate is: 2" in b


def test_page_numbers_with_small_offset_dropped():
    txt = pages(*(f"ARTICLE {n}: TOPIC\n{n}.01 Clause text {n}.\n{n + 2}" for n in (1, 2, 3, 4)))
    assert not re.search(r"^\d+$", body(split_sections(txt)), re.M)


# ---- blocker 3: quoted ids; explicit page forms anchor a bare final footer ----
def test_quoted_schedule_id_is_heading():
    secs = split_sections('ARTICLE 1: PURPOSE\n1.01 Text.\nSCHEDULE "B" - BENEFITS\n1. Dental.\n'
                          "SCHEDULE \u201cC\u201d - PENSION\n1. Plan.\n")
    tops = [(s.number, s.title) for s in secs if s.level == 1]
    assert ("Schedule B", "BENEFITS") in tops and ("Schedule C", "PENSION") in tops


def test_bare_final_page_footer_dropped_when_other_pages_use_dash_form():
    txt = pages("ARTICLE 1: A\n1.01 One.\n- 1 -", "ARTICLE 2: B\n2.01 Two.\n- 2 -",
                "ARTICLE 3: C\n3.01 Three.\n- 3 -", "ARTICLE 4: D\n4.01 Four.\n4")
    assert not re.search(r"^4$", body(split_sections(txt)), re.M)


# ---- suggestion 1: a fact crossing the 2,000-char cut is found once ----
def test_fact_across_chunk_cut_found_once():
    filler = "Filler words go here " * 94          # ~1974 chars, no sentence end
    text = filler + "and the fee is $1,234.56 payable within thirty (30) days. The Employer shall pay it."
    assert len(filler) < facts.MAX_CHUNK < len(text)
    f = facts.extract([("1", text)])
    assert [a["value"] for a in f["amounts"]] == ["$1,234.56"]
    assert len(f["deadlines"]) == 1
    assert sum("shall pay it" in o["text"] for o in f["obligations"]) == 1


def test_many_chunks_no_duplicates():
    text = " ".join(f"Clause {i} pays ${i}.00 per day." for i in range(1, 400))
    vals = [a["value"] for a in facts.extract([("1", text)])["amounts"]]
    assert vals == [f"${i}.00" for i in range(1, 400)]


# ---- suggestion 2: wage rows keep their amounts; annex title from next line ----
def test_wage_rows_not_titles_and_appendix_title_from_next_line():
    secs = split_sections("APPENDIX A\nWAGE GRID\n1.01 Grade 1 $1,500.00\n1.02 Grade 2 $1,650.00\n")
    a = next(s for s in secs if s.number == "Appendix A")
    assert a.title == "WAGE GRID"
    amounts = [x["value"] for x in facts.extract([p for s in secs for p in s.parts])["amounts"]]
    assert amounts == ["$1,500.00", "$1,650.00"]
    assert all("$" not in s.title for s in secs)


# ---- suggestion 3: deep JSON ----
def test_deeply_nested_summaries_exit_2(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("ARTICLE 1: PURPOSE\n1.01 Text.\n")
    j = tmp_path / "s.json"
    j.write_text("[" * 100000 + "]" * 100000)
    code, _, err = run("outline", doc, "--format", "md", "--summaries", j)
    assert code == 2 and "Traceback" not in err


# ---- suggestions 4 and 5: escaping ----
def test_md_escape_ampersand_and_links():
    out = md_escape("A & B <i>x</i> see https://example.com/a_b or www.example.org, mail a@example.com ![x](y)")
    assert "\\&" in out and "\\<i\\>" in out and "\\!\\[x\\]" in out
    assert "`https://example.com/a_b`" in out and "`www.example.org`," in out and "`a@example.com`" in out


def test_evolve_summary_file_is_escaped(tmp_path, fixtures):
    s = tmp_path / "sum.txt"
    s.write_text("# Heading\nline two & <b>bold</b> https://example.com")
    code, md, _ = run("evolve", fixtures / "msa_v1.txt", fixtures / "msa_v2.txt", "--section", "Termination",
                      "--summary-file", s, "--format", "md")
    assert code == 0
    assert "\\# Heading line two \\& \\<b\\>bold\\</b\\> `https://example.com`" in md
    assert "\n# Heading" not in md


# ---- suggestion 7 ----
def test_nothing_shall_prevent_is_not_an_obligation():
    assert facts.obligation("Nothing shall prevent the Employer from granting leave.") is None
    assert facts.obligation("Nothing in this Agreement shall limit any right.") is None


# ---- heading exactly at the line cut ----
def test_heading_at_line_cut_is_found():
    long = "x" * (MAX_LINE - 1)
    secs = split_sections(f"ARTICLE 1: PURPOSE\n1.01 Text.\n{long} ARTICLE 2: WAGES\n2.01 Wage text.\n")
    assert [s.number for s in secs if s.level == 1] == ["1", "2"]
    assert any(s.title == "WAGES" for s in secs)
