# Publish CareFlow to the Prompt Opinion Marketplace

This is the gating step for the *Agents Assemble — The Healthcare AI Endgame* hackathon. Until your project is **discoverable and invokable inside Prompt Opinion**, judges won't even score it.

Follow these steps in order.

---

## 1. Make sure the MCP server runs locally

```cmd
cd C:\Users\Fatima ezzahrae\Documents\A2A_Healthcare\careflow\careflow_mcp
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e .
```

Then test it:
```cmd
careflow-mcp
```

You should see the server start and wait for input on stdio (looks like nothing's happening — that's correct). Press `Ctrl+C` to stop.

Quick sanity check via the MCP inspector (opens a browser UI):
```cmd
mcp dev careflow_mcp/server.py
```

Click each tool, hit *Run*, confirm none crash. Hit `careflow_info` first — should return `"llm_required": false` and list 8 tools.

---

## 2. Sign up for Prompt Opinion

1. Go to **https://app.promptopinion.ai**.
2. Create a free account (the hackathon rules require this).
3. Verify your email.

---

## 3. Add CareFlow as an MCP server inside Prompt Opinion

The exact UI may have shifted, but the canonical flow is:

1. Top-right menu → **Configuration** (or **Settings**) → **MCP Servers** → **+ New Server**.
2. Pick a name: `CareFlow`.
3. Pick transport: **stdio** (the default).
4. **Command:** `careflow-mcp`
   - If that's not on PATH on the host where PO runs, use: `python` and **Args:** `["-m", "careflow_mcp.server"]`
   - If PO runs in their cloud and needs to install your package, point them at this repo (see step 4).
5. Save.
6. Click **Test connection**. You should see all 8 tools listed.

If your PO instance only supports HTTP/SSE servers, run:
```cmd
python -c "from careflow_mcp.server import main_sse; main_sse()"
```
and configure PO with the SSE URL it prints (usually `http://localhost:8000/sse`).

---

## 4. Make it installable (so PO's cloud can fetch it)

Push your repo to GitHub (see `GITHUB.md`), then in PO's MCP server config you can typically point at:

```
git+https://github.com/YOUR_USERNAME/careflow.git#subdirectory=careflow_mcp
```

That tells PO to `pip install` your package. Confirm with PO support if their UI accepts `git+` URLs — if not, publish to PyPI:

```cmd
cd careflow_mcp
pip install build twine
python -m build
twine upload dist/*
```

(You'll need a free PyPI account.)

---

## 5. Build a test agent inside Prompt Opinion

This proves end-to-end integration for the demo video.

1. **Agents → New Agent.**
2. Name: `CareFlow Demo Agent`.
3. Model: pick any of the free models PO provides (GitHub GPT-4.1 or Gemini Flash). **You don't need your own LLM key** — PO supplies it.
4. **Connected Tools:** check every tool from the `CareFlow` MCP server.
5. **System prompt** (paste this verbatim):

   ```
   You are CareFlow's clinical assistant. When the user provides clinical text,
   PDFs, or images, use the CareFlow tools to:
     1. Extract structured events (extract_clinical_events or ingest_clinical_record).
     2. If they provide a prior record, call detect_risk_changes.
     3. Always finish with generate_doctor_summary and present the Markdown brief.
   Use the deterministic CareFlow tools — do not extract events yourself.
   ```

6. Save.
7. Test it: paste a clinical snippet like:
   > *"Patient: BP 162/98 mmHg, HR 112 bpm, HbA1c 7.4%. Diagnoses: hypertension, type 2 diabetes. On lisinopril 10 mg daily."*

   The agent should call `extract_clinical_events`, then `generate_doctor_summary`, and reply with a structured brief.

---

## 6. Publish to the Marketplace

1. Open the agent's **Publish / Share** menu.
2. Add description, tags (`healthcare`, `mcp`, `multi-agent`).
3. Set visibility to **Public**.
4. Submit.
5. Copy the public Marketplace URL — this goes into your Devpost submission.

---

## 7. Record the demo video (max 3 min)

Hackathon requires the video to **show your project working inside the Prompt Opinion platform**. So:

1. Open your published agent on PO.
2. Paste a clinical snippet → show it calling CareFlow tools → show the structured output.
3. Upload `discharge_summary.pdf` → show ingestion + summary.
4. Show the agent calling `detect_risk_changes` between two records.
5. End on the Marketplace listing page.

Video script template is in `DEMO_VIDEO.md` — adapt the wording to mention "Prompt Opinion" and "MCP" prominently.

---

## 8. Devpost submission checklist

- [ ] Public repo URL (GitHub).
- [ ] **Public Marketplace URL** of your CareFlow agent on Prompt Opinion.
- [ ] Demo video URL (YouTube/Vimeo, < 3 min, shows it running inside PO).
- [ ] Text description: copy the top section of `careflow_mcp/README.md`.
- [ ] Confirm "synthetic data only" checkbox.

---

## Common problems

| Symptom | Fix |
|---|---|
| `careflow-mcp: command not found` after `pip install -e .` | Reactivate the venv. On Windows: `.venv\Scripts\activate.bat`. |
| PO inspector says "0 tools found" | Server isn't speaking stdio MCP — check `python -m careflow_mcp.server` runs without error. |
| Agent picks the wrong tool | Tighten the system prompt in step 5 — be explicit which tool to call when. |
| Tesseract OCR returns empty | Tesseract isn't installed where PO runs. The `analyze_medical_image` tool will still return modality/findings via OCR-less heuristics. |

---

## What this satisfies in the hackathon rules

- **Marketplace Verified** ✓ (step 6)
- **Protocol Adherence (MCP)** ✓ (FastMCP server in `careflow_mcp/`)
- **Platform Integration** ✓ (steps 3 + 5: agent calls your tools)
- **Safety Compliance** ✓ (synthetic data only, disclaimer in README)

That's all four Stage-One gates.
