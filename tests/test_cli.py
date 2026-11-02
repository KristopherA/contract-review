import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "contract_review.py"


def run(*args):
    r = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def test_diff_json_and_md(fixtures, tmp_path):
    rc, out, _ = run("diff", fixtures / "msa_v1.txt", fixtures / "msa_v2.txt")
    assert rc == 0
    changes = json.loads(out)
    s = tmp_path / "s.json"; s.write_text(json.dumps({changes[0]["id"]: "Effective date moved."}))
    rc, md, _ = run("diff", fixtures / "msa_v1.txt", fixtures / "msa_v2.txt", "--format", "md", "--summaries", s)
    assert rc == 0 and "Effective date moved." in md


def test_outline_evolve_errors(fixtures, tmp_path):
    rc, out, _ = run("outline", fixtures / "msa_v2.txt")
    assert rc == 0 and json.loads(out)["boilerplate_folded"]
    rc, md, _ = run("evolve", *(fixtures / f"msa_v{n}.txt" for n in (1, 2, 3)), "--section", "Confidentiality", "--format", "md")
    assert rc == 0 and "five (5)" in md
    rc, _, err = run("sections", tmp_path / "nope.pdf")
    assert rc == 2 and "not found" in err


def test_helpers_have_no_network_code():
    banned = re.compile(r"^\s*(import|from)\s+(socket|urllib|http|requests|httpx|aiohttp|ftplib|smtplib)\b", re.M)
    for p in (ROOT / "scripts").rglob("*.py"):
        assert not banned.search(p.read_text()), p


def test_cli_clean_errors(tmp_path, fixtures):
    import zipfile
    bad = tmp_path / "corrupt.docx"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("word/document.xml", "<w:document><unclosed>")
    rc, out, err = run("outline", bad)
    assert rc == 2 and err.startswith("error:") and "Traceback" not in err
    y = tmp_path / "bad.yaml"; y.write_text("clauses: [\n  - id: x\n")
    rc, _, err = run("outline", fixtures / "msa_v1.txt", "--library", y)
    assert rc == 2 and "invalid YAML" in err and "Traceback" not in err
    pdf = tmp_path / "bad.pdf"; pdf.write_bytes(b"%PDF-1.4 garbage")
    rc, _, err = run("--pdf-backend", "pypdf", "sections", pdf)
    assert rc == 2 and "Traceback" not in err
    j = tmp_path / "s.json"; j.write_text("{not json")
    rc, _, err = run("diff", fixtures / "msa_v1.txt", fixtures / "msa_v2.txt", "--format", "md", "--summaries", j)
    assert rc == 2 and "Traceback" not in err
