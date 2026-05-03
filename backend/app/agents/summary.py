"""SummaryAgent: produces a doctor-ready Markdown brief.

Two paths:
  1. Primary — call the configured LLM (Gemini / OpenAI) over the timeline.
  2. Fallback — if the LLM is missing or errors out, generate a deterministic
     summary directly from the events table. This keeps the demo working
     offline / on free-tier quota exhaustion.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from app.db import models
from app.llm import STUB_TEXT, chat_text
from app.config import settings


SYSTEM = (
    "You are a clinical scribe. Given a patient's recent timeline and detected changes, "
    "write a concise (<= 250 words) Markdown brief for the treating physician with these sections: "
    "**Active issues**, **Trends**, **Recent changes**, **Suggested follow-ups**. "
    "Use plain language. Do not invent facts."
)


class SummaryAgent:
    def run(self, db: Session, patient_id: int, window_days: int = 180) -> models.Summary:
        since = datetime.utcnow() - timedelta(days=window_days)

        events = (
            db.query(models.Event)
            .filter(models.Event.patient_id == patient_id, models.Event.recorded_at >= since)
            .order_by(models.Event.recorded_at.asc())
            .all()
        )
        changes = (
            db.query(models.Change)
            .filter(models.Change.patient_id == patient_id)
            .order_by(models.Change.created_at.desc())
            .limit(5)
            .all()
        )

        timeline_lines = [
            f"- {e.recorded_at.isoformat() if e.recorded_at else '?'} | {e.event_type} | "
            f"{e.code or ''} | {e.value_text or ''} {e.value_num or ''} {e.unit or ''} | "
            f"severity={e.severity}"
            for e in events
        ]
        change_blobs = [
            f"- risk={c.risk_level} :: {c.notes or ''} :: {c.delta_json or ''}"
            for c in changes
        ]
        user = (
            f"WINDOW: last {window_days} days\n\n"
            f"TIMELINE ({len(events)} events):\n" + "\n".join(timeline_lines or ["(none)"]) +
            "\n\nRECENT CHANGES:\n" + "\n".join(change_blobs or ["(none)"])
        )

        content = chat_text(SYSTEM, user)
        used_model = settings.gemini_model if settings.llm_provider == "gemini" else settings.llm_model

        if content == STUB_TEXT or not content.strip():
            content = _deterministic_summary(events, changes, window_days)
            used_model = "deterministic-fallback"

        summary = models.Summary(
            patient_id=patient_id,
            window_days=window_days,
            content_md=content,
            model=used_model,
        )
        db.add(summary)
        db.commit()
        db.refresh(summary)
        return summary


# ---------------------------------------------------------------------------
# Deterministic fallback — runs WITHOUT any LLM call.
# Generates a real-looking, accurate-to-the-data Markdown brief from the
# events and changes tables.
# ---------------------------------------------------------------------------

def _deterministic_summary(
    events: Iterable[models.Event],
    changes: Iterable[models.Change],
    window_days: int,
) -> str:
    events = list(events)
    changes = list(changes)

    # Bucket events by type.
    by_type: dict[str, list[models.Event]] = defaultdict(list)
    for e in events:
        by_type[e.event_type].append(e)

    # ------- Active issues: latest diagnoses + flagged events ----------------
    active_issues: list[str] = []
    seen_codes: set[str] = set()
    for e in reversed(by_type["diagnosis"]):
        key = (e.code or e.value_text or "").lower()
        if not key or key in seen_codes:
            continue
        seen_codes.add(key)
        label = e.value_text or e.code or "Unspecified diagnosis"
        active_issues.append(f"{label}" + (f" ({e.code})" if e.code and e.value_text else ""))
    for e in by_type["note"]:
        if e.severity in ("warn", "critical") and e.value_text:
            active_issues.append(e.value_text)

    # ------- Trends: numeric labs/vitals first vs last ----------------------
    numeric_series: dict[str, list[models.Event]] = defaultdict(list)
    for e in events:
        if e.event_type in ("vital", "lab") and e.value_num is not None and e.code:
            numeric_series[e.code].append(e)

    trends: list[str] = []
    for code, series in numeric_series.items():
        if len(series) < 2:
            continue
        first, last = series[0], series[-1]
        delta = last.value_num - first.value_num
        if abs(delta) < 1e-9:
            continue
        arrow = "↑" if delta > 0 else "↓"
        trends.append(
            f"**{code}**: {first.value_num} → {last.value_num} {last.unit or ''} "
            f"({arrow} {abs(round(delta, 2))})"
        )
    # Always show latest values if no trend was computable.
    if not trends:
        latest_each: dict[str, models.Event] = {}
        for e in events:
            if e.event_type in ("vital", "lab") and e.code:
                latest_each[e.code] = e
        for e in latest_each.values():
            v = e.value_num if e.value_num is not None else e.value_text or ""
            trends.append(f"**{e.code}**: {v} {e.unit or ''}".strip())

    # ------- Recent changes ------------------------------------------------
    recent_change_lines: list[str] = []
    for c in changes[:3]:
        if c.notes:
            recent_change_lines.append(f"_{c.risk_level.title()} risk_ — {c.notes}")
        else:
            recent_change_lines.append(f"_{c.risk_level.title()} risk_ delta detected.")

    # ------- Suggested follow-ups ------------------------------------------
    follow_ups: list[str] = []
    crit = [e for e in events if e.severity == "critical"]
    warns = [e for e in events if e.severity == "warn"]
    if crit:
        follow_ups.append("Address critical-flagged findings (" +
                          ", ".join(sorted({e.code or e.event_type for e in crit})) +
                          ") at the next visit.")
    if warns and not crit:
        follow_ups.append("Monitor warning-flagged values (" +
                          ", ".join(sorted({e.code or e.event_type for e in warns})) +
                          ") and reassess at next visit.")
    high_risk = any(c.risk_level == "high" for c in changes)
    if high_risk:
        follow_ups.append("Consider specialist referral given high-risk delta.")
    recent_meds = [e for e in by_type["medication"][-3:]]
    if recent_meds:
        meds_str = ", ".join((e.code or "med") + (f" {e.value_text}" if e.value_text else "") for e in recent_meds)
        follow_ups.append(f"Confirm adherence to recent regimen ({meds_str}).")
    if not follow_ups:
        follow_ups.append("Routine follow-up in 3 months unless symptoms change.")

    # ------- Stitch it together --------------------------------------------
    def bullet(items: list[str]) -> str:
        return "\n".join(f"- {x}" for x in items) if items else "- _(none)_"

    return (
        f"# Patient brief — last {window_days} days\n\n"
        f"## Active issues\n{bullet(active_issues or ['No active diagnoses on record.'])}\n\n"
        f"## Trends\n{bullet(trends or ['No numeric trends available.'])}\n\n"
        f"## Recent changes\n{bullet(recent_change_lines or ['No prior comparison available yet.'])}\n\n"
        f"## Suggested follow-ups\n{bullet(follow_ups)}\n\n"
        f"_Generated locally without LLM — facts are pulled directly from the event log._"
    )
