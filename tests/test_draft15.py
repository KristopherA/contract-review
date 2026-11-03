"""Draft 15: evolve follows the clause by alignment after its first match; whole-word
title substrings; ties broken by alignment; positional-id warning; query cap; '12.01(a)',
'12,01', 'LOU'; appendix labels must start at 1; escaped titles in report labels."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from crlib import boilerplate as bp
from crlib.evolution import MAX_QUERY, AmbiguousQuery, evolve, match_section
from crlib.report import _lbl, evolution_markdown
from crlib.sections import split_sections

ROOT = Path(__file__).resolve().parents[1]
WAGES_BODY = ("{n}.01 The Employer shall pay each employee the hourly rate set out in Appendix A.\n"
              "{n}.02 Rates increase by two percent (2%) on each anniversary of this Agreement.\n")
V1 = ("ARTICLE 1: PURPOSE\n1.01 The purpose of this Agreement is to set terms.\n"
      "ARTICLE 2: WAGES\n" + WAGES_BODY.format(n=2) +
      "ARTICLE 3: TERM\n3.01 This Agreement runs for three years.\n")
V2 = ("ARTICLE 1: PURPOSE\n1.01 The purpose of this Agreement is to set terms.\n"
      "ARTICLE 2: WAIVERS\n2.01 No waiver of a breach is a waiver of a later breach.\n"
      "ARTICLE 3: STAGES\n3.01 A grievance proceeds through three stages in order.\n"
      "ARTICLE 4: SALARIES\n" + WAGES_BODY.format(n=4) +
      "ARTICLE 5: TERM\n5.01 This Agreement runs for three years.\n")


def vs(*texts):
    return [(f"v{k + 1}", split_sections(t)) for k, t in enumerate(texts)]


def test_renamed_section_is_followed_by_alignment_not_a_lookalike_title():
    assert match_section(split_sections(V2), "Wages")["section"].title == "STAGES"  # the trap
    r = evolve(vs(V1, V2), "Wages")
    t = r["timeline"]
    assert [e["section"]["title"] for e in t] == ["WAGES", "SALARIES"]
    assert t[1]["matched_by"] == "aligned" and t[1]["renumbered_from"] == "2"
    assert any("also matches §3 STAGES" in w and "following the aligned §4 SALARIES" in w for w in r["warnings"])


@pytest.mark.parametrize("q,title", [("Termination", "DETERMINATION OF SENIORITY"),
                                     ("pay", "REPAYMENT OF OVERPAYMENTS"), ("art", "DEPARTURE")])
def test_substring_needs_whole_words(q, title):
    s = split_sections(f"ARTICLE 1: {title}\n1.01 Some text here.\nARTICLE 2: HOURS\n2.01 Other text.\n")
    assert match_section(s, q) is None
    r = evolve([("v1", s), ("v2", s)], q)
    assert not any(e["present"] for e in r["timeline"]) and "no version has a section" in r["warnings"][-1]


def test_whole_word_substring_still_matches():
    s = split_sections("ARTICLE 1: RATES OF PAY\n1.01 Text.\nARTICLE 2: HOURS\n2.01 Text.\n")
    assert match_section(s, "pay")["section"].number == "1"


def test_tie_in_later_version_broken_by_alignment():
    a = "ARTICLE 1: OVERTIME RATES\n1.01 Overtime is paid at one and one-half times the basic rate.\n"
    b = ("ARTICLE 1: OVERTIME RATES\n1.01 Overtime is paid at one and one-half times the basic rate.\n"
         "ARTICLE 2: OVERTIME BANKS\n2.01 Banked overtime may be taken as paid leave by agreement.\n")
    t = evolve(vs(a, b), "overtime")["timeline"]
    assert [e["section"]["number"] for e in t] == ["1", "1"]
    with pytest.raises(AmbiguousQuery):
        evolve(vs(b, a), "overtime")  # tie in the first version: nothing to follow


def test_id_query_warns_that_ids_are_positional():
    r = evolve(vs(V1, V2), "s2")
    assert any("positional" in w for w in r["warnings"])


def test_query_length_is_capped():
    with pytest.raises(ValueError, match="at most"):
        evolve(vs(V1, V1), "x" * (MAX_QUERY + 1))
    assert match_section(split_sections(V1), "Wages " * 30) is None  # 180 chars is fine


X = ("ARTICLE 12: OVERTIME\n12.01 Overtime is paid at double time.\n12.02 Call-back pays three hours.\n"
     "LETTER OF UNDERSTANDING #3: PARKING\nThe Employer shall provide parking.\n")


@pytest.mark.parametrize("q,num,note", [("12.01(a)", "12", "sub-item (a)"), ("§12.01(a)(ii)", "12", "sub-item (a)(ii)"),
                                        ("12,01", "12", None), ("LOU", "Letter of Understanding 3", None),
                                        ("LOU 3", "Letter of Understanding 3", None), ("lou #3", None, None)])
def test_query_forms(q, num, note):
    m = match_section(split_sections(X), q)
    if num is None:
        assert m is None or m["section"].number == "Letter of Understanding 3"
        return
    assert m["section"].number == num
    assert (note in m["note"]) if note else m["note"] is None


def test_bare_lou_with_several_letters_lists_them():
    s = split_sections(X + "LETTER OF UNDERSTANDING #4: TRAINING\nTraining is provided.\n")
    with pytest.raises(AmbiguousQuery, match="Add its number"):
        match_section(s, "LOU")


def run(*args):
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "contract_review.py"), *map(str, args)],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout, p.stderr


def test_cli_follows_renamed_section_and_rejects_substring_traps(tmp_path):
    a, b = tmp_path / "v1.txt", tmp_path / "v2.txt"
    a.write_text(V1); b.write_text(V2)
    rc, out, err = run("evolve", a, b, "--section", "Wages")
    assert rc == 0 and [e["section"]["title"] for e in json.loads(out)["timeline"]] == ["WAGES", "SALARIES"]
    assert "following the aligned §4 SALARIES" in err
    c = tmp_path / "c.txt"
    c.write_text("ARTICLE 1: DETERMINATION OF SENIORITY\n1.01 Text.\nARTICLE 2: REPAYMENT\n2.01 Text.\n"
                 "ARTICLE 3: DEPARTURE\n3.01 Text.\n")
    for q in ("Termination", "pay", "art"):
        rc, out, err = run("evolve", c, c, "--section", q)
        assert rc == 0 and not any(e["present"] for e in json.loads(out)["timeline"]), q
        assert "no version has a section" in err
    rc, _, err = run("evolve", a, b, "--section", "q" * 300)
    assert rc == 2 and "at most 200" in err


# ---- labels under an appendix must start at 1 ----
LIB = bp.load_library()
CBA = [c for c in LIB["clauses"] if c["id"].startswith("cba-")]


@pytest.mark.parametrize("c", CBA, ids=lambda c: c["id"])
@pytest.mark.parametrize("first", ["30.01", "2.1", "4.01", "30.5"])
def test_appendix_labels_not_starting_at_1_do_not_fold(c, first):
    assert bp.match(first + " " + c["text"], "", LIB, number="Appendix A") is None


def test_strip_labels_start_at_1():
    assert bp.strip_labels("30.01 The A.\n\n30.02 The B.", "Appendix A") == "30.01 The A.\n\n30.02 The B."
    assert bp.strip_labels("2.1 The A.", "Appendix A") == "2.1 The A."
    assert bp.strip_labels("1.1 The A.\n\n1.2 The B.", "Appendix A") == "The A.\n\nThe B."


# ---- report labels ----
def test_label_escapes_pipe_in_title():
    lbl = _lbl({"number": "4", "title": "RATES | PREMIUMS", "id": "s4"})
    assert "|" not in lbl.replace("\\|", "")
    t = split_sections("ARTICLE 1: RATES | PREMIUMS\n1.01 Rates are paid.\n")
    md = evolution_markdown(evolve([("v1", t), ("v2", t)], "1"), None, {})
    rows = [l for l in md.splitlines() if l.startswith("| v")]
    assert rows and all(l.count("|") - l.count("\\|") == rows[0].count("|") - rows[0].count("\\|") for l in rows)
    assert "RATES \\| PREMIUMS" in md


def test_known_tradeoff_masked_shift_line_is_dropped_with_warning(capsys):
    from layout_cases import art, doc
    text = doc(*(art(k, bottom=[f"Shift {k} employees shall receive $2.00 per hour." if k % 2 else f"Page {k}"])
                 for k in range(1, 11)))
    body = "\n".join(s.text for s in split_sections(text))
    assert "Shift 1 employees" not in body  # documented trade-off
    assert "warning:" in capsys.readouterr().err


def test_known_tradeoff_three_pages_per_parity_keeps_pension():
    from layout_cases import PENSION, art, doc
    text = doc(*(art(k, bottom=[PENSION + "." if k % 2 else f"Page {k}"]) for k in range(1, 7)))
    assert "Pension" in "\n".join(s.text for s in split_sections(text))
