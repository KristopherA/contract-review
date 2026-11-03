"""Draft-9 regressions (synthetic text only): headers identical on (nearly) every page,
minority sentence footers, body resuming after an annex, obligation subjects."""
from crlib import facts
from crlib.sections import split_sections

HDRS = ["Collective Agreement 2024-2027.", "Subject to Article 30 Ratification",
        "This Agreement shall be read with the Pension Plan."]


def body(secs):
    return "\n".join(s.text for s in secs)


def pages(*pgs):
    return "\n\f\n".join(pgs)


def page(n, top=(), bottom=()):
    return "\n".join([*top, f"ARTICLE {n}: TOPIC {n}", f"{n}.01 The Employer shall pay ${n}0.00 per hour.",
                      f"{n}.02 Clause {n} more text here.", *bottom])


def _all_facts(secs):
    return facts.extract([p for s in secs for p in s.parts])


def test_headers_on_every_page_dropped_top_and_bottom():
    for kw in ({"top": HDRS}, {"bottom": HDRS}):
        secs = split_sections(pages(*(page(n, **kw) for n in range(1, 5))))
        b = body(secs)
        for h in HDRS:
            assert h.rstrip(".") not in b, (kw.keys(), h)
        f = _all_facts(secs)
        assert not any("Pension" in o["text"] for o in f["obligations"])
        assert len([o for o in f["obligations"] if o["kind"] == "obligation"]) == 4  # the real ones
        assert [a["value"] for a in f["amounts"]] == ["$10.00", "$20.00", "$30.00", "$40.00"]


def test_header_on_nearly_every_page_dropped():
    pgs = [page(n, top=HDRS[2:]) if n != 7 else page(n) for n in range(1, 11)]  # 9 of 10 pages
    assert "Pension" not in body(split_sections(pages(*pgs)))


def test_sentence_footer_on_minority_of_pages_kept():
    pgs = [page(n, bottom=["Subject to Article 12."] if n in (2, 5, 9) else []) for n in range(1, 13)]
    assert body(split_sections(pages(*pgs))).count("Subject to Article 12") == 3


def test_sentence_footer_on_3_of_5_pages():
    """Documented: below 80%, a bottom-edge sentence/citation line is kept; at the top it
    is a running header and dropped."""
    bot = [page(n, bottom=["Subject to Article 12."] if n <= 3 else []) for n in range(1, 6)]
    assert body(split_sections(pages(*bot))).count("Subject to Article 12") == 3
    top = [page(n, top=["Subject to Article 12."] if n <= 3 else []) for n in range(1, 6)]
    assert "Subject to Article 12" not in body(split_sections(pages(*top)))


def test_numbers_after_annex_stay_in_annex_without_toc():
    """Draft 10 replaced draft 9's last+1 rule: without a TOC or ARTICLE keyword, "3." after
    a schedule stays in it (the corpus covers the TOC / keyword cases)."""
    txt = ("1. PURPOSE\nPurpose text here.\n2. WAGES\nWage text here.\n"
           "SCHEDULE A - BENEFITS\n1. DENTAL\nDental text here.\n"
           "3. HOURS\nThe Employer shall schedule hours.\n")
    secs = {s.number: s for s in split_sections(txt)}
    assert "3" not in secs and secs["Schedule A 3"].title == "HOURS"


def test_who_is_last_noun_phrase():
    o = facts.obligation("See Art. 5. The Union shall notify the Employer.")
    assert o["who"] == "The Union"
    o = facts.obligation("Where notice is late, i.e. after the deadline, the Employer shall pay $5.00.")
    assert o["who"] == "the Employer"
    o = facts.obligation("Article 7 the Employer shall post notices.")
    assert o["who"] == "the Employer"


def test_no_split_on_abbreviations():
    for s in ("Benefits, e.g. Dental and Vision, shall continue.",
              "Leave under Art. Four shall be paid.",
              "Grievance No. Twelve shall be heard.",
              "Notice under s. (2) shall be given.",
              "The rate, i.e. The Base Rate, shall apply."):
        assert facts.sentences(s) == [s], s
