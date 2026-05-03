# CareFlow Dashboard

Standalone React + Tailwind + Recharts dashboard. The visual companion to the CareFlow MCP server — same deterministic logic, doctor-friendly UI.

## What's inside

- **Patient list** with severity dots
- **Risk overview** donut + critical/warning/normal counts
- **Latest measurements** color-coded horizontal bar chart
- **Trends over time** line charts per metric (HbA1c, BP, LDL, etc.) with severity-colored points
- **Doctor summary** deterministic Markdown brief
- **Visit timeline** chronological event list

All synthetic data. No LLM. No backend required for the demo.

## Run it

You need Node.js 18+ installed. Check with `node --version`.

```bash
cd careflow/frontend
npm install
npm run dev
```

Vite opens http://localhost:5173 automatically. The dashboard works immediately — Sarah Mansouri and James Okafor are pre-loaded.

## Build for production

```bash
npm run build
```

Output goes to `dist/`. You can serve it from any static host (Netlify, Vercel, GitHub Pages, or just drop it in your FastAPI backend's static folder).

## How this fits the hackathon submission

Two demos, one product:

1. **CareFlow MCP server on Prompt Opinion** — satisfies the hackathon protocol requirement (Path A: MCP).
2. **This dashboard** — visual story for the demo video, doctor-friendly UI judges remember.

Both share the same deterministic extraction logic (regex over clinical text, threshold-based severity scoring, no LLM).
