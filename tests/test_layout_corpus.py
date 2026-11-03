"""Table-driven layout corpus: every page-layout case from drafts 5-12 (tests/layout_cases.py).
For each case the full section tree (ids, numbers, titles), the clause every fact cites,
and the absence of leaked header/footer text are asserted."""
import pytest

from crlib import facts
from crlib.sections import cite, split_sections
from layout_cases import CASES, HDRS


@pytest.mark.parametrize("c", CASES, ids=[c["name"] for c in CASES])
def test_layout_case(c):
    secs = split_sections(c["text"])
    real = [s for s in secs if s.level > 0]
    assert [(s.number, s.title) for s in real] == c["tree"]
    assert [s.id for s in real] == [f"s{k}" for k in range(1, len(real) + 1)]
    f = facts.extract([p for s in secs for p in s.parts])
    if c["amounts"] is not None:
        assert [(a["value"], a["cite"]) for a in f["amounts"]] == c["amounts"]
    valid = {cite(s.number) for s in secs} | {cite(p[0]) for s in secs for p in s.parts}
    for kind in ("amounts", "percentages", "deadlines", "obligations"):
        for x in f[kind]:
            assert x["cite"] in valid, (kind, x)  # every fact points at a real clause
    text = "\n".join(s.text for s in secs)
    for k in c["keep"]:
        assert k in text, k
    for g in c["gone"]:
        assert g not in text, g
    lines = text.split("\n")
    for g in c["gone_lines"]:
        assert g not in lines, g
    if c["obligations"] is not None:
        assert len(f["obligations"]) == c["obligations"]
    if "reviewer headers" in c["name"] or "Pension" in c["name"]:
        assert not any("Pension" in o["text"] or "2024" in o["text"] for o in f["obligations"])
        assert all(h.rstrip(".") not in text for h in HDRS)


def test_corpus_size():
    assert len(CASES) >= 45
