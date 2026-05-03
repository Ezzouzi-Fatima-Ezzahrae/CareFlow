"""Deterministic analysis: change detection, summary generation, trend detection.

Designed to run without any LLM. Operates on lists of clinical events
returned by `extractors.extract_events`.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from typing import Any


# Threshold matrix for "moderate" vs "high" deltas on common numeric measures.
NUMERIC_DELTA_THRESHOLDS: dict[str, dict[str, float]] = {
    "systolic_bp":     {"moderate": 10, "high": 20},
    "diastolic_bp":    {"moderate": 5,  "high": 15},
    "heart_rate":      {"moderate": 15, "high": 30},
    "HbA1c":           {"moderate": 0.3, "high": 0.7},
    "fasting_glucose": {"moderate": 30, "high": 60},
    "ldl":             {"moderate": 20, "high": 40},
    "weight_kg":       {"moderate": 3,  "high": 6},
    "creatinine":      {"moderate": 0.2, "high": 0.5},
    "egfr":            {"moderate": 5,  "high": 10},
    "bnp":             {"moderate": 100, "high": 300},
}


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def detect_changes(prior: list[dict], current: list[dict]) -> dict[str, Any]:
    """Diff two event lists. Returns {risk_level, deltas, summary}.
    Inputs are dicts (as produced by `ClinicalEvent.to_dict()`)."""
    prior_by_code = {e["code"]: e for e in prior if e.get("code") and e.get("value_num") is not None}
    current_by_code = {e["code"]: e for e in current if e.get("code") and e.get("value_num") is not None}

    deltas: list[dict[str, Any]] = []
    risk = "low"

    for code, cur in current_by_code.items():
        if code not in prior_by_code:
            continue
        pv = prior_by_code[code]["value_num"]
        cv = cur["value_num"]
        diff = cv - pv
        level = _delta_level(code, diff)
        deltas.append({
            "code": code,
            "type": "numeric",
            "from": pv,
            "to": cv,
            "unit": cur.get("unit"),
            "delta": round(diff, 3),
            "level": level,
        })
        if level == "high":
            risk = "high"
        elif level == "moderate" and risk == "low":
            risk = "moderate"

    # New diagnoses appearing in current but not prior
    prior_dx = {(e.get("code") or e.get("value_text") or "").lower() for e in prior if e["event_type"] == "diagnosis"}
    new_dx = []
    for e in current:
        if e["event_type"] != "diagnosis":
            continue
        key = (e.get("code") or e.get("value_text") or "").lower()
        if key and key not in prior_dx:
            new_dx.append(e.get("value_text") or e.get("code"))
    if new_dx:
        deltas.append({"type": "new_diagnoses", "items": new_dx})
        if risk == "low":
            risk = "moderate"

    summary = _summarize_deltas(deltas, risk)
    return {"risk_level": risk, "deltas": deltas, "summary": summary}


def _delta_level(code: str, diff: float) -> str:
    t = NUMERIC_DELTA_THRESHOLDS.get(code)
    if not t:
        return "info"
    a = abs(diff)
    if a >= t["high"]:
        return "high"
    if a >= t["moderate"]:
        return "moderate"
    return "low"


def _summarize_deltas(deltas: list[dict], risk: str) -> str:
    if not deltas:
        return "No comparable changes detected."
    parts: list[str] = []
    for d in deltas:
        if d.get("type") == "new_diagnoses":
            parts.append("New diagnoses: " + ", ".join(d["items"][:3]))
            continue
        parts.append(f"{d['code']} {d['from']} → {d['to']} {d.get('unit') or ''} ({d['level']})")
    head = {"high": "High-risk delta detected.", "moderate": "Moderate change.", "low": "Minor change."}[risk]
    return head + " " + "; ".join(parts)


# ---------------------------------------------------------------------------
# Trend detection
# ---------------------------------------------------------------------------

def detect_trends(events: list[dict]) -> list[dict[str, Any]]:
    """For each numeric code, compute first→last trend. Returns list of trends."""
    series: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if e.get("value_num") is not None and e.get("code"):
            series[e["code"]].append(e)
    trends: list[dict[str, Any]] = []
    for code, arr in series.items():
        if len(arr) < 2:
            continue
        arr.sort(key=lambda x: x.get("recorded_at") or "")
        first, last = arr[0], arr[-1]
        diff = last["value_num"] - first["value_num"]
        direction = "up" if diff > 0 else "down" if diff < 0 else "flat"
        trends.append({
            "code": code,
            "from": first["value_num"],
            "to": last["value_num"],
            "unit": last.get("unit"),
            "delta": round(diff, 3),
            "direction": direction,
            "from_date": first.get("recorded_at"),
            "to_date": last.get("recorded_at"),
            "n_points": len(arr),
        })
    return trends


# ---------------------------------------------------------------------------
# Summary generation (Markdown)
# ---------------------------------------------------------------------------

def generate_summary(events: list[dict], window_days: int = 365) -> str:
    """Doctor-ready Markdown brief built from events. No LLM."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_type[e["event_type"]].append(e)

    # Active issues: latest diagnoses + flagged notes.
    active: list[str] = []
    seen: set[str] = set()
    for e in reversed(by_type.get("diagnosis", [])):
        key = (e.get("code") or e.get("value_text") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        label = e.get("value_text") or e.get("code") or "Unspecified diagnosis"
        if e.get("code") and e.get("value_text"):
            label = f"{label} ({e['code']})"
        active.append(label)
    for e in by_type.get("note", []):
        if e.get("severity") in ("warn", "critical") and e.get("value_text"):
            active.append(e["value_text"])

    # Trends
    trends = detect_trends(events)
    trend_lines: list[str] = []
    for t in trends:
        if t["direction"] == "flat":
            continue
        arrow = "↑" if t["direction"] == "up" else "↓"
        trend_lines.append(
            f"**{t['code']}**: {t['from']} → {t['to']} {t['unit'] or ''} "
            f"({arrow} {abs(t['delta'])})"
        )
    if not trend_lines:
        latest_each: dict[str, dict] = {}
        for e in events:
            if e.get("event_type") in ("vital", "lab") and e.get("code"):
                latest_each[e["code"]] = e
        for e in latest_each.values():
            v = e.get("value_num") if e.get("value_num") is not None else (e.get("value_text") or "")
            trend_lines.append(f"**{e['code']}**: {v} {e.get('unit') or ''}".strip())

    # Recent meds (last 3)
    meds = by_type.get("medication", [])[-3:]
    med_lines = [m.get("value_text") or m.get("code") for m in meds]

    # Suggested follow-ups
    follow: list[str] = []
    crit = [e for e in events if e.get("severity") == "critical"]
    warn = [e for e in events if e.get("severity") == "warn"]
    if crit:
        codes = sorted({e.get("code") or e["event_type"] for e in crit})
        follow.append(f"Address critical-flagged findings ({', '.join(codes)}).")
    elif warn:
        codes = sorted({e.get("code") or e["event_type"] for e in warn})
        follow.append(f"Monitor warning-flagged values ({', '.join(codes)}).")
    if med_lines:
        follow.append(f"Confirm adherence to recent regimen ({', '.join(str(m) for m in med_lines)}).")
    if not follow:
        follow.append("Routine follow-up unless symptoms change.")

    def bullet(items: list[str]) -> str:
        return "\n".join(f"- {x}" for x in items) if items else "- _(none)_"

    return (
        f"# Patient brief — last {window_days} days\n\n"
        f"## Active issues\n{bullet(active or ['No active diagnoses on record.'])}\n\n"
        f"## Trends\n{bullet(trend_lines or ['No numeric trends available.'])}\n\n"
        f"## Recent medications\n{bullet([str(m) for m in med_lines] or ['(none recorded)'])}\n\n"
        f"## Suggested follow-ups\n{bullet(follow)}\n\n"
        f"_Generated by CareFlow MCP — facts pulled directly from the event log._"
    )
