# CareFlow — Windows + VS Code Setup

Step-by-step to get the backend running on Windows using Visual Studio Code.

---

## 1. Install prerequisites (one-time)

1. **Python 3.11 or 3.12** — download from https://www.python.org/downloads/windows/ and during install **tick "Add Python to PATH"**.
2. **VS Code** — https://code.visualstudio.com/
3. **VS Code Python extension** — open VS Code → Extensions (Ctrl+Shift+X) → search "Python" by Microsoft → Install.
4. *(Optional, only if you want OCR for scanned images)* **Tesseract** — https://github.com/UB-Mannheim/tesseract/wiki → install the Windows installer → add `C:\Program Files\Tesseract-OCR` to your PATH. Skip this for now if you don't need OCR.

Verify Python:
```powershell
python --version
```
You should see `Python 3.11.x` or `3.12.x`.

---

## 2. Open the project in VS Code

1. Launch VS Code.
2. **File → Open Folder…** → choose `C:\Users\Fatima ezzahrae\Documents\A2A_Healthcare\careflow`.
3. Open the integrated terminal: **Terminal → New Terminal** (or `` Ctrl+` ``). It opens in PowerShell by default — that's fine.

---

## 3. Create a virtual environment

In the VS Code terminal:

```powershell
cd backend
python -m venv .venv
```

Activate it. **In PowerShell:**
```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell complains *"running scripts is disabled on this system"*, run this once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
…then try the activate command again.

**Or use Command Prompt instead** — change the terminal to cmd (click the `▾` next to the `+` in the terminal panel → Select Default Profile → Command Prompt) and run:
```cmd
.venv\Scripts\activate.bat
```

You'll know it worked when your prompt starts with `(.venv)`.

---

## 4. Tell VS Code to use this interpreter

Press **Ctrl+Shift+P** → type **"Python: Select Interpreter"** → pick the one inside `.venv` (it shows the path ending in `careflow\backend\.venv\Scripts\python.exe`).

This makes "Run Python File" and IntelliSense use the right environment.

---

## 5. Install dependencies

Still in the activated terminal:

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

This takes a couple of minutes the first time.

---

## 6. Configure your API key

```powershell
copy .env.example .env
```

Open `.env` in VS Code and paste your OpenAI key:
```
OPENAI_API_KEY=sk-your-real-key-here
```

If you don't have a key yet, the app still runs — it just returns empty extractions and you'll see `"stub": true` in responses.

---

## 7. Initialize the database

```powershell
python -m app.db.init_db
```

You should see `Tables created.` This makes a `careflow.db` SQLite file in the `backend` folder.

---

## 8. Run the server

```powershell
uvicorn app.main:app --reload
```

You'll see something like:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Leave this terminal open.

---

## 9. Test it

Open your browser at **http://127.0.0.1:8000/docs** — you'll see the Swagger UI with every endpoint.

Try this flow:

1. **POST `/patients`** → click "Try it out", paste:
   ```json
   { "name": "Test Patient", "gender": "F" }
   ```
   Hit Execute. Note the returned `id`.

2. **POST `/patients/{id}/records`** → upload any small PDF or `.txt` file with some clinical text in it. Use the `id` from step 1.

3. **GET `/patients/{id}/timeline`** → see extracted events.

4. **POST `/patients/{id}/summary`** → get a Markdown summary.

5. Upload a **second** record (later date), then **GET `/patients/{id}/changes`** → see the risk-level delta.

---

## 10. Daily workflow

Whenever you reopen the project:

```powershell
cd C:\Users\Fatima ezzahrae\Documents\A2A_Healthcare\careflow\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

That's it.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognized | Reinstall Python and tick *Add Python to PATH*. Restart VS Code. |
| `Activate.ps1 cannot be loaded` | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` once. |
| `ModuleNotFoundError: app` | You ran the command from the wrong folder. `cd` into `careflow\backend` first. |
| `pip install` fails on `PyMuPDF` | Make sure you're on Python 3.11 or 3.12 (3.13 sometimes lags). Then `pip install --upgrade pip` and retry. |
| `pytesseract.TesseractNotFoundError` | Either install Tesseract (step 1.4) or just don't upload pure-scan images for now — text and PDF still work. |
| OpenAI calls fail | Check `.env` is in the `backend` folder and that you restarted uvicorn after editing it. |
| Port 8000 already in use | `uvicorn app.main:app --reload --port 8001` |

---

## Recommended VS Code extensions (optional)

- **Python** (Microsoft) — required.
- **Pylance** — better IntelliSense.
- **Thunder Client** or **REST Client** — test endpoints from inside VS Code instead of Swagger.
- **SQLite Viewer** — peek at `careflow.db` to see your data.
