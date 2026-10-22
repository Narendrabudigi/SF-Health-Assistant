"""What the program records for the dashboard (runs, events and model calls; recording can never break a run) and the API that shows
it and starts and stops runs.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sf_orchestrator import dashboard as tracker
from sf_orchestrator.dashboard import (
    EVENTS,
    LLM_CALLS,
    RUNS,
    RunError,
    RunManager,
    RunTracker,
    StartRequest,
    SupabaseRepo,
    build_command,
    create_app,
    present_run,
)
from sf_orchestrator.llm import _ATTEMPT_LOG
from sf_orchestrator.reports import Orchestrator, Prompt
from sf_orchestrator.schemas import parse_draft

from fake_db import FakeDb
from helpers import OK, RUN_DATE, FakeLlm, MemStore, insight, make_settings, rec, with_fake_router


# ───────────────────────── recording ─────────────────────────


@pytest.fixture
def db():
    return FakeDb()


@pytest.fixture(autouse=True)
def _no_run_left_behind():
    yield
    while tracker.current().active:  # a test that fails half way must not leak its run into the next test
        tracker.end(1)


def begin(db, **over):
    settings = make_settings(dashboard_tracking=True)
    return tracker.begin(settings, kind=over.pop("kind", "pipeline"), standards="industry", run_date=RUN_DATE, args={"force": False}, client=db, **over)


def kinds(db):
    return [e["kind"] for e in db.tables.get(EVENTS, [])]


# ───────── the run ─────────


def test_a_run_is_recorded_from_its_start_to_its_end(db):
    t = begin(db)
    t.event("run_started", "Pipeline started")
    tracker.end(0)
    (run,) = db.tables[RUNS]
    assert run["status"] == "succeeded" and run["exit_code"] == 0 and run["finished_at"] and run["kind"] == "pipeline"
    assert run["trigger"] == "cli" and run["run_date"] == RUN_DATE and run["pid"]
    assert kinds(db) == ["run_started"]
    assert not tracker.current().active


def test_a_non_zero_exit_code_is_a_failed_run(db):
    begin(db)
    tracker.end(1)
    assert db.tables[RUNS][0]["status"] == "failed" and db.tables[RUNS][0]["exit_code"] == 1


def test_the_llm_step_inside_a_pipeline_joins_the_same_run(db):
    outer = begin(db)
    inner = begin(db, kind="llm")
    assert inner is outer
    tracker.end(0)  # the LLM step ends: the run goes on
    assert tracker.current().active
    tracker.end(0)
    assert not tracker.current().active
    assert len(db.tables[RUNS]) == 1 and db.tables[RUNS][0]["status"] == "succeeded"


def test_a_run_created_by_the_dashboard_keeps_its_id_start_time_and_trigger(db, monkeypatch):
    db.tables[RUNS] = [{"id": "run-1", "status": "queued", "trigger": "dashboard", "started_at": "2026-10-19T01:00:00+00:00"}]
    monkeypatch.setenv("SF_RUN_ID", "run-1")
    monkeypatch.setenv("SF_TRIGGER", "dashboard")
    begin(db)
    tracker.end(0)
    (run,) = db.tables[RUNS]
    assert run["id"] == "run-1" and run["trigger"] == "dashboard" and run["started_at"] == "2026-10-19T01:00:00+00:00"
    assert run["status"] == "succeeded"


@pytest.mark.parametrize("over", [{"dashboard_tracking": False}, {"supabase_url": None}])
def test_nothing_is_recorded_when_it_is_switched_off_or_there_is_no_database(over):
    settings = make_settings(**{"dashboard_tracking": True, **over})
    t = tracker.begin(settings, kind="pipeline", standards="industry", run_date=RUN_DATE, args={})
    assert not t.active and not tracker.current().active
    tracker.current().event("x", "y")  # a no-op, never an error
    tracker.end(0)


# ───────── events and log lines ─────────


def test_the_programs_log_lines_become_events_and_other_libraries_do_not(db):
    begin(db)
    logging.getLogger("sf_orchestrator.pipeline").warning("Notebook a: slow")
    logging.getLogger("httpx").warning("HTTP Request: GET ...")
    logging.getLogger("sf_orchestrator.pipeline").debug("too detailed")
    tracker.end(0)
    logs = [e for e in db.tables[EVENTS] if e["kind"] == "log"]
    assert [(e["level"], e["message"]) for e in logs] == [("warning", "Notebook a: slow")]


def test_secrets_never_reach_the_database(db):
    begin(db, redact=lambda s: s.replace("topsecret-key-123", "[REDACTED]"))
    tracker.current().event("x", "failed with key topsecret-key-123")
    tracker.current().llm_call(module="RCM", metric="M", outcome="error", error_message="bad key topsecret-key-123",
                               messages=[{"role": "user", "content": "key topsecret-key-123"}], response="topsecret-key-123")
    tracker.end(0)
    assert "topsecret" not in str(db.tables)


def test_a_failing_database_never_breaks_the_run_and_tracking_switches_itself_off(db, caplog):
    t = RunTracker(db, threaded=False)
    db.fail = "relation does not exist"
    with caplog.at_level(logging.WARNING):
        for i in range(6):
            t.event("x", f"event {i}")
    assert [c for c in db.calls].count(("insert", EVENTS)) == 3  # it gave up after three failures in a row
    assert caplog.text.count("could not write") == 1 and "switched off" in caplog.text


def test_a_slow_database_does_not_block_the_caller(db):
    t = RunTracker(db)  # background thread
    t.start()
    for i in range(50):
        t.event("x", f"event {i}")
    t.finish(0)
    assert len(db.tables[EVENTS]) == 50 and db.tables[RUNS][0]["status"] == "succeeded"


# ───────── model calls ─────────


async def test_a_call_that_works_and_a_rejected_answer_are_both_recorded_with_prompt_and_answer(db):
    begin(db)
    seen = []

    def strict(text):
        seen.append(text)
        if len(seen) == 1:
            raise ValueError("never reached")  # replaced below
        return parse_draft(text)

    from sf_orchestrator.schemas import ReportError

    def parse(text):
        seen.append(text)
        if len(seen) == 1:
            raise ReportError("the text must not contain internal wording")
        return parse_draft(text)

    c, _ = with_fake_router([(OK, "stop"), (OK, "stop")])
    await c.generate("system text", "user text", parse, run_key="RCM/TimeToHire")
    tracker.end(0)
    first, second = db.tables[LLM_CALLS]
    assert (first["outcome"], first["round"], first["error_message"]) == ("rejected", 0, "the text must not contain internal wording")
    assert (second["outcome"], second["round"]) == ("success", 1)
    assert (second["module"], second["metric"]) == ("RCM", "TimeToHire")
    assert second["messages"][0] == {"role": "system", "content": "system text"} and second["messages"][1]["content"] == "user text"
    assert second["response"] == OK and second["input_tokens"] is not None


async def test_a_failed_attempt_is_recorded_with_its_status_and_what_happens_next(db):
    begin(db, redact=lambda s: s.replace("topsecret-key-123", "[REDACTED]"))
    _ATTEMPT_LOG.configure(["topsecret-key-123"], 2, 1, 10)
    _ATTEMPT_LOG.begin("RCM/TimeToHire", 0)

    class Quota(Exception):
        status_code = 429

    start = datetime.now(timezone.utc)
    kwargs = {"model": "gemini-a", "custom_llm_provider": "gemini", "exception": Quota("quota exceeded for topsecret-key-123"),
              "litellm_params": {"metadata": {"run_key": "RCM/TimeToHire"}}, "messages": [{"role": "user", "content": "hello"}]}
    await _ATTEMPT_LOG.async_log_failure_event(kwargs, None, start, start + timedelta(milliseconds=250))
    tracker.end(0)
    (call,) = db.tables[LLM_CALLS]
    assert (call["outcome"], call["status_code"], call["provider"], call["model"]) == ("error", 429, "gemini", "gemini-a")
    assert call["error_class"] == "Quota" and call["latency_ms"] == 250 and call["messages"][0]["content"] == "hello"
    assert "topsecret" not in call["error_message"] and call["retry_info"]


# ───────── what the orchestrator tells the dashboard ─────────


async def test_every_metric_has_its_start_and_its_outcome_as_events(db):
    begin(db)
    store = MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical")), rec("RCM", "OfferAcceptance", insight("OfferAcceptance", "healthy"))])
    await Orchestrator(store=store, llm=FakeLlm(retries=1), prompt=Prompt("breach", "b1")).run(RUN_DATE)
    tracker.end(0)
    events = db.tables[EVENTS]
    assert kinds(db)[0] == "insights_loaded" and kinds(db).count("metric_started") == 2
    done = {e["metric"]: e for e in events if e["kind"].startswith("metric_") and e["kind"] != "metric_started"}
    assert done["TimeToHire"]["kind"] == "metric_generated"
    assert done["TimeToHire"]["data"]["provider"] == "gemini" and done["TimeToHire"]["data"]["retries"] == 1
    assert done["TimeToHire"]["level"] == "warning"  # it needed a retry
    assert done["OfferAcceptance"]["kind"] == "metric_healthy"


async def test_a_failed_metric_carries_the_reason(db):
    begin(db)
    store = MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))])
    await Orchestrator(store=store, llm=FakeLlm(steps=[RuntimeError("all models failed")]), prompt=Prompt("breach", "b1")).run(RUN_DATE)
    tracker.end(1)
    failed = next(e for e in db.tables[EVENTS] if e["kind"] == "metric_failed")
    assert failed["level"] == "error" and "all models failed" in failed["data"]["reason"] and failed["metric"] == "TimeToHire"


async def test_a_cached_metric_is_an_event_too(db):
    store = MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))])
    orch = Orchestrator(store=store, llm=FakeLlm(), prompt=Prompt("breach", "b1"))
    await orch.run(RUN_DATE)
    begin(db)
    await orch.run(RUN_DATE)
    tracker.end(0)
    assert "metric_cached" in kinds(db)


# ───────── notebooks ─────────


def test_notebooks_are_recorded_with_the_end_of_the_output_when_one_fails(db, tmp_path):
    from sf_orchestrator.pipeline import find_notebooks, run_notebooks

    (tmp_path / "a_good.py").write_text("print('fine')\n")
    (tmp_path / "b_bad.py").write_text("print('about to fail')\nraise SystemExit(3)\n")
    begin(db)
    run_notebooks(find_notebooks(tmp_path), run_date=RUN_DATE, python=__import__("sys").executable, timeout_seconds=60, log_dir=tmp_path / "logs")
    tracker.end(1)
    done = {e["data"]["name"]: e for e in db.tables[EVENTS] if e["kind"] == "notebook_finished"}
    assert done["a_good"]["data"]["ok"] is True and done["a_good"]["level"] == "info"
    bad = done["b_bad"]
    assert bad["data"]["ok"] is False and bad["data"]["exitCode"] == 3 and bad["level"] == "error"
    assert "about to fail" in bad["data"]["tail"][-1]
    assert kinds(db).count("notebook_started") == 2


# ───────────────────────── the API ─────────────────────────


def iso(seconds_ago: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


class FakeProc:
    def __init__(self, pid=4242, code=0):
        self.pid, self._code = pid, code

    def wait(self):
        return self._code


class Spawner:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, argv, env, log_path):
        if self.fail:
            raise OSError("no such interpreter")
        self.calls.append((argv, env, log_path))
        return FakeProc()


@pytest.fixture
def repo(db):
    return SupabaseRepo(db)


@pytest.fixture
def spawner():
    return Spawner()


@pytest.fixture
def killed():
    return []


@pytest.fixture
def manager(repo, spawner, killed, tmp_path):
    return RunManager(repo, tmp_path / "logs", spawn=spawner, kill=killed.append, threaded=False)


@pytest.fixture
def client(repo, manager):
    return TestClient(create_app(repo, manager, {"chain": ["gemini/a"], "notebooks": ["n1"]}))


def add_run(db, **over):
    row = {"id": "r1", "status": "succeeded", "kind": "pipeline", "standards": "industry", "started_at": iso(100), "heartbeat_at": iso(90), **over}
    db.tables.setdefault(RUNS, []).append(row)
    return row


# ───────── what to show ─────────


def test_with_nothing_running_the_last_run_is_shown(client, db):
    add_run(db, id="old", started_at=iso(5000))
    add_run(db, id="last", started_at=iso(100), status="failed")
    body = client.get("/api/overview").json()
    assert body["isLive"] is False and body["run"]["id"] == "last" and body["run"]["liveStatus"] == "failed"
    assert [r["id"] for r in body["history"]] == ["last", "old"]


def test_a_run_in_progress_is_shown_even_when_it_is_not_the_newest(client, db):
    add_run(db, id="live", status="running", started_at=iso(300), heartbeat_at=iso(2))
    add_run(db, id="newer", status="succeeded", started_at=iso(100))
    body = client.get("/api/overview").json()
    assert body["isLive"] is True and body["run"]["id"] == "live"


def test_an_empty_database_shows_no_run(client):
    assert client.get("/api/overview").json() == {"run": None, "isLive": False, "history": []}


def test_a_run_that_went_silent_is_shown_as_stalled():
    quiet = {"id": "r", "status": "running", "started_at": iso(500), "heartbeat_at": iso(200)}
    assert present_run(quiet)["liveStatus"] == "stalled"
    assert present_run({**quiet, "heartbeat_at": iso(5)})["liveStatus"] == "running"
    assert present_run({"id": "r", "status": "queued", "started_at": iso(400)})["liveStatus"] == "stalled"
    assert present_run({"id": "r", "status": "queued", "started_at": iso(10)})["liveStatus"] == "queued"


def test_column_names_reach_the_browser_in_camel_case(client, db):
    add_run(db, run_date="2026-10-19", exit_code=0)
    run = client.get("/api/runs/r1").json()
    assert run["runDate"] == "2026-10-19" and run["exitCode"] == 0 and run["startedAt"] and "run_date" not in run


def test_an_unknown_run_is_a_404(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/llm-calls/nope").status_code == 404


def test_events_are_read_in_pages_after_the_last_one_seen(client, db):
    add_run(db)
    for i in range(5):
        db.tables.setdefault(EVENTS, []).append({"id": i + 1, "run_id": "r1", "kind": "log", "message": f"m{i}"})
    db.tables[EVENTS].append({"id": 99, "run_id": "other", "kind": "log", "message": "elsewhere"})
    first = client.get("/api/runs/r1/events?limit=3").json()
    assert [e["message"] for e in first["events"]] == ["m0", "m1", "m2"] and first["last"] == 3
    rest = client.get(f"/api/runs/r1/events?after={first['last']}").json()
    assert [e["message"] for e in rest["events"]] == ["m3", "m4"] and rest["last"] == 5
    none = client.get("/api/runs/r1/events?after=5").json()
    assert none == {"events": [], "last": 5}


def test_the_call_list_leaves_out_prompts_and_answers_until_a_call_is_opened(client, db):
    add_run(db)
    db.tables.setdefault(LLM_CALLS, []).append({
        "id": "c1", "run_id": "r1", "ts": iso(10), "module": "RCM", "metric": "M", "outcome": "success", "round": 0,
        "messages": [{"role": "user", "content": "long prompt"}], "response": "long answer", "input_tokens": 10,
    })
    (listed,) = client.get("/api/runs/r1/llm-calls").json()["calls"]
    assert listed["id"] == "c1" and listed["inputTokens"] == 10 and "messages" not in listed and "response" not in listed
    opened = client.get("/api/llm-calls/c1").json()
    assert opened["messages"][0]["content"] == "long prompt" and opened["response"] == "long answer"


def test_config_lists_the_modules_and_what_can_be_run(client):
    body = client.get("/api/config").json()
    assert body["modules"] == ["RCM", "ONB2", "OFB2", "EC", "ECP"] and body["notebooks"] == ["n1"] and body["chain"] == ["gemini/a"]


# ───────── commands ─────────


@pytest.mark.parametrize("body,kind,argv", [
    ({}, "pipeline", ["-m", "sf_orchestrator.pipeline", "--standards", "all"]),
    ({"standards": "industry", "skipLlm": True, "force": True, "runDate": "2026-10-01"},
     "pipeline", ["-m", "sf_orchestrator.pipeline", "--standards", "industry", "--skip-llm", "--run-date", "2026-10-01", "--force"]),
    ({"standards": "industry", "only": ["a", "b"]}, "pipeline", ["-m", "sf_orchestrator.pipeline", "--standards", "industry", "--only", "a", "--only", "b"]),
    ({"standards": "custom", "module": "RCM", "metric": "TimeToHire", "force": True},
     "llm", ["-m", "sf_orchestrator", "--standards", "custom", "--module", "RCM", "--metric", "TimeToHire", "--force"]),
])
def test_a_request_becomes_the_command_you_would_type(body, kind, argv):
    assert build_command(StartRequest(**body)) == (kind, argv)


@pytest.mark.parametrize("body", [
    {"module": "RCM"},  # standards "all" does not apply to one metric
    {"standards": "industry", "module": "RCM", "skipLlm": True},
    {"standards": "custom", "only": ["a"]},
])
def test_impossible_combinations_are_refused_with_a_reason(body):
    with pytest.raises(RunError) as err:
        build_command(StartRequest(**body))
    assert err.value.status == 422 and err.value.message


def test_a_bad_date_is_refused(client):
    assert client.post("/api/runs", json={"runDate": "19/10/2026"}).status_code == 422


# ───────── start and stop ─────────


def test_starting_a_run_creates_its_row_and_hands_the_process_its_id(client, db, spawner):
    res = client.post("/api/runs", json={"standards": "industry", "force": True})
    assert res.status_code == 202
    run = res.json()
    argv, env, log_path = spawner.calls[0]
    assert argv[:2] == ["-m", "sf_orchestrator.pipeline"] and "--force" in argv
    assert env["SF_RUN_ID"] == run["id"] and env["SF_TRIGGER"] == "dashboard" and env["PYTHONUTF8"] == "1"
    row = db.tables[RUNS][0]
    assert row["trigger"] == "dashboard" and row["status"] == "queued" and row["pid"] == 4242 and row["args"]["force"] is True
    assert run["canStop"] is True and Path(log_path).name == f"{run['id']}.log"


def test_only_one_run_at_a_time(client, db):
    add_run(db, status="running", heartbeat_at=iso(1))
    res = client.post("/api/runs", json={})
    assert res.status_code == 409 and "already in progress" in res.json()["error"]


def test_a_dead_run_does_not_block_a_new_one(client, db):
    add_run(db, status="running", started_at=iso(900), heartbeat_at=iso(800))  # stalled
    assert client.post("/api/runs", json={}).status_code == 202


def test_a_process_that_cannot_start_leaves_a_failed_run_and_a_clear_error(client, db, repo, killed, tmp_path):
    manager = RunManager(repo, tmp_path, spawn=Spawner(fail=True), kill=killed.append, threaded=False)
    c = TestClient(create_app(repo, manager))
    res = c.post("/api/runs", json={})
    assert res.status_code == 500 and "no such interpreter" in res.json()["error"]
    assert db.tables[RUNS][0]["status"] == "failed"


def test_a_process_that_ends_without_writing_its_own_ending_is_settled(manager, db):
    run = manager.start(StartRequest())
    manager.settle(run["id"], 3)
    row = db.tables[RUNS][0]
    assert row["status"] == "failed" and row["exit_code"] == 3 and row["finished_at"]


def test_a_run_that_wrote_its_own_ending_is_left_alone(manager, db):
    run = manager.start(StartRequest())
    db.tables[RUNS][0].update(status="succeeded", exit_code=0, summary={"generated": 4})
    manager.settle(run["id"], 0)
    assert db.tables[RUNS][0]["summary"] == {"generated": 4} and db.tables[RUNS][0]["status"] == "succeeded"


def test_stop_ends_the_process_and_marks_the_run_stopped(client, db, killed):
    run = client.post("/api/runs", json={}).json()
    res = client.post(f"/api/runs/{run['id']}/stop")
    assert res.status_code == 200 and res.json()["status"] == "stopped" and len(killed) == 1
    manager_row = db.tables[RUNS][0]
    assert manager_row["status"] == "stopped" and manager_row["finished_at"]


def test_a_stopped_run_stays_stopped_when_the_process_reports_back(manager, db):
    run = manager.start(StartRequest())
    manager.stop(run["id"])
    manager.settle(run["id"], -15)
    assert db.tables[RUNS][0]["status"] == "stopped"


def test_stop_refuses_what_it_cannot_stop(client, db):
    assert client.post("/api/runs/nope/stop").status_code == 404
    add_run(db, id="done")
    assert client.post("/api/runs/done/stop").status_code == 409
    add_run(db, id="elsewhere", status="running", heartbeat_at=iso(1))  # started from a terminal
    res = client.post("/api/runs/elsewhere/stop")
    assert res.status_code == 409 and "not started from the dashboard" in res.json()["error"]


def test_the_output_of_a_dashboard_run_is_its_last_lines(manager, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "abc.log").write_text("\n".join(f"line {i}" for i in range(10)))
    assert manager.output("abc", tail=3) == ["line 7", "line 8", "line 9"]
    assert manager.output("missing") == []


def test_a_database_that_cannot_record_the_run_gives_a_readable_error(client, db):
    db.fail = 'relation "public.sf_dashboard_runs" does not exist'
    res = client.post("/api/runs", json={})
    assert res.status_code == 500
    assert "sf_dashboard_runs" in res.json()["error"] and "sql/dashboard.sql" in res.json()["error"]


def test_any_process_start_problem_gives_a_readable_error_and_a_failed_run(repo, db, killed, tmp_path):
    class Boom:
        def __call__(self, argv, env, log_path):
            raise PermissionError("access denied")

    c = TestClient(create_app(repo, RunManager(repo, tmp_path, spawn=Boom(), kill=killed.append, threaded=False)))
    res = c.post("/api/runs", json={})
    assert res.status_code == 500 and "access denied" in res.json()["error"]
    assert db.tables[RUNS][0]["status"] == "failed"
