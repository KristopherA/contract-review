"""Text extraction for PDF, DOCX, TXT and Markdown. Local only, bounded resources."""
from __future__ import annotations

import contextlib
import logging
import re
import warnings
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:  # pinned in requirements.txt; stdlib + DOCTYPE guard if it is missing
    from defusedxml import ElementTree as _SAFE_ET
    from defusedxml import DefusedXmlException as _DefusedError
except ImportError:  # pragma: no cover - exercised only without defusedxml
    _SAFE_ET, _DefusedError = None, ()

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MAX_XML_BYTES = 20 * 1024 * 1024      # uncompressed word/document.xml
MAX_COMPRESSION_RATIO = 100           # uncompressed / compressed
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_TEXT_BYTES = 20 * 1024 * 1024
PDFTOTEXT_TIMEOUT = 120


@contextlib.contextmanager
def _quiet_pypdf():
    """pypdf logs recoverable damage ("Ignoring wrong pointing object") to stderr; silence
    its logger and warnings while we read. Real failures still raise and are reported."""
    log = logging.getLogger("pypdf")
    old = log.level
    log.setLevel(logging.CRITICAL)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            yield
    finally:
        log.setLevel(old)


class ExtractionError(RuntimeError):
    pass


class PageMismatchError(ExtractionError):
    """Extractor output does not cover every page. Never fall back past this."""


def _pdf_pdftotext(path: Path, timeout: float, expected_pages: int | None = None) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise ExtractionError("pdftotext not found")
    try:
        res = subprocess.run([exe, "-layout", "-enc", "UTF-8", "-l", str(MAX_PDF_PAGES), "--", str(path), "-"],
                             capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError(f"pdftotext timed out after {timeout:g}s") from exc
    except OSError as exc:
        raise ExtractionError(f"pdftotext could not run: {exc}") from exc
    if res.returncode != 0:
        raise ExtractionError(f"pdftotext failed: {res.stderr.strip()[:300]}")
    got = res.stdout.count("\f")  # pdftotext ends every page with a form feed
    if expected_pages is not None and got != expected_pages:
        raise PageMismatchError(f"pdftotext returned {got} pages but the PDF has {expected_pages}; "
                              "refusing partial text")
    return res.stdout


def _page_count_pdfinfo(path: Path, timeout: float) -> int | None:
    exe = shutil.which("pdfinfo")
    if not exe:
        return None
    try:
        res = subprocess.run([exe, "--", str(path)], capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    m = re.search(r"^Pages:\s+(\d+)", res.stdout, re.M) if res.returncode == 0 else None
    return int(m[1]) if m else None


def _pypdf_available() -> bool:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def _page_count_pypdf(path: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractionError("cannot count PDF pages: neither pdfinfo nor pypdf is available") from exc
    try:
        with _quiet_pypdf():
            return len(PdfReader(str(path)).pages)
    except Exception as exc:
        raise ExtractionError(f"{path.name}: unreadable PDF ({type(exc).__name__}: {exc})") from exc


def pdf_page_count(path: Path, timeout: float = PDFTOTEXT_TIMEOUT) -> int:
    """Count pages with pdfinfo and (when installed) pypdf; refuse if they disagree.

    pdfinfo trusts the /Count entry, which a crafted file can understate to hide
    pages; pypdf walks the real page tree. Without pypdf the cross-check is skipped.
    """
    n = _page_count_pdfinfo(path, timeout)
    if not _pypdf_available():
        if n is None:
            raise ExtractionError("cannot count PDF pages: neither pdfinfo nor pypdf is available")
        return n
    m = _page_count_pypdf(path)
    if n is not None and n != m:
        raise ExtractionError(f"{path.name}: page counts disagree (pdfinfo {n}, page tree {m}); "
                              "the PDF may be crafted to hide pages")
    return m


def _pdf_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractionError("pypdf is not installed") from exc
    try:
        with _quiet_pypdf():
            reader = PdfReader(str(path))
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ExtractionError(f"{path.name}: more than {MAX_PDF_PAGES} pages")
            return "\n\f\n".join((page.extract_text() or "") for page in reader.pages)
    except ExtractionError:
        raise
    except Exception as exc:  # pypdf raises many types (PdfReadError, ValueError, KeyError...)
        raise ExtractionError(f"{path.name}: unreadable PDF ({type(exc).__name__}: {exc})") from exc


def extract_pdf(path: Path, backend: str = "auto", timeout: float = PDFTOTEXT_TIMEOUT) -> str:
    if path.stat().st_size > MAX_PDF_BYTES:
        raise ExtractionError(f"{path.name}: larger than {MAX_PDF_BYTES // 2**20} MB")
    pages = pdf_page_count(path, timeout)
    if pages > MAX_PDF_PAGES:
        raise ExtractionError(f"{path.name}: {pages} pages; the limit is {MAX_PDF_PAGES} "
                              "(split the PDF; nothing is truncated silently)")
    if backend in ("auto", "pdftotext"):
        try:
            text = _pdf_pdftotext(path, timeout, pages)
            if text.strip() or backend == "pdftotext":
                return text
        except PageMismatchError:
            raise
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
        root = (_SAFE_ET.fromstring(xml, forbid_dtd=True) if _SAFE_ET else ET.fromstring(xml))
    except _DefusedError as exc:
        raise ExtractionError(f"{path.name}: unsafe XML rejected ({type(exc).__name__})") from exc
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
    # page breaks are kept as a lone "\f" line so the splitter can find running headers/footers
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\f\n")
    text = text.replace("\u00a0", " ")
    # de-hyphenate line breaks, but keep compound number words ("twenty-\none" -> "twenty-one")
    text = re.sub(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)-[ \t]*\n[ \t]*(?=[a-z])",
                  r"\1-", text, flags=re.I)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip(" \t") for line in text.split("\n"))
    text = re.sub(r"\n{3,}(?=\f)|(?<=\f)\n{3,}", "\n", text)
    return text.strip() + "\n"
