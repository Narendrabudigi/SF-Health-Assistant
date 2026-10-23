"""Run the ML and LLM orchestrator as a managed background process."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
_configured_dir = Path(os.getenv("ORCHESTRATOR_DIR", "../sf-genai-orchestrator 1"))
ORCHESTRATOR_DIR = _configured_dir if _configured_dir.is_absolute() else BACKEND_ROOT / _configured_dir
_configured_python = os.getenv("ORCHESTRATOR_PYTHON")
if _configured_python:
    _python_path = Path(_configured_python)
    ORCHESTRATOR_PYTHON = _python_path if _python_path.is_absolute() else BACKEND_ROOT / _python_path
else:
    venv_python = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    ORCHESTRATOR_PYTHON = ORCHESTRATOR_DIR / ".venv" / venv_python

STANDARDS = {"all", "industry", "custom"}
_lock = threading.RLock()
_job: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _watch(job: dict[str, Any], proc: subprocess.Popen[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        with _lock:
            job["output"].append(line.rstrip())
    code = proc.wait()
    with _lock:
        job["exit_code"] = code
        job["finished_at"] = _now()
        if job["status"] != "stopped":
            job["status"] = "succeeded" if code == 0 else "failed"


def _public_status(tail: int = 50) -> dict[str, Any]:
    if not _job:
        return {"status": "idle"}
    return {
        **{key: value for key, value in _job.items() if key not in {"proc", "output"}},
        "output": list(_job["output"])[-tail:],
    }


def status(tail: int = 50) -> dict[str, Any]:
    with _lock:
        return _public_status(min(max(tail, 1), 300))


def start(standards: str = "all", run_date: str | None = None, force: bool = False) -> dict[str, Any]:
    global _job
    if standards not in STANDARDS:
        raise ValueError("standards must be one of: all, industry, custom")
    if run_date:
        try:
            datetime.strptime(run_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("run_date must use YYYY-MM-DD format") from None
    if not (ORCHESTRATOR_DIR / "pyproject.toml").is_file():
        raise FileNotFoundError(f"Orchestrator package was not found at {ORCHESTRATOR_DIR}")
    if not ORCHESTRATOR_PYTHON.is_file():
        raise FileNotFoundError(
            f"Orchestrator Python was not found at {ORCHESTRATOR_PYTHON}. "
            f"Create its virtual environment and install dependencies: "
            f"cd {ORCHESTRATOR_DIR} && python -m venv .venv && "
            f".venv\\Scripts\\activate && pip install -e \".[notebooks]\""
        )

    with _lock:
        if _job and _job["status"] == "running":
            raise RuntimeError("An orchestrator run is already in progress")
        argv = [str(ORCHESTRATOR_PYTHON), "-u", "-m", "sf_orchestrator.pipeline", "--standards", standards]
        if run_date:
            argv.extend(["--run-date", run_date])
        if force:
            argv.append("--force")
        env = {
            **os.environ,
            "PYTHONPATH": str(ORCHESTRATOR_DIR / "src"),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "SF_TRIGGER": "backend",
        }
        try:
            proc = subprocess.Popen(
                argv,
                cwd=ORCHESTRATOR_DIR,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}),
            )
        except OSError as err:
            raise RuntimeError(f"Could not start the orchestrator: {err}") from None

        _job = {
            "status": "running",
            "standards": standards,
            "run_date": run_date,
            "force": force,
            "started_at": _now(),
            "finished_at": None,
            "exit_code": None,
            "output": deque(maxlen=300),
            "proc": proc,
        }
        threading.Thread(target=_watch, args=(_job, proc), daemon=True).start()
        return _public_status()


def stop() -> dict[str, Any]:
    with _lock:
        if not _job or _job["status"] != "running":
            raise RuntimeError("No orchestrator run is in progress")
        proc = _job["proc"]
        _job["status"] = "stopped"
        _job["finished_at"] = _now()
    _kill_tree(proc)
    return status()
