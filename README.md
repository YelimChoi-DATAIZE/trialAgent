# DATAIZEAI · Trial Agent

A desktop assistant for clinical-trial protocol work. A PyQt6 UI talks to a
FastAPI agent server that orchestrates several LLM tools:

- **Protocol Drafting** — generate an ICH-GCP style protocol draft from a request.
- **Scientific & PI Review / Site Feasibility Review / Regulatory Review** — multi-agent review of a protocol.
- **TrialGPT Retrieval / Matching / Ranking** — patient-to-trial matching pipeline.
- **CTG Retrieval** — live ClinicalTrials.gov search via a ReAct loop.

Tools share a vector memory (FAISS) so later tools can reuse earlier results,
and tool selection is handled automatically by an LLM planner when you don't
pick tools yourself.

> Without an API key the app runs in **mock mode** (no LLM calls), so you can
> explore the UI right away.

## Requirements

- **Python 3.10+** (developed on 3.12)
- macOS / Windows / Linux with a desktop environment (PyQt6 opens a window)
- An OpenAI API key for real (non-mock) runs
- No editor/IDE required — a plain terminal is enough.

### Prerequisites (terminal, Python, git)

You only need a terminal. Everything below runs from the command line.

**Which terminal?**

- **Windows** — *Windows PowerShell* is built into every Windows version
  (Win7 SP1 and later). Just open the Start menu and search for "PowerShell".
  (Command Prompt `cmd` also works.)
- **macOS** — open the built-in *Terminal* app.
- **Linux** — any terminal emulator (GNOME Terminal, Konsole, etc.).

**Install Python 3.10+ and git** (only if you don't have them):

- **Windows**
  - Python: download from <https://www.python.org/downloads/> and, in the
    installer, **check "Add python.exe to PATH"**. Verify with `python --version`
    (or `py --version`).
  - git: download from <https://git-scm.com/download/win>. Verify with
    `git --version`. (No git? You can also download the repo as a ZIP from GitHub.)
- **macOS**
  - `python3 --version` / `git --version`. If missing, install via
    [Homebrew](https://brew.sh): `brew install python git`.
- **Linux (Debian/Ubuntu)**
  - `sudo apt update && sudo apt install -y python3 python3-venv git`

## Setup

### Windows (PowerShell)

```powershell
# 1. Clone (or download the repo ZIP and unzip)
git clone https://github.com/YelimChoi-DATAIZE/trialAgent.git
cd trialAgent

# 2. Create a virtual environment
python -m venv venv
#   If `python` isn't found, use the Python launcher:  py -m venv venv

# 3. Install dependencies (calling the venv's python directly — no activation
#    needed, which avoids PowerShell execution-policy issues)
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\venv\Scripts\python.exe -m pip install -r frontend\requirements.txt
```

> To activate the venv instead (optional): `.\venv\Scripts\Activate.ps1`.
> If blocked by execution policy, run once per session:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

### macOS / Linux

```bash
# 1. Clone
git clone https://github.com/YelimChoi-DATAIZE/trialAgent.git
cd trialAgent

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

## API key

The app reads the OpenAI key from any of these (in order of convenience):

1. **In the app** — paste it into the `OPENAI_API_KEY` field on the launcher
   screen. It is sent with each run and applied server-side.
2. **`.env` file** — `cp backend/.env.example backend/.env` and set
   `OPENAI_API_KEY=sk-...` (loaded automatically by the backend).
3. **Environment variable** — `export OPENAI_API_KEY=sk-...` before launching.

If no key is found, the app runs in mock mode.

## Run

### One command (recommended)

```powershell
# Windows (PowerShell)
.\venv\Scripts\python.exe run.py
```

```bash
# macOS / Linux (venv activated)
python run.py
```

This starts the agent server, waits until it is healthy, then opens the UI.
Closing the UI (or pressing Ctrl+C) shuts the server down automatically.

### Or start the two processes manually

Open two terminals:

```powershell
# Windows (PowerShell)
# Terminal 1 — agent server (FastAPI)
.\venv\Scripts\python.exe backend\agent_server.py
# Terminal 2 — desktop UI (PyQt6)
.\venv\Scripts\python.exe frontend\app.py
```

```bash
# macOS / Linux (both terminals with the venv activated)
# Terminal 1 — agent server (FastAPI)
python backend/agent_server.py
# Terminal 2 — desktop UI (PyQt6)
python frontend/app.py
```

The server listens on `http://127.0.0.1:8000` by default.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | _(none)_ | Enables real LLM mode; otherwise mock mode. |
| `AGENT_MODEL` | `gpt-5.1` | Model used by all agents. |
| `AGENT_MOCK` | _(unset)_ | Set to `1` to force mock mode. |
| `AGENT_HOST` | `127.0.0.1` | Server bind host. |
| `AGENT_PORT` | `8000` | Server port. |
| `AGENT_MEMORY_TOP_K` | `4` | Shared-memory chunks retrieved per tool. |
| `AGENT_SERVER_URL` | `http://127.0.0.1:8000` | URL the UI uses to reach the server. |

## Project layout

```
backend/
  agent_server.py        FastAPI server: tool router, executor, streaming API
  trialgpt_tools.py      TrialGPT pipeline adapter
  util/                  Shared vector memory (embeddings, chunking, reasoning)
  tool_registry/         Agents, templates, and the CTG retriever
  requirements.txt
frontend/
  app.py                 PyQt6 desktop UI
  requirements.txt
```

## Notes

- `venv/` and `backend/.env` are git-ignored; never commit your real key.
- Mock mode requires no key and makes no network calls — handy for demos.
