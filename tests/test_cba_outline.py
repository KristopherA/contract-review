"""Draft 5 regressions: a synthetic, generic collective-agreement fixture with a
table of contents, lettered/roman sub-items, numbered lists and numeric facts."""
import re

import pytest

from crlib import boilerplate as bp
from crlib.extract import extract_text
from crlib.outline import build
from crlib.report import outline_markdown
from crlib.sections import split_sections

def _outline(text, fixtures):
    lib = bp.load_library(fixtures.parents[1] / "assets" / "boilerplate.yaml")
    return split_sections(text), build(split_sections(text), lib)


@pytest.fixture(params=["txt", "pdf"])
def cba_text(request, fixtures, pdf_factory):
    raw = (fixtures / "cba_generic.txt").read_text()
    if request.param == "txt":
        return extract_text(fixtures / "cba_generic.txt")
    return extract_text(pdf_factory("cba.pdf", _wrapped(raw)))  # multi-page, wrapped like a real PDF


def _wrapped(raw):
    import textwrap
    return [w for line in raw.splitlines() for w in (textwrap.wrap(line, 80, break_on_hyphens=False) or [""])]


def _vals(sec, key):
    return [x.get("value") or x.get("text") for x in sec["key_facts"][key]]


def test_pdf_is_multipage(fixtures, pdf_factory):
    from pypdf import PdfReader
    p = pdf_factory("cba.pdf", _wrapped((fixtures / "cba_generic.txt").read_text()))
    assert len(PdfReader(p).pages) >= 2


def test_no_toc_or_subitem_sections(cba_text):
    secs = split_sections(cba_text)
    nums = [s.number for s in secs if s.number]
    assert nums == ["1", "2", "3", "3.01", "3.02", "4", "4.01", "4.02", "5", "5.01", "6", "6.01", "6.02", "7"]
    assert len(nums) == len(set(nums))
    for s in secs:
        assert s.title.strip(), s.number
        assert not re.search(r"\.{3,}|\s\d+$", s.title), s.title          # no TOC leader/page number
        assert not re.match(r"^\(?([a-z]{1,2}|[ivx]+)\)|^\d\.\s", s.title)  # no (a)/(i)/1. headings
    titles = {s.number: s.title for s in secs}
    assert titles["3"] == "HOURS OF WORK" and titles["6.01"] == "Step One"
    assert not any(t.upper() == "CONTENTS" or "TABLE OF CONTENTS" in t.upper() for t in titles.values())


def test_list_items_stay_in_body(cba_text):
    secs = {s.number: s for s in split_sections(cba_text)}
    assert "(a) Employees with less than five" in secs["5.01"].text
    assert "2. the days off" in secs["3"].text


def test_facts_extracted(cba_text, fixtures):
    _, o = _outline(cba_text, fixtures)
    s = {x["number"]: x for x in o["sections"]}
    assert "$15.00" in _vals(s["4.02"], "amounts")
    assert {"150%", "200%"} <= set(_vals(s["4.01"], "percentages"))
    assert {"6%", "8%"} <= set(_vals(s["5.01"], "percentages"))
    assert "within twenty-one (21) days of the incident" in _vals(s["6.01"], "deadlines")
    assert any("no later than March 1" in d for d in _vals(s["5"], "deadlines"))
    obs = s["6.02"]["key_facts"]["obligations"]
    assert any(o["who"] == "The Employer" and o["kind"] == "obligation" for o in obs)
    assert any(o["kind"] == "right" and "Union may" in o["text"] for o in obs)
    assert all(f["cite"].startswith("§") for x in o["sections"] if x["number"]
               for v in x["key_facts"].values() for f in v)
    assert s["3"]["key_facts"]["obligations"][0]["cite"] == "§3.03"


def test_boilerplate_folded_and_markdown(cba_text, fixtures):
    _, o = _outline(cba_text, fixtures)
    assert [f["clause"] for f in o["boilerplate_folded"]] == ["entire-agreement"]
    md = outline_markdown(o, "cba", {o["sections"][1]["id"]: "PLAIN"})
    assert "## §4.02 Meal Allowance" in md and "$15.00 (§4.02)" in md and "**Summary:** PLAIN" in md
    assert "hints" not in md and "§7 ENTIRE AGREEMENT ≈ standard" in md


def test_summaries_off_by_default(fixtures, capsys):
    import contract_review as cr
    rc = cr.main(["outline", str(fixtures / "cba_generic.txt"), "--format", "md"])
    assert rc in (0, None) and "**Summary:**" not in capsys.readouterr().out
