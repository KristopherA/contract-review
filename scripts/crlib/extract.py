"""Text extraction for PDF, DOCX, TXT and Markdown. Local only."""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ExtractionError(RuntimeError):
    pass


def _pdf_pdftotext(path: Path) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise ExtractionError("pdftotext not found")
    res = subprocess.run([exe, "-enc", "UTF-8", str(path), "-"],
                         capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise ExtractionError(f"pdftotext failed: {res.stderr.strip()}")
    return res.stdout


def _pdf_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("pypdf is not installed") from exc
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_pdf(path: Path, backend: str = "auto") -> str:
    if backend in ("auto", "pdftotext"):
        try:
            text = _pdf_pdftotext(path)
            if text.strip() or backend == "pdftotext":
                return text
        except ExtractionError:
            if backend == "pdftotext":
                raise
    text = _pdf_pypdf(path)
    if not text.strip():
        raise ExtractionError(f"{path}: no text layer (scanned PDF? OCR is out of scope)")
    return text


def extract_docx(path: Path) -> str:
    """Read word/document.xml directly (zip + XML), no python-docx needed."""
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ExtractionError(f"{path}: not a valid .docx") from exc
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(f"{W_NS}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{W_NS}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{W_NS}tab":
                parts.append("\t")
            elif node.tag in (f"{W_NS}br", f"{W_NS}cr"):
                parts.append("\n")
        paras.append("".join(parts))
    return "\n".join(paras)


def extract_text(path: str | Path, pdf_backend: str = "auto") -> str:
    path = Path(path)
    if not path.is_file():
        raise ExtractionError(f"{path}: file not found")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = extract_pdf(path, pdf_backend)
    elif suffix == ".docx":
        text = extract_docx(path)
    elif suffix in (".txt", ".md", ".markdown", ""):
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ExtractionError(f"{path}: unsupported type {suffix} (use pdf, docx, txt, md)")
    return normalise(text)


def normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate line breaks
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip() + "\n"
