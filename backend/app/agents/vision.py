"""VisionAgent: describes medical images and pulls OCR text via the vision LLM."""
from __future__ import annotations
import json

from app.llm import vision_describe


VISION_PROMPT = (
    "You are a clinical assistant. Look at this medical image and return JSON with keys: "
    "modality (e.g. 'chest_xray', 'derm_photo', 'lab_printout', 'prescription_scan'), "
    "body_region (string|null), findings (list of short strings), "
    "ocr_text (string — any printed/handwritten text), urgent (boolean). "
    "Be conservative; say 'unclear' rather than guess."
)


class VisionAgent:
    def run(self, image_bytes: bytes, context: str | None = None) -> dict:
        prompt = VISION_PROMPT
        if context:
            prompt += f"\nContext: {context}"
        raw = vision_describe(image_bytes, prompt)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"description": raw, "ocr_text": "", "findings": []}
        return data
