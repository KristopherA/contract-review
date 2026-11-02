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
