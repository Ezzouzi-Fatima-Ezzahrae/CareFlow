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


## Compliance

- **Synthetic data only.** Never send real PHI — this implementation is not BAA-covered.
- **Not a medical device.** Decision support, not diagnosis.

## License

MIT.
