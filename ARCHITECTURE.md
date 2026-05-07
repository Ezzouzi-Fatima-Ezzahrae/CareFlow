# CareFlow — MVP Architecture & Build Plan

> AI-powered, multi-agent healthcare system that ingests patient data over time, builds a medical timeline, detects clinically meaningful changes, and produces doctor-ready summaries.

---

## Step 1 — System Architecture

CareFlow is a **modular agent pipeline** sitting behind a FastAPI gateway with a thin React dashboard on top. Everything is intentionally simple for an MVP/hackathon: one process, one SQLite file, one LLM provider, one folder of uploads.

### Components

| Layer | Tech | Responsibility |
|---|---|---|
| Frontend | React + Vite + Tailwind | Patient list, upload, timeline view, summary view |
| API Gateway | FastAPI | REST endpoints, auth (basic), file upload |
| Agent Orchestrator | Python module (`app/agents/orchestrator.py`) | Routes records through ingestion → structuring → memory → analysis |
| Ingestion / Parsers | `pdfplumber`, `PyMuPDF`, `pytesseract`, `Pillow` | Convert PDF/image/text into raw text + image bytes |
| LLM Provider | OpenAI (or Anthropic) | Structuring, vision, change-detection, summaries |
| Memory / DB | SQLite + SQLAlchemy | Patients, raw records, structured events, summaries, changes |
| Object Storage | Local `storage/` folder (swap to S3 later) | Original uploaded files |

### Data Flow

```
[Doctor uploads file]
        |
        v
 FastAPI /upload  ──>  saves blob to storage/, creates `records` row (status=pending)
        |
        v
 Orchestrator  ──> IngestionAgent (text? pdf? image?)
        |                |
        |                +--> PDFParser  (pdfplumber + PyMuPDF for embedded images)
        |                +--> VisionAgent (OCR + GPT-4V/Claude Vision description)
        |                +--> Plain text passthrough
        |
        v
 StructuringAgent (LLM)  ──> normalized JSON: vitals, diagnoses, medications, labs, notes, recorded_at
        |
        v
 MemoryAgent  ──> persists `events` (one per clinical fact) tied to record + patient
        |
        v
 ChangeDetectionAgent  ──> diff vs latest prior events for this patient → `changes` row, risk level
        |
        v
 SummaryAgent (on request)  ──> reads timeline + recent changes → `summaries` row
        |
        v
 React dashboard polls /timeline and /summary
```

The pipeline runs **synchronously for MVP** (small files, single user). Add Celery/RQ only if you need it for the demo.

---

## Step 2 — The Agents

Each agent is a small Python class with a single `run()` method. They are pure functions over inputs except `MemoryAgent`, which writes to the DB.

### 1. `IngestionAgent`
- **Role:** Detect file type and dispatch to the right parser.
- **Input:** `{file_path, mime_type, source_type}`
- **Output:** `{raw_text: str, images: list[bytes], metadata: dict}`

### 2. `VisionAgent`
- **Role:** Describe medical images (X-ray, dermatology photo, scanned chart) and OCR any text.
- **Input:** `image_bytes` + optional context (e.g., "chest X-ray")
- **Output:** `{ocr_text: str, description: str, findings: list[str]}`
- **Implementation:** GPT-4o / Claude Sonnet vision endpoint + Tesseract fallback for pure OCR.

### 3. `StructuringAgent`
- **Role:** Turn unstructured text into a normalized clinical JSON.
- **Input:** `{raw_text, vision_output?, patient_context}`
- **Output:** `StructuredRecord` (Pydantic model — see schema below)
- **Prompt strategy:** Few-shot, JSON-only output, validated against Pydantic. Reject + retry once on parse failure.

### 4. `MemoryAgent`
- **Role:** Persist structured output as discrete `events` plus the original `record`.
- **Input:** `StructuredRecord`
- **Output:** record_id + list of event_ids; updates `records.status` to `processed`.

### 5. `TimelineAgent`
- **Role:** Build an ordered, filterable view of a patient's history.
- **Input:** `patient_id`, optional `since/until`, optional `event_type` filter.
- **Output:** `[{timestamp, event_type, description, severity, source_record_id}, ...]`

### 6. `ChangeDetectionAgent`
- **Role:** Compare current record's events to the most recent prior snapshot for the same patient.
- **Input:** `patient_id`, `current_record_id`
- **Output:** `{deltas: [...], risk_level: "low|moderate|high", flags: [...]}`
- **Approach:** Deterministic diffing on numeric fields (BP, HbA1c, etc.) + LLM call to interpret narrative deltas.

### 7. `SummaryAgent`
- **Role:** Doctor-facing brief.
- **Input:** `patient_id`, optional `window` (e.g., last 90 days)
- **Output:** Markdown summary with sections: *Active issues, Trends, Recent changes, Suggested follow-ups*.

---

## Step 3 — Database Schema

SQLite via SQLAlchemy. JSON columns where helpful.

```sql
patients
  id              INTEGER PK
  external_id     TEXT UNIQUE      -- MRN or generated
  name            TEXT
  dob             DATE
  gender          TEXT
  created_at      DATETIME

records                            -- one per uploaded artifact
  id              INTEGER PK
  patient_id      INTEGER FK
  source_type     TEXT             -- 'text' | 'pdf' | 'image'
  file_path       TEXT
  raw_text        TEXT
  structured_json TEXT (JSON)
  status          TEXT             -- 'pending' | 'processed' | 'failed'
  recorded_at     DATETIME         -- when the clinical event happened
  created_at      DATETIME

events                             -- atomic facts derived from records
  id              INTEGER PK
  patient_id      INTEGER FK
  record_id       INTEGER FK
  event_type      TEXT             -- 'vital' | 'diagnosis' | 'medication' | 'lab' | 'note' | 'imaging'
  code            TEXT             -- e.g., 'systolic_bp', 'HbA1c', ICD-10 code
  value_text      TEXT
  value_num       REAL
  unit            TEXT
  severity        TEXT             -- 'info' | 'warn' | 'critical'
  recorded_at     DATETIME
  created_at      DATETIME

changes                            -- output of ChangeDetectionAgent
  id              INTEGER PK
  patient_id      INTEGER FK
  from_record_id  INTEGER FK
  to_record_id    INTEGER FK
  delta_json      TEXT (JSON)
  risk_level      TEXT             -- 'low' | 'moderate' | 'high'
  notes           TEXT
  created_at      DATETIME

summaries
  id              INTEGER PK
  patient_id      INTEGER FK
  window_days     INTEGER
  content_md      TEXT
  model           TEXT
  created_at      DATETIME
```

**Indexes:** `events(patient_id, recorded_at)`, `records(patient_id, created_at)`. That's enough for the MVP.

---

## Step 4 — 12-Day MVP Plan

Built so you have a demo-able product by Day 9 and polish through Day 12.

| Day | Goal | Output |
|---|---|---|
| 1 | Repo scaffold, FastAPI bootstrap, SQLAlchemy models, Alembic-free init script | `uvicorn` runs, `/health` returns 200 |
| 2 | Patient CRUD endpoints + Pydantic schemas | `POST /patients`, `GET /patients/{id}` |
| 3 | File upload endpoint + local storage | `POST /patients/{id}/records` accepts pdf/png/txt |
| 4 | PDF parser (pdfplumber for text, PyMuPDF for images) | Raw text extracted on upload |
| 5 | Vision agent + Tesseract OCR fallback | Image upload returns description + OCR |
| 6 | StructuringAgent (LLM → Pydantic JSON), MemoryAgent persists events | Events visible in DB after upload |
| 7 | TimelineAgent + `GET /patients/{id}/timeline` | Frontend-ready chronological JSON |
| 8 | ChangeDetectionAgent + `GET /patients/{id}/changes` | Risk flag on second upload |
| 9 | SummaryAgent + `POST /patients/{id}/summary` | Markdown summary returned |
| 10 | React scaffold: patient list, upload form | UI hits real backend |
| 11 | Timeline visualization + summary view | End-to-end demo path works |
| 12 | Seed demo data, error handling, README, deploy script | Hackathon demo locked |

**Cut list if you fall behind:** drop the React frontend (use Swagger UI), drop ChangeDetectionAgent's LLM half (keep numeric diffs only), drop multi-image handling.

---

## Step 5 — Starter Backend Code

The starter backend lives in `careflow/backend/`. Highlights:

- `app/main.py` — FastAPI app, routers, CORS
- `app/db/models.py` — SQLAlchemy models matching the schema above
- `app/db/session.py` — engine + session factory + `init_db()`
- `app/schemas.py` — Pydantic request/response models, including `StructuredRecord`
- `app/agents/` — one file per agent (`ingestion`, `vision`, `structuring`, `memory`, `timeline`, `change_detection`, `summary`) plus `orchestrator.py`
- `app/parsers/` — `pdf.py`, `image.py`, `text.py`
- `app/routers/` — `patients.py`, `records.py`, `analysis.py`
- `app/llm.py` — single chokepoint for OpenAI/Anthropic calls (easy to swap)
- `requirements.txt`, `.env.example`, `README.md`

Key endpoints:

```
POST   /patients                                  create patient
GET    /patients                                  list patients
GET    /patients/{id}                             patient detail
POST   /patients/{id}/records                     upload (multipart) → triggers pipeline
GET    /patients/{id}/records                     list raw records
GET    /patients/{id}/timeline                    chronological events
GET    /patients/{id}/changes                     detected deltas + risks
POST   /patients/{id}/summary                     generate doctor summary (window_days optional)
GET    /health
```

See `careflow/backend/` for the running code.

---

## Step 6 — PDF Parsing & Image Analysis

### PDFs
- **Primary:** `pdfplumber` — clean text + tables (good for lab reports).
- **Embedded images:** `PyMuPDF` (`fitz`) — extract images per page; pass each into `VisionAgent`.
- **Scanned PDFs (image-only):** detect by checking if `pdfplumber` extracts < 30 chars; fall back to rasterizing with PyMuPDF and OCR'ing each page via Tesseract, then send the rasterized page to vision LLM if the OCR is messy.

### Images
- **Cheap path:** `pytesseract` for any printed text (lab printouts, prescription scans).
- **Smart path:** Send image (base64) to GPT-4o or Claude Sonnet vision with a structured prompt:
  > *"You are a clinical assistant. Describe this medical image. Return JSON with keys: modality, body_region, findings (list), ocr_text, urgent (bool)."*
- **Privacy reminder:** for a real product you'd never send PHI to a third-party LLM without a BAA. For the hackathon demo: use synthetic patients only and add a banner.

### Practical defaults for MVP
- Skip DICOM. Accept JPEG/PNG/PDF only.
- Reject files > 10 MB.
- Cache LLM results keyed by file SHA-256 so re-uploads don't burn tokens.

---

## Tech-stack notes / suggested tweaks

- **DB:** Stay on **SQLite** for MVP. Firebase adds auth complexity you don't need. If you later want real-time UI updates, switch to Postgres + a `/events/stream` SSE endpoint — simpler than Firebase.
- **Auth:** Skip real auth. One hardcoded API key in a header is enough for the demo.
- **LLM client:** Wrap calls in `app/llm.py` so swapping OpenAI ↔ Anthropic is a one-line change.
- **Vector DB:** *Not needed for MVP.* Patient memory is structured (events table). Add pgvector only when you want semantic search across notes.
- **Frontend:** Vite + React + Tailwind + a single chart lib (`recharts`). Don't bring in a UI framework.

---

## What "done" looks like for the demo

1. Upload three records for a fake patient over a simulated 6-month span (a discharge note PDF, a lab report PDF, a prescription photo).
2. Open the patient page → see a timeline with events grouped by date.
3. See a *"Risk increased: HbA1c trending up, BP uncontrolled"* card from ChangeDetectionAgent.
4. Click *Generate summary* → get a 200-word doctor-ready brief.

That's the whole pitch. Build toward that screenshot.
