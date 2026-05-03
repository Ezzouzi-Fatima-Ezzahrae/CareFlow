"""TimelineAgent: ordered, filterable view of a patient's events."""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db import models
from app.schemas import TimelineItem


class TimelineAgent:
    def run(
        self,
        db: Session,
        patient_id: int,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_type: Optional[str] = None,
    ) -> list[TimelineItem]:
        q = db.query(models.Event).filter(models.Event.patient_id == patient_id)
        if since:
            q = q.filter(models.Event.recorded_at >= since)
        if until:
            q = q.filter(models.Event.recorded_at <= until)
        if event_type:
            q = q.filter(models.Event.event_type == event_type)
        events = q.order_by(models.Event.recorded_at.asc()).all()
        return [
            TimelineItem(
                event_id=e.id,
                record_id=e.record_id,
                timestamp=e.recorded_at,
                event_type=e.event_type,
                code=e.code,
                value_text=e.value_text,
                value_num=e.value_num,
                unit=e.unit,
                severity=e.severity,
            )
            for e in events
        ]
