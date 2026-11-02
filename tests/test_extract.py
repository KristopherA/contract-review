import shutil

import pytest

from crlib.extract import ExtractionError, extract_text
from crlib.sections import split_sections

LINES = ["SERVICE AGREEMENT", "between Example Corp and Sample Services Ltd.",
         "1. Scope", "Supplier provides support for example.com.",
         "2. Fees", "Customer pays $1,200 USD per month."]


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="pdftotext not installed")
def test_pdf_pdftotext(pdf_factory):
    p = pdf_factory("a.pdf", LINES)
    text = extract_text(p, "pdftotext")
    assert "Supplier provides support for example.com." in text
    assert [s.title for s in split_sections(text)] == ["Preamble", "Scope", "Fees"]


def test_pdf_pypdf(pdf_factory):
    p = pdf_factory("b.pdf", LINES)
    text = extract_text(p, "pypdf")
    assert "$1,200 USD" in text
    assert [s.number for s in split_sections(text) if s.number] == ["1", "2"]


def test_docx_zip_xml(docx_factory):
    p = docx_factory("c.docx", LINES)
    text = extract_text(p)
    secs = split_sections(text)
    assert secs[2].title == "Fees" and "$1,200" in secs[2].text


def test_bad_inputs(tmp_path):
    with pytest.raises(ExtractionError):
        extract_text(tmp_path / "missing.pdf")
    bad = tmp_path / "x.docx"; bad.write_bytes(b"not a zip")
    with pytest.raises(ExtractionError):
        extract_text(bad)
    odd = tmp_path / "x.rtf"; odd.write_text("hi")
    with pytest.raises(ExtractionError):
        extract_text(odd)


# --- resource limits and error handling -------------------------------------
import subprocess
import tracemalloc
import zipfile

from crlib import extract as ex


def _docx_with(path, xml: bytes, method=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", method) as z:
        z.writestr("word/document.xml", xml)
    return path


def test_docx_zip_bomb_rejected_without_inflating(tmp_path):
    p = _docx_with(tmp_path / "bomb.docx", b"<a>" + b"A" * (ex.MAX_XML_BYTES + 1024) + b"</a>")
    assert p.stat().st_size < 200_000
    tracemalloc.start()
    with pytest.raises(ExtractionError, match="cap"):
        extract_text(p)
    peak = tracemalloc.get_traced_memory()[1]; tracemalloc.stop()
    assert peak < 5 * 1024 * 1024


def test_docx_high_ratio_rejected(tmp_path):
    p = _docx_with(tmp_path / "ratio.docx", b"<a>" + b" " * 2_000_000 + b"</a>")
    with pytest.raises(ExtractionError, match="zip bomb"):
        extract_text(p)


def test_docx_stream_cap_even_if_header_lies(tmp_path, monkeypatch):
    p = _docx_with(tmp_path / "lie.docx", b"<a>" + b"x y " * 5000 + b"</a>", zipfile.ZIP_STORED)
    monkeypatch.setattr(ex, "MAX_XML_BYTES", 10_000)
    real = zipfile.ZipFile.getinfo
    def lying(self, name):
        info = real(self, name); info.file_size = 10; return info
    monkeypatch.setattr(zipfile.ZipFile, "getinfo", lying)
    with pytest.raises(ExtractionError):  # either our stream cap or zipfile's CRC/length check
        extract_text(p)


def test_docx_corrupt_xml(tmp_path):
    p = _docx_with(tmp_path / "corrupt.docx", b"<w:document><w:body><w:p>")
    with pytest.raises(ExtractionError, match="corrupt"):
        extract_text(p)


def test_docx_doctype_entity_rejected(tmp_path):
    xml = b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]><d>&a;</d>'
    with pytest.raises(ExtractionError, match="DOCTYPE"):
        extract_text(_docx_with(tmp_path / "ent.docx", xml))


def test_docx_missing_part(tmp_path):
    p = tmp_path / "empty.docx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("other.xml", "<a/>")
    with pytest.raises(ExtractionError, match="no word/document.xml"):
        extract_text(p)


def test_pdftotext_timeout_falls_back_to_pypdf(pdf_factory, monkeypatch):
    p = pdf_factory("slow.pdf", LINES)
    def slow(*a, **k):
        raise subprocess.TimeoutExpired(a[0], k.get("timeout"))
    monkeypatch.setattr(ex.subprocess, "run", slow)
    monkeypatch.setattr(ex.shutil, "which", lambda _: "/usr/bin/pdftotext")
    assert "$1,200 USD" in extract_text(p, "auto")
    with pytest.raises(ExtractionError, match="timed out"):
        extract_text(p, "pdftotext")


def test_corrupt_pdf_clean_error(tmp_path):
    p = tmp_path / "bad.pdf"; p.write_bytes(b"%PDF-1.4\nthis is not a pdf at all")
    with pytest.raises(ExtractionError):
        extract_text(p, "pypdf")
    with pytest.raises(ExtractionError):
        extract_text(p, "auto")


def test_pdf_caps(pdf_factory, monkeypatch):
    p = pdf_factory("cap.pdf", LINES)
    monkeypatch.setattr(ex, "MAX_PDF_PAGES", 0)
    with pytest.raises(ExtractionError, match="pages"):
        extract_text(p, "pypdf")
    monkeypatch.setattr(ex, "MAX_PDF_BYTES", 10)
    with pytest.raises(ExtractionError, match="larger"):
        extract_text(p, "auto")


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="pdftotext not installed")
def test_pdftotext_dash_filename(tmp_path, monkeypatch):
    import conftest
    conftest.make_pdf(tmp_path / "-n.pdf", LINES)
    monkeypatch.chdir(tmp_path)
    assert "Scope" in extract_text("-n.pdf", "pdftotext")
    calls = []
    real = ex.subprocess.run
    monkeypatch.setattr(ex.subprocess, "run", lambda cmd, **k: calls.append(cmd) or real(cmd, **k))
    extract_text("-n.pdf", "pdftotext")
    info = next(c for c in calls if c[0].endswith("pdfinfo"))
    text = next(c for c in calls if c[0].endswith("pdftotext"))
    assert info[-2] == "--" and info[-1].startswith("/")
    assert text[-3] == "--" and text[-2].startswith("/")


# --- draft 3: refuse, never truncate, long PDFs -------------------------------
def test_501_page_pdf_refused_in_every_mode(tmp_path):
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(501):
        w.add_blank_page(width=200, height=200)
    p = tmp_path / "long.pdf"
    with open(p, "wb") as fh:
        w.write(fh)
    assert ex.pdf_page_count(p) == 501
    for backend in ("auto", "pdftotext", "pypdf"):
        with pytest.raises(ExtractionError, match="501 pages"):
            extract_text(p, backend)


def test_page_count_falls_back_to_pypdf(pdf_factory, monkeypatch):
    p = pdf_factory("count.pdf", LINES)
    monkeypatch.setattr(ex.shutil, "which", lambda _: None)
    assert ex.pdf_page_count(p) == 1
    monkeypatch.setattr(ex, "_page_count_pypdf", lambda _p: 600)
    with pytest.raises(ExtractionError, match="600 pages"):
        extract_text(p, "auto")


def test_monkeypatched_pdfinfo_count_blocks_pdftotext(pdf_factory, monkeypatch):
    p = pdf_factory("fake.pdf", LINES)
    monkeypatch.setattr(ex, "_page_count_pdfinfo", lambda _p, _t: 600)
    with pytest.raises(ExtractionError, match="limit is 500"):
        extract_text(p, "pdftotext")


def test_defusedxml_in_use():
    assert ex._SAFE_ET is not None
