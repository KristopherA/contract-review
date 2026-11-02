from crlib import boilerplate as bp
from crlib.extract import extract_text
from crlib.outline import build
from crlib.sections import split_sections


def test_fold_default_library(fixtures):
    secs = split_sections(extract_text(fixtures / "msa_v1.txt"))
    o = build(secs, bp.load_library())
    assert {f["clause"] for f in o["boilerplate_folded"]} == {"entire-agreement", "counterparts"}
    titles = [s["title"] for s in o["sections"]]
    assert "Entire Agreement" not in titles and "Limitation of Liability" in titles


def test_fuzzy_match_and_threshold(tmp_path):
    lib = tmp_path / "lib.yaml"
    lib.write_text("threshold: 80\nclauses:\n  - id: waiver\n    text: No failure or delay by either party in exercising any right shall operate as a waiver.\n")
    library = bp.load_library(lib)
    near = "No failure or delay by a party in exercising any right shall operate as a waiver of it."
    assert bp.match(near, "Waiver", library)[0] == "waiver"
    assert bp.match(near, "Waiver", library, threshold=99) is None
    assert bp.match("Customer pays $10 per seat.", "Fees", library) is None


def test_no_fold_and_hints(fixtures):
    secs = split_sections(extract_text(fixtures / "msa_v1.txt"))
    o = build(secs, None)
    assert len(o["sections"]) == len(secs) and o["boilerplate_folded"] == []
    fees = next(s for s in o["sections"] if s["title"] == "Fees and Payment")
    assert "money_rates" in fees["topic_hints"] and "$5,000 USD" in fees["amounts"]
    assert "1.5%" in fees["amounts"] and fees["cite"] == "§4 Fees and Payment"
    pre = o["sections"][0]
    assert "January 15, 2025" in pre["dates"]


def test_library_validation(tmp_path):
    lib = tmp_path / "bad.yaml"; lib.write_text("clauses:\n  - id: x\n")
    import pytest
    with pytest.raises(ValueError):
        bp.load_library(lib)
