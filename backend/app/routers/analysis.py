"""Timeline, changes, and summary endpoints."""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.summary import SummaryAgent
from app.agents.timeline import TimelineAgent
from app.db import models
from app.db.session import get_db
from app.schemas import ChangeOut, SummaryOut, SummaryRequest, TimelineItem

router = APIRouter(prefix="/patients/{patient_id}", tags=["analysis"])
timeline_agent = TimelineAgent()
summary_agent = SummaryAgent()


@router.get("/timeline", response_model=list[TimelineItem])
def get_timeline(
    patient_id: int,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    event_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if not db.query(models.Patient).get(patient_id):
        raise HTTPException(404, "Patient not found")
    return timeline_agent.run(db, patient_id, since=since, until=until, event_type=event_type)


@router.get("/changes", response_model=list[ChangeOut])
def get_changes(patient_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Change)
        .filter(models.Change.patient_id == patient_id)
        .order_by(models.Change.created_at.desc())
        .all()
    )


@router.post("/summary", response_model=SummaryOut)
def generate_summary(
    patient_id: int,
    payload: SummaryRequest = SummaryRequest(),
    db: Session = Depends(get_db),
):
    if not db.query(models.Patient).get(patient_id):
        raise HTTPException(404, "Patient not found")
    return summary_agent.run(db, patient_id, window_days=payload.window_days or 180)
