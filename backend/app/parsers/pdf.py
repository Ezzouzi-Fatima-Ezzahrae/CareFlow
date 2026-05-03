"""PDF parsing: text via pdfplumber, embedded images via PyMuPDF.

Falls back to rasterizing pages if the PDF has < 30 chars of text (likely scanned).
"""
from __future__ import annotations
import io
from typing import Iterable

import pdfplumber
import fitz  # PyMuPDF


def extract_text(file_path: str) -> str:
    chunks: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def extract_embedded_images(file_path: str) -> list[bytes]:
    """Return PNG-encoded bytes for every embedded image in the PDF."""
    out: list[bytes] = []
    doc = fitz.open(file_path)
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            for img in page.get_images(full=True):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:  # CMYK → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                out.append(pix.tobytes("png"))
    finally:
        doc.close()
    return out


def rasterize_pages(file_path: str, dpi: int = 200) -> Iterable[bytes]:
    """Yield each page as PNG bytes — used when PDF is image-only."""
    doc = fitz.open(file_path)
    try:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            yield pix.tobytes("png")
    finally:
        doc.close()


def parse_pdf(file_path: str) -> dict:
    """Returns {raw_text, images: list[bytes], scanned: bool}."""
    text = extract_text(file_path)
    images = extract_embedded_images(file_path)
    scanned = len(text) < 30
    if scanned and not images:
        images = list(rasterize_pages(file_path))
    return {"raw_text": text, "images": images, "scanned": scanned}
