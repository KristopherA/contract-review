import pytest

from crlib import boilerplate as bp
from crlib import similarity
from crlib.extract import extract_text
from crlib.outline import build
from crlib.sections import split_sections

LIB = bp.load_library()
EA = next(c["text"] for c in LIB["clauses"] if c["id"] == "entire-agreement")
NOTICES = next(c["text"] for c in LIB["clauses"] if c["id"] == "notices")


def test_fold_default_library(fixtures):
    secs = split_sections(extract_text(fixtures / "msa_v1.txt"))
    o = build(secs, LIB)
    assert {f["clause"] for f in o["boilerplate_folded"]} == {"entire-agreement", "counterparts"}
    titles = [s["title"] for s in o["sections"]]
    assert "Entire Agreement" not in titles and "Limitation of Liability" in titles


def test_default_threshold_is_strict():
    assert LIB["threshold"] == 95


def test_trivial_formatting_still_folds():
    assert bp.match(EA.upper().replace(",", "") + "  ", "Entire Agreement", LIB)[0] == "entire-agreement"
    # "its" -> "the" is no longer treated as filler (determiners can carry meaning)
    assert bp.match(EA.replace("with respect to its", "with respect to the"), "", LIB) is None


@pytest.mark.parametrize("variant", [
    EA.replace("constitutes", "does not constitute"),                       # measured 97.5
    EA.replace("and supersedes", "and does not supersede"),                 # measured 97.5
    EA.rstrip(".") + ", except Schedule 3 which survives.",                 # measured 92.7
    EA.replace("This Agreement constitutes", "Subject to Clause 9, this Agreement constitutes"),
    EA.replace("whether written or oral", "unless written"),
    "Notwithstanding Schedule 2, " + EA,
    EA + " Provided that the Order Form prevails.",
    EA.replace("prior agreements", "prior agreements other than the Pilot Agreement"),
])
def test_meaning_changes_do_not_fold(variant):
    assert bp.match(variant, "Entire Agreement", LIB) is None


def test_notices_effective_later_does_not_fold():
    variant = NOTICES.replace("are effective on receipt", "are effective 30 days after dispatch")  # measured 94.1
    assert bp.match(variant, "Notices", LIB) is None
    assert not bp.safe_to_fold(variant, NOTICES)[0]


def test_amounts_are_compared():
    assert similarity.ratio("capped at $1,000,000", "capped at $10") == 100  # numbers stripped for alignment
    lib = {"threshold": 95, "clauses": [{"id": "cap", "text": "Liability is capped at $1,000,000."}]}
    assert bp.match("Liability is capped at $1,000,000.", "", lib)[0] == "cap"
    assert bp.match("Liability is capped at $10.", "", lib) is None
    assert bp.numbers("pay $1,000.00 or 5%") == {"$1000.00", "5%"}


def test_guard_words():
    assert bp.guard_words("It shall not apply unless agreed") == {"shall not", "unless"}
    assert bp.guard_words("It applies.") == frozenset()


def test_threshold_override(tmp_path):
    lib = tmp_path / "lib.yaml"
    lib.write_text("threshold: 80\nclauses:\n  - id: waiver\n    text: No failure or delay by either party shall operate as a waiver.\n")
    library = bp.load_library(lib)
    t = "No failure or delay by either party shall operate as a waiver."
    assert bp.match(t, "Waiver", library)[0] == "waiver"
    assert bp.match(t, "Waiver", library, threshold=101) is None
    assert bp.match("Customer pays $10 per seat.", "Fees", library) is None


def test_no_fold_and_hints(fixtures):
    secs = split_sections(extract_text(fixtures / "msa_v1.txt"))
    o = build(secs, None)
    assert len(o["sections"]) == len(secs) and o["boilerplate_folded"] == []
    fees = next(s for s in o["sections"] if s["title"] == "Fees and Payment")
    assert "money_rates" in fees["topic_hints"] and "$5,000 USD" in fees["amounts"]
    assert "1.5%" in fees["amounts"] and fees["cite"] == "§4 Fees and Payment"
    assert "January 15, 2025" in o["sections"][0]["dates"]


@pytest.mark.parametrize("body", ["clauses:\n  - id: x\n", "clauses: {a: 1}\n", "- 1\n- 2\n",
                                  "threshold: high\nclauses: []\n", "clauses: [\n  - id: x\n"])
def test_library_validation(tmp_path, body):
    lib = tmp_path / "bad.yaml"; lib.write_text(body)
    with pytest.raises(ValueError):
        bp.load_library(lib)


# --- draft 3: meaning-bearing small words and word order ---------------------
@pytest.mark.parametrize("variant", [
    NOTICES.replace("by courier or by email", "by courier and by email"),   # measured 98.4
    NOTICES.replace("All notices", "Any notices"),                          # measured 98.7
    NOTICES.replace("All notices", "Each notice"),
    NOTICES.replace("shall be in writing", "may be in writing"),
    NOTICES.replace("shall be in writing", "must be in writing"),
    NOTICES.replace("by hand, by courier or by email", "by hand, by courier or email"),
])
def test_small_meaning_words_do_not_fold(variant):
    assert similarity.ratio(variant, NOTICES, keep_numbers=True) >= 95  # fuzzy score alone would fold
    assert bp.match(variant, "Notices", LIB) is None


def test_role_swap_does_not_fold():
    lib = {"threshold": 95, "clauses": [{"id": "indem", "text": "Supplier indemnifies Customer against third-party claims."}]}
    assert bp.match("Supplier indemnifies Customer against third-party claims.", "", lib)[0] == "indem"
    swapped = "Customer indemnifies Supplier against third-party claims."
    assert bp.match(swapped, "", lib, threshold=0) is None
    ok, why = bp.safe_to_fold(swapped, lib["clauses"][0]["text"])
    assert not ok and "order" in why


@pytest.mark.parametrize("variant", [
    NOTICES.upper(),
    NOTICES.replace(",", "").replace(".", ";"),
    "  " + NOTICES.replace(" ", "\n  ") + "\n",
    NOTICES.replace("All notices", "All notices hereby"),
])
def test_case_punctuation_whitespace_still_fold(variant):
    assert bp.match(variant, "Notices", LIB)[0] == "notices"


def test_filler_list_has_no_meaning_words():
    assert bp.FILLER == {"hereby"}
    for w in ("the", "a", "an", "and", "or", "nor", "any", "all", "each", "every", "either", "neither", "both",
              "may", "must", "will", "shall", "not", "of", "to", "by", "this", "that", "its", "their"):
        assert w not in bp.FILLER


@pytest.mark.parametrize("variant", [
    NOTICES.replace("All notices", "All the notices"),
    EA.replace("This Agreement", "The Agreement") if "This Agreement" in EA else EA.replace("the ", "a ", 1),
])
def test_article_changes_do_not_fold(variant):
    assert bp.match(variant, "", LIB) is None
