"""Record upload + listing. Triggers the agent pipeline synchronously."""
from __future__ import annotations
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.orchestrator import Orchestrator
from app.config import settings
from app.db import models
from app.db.session import get_db
from app.schemas import RecordOut

router = APIRouter(prefix="/patients/{patient_id}/records", tags=["records"])
orchestrator = Orchestrator()


def _detect_source_type(filename: str, content_type: str | None) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    if name.endswith((".txt", ".md")):
        return "text"
    if (content_type or "").startswith("image/"):
        return "image"
    if (content_type or "") == "application/pdf":
        return "pdf"
    return "text"


@router.post("", response_model=RecordOut)
async def upload_record(
    patient_id: int,
    file: UploadFile = File(...),
    recorded_at: Optional[datetime] = Form(None),
    db: Session = Depends(get_db),
):
    patient = db.query(models.Patient).get(patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    contents = await file.read()
    if len(contents) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit")

    os.makedirs(settings.storage_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".bin"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(settings.storage_dir, stored_name)
    with open(file_path, "wb") as f:
        f.write(contents)

    source_type = _detect_source_type(file.filename or "", file.content_type)
    record = models.Record(
        patient_id=patient_id,
        source_type=source_type,
        file_path=file_path,
        recorded_at=recorded_at,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Run the pipeline. For MVP this is synchronous; swap to a background task later.
    orchestrator.process_record(db, record)
    db.refresh(record)
    return record


@router.get("", response_model=list[RecordOut])
def list_records(patient_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Record)
        .filter(models.Record.patient_id == patient_id)
        .order_by(models.Record.created_at.desc())
        .all()
    )
