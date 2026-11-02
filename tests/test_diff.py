from crlib.diffing import align, diff_documents, render_word_diff, word_diff
from crlib.extract import extract_text
from crlib.report import diff_markdown
from crlib.sections import split_sections


def _load(fixtures, n):
    return split_sections(extract_text(fixtures / f"msa_v{n}.txt"))


def _by_title(changes, title):
    return next(c for c in changes if (c["new"] or c["old"])["title"] == title)


def test_renumbered_and_moved_alignment(fixtures):
    old, new = _load(fixtures, 1), _load(fixtures, 2)
    pairs, _ = align(old, new)
    matched = {a.title: b.number for a, b, _ in pairs if a and b}
    assert matched["Term and Renewal"] == "4"   # moved from 2 to 4
    assert matched["Fees and Payment"] == "3"   # renumbered 4 -> 3
    assert matched["Services"] == "2"
    ch = diff_documents(old, new)
    term = _by_title(ch, "Term and Renewal")
    assert {"modified", "renumbered", "moved"} <= set(term["kinds"])
    services = _by_title(ch, "Services")
    assert services["kinds"] == ["renumbered"] and services["word_diff"] == []


def test_added_removed_unchanged(fixtures):
    ch = diff_documents(_load(fixtures, 1), _load(fixtures, 2))
    assert _by_title(ch, "Data Protection")["kinds"] == ["added"]
    assert _by_title(ch, "Counterparts")["kinds"] == ["removed"]
    assert not any((c["new"] or {}).get("title") == "Confidentiality" for c in ch)
    assert [c["id"] for c in ch] == [f"c{i}" for i in range(1, len(ch) + 1)]


def test_match_on_content_when_title_changes():
    old = split_sections("1. Fees\nCustomer shall pay the monthly fee within thirty days of invoice.\n")
    new = split_sections("4. Charges\nCustomer shall pay the monthly fee within thirty days of invoice.\n")
    ch = diff_documents(old, new)
    assert len(ch) == 1 and set(ch[0]["kinds"]) == {"retitled", "renumbered"}


def test_word_diff_ops():
    ops = word_diff("pay within thirty (30) days", "pay within forty-five (45) days")
    assert ops == [{"op": "equal", "text": "pay within"},
                   {"op": "delete", "text": "thirty (30)"},
                   {"op": "insert", "text": "forty-five (45)"},
                   {"op": "equal", "text": "days"}]
    assert render_word_diff(ops) == "pay within ~~thirty (30)~~ **forty-five (45)** days"


def test_markdown_merges_summaries(fixtures):
    ch = diff_documents(_load(fixtures, 1), _load(fixtures, 2))
    fid = _by_title(ch, "Fees and Payment")["id"]
    md = diff_markdown(ch, "v1", "v2", {fid: "Fee up 10%; payment window 30 -> 45 days."})
    assert "Fee up 10%" in md and "Not legal advice" in md
    assert "~~$5,000~~ **$5,500**" in md


# --- draft 2: retitle fallback, split/merge, difflib fallback ----------------
import pytest

from crlib import diffing, similarity
from crlib.sections import Section


def _s(n, title, text):
    return Section(id=f"s{n}", number=str(n), title=title, level=1, text=text, order=n - 1)


BODY = ("Each party shall keep the other party's confidential information secret, use it only "
        "for this Agreement, and return or destroy it within thirty days after termination.")


def test_retitled_section_matches_on_content():
    old = [_s(1, "Confidentiality", BODY)]
    new_body = ("Each recipient shall protect all non-public material it receives with reasonable care, "
                "use it only for this Agreement, and return or erase it within thirty days after expiry.")
    new = [_s(1, "Duty of Care", new_body)]
    c = diffing.content_score(old[0], new[0])
    assert 65 <= c <= 75  # ~70% content similarity
    assert diffing.pair_score(old[0], new[0]) < diffing.DEFAULT_MATCH  # blend alone would miss it
    changes = diffing.diff_documents(old, new)
    assert len(changes) == 1 and changes[0]["old"] and changes[0]["new"]
    assert "added" not in changes[0]["kinds"] and "removed" not in changes[0]["kinds"]


def test_unrelated_retitled_section_not_matched():
    old = [_s(1, "Confidentiality", BODY)]
    new = [_s(1, "Governing Law", "This Agreement is governed by the laws of the State of Exampleland.")]
    kinds = sorted(k for c in diffing.diff_documents(old, new) for k in c["kinds"])
    assert kinds == ["added", "removed"]


A = ("Customer shall pay all fees within thirty days of each invoice and late amounts accrue "
     "interest at the stated monthly rate until paid in full.")
B = ("Supplier may suspend the services on ten days written notice if any undisputed amount "
     "remains unpaid after the due date and must restore them promptly once paid.")


def test_split_detected():
    old = [_s(1, "Payment", A + " " + B), _s(2, "Term", "This Agreement lasts one year.")]
    new = [_s(1, "Payment", A), _s(2, "Suspension", B), _s(3, "Term", "This Agreement lasts one year.")]
    changes = diffing.diff_documents(old, new)
    split = [c for c in changes if "split" in c["kinds"]]
    assert len(split) == 1 and [x["title"] for x in split[0]["split_into"]] == ["Suspension"]
    assert not any("added" in c["kinds"] for c in changes)


def test_merge_detected():
    old = [_s(1, "Payment", A), _s(2, "Suspension", B), _s(3, "Term", "This Agreement lasts one year.")]
    new = [_s(1, "Payment", A + " " + B), _s(2, "Term", "This Agreement lasts one year.")]
    changes = diffing.diff_documents(old, new)
    merged = [c for c in changes if "merged" in c["kinds"]]
    assert len(merged) == 1 and [x["title"] for x in merged[0]["merged_from"]] == ["Suspension"]
    assert not any("removed" in c["kinds"] for c in changes)


def test_genuinely_new_section_is_not_absorbed():
    old = [_s(1, "Payment", A)]
    new = [_s(1, "Payment", A), _s(2, "Insurance", "Supplier maintains liability insurance of five million.")]
    kinds = sorted(k for c in diffing.diff_documents(old, new) for k in c["kinds"])
    assert kinds == ["added"]


@pytest.mark.parametrize("a,b", [
    ("the quick brown fox", "the quick brown fox"),
    ("the quick brown fox", "the quick brown cat"),
    ("payment within thirty days", "payment within sixty days of invoice"),
    ("alpha", "omega"),
    ("", ""),
])
def test_difflib_fallback_close_to_rapidfuzz(monkeypatch, a, b):
    fast = similarity.ratio(a, b)
    monkeypatch.setattr(similarity, "_fuzz", None)
    slow = similarity.ratio(a, b)
    assert abs(fast - slow) <= 1.0


def test_difflib_fallback_alignment_near_threshold(monkeypatch, fixtures):
    from crlib.extract import extract_text
    from crlib.sections import split_sections
    v1 = split_sections(extract_text(fixtures / "msa_v1.txt"))
    v2 = split_sections(extract_text(fixtures / "msa_v2.txt"))
    fast = [sorted(c["kinds"]) for c in diffing.diff_documents(v1, v2)]
    monkeypatch.setattr(similarity, "_fuzz", None)
    slow = [sorted(c["kinds"]) for c in diffing.diff_documents(v1, v2)]
    assert fast == slow
    from crlib import boilerplate as bp
    lib = bp.load_library()
    ea = next(c["text"] for c in lib["clauses"] if c["id"] == "entire-agreement")
    assert bp.match(ea, "", lib)[0] == "entire-agreement"
    assert bp.match(ea.replace("constitutes", "does not constitute"), "", lib) is None


# --- draft 3: low-confidence pairings -----------------------------------------
GOV = ("This Agreement is governed by the laws of Exampleland, and the courts of Example City "
       "have exclusive jurisdiction over any dispute.")
JUR = ("The courts of Example City have exclusive jurisdiction over any dispute arising under this "
       "Agreement, and each party submits to them.")
CAP = ("Each party's total liability under this Agreement for any claim is capped at the fees paid in "
       "the prior twelve months.")
IND = ("Each party shall indemnify the other for any third-party claim under this Agreement, and that "
       "liability is not capped.")


@pytest.mark.parametrize("old,new", [(("Governing Law", GOV), ("Jurisdiction", JUR)),
                                     (("Liability Cap", CAP), ("Indemnity", IND))])
def test_low_confidence_flag_and_report(old, new):
    from crlib.report import diff_markdown
    a, b = _s(1, *old), _s(1, *new)
    score = diffing.pair_score(a, b)
    assert diffing.DEFAULT_MATCH <= score < diffing.LOW_CONFIDENCE  # weak but accepted pairing
    changes = diffing.diff_documents([a], [b])
    assert len(changes) == 1 and changes[0]["low_confidence"] is True
    md = diff_markdown(changes, "a", "b")
    assert "low-confidence match" in md and "Low-confidence pairing" in md


def test_strong_pair_not_low_confidence():
    from crlib.report import diff_markdown
    changes = diffing.diff_documents([_s(1, "Payment", A)], [_s(1, "Payment", A + " Extra words.")])
    assert changes[0]["low_confidence"] is False
    assert "low-confidence" not in diff_markdown(changes, "a", "b").lower()
