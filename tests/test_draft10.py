"""Draft-10 regressions (synthetic text only): obligation subjects and abbreviations.
Layout cases live in the table-driven corpus (test_layout_corpus.py)."""
import pytest

from crlib import facts


@pytest.mark.parametrize("sentence,who,kind", [
    ("The Union, i.e. Local 1, may not strike.", "The Union", "prohibition"),
    ("The Employer, e.g. through its agent, shall post notices.", "The Employer", "obligation"),
    ("Pursuant to s. 12 of the Act the Employer shall post notices.", "the Employer", "obligation"),
    ("Subject to Article 30 the Union shall ratify the terms.", "the Union", "obligation"),
    ("Under Section 4.2 of this Agreement each employee shall sign.", "each employee", "obligation"),
    ("See Art. 5. The Union shall notify the Employer.", "The Union", "obligation"),
    ("No employee shall be disciplined without cause.", "No employee", "prohibition"),
])
def test_who_label(sentence, who, kind):
    o = facts.obligation(sentence)
    assert (o["who"], o["kind"]) == (who, kind)
    f = facts.extract([("1", sentence)])
    assert f["obligations"] and f["obligations"][0]["cite"] == "§1"


@pytest.mark.parametrize("s", [
    "Mr. Smith shall chair the committee.", "Ms. Jones may attend.", "Dr. Brown shall assess fitness.",
    "Leave under Sec. Four shall be paid.", "Leave under sec. Four shall be paid.",
])
def test_no_split_after_titles(s):
    assert facts.sentences(s + " Then it ends.") == [s, "Then it ends."]
