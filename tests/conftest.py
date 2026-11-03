import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
FIX = ROOT / "tests" / "fixtures"


@pytest.fixture
def fixtures():
    return FIX


def make_pdf(path: Path, lines: list[str], per_page: int = 60) -> Path:
    """Write a minimal text PDF (Helvetica), `per_page` lines per page, no third-party libs."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]
    n = len(pages)
    font = 3 + 2 * n
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{3 + 2 * i} 0 R" for i in range(n)).encode(), n)]
    for i, pg in enumerate(pages):
        body = "BT /F1 10 Tf 12 TL 50 780 Td " + " ".join(f"({esc(l)}) Tj T*" for l in pg) + " ET"
        stream = body.encode("latin-1")
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents %d 0 R "
                    b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (4 + 2 * i, font))
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    path.write_bytes(bytes(out))
    return path


def make_docx(path: Path, paragraphs: list[str]) -> Path:
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paras = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(p)}</w:t></w:r></w:p>' for p in paragraphs)
    doc = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>{paras}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("word/document.xml", doc)
    return path


@pytest.fixture
def pdf_factory(tmp_path):
    return lambda name, lines: make_pdf(tmp_path / name, lines)


@pytest.fixture
def docx_factory(tmp_path):
    return lambda name, paras: make_docx(tmp_path / name, paras)
