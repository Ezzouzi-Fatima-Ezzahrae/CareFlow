"""CareFlow MCP server.

Exposes deterministic healthcare tools so any LLM-powered agent on the
Prompt Opinion platform (or any other MCP host) can:

  - parse PDFs and medical images
  - extract structured clinical events (vitals, labs, diagnoses, meds)
  - compare two records and detect risk evolution
  - generate a doctor-ready summary

No LLM is required. Every tool runs deterministically over the input data.

"""
from __future__ import annotations
import json
from typing import Any

import base64
import json as _json
import os
import time
import urllib.parse
import urllib.request
from threading import Lock
from contextvars import ContextVar

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import __version__

# FastMCP enables DNS-rebinding protection by default which rejects any
# Host header that isn't localhost — that's why /sse returns "Invalid Host
# header" when reached through Fly.io / cloudflared / ngrok. Disable it so
# the SSE transport accepts any public hostname.
try:
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError:
    try:
        from mcp.shared.transport_security import TransportSecuritySettings
    except ImportError:
        TransportSecuritySettings = None  # older mcp SDK; nothing to do


# ===========================================================================
# In-memory patient cache — bridges PO's selected patient to the standalone
# dashboard at http://localhost:5173. The agent populates this via the
# register_patient tool whenever PO has injected patient context.
# ===========================================================================

_PATIENT_CACHE: dict[str, dict] = {}
_CACHE_LOCK = Lock()

# Capture every request's headers + body so we can SEE what PO actually sends
# (in particular, the FHIR Context Extension payload format).
_LAST_REQUESTS: list[dict] = []
_REQUESTS_LOCK = Lock()
_MAX_CAPTURED = 50

# Per-request FHIR context (populated by middleware)
_CURRENT_FHIR: ContextVar[dict | None] = ContextVar("careflow_fhir", default=None)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Max-Age": "3600",
}


def _patient_resource_basics(res: dict) -> tuple[str | None, str, str | None, str | None]:
    """From a FHIR Patient resource, extract (id, name, dob, gender)."""
    pid = res.get("id")
    n = (res.get("name") or [{}])[0]
    given = " ".join(n.get("given") or [])
    family = n.get("family") or ""
    name = (given + " " + family).strip() or "Unknown patient"
    dob = res.get("birthDate")
    gender = res.get("gender")
    return pid, name, dob, gender


def _extract_patient_basics(data: dict) -> tuple[str | None, str, str | None, str | None]:
    """Pull (id, name, dob, gender) from various input shapes."""
    if not isinstance(data, dict):
        return None, "Unknown patient", None, None

    rt = data.get("resourceType")
    if rt == "Bundle":
        for entry in (data.get("entry") or []):
            res = entry.get("resource", {})
            if isinstance(res, dict) and res.get("resourceType") == "Patient":
                return _patient_resource_basics(res)
    elif rt == "Patient":
        return _patient_resource_basics(data)

    # Plain JSON fallback — best-effort guesses
    name = data.get("name") or data.get("patientName") or data.get("display") or "Unknown patient"
    if isinstance(name, dict):
        given = " ".join(name.get("given") or [])
        family = name.get("family") or ""
        name = (given + " " + family).strip() or "Unknown patient"
    dob = data.get("dob") or data.get("birthDate") or data.get("dateOfBirth")
    pid = data.get("id") or data.get("patientId") or data.get("mrn")
    gender = data.get("gender") or data.get("sex")
    return (str(pid) if pid is not None else None), str(name), dob, gender
from .extractors import extract_events, ClinicalEvent
from .parsers import parse_pdf, ocr_image, b64_decode, image_metadata
from .image_analysis import analyze_image as _analyze_image
from .analysis import detect_changes, detect_trends, generate_summary
from .visualizations import (
    render_health_dashboard as _render_health_dashboard,
    render_metric_chart as _render_metric_chart,
    render_severity_distribution as _render_severity_distribution,
    render_progress_timeline as _render_progress_timeline,
)


def _parse_events(events_json: str) -> list[dict]:
    """Tolerantly parse events_json input. Accepts THREE shapes the LLM might send:

      1. A JSON array of events:           [{...}, {...}]
      2. A JSON object with "events" key:  {"events": [...], ...}
      3. A single-event JSON object:       {"event_type": ..., ...}

    Returns a normalized list of event dicts. Empty list on any failure.
    """
    if not events_json:
        return []
    if isinstance(events_json, list):
        return events_json
    try:
        data = json.loads(events_json) if isinstance(events_json, str) else events_json
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "events" in data and isinstance(data["events"], list):
            return data["events"]
        if data.get("event_type"):
            return [data]
    return []


# ===========================================================================
# Request capture + FHIR context extraction
# ===========================================================================

# Common header names PO might use to ship the FHIR context.
# We try them all on every request — whichever matches wins.
FHIR_BASE_HEADERS = (
    "x-fhir-base-url", "x-fhir-base", "x-careflow-fhir-base",
    "fhir-base-url", "x-prompt-opinion-fhir-base",
)
FHIR_TOKEN_HEADERS = (
    "x-fhir-authorization", "x-fhir-token", "fhir-authorization",
    "authorization",
)
FHIR_PATIENT_ID_HEADERS = (
    "x-fhir-patient-id", "x-patient-id", "x-careflow-patient",
)


def _extract_fhir_from_headers(headers: dict) -> dict | None:
    """Look for a FHIR context (base URL + token) in request headers."""
    lc = {k.lower(): v for k, v in headers.items()}
    base = next((lc[h] for h in FHIR_BASE_HEADERS if h in lc), None)
    token = next((lc[h] for h in FHIR_TOKEN_HEADERS if h in lc), None)
    patient_id = next((lc[h] for h in FHIR_PATIENT_ID_HEADERS if h in lc), None)
    if base or token or patient_id:
        return {
            "base_url": base,
            "auth": token,
            "patient_id": patient_id,
        }
    return None


def _record_request(method: str, path: str, headers: dict, body_preview: str) -> None:
    with _REQUESTS_LOCK:
        _LAST_REQUESTS.append({
            "ts": time.time(),
            "method": method,
            "path": path,
            "headers": dict(headers),
            "body_preview": body_preview[:2000],
        })
        if len(_LAST_REQUESTS) > _MAX_CAPTURED:
            del _LAST_REQUESTS[0:len(_LAST_REQUESTS) - _MAX_CAPTURED]


# Middleware: capture every request's headers + body, then set the FHIR
# context-var so tools called downstream can access it.
class CaptureMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Read headers
        raw_headers = scope.get("headers") or []
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in raw_headers}

        # Buffer the body so we can both inspect it AND replay it for the app
        body = b""
        more_body = True
        while more_body:
            msg = await receive()
            if msg["type"] == "http.request":
                body += msg.get("body") or b""
                more_body = msg.get("more_body", False)

        # Replay the buffered body
        async def replay_receive():
            return {"type": "http.request", "body": body, "more_body": False}

        # Try to also pull FHIR data from the JSON body (some platforms put
        # `_meta` there for tool calls).
        fhir_ctx = _extract_fhir_from_headers(headers)
        body_preview = body[:2000].decode("utf-8", errors="replace")
        try:
            parsed = _json.loads(body) if body else None
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            meta = (parsed.get("params") or {}).get("_meta") or parsed.get("_meta") or {}
            fhir_meta = meta.get("fhir") or meta.get("https://app.promptopinion.ai/schemas/a2a/v1/fhir-context")
            if isinstance(fhir_meta, dict):
                fhir_ctx = (fhir_ctx or {}) | {
                    "base_url": fhir_meta.get("baseUrl") or fhir_meta.get("base_url") or (fhir_ctx or {}).get("base_url"),
                    "auth": fhir_meta.get("accessToken") or fhir_meta.get("token") or (fhir_ctx or {}).get("auth"),
                    "patient_id": fhir_meta.get("patient") or fhir_meta.get("patientId") or (fhir_ctx or {}).get("patient_id"),
                }

        _record_request(scope.get("method", "?"), scope.get("path", "?"), headers, body_preview)

        if fhir_ctx:
            ctx_token = _CURRENT_FHIR.set(fhir_ctx)
            try:
                await self.app(scope, replay_receive, send)
            finally:
                _CURRENT_FHIR.reset(ctx_token)
        else:
            await self.app(scope, replay_receive, send)


def fetch_fhir_patient_bundle(patient_id: str) -> dict | None:
    """Use the captured FHIR context (if any) to fetch a patient $everything bundle.
    Returns the parsed JSON or None on failure."""
    ctx = _CURRENT_FHIR.get()
    if not ctx or not ctx.get("base_url"):
        return None
    base = ctx["base_url"].rstrip("/")
    token = ctx.get("auth") or ""
    if token and not token.lower().startswith("bearer "):
        token = f"Bearer {token}"
    url = f"{base}/Patient/{urllib.parse.quote(patient_id)}/$everything"
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/fhir+json, application/json",
            "Authorization": token,
        } if token else {"Accept": "application/fhir+json, application/json"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return _json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


_fastmcp_kwargs: dict = dict(
    name="CareFlow",
    instructions=(
        "CareFlow exposes deterministic healthcare tools for ingesting patient "
        "records (text, PDFs, medical images), extracting structured clinical "
        "events, detecting changes between visits, and generating doctor "
        "summaries. Use these tools to build longitudinal patient timelines "
        "without needing your own extractor model."
    ),
)

# Disable DNS-rebinding host validation so the SSE transport accepts requests
# proxied through Fly.io, cloudflared, ngrok, etc. (Has no security impact for
# our use case — this is a deterministic, public, read-mostly service.)
if TransportSecuritySettings is not None:
    _fastmcp_kwargs["transport_security"] = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=["*"],
        allowed_origins=["*"],
    )

mcp = FastMCP(**_fastmcp_kwargs)


# ---------------------------------------------------------------------------
# Tool 1 — Extract clinical events from text
# ---------------------------------------------------------------------------

@mcp.tool()
def extract_clinical_events(text: str, recorded_at: str | None = None) -> dict[str, Any]:
    """Extract structured clinical events (vitals, labs, diagnoses, medications)
    from a free-text clinical document.

    Args:
        text: The raw clinical text (discharge note, lab report, progress note).
        recorded_at: Optional ISO8601 date the events should be tagged with.
            If omitted, CareFlow infers the latest plausible date in the text.

    Returns a JSON object:
        {
          "event_count": int,
          "events": [ {event_type, code, value_num, value_text, unit, severity, recorded_at}, ... ],
          "method": "regex-deterministic"
        }
    """
    events = extract_events(text or "", recorded_at=recorded_at)
    return {
        "event_count": len(events),
        "events": [e.to_dict() for e in events],
        "method": "regex-deterministic",
    }


# ---------------------------------------------------------------------------
# Tool 2 — Parse a PDF document
# ---------------------------------------------------------------------------

@mcp.tool()
def parse_pdf_document(pdf_b64: str, include_images: bool = False) -> dict[str, Any]:
    """Parse a PDF and return extracted text + optional embedded images.

    Args:
        pdf_b64: Base64-encoded PDF bytes (with or without "data:" prefix).
        include_images: If true, also return embedded images as base64 PNGs.
            Defaults to false to keep payloads small.

    Returns:
        {
          "raw_text": str,
          "page_count": int,
          "image_count": int,
          "scanned": bool,
          "images_b64": [str, ...]   # only if include_images=true
        }
    """
    if not pdf_b64:
        return {"error": "no PDF provided", "raw_text": "", "page_count": 0,
                "image_count": 0, "scanned": False}
    try:
        pdf_bytes = b64_decode(pdf_b64)
    except Exception as e:
        return {"error": f"could not decode PDF: {e}", "raw_text": "",
                "page_count": 0, "image_count": 0, "scanned": False}
    out = parse_pdf(pdf_bytes)
    if not include_images:
        out.pop("images_b64", None)
    return out


# ---------------------------------------------------------------------------
# Tool 3 — Analyze a medical image
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_medical_image(image_b64: str, context: str = "") -> dict[str, Any]:
    """OCR a medical image and infer its modality + likely findings.
    Deterministic — uses Tesseract OCR plus keyword heuristics.

    Args:
        image_b64: Image input. Accepts base64 (with or without data: prefix)
            OR an HTTP/HTTPS URL.
        context: Optional free-text hint (e.g. "chest X-ray, PA view") to
            improve modality classification.

    Returns: { modality, body_region, ocr_text, findings, urgent, char_count, dimensions }
    """
    if not image_b64:
        return {"error": "no image provided", "modality": "unknown",
                "findings": [], "ocr_text": "", "urgent": False}
    try:
        image_bytes = b64_decode(image_b64)
    except Exception as e:
        return {"error": f"could not decode image: {e}", "modality": "unknown",
                "findings": [], "ocr_text": "", "urgent": False}
    return _analyze_image(image_bytes, context=context or "")


# ---------------------------------------------------------------------------
# Tool 4 — Ingest one record end-to-end
# ---------------------------------------------------------------------------

@mcp.tool()
def ingest_clinical_record(
    text: str | None = None,
    pdf_b64: str | None = None,
    image_b64: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """One-shot ingestion: provide any of text, pdf_b64, or image_b64 (or
    several) and CareFlow returns a single normalized record with extracted
    events. Useful when an upstream agent has a multi-modal blob and just
    wants events back.

    Args:
        text: Optional plain text.
        pdf_b64: Optional base64-encoded PDF.
        image_b64: Optional base64-encoded image.
        recorded_at: Optional ISO8601 timestamp for the record.

    Returns:
        {
          "raw_text": str,           # union of all extracted text
          "image_findings": dict|null,
          "events": [ ... ],         # extracted clinical events
          "event_count": int,
          "recorded_at": str|null
        }
    """
    raw_chunks: list[str] = []
    image_findings: dict | None = None

    if text:
        raw_chunks.append(text)

    if pdf_b64:
        parsed = parse_pdf(b64_decode(pdf_b64))
        raw_chunks.append(parsed.get("raw_text") or "")
        # If the PDF had embedded images, OCR the first one.
        if parsed.get("images_b64"):
            first_img = b64_decode(parsed["images_b64"][0])
            image_findings = _analyze_image(first_img)
            if image_findings.get("ocr_text"):
                raw_chunks.append(image_findings["ocr_text"])

    if image_b64:
        img_bytes = b64_decode(image_b64)
        image_findings = _analyze_image(img_bytes)
        if image_findings.get("ocr_text"):
            raw_chunks.append(image_findings["ocr_text"])

    raw_text = "\n\n".join(c for c in raw_chunks if c).strip()
    events = extract_events(raw_text, recorded_at=recorded_at)
    # Add an explicit imaging event if we have findings.
    if image_findings and image_findings.get("findings"):
        events.append(ClinicalEvent(
            event_type="imaging",
            code=image_findings.get("modality"),
            value_text="; ".join(image_findings["findings"])[:500],
            severity="warn" if image_findings.get("urgent") else "info",
            recorded_at=recorded_at,
        ))

    return {
        "raw_text": raw_text,
        "image_findings": image_findings,
        "events": [e.to_dict() for e in events],
        "event_count": len(events),
        "recorded_at": recorded_at,
    }


# ---------------------------------------------------------------------------
# Tool 5 — Compare two records (change / risk detection)
# ---------------------------------------------------------------------------

@mcp.tool()
def detect_risk_changes(
    prior_events_json: str,
    current_events_json: str,
) -> dict[str, Any]:
    """Compare two sets of clinical events and report risk evolution.

    Args:
        prior_events_json: JSON string — list of ClinicalEvent dicts (older record).
        current_events_json: JSON string — list of ClinicalEvent dicts (newer record).

    Returns:
        {
          "risk_level": "low|moderate|high",
          "summary": str,
          "deltas": [ {code, from, to, unit, delta, level}, ... ]
        }
    """
    prior = _parse_events(prior_events_json)
    current = _parse_events(current_events_json)
    return detect_changes(prior, current)


# ---------------------------------------------------------------------------
# Tool 6 — Numeric trend detection
# ---------------------------------------------------------------------------

@mcp.tool()
def detect_lab_trends(events_json: str) -> dict[str, Any]:
    """Identify first→last trends for every numeric code in a patient's timeline.

    Args:
        events_json: JSON string — list of ClinicalEvent dicts spanning time.

    Returns:
        {
          "trends": [ {code, from, to, unit, delta, direction, from_date, to_date, n_points}, ... ]
        }
    """
    events = _parse_events(events_json)
    return {"trends": detect_trends(events)}


# ---------------------------------------------------------------------------
# Tool 7 — Doctor summary
# ---------------------------------------------------------------------------

@mcp.tool()
def generate_doctor_summary(events_json: str, window_days: int = 365) -> dict[str, Any]:
    """Generate a Markdown brief for the treating physician from a patient's
    timeline. Sections: Active issues, Trends, Recent medications, Suggested
    follow-ups. Deterministic — no LLM call.

    Args:
        events_json: JSON string — list of ClinicalEvent dicts.
        window_days: Window of history to summarize (default 365).

    Returns:
        { "markdown": str, "event_count": int }
    """
    events = _parse_events(events_json)
    return {
        "markdown": generate_summary(events, window_days=window_days),
        "event_count": len(events),
    }


# ---------------------------------------------------------------------------
# Tool 8 (NEW PRIMARY) — Text-based health dashboard (renders cleanly in PO)
# ---------------------------------------------------------------------------

@mcp.tool()
def render_text_dashboard(events_json: str) -> str:
    """Generate a clean Markdown dashboard with severity emojis (🔴🟠🟢) instead
    of an image. THIS IS THE DEFAULT VISUAL — use it after generate_doctor_summary.
    Renders correctly in any chat UI, no base64 bloat, doctor-friendly.

    Args:
        events_json: JSON string — list of ClinicalEvent dicts.
    """
    events = _parse_events(events_json)
    if not events:
        return "_No events to display._"

    SEV = {"info": "🟢", "warn": "🟠", "critical": "🔴"}

    vitals = [e for e in events if e.get("event_type") == "vital"]
    labs = [e for e in events if e.get("event_type") == "lab"]
    diagnoses = [e for e in events if e.get("event_type") == "diagnosis"]
    meds = [e for e in events if e.get("event_type") == "medication"]
    notes = [e for e in events if e.get("event_type") == "note"]
    imaging = [e for e in events if e.get("event_type") == "imaging"]

    lines: list[str] = ["## Health dashboard"]

    if vitals:
        lines.append("\n### Vitals")
        for e in vitals:
            emoji = SEV.get(e.get("severity", "info"), "⚪")
            val = f"{e.get('value_num')} {e.get('unit') or ''}".strip()
            lines.append(f"- {emoji}  **{e.get('code')}**: {val}")

    if labs:
        lines.append("\n### Labs")
        for e in labs:
            emoji = SEV.get(e.get("severity", "info"), "⚪")
            val = f"{e.get('value_num')} {e.get('unit') or ''}".strip()
            lines.append(f"- {emoji}  **{e.get('code')}**: {val}")

    if diagnoses:
        lines.append("\n### Diagnoses")
        seen: set[str] = set()
        for e in diagnoses:
            key = (e.get("code") or e.get("value_text") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            label = e.get("value_text") or e.get("code") or "Unspecified"
            if e.get("code") and e.get("value_text"):
                label = f"{label} ({e.get('code')})"
            lines.append(f"- 📋 {label}")

    if meds:
        lines.append("\n### Medications")
        seen_meds: set[str] = set()
        for e in meds:
            key = (e.get("code") or "").lower()
            if key in seen_meds:
                continue
            seen_meds.add(key)
            lines.append(f"- 💊 {e.get('value_text') or e.get('code')}")

    if imaging:
        lines.append("\n### Imaging")
        for e in imaging:
            emoji = SEV.get(e.get("severity", "info"), "⚪")
            label = e.get("value_text") or e.get("code") or "imaging study"
            lines.append(f"- {emoji}  {label}")

    if notes:
        lines.append("\n### Notes")
        for e in notes:
            emoji = SEV.get(e.get("severity", "info"), "⚪")
            lines.append(f"- {emoji}  {e.get('value_text') or '(no detail)'}")

    # Risk summary at bottom
    crit = sum(1 for e in events if e.get("severity") == "critical")
    warn = sum(1 for e in events if e.get("severity") == "warn")
    total = len(events)
    if crit:
        risk_line = f"\n**🔴 Overall risk: HIGH** — {crit} critical, {warn} warning, out of {total} events."
    elif warn:
        risk_line = f"\n**🟠 Overall risk: MODERATE** — {warn} warning out of {total} events."
    else:
        risk_line = f"\n**🟢 Overall risk: LOW** — all {total} events within normal range."
    lines.append(risk_line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 9 (advanced, on-demand only) — Health dashboard chart (image)
# ---------------------------------------------------------------------------

def _png_to_markdown(png: bytes, alt: str) -> str:
    """Encode PNG bytes as a markdown image with a data URL.
    PO and most chat UIs render this inline."""
    b64 = base64.b64encode(png).decode()
    return f"![{alt}](data:image/png;base64,{b64})"


@mcp.tool()
def render_health_dashboard(events_json: str) -> str:
    """Render a horizontal bar chart of every numeric metric, color-coded by
    severity (red=critical, amber=warn, green=normal). Returns a Markdown
    image string that the chat UI renders inline.

    Args:
        events_json: JSON string — list of ClinicalEvent dicts.
    """
    events = _parse_events(events_json)
    return _png_to_markdown(_render_health_dashboard(events), "Health dashboard")


# ---------------------------------------------------------------------------
# Tool 9 — Metric trend over time (image)
# ---------------------------------------------------------------------------

@mcp.tool()
def render_metric_chart(events_json: str, code: str) -> str:
    """Render a line chart of a single clinical metric (e.g., HbA1c, systolic_bp,
    LDL) across visits. Each point is colored by its severity at that visit.
    Returns a Markdown image string that the chat UI renders inline.

    Args:
        events_json: JSON string — list of ClinicalEvent dicts spanning time.
        code: The metric code to plot (e.g., 'HbA1c', 'systolic_bp', 'ldl').
    """
    events = _parse_events(events_json)
    return _png_to_markdown(_render_metric_chart(events, code), f"{code} over time")


# ---------------------------------------------------------------------------
# Tool 10 — Severity distribution (image)
# ---------------------------------------------------------------------------

@mcp.tool()
def render_severity_distribution(events_json: str) -> str:
    """Render a donut chart showing the proportion of normal / warning /
    critical events for the patient, with a big risk label in the center.
    Returns a Markdown image string that the chat UI renders inline.

    Args:
        events_json: JSON string — list of ClinicalEvent dicts.
    """
    events = _parse_events(events_json)
    return _png_to_markdown(_render_severity_distribution(events), "Severity distribution")


# ---------------------------------------------------------------------------
# Tool 11 — Progress timeline (image)
# ---------------------------------------------------------------------------

@mcp.tool()
def render_progress_timeline(events_json: str) -> str:
    """Render a multi-panel chart with one subplot per numeric metric, plotted
    across all visits. Color-coded by severity (red/amber/green). Use this
    when the patient has 2+ records spanning time — it's the single best way
    to see how the patient is progressing overall.

    Args:
        events_json: JSON string — list of ClinicalEvent dicts spanning time.
    """
    events = _parse_events(events_json)
    return _png_to_markdown(_render_progress_timeline(events), "Patient progress timeline")


# ---------------------------------------------------------------------------
# Tool 12 — Server info / smoke test
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tool — Register patient context (the bridge for the dashboard)
# ---------------------------------------------------------------------------

@mcp.tool()
def register_patient(
    name: str,
    summary_text: str = "",
    patient_json: str = "",
    patient_id: str = "",
) -> str:
    """ALL-IN-ONE — registers the patient in CareFlow's dashboard cache,
    extracts events, generates the doctor brief, AND returns one ready-to-paste
    Markdown string that already contains the brief + the clickable dashboard
    link + the disclaimer.

    Call this ONCE. Then paste the return value VERBATIM as your reply.

    Speed tip: prefer `summary_text` over `patient_json`. A short 200–500 char
    summary is fast; a full FHIR JSON is slow.

    Args:
        name: Patient's full name (required).
        summary_text: Plain-text clinical summary (vitals, labs, diagnoses, meds).
        patient_json: Optional full FHIR Bundle JSON.
        patient_id: Optional ID; auto-generated if omitted.

    Returns: A single Markdown string. Paste it as your reply with no edits.
    """
    data: dict | None = None
    if patient_json:
        try:
            data = json.loads(patient_json) if isinstance(patient_json, str) else patient_json
        except (json.JSONDecodeError, TypeError):
            data = None

    pid, parsed_name, dob, gender = _extract_patient_basics(data or {})
    final_id = patient_id or pid or f"patient-{int(time.time() * 1000)}"
    final_name = name or parsed_name or "Unknown patient"

    # Always run the regex extractor on summary_text — fast, no LLM.
    derived_events_objs = extract_events(summary_text) if summary_text else []
    derived_events = [e.to_dict() for e in derived_events_objs]

    record = {
        "id": str(final_id),
        "name": final_name,
        "dob": dob,
        "gender": gender,
        "fhir": data,
        "derived_events": derived_events,
        "summary_text": summary_text or None,
        "registered_at": time.time(),
        "source": "po-mcp-bridge",
    }
    with _CACHE_LOCK:
        _PATIENT_CACHE[record["id"]] = record

    # Build the doctor brief NOW so the agent doesn't need a second call.
    summary_md = generate_summary(derived_events, window_days=365) if derived_events else (
        f"# Patient brief — {final_name}\n\n"
        f"_No structured events extracted yet. Cached for the dashboard._"
    )

    # Construct a deep link to the dashboard. If the dashboard is on Vercel,
    # it uses its own /api/* proxy (no need for ?mcp=). For local dev or
    # other hosts, include the mcp= param so the dashboard knows where to
    # fetch from.
    dashboard_base = os.environ.get( "http://localhost:5173").rstrip("/")
    public_mcp = os.environ.get ("http://localhost:8000").rstrip("/")
    params: dict = {"patient": final_id}
    if ".vercel.app" not in dashboard_base:
        params["mcp"] = public_mcp
    dashboard_url = f"{dashboard_base}?{urllib.parse.urlencode(params)}"

    # Compose ONE single Markdown string the agent just pastes verbatim.
    response = (
        f"{summary_md.rstrip()}"
        f"\n\n"
        f"**[📊 Open {final_name}'s dashboard]({dashboard_url})**"
        f"\n\n"
        f"_Synthetic data only. Not a medical device._"
    )
    return response


# ---------------------------------------------------------------------------
# REST endpoints (so the dashboard can poll the MCP server)
# ---------------------------------------------------------------------------

@mcp.custom_route("/api/patients", methods=["GET", "OPTIONS"])
async def api_list_patients(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response(headers=CORS_HEADERS)
    with _CACHE_LOCK:
        patients = list(_PATIENT_CACHE.values())
    patients.sort(key=lambda p: p.get("registered_at") or 0, reverse=True)
    return JSONResponse({"patients": patients, "count": len(patients)},
                        headers=CORS_HEADERS)


@mcp.custom_route("/api/patients/{patient_id}", methods=["GET", "DELETE", "OPTIONS"])
async def api_patient_detail(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response(headers=CORS_HEADERS)
    pid = request.path_params["patient_id"]
    if request.method == "DELETE":
        with _CACHE_LOCK:
            removed = _PATIENT_CACHE.pop(pid, None)
        return JSONResponse(
            {"deleted": pid, "found": removed is not None},
            headers=CORS_HEADERS,
        )
    with _CACHE_LOCK:
        patient = _PATIENT_CACHE.get(pid)
    if not patient:
        return JSONResponse({"error": "not found"}, status_code=404, headers=CORS_HEADERS)
    return JSONResponse(patient, headers=CORS_HEADERS)


@mcp.custom_route("/api/clear", methods=["POST", "OPTIONS"])
async def api_clear(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response(headers=CORS_HEADERS)
    with _CACHE_LOCK:
        n = len(_PATIENT_CACHE)
        _PATIENT_CACHE.clear()
    return JSONResponse({"cleared": n}, headers=CORS_HEADERS)


@mcp.custom_route("/api/health", methods=["GET", "OPTIONS"])
async def api_health(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response(headers=CORS_HEADERS)
    with _CACHE_LOCK:
        n = len(_PATIENT_CACHE)
    return JSONResponse({"ok": True, "cached_patients": n, "version": __version__},
                        headers=CORS_HEADERS)


@mcp.custom_route("/api/debug/requests", methods=["GET", "OPTIONS"])
async def api_debug_requests(request: Request) -> Response:
    """Returns the last N captured requests so we can SEE what PO is sending,
    including the FHIR Context Extension headers/body if any."""
    if request.method == "OPTIONS":
        return Response(headers=CORS_HEADERS)
    with _REQUESTS_LOCK:
        out = list(_LAST_REQUESTS[-20:])
    return JSONResponse({"count": len(out), "requests": out}, headers=CORS_HEADERS)


@mcp.custom_route("/api/debug/fhir", methods=["GET", "OPTIONS"])
async def api_debug_fhir(request: Request) -> Response:
    """Show whether the FHIR context was set on the most recent request."""
    if request.method == "OPTIONS":
        return Response(headers=CORS_HEADERS)
    with _REQUESTS_LOCK:
        recent = list(_LAST_REQUESTS[-10:])
    fhirs = []
    for req in recent:
        ctx = _extract_fhir_from_headers(req.get("headers") or {})
        fhirs.append({
            "ts": req.get("ts"),
            "path": req.get("path"),
            "fhir_in_headers": ctx,
            "header_keys": sorted((req.get("headers") or {}).keys()),
        })
    return JSONResponse({"recent_fhir_contexts": fhirs}, headers=CORS_HEADERS)


# ---------------------------------------------------------------------------
# Server info / smoke test
# ---------------------------------------------------------------------------

@mcp.tool()
def careflow_info() -> dict[str, Any]:
    """Return server version + tool list. Useful for smoke-testing integration."""
    return {
        "name": "CareFlow",
        "version": __version__,
        "deterministic": True,
        "llm_required": False,
        "tools": [
            "extract_clinical_events",
            "parse_pdf_document",
            "analyze_medical_image",
            "ingest_clinical_record",
            "detect_risk_changes",
            "detect_lab_trends",
            "generate_doctor_summary",
            "register_patient",
            "render_text_dashboard",
            "render_health_dashboard",
            "render_metric_chart",
            "render_severity_distribution",
            "render_progress_timeline",
            "careflow_info",
        ],
    }


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def _with_cors(app):
    """Wrap an ASGI app with CORS so the dashboard (different origin) can fetch."""
    from starlette.middleware.cors import CORSMiddleware
    return CORSMiddleware(
        app,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )


def main() -> None:
    """Run the server over stdio (default for MCP hosts that spawn the process)."""
    mcp.run()


def _resolve_host_port():
    """Return (host, port) — defaults are local dev; cloud overrides via env."""
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    return host, port


_UVICORN_KW = {
    # Trust the X-Forwarded-* headers Fly.io / Render / any reverse proxy adds.
    # Without these, uvicorn returns 421 "Invalid Host header" for proxied
    # requests (PO → Fly edge → our app).
    "forwarded_allow_ips": "*",
    "proxy_headers": True,
    "log_level": "info",
}


def main_http() -> None:
    """Streamable HTTP transport."""
    mcp.run(transport="streamable-http")


def main_sse() -> None:
    """SSE transport. Used by Prompt Opinion."""
    mcp.run(transport="sse")


if __name__ == "__main__":
    import sys
    if "--http" in sys.argv:
        main_http()
    elif "--sse" in sys.argv:
        main_sse()
    else:
        main()
