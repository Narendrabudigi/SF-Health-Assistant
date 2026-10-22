"""The dashboard: the run records the program writes while it works, and the API that serves them (the React app in dashboard/).

1. Recording (sql/dashboard.sql). A run is one row of `sf_dashboard_runs`. While it works the program adds rows to
   `sf_dashboard_events` (notebooks started and finished, the outcome of every metric, every warning and error) and to
   `sf_dashboard_llm_calls` (every call to a model, with the prompt and the answer). Nothing else reads them but the API.

   Recording must never break a run:
   - every write happens on a background thread, so a slow database does not slow the notebooks or the model calls;
   - a write that fails is logged once, and after three failures in a row recording switches itself off for the rest of the run;
   - without Supabase settings, with DASHBOARD_TRACKING=false or in a dry run, nothing is recorded and every call is a no-op.

   `begin()` and `end()` are reference counted: `sf-pipeline` begins the run and calls the LLM step (`sf-orchestrate`) inside it,
   which begins again and simply joins the same run. The run is finished by the outermost `end()`.

2. The API.

       sf-dashboard                 serves http://127.0.0.1:8765 (the API, and the built React app when dashboard/dist exists)

   It READS what was recorded and it STARTS and STOPS runs: a run started here is the same `sf-pipeline` / `sf-orchestrate`
   command you would type, started as a separate process. Everything the dashboard shows comes from the three tables, so a run
   started from a terminal, a scheduler or Cloud Foundry shows up in the same way.

   The dashboard talks only to this API. The Supabase key stays here, and the prompts and answers stored with each model call
   are sent to the browser only when someone expands that call.

   It listens on 127.0.0.1 only. There is no login: do not expose it on a network as it is.
"""
from __future__ import annotations

import argparse
import logging
import os
import queue
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from .config import ConfigError, Settings, load_settings

log = logging.getLogger(__name__)

# ── 1. recording ──

RUNS, EVENTS, LLM_CALLS = "sf_dashboard_runs", "sf_dashboard_events", "sf_dashboard_llm_calls"
HEARTBEAT_SECONDS = 15
MAX_TEXT = 200_000  # a prompt or an answer longer than this is cut (it stays far above any real one)
FAILURES_BEFORE_OFF = 3
_STOP = object()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cut(text: str | None, limit: int = MAX_TEXT) -> str | None:
    if text is None or len(text) <= limit:
        return text
    return text[:limit] + "\n...[cut]"


class NullTracker:
    """Does nothing. What `current()` returns when no run is being recorded."""

    active = False
    run_id: str | None = None

    def event(self, kind: str, message: str, **_: Any) -> None: ...

    def llm_call(self, **_: Any) -> None: ...


class RunTracker:
    active = True

    def __init__(
        self,
        client: Any,
        *,
        run_id: str | None = None,
        kind: str = "pipeline",
        standards: str | None = None,
        run_date: str | None = None,
        args: dict[str, Any] | None = None,
        trigger: str = "cli",
        redact: Callable[[str], str] = lambda s: s,
        threaded: bool = True,
    ):
        """`run_id` is given when the dashboard created the run row before starting this process."""
        self._db = client
        self.run_id = run_id or str(uuid.uuid4())
        self._existing = run_id is not None
        self._meta = dict(kind=kind, standards=standards, run_date=run_date, args=args or {}, trigger=trigger)
        self._redact = redact
        self._failures = 0
        self._off = False
        self._queue: queue.Queue[Any] = queue.Queue()
        self._thread: threading.Thread | None = None
        self.depth = 0
        if threaded:
            self._thread = threading.Thread(target=self._work, name="run-tracker", daemon=True)
            self._thread.start()

    # ── the public calls ──

    def start(self) -> None:
        row: dict[str, Any] = {
            "id": self.run_id, "status": "running", "heartbeat_at": now(), "pid": os.getpid(),
            "kind": self._meta["kind"], "standards": self._meta["standards"], "run_date": self._meta["run_date"], "args": self._meta["args"],
        }
        if not self._existing:  # a run created by the dashboard keeps its own start time and trigger
            row.update(started_at=now(), trigger=self._meta["trigger"])
        self._put(("upsert", RUNS, row))

    def event(
        self, kind: str, message: str, *, level: str = "info", stage: str | None = None,
        module: str | None = None, metric: str | None = None, data: dict[str, Any] | None = None,
    ) -> None:
        self._put((
            "insert", EVENTS,
            {"run_id": self.run_id, "ts": now(), "level": level, "kind": kind, "stage": stage, "module": module, "metric": metric,
             "message": _cut(self._redact(message), 2000), "data": data or {}},
        ))

    def llm_call(
        self, *, module: str | None, metric: str | None, outcome: str, provider: str | None = None, model: str | None = None,
        round: int = 0, status_code: int | None = None, error_class: str | None = None, error_message: str | None = None,
        retry_info: str | None = None, input_tokens: int | None = None, output_tokens: int | None = None,
        cached_tokens: int | None = None, latency_ms: int | None = None, messages: list[dict[str, Any]] | None = None, response: str | None = None, ts: str | None = None,
    ) -> None:
        self._put((
            "insert", LLM_CALLS,
            {"id": str(uuid.uuid4()), "run_id": self.run_id, "ts": ts or now(), "module": module, "metric": metric, "round": round,
             "provider": provider, "model": model, "outcome": outcome, "status_code": status_code, "error_class": error_class,
             "error_message": _cut(self._redact(error_message), 4000) if error_message else None, "retry_info": _cut(self._redact(retry_info), 2000) if retry_info else None,
             "input_tokens": input_tokens, "output_tokens": output_tokens, "cached_tokens": cached_tokens, "latency_ms": latency_ms,
             "messages": [{"role": m.get("role"), "content": _cut(self._redact(str(m.get("content", ""))))} for m in messages] if messages else None,
             "response": _cut(self._redact(response)) if response else None},
        ))

    def finish(self, exit_code: int, summary: dict[str, Any] | None = None) -> None:
        """Write the end of the run, wait until everything is written, and stop the background thread."""
        status = "succeeded" if exit_code == 0 else "failed"
        self._put(("update", RUNS, {"status": status, "finished_at": now(), "exit_code": exit_code, "summary": summary or {}, "heartbeat_at": now()}))
        self.close()

    def close(self) -> None:
        if self._thread is not None:
            self._queue.put(_STOP)
            self._thread.join(timeout=30)
            self._thread = None
        else:
            self._drain()

    # ── writing ──

    def _put(self, op: tuple[Any, ...]) -> None:
        if self._off:
            return
        if self._thread is None:  # not threaded (tests): write at once
            self._write(op)
        else:
            self._queue.put(op)

    def _work(self) -> None:
        while True:
            try:
                op = self._queue.get(timeout=HEARTBEAT_SECONDS)
            except queue.Empty:
                self._write(("update", RUNS, {"heartbeat_at": now()}))
                continue
            if op is _STOP:
                return
            self._write(op)

    def _drain(self) -> None:
        while True:
            try:
                op = self._queue.get_nowait()
            except queue.Empty:
                return
            if op is not _STOP:
                self._write(op)

    def _write(self, op: tuple[Any, ...]) -> None:
        if self._off:
            return
        verb, table, row = op
        try:
            t = self._db.table(table)
            if verb == "insert":
                t.insert(row).execute()
            elif verb == "upsert":
                t.upsert(row, on_conflict="id").execute()
            else:
                t.update(row).eq("id", self.run_id).execute()
            self._failures = 0
        except Exception as err:  # noqa: BLE001  (tracking must never break a run)
            self._failures += 1
            reason = self._redact(f"{type(err).__name__}: {err}")[:300]
            if self._failures == 1:
                log.warning("Dashboard tracking could not write to '%s': %s (did you run sql/dashboard.sql?)", table, reason)
            if self._failures >= FAILURES_BEFORE_OFF:
                self._off = True
                log.warning("Dashboard tracking is switched off for the rest of this run")


class _LogToEvents(logging.Handler):
    """Every log line of the program becomes an event, so the dashboard shows what the terminal shows."""

    LEVELS = {"DEBUG": "debug", "INFO": "info", "WARNING": "warning", "ERROR": "error", "CRITICAL": "error"}

    def __init__(self, tracker: RunTracker):
        super().__init__(level=logging.INFO)
        self._tracker = tracker

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == __name__ or not record.name.startswith("sf_orchestrator"):
            return  # our own warnings would loop; other libraries are not the program's story
        try:
            self._tracker.event("log", record.getMessage(), level=self.LEVELS.get(record.levelname, "info"), data={"logger": record.name})
        except Exception:  # noqa: BLE001
            pass


_NULL = NullTracker()
_current: RunTracker | NullTracker = _NULL
_handler: _LogToEvents | None = None
_lock = threading.Lock()


def current() -> RunTracker | NullTracker:
    return _current


def begin(
    settings: Any, *, kind: str, standards: str | None, run_date: str, args: dict[str, Any],
    redact: Callable[[str], str] = lambda s: s, client: Any = None,
) -> RunTracker | NullTracker:
    """Start recording (or join the run that is already being recorded). Never raises."""
    global _current, _handler
    with _lock:
        if isinstance(_current, RunTracker):
            _current.depth += 1
            return _current
        if not getattr(settings, "dashboard_tracking", True):
            return _NULL
        try:
            if client is None:
                if not (settings.supabase_url and settings.supabase_service_role_key):
                    return _NULL
                from supabase import create_client

                client = create_client(settings.supabase_url, settings.supabase_service_role_key.get_secret_value())
            tracker = RunTracker(
                client, run_id=os.environ.get("SF_RUN_ID") or None, kind=kind, standards=standards, run_date=run_date, args=args,
                trigger=os.environ.get("SF_TRIGGER") or "cli", redact=redact,
            )
            tracker.depth = 1
            tracker.start()
        except Exception as err:  # noqa: BLE001
            log.warning("Dashboard tracking is off: %s", redact(f"{type(err).__name__}: {err}")[:300])
            return _NULL
        _current = tracker
        _handler = _LogToEvents(tracker)
        logging.getLogger().addHandler(_handler)
        return tracker


def end(exit_code: int, summary: dict[str, Any] | None = None) -> None:
    """Leave the run. The outermost `end()` finishes it."""
    global _current, _handler
    with _lock:
        tracker = _current
        if not isinstance(tracker, RunTracker):
            return
        tracker.depth -= 1
        if tracker.depth > 0:
            return
        if _handler is not None:
            logging.getLogger().removeHandler(_handler)
            _handler = None
        _current = _NULL
    tracker.finish(exit_code, summary)


# ── 2. the API ──

STALL_SECONDS = 90  # a running run that has not written anything for this long is shown as stalled
MODULES = ("RCM", "ONB2", "OFB2", "EC", "ECP")
LIST_COLUMNS = (
    "id,run_id,ts,module,metric,round,provider,model,outcome,status_code,error_class,error_message,retry_info,"
    "input_tokens,output_tokens,cached_tokens,latency_ms"
)  # everything except the prompt and the answer, which can be long


# ───────────────────────────── reading ─────────────────────────────


class Repo(Protocol):
    def list_runs(self, limit: int) -> list[dict[str, Any]]: ...
    def get_run(self, run_id: str) -> dict[str, Any] | None: ...
    def active_run(self) -> dict[str, Any] | None: ...
    def events(self, run_id: str, after: int, limit: int) -> list[dict[str, Any]]: ...
    def llm_calls(self, run_id: str) -> list[dict[str, Any]]: ...
    def llm_call(self, call_id: str) -> dict[str, Any] | None: ...
    def create_run(self, row: dict[str, Any]) -> None: ...
    def update_run(self, run_id: str, patch: dict[str, Any]) -> None: ...


class SupabaseRepo:
    def __init__(self, client: Any):
        self._db = client

    def list_runs(self, limit: int) -> list[dict[str, Any]]:
        return self._db.table(RUNS).select("*").order("started_at", desc=True).limit(limit).execute().data or []

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        rows = self._db.table(RUNS).select("*").eq("id", run_id).limit(1).execute().data or []
        return rows[0] if rows else None

    def active_run(self) -> dict[str, Any] | None:
        rows = self._db.table(RUNS).select("*").in_("status", ["queued", "running"]).order("started_at", desc=True).limit(1).execute().data or []
        return rows[0] if rows else None

    def events(self, run_id: str, after: int, limit: int) -> list[dict[str, Any]]:
        return (
            self._db.table(EVENTS).select("*").eq("run_id", run_id).gt("id", after).order("id").limit(limit).execute().data or []
        )

    def llm_calls(self, run_id: str) -> list[dict[str, Any]]:
        return self._db.table(LLM_CALLS).select(LIST_COLUMNS).eq("run_id", run_id).order("ts").limit(2000).execute().data or []

    def llm_call(self, call_id: str) -> dict[str, Any] | None:
        rows = self._db.table(LLM_CALLS).select("*").eq("id", call_id).limit(1).execute().data or []
        return rows[0] if rows else None

    def create_run(self, row: dict[str, Any]) -> None:
        self._db.table(RUNS).insert(row).execute()

    def update_run(self, run_id: str, patch: dict[str, Any]) -> None:
        self._db.table(RUNS).update(patch).eq("id", run_id).execute()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _camel(row: dict[str, Any]) -> dict[str, Any]:
    """Top-level column names in camelCase (what the website's code expects); the JSON inside the columns is left as written."""
    return {to_camel(k): v for k, v in row.items()}


def present_run(row: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """A run as the dashboard sees it. A run that says 'running' but has gone silent shows as 'stalled': its process died."""
    out = _camel(row)
    now = now or datetime.now(timezone.utc)
    beat = _parse_time(row.get("heartbeat_at")) or _parse_time(row.get("started_at"))
    out["liveStatus"] = row.get("status")
    if row.get("status") == "running" and beat and now - beat > timedelta(seconds=STALL_SECONDS):
        out["liveStatus"] = "stalled"
    if row.get("status") == "queued" and (started := _parse_time(row.get("started_at"))) and now - started > timedelta(seconds=STALL_SECONDS * 2):
        out["liveStatus"] = "stalled"
    return out


# ───────────────────────────── starting and stopping ─────────────────────────────


class StartRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    standards: Literal["all", "industry", "custom"] = "all"
    run_date: str | None = None
    force: bool = False
    skip_llm: bool = False
    only: list[str] = Field(default_factory=list)  # notebook names
    module: str | None = None  # with metric: run the LLM step for one metric only
    metric: str | None = None

    @field_validator("run_date")
    @classmethod
    def _date(cls, v: str | None) -> str | None:
        if v:
            datetime.strptime(v, "%Y-%m-%d")
        return v or None

    @field_validator("module", "metric")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class RunError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def build_command(req: StartRequest) -> tuple[str, list[str]]:
    """(kind, argv) of the command a request stands for."""
    if req.module or req.metric:
        if req.standards == "all":
            raise RunError(422, "Choose industry or custom standards to run the LLM step for one metric")
        if req.only or req.skip_llm:
            raise RunError(422, "Running one metric is the LLM step only: it cannot be combined with notebooks or 'skip LLM'")
        argv = ["-m", "sf_orchestrator", "--standards", req.standards]
        argv += ["--module", req.module] if req.module else []
        argv += ["--metric", req.metric] if req.metric else []
        kind = "llm"
    else:
        if req.only and req.standards != "industry":
            raise RunError(422, "Running chosen notebooks needs industry standards")
        argv = ["-m", "sf_orchestrator.pipeline", "--standards", req.standards]
        for name in req.only:
            argv += ["--only", name]
        argv += ["--skip-llm"] if req.skip_llm else []
        kind = "pipeline"
    argv += ["--run-date", req.run_date] if req.run_date else []
    argv += ["--force"] if req.force else []
    return kind, argv


class Handle(Protocol):
    pid: int

    def wait(self) -> int: ...


def spawn_process(argv: list[str], env: dict[str, str], log_path: Path) -> Handle:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out = open(log_path, "wb")  # noqa: SIM115  (closed when the process ends: see RunManager._watch)
    proc = subprocess.Popen(
        [sys.executable, "-u", *argv], env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
        **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}),  # type: ignore[attr-defined]
    )
    proc._log_file = out  # type: ignore[attr-defined]
    return proc  # type: ignore[return-value]


class RunManager:
    """Starts a run as a separate process, keeps track of it, and settles its row when the process ends."""

    def __init__(
        self, repo: Repo, logs_dir: Path = Path("logs") / "dashboard",
        spawn: Callable[[list[str], dict[str, str], Path], Handle] = spawn_process,
        kill: Callable[[Any], None] | None = None, threaded: bool = True,
    ):
        if kill is None:
            from .pipeline import _kill_tree  # imported here: the pipeline itself imports this module

            kill = _kill_tree
        self._repo, self._logs, self._spawn, self._kill, self._threaded = repo, logs_dir, spawn, kill, threaded
        self._procs: dict[str, Handle] = {}
        self._stopped: set[str] = set()
        self._lock = threading.Lock()

    def start(self, req: StartRequest) -> dict[str, Any]:
        kind, argv = build_command(req)
        with self._lock:
            try:
                active = self._repo.active_run()
            except Exception as err:  # noqa: BLE001  (usually the tables of sql/dashboard.sql are missing)
                log.exception("Could not read the runs from Supabase")
                raise RunError(500, f"The runs could not be read from Supabase ({type(err).__name__}: {str(err)[:300]}). Did you run sql/dashboard.sql?") from err
            if active and present_run(active)["liveStatus"] in ("queued", "running"):
                raise RunError(409, "A run is already in progress. Wait for it to finish, or stop it first")
            run_id = str(uuid.uuid4())
            args = {"standards": req.standards, "only": req.only, "skipLlm": req.skip_llm, "force": req.force, "module": req.module, "metric": req.metric}
            try:
                self._repo.create_run({
                    "id": run_id, "status": "queued", "kind": kind, "standards": req.standards, "run_date": req.run_date,
                    "trigger": "dashboard", "args": args, "started_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as err:  # noqa: BLE001  (say why on the page: usually the tables of sql/dashboard.sql are missing)
                log.exception("Could not record the new run in Supabase")
                raise RunError(500, f"The run could not be recorded in Supabase ({type(err).__name__}: {str(err)[:300]}). Did you run sql/dashboard.sql?") from err
            env = {**os.environ, "SF_RUN_ID": run_id, "SF_TRIGGER": "dashboard", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            try:
                proc = self._spawn(argv, env, self._log_path(run_id))
            except Exception as err:  # noqa: BLE001
                log.exception("Could not start the run process")
                self._repo.update_run(run_id, {"status": "failed", "finished_at": datetime.now(timezone.utc).isoformat(), "summary": {"error": str(err)}})
                raise RunError(500, f"The run could not be started: {type(err).__name__}: {err}") from err
            self._procs[run_id] = proc
            self._repo.update_run(run_id, {"pid": proc.pid})
        if self._threaded:
            threading.Thread(target=self._watch, args=(run_id, proc), name=f"watch-{run_id[:8]}", daemon=True).start()
        return present_run(self._repo.get_run(run_id) or {"id": run_id})

    def _watch(self, run_id: str, proc: Handle) -> None:
        code = proc.wait()
        self.settle(run_id, code)
        log_file = getattr(proc, "_log_file", None)
        if log_file:
            log_file.close()

    def settle(self, run_id: str, code: int) -> None:
        """The process ended. If the run never wrote its own ending (it crashed, or stopped before it began), write it here."""
        with self._lock:
            self._procs.pop(run_id, None)
            row = self._repo.get_run(run_id)
            if row and row.get("status") in ("queued", "running"):
                status = "stopped" if run_id in self._stopped else "succeeded" if code == 0 else "failed"
                self._repo.update_run(run_id, {"status": status, "exit_code": code, "finished_at": datetime.now(timezone.utc).isoformat()})
            self._stopped.discard(run_id)

    def stop(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            proc = self._procs.get(run_id)
            row = self._repo.get_run(run_id)
            if not row:
                raise RunError(404, "No such run")
            if row.get("status") not in ("queued", "running"):
                raise RunError(409, "This run has already ended")
            if proc is None:
                raise RunError(409, "This run was not started from the dashboard, so it cannot be stopped from here")
            self._stopped.add(run_id)
            self._kill(proc)
            self._repo.update_run(run_id, {"status": "stopped", "finished_at": datetime.now(timezone.utc).isoformat()})
        return present_run(self._repo.get_run(run_id) or row)

    def can_stop(self, run_id: str) -> bool:
        return run_id in self._procs

    def _log_path(self, run_id: str) -> Path:
        return self._logs / f"{run_id}.log"

    def output(self, run_id: str, tail: int = 200) -> list[str]:
        try:
            text = self._log_path(run_id).read_bytes().decode("utf-8", errors="replace")
        except OSError:
            return []
        return text.splitlines()[-tail:]


# ───────────────────────────── the web app ─────────────────────────────


def create_app(repo: Repo, manager: RunManager, options: dict[str, Any] | None = None, static_dir: Path | None = None) -> Any:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Orchestrator dashboard API", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(RunError)
    async def _run_error(_: Any, err: RunError) -> JSONResponse:
        return JSONResponse({"error": err.message}, status_code=err.status)

    @app.exception_handler(Exception)
    async def _unexpected(_: Any, err: Exception) -> JSONResponse:
        log.error("Unexpected error in the dashboard API", exc_info=err)
        return JSONResponse({"error": f"{type(err).__name__}: {str(err)[:400]}"}, status_code=500)

    def run_or_404(run_id: str) -> dict[str, Any]:
        row = repo.get_run(run_id)
        if not row:
            raise HTTPException(404, "No such run")
        return row

    def with_control(row: dict[str, Any]) -> dict[str, Any]:
        out = present_run(row)
        out["canStop"] = manager.can_stop(row["id"])
        return out

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        """The run to show: the one in progress, else the last one. Plus the recent history for the picker."""
        runs = [with_control(r) for r in repo.list_runs(15)]
        live = next((r for r in runs if r["liveStatus"] in ("queued", "running")), None)
        return {"run": live or (runs[0] if runs else None), "isLive": live is not None, "history": runs}

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return {"modules": list(MODULES), **(options or {})}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return with_control(run_or_404(run_id))

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str, after: int = 0, limit: int = 1000) -> dict[str, Any]:
        rows = repo.events(run_id, after, min(max(limit, 1), 5000))
        return {"events": [_camel(r) for r in rows], "last": rows[-1]["id"] if rows else after}

    @app.get("/api/runs/{run_id}/llm-calls")
    def llm_calls(run_id: str) -> dict[str, Any]:
        return {"calls": [_camel(r) for r in repo.llm_calls(run_id)]}

    @app.get("/api/llm-calls/{call_id}")
    def llm_call(call_id: str) -> dict[str, Any]:
        row = repo.llm_call(call_id)
        if not row:
            raise HTTPException(404, "No such call")
        return _camel(row)

    @app.get("/api/runs/{run_id}/output")
    def output(run_id: str, tail: int = 200) -> dict[str, Any]:
        return {"lines": manager.output(run_id, min(max(tail, 1), 2000))}

    @app.post("/api/runs", status_code=202)
    def start(req: StartRequest) -> dict[str, Any]:
        out = manager.start(req)
        out["canStop"] = manager.can_stop(out["id"])
        return out

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: str) -> dict[str, Any]:
        out = manager.stop(run_id)
        out["canStop"] = manager.can_stop(run_id)
        return out

    if static_dir and static_dir.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="dashboard")
    return app


def _options(settings: Settings) -> dict[str, Any]:
    def names(folder: str) -> list[str]:
        from .pipeline import find_notebooks  # imported here: the pipeline itself imports this module

        try:
            return [p.stem for p in find_notebooks(Path(folder))]
        except ValueError:
            return []

    return {
        "chain": settings.chain,
        "notebooks": names(settings.notebooks_dir),
        "customNotebooks": names(settings.custom_notebooks_dir) if settings.custom_configured else [],
        "customConfigured": settings.custom_configured,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sf-dashboard", description="Serve the orchestrator dashboard API (and the built React app) on this computer.")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1", help="leave it as it is: there is no login")
    args = p.parse_args(argv)
    try:
        settings = load_settings(require_llm=False, require_tables=False)
    except ConfigError as err:
        print(f"{err}\nSee .env.example", file=sys.stderr)
        return 2
    try:
        import uvicorn
        from supabase import create_client
    except ImportError:
        print('The dashboard needs two more packages: pip install -e ".[dashboard]"', file=sys.stderr)
        return 2
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    repo = SupabaseRepo(create_client(settings.supabase_url, settings.supabase_service_role_key.get_secret_value()))  # type: ignore[union-attr]
    app = create_app(repo, RunManager(repo), _options(settings), static_dir=Path("dashboard") / "dist")
    log.info("Dashboard API on http://%s:%d  (open http://localhost:5173 while developing the React app, or this address after 'npm run build')", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())