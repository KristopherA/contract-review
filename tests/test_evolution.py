from crlib.evolution import evolve
from crlib.extract import extract_text
from crlib.report import evolution_markdown
from crlib.sections import split_sections


def _vs(fixtures):
    return [(f"v{n}", split_sections(extract_text(fixtures / f"msa_v{n}.txt"))) for n in (1, 2, 3)]


def test_termination_timeline(fixtures):
    r = evolve(_vs(fixtures), "Termination")
    t = r["timeline"]
    assert [e["status"] for e in t] == ["baseline", "changed", "changed"]
    assert [e["section"]["number"] for e in t] == ["7", "7", "4"]
    assert t[2]["renumbered_from"] == "7"
    md = evolution_markdown(r, "Cure period and convenience notice both shortened.", {"v3": "cure 30 -> 15 days"})
    assert "changed (was §7)" in md and "cure 30 -> 15 days" in md and "~~thirty (30)~~ **fifteen (15)**" in md


def test_removed_and_by_number(fixtures):
    t = evolve(_vs(fixtures), "Limitation of Liability")["timeline"]
    assert [e["status"] for e in t] == ["baseline", "unchanged", "removed"]
    t = evolve(_vs(fixtures), "§8")["timeline"]
    assert t[0]["section"]["title"] == "Entire Agreement"


def test_added_later(fixtures):
    t = evolve(_vs(fixtures), "Data Protection")["timeline"]
    assert [e["status"] for e in t] == ["absent", "first-seen", "removed"]
