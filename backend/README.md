# CareFlow Backend (MVP)

Multi-agent healthcare pipeline. FastAPI + SQLite + OpenAI.

## Quickstart

```bash
cd careflow/backend
python -m venv .venv && source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env                                  # add your OPENAI_API_KEY
python -m app.db.init_db                              # creates careflow.db
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the Swagger UI.

## Demo flow

1. `POST /patients` — create a patient.
2. `POST /patients/{id}/records` — upload a PDF, image, or .txt file.
3. `GET /patients/{id}/timeline` — see chronological events.
4. `GET /patients/{id}/changes` — see deltas/risk after the second upload.
5. `POST /patients/{id}/summary` — generate a doctor-ready summary.

## Layout

```
app/
  main.py              FastAPI app + router includes
  config.py            Settings (pydantic-settings)
  llm.py               LLM provider chokepoint
  schemas.py           Pydantic request/response + StructuredRecord
  db/
    session.py         Engine, SessionLocal
    models.py          SQLAlchemy models
    init_db.py         Creates tables (run once)
  parsers/
    text.py
    pdf.py
    image.py
  agents/
    ingestion.py
    vision.py
    structuring.py
    memory.py
    timeline.py
    change_detection.py
    summary.py
    orchestrator.py
  routers/
    patients.py
    records.py
    analysis.py
storage/                Uploaded files
```

## Notes

- Use synthetic data only. No PHI without a BAA.
- Files > 10 MB are rejected by default (`MAX_UPLOAD_MB`).
- Swap LLM provider by editing `app/llm.py`.
