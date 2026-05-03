# CareFlow

> **Healthcare timeline & risk-detection tools as an MCP server.** Built for *Agents Assemble — The Healthcare AI Endgame* on the Prompt Opinion platform.

[![MCP](https://img.shields.io/badge/protocol-MCP-blue)](https://modelcontextprotocol.io) ![Deterministic](https://img.shields.io/badge/LLM-not%20required-brightgreen) ![Status](https://img.shields.io/badge/status-hackathon%20MVP-orange)

---

## What it is

CareFlow is a **Model Context Protocol (MCP) server** that exposes 8 deterministic healthcare tools any AI agent can call:

- Parse clinical PDFs and medical images
- Extract structured clinical events (vitals, labs, diagnoses, medications)
- Compare two patient records and report risk evolution
- Generate doctor-ready summaries

**Every tool runs without an LLM.** That makes them fast, free, predictable, and auditable — exactly what real clinical workflows need.

The MCP server is published to the **Prompt Opinion Marketplace** so any agent on the PO platform can ingest patient documents and build a longitudinal timeline without writing its own extraction code.

---

## Project structure

```
careflow/
├── README.md                          ← you are here
├── PUBLISH_TO_PROMPT_OPINION.md       ← step-by-step deployment to the hackathon platform
├── ARCHITECTURE.md                    ← original design doc (still mostly accurate)
├── DEMO_VIDEO.md                      ← 90s recording script
├── GITHUB.md                          ← push the repo to GitHub
├── CareFlow_Pitch.pptx                ← pitch deck (8 slides)
│
├── careflow_mcp/                      ← THE HACKATHON SUBMISSION (MCP server)
│   ├── careflow_mcp/
│   │   ├── server.py                  ← FastMCP server, 8 tools
│   │   ├── extractors.py              ← regex clinical-event extractor
│   │   ├── parsers.py                 ← PDF + image + OCR
│   │   ├── image_analysis.py          ← deterministic image classifier
│   │   └── analysis.py                ← change detection, trend, summary
│   ├── pyproject.toml
│   └── README.md                      ← MCP-focused readme
│
├── test_files/                        ← synthetic patient documents
│   ├── discharge_summary.pdf
│   ├── lab_report.pdf
│   ├── chest_xray.png
│   └── cxr_report_with_image.pdf
│
└── backend/                           ← the original standalone FastAPI prototype
                                        (kept as a reference; the MCP server above
                                        is the actual hackathon submission)
```

---

## The 60-second pitch

1. Doctors lose hours per patient stitching scattered PDFs, lab printouts, and old notes.
2. CareFlow's MCP server gives any AI agent a one-line capability to ingest a record and get back structured events.
3. Two records in → CareFlow tells you what changed and how worried to be.
4. Three records in → CareFlow generates a 200-word doctor brief.
5. Because it's all deterministic regex + threshold logic, there's no LLM bill, no quota, no flaky output. Real clinics could deploy this tomorrow.

---

## Quickstart

```cmd
cd careflow_mcp
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e .
careflow-mcp                            # runs the server over stdio
```

Smoke-test in another terminal:
```cmd
mcp dev careflow_mcp/server.py          # opens the MCP inspector in your browser
```

Then publish it to Prompt Opinion → see [`PUBLISH_TO_PROMPT_OPINION.md`](./PUBLISH_TO_PROMPT_OPINION.md).

---

## What CareFlow's tools look like to an agent

```
extract_clinical_events(text)              → vitals, labs, diagnoses, meds (typed JSON)
parse_pdf_document(pdf_b64)                → raw text + page count + image count
analyze_medical_image(image_b64, context)  → modality, OCR text, findings, urgency flag
ingest_clinical_record(text, pdf, image)   → one-shot multimodal → events
detect_risk_changes(prior_json, curr_json) → low|moderate|high + per-code deltas
detect_lab_trends(events_json)             → first→last trend per numeric code
generate_doctor_summary(events_json)       → Markdown brief
careflow_info()                            → server version + tool list (smoke test)
```

The tools are pure: same input → same output, every time. Auditable in production.

---

## Demo path (for the video)

1. Open your published CareFlow agent in the Prompt Opinion platform.
2. Paste in a clinical text snippet → agent calls `extract_clinical_events` → structured events appear.
3. Upload `test_files/discharge_summary.pdf` → agent calls `ingest_clinical_record` → events appear.
4. Paste a second snippet → agent calls `detect_risk_changes` → risk badge + deltas.
5. Agent calls `generate_doctor_summary` → 200-word brief.
6. End on the public Marketplace listing.

---

## Compliance

- **Synthetic data only.** Never send real PHI — this implementation is not BAA-covered.
- **Not a medical device.** Decision support, not diagnosis.

## License

MIT.
