# CareFlow — Demo Video Script

A 60–90 second screen recording. Most hackathons cap at 2 minutes; aim for 75s.

---

## Before recording

1. **Run the app and seed it:**
   ```cmd
   python -m app.db.init_db
   python -m scripts.seed_demo
   uvicorn app.main:app --reload
   ```
2. Open `http://127.0.0.1:8000` in a clean browser window. Close all other tabs.
3. Set your screen resolution to **1920×1080** if possible (looks crisp on judging screens).
4. Have a small test PDF or image of any clinical text ready on your desktop — call it `lab_report.pdf`.
5. **Mute notifications.** Close Slack, email, Discord. Hide your taskbar.

## Recording tools (free, Windows)

- **OBS Studio** — best quality, https://obsproject.com/. Use *Display Capture*, 60fps, MP4.
- **Windows Game Bar** (`Win + G`) — built in, decent quality, no install needed.
- **Loom** — easiest if you want auto-upload + a sharable link. https://loom.com/

---

## The script — 75 seconds

> Speak naturally. Don't read this verbatim. The bracketed cues tell you what to do on screen.

### [0:00 – 0:08] Hook
> "Doctors lose hours per patient stitching PDFs, labs, and old notes together. Critical changes get buried. CareFlow fixes that."

*[Show a static screen: the CareFlow dashboard with Sarah Mansouri already loaded.]*

### [0:08 – 0:18] What it is
> "CareFlow is a multi-agent AI system that ingests any patient document — PDF, image, or text — and turns it into a clean medical timeline."

*[Click on the patient "Sarah Mansouri" in the left sidebar. The timeline scrolls into view.]*

### [0:18 – 0:32] The timeline
> "Here's a real patient view. Six months of records — a discharge note, lab results, a follow-up — all extracted automatically. Vitals, diagnoses, medications, labs are tagged and dated."

*[Hover over a couple of timeline entries — let the viewer see HbA1c values, BP readings.]*

### [0:32 – 0:48] The risk detection
> "Now look at the top — a *high risk* alert. CareFlow noticed Sarah's HbA1c climbed from 7.4 to 8.3 over six months while her blood pressure stayed uncontrolled. It also caught a new symptom: chest tightness on exertion."

*[Point to the red risk badge. Scroll to the "Detected changes" card. Pause for 2 seconds.]*

### [0:48 – 1:05] The summary
> "Click *Generate doctor summary*. CareFlow combines the timeline and the changes into a 200-word brief — active issues, trends, recent changes, suggested follow-ups."

*[Click the "Generate doctor summary" button. While it loads, talk through what's happening:]*

> "Under the hood: a chain of seven agents — ingestion, vision, structuring, memory, change-detection, summary — orchestrated by FastAPI."

*[Summary appears. Don't read it word-for-word; just hover.]*

### [1:05 – 1:15] Upload demo
> "And it works on new uploads in real time."

*[Drag `lab_report.pdf` into the upload form, click Upload. Wait for the timeline to update.]*

> "New events extracted, timeline updated, risk recomputed."

### [1:15 – 1:25] Close
> "Built in 12 days with FastAPI, SQLite, and OpenAI. Open source. Synthetic data only. Thank you."

*[Show the GitHub URL on screen for 2 seconds.]*

---

## Tips for a good recording

- **Move the mouse slowly.** Fast cursors look frantic on playback.
- **Pause 1 second after every click** so judges can see what changed.
- **Don't say "um."** Stop, breathe, restart. Editing pauses out is harder than re-recording.
- **One full take is better than spliced takes.** If you fluff a line, restart from the beginning. 75 seconds is short.
- **Record audio separately** if you can — way cleaner. Your phone's voice memo app is fine.
- **Watch your final cut at 1.5x.** If it still feels coherent, you're good. If it drags, you have too much.

## Common mistakes to avoid

- Reading the README on screen.
- Showing Swagger UI / `/docs`. Judges don't want to see JSON forms.
- Forgetting to seed the demo data — empty timeline = boring video.
- Recording at low resolution. Anything below 1280×720 looks cheap.
- Not testing audio. Always do a 5-second test clip first.

## File output

- Format: **MP4** (H.264).
- Length: **60–90 seconds**.
- Filename: `careflow_demo.mp4`.
- Upload to YouTube (unlisted) or Loom — paste the link in your hackathon submission.
