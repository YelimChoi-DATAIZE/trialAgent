#!/usr/bin/env python3
"""Launch the Trial Agent backend and frontend together.

Starts the FastAPI agent server, waits until it is healthy, then opens the
PyQt6 desktop UI. When the UI is closed (or you press Ctrl+C), the agent
server is shut down automatically.

Usage:
    ./venv/bin/python run.py      # inside the project venv
    python run.py                 # if the venv is already activated
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable  # use the same interpreter (venv) that launched this
HOST = os.getenv("AGENT_HOST", "127.0.0.1")
PORT = os.getenv("AGENT_PORT", "8000")
HEALTH_URL = f"http://{HOST}:{PORT}/health"


def _wait_for_health(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - server not up yet, keep polling
            time.sleep(0.4)
    return False


def main() -> int:
    env = os.environ.copy()

    backend = subprocess.Popen(
        [PYTHON, os.path.join("backend", "agent_server.py")],
        cwd=ROOT,
        env=env,
    )

    def _stop_backend() -> None:
        if backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()

    atexit.register(_stop_backend)

    print(f"[run] agent server starting (pid={backend.pid}); waiting for {HEALTH_URL} ...")
    if not _wait_for_health():
        print("[run] agent server did not become healthy in time; aborting.", file=sys.stderr)
        _stop_backend()
        return 1
    print("[run] agent server ready - launching UI ...")

    frontend = subprocess.Popen(
        [PYTHON, os.path.join("frontend", "app.py")],
        cwd=ROOT,
        env=env,
    )
    try:
        frontend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if frontend.poll() is None:
            frontend.terminate()
        _stop_backend()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
