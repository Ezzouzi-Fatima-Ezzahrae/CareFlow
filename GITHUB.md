# Push CareFlow to GitHub

Step-by-step. Takes ~5 minutes.

## 1. Create the repo on GitHub

1. Go to https://github.com/new
2. **Repository name:** `careflow`
3. **Public** (so judges can see it)
4. **Don't** initialize with README or .gitignore — we already have them.
5. Click **Create repository**.
6. Copy the URL — it looks like `https://github.com/YOUR_USERNAME/careflow.git`.

## 2. Initialize and push (run these in VS Code's terminal)

From inside the `careflow` folder:

```cmd
cd C:\Users\Fatima ezzahrae\Documents\A2A_Healthcare\careflow
git init
git branch -M main
git add .
git commit -m "Initial commit: CareFlow MVP"
git remote add origin https://github.com/YOUR_USERNAME/careflow.git
git push -u origin main
```

If git asks you to log in, a browser window will pop up — sign in to GitHub and confirm.

## 3. Verify

Refresh your repo page. You should see:

- `README.md` rendered as the homepage
- `backend/` folder with all the code
- `ARCHITECTURE.md`, `SETUP_WINDOWS.md`, `DEMO_VIDEO.md`, etc.
- **No** `.venv/`, **no** `.env`, **no** `careflow.db` — those are git-ignored.

## 4. Final touches that judges notice

On the GitHub repo page:

1. Click the gear icon next to **About** (top right) → add a one-line description and topics:
   - **Description:** *AI-powered medical timeline + risk detection. Multi-agent pipeline over patient PDFs, images, and notes.*
   - **Topics:** `healthcare`, `ai`, `multi-agent`, `fastapi`, `hackathon`, `openai`
   - **Website:** your live demo URL once deployed (or leave blank)

2. *(Optional)* Add a screenshot to the README. Take a screenshot of `http://127.0.0.1:8000` (the dashboard with Sarah's seeded data and the red risk badge), save it as `docs/screenshot.png`, then add this near the top of `README.md`:
   ```markdown
   ![CareFlow dashboard](docs/screenshot.png)
   ```

## 5. (Optional) Deploy a live URL

For a public demo URL judges can click:

- **Easiest free option: Render.com**
  1. Sign up → New → Web Service → connect your GitHub repo.
  2. **Build command:** `pip install -r backend/requirements.txt`
  3. **Start command:** `cd backend && python -m app.db.init_db && python -m scripts.seed_demo && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  4. **Environment:** add `OPENAI_API_KEY` in the dashboard.
  5. Deploy. You'll get a URL like `https://careflow.onrender.com`.

- **Alternative: Railway.app** — same pattern, slightly faster.

Add the live URL to the top of your README and to the GitHub *Website* field.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `git: command not found` | Install Git from https://git-scm.com/download/win |
| `permission denied (publickey)` | Use HTTPS URL (`https://github.com/...`), not SSH (`git@github.com:...`) |
| Push asks for password | GitHub no longer accepts passwords. Use a [Personal Access Token](https://github.com/settings/tokens) — paste it where it asks for password. |
| `careflow.db` got committed by accident | `git rm --cached backend/careflow.db` then commit again. |
