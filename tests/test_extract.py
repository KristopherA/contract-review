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
