"""Document parsers.

Standalone helpers for PDF text/image extraction and image OCR. No LLM.
"""
from __future__ import annotations
import base64
import io
from typing import Iterator

import pdfplumber
import fitz  # PyMuPDF
from PIL import Image


# ---------- PDF -------------------------------------------------------------

def pdf_extract_text(pdf_bytes: bytes) -> str:
    """Pure text from a PDF (pdfplumber)."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages).strip()


def pdf_extract_images(pdf_bytes: bytes) -> list[bytes]:
    """All embedded images as PNG bytes."""
    out: list[bytes] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                out.append(pix.tobytes("png"))
    finally:
        doc.close()
    return out


def pdf_rasterize_pages(pdf_bytes: bytes, dpi: int = 200) -> Iterator[bytes]:
    """Yield each page as PNG bytes — used when the PDF has no extractable text."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        for page in doc:
            yield page.get_pixmap(matrix=mat).tobytes("png")
    finally:
        doc.close()


def parse_pdf(pdf_bytes: bytes) -> dict:
    """Combined extraction. Returns:
        {
          'raw_text': str,
          'page_count': int,
          'image_count': int,
          'scanned': bool,
          'images_b64': [str, ...]   # base64 PNGs
        }
    """
    text = pdf_extract_text(pdf_bytes)
    images = pdf_extract_images(pdf_bytes)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    doc.close()
    scanned = len(text) < 30
    if scanned and not images:
        images = list(pdf_rasterize_pages(pdf_bytes))
    return {
        "raw_text": text,
        "page_count": page_count,
        "image_count": len(images),
        "scanned": scanned,
        "images_b64": [base64.b64encode(img).decode() for img in images],
    }


# ---------- Image / OCR ----------------------------------------------------

def ocr_image(image_bytes: bytes) -> str:
    """Best-effort OCR. Returns empty string if Tesseract isn't installed."""
    try:
        import pytesseract  # type: ignore
    except ImportError:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img).strip()
    except Exception:
        return ""


def image_metadata(image_bytes: bytes) -> dict:
    """Basic image stats — width, height, format."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return {"width": img.width, "height": img.height, "format": img.format, "mode": img.mode}
    except Exception:
        return {"width": 0, "height": 0, "format": None, "mode": None}


# ---------- Utility ---------------------------------------------------------

def b64_decode(data: str) -> bytes:
    """Convert any string input to bytes. Handles three formats so the tools
    don't care which one the host sent:
      - http(s):// URL → downloads and returns the bytes
      - data:image/png;base64,XXX → strips the prefix and decodes
      - bare base64 string → decodes directly
    """
    if not data:
        raise ValueError("empty input")
    if data.startswith(("http://", "https://")):
        import urllib.request
        with urllib.request.urlopen(data, timeout=15) as resp:
            return resp.read()
    if data.startswith("data:"):
        data = data.split(",", 1)[1]
    return base64.b64decode(data)
