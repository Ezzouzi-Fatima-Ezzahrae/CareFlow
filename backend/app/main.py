"""CareFlow FastAPI entrypoint."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db.session import Base, engine
from app.db import models  # noqa: F401  (register models for create_all)
from app.routers import analysis, patients, records


app = FastAPI(title="CareFlow API", version="0.1.0")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Permissive CORS for the demo. Lock down in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/debug/llm")
def debug_llm() -> dict:
    """Tells you exactly why the LLM is or isn't working. Hit it in the browser."""
    from app.config import settings
    from app import llm

    provider = (settings.llm_provider or "").lower()
    key_present = bool(llm._key_for(provider))
    masked_key = ""
    if key_present:
        k = llm._key_for(provider)
        masked_key = f"{k[:6]}…{k[-4:]} (len {len(k)})"

    sdk_status = {}
    try:
        if provider == "gemini":
            import google.generativeai as genai  # noqa: F401
            sdk_status["google-generativeai"] = "installed"
        else:
            import openai  # noqa: F401
            sdk_status["openai"] = "installed"
    except ImportError as e:
        sdk_status["error"] = f"package not installed: {e}"

    test_call: dict = {"attempted": False}
    if key_present and "error" not in sdk_status:
        test_call["attempted"] = True
        try:
            out = llm.chat_json(
                "You return JSON.",
                "Reply with {\"ok\": true, \"echo\": \"hello\"}",
            )
            test_call["raw"] = out[:500]
            test_call["is_stub"] = '"stub": true' in out
        except Exception as e:
            test_call["error"] = repr(e)

    return {
        "provider": provider,
        "model": settings.gemini_model if provider == "gemini" else settings.llm_model,
        "vision_model": settings.gemini_vision_model if provider == "gemini" else settings.vision_model,
        "key_present": key_present,
        "masked_key": masked_key,
        "sdk": sdk_status,
        "test_call": test_call,
    }


@app.get("/debug/env_source")
def debug_env_source() -> dict:
    """Show where the Gemini key is actually coming from. Crucial when an OS-level
    env var is overriding the .env file."""
    import os
    from app.config import settings
    env_path = os.path.abspath(".env")
    env_exists = os.path.exists(env_path)
    env_mtime = None
    env_first_lines: list[str] = []
    if env_exists:
        env_mtime = os.path.getmtime(env_path)
        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().startswith("GEMINI_API_KEY"):
                    # mask the value
                    if "=" in line:
                        k, v = line.split("=", 1)
                        v = v.strip()
                        if len(v) > 10:
                            env_first_lines.append(f"{k}={v[:6]}…{v[-4:]} (len {len(v)})")
                        else:
                            env_first_lines.append(f"{k}=<empty or too short>")
    os_var = os.environ.get("GEMINI_API_KEY", "")
    os_var_masked = ""
    if os_var:
        os_var_masked = f"{os_var[:6]}…{os_var[-4:]} (len {len(os_var)})"
    loaded = settings.gemini_api_key
    loaded_masked = f"{loaded[:6]}…{loaded[-4:]} (len {len(loaded)})" if loaded else ""
    return {
        "cwd": os.getcwd(),
        "dotenv_path": env_path,
        "dotenv_exists": env_exists,
        "dotenv_mtime": env_mtime,
        "dotenv_gemini_lines": env_first_lines,
        "os_env_GEMINI_API_KEY": os_var_masked or "<not set>",
        "loaded_into_settings": loaded_masked,
        "verdict": (
            "OS env var is overriding .env" if os_var and os_var == loaded
            else ".env file is the source" if loaded and (env_first_lines and loaded[-4:] in env_first_lines[0])
            else "unclear — compare last-4 chars manually"
        ),
    }


@app.get("/debug/gemini_models")
def debug_gemini_models() -> dict:
    """List Gemini models your API key can use. Helps when a model name is deprecated."""
    from app.config import settings
    if not settings.gemini_api_key:
        return {"error": "no GEMINI_API_KEY set"}
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        rows = []
        for m in genai.list_models():
            if "generateContent" in (m.supported_generation_methods or []):
                rows.append({
                    "name": m.name,
                    "display_name": m.display_name,
                    "input_token_limit": m.input_token_limit,
                })
        return {"current_setting": settings.gemini_model, "available_for_generateContent": rows}
    except Exception as e:
        return {"error": repr(e)}


@app.get("/debug/last_record/{patient_id}")
def debug_last_record(patient_id: int) -> dict:
    """Returns the raw text and structured JSON of the latest record so you
    can see what the pipeline actually extracted."""
    from app.db.session import SessionLocal
    from app.db import models
    db = SessionLocal()
    try:
        rec = (db.query(models.Record)
                 .filter(models.Record.patient_id == patient_id)
                 .order_by(models.Record.created_at.desc())
                 .first())
        if not rec:
            return {"error": "no records for this patient"}
        events = db.query(models.Event).filter(models.Event.record_id == rec.id).count()
        return {
            "record_id": rec.id,
            "source_type": rec.source_type,
            "status": rec.status,
            "raw_text_preview": (rec.raw_text or "")[:600],
            "raw_text_length": len(rec.raw_text or ""),
            "structured_json_preview": (rec.structured_json or "")[:600],
            "events_extracted": events,
        }
    finally:
        db.close()


app.include_router(patients.router)
app.include_router(records.router)
app.include_router(analysis.router)


# Serve the dashboard at "/" (must be added LAST so /patients, /docs, etc. take precedence).
@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
