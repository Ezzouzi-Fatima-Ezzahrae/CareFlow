"""Deterministic clinical-event extractor.

Pulls vitals, labs, diagnoses, and medications out of free-text using regex.
No LLM required. Built to handle real-world clinical document shapes
(discharge notes, lab printouts, radiology reports).
"""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class ClinicalEvent:
    event_type: str           # 'vital' | 'diagnosis' | 'medication' | 'lab' | 'note' | 'imaging'
    code: str | None = None
    value_text: str | None = None
    value_num: float | None = None
    unit: str | None = None
    severity: str = "info"    # 'info' | 'warn' | 'critical'
    recorded_at: str | None = None  # ISO8601

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Severity thresholds (best-effort, conservative)
# ---------------------------------------------------------------------------

# (warn_threshold, critical_threshold). Direction handled per-code in _severity.
THRESHOLDS: dict[str, tuple[float, float]] = {
    "systolic_bp":     (140, 160),
    "diastolic_bp":    (90, 100),
    "heart_rate":      (100, 130),
    "spo2":            (92, 88),    # lower-is-worse
    "HbA1c":           (7.0, 9.0),
    "fasting_glucose": (125, 200),
    "glucose":         (140, 250),
    "ldl":             (130, 190),
    "creatinine":      (1.3, 2.0),
    "egfr":            (60, 30),    # lower-is-worse
    "bnp":             (100, 400),
    "troponin":        (0.04, 0.4),
}
LOWER_IS_WORSE = {"spo2", "egfr"}


def _severity(code: str, value: float) -> str:
    if code not in THRESHOLDS:
        return "info"
    a, b = THRESHOLDS[code]
    if code in LOWER_IS_WORSE:
        if value <= b:
            return "critical"
        if value <= a:
            return "warn"
        return "info"
    if value >= b:
        return "critical"
    if value >= a:
        return "warn"
    return "info"


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# (code, regex, unit, event_type)
NUMERIC_PATTERNS: list[tuple[str, str, str, str]] = [
    ("heart_rate",        r"\b(?:heart\s*rate|HR|pulse)[\s:]*(\d{2,3})\b",                  "bpm",            "vital"),
    ("resp_rate",         r"\b(?:resp(?:iratory)?\s*rate|RR)[\s:]*(\d{1,2})\b",             "/min",           "vital"),
    ("spo2",              r"\b(?:SpO2|oxygen\s*saturation|O2\s*sat)[\s:]*(\d{2,3})\s*%?",   "%",              "vital"),
    ("temperature_c",     r"\b(?:temp(?:erature)?)[\s:]*(\d{2}\.?\d?)\s*°?\s*C\b",          "°C",             "vital"),
    ("weight_kg",         r"\b(?:weight)[\s:]*(\d{2,3}\.?\d?)\s*kg\b",                       "kg",             "vital"),
    ("bmi",               r"\bBMI[\s:]*(\d{1,2}\.?\d?)\b",                                    "kg/m²",          "vital"),
    ("HbA1c",             r"\bHbA1c[\s:]*(\d{1,2}\.\d)\s*%?",                                "%",              "lab"),
    ("fasting_glucose",   r"\b(?:fasting\s*glucose|FBG|FPG)[\s:]*(\d{2,3})\b",               "mg/dL",          "lab"),
    ("glucose",           r"\b(?:glucose|blood\s*sugar)[\s:]*(\d{2,3})\s*mg/?dL\b",          "mg/dL",          "lab"),
    ("ldl",               r"\bLDL[\s\w]*?(\d{2,3})\s*mg/?dL\b",                              "mg/dL",          "lab"),
    ("hdl",               r"\bHDL[\s\w]*?(\d{1,3})\s*mg/?dL\b",                              "mg/dL",          "lab"),
    ("total_cholesterol", r"\b(?:total\s*cholesterol|cholesterol\s*total)[\s:]*(\d{2,3})\s*mg/?dL\b", "mg/dL", "lab"),
    ("triglycerides",     r"\btriglycerides[\s:]*(\d{2,4})\s*mg/?dL\b",                      "mg/dL",          "lab"),
    ("creatinine",        r"\bcreatinine[\s:]*(\d\.\d)\s*mg/?dL\b",                          "mg/dL",          "lab"),
    ("egfr",              r"\beGFR[\s:]*(\d{1,3})\b",                                        "mL/min/1.73m²",  "lab"),
    ("bun",               r"\bBUN[\s:]*(\d{1,3})\s*mg/?dL\b",                                "mg/dL",          "lab"),
    ("bnp",               r"\bBNP[\s:]*(\d{1,4})\s*pg/?mL\b",                                "pg/mL",          "lab"),
    ("troponin",          r"\btroponin[\s\w]*?(\d\.\d{1,3})\s*ng/?mL\b",                     "ng/mL",          "lab"),
    ("potassium",         r"\bpotassium[\s:]*(\d\.\d)\s*mmol/?L\b",                          "mmol/L",         "lab"),
    ("sodium",            r"\bsodium[\s:]*(\d{2,3})\s*mmol/?L\b",                            "mmol/L",         "lab"),
    ("hemoglobin",        r"\bhemoglobin[\s:]*(\d{1,2}\.\d)\s*g/?dL\b",                      "g/dL",           "lab"),
]

ICD10_PATTERN = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,3})?)\b")

DIAGNOSIS_HINTS: list[tuple[str, str]] = [
    ("hypertension",          "Hypertension"),
    ("diabetes",              "Type 2 diabetes mellitus"),
    ("heart failure",         "Heart failure"),
    ("chronic kidney disease", "Chronic kidney disease"),
    ("hyperlipidemia",        "Hyperlipidemia"),
    ("dyslipidemia",          "Dyslipidemia"),
    ("atrial fibrillation",   "Atrial fibrillation"),
    ("asthma",                "Asthma"),
    ("copd",                  "COPD"),
    ("myocardial infarction", "Myocardial infarction"),
    ("stroke",                "Stroke"),
]

MEDICATIONS = [
    "lisinopril", "metformin", "amlodipine", "atorvastatin", "metoprolol",
    "furosemide", "aspirin", "insulin", "glargine", "warfarin", "apixaban",
    "rivaroxaban", "clopidogrel", "losartan", "simvastatin", "rosuvastatin",
    "hydrochlorothiazide", "carvedilol", "spironolactone", "ramipril",
    "enalapril", "valsartan", "candesartan", "ezetimibe", "empagliflozin",
    "dapagliflozin", "semaglutide", "liraglutide",
]
MED_DOSE_PATTERN = re.compile(
    r"\b(?P<drug>" + "|".join(MEDICATIONS) + r")\b[\s\w]*?(?P<dose>\d{1,4}\s*(?:mg|mcg|units))",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_recorded_at(text: str) -> str | None:
    """Latest plausible date in the document, ISO8601 string. Returns None if not found."""
    candidates: list[datetime] = []
    for m in re.finditer(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text):
        try:
            candidates.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    for m in re.finditer(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text):
        try:
            candidates.append(datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))))
        except ValueError:
            pass
    if not candidates:
        return None
    return max(candidates).isoformat()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_events(text: str, *, recorded_at: str | None = None) -> list[ClinicalEvent]:
    """Extract clinical events from free-text. Pure function, no LLM."""
    out: list[ClinicalEvent] = []
    seen_codes: set[str] = set()
    if not text or not text.strip():
        return out
    when = recorded_at or find_recorded_at(text)

    # 1. Blood pressure (systolic/diastolic, one pattern).
    for m in re.finditer(r"\b(\d{2,3})\s*/\s*(\d{2,3})\s*mmHg\b", text):
        sys_v, dia_v = float(m.group(1)), float(m.group(2))
        if "systolic_bp" not in seen_codes:
            out.append(ClinicalEvent("vital", "systolic_bp", value_num=sys_v, unit="mmHg",
                                     severity=_severity("systolic_bp", sys_v), recorded_at=when))
            seen_codes.add("systolic_bp")
        if "diastolic_bp" not in seen_codes:
            out.append(ClinicalEvent("vital", "diastolic_bp", value_num=dia_v, unit="mmHg",
                                     severity=_severity("diastolic_bp", dia_v), recorded_at=when))
            seen_codes.add("diastolic_bp")

    # 2. Numeric vitals + labs.
    for code, pattern, unit, kind in NUMERIC_PATTERNS:
        if code in seen_codes:
            continue
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except (TypeError, ValueError):
            continue
        out.append(ClinicalEvent(kind, code, value_num=val, unit=unit,
                                 severity=_severity(code, val), recorded_at=when))
        seen_codes.add(code)

    # 3. Diagnoses by ICD-10 code.
    for m in ICD10_PATTERN.finditer(text):
        code = m.group(1)
        if any(e.code == code for e in out):
            continue
        start = max(0, m.start() - 60)
        ctx = text[start:m.end() + 20].replace("\n", " ").strip()
        out.append(ClinicalEvent("diagnosis", code=code, value_text=ctx, recorded_at=when))

    # 4. Diagnoses by keyword (fallback when no ICD code appears).
    low = text.lower()
    for keyword, label in DIAGNOSIS_HINTS:
        if keyword in low:
            already = any(label.lower() in (e.value_text or "").lower() for e in out)
            if not already:
                out.append(ClinicalEvent("diagnosis", code=None, value_text=label, recorded_at=when))

    # 5. Medications with doses.
    seen_meds: set[str] = set()
    for m in MED_DOSE_PATTERN.finditer(text):
        drug = m.group("drug").lower()
        if drug in seen_meds:
            continue
        seen_meds.add(drug)
        out.append(ClinicalEvent("medication", code=drug,
                                 value_text=f"{drug} {m.group('dose')}", recorded_at=when))

    return out
