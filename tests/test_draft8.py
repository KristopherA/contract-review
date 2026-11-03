"""Draft-8 regressions (synthetic text only): sentence-level fact scanning, majority
running headers/footers, annex-scoped numbering, prohibitions, Markdown code spans."""
import time

from crlib import facts
from crlib.report import md_escape
from crlib.sections import split_sections


def body(secs):
    return "\n".join(s.text for s in secs)


def pages(*pgs):
    return "\n\f\n".join(pgs)


def ex(text):
    return facts.extract([("1", text)])


# ---- B1: sentence segmentation ----
def test_within_ten_days_is_a_deadline():
    f = ex("The Employer shall reply within ten days of the request.")
    assert f["deadlines"], f
    assert any("ten days" in d["text"] for d in f["deadlines"])
    assert f["obligations"] and f["obligations"][0]["kind"] == "obligation"


def _long_sentence(cut):
    """One >2000-char sentence whose "shall pay $9.00 within ten days" starts at `cut`."""
    head = "The Union " + "word " * ((cut - 10) // 5)
    head += "w" * (cut - len(head))
    s = head + "shall pay $9.00 within ten days of notice" + " and more" * 120 + "."
    assert s.index("shall pay") == cut
    return s


def test_long_sentence_crossing_window_edges_keeps_its_facts():
    for cut in (1700, 1850, 1950):
        s = _long_sentence(cut)
        assert len(s) > facts.MAX_CHUNK
        f = ex(s)
        assert any(o["kind"] == "obligation" for o in f["obligations"]), cut
        assert [a["value"] for a in f["amounts"]] == ["$9.00"], cut
        assert f["deadlines"], cut


def test_filler_before_short_obligation():
    text = " ".join(["filler"] * 1500) + ". The Union shall pay $9.00."
    f = ex(text)
    obs = [o for o in f["obligations"] if "$9.00" in o["text"]]
    assert obs and obs[0]["kind"] == "obligation"
    assert [a["value"] for a in f["amounts"]] == ["$9.00"]


def test_b1_timing():
    text = ("The Employer shall pay $1.00 within ten days. " * 3000) + ("x " * 50000)
    t = time.perf_counter(); f = ex(text)
    assert time.perf_counter() - t < 1.0
    assert f["obligations"] and f["deadlines"] and f["amounts"]


def test_no_employee_shall_is_prohibition():
    f = ex("No employee shall be disciplined without just cause.")
    assert f["obligations"][0]["kind"] == "prohibition"
    assert ex("Nothing in this Agreement shall limit any right.")["obligations"] == []
    assert ex("Neither party shall assign this Agreement.")["obligations"][0]["kind"] == "prohibition"


# ---- B2/B3: majority running header/footer rule ----
def test_sentence_footer_citing_article_is_kept():
    txt = pages(*(f"ARTICLE {n}: TOPIC\n{n}.01 Clause {n} text here.\nSubject to Article 12." for n in (1, 2, 3)))
    assert body(split_sections(txt)).count("Subject to Article 12") == 3


def test_majority_running_header_with_modal_is_dropped():
    hdr = "This Agreement shall be read with the Pension Plan"
    txt = pages(*(f"{hdr}\nARTICLE {n}: TOPIC\n{n}.01 Clause {n} text here." for n in (1, 2, 3, 4)))
    secs = split_sections(txt)
    assert hdr not in body(secs)
    f = facts.extract([p for s in secs for p in s.parts])
    assert not any("Pension Plan" in o["text"] for o in f["obligations"])


def test_minority_money_lines_and_percent_kept():
    txt = pages(*(f"ARTICLE {n}: TOPIC\n{n}.01 Intro text.\nThe Employer shall pay ${8 + 2 * n} per hour."
                  for n in (1, 2, 3)))
    b = body(split_sections(txt))
    assert all(a in b for a in ("$10", "$12", "$14"))
    txt2 = pages(*(f"ARTICLE {n}: TOPIC\n{n}.01 Intro text.\nRates rise 2% each year" for n in range(1, 9)),
                 *(f"ARTICLE {n}: TOPIC\n{n}.01 Other text here." for n in range(9, 30)))
    assert "2%" in body(split_sections(txt2))


def test_header_with_page_number_dropped():
    txt = pages(*(f"Sample Agreement - page {n}\nARTICLE {n}: TOPIC\n{n}.01 Clause text." for n in (1, 2, 3)))
    assert "Sample Agreement" not in body(split_sections(txt))


def test_many_form_feeds_fast():
    txt = "\f".join("x" for _ in range(50000))  # 50k one-line pages: was 3+ s in draft 7
    t = time.perf_counter(); split_sections(txt)
    assert time.perf_counter() - t < 0.5


def test_many_pages_with_running_header_linear():
    txt = "\f".join(f"Running Header\nline {i}\n{i + 1}" for i in range(20000))
    t = time.perf_counter(); secs = split_sections(txt)
    assert time.perf_counter() - t < 1.5
    assert "Running Header" not in body(secs)


# ---- B4: numbered schedule items stay in their annex ----
def test_schedule_items_do_not_merge_into_articles():
    txt = ("1. PURPOSE\n1.01 Purpose text here.\n2. WAGES\nThe Employer shall pay $20.00 per hour.\n"
           "SCHEDULE C - BENEFITS\n1. DENTAL\nThe Employer shall pay 80% of dental premiums.\n"
           "2. VISION\nVision text here.\nSCHEDULE E - PENSION\n1. PLAN\nThe Plan shall vest after two years.\n")
    secs = {s.number: s for s in split_sections(txt)}
    assert "dental" not in secs["1"].text.lower() and "Plan" not in secs["1"].text
    assert "Vision" not in secs["2"].text
    assert secs["Schedule C 1"].title == "DENTAL" and "80%" in secs["Schedule C 1"].text
    assert secs["Schedule C 2"].title == "VISION"
    assert secs["Schedule E 1"].title == "PLAN" and secs["Schedule E 1"].level == 2


# ---- report code spans ----
def test_code_span_pipe_and_trailing_punct():
    out = md_escape("see (https://example.org/a|b).")
    assert "`https://example.org/a\\|b`" in out
    assert out.endswith("`\\).") or out.endswith("`).")
    assert "|" not in out.replace("\\|", "")
