"""Draft-11 regressions (synthetic text only): quantities next to clause references,
definitions, subject length, quiet pypdf, and boilerplate folding of numbered clauses.
Layout cases live in the table-driven corpus (test_layout_corpus.py)."""
import logging

import pytest

from crlib import boilerplate as bp
from crlib import facts
from crlib.extract import _quiet_pypdf


def ex(s):
    return facts.extract([("1", s)])


@pytest.mark.parametrize("s,durations", [
    ("Employees shall work five (7.5) hours per shift.", ["five hours"]),   # bracket is a reference
    ("Leave lasts seven (1.07) days.", ["seven days"]),
    ("Notice is due within ten (10) days.", ["ten (10) days"]),             # agreeing pair kept
    ("A shift is seven and one-half (7.5) hours.", ["seven and one-half (7.5) hours"]),
    ("A shift is 7.5 hours long.", ["7.5 hours"]),
    ("See clause 1.07 days later.", []),                                   # clause number, not a quantity
    ("Breaks under Article 7 days are paid.", []),
    ("Leave under (3.02) days is paid.", []),
])
def test_quantities_and_clause_references(s, durations):
    assert [d["value"] for d in ex(s)["durations"]] == durations


def test_deadline_pairs_checked():
    assert [d["text"] for d in ex("Reply within five (3.02) days.")["deadlines"]] == ["within five days"]
    assert [d["text"] for d in ex("Reply within five (5) days.")["deadlines"]] == ["within five (5) days"]


@pytest.mark.parametrize("s,term", [
    ('"Employee" shall mean a person in the bargaining unit.', "Employee"),
    ("Overtime means hours worked beyond the scheduled shift.", "Overtime"),
    ("Spouse includes a common-law partner.", "Spouse"),
    ("Day refers to a calendar day.", "Day"),
    ("(a) Shift Premium shall mean the hourly amount paid for evening work.", "Shift Premium"),
])
def test_definitions_are_not_obligations(s, term):
    f = ex(s)
    assert [d["term"] for d in f["definitions"]] == [term]
    assert f["definitions"][0]["cite"] == "§1"
    assert f["obligations"] == []


def test_obligation_not_a_definition():
    f = ex("The Employer shall pay the premium that the schedule means to cover.")
    assert f["definitions"] == [] and f["obligations"][0]["who"] == "The Employer"


def test_who_label_capped_at_eight_words():
    o = facts.obligation("Every single regular full time and part time casual employee in the unit shall sign.")
    assert len(o["who"].split()) <= facts.MAX_WHO_WORDS


def test_pypdf_logging_silenced_and_restored(caplog):
    log = logging.getLogger("pypdf")
    before = log.level
    with caplog.at_level(logging.WARNING):
        with _quiet_pypdf():
            log.warning("Ignoring wrong pointing object 1 0 (offset 0)")
        assert not caplog.records
    assert log.level == before


def test_numbered_clause_folds_but_changed_number_does_not():
    lib = bp.load_library()
    ids = {c["id"] for c in lib["clauses"]}
    assert {"cba-management-rights", "cba-no-discrimination", "cba-severability", "cba-entire-agreement",
            "cba-notices", "cba-term", "cba-no-strike"} <= ids
    text = "15.01 There shall be no strike or lockout during the term of this Agreement."
    assert bp.match(text, "No Strike", lib)[0] == "cba-no-strike"
    assert bp.match("15.01 There shall be no strike or lockout during the first 2 years of this Agreement.",
                    "No Strike", lib) is None
    assert bp.match("15.01 There shall be a strike or lockout during the term of this Agreement.",
                    "No Strike", lib) is None


@pytest.mark.parametrize("text,want", [
    ("Shifts of seven point five (7.5) hours.", "seven point five (7.5) hours"),
    ("Leave of one point zero seven (1.07) days.", "one point zero seven (1.07) days"),
    ("A cap of four hundred and fifty six (456) hours.", "four hundred and fifty six (456) hours"),
    ("For the first twenty four (24) months.", "twenty four (24) months"),
    ("A shift of eight point two five (8.25) hours.", "eight point two five (8.25) hours"),
])
def test_spelled_out_numbers_pair_with_agreeing_figures(text, want):
    assert [d["value"] for d in facts.extract([("1", text)])["durations"]] == [want]
