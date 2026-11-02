import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def _frontmatter():
    text = (ROOT / "SKILL.md").read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md must start with YAML frontmatter"
    return text, yaml.safe_load(m[1])


def test_frontmatter_follows_agentskills_spec():
    text, fm = _frontmatter()
    assert set(fm) <= SPEC_FIELDS, f"non-spec fields: {set(fm) - SPEC_FIELDS}"
    assert {"name", "description"} <= set(fm)
    assert fm["name"] == ROOT.name or fm["name"] == "contract-review"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm["name"]) and len(fm["name"]) <= 64
    assert isinstance(fm["description"], str) and 0 < len(fm["description"]) <= 1024
    assert isinstance(fm["compatibility"], str) and 0 < len(fm["compatibility"]) <= 500
    assert isinstance(fm["allowed-tools"], str)
    assert len(text.splitlines()) < 500


def test_metadata_is_string_to_string():
    _, fm = _frontmatter()
    md = fm["metadata"]
    assert isinstance(md, dict) and md
    for k, v in md.items():
        assert isinstance(k, str) and isinstance(v, str), (k, type(v))
    assert md["version"] == "0.1.0"


def test_relative_links_exist():
    text, _ = _frontmatter()
    for ref in re.findall(r"\]\(((?:references|templates|assets|scripts)/[^)]+)\)", text):
        assert (ROOT / ref).is_file(), ref
