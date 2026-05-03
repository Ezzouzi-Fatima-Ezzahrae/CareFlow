"""MemoryAgent: persists a StructuredRecord as Events tied to a Record."""
from __future__ import annotations
from datetime import datetime

from sqlalchemy.orm import Session

from app.db import models
from app.schemas import StructuredRecord


class MemoryAgent:
    def run(
        self,
        db: Session,
        record: models.Record,
        structured: StructuredRecord,
    ) -> list[int]:
        # Prefer the document-level recorded_at if the record didn't already have one.
        if structured.recorded_at and not record.recorded_at:
            record.recorded_at = structured.recorded_at

        record.structured_json = structured.model_dump_json()
        record.status = "processed"

        event_ids: list[int] = []
        for ev in structured.events:
            db_event = models.Event(
                patient_id=record.patient_id,
                record_id=record.id,
                event_type=ev.event_type,
                code=ev.code,
                value_text=ev.value_text,
                value_num=ev.value_num,
                unit=ev.unit,
                severity=ev.severity,
                recorded_at=ev.recorded_at or record.recorded_at or datetime.utcnow(),
            )
            db.add(db_event)
            db.flush()
            event_ids.append(db_event.id)

        db.commit()
        return event_ids
