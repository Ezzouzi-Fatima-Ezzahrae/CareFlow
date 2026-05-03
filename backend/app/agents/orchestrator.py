"""Orchestrator: glues the agents together for a single uploaded record."""
from __future__ import annotations
import logging
from typing import Literal

from sqlalchemy.orm import Session

from app.db import models
from app.agents.ingestion import IngestionAgent
from app.agents.vision import VisionAgent
from app.agents.structuring import StructuringAgent
from app.agents.memory import MemoryAgent
from app.agents.change_detection import ChangeDetectionAgent

log = logging.getLogger(__name__)

SourceType = Literal["text", "pdf", "image"]


class Orchestrator:
    def __init__(self) -> None:
        self.ingestion = IngestionAgent()
        self.vision = VisionAgent()
        self.structuring = StructuringAgent()
        self.memory = MemoryAgent()
        self.changes = ChangeDetectionAgent()

    def process_record(self, db: Session, record: models.Record) -> dict:
        try:
            ingested = self.ingestion.run(record.file_path, record.source_type)
            record.raw_text = ingested.get("raw_text", "")

            vision_output = None
            images = ingested.get("images", []) or []
            if images:
                # For MVP, only describe the first image to keep token costs predictable.
                vision_output = self.vision.run(images[0])
                # Merge OCR'd text into raw_text if it adds anything.
                ocr = (vision_output or {}).get("ocr_text") or ""
                if ocr and ocr not in record.raw_text:
                    record.raw_text = (record.raw_text + "\n" + ocr).strip()

            structured = self.structuring.run(record.raw_text, vision_output)
            event_ids = self.memory.run(db, record, structured)

            change = self.changes.run(db, record.patient_id, record.id)
            return {
                "record_id": record.id,
                "event_ids": event_ids,
                "change_id": change.id if change else None,
            }
        except Exception as exc:
            log.exception("Pipeline failed for record %s", record.id)
            record.status = "failed"
            db.commit()
            raise
