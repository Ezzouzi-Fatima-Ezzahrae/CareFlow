"""OCR for images. Tesseract for cheap path; vision LLM is called from VisionAgent."""
from __future__ import annotations
import io

from PIL import Image


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


def read_image_bytes(file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        return f.read()
