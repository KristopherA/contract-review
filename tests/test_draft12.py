"""Draft 12: label stripping only at section/paragraph start, odd/even rule limits,
definition plus obligation, half a day, bare "(n) days", continued LOU, restated
article, and the no-TOC gap warning."""
import re

import pytest

from crlib import boilerplate as bp
from crlib import facts
from crlib.sections import split_sections

LIB = bp.load_library()
CBA = [c for c in LIB["clauses"] if c["id"].startswith("cba-")]


def test_eight_cba_clauses():
    assert len(CBA) == 8


def _labelled(text):
    sents = re.split(r"(?<=\.)\s+", text.strip())
    return "\n\n".join(f"7.{k + 1:02d} {s}" for k, s in enumerate(sents))


def _inject(text, line):
    words = text.split()
    mid = len(words) // 2
    return " ".join(words[:mid]) + "\n" + line + " " + " ".join(words[mid:])


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
def test_labelled_clause_folds(c):
    assert bp.match(_labelled(c["text"]), "", LIB)[0] == c["id"]


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
@pytest.mark.parametrize("line", ["30.5 The", "30.5"])
def test_mid_paragraph_number_line_blocks_fold(c, line):
    assert bp.match("7.01 " + _inject(c["text"], line), "", LIB) is None


def test_label_before_lowercase_is_kept():
    assert bp.CLAUSE_LABEL.sub(r"\1", "12.01 hours of work") == "12.01 hours of work"
    assert bp.CLAUSE_LABEL.sub(r"\1", "12.01 The Union") == "The Union"
    assert bp.CLAUSE_LABEL.sub(r"\1", "Text.\n12.02 The Union") == "Text.\n12.02 The Union"
    assert bp.CLAUSE_LABEL.sub(r"\1", "Text.\n\n12.02 The Union") == "Text.\n\nThe Union"


def ex(s):
    return facts.extract([("1", s)])


def test_definition_and_obligation_in_one_sentence():
    f = ex("A day means a calendar day and the Employer shall pay overtime.")
    assert f["definitions"][0]["term"] == "A day"
    assert [o["who"] for o in f["obligations"]] == ["the Employer"]


def test_pure_definition_has_no_obligation():
    f = ex("Overtime means hours an employee shall work beyond eight in a day.")
    assert f["definitions"] and not f["obligations"]


def test_half_a_day():
    assert [d["value"] for d in ex("An employee may take half a day off.")["durations"]] == ["half a day"]
    assert facts._word_value("half a") == 0.5


@pytest.mark.parametrize("text,want", [
    ("Leave of (10) days is granted.", ["10 days"]),
    ("Take (2.5) hours.", ["2.5 hours"]),
    ("See Article (3) days.", []),
    ("five (5) days", ["five (5) days"]),
])
def test_bare_bracketed_figure(text, want):
    assert [d["value"] for d in ex(text)["durations"]] == want


def tree(t):
    return [(s.number, s.title) for s in split_sections(t) if s.level == 1]


def test_lou_continued_joins_open_letter():
    t = ("ARTICLE 1: PURPOSE\n1.01 Purpose text.\nLETTER OF UNDERSTANDING #1\nRe: Meals\n"
         "The Employer shall pay $5.00 per meal.\nLETTER OF UNDERSTANDING #2\nRe: Mileage\n"
         "The Employer shall pay $6.00 per km.\nLETTER OF UNDERSTANDING - continued\n"
         "The Employer shall pay $7.00 per trip.\n")
    secs = split_sections(t)
    assert [n for n, _ in tree(t)] == ["1", "Letter of Understanding 1", "Letter of Understanding 2"]
    assert "$7.00" in secs[-1].text


def test_restated_article_keeps_both_titles_and_clauses():
    t = ("ARTICLE 1: PURPOSE\n1.01 Purpose text here.\nARTICLE 2: WAGES\n2.01 RATES\n"
         "The Employer shall pay $20.00 per hour.\nARTICLE 2: HOURS OF WORK\n2.02 The normal day is eight hours.\n"
         "ARTICLE 3: TERM\n3.01 Term text.\n")
    secs = split_sections(t)
    assert ("2", "WAGES / HOURS OF WORK") in tree(t)
    assert any(s.number == "2.01" and "$20.00" in s.text for s in secs)
    assert any("2.02" in s.text for s in secs)


def test_gap_resume_warns(capsys):
    t = ("1. PURPOSE\nPurpose text here.\n2. WAGES\nWage text here.\nSCHEDULE A - RATES\n1. RATES\nRate text.\n"
         "3. DRUGS\nThe Employer shall pay $7.00 per shift.\n")
    assert ("3", "DRUGS") in tree(t)
    assert "3. DRUGS" in capsys.readouterr().err


def test_no_warning_without_gap(capsys):
    split_sections("1. PURPOSE\nPurpose text.\n2. WAGES\nWage text.\nSCHEDULE A - RATES\n1. RATES\nRate.\n2. HOURS\nHours.\n")
    assert capsys.readouterr().err == ""
