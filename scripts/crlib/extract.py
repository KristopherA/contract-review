"""Text extraction for PDF, DOCX, TXT and Markdown. Local only, bounded resources."""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MAX_XML_BYTES = 20 * 1024 * 1024      # uncompressed word/document.xml
MAX_COMPRESSION_RATIO = 100           # uncompressed / compressed
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_TEXT_BYTES = 20 * 1024 * 1024
PDFTOTEXT_TIMEOUT = 120


class ExtractionError(RuntimeError):
    pass


def _pdf_pdftotext(path: Path, timeout: float) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise ExtractionError("pdftotext not found")
    try:
        res = subprocess.run([exe, "-enc", "UTF-8", "-l", str(MAX_PDF_PAGES), "--", str(path), "-"],
                             capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError(f"pdftotext timed out after {timeout:g}s") from exc
    except OSError as exc:
        raise ExtractionError(f"pdftotext could not run: {exc}") from exc
    if res.returncode != 0:
        raise ExtractionError(f"pdftotext failed: {res.stderr.strip()[:300]}")
    return res.stdout


def _pdf_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractionError("pypdf is not installed") from exc
    try:
        reader = PdfReader(str(path))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ExtractionError(f"{path.name}: more than {MAX_PDF_PAGES} pages")
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except ExtractionError:
        raise
    except Exception as exc:  # pypdf raises many types (PdfReadError, ValueError, KeyError...)
        raise ExtractionError(f"{path.name}: unreadable PDF ({type(exc).__name__}: {exc})") from exc


def extract_pdf(path: Path, backend: str = "auto", timeout: float = PDFTOTEXT_TIMEOUT) -> str:
    if path.stat().st_size > MAX_PDF_BYTES:
        raise ExtractionError(f"{path.name}: larger than {MAX_PDF_BYTES // 2**20} MB")
    if backend in ("auto", "pdftotext"):
        try:
            text = _pdf_pdftotext(path, timeout)
            if text.strip() or backend == "pdftotext":
                return text
        except ExtractionError:
            if backend == "pdftotext":
                raise
    text = _pdf_pypdf(path)
    if not text.strip():
        raise ExtractionError(f"{path.name}: no text layer (scanned PDF? OCR is out of scope)")
    return text


def _read_bounded(zf: zipfile.ZipFile, name: str) -> bytes:
    info = zf.getinfo(name)
    if info.file_size > MAX_XML_BYTES:
        raise ExtractionError(f"{name} is {info.file_size} bytes uncompressed (cap {MAX_XML_BYTES})")
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise ExtractionError(f"{name} compression ratio is suspicious (possible zip bomb)")
    out = bytearray()
    with zf.open(info) as fh:  # stream; never trust the header alone
        while chunk := fh.read(1 << 16):
            out += chunk
            if len(out) > MAX_XML_BYTES:
                raise ExtractionError(f"{name} exceeds {MAX_XML_BYTES} bytes when decompressed")
    return bytes(out)


def extract_docx(path: Path) -> str:
    """Read word/document.xml directly (zip + XML), no python-docx needed."""
    try:
        with zipfile.ZipFile(path) as zf:
            xml = _read_bounded(zf, "word/document.xml")
    except KeyError as exc:
        raise ExtractionError(f"{path.name}: not a .docx (no word/document.xml)") from exc
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, OSError, EOFError) as exc:
        raise ExtractionError(f"{path.name}: not a valid .docx ({exc})") from exc
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", xml, re.IGNORECASE):
        raise ExtractionError(f"{path.name}: DOCTYPE/ENTITY declarations are not allowed")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ExtractionError(f"{path.name}: corrupt document.xml ({exc})") from exc
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
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ExtractionError(f"{path}: file not found")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = extract_pdf(path, pdf_backend)
    elif suffix == ".docx":
        text = extract_docx(path)
    elif suffix in (".txt", ".md", ".markdown", ""):
        if path.stat().st_size > MAX_TEXT_BYTES:
            raise ExtractionError(f"{path.name}: larger than {MAX_TEXT_BYTES // 2**20} MB")
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ExtractionError(f"{path.name}: unsupported type {suffix} (use pdf, docx, txt, md)")
    return normalise(text)


def normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate line breaks
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip() + "\n"
