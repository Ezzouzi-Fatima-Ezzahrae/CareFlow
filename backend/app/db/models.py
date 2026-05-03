from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, ForeignKey, Float, Index
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    external_id = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    dob = Column(Date)
    gender = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("Record", back_populates="patient", cascade="all,delete")
    events = relationship("Event", back_populates="patient", cascade="all,delete")


class Record(Base):
    __tablename__ = "records"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    source_type = Column(String, nullable=False)   # 'text' | 'pdf' | 'image'
    file_path = Column(String)
    raw_text = Column(Text)
    structured_json = Column(Text)                 # JSON-encoded StructuredRecord
    status = Column(String, default="pending")     # 'pending' | 'processed' | 'failed'
    recorded_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="records")
    events = relationship("Event", back_populates="record", cascade="all,delete")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    record_id = Column(Integer, ForeignKey("records.id"), index=True)
    event_type = Column(String, nullable=False)    # 'vital'|'diagnosis'|'medication'|'lab'|'note'|'imaging'
    code = Column(String)
    value_text = Column(Text)
    value_num = Column(Float)
    unit = Column(String)
    severity = Column(String, default="info")
    recorded_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="events")
    record = relationship("Record", back_populates="events")


Index("ix_events_patient_recorded", Event.patient_id, Event.recorded_at)


class Change(Base):
    __tablename__ = "changes"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    from_record_id = Column(Integer, ForeignKey("records.id"))
    to_record_id = Column(Integer, ForeignKey("records.id"))
    delta_json = Column(Text)
    risk_level = Column(String, default="low")     # 'low'|'moderate'|'high'
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Summary(Base):
    __tablename__ = "summaries"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True, nullable=False)
    window_days = Column(Integer)
    content_md = Column(Text)
    model = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
