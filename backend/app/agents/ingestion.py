"""IngestionAgent: dispatches to the right parser based on source type."""
from __future__ import annotations
from typing import Literal

from app.parsers import text as text_parser
from app.parsers import pdf as pdf_parser
from app.parsers import image as image_parser

SourceType = Literal["text", "pdf", "image"]


class IngestionAgent:
    def run(self, file_path: str, source_type: SourceType) -> dict:
        if source_type == "text":
            return {"raw_text": text_parser.parse_text(file_path), "images": []}
        if source_type == "pdf":
            return pdf_parser.parse_pdf(file_path)
        if source_type == "image":
            img_bytes = image_parser.read_image_bytes(file_path)
            return {
                "raw_text": image_parser.ocr_image(img_bytes),
                "images": [img_bytes],
            }
        raise ValueError(f"Unsupported source_type: {source_type}")
