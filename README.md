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
- macOS / Windows / Linux with a desktop environment (PyQt6)
- An OpenAI API key for real (non-mock) runs

## Setup

```bash
# 1. Clone
git clone <your-repo-url>
cd TrialAx

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

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

Open two terminals (both with the venv activated):

```bash
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
