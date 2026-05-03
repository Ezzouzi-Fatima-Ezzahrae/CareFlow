"""Heuristic medical-image analysis. No LLM.

Extracts OCR text from medical images and uses keyword matching to guess
modality (CXR, lab printout, prescription, etc.) and pull plausible findings.
"""
from __future__ import annotations
import re

from .parsers import ocr_image, image_metadata


MODALITY_HINTS: list[tuple[str, str]] = [
    ("chest x-ray",      "chest_xray"),
    ("cxr",              "chest_xray"),
    ("radiology",        "radiology"),
    ("ecg",              "ecg"),
    ("ekg",              "ecg"),
    ("electrocardiogram","ecg"),
    ("ct scan",          "ct"),
    ("mri",              "mri"),
    ("ultrasound",       "ultrasound"),
    ("dermat",           "dermatology"),
    ("prescription",     "prescription_scan"),
    ("rx",               "prescription_scan"),
    ("laboratory",       "lab_printout"),
    ("lab report",       "lab_printout"),
]

URGENT_HINTS = [
    "consolidation", "pneumothorax", "infarct", "hemorrhage", "embolism",
    "stroke", "tumor", "fracture", "rupture", "perforation",
    "consistent with hf", "decompensated", "tachycardia",
]

FINDING_HINTS = [
    "cardiomegaly", "pulmonary congestion", "consolidation", "effusion",
    "pneumothorax", "kerley b lines", "edema", "infiltrate", "opacity",
    "atelectasis", "nodule", "mass", "fracture", "calcification",
    "hyperinflation", "infiltration",
]


def analyze_image(image_bytes: bytes, *, context: str = "") -> dict:
    """Run OCR and heuristics. Returns:
        {
          modality, body_region, ocr_text, findings: [str],
          urgent: bool, dimensions: {width,height,format}, char_count
        }
    """
    ocr = ocr_image(image_bytes)
    blob = (ocr + "\n" + (context or "")).lower()
    meta = image_metadata(image_bytes)

    # Modality
    modality = "unknown"
    for needle, label in MODALITY_HINTS:
        if needle in blob:
            modality = label
            break

    # Findings
    findings: list[str] = []
    for f in FINDING_HINTS:
        if f in blob and f not in findings:
            findings.append(f)

    # Urgency
    urgent = any(h in blob for h in URGENT_HINTS)

    # Body region: only set if we matched a modality.
    body_region = None
    if modality in ("chest_xray", "ecg"):
        body_region = "chest"
    elif modality in ("ct", "mri", "ultrasound"):
        body_region = "unspecified"
    elif modality == "dermatology":
        body_region = "skin"

    return {
        "modality": modality,
        "body_region": body_region,
        "ocr_text": ocr,
        "findings": findings,
        "urgent": urgent,
        "char_count": len(ocr),
        "dimensions": meta,
    }
