"""Single chokepoint for LLM calls. Provider-agnostic.

Supports:
  - 'gemini' (free)   →  google-generativeai
  - 'openai' (paid)   →  openai

All public functions return strings. They never raise — if the provider has
no key, hits a quota, or errors out, callers get a stub sentinel they can
detect and fall back on. This keeps the demo running even with no internet.
"""
from __future__ import annotations
import base64
import json
import logging
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)


# Sentinel that callers (e.g. SummaryAgent) check to fall back to a
# deterministic, no-LLM output that still looks reasonable in a demo.
STUB_TEXT = "[[CAREFLOW_STUB]]"


def _provider() -> str:
    return (settings.llm_provider or "gemini").lower()


def _key_for(provider: str) -> str:
    return settings.gemini_api_key if provider == "gemini" else settings.openai_api_key


def _stub_json(reason: str) -> str:
    return json.dumps({
        "stub": True, "reason": reason,
        "events": [], "ocr_text": "", "description": "", "findings": [],
    })


# ============================== Gemini ====================================

def _gemini_model(model_name: str):
    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(model_name)


def _gemini_chat_json(system: str, user: str, model: str) -> str:
    m = _gemini_model(model)
    prompt = f"{system}\n\nReturn ONLY valid JSON. No prose, no markdown fences.\n\n{user}"
    resp = m.generate_content(
        prompt,
        generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
    )
    return (resp.text or "{}").strip()


def _gemini_chat_text(system: str, user: str, model: str) -> str:
    m = _gemini_model(model)
    resp = m.generate_content(
        f"{system}\n\n{user}",
        generation_config={"temperature": 0.2},
    )
    return (resp.text or "").strip()


def _gemini_vision(image_bytes: bytes, prompt: str, model: str) -> str:
    m = _gemini_model(model)
    resp = m.generate_content(
        [
            f"{prompt}\n\nReturn ONLY valid JSON. No prose, no markdown fences.",
            {"mime_type": "image/png", "data": image_bytes},
        ],
        generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
    )
    return (resp.text or "{}").strip()


# ============================== OpenAI ====================================

def _openai_client():
    from openai import OpenAI
    return OpenAI(api_key=settings.openai_api_key)


def _openai_chat_json(system: str, user: str, model: str) -> str:
    resp = _openai_client().chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.1,
    )
    return resp.choices[0].message.content or "{}"


def _openai_chat_text(system: str, user: str, model: str) -> str:
    resp = _openai_client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


def _openai_vision(image_bytes: bytes, prompt: str, model: str) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    resp = _openai_client().chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        temperature=0.1,
    )
    return resp.choices[0].message.content or "{}"


# ============================== Public API ================================

def chat_json(system: str, user: str, model: Optional[str] = None) -> str:
    """JSON-mode chat completion. Returns raw string. Stubs on any failure."""
    p = _provider()
    if not _key_for(p):
        return _stub_json(f"no API key for provider={p}")
    try:
        if p == "gemini":
            return _gemini_chat_json(system, user, model or settings.gemini_model)
        return _openai_chat_json(system, user, model or settings.llm_model)
    except Exception as exc:
        log.warning("chat_json fell back to stub: %s", exc)
        return _stub_json(str(exc))


def chat_text(system: str, user: str, model: Optional[str] = None) -> str:
    """Plain-text completion. Returns STUB_TEXT on failure (callers fall back)."""
    p = _provider()
    if not _key_for(p):
        return STUB_TEXT
    try:
        if p == "gemini":
            return _gemini_chat_text(system, user, model or settings.gemini_model)
        return _openai_chat_text(system, user, model or settings.llm_model)
    except Exception as exc:
        log.warning("chat_text fell back to stub: %s", exc)
        return STUB_TEXT


def vision_describe(image_bytes: bytes, prompt: str) -> str:
    """Vision call. JSON output. Stubs on any failure."""
    p = _provider()
    if not _key_for(p):
        return _stub_json(f"no API key for provider={p}")
    try:
        if p == "gemini":
            return _gemini_vision(image_bytes, prompt, settings.gemini_vision_model)
        return _openai_vision(image_bytes, prompt, settings.vision_model)
    except Exception as exc:
        log.warning("vision_describe fell back to stub: %s", exc)
        return _stub_json(str(exc))
