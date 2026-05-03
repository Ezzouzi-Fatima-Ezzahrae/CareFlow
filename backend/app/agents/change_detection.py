"""ChangeDetectionAgent.

Compares the most recent record's events to the prior record for the same patient.
Numeric diffs are deterministic. The LLM provides risk interpretation on top.
"""
from __future__ import annotations
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.db import models
from app.llm import chat_json


# Thresholds for "moderate" vs "high" change on common vitals/labs.
NUMERIC_THRESHOLDS = {
    "systolic_bp":  {"warn": 10, "high": 20},   # mmHg delta
    "diastolic_bp": {"warn": 5,  "high": 15},
    "heart_rate":   {"warn": 15, "high": 30},
    "HbA1c":        {"warn": 0.3, "high": 0.7},
    "ldl":          {"warn": 20, "high": 40},
    "weight_kg":    {"warn": 3,   "high": 6},
}


class ChangeDetectionAgent:
    def run(
        self,
        db: Session,
        patient_id: int,
        current_record_id: int,
    ) -> Optional[models.Change]:
        prior = (
            db.query(models.Record)
            .filter(
                models.Record.patient_id == patient_id,
                models.Record.id != current_record_id,
                models.Record.status == "processed",
            )
            .order_by(models.Record.created_at.desc())
            .first()
        )
        if not prior:
            return None  # Nothing to compare against yet.

        current_events = self._events_by_code(db, current_record_id)
        prior_events = self._events_by_code(db, prior.id)

        deltas: list[dict] = []
        risk = "low"

        for code, cur in current_events.items():
            if code in prior_events and cur.value_num is not None and prior_events[code].value_num is not None:
                diff = cur.value_num - prior_events[code].value_num
                level = self._score_numeric(code, diff)
                deltas.append({
                    "code": code,
                    "type": "numeric",
                    "from": prior_events[code].value_num,
                    "to": cur.value_num,
                    "unit": cur.unit,
                    "delta": round(diff, 3),
                    "level": level,
                })
                if level == "high":
                    risk = "high"
                elif level == "moderate" and risk == "low":
                    risk = "moderate"

        # Categorical/qualitative deltas via LLM.
        narrative = self._narrative_diff(prior.raw_text or "", _record(db, current_record_id).raw_text or "")
        if narrative:
            deltas.append({"type": "narrative", **narrative})
            if narrative.get("risk") == "high":
                risk = "high"
            elif narrative.get("risk") == "moderate" and risk != "high":
                risk = "moderate"

        change = models.Change(
            patient_id=patient_id,
            from_record_id=prior.id,
            to_record_id=current_record_id,
            delta_json=json.dumps(deltas),
            risk_level=risk,
            notes=narrative.get("notes") if narrative else None,
        )
        db.add(change)
        db.commit()
        db.refresh(change)
        return change

    @staticmethod
    def _events_by_code(db: Session, record_id: int) -> dict[str, models.Event]:
        events = db.query(models.Event).filter(models.Event.record_id == record_id).all()
        return {e.code: e for e in events if e.code}

    @staticmethod
    def _score_numeric(code: str, diff: float) -> str:
        t = NUMERIC_THRESHOLDS.get(code)
        if not t:
            return "info"
        a = abs(diff)
        if a >= t["high"]:
            return "high"
        if a >= t["warn"]:
            return "moderate"
        return "low"

    @staticmethod
    def _narrative_diff(prior_text: str, current_text: str) -> dict:
        if not prior_text or not current_text:
            return {}
        system = (
            "You compare two clinical notes for the same patient over time. "
            "Return JSON: {risk: 'low|moderate|high', notes: 'short clinical interpretation', "
            "new_issues: [strings], resolved_issues: [strings]}. Be conservative."
        )
        user = f"PRIOR NOTE:\n{prior_text[:4000]}\n\nCURRENT NOTE:\n{current_text[:4000]}"
        try:
            data = json.loads(chat_json(system, user))
            if data.get("stub"):
                return {}
            return data
        except json.JSONDecodeError:
            return {}


def _record(db: Session, record_id: int) -> models.Record:
    return db.query(models.Record).get(record_id)
