# CareFlow — MCP Server

> Deterministic healthcare timeline & risk-detection tools for any AI agent. Built for the *Agents Assemble — The Healthcare AI Endgame* hackathon on the Prompt Opinion platform.

CareFlow is a **Model Context Protocol (MCP) server** that exposes 8 specialized tools for working with patient records. Any LLM-powered agent can call these tools to ingest documents, extract structured clinical events, detect risk evolution, and produce doctor-ready summaries — without writing its own extraction or parsing code.

**Why deterministic?** Every tool runs without an LLM. That makes them fast, free, predictable, auditable, and safe — exactly what a real clinical workflow needs.

---

## Tools exposed

| Tool | What it does |
|---|---|
| `extract_clinical_events` | Pulls vitals, labs, diagnoses, and medications from free-text using a regex-based clinical extractor. |
| `parse_pdf_document` | Extracts text + embedded images from a PDF (pdfplumber + PyMuPDF). |
| `analyze_medical_image` | OCRs a medical image and infers modality (CXR, ECG, lab printout, etc.) and likely findings. |
| `ingest_clinical_record` | One-shot multimodal ingest — accepts text, PDF, and/or image, returns normalized events. |
| `detect_risk_changes` | Diffs two event sets, returns risk level (low/moderate/high) plus per-code deltas. |
| `detect_lab_trends` | Identifies first→last trends for every numeric code across a patient's timeline. |
| `generate_doctor_summary` | Builds a Markdown brief: Active issues, Trends, Recent meds, Suggested follow-ups. |
| `careflow_info` | Smoke test — returns server version + tool list. |

All tools are pure functions over their inputs. They never call out to a paid API.

---

## Quick install

```bash
cd careflow_mcp
pip install -e .
careflow-mcp                # runs over stdio
```

Or run directly:
```bash
python -m careflow_mcp.server
```

The server speaks the MCP protocol over stdio by default — the standard transport used by Prompt Opinion, Claude Desktop, and most MCP hosts.

---

## Publish to the Prompt Opinion Marketplace

Step-by-step in [`PUBLISH_TO_PROMPT_OPINION.md`](../PUBLISH_TO_PROMPT_OPINION.md). Short version:

1. Create an account at https://app.promptopinion.ai.
2. Open *Configuration → MCP Servers → New*.
3. Choose **stdio** transport, command `careflow-mcp`, args `[]` (or point at `python -m careflow_mcp.server`).
4. Save → Test connection → confirm all 8 tools appear.
5. Submit to the Marketplace via the *Publish* button.

The hackathon requires the project to be **discoverable and invokable from the Prompt Opinion platform** to pass Stage One. Following the steps above satisfies that.

---

## Quick test (no Prompt Opinion needed)

```bash
# Install the MCP CLI tools (already in requirements)
pip install -e .

# Start the inspector — opens a web UI to call your tools manually
mcp dev careflow_mcp/server.py
```

Then call `careflow_info` from the inspector — should return the tool list and `"llm_required": false`.

To test event extraction with no setup:
```bash
python - <<'PY'
from careflow_mcp.extractors import extract_events
text = """
Discharge: BP 162/98 mmHg, HR 112 bpm. HbA1c 7.4%. LDL 138 mg/dL.
Diagnoses: I10, E11.9. Discharged on lisinopril 10 mg daily and metformin 500 mg BID.
"""
for e in extract_events(text):
    print(e)
PY
```

You'll see 8+ extracted events.

---

## Test files

The `careflow/test_files/` folder contains synthetic patient documents you can feed through any tool:

- `discharge_summary.pdf` — narrative + structured fields, exercises `parse_pdf_document` + `extract_clinical_events`.
- `lab_report.pdf` — dense numeric labs.
- `chest_xray.png` — synthetic CXR with annotations, exercises `analyze_medical_image`.
- `cxr_report_with_image.pdf` — radiology report + embedded image, exercises `ingest_clinical_record`.

All synthetic. **No PHI.**

---

## Tech notes

- **Python 3.10+**, MCP Python SDK (`mcp[cli]>=1.2.0`).
- PDF parsing: `pdfplumber` (text) + `PyMuPDF` (images, rasterization).
- Image OCR: `pytesseract` + `Pillow`.
- All extraction logic is pure regex + threshold tables — auditable and reproducible.

## Compliance

- Synthetic data only. **No PHI.** Never send real patient information through this tool — it isn't BAA-covered.
- Not a medical device. Output is decision-support, not diagnosis.

## License

MIT.
