"""Draft 14: evolve finds a clause by id, number or partial title in each version;
digit-masked book pairs; label numbering without a section number; keyword+number
references; definitions continued by 'and shall not include'."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from crlib import boilerplate as bp
from crlib import facts
from crlib.evolution import AmbiguousQuery, evolve, match_section
from crlib.sections import split_sections

ROOT = Path(__file__).resolve().parents[1]
V1 = """ARTICLE 1: PURPOSE
1.01 The purpose of this Agreement is to set terms.
ARTICLE 12: OVERTIME AND CALL-BACK
12.01 RATE
The Employer shall pay overtime at 1.5 times the basic rate.
12.02 An employee called back shall be paid a minimum of three (3) hours.
ARTICLE 13: HOLIDAYS
13.01 The Employer shall recognise ten (10) holidays.
APPENDIX A: SHIFT PREMIUMS
1.01 Night shift is paid $2.00 per hour.
1.02 WEEKEND
A weekend premium of $1.50 per hour is paid.
"""
# v2: a new Article 2 renumbers everything after it; overtime becomes Article 13
V2 = """ARTICLE 1: PURPOSE
1.01 The purpose of this Agreement is to set terms.
ARTICLE 2: DEFINITIONS
2.01 Words have their plain meaning.
ARTICLE 13: OVERTIME AND CALL-BACK
13.01 RATE
The Employer shall pay overtime at 2 times the basic rate.
13.02 An employee called back shall be paid a minimum of four (4) hours.
ARTICLE 14: HOLIDAYS
14.01 The Employer shall recognise eleven (11) holidays.
APPENDIX A: SHIFT PREMIUMS
1.01 Night shift is paid $2.50 per hour.
1.02 WEEKEND
A weekend premium of $1.75 per hour is paid.
"""


def vs():
    return [("v1", split_sections(V1)), ("v2", split_sections(V2))]


def secs1():
    return split_sections(V1)


@pytest.mark.parametrize("q,number", [
    ("12", "12"), ("§12", "12"), ("Article 12", "12"), ("article 12", "12"), ("Art. 12", "12"),
    ("12.01", "12.01"), ("§12.01", "12.01"), ("Appendix A", "Appendix A"),
    ("Appendix A 1.02", "Appendix A 1.02"), ("appendix a, 1.02", "Appendix A 1.02"),
])
def test_match_by_number(q, number):
    m = match_section(secs1(), q)
    assert m["how"] == "number" and m["section"].number == number


def test_match_by_cite_inside_a_section():
    m = match_section(secs1(), "12.02")
    assert m["section"].number == "12" and m["part"] == "12.02"


def test_match_by_id_first():
    s = secs1()
    m = match_section(s, s[2].id)
    assert m["how"] == "id" and m["section"] is s[2]


@pytest.mark.parametrize("q", ["overtime", "OVERTIME", "Overtime and call", "call-back", "call back"])
def test_match_by_partial_title(q):
    m = match_section(secs1(), q)
    assert m["how"] == "title-substring" and m["section"].title == "OVERTIME AND CALL-BACK"


def test_exact_title_beats_substring_and_fuzzy_is_last():
    assert match_section(secs1(), "holidays")["how"] == "title"
    m = match_section(secs1(), "Overtme and Call-back")
    assert m["how"] == "title-fuzzy" and m["section"].number == "12"
    assert match_section(secs1(), "Pension") is None


def test_tighter_substring_wins_and_others_are_listed():
    s = split_sections("ARTICLE 1: OVERTIME\n1.01 A.\nARTICLE 2: OVERTIME BANKS\n2.01 B.\n")
    m = match_section(s, "overtim")
    assert m["section"].number == "1" and m["others"] == ["§2 OVERTIME BANKS"]


def test_exact_tie_is_ambiguous():
    s = split_sections("ARTICLE 1: OVERTIME RATES\n1.01 A.\nARTICLE 2: OVERTIME BANKS\n2.01 B.\n")
    with pytest.raises(AmbiguousQuery) as e:
        match_section(s, "overtime")
    assert "§1 OVERTIME RATES" in str(e.value) and "§2 OVERTIME BANKS" in str(e.value)


def test_renumbered_clause_found_by_title_in_each_version():
    t = evolve(vs(), "overtime")["timeline"]
    assert [e["section"]["number"] for e in t] == ["12", "13"]
    assert [e["matched_by"] for e in t] == ["title-substring"] * 2
    assert t[1]["status"] == "changed" and t[1]["renumbered_from"] == "12"


def test_number_query_is_matched_per_version():
    t = evolve(vs(), "13.01")["timeline"]  # v1 13.01 is holidays (a cite), v2 13.01 RATE
    assert t[0]["section"]["title"] == "HOLIDAYS" and t[0]["matched_part"] == "13.01"
    assert t[1]["section"]["title"] == "RATE"
    t = evolve(vs(), "Appendix A 1.02")["timeline"]
    assert [e["status"] for e in t] == ["baseline", "changed"]


def test_unmatched_version_falls_back_to_alignment():
    t = evolve(vs(), "12.01")["timeline"]  # v2 has no 12.01: follow v1's section
    assert t[1]["matched_by"] == "aligned" and t[1]["section"]["number"] == "13.01"


def run(*args):
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "contract_review.py"), *map(str, args)],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout, p.stderr


def test_cli_lists_other_candidates_and_exits_2_on_a_tie(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("ARTICLE 1: OVERTIME\n1.01 A x.\nARTICLE 2: OVERTIME BANKS\n2.01 B x.\n")
    b.write_text("ARTICLE 1: OVERTIME\n1.01 A y.\nARTICLE 2: OVERTIME BANKS\n2.01 B y.\n")
    rc, out, err = run("evolve", a, b, "--section", "overtim")
    assert rc == 0 and json.loads(out)["timeline"][0]["section"]["number"] == "1"
    assert "also close: §2 OVERTIME BANKS" in err
    a.write_text("ARTICLE 1: OVERTIME RATES\n1.01 A x.\nARTICLE 2: OVERTIME BANKS\n2.01 B x.\n")
    rc, out, err = run("evolve", a, b, "--section", "overtime")
    assert rc == 2 and out == "" and "§1 OVERTIME RATES" in err and "§2 OVERTIME BANKS" in err


# ---- book pairs ----
def _book(n, odd, even):
    from layout_cases import art, doc
    return doc(*(art(k, bottom=[odd if k % 2 else even.format(k=k)]) for k in range(1, n + 1)))


def test_masked_pair_drops_both(capsys):
    from layout_cases import PENSION
    text = "\n".join(s.text for s in split_sections(_book(10, PENSION + ".", "Page {k}")))
    assert "Pension" not in text and "Page " not in text
    assert "warning:" in capsys.readouterr().err  # the Pension line has a modal verb


def test_plain_pair_drops_without_warning(capsys):
    text = "\n".join(s.text for s in split_sections(_book(10, "Union Copy", "Page {k}")))
    assert "Union Copy" not in text
    assert "warning" not in capsys.readouterr().err


def test_pair_needs_four_pages_per_parity():
    from layout_cases import PENSION
    text = "\n".join(s.text for s in split_sections(_book(7, PENSION + ".", "Page {k}")))  # 4 odd, 3 even
    assert "Pension" in text


# ---- labels in a section with no numeric number ----
LIB = bp.load_library()
CBA = [c for c in LIB["clauses"] if c["id"].startswith("cba-")]


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
@pytest.mark.parametrize("number", ["", "Appendix A", "LOU 3"])
def test_foreign_first_label_does_not_fold(c, number):
    assert bp.match("30.5 " + c["text"], "", LIB, number=number) is None
    assert bp.match("30.5 Employees shall receive the benefit.\n\n30.6 " + c["text"], "", LIB, number=number) is None


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
@pytest.mark.parametrize("first", ["1.01", "1.1", "4.01"])
def test_first_label_ending_01_or_1_folds(c, first):
    assert bp.match(first + " " + c["text"], "", LIB, number="Appendix A")[0] == c["id"]


def test_strip_labels_without_number():
    assert bp.strip_labels("30.5 The A.\n\n30.6 The B.") == "30.5 The A.\n\n30.6 The B."
    assert bp.strip_labels("1.1 The A.\n\n1.2 The B.") == "The A.\n\nThe B."
    assert bp.strip_labels("1.01 The A.\n\n1.03 The B.\n\n1.02 The C.") == "The A.\n\nThe B.\n\n1.02 The C."


# ---- references and definitions ----
def durs(s):
    return [d["value"] for d in facts.extract([("1", s)])["durations"]]


@pytest.mark.parametrize("text", [
    "Leave per Clause 12 (10) days applies.", "As set out in Article 7, (10) days apply.",
    "See Section 4.2 (3) weeks.", "Under Appendix A (2) days.", "Per Clause 12(b) (10) days.",
])
def test_keyword_and_number_are_references(text):
    assert durs(text) == []


def test_bracketed_durations_after_ordinary_words_still_count():
    assert durs("Leave is (10) days.") == ["10 days"]
    assert durs("Leave of ten (10) days in Article 7.") == ["ten (10) days"]


@pytest.mark.parametrize("text", [
    "A day means a calendar day and shall not include holidays.",
    "Shift means a work period and shall include breaks.",
    "Wages means basic pay and does not include overtime.",
])
def test_definition_scope_is_not_a_duty(text):
    f = facts.extract([("1", text)])
    assert len(f["definitions"]) == 1 and f["obligations"] == []


def test_definition_followed_by_a_duty_still_obliges():
    f = facts.extract([("1", "Overtime means work beyond eight hours and shall be paid at 1.5 times the rate.")])
    assert [(o["who"], o["kind"]) for o in f["obligations"]] == [("Overtime", "obligation")]
