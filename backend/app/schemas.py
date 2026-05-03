from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------- Patient ----------

class PatientCreate(BaseModel):
    external_id: Optional[str] = None
    name: str
    dob: Optional[date] = None
    gender: Optional[str] = None


class PatientOut(BaseModel):
    id: int
    external_id: Optional[str]
    name: str
    dob: Optional[date]
    gender: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Structured clinical extraction ----------

EventType = Literal["vital", "diagnosis", "medication", "lab", "note", "imaging"]
Severity = Literal["info", "warn", "critical"]


class ClinicalEvent(BaseModel):
    """One atomic fact extracted from a record."""
    event_type: EventType
    code: Optional[str] = Field(None, description="e.g. 'systolic_bp', 'HbA1c', ICD-10")
    value_text: Optional[str] = None
    value_num: Optional[float] = None
    unit: Optional[str] = None
    severity: Severity = "info"
    recorded_at: Optional[datetime] = None


class StructuredRecord(BaseModel):
    """LLM output for a single uploaded document."""
    recorded_at: Optional[datetime] = None
    summary: Optional[str] = None
    events: list[ClinicalEvent] = []


# ---------- Record / Timeline / Analysis responses ----------

class RecordOut(BaseModel):
    id: int
    patient_id: int
    source_type: str
    status: str
    recorded_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TimelineItem(BaseModel):
    event_id: int
    record_id: Optional[int]
    timestamp: Optional[datetime]
    event_type: str
    code: Optional[str]
    value_text: Optional[str]
    value_num: Optional[float]
    unit: Optional[str]
    severity: str


class ChangeOut(BaseModel):
    id: int
    from_record_id: Optional[int]
    to_record_id: Optional[int]
    risk_level: str
    notes: Optional[str]
    delta_json: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SummaryOut(BaseModel):
    id: int
    patient_id: int
    window_days: Optional[int]
    content_md: str
    model: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SummaryRequest(BaseModel):
    window_days: Optional[int] = 180
