"""StructuringAgent: turn raw clinical text into typed events.

Two paths:
  1. Primary — LLM extraction via chat_json (Gemini / OpenAI).
  2. Fallback — deterministic regex extractor (no LLM needed).

The fallback runs whenever the LLM is unavailable (no key, quota exhausted,
404 on model name, etc.) so the pipeline keeps producing real events.
"""
from __future__ import annotations
import json
import re
from datetime import datetime
from typing import Iterable

from pydantic import ValidationError

from app.llm import chat_json
from app.schemas import ClinicalEvent, StructuredRecord


SYSTEM = (
    "You are a medical information extractor. Read the document and return strictly valid JSON "
    "matching this schema:\n"
    "{\n"
    '  "recorded_at": "ISO8601 datetime or null",\n'
    '  "summary": "one-line summary",\n'
    '  "events": [\n'
    "    {\n"
    '      "event_type": "vital|diagnosis|medication|lab|note|imaging",\n'
    '      "code": "short slug (e.g. systolic_bp, HbA1c, ICD-10) or null",\n'
    '      "value_text": "string or null",\n'
    '      "value_num": number or null,\n'
    '      "unit": "string or null",\n'
    '      "severity": "info|warn|critical",\n'
    '      "recorded_at": "ISO8601 datetime or null"\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Rules: numeric vitals/labs MUST populate value_num and unit. Use 'critical' only for clearly "
    "abnormal results. If you cannot extract anything, return events: []."
)


class StructuringAgent:
    def run(self, raw_text: str, vision_output: dict | None = None) -> StructuredRecord:
        user = f"DOCUMENT TEXT:\n{raw_text or '(empty)'}\n"
        if vision_output:
            user += f"\nVISION FINDINGS:\n{json.dumps(vision_output, ensure_ascii=False)}\n"

        raw = chat_json(SYSTEM, user)
        parsed = self._parse(raw)

        # If the LLM didn't extract anything OR returned a stub, fall back to
        # deterministic regex extraction over the raw text.
        if not parsed.events:
            fallback_events = list(_regex_extract(raw_text or "", vision_output))
            if fallback_events:
                parsed = StructuredRecord(
                    recorded_at=parsed.recorded_at or _find_recorded_at(raw_text or ""),
                    summary=parsed.summary or "Extracted via deterministic fallback (no LLM).",
                    events=fallback_events,
                )

        return parsed

    @staticmethod
    def _parse(raw: str) -> StructuredRecord:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return StructuredRecord(events=[])
        if data.get("stub"):
            return StructuredRecord(events=[])
        try:
            return StructuredRecord.model_validate(data)
        except ValidationError:
            return StructuredRecord(summary=data.get("summary"), events=[])


# ===========================================================================
# Regex fallback — deterministic, no LLM
# ===========================================================================

def _find_recorded_at(text: str) -> datetime | None:
    """Find a plausible event date in the document. Looks for ISO and US-ish dates."""
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
    # Prefer the latest plausible date (most recent event).
    return max(candidates)


# ----- patterns ------------------------------------------------------------
# Each entry: code, regex (group 1 = numeric value), unit, severity_func.
NUMERIC_PATTERNS: list[tuple[str, str, str, str | None]] = [
    # Vitals — BP is special (handled separately below).
    ("heart_rate",      r"\b(?:heart\s*rate|HR|pulse)[\s:]*(\d{2,3})\b",                 "bpm",          "vital"),
    ("resp_rate",       r"\b(?:resp(?:iratory)?\s*rate|RR)[\s:]*(\d{1,2})\b",            "/min",         "vital"),
    ("spo2",            r"\b(?:SpO2|oxygen\s*saturation|O2\s*sat)[\s:]*(\d{2,3})\s*%?",  "%",            "vital"),
    ("temperature_c",   r"\b(?:temp(?:erature)?)[\s:]*(\d{2}\.?\d?)\s*°?\s*C\b",         "°C",           "vital"),
    ("weight_kg",       r"\b(?:weight)[\s:]*(\d{2,3}\.?\d?)\s*kg\b",                     "kg",           "vital"),
    ("bmi",             r"\bBMI[\s:]*(\d{1,2}\.?\d?)\b",                                  "kg/m²",        "vital"),
    # Labs.
    ("HbA1c",           r"\bHbA1c[\s:]*(\d{1,2}\.\d)\s*%?",                              "%",            "lab"),
    ("fasting_glucose", r"\b(?:fasting\s*glucose|FBG|FPG)[\s:]*(\d{2,3})\b",             "mg/dL",        "lab"),
    ("glucose",         r"\b(?:glucose|blood\s*sugar)[\s:]*(\d{2,3})\s*mg/?dL\b",        "mg/dL",        "lab"),
    ("ldl",             r"\bLDL[\s\w]*?(\d{2,3})\s*mg/?dL\b",                            "mg/dL",        "lab"),
    ("hdl",             r"\bHDL[\s\w]*?(\d{1,3})\s*mg/?dL\b",                            "mg/dL",        "lab"),
    ("total_cholesterol", r"\b(?:total\s*cholesterol|cholesterol\s*total)[\s:]*(\d{2,3})\s*mg/?dL\b", "mg/dL", "lab"),
    ("triglycerides",   r"\btriglycerides[\s:]*(\d{2,4})\s*mg/?dL\b",                    "mg/dL",        "lab"),
    ("creatinine",      r"\bcreatinine[\s:]*(\d\.\d)\s*mg/?dL\b",                        "mg/dL",        "lab"),
    ("egfr",            r"\beGFR[\s:]*(\d{1,3})\b",                                      "mL/min/1.73m²","lab"),
    ("bun",             r"\bBUN[\s:]*(\d{1,3})\s*mg/?dL\b",                              "mg/dL",        "lab"),
    ("bnp",             r"\bBNP[\s:]*(\d{1,4})\s*pg/?mL\b",                              "pg/mL",        "lab"),
    ("troponin",        r"\btroponin[\s\w]*?(\d\.\d{1,3})\s*ng/?mL\b",                   "ng/mL",        "lab"),
    ("potassium",       r"\bpotassium[\s:]*(\d\.\d)\s*mmol/?L\b",                        "mmol/L",       "lab"),
    ("sodium",          r"\bsodium[\s:]*(\d{2,3})\s*mmol/?L\b",                          "mmol/L",       "lab"),
    ("hemoglobin",      r"\bhemoglobin[\s:]*(\d{1,2}\.\d)\s*g/?dL\b",                    "g/dL",         "lab"),
]

# Severity thresholds (best-effort, conservative).
THRESHOLDS = {
    "systolic_bp":  ((140, 160), "warn", "critical"),
    "diastolic_bp": ((90, 100),  "warn", "critical"),
    "heart_rate":   ((100, 130), "warn", "critical"),
    "spo2":         ((92, 88),   "warn", "critical"),  # lower-is-worse handled below
    "HbA1c":        ((7.0, 9.0), "warn", "critical"),
    "fasting_glucose": ((125, 200), "warn", "critical"),
    "glucose":      ((140, 250), "warn", "critical"),
    "ldl":          ((130, 190), "warn", "critical"),
    "creatinine":   ((1.3, 2.0), "warn", "critical"),
    "egfr":         ((60, 30),   "warn", "critical"),  # lower-is-worse
    "bnp":          ((100, 400), "warn", "critical"),
}


def _severity(code: str, value: float) -> str:
    if code not in THRESHOLDS:
        return "info"
    (a, b), warn_label, crit_label = THRESHOLDS[code]
    # Lower-is-worse codes:
    if code in ("spo2", "egfr"):
        if value <= b:
            return crit_label
        if value <= a:
            return warn_label
        return "info"
    # Higher-is-worse:
    if value >= b:
        return crit_label
    if value >= a:
        return warn_label
    return "info"


# Common ICD-10 prefixes we look for explicitly.
ICD10_PATTERN = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,3})?)\b")
DIAGNOSIS_HINTS = [
    ("hypertension",        "hypertension"),
    ("diabetes",            "type 2 diabetes mellitus"),
    ("heart failure",       "heart failure"),
    ("chronic kidney disease", "chronic kidney disease"),
    ("hyperlipidemia",      "hyperlipidemia"),
    ("dyslipidemia",        "dyslipidemia"),
    ("atrial fibrillation", "atrial fibrillation"),
    ("asthma",              "asthma"),
    ("copd",                "COPD"),
]

MEDICATIONS = [
    "lisinopril", "metformin", "amlodipine", "atorvastatin", "metoprolol",
    "furosemide", "aspirin", "insulin", "glargine", "warfarin", "apixaban",
    "rivaroxaban", "clopidogrel", "losartan", "simvastatin", "rosuvastatin",
    "hydrochlorothiazide", "carvedilol", "spironolactone", "ramipril",
    "enalapril", "valsartan", "candesartan",
]
MED_DOSE = re.compile(
    r"\b(?P<drug>" + "|".join(MEDICATIONS) + r")\b[\s\w]*?(?P<dose>\d{1,4}\s*(?:mg|mcg|units))",
    re.IGNORECASE,
)


def _regex_extract(text: str, vision_output: dict | None) -> Iterable[ClinicalEvent]:
    """Pull events out of plain text using regex. Best-effort, no LLM."""
    out: list[ClinicalEvent] = []
    seen_codes: set[str] = set()

    if not text and vision_output:
        text = (vision_output.get("ocr_text") or "") + "\n" + (vision_output.get("description") or "")

    if not text.strip():
        return out

    # 1. Blood pressure (systolic/diastolic in one pattern).
    for m in re.finditer(r"\b(\d{2,3})\s*/\s*(\d{2,3})\s*mmHg\b", text):
        sys_v, dia_v = float(m.group(1)), float(m.group(2))
        if "systolic_bp" not in seen_codes:
            out.append(ClinicalEvent(
                event_type="vital", code="systolic_bp",
                value_num=sys_v, unit="mmHg",
                severity=_severity("systolic_bp", sys_v),
            ))
            seen_codes.add("systolic_bp")
        if "diastolic_bp" not in seen_codes:
            out.append(ClinicalEvent(
                event_type="vital", code="diastolic_bp",
                value_num=dia_v, unit="mmHg",
                severity=_severity("diastolic_bp", dia_v),
            ))
            seen_codes.add("diastolic_bp")

    # 2. Numeric vitals/labs.
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
        out.append(ClinicalEvent(
            event_type=kind or "lab",
            code=code,
            value_num=val,
            unit=unit,
            severity=_severity(code, val),
        ))
        seen_codes.add(code)

    # 3. Diagnoses — ICD-10 codes.
    for m in ICD10_PATTERN.finditer(text):
        code = m.group(1)
        # surrounding context (~80 chars) for human-readable label
        start = max(0, m.start() - 80)
        ctx = text[start:m.end() + 20].replace("\n", " ")
        if any(e.code == code for e in out):
            continue
        out.append(ClinicalEvent(
            event_type="diagnosis", code=code, value_text=ctx.strip(),
            severity="info",
        ))

    # 4. Diagnoses — keyword fallback.
    low = text.lower()
    for keyword, label in DIAGNOSIS_HINTS:
        if keyword in low and not any((e.value_text or "").lower().find(keyword) >= 0 for e in out):
            out.append(ClinicalEvent(
                event_type="diagnosis", code=None, value_text=label.title(),
                severity="info",
            ))

    # 5. Medications with doses.
    seen_meds: set[str] = set()
    for m in MED_DOSE.finditer(text):
        drug = m.group("drug").lower()
        dose = m.group("dose")
        if drug in seen_meds:
            continue
        seen_meds.add(drug)
        out.append(ClinicalEvent(
            event_type="medication", code=drug,
            value_text=f"{drug} {dose}",
            severity="info",
        ))

    # 6. Imaging finding from vision output, if any.
    if vision_output:
        findings = vision_output.get("findings") or []
        if findings:
            out.append(ClinicalEvent(
                event_type="imaging",
                code=vision_output.get("modality"),
                value_text="; ".join(findings)[:500],
                severity="warn" if vision_output.get("urgent") else "info",
            ))

    return out
