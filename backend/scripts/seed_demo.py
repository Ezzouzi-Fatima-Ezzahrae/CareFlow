"""Seed demo data so the dashboard has interesting content for the judges.

Run after the DB is initialized:
    python -m scripts.seed_demo

It creates one synthetic patient ("Sarah Mansouri") with three records spaced
over 6 months — a discharge note, a lab report, and a recent follow-up.
The records are written as text so the pipeline runs the same way it would
for real uploads (no API key needed; it falls back to the stub agent and
seeds events directly so the demo still has content).
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta

# Allow running with `python scripts/seed_demo.py` from the backend folder.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.db.session import Base, engine, SessionLocal  # noqa: E402
from app.db import models  # noqa: E402

Base.metadata.create_all(bind=engine)


# --- Synthetic patient + records -----------------------------------------

PATIENT = {
    "external_id": "MRN-DEMO-001",
    "name": "Sarah Mansouri",
    "gender": "F",
    "dob": datetime(1968, 4, 12).date(),
}

NOW = datetime.utcnow()

DEMO_RECORDS = [
    {
        "label": "Discharge note — Cardiology, 6 months ago",
        "recorded_at": NOW - timedelta(days=180),
        "raw_text": (
            "DISCHARGE SUMMARY — Cardiology Service\n"
            "Patient presented with hypertensive urgency. BP 162/98 mmHg on admission.\n"
            "Diagnoses: Essential hypertension (I10), Type 2 diabetes mellitus (E11.9).\n"
            "Labs: HbA1c 7.4%, LDL 138 mg/dL.\n"
            "Discharged on lisinopril 10 mg daily and metformin 500 mg BID.\n"
        ),
        "events": [
            {"event_type": "vital", "code": "systolic_bp",  "value_num": 162, "unit": "mmHg", "severity": "warn"},
            {"event_type": "vital", "code": "diastolic_bp", "value_num": 98,  "unit": "mmHg", "severity": "warn"},
            {"event_type": "diagnosis", "code": "I10",   "value_text": "Essential hypertension"},
            {"event_type": "diagnosis", "code": "E11.9", "value_text": "Type 2 diabetes mellitus"},
            {"event_type": "lab", "code": "HbA1c", "value_num": 7.4,  "unit": "%",      "severity": "warn"},
            {"event_type": "lab", "code": "ldl",   "value_num": 138,  "unit": "mg/dL",  "severity": "warn"},
            {"event_type": "medication", "code": "lisinopril",  "value_text": "10 mg PO daily"},
            {"event_type": "medication", "code": "metformin",   "value_text": "500 mg PO BID"},
        ],
    },
    {
        "label": "Lab report — 3 months ago",
        "recorded_at": NOW - timedelta(days=90),
        "raw_text": (
            "OUTPATIENT LABS\n"
            "HbA1c: 7.8%  (prior 7.4%)\n"
            "LDL:   146 mg/dL\n"
            "Fasting glucose: 162 mg/dL\n"
            "Notes: glycemic control trending worse. Consider intensification.\n"
        ),
        "events": [
            {"event_type": "lab", "code": "HbA1c",          "value_num": 7.8, "unit": "%",     "severity": "warn"},
            {"event_type": "lab", "code": "ldl",            "value_num": 146, "unit": "mg/dL", "severity": "warn"},
            {"event_type": "lab", "code": "fasting_glucose","value_num": 162, "unit": "mg/dL", "severity": "warn"},
        ],
    },
    {
        "label": "Follow-up note — last week",
        "recorded_at": NOW - timedelta(days=7),
        "raw_text": (
            "FOLLOW-UP — Endocrinology\n"
            "BP today: 156/96 mmHg (still elevated despite lisinopril).\n"
            "HbA1c: 8.3% — worsening.\n"
            "Patient reports occasional chest tightness on exertion. ECG ordered.\n"
            "Plan: add amlodipine 5 mg, increase metformin to 1000 mg BID, refer to cardiology.\n"
        ),
        "events": [
            {"event_type": "vital", "code": "systolic_bp",  "value_num": 156, "unit": "mmHg", "severity": "warn"},
            {"event_type": "vital", "code": "diastolic_bp", "value_num": 96,  "unit": "mmHg", "severity": "warn"},
            {"event_type": "lab",   "code": "HbA1c",        "value_num": 8.3, "unit": "%",    "severity": "critical"},
            {"event_type": "medication", "code": "amlodipine", "value_text": "5 mg PO daily"},
            {"event_type": "medication", "code": "metformin",  "value_text": "1000 mg PO BID"},
            {"event_type": "note", "code": None, "value_text": "Chest tightness on exertion — ECG ordered"},
        ],
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        # Idempotent: skip if already seeded.
        existing = db.query(models.Patient).filter_by(external_id=PATIENT["external_id"]).first()
        if existing:
            print(f"Patient {PATIENT['external_id']} already exists (id={existing.id}). Skipping.")
            return

        patient = models.Patient(**PATIENT)
        db.add(patient)
        db.commit()
        db.refresh(patient)
        print(f"Created patient #{patient.id}: {patient.name}")

        for entry in DEMO_RECORDS:
            record = models.Record(
                patient_id=patient.id,
                source_type="text",
                file_path=None,
                raw_text=entry["raw_text"],
                status="processed",
                recorded_at=entry["recorded_at"],
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            for ev in entry["events"]:
                db.add(models.Event(
                    patient_id=patient.id,
                    record_id=record.id,
                    recorded_at=entry["recorded_at"],
                    severity=ev.get("severity", "info"),
                    **{k: v for k, v in ev.items() if k != "severity"},
                ))
            db.commit()
            print(f"  + record #{record.id} — {entry['label']}  ({len(entry['events'])} events)")

        # Manually create a "change" row so the dashboard shows risk on first load.
        first = db.query(models.Record).filter_by(patient_id=patient.id).order_by(models.Record.recorded_at.asc()).first()
        last  = db.query(models.Record).filter_by(patient_id=patient.id).order_by(models.Record.recorded_at.desc()).first()
        change = models.Change(
            patient_id=patient.id,
            from_record_id=first.id,
            to_record_id=last.id,
            risk_level="high",
            notes="HbA1c trending up (7.4 → 8.3) and BP remains uncontrolled despite lisinopril. New exertional chest tightness — refer to cardiology.",
            delta_json='[{"type":"numeric","code":"HbA1c","from":7.4,"to":8.3,"unit":"%","delta":0.9,"level":"high"},'
                       '{"type":"numeric","code":"systolic_bp","from":162,"to":156,"unit":"mmHg","delta":-6,"level":"low"},'
                       '{"type":"numeric","code":"ldl","from":138,"to":146,"unit":"mg/dL","delta":8,"level":"low"}]',
        )
        db.add(change)
        db.commit()
        print(f"  + change #{change.id} — risk=high")

        print("\nDemo data ready. Open http://127.0.0.1:8000")
    finally:
        db.close()


if __name__ == "__main__":
    main()
