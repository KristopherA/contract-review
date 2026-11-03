"""Draft 13: label stripping follows the section's own numbering, more reference words
before a figure, subjectless clause after a definition, restated-article cites, A-1 ids."""
import re

import pytest

from crlib import boilerplate as bp
from crlib import facts
from crlib.sections import split_sections

LIB = bp.load_library()
CBA = [c for c in LIB["clauses"] if c["id"].startswith("cba-")]


def _labelled(text, major="12"):
    sents = re.split(r"(?<=\.)\s+", text.strip())
    return "\n\n".join(f"{major}.{k + 1:02d} {s}" for k, s in enumerate(sents))


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
def test_own_numbering_folds(c):
    assert bp.match(_labelled(c["text"]), "", LIB, number="12")[0] == c["id"]


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
@pytest.mark.parametrize("number", ["12", ""])
def test_new_foreign_paragraph_blocks_fold(c, number):
    text = _labelled(c["text"]) + "\n\n30.5 Employees shall receive the benefit."
    assert bp.match(text, "", LIB, number=number) is None


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
def test_label_going_backwards_blocks_fold(c):
    text = "12.02 " + c["text"] + "\n\n12.01 Employees shall receive the benefit."
    assert bp.match(text, "", LIB, number="12") is None


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
def test_other_articles_numbering_is_kept(c):
    assert bp.match("7.01 " + c["text"], "", LIB, number="12") is None


def test_strip_labels_rules():
    assert bp.strip_labels("12.01 The A.\n\n12.02 The B.", "12") == "The A.\n\nThe B."
    assert bp.strip_labels("12.01 The A.\n\n30.5 Employees", "12") == "The A.\n\n30.5 Employees"
    assert bp.strip_labels("12.02 The A.\n\n12.01 The B.", "12") == "The A.\n\n12.01 The B."
    assert bp.strip_labels("4.01 The A.\n\n4.02 The B.") == "The A.\n\nThe B."


def durs(s):
    return [d["value"] for d in facts.extract([("1", s)])["durations"]]


@pytest.mark.parametrize("text", [
    "Leave under subsection (10) days applies.", "As pursuant to 12.01 (10) days apply.",
    "Under paragraph (4) days off.", "See item (3) days.", "As in para. (6) weeks.",
    "Per 12.01(a) (10) days.",
])
def test_reference_numbers_are_not_durations(text):
    assert durs(text) == []


def test_real_bracketed_durations_still_count():
    assert durs("Leave of (10) days.") == ["10 days"]
    assert durs("Take ten (10) days.") == ["ten (10) days"]


def test_subjectless_clause_after_definition():
    f = facts.extract([("1", "Overtime means work beyond eight hours and shall be paid at 1.5 times the rate.")])
    assert f["definitions"][0]["term"] == "Overtime"
    assert [(o["who"], o["kind"]) for o in f["obligations"]] == [("Overtime", "obligation")]


def test_restated_clause_gets_distinct_cite():
    t = ("ARTICLE 1: PURPOSE\n1.01 Purpose text.\nARTICLE 2: WAGES\n2.01 The Employer shall pay $20.00 per hour.\n"
         "ARTICLE 2: HOURS OF WORK\n2.01 The normal day is eight hours.\nARTICLE 3: TERM\n3.01 Term text.\n")
    s2 = next(s for s in split_sections(t) if s.number == "2")
    assert [n for n, _ in s2.parts] == ["2.01", "2.01 (restated)"]
    f = facts.extract([p for p in s2.parts])
    assert [a["cite"] for a in f["amounts"]] == ["§2.01"]
    assert "§2.01 (restated)" in {d["cite"] for d in f["durations"]}


def test_restated_titled_clause_gets_distinct_cite():
    t = ("ARTICLE 1: PURPOSE\n1.01 Purpose text.\nARTICLE 2: WAGES\n2.01 RATES\nThe Employer shall pay $20.00 per hour.\n"
         "ARTICLE 2: HOURS OF WORK\n2.01 The normal day is eight hours.\nARTICLE 3: TERM\n3.01 Term text.\n")
    cites = [p[0] for s in split_sections(t) for p in s.parts]
    assert len(cites) == len(set(cites)) and "2.01 (restated)" in cites


def test_appendix_with_dash_id():
    t = "ARTICLE 1: PURPOSE\n1.01 Purpose text.\nAPPENDIX A-1: SHIFT\nShift text here.\n"
    assert [(s.number, s.title) for s in split_sections(t) if s.level == 1] == \
        [("1", "PURPOSE"), ("Appendix A-1", "SHIFT")]
