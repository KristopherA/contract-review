import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_frontmatter_follows_agentskills_spec():
    text = (ROOT / "SKILL.md").read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    fm = yaml.safe_load(m[1])
    assert fm["name"] == "contract-review" and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm["name"])
    assert 0 < len(fm["description"]) <= 1024
    assert len(fm["compatibility"]) <= 500
    assert len(text.splitlines()) < 500
    for ref in re.findall(r"\]\(((?:references|templates|assets|scripts)/[^)]+)\)", text):
        assert (ROOT / ref).is_file(), ref
