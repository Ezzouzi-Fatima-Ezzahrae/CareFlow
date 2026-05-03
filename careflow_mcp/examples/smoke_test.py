"""Smoke test — runs every CareFlow tool against the synthetic test files
without going through the MCP transport. Useful for local debugging.

Usage:
    cd careflow_mcp
    pip install -e .
    python examples/smoke_test.py
"""
from __future__ import annotations
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, PKG_ROOT)

from careflow_mcp.extractors import extract_events
from careflow_mcp.parsers import parse_pdf
from careflow_mcp.image_analysis import analyze_image
from careflow_mcp.analysis import detect_changes, detect_trends, generate_summary

TEST_FILES = os.path.abspath(os.path.join(PKG_ROOT, "..", "test_files"))


def header(label: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {label}")
    print("=" * 70)


def show_events(events: list, limit: int = 10) -> None:
    for e in events[:limit]:
        d = e.to_dict() if hasattr(e, "to_dict") else e
        print(f"  - [{d['event_type']:10}] {d.get('code') or '':18} "
              f"{d.get('value_num') if d.get('value_num') is not None else d.get('value_text') or ''} "
              f"{d.get('unit') or ''} ({d.get('severity')})")
    if len(events) > limit:
        print(f"  ... and {len(events) - limit} more")


def main() -> None:
    # --- 1. extract_clinical_events from text ------------------------------
    header("1. extract_clinical_events on plain text")
    sample = (
        "Discharge: BP 162/98 mmHg, HR 112 bpm, SpO2 91%. "
        "HbA1c 7.4%. LDL 138 mg/dL. eGFR 48. "
        "Diagnoses: I10, E11.9 (type 2 diabetes mellitus). "
        "On lisinopril 10 mg daily and metformin 500 mg BID."
    )
    events = extract_events(sample)
    print(f"Extracted {len(events)} events:")
    show_events(events)

    # --- 2. parse_pdf_document --------------------------------------------
    header("2. parse_pdf_document on discharge_summary.pdf")
    pdf_path = os.path.join(TEST_FILES, "discharge_summary.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    parsed = parse_pdf(pdf_bytes)
    print(f"  pages:        {parsed['page_count']}")
    print(f"  images:       {parsed['image_count']}")
    print(f"  scanned:      {parsed['scanned']}")
    print(f"  raw_text len: {len(parsed['raw_text'])}")
    print(f"  preview:      {parsed['raw_text'][:160]!r}")

    # --- 3. extract from PDF text -----------------------------------------
    header("3. extract_clinical_events on PDF text")
    pdf_events = extract_events(parsed["raw_text"])
    print(f"Extracted {len(pdf_events)} events from the discharge PDF:")
    show_events(pdf_events, limit=15)

    # --- 4. analyze_medical_image -----------------------------------------
    header("4. analyze_medical_image on chest_xray.png")
    img_path = os.path.join(TEST_FILES, "chest_xray.png")
    with open(img_path, "rb") as f:
        img_bytes = f.read()
    img_result = analyze_image(img_bytes)
    print(f"  modality:    {img_result['modality']}")
    print(f"  body_region: {img_result['body_region']}")
    print(f"  urgent:      {img_result['urgent']}")
    print(f"  findings:    {img_result['findings']}")
    print(f"  ocr chars:   {img_result['char_count']}")

    # --- 5. detect_risk_changes -------------------------------------------
    header("5. detect_risk_changes (prior vs current)")
    prior = [e.to_dict() for e in extract_events(
        "BP 142/88 mmHg. HbA1c 6.9%. Diagnoses: I10."
    )]
    current = [e.to_dict() for e in extract_events(
        "BP 168/102 mmHg. HbA1c 8.3%. Diagnoses: I10, E11.9."
    )]
    changes = detect_changes(prior, current)
    print(f"  risk_level:  {changes['risk_level']}")
    print(f"  summary:     {changes['summary']}")
    print(f"  deltas:")
    print(json.dumps(changes['deltas'], indent=2))

    # --- 6. detect_lab_trends ---------------------------------------------
    header("6. detect_lab_trends across pdf_events")
    trends = detect_trends([e.to_dict() for e in pdf_events])
    print(f"  trends found: {len(trends)}")
    for t in trends:
        print(f"    {t['code']}: {t['from']} → {t['to']} {t['unit'] or ''} "
              f"({t['direction']}, n={t['n_points']})")

    # --- 7. generate_doctor_summary ---------------------------------------
    header("7. generate_doctor_summary")
    md = generate_summary([e.to_dict() for e in pdf_events])
    print(md)

    # --- Done -------------------------------------------------------------
    header("ALL TOOLS RAN SUCCESSFULLY")
    print("If you see this, every CareFlow tool works without an LLM.")
    print("Next step: PUBLISH_TO_PROMPT_OPINION.md")


if __name__ == "__main__":
    main()
