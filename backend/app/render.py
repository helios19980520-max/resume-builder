"""
DOCX -> PDF with whatever is available on this machine, in order of fidelity:
  1. Microsoft Word (Windows, via COM)      - identical to what Word shows
  2. LibreOffice (soffice)                  - very close, uses metric-compatible fonts if MS fonts are absent
  3. nothing                                 -> RenderUnavailable (the app still produces the .docx + ATS score)
Page counts and PNG thumbnails use PyMuPDF (pure wheel, no system dependency).
"""
from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
import sys
import tempfile

from . import config

log = logging.getLogger("render")


class RenderUnavailable(RuntimeError):
    pass


# --------------------------------------------------------------------------- discovery
def find_soffice() -> str | None:
    if config.SOFFICE_BIN and os.path.exists(config.SOFFICE_BIN):
        return config.SOFFICE_BIN
    for name in ("soffice", "libreoffice", "soffice.exe"):
        p = shutil.which(name)
        if p:
            return p
    candidates = []
    if sys.platform.startswith("win"):
        for root in (os.getenv("ProgramFiles", r"C:\Program Files"), os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            candidates += glob.glob(os.path.join(root, "LibreOffice*", "program", "soffice.exe"))
    elif sys.platform == "darwin":
        candidates += ["/Applications/LibreOffice.app/Contents/MacOS/soffice"]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


_word_checked: bool | None = None


def word_available() -> bool:
    global _word_checked
    if _word_checked is not None:
        return _word_checked
    ok = False
    if sys.platform.startswith("win"):
        try:
            import winreg  # type: ignore
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Word.Application")
            ok = True
        except Exception:
            ok = False
    _word_checked = ok
    return ok


def capabilities() -> dict:
    return {"word": word_available(), "libreoffice": find_soffice() is not None}


# --------------------------------------------------------------------------- converters
def _word_to_pdf(docx_path: str, pdf_path: str) -> None:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore
    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(os.path.abspath(docx_path), ReadOnly=True)
        try:
            doc.ExportAsFixedFormat(OutputFileName=os.path.abspath(pdf_path), ExportFormat=17)  # 17 = wdExportFormatPDF
        finally:
            doc.Close(False)
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def _soffice_to_pdf(soffice: str, docx_path: str, out_dir: str) -> str:
    profile = tempfile.mkdtemp(prefix="lo-profile-")
    try:
        cmd = [soffice, "--headless", "--norestore", f"-env:UserInstallation=file:///{profile.replace(os.sep, '/')}" if sys.platform.startswith("win")
               else f"-env:UserInstallation=file://{profile}", "--convert-to", "pdf", "--outdir", out_dir, docx_path]
        subprocess.run(cmd, check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
    if not os.path.exists(pdf):
        raise RuntimeError("LibreOffice produced no PDF")
    return pdf


def docx_to_pdf(docx_path: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
    errors = []
    if word_available():
        try:
            _word_to_pdf(docx_path, pdf)
            return pdf
        except Exception as e:
            errors.append(f"Word: {e}")
            log.warning("Word conversion failed: %s", e)
    soffice = find_soffice()
    if soffice:
        try:
            return _soffice_to_pdf(soffice, docx_path, out_dir)
        except Exception as e:
            errors.append(f"LibreOffice: {e}")
            log.warning("LibreOffice conversion failed: %s", e)
    raise RenderUnavailable("No PDF converter available (install Microsoft Word or LibreOffice). " + "; ".join(errors))


# --------------------------------------------------------------------------- pdf helpers
def pdf_pages(pdf_path: str) -> int:
    try:
        import pymupdf as fitz
        with fitz.open(pdf_path) as d:
            return d.page_count
    except Exception:
        return 0


def pdf_first_page_png(pdf_path: str, png_path: str, zoom: float = 0.7) -> str:
    import pymupdf as fitz
    with fitz.open(pdf_path) as d:
        page = d[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(png_path)
    return png_path


def docx_preview_png(docx_path: str, png_path: str) -> str:
    """Thumbnail of a docx's first page (needs a PDF converter)."""
    tmp = tempfile.mkdtemp(prefix="rb-prev-")
    try:
        pdf = docx_to_pdf(docx_path, tmp)
        return pdf_first_page_png(pdf, png_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
