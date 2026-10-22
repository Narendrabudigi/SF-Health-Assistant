"""sf-pipeline: run every notebook, and only if all of them succeeded, the LLM step. The notebooks get the settings of the .env file.
The company's own standards (an xlsx file) decide what runs for the custom part.
"""
import io
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest
import sf_orchestrator.pipeline as pipeline
import sf_orchestrator.store as store_module
from openpyxl import Workbook
from sf_orchestrator.config import ConfigError, Settings, load_settings
from sf_orchestrator.pipeline import find_notebooks, run_notebook, run_notebooks
from sf_orchestrator.reports import load_healthy_prompt, load_setup_prompt, load_system_prompt
from sf_orchestrator.store import StandardsCheck, StandardsError, describe, fetch_standards, notebook_module, parse_standards


# ───────────────────────── the pipeline ─────────────────────────


RUN_DATE = "2026-10-06"


def write(folder: Path, name: str, code: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(code, encoding="utf-8")
    return path


def run(path: Path, tmp_path: Path, timeout: float = 30) -> pipeline.NotebookResult:
    return run_notebook(path, run_date=RUN_DATE, python=sys.executable, timeout_seconds=timeout, log_dir=tmp_path / "logs")


# ───────────────────────── finding the notebooks ─────────────────────────


def test_notebooks_are_the_py_files_of_the_folder_in_name_order(tmp_path):
    for name in ("b_second.py", "A_first.py", "c_third.py", "_helpers.py", ".hidden.py", "notes.txt", "data.csv"):
        write(tmp_path, name, "pass")
    write(tmp_path / "sub", "nested.py", "pass")  # a subfolder is not searched
    assert [p.name for p in find_notebooks(tmp_path)] == ["A_first.py", "b_second.py", "c_third.py"]


def test_only_picks_notebooks_by_name_with_or_without_py_and_any_capitals(tmp_path):
    for name in ("rcm.py", "onb2.py", "ofb2.py"):
        write(tmp_path, name, "pass")
    assert [p.name for p in find_notebooks(tmp_path, ["RCM", "ofb2.py"])] == ["ofb2.py", "rcm.py"]


def test_only_with_an_unknown_name_lists_the_notebooks_there_are(tmp_path):
    write(tmp_path, "rcm.py", "pass")
    with pytest.raises(ValueError, match="No notebook named ec in .*Available: rcm"):
        find_notebooks(tmp_path, ["ec"])


def test_a_missing_folder_is_explained(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        find_notebooks(tmp_path / "nope")


# ───────────────────────── running one notebook ─────────────────────────


def test_a_notebook_that_finishes_is_ok_and_everything_it_printed_is_kept(tmp_path):
    result = run(write(tmp_path / "nb", "good.py", "print('hello from the notebook')\nimport sys\nprint('and a warning', file=sys.stderr)"), tmp_path)
    assert (result.ok, result.exit_code, result.reason, result.name) == (True, 0, "", "good")
    text = result.log_path.read_text(encoding="utf-8")
    assert "hello from the notebook" in text and "and a warning" in text  # standard output and errors, both
    assert result.log_path == tmp_path / "logs" / "good.log"


def test_a_notebook_that_crashes_has_failed_and_its_error_is_in_the_log(tmp_path):
    result = run(write(tmp_path / "nb", "bad.py", "print('step 1 done')\nraise ValueError('the model could not be trained')"), tmp_path)
    assert (result.ok, result.exit_code, result.reason) == (False, 1, "failed with exit code 1")
    text = result.log_path.read_text(encoding="utf-8")
    assert "step 1 done" in text and "ValueError: the model could not be trained" in text


def test_an_explicit_exit_code_counts(tmp_path):
    assert run(write(tmp_path / "nb", "quiet_fail.py", "raise SystemExit(3)"), tmp_path).exit_code == 3
    assert run(write(tmp_path / "nb", "quiet_ok.py", "raise SystemExit(0)"), tmp_path).ok


def test_a_notebook_runs_in_its_own_folder_and_sees_the_run_date_and_your_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_TEST_SETTING", "from the terminal")
    nb = write(tmp_path / "nb", "env.py", "import os\nprint(os.getcwd())\nprint(os.environ['PIPELINE_RUN_DATE'])\nprint(os.environ['MY_TEST_SETTING'])")
    lines = run(nb, tmp_path).log_path.read_text(encoding="utf-8").splitlines()
    assert Path(lines[0]).resolve() == (tmp_path / "nb").resolve() and lines[1:] == [RUN_DATE, "from the terminal"]


def test_a_notebook_that_asks_for_input_fails_instead_of_waiting_for_ever(tmp_path):
    started = time.monotonic()
    result = run(write(tmp_path / "nb", "asks.py", "input('continue? ')"), tmp_path, timeout=30)
    assert not result.ok and time.monotonic() - started < 15
    assert "EOFError" in result.log_path.read_text(encoding="utf-8")


def test_accents_and_symbols_in_the_output_do_not_crash_a_notebook(tmp_path):
    result = run(write(tmp_path / "nb", "unicode.py", "print('Zürich ✓ résumé')"), tmp_path)
    assert result.ok and "Zürich ✓ résumé" in result.log_path.read_text(encoding="utf-8")


def test_a_notebook_that_runs_too_long_is_stopped_and_counted_as_failed(tmp_path):
    pid_file = tmp_path / "pid.txt"
    nb = write(tmp_path / "nb", "stuck.py", f"import os, time\nopen(r'{pid_file}', 'w').write(str(os.getpid()))\nprint('started', flush=True)\ntime.sleep(60)")
    started = time.monotonic()
    result = run(nb, tmp_path, timeout=1.5)
    assert (result.ok, result.exit_code) == (False, None) and "timed out after 0.025 minutes and was stopped" in result.reason
    assert time.monotonic() - started < 20
    assert "started" in result.log_path.read_text(encoding="utf-8")  # what it printed before it was stopped is kept
    if os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)  # the process is really gone


def test_an_interpreter_that_cannot_be_started_is_a_failure_not_a_crash(tmp_path):
    result = run_notebook(
        write(tmp_path / "nb", "x.py", "pass"), run_date=RUN_DATE, python=str(tmp_path / "no-such-python"), timeout_seconds=5, log_dir=tmp_path / "logs"
    )
    assert not result.ok and "could not be started" in result.reason


# ───────────────────────── running several ─────────────────────────


def test_one_failing_notebook_does_not_stop_the_others_and_results_keep_the_order(tmp_path):
    paths = [
        write(tmp_path / "nb", "a_ok.py", "pass"),
        write(tmp_path / "nb", "b_bad.py", "raise SystemExit(1)"),
        write(tmp_path / "nb", "c_ok.py", "pass"),
    ]
    results = run_notebooks(paths, run_date=RUN_DATE, python=sys.executable, timeout_seconds=30, log_dir=tmp_path / "logs")
    assert [(r.name, r.ok) for r in results] == [("a_ok", True), ("b_bad", False), ("c_ok", True)]


def test_notebooks_can_run_at_the_same_time(tmp_path):
    paths = [write(tmp_path / "nb", f"n{i}.py", "import time\ntime.sleep(0.8)") for i in range(3)]

    def elapsed(concurrency: int) -> float:
        started = time.monotonic()
        results = run_notebooks(paths, run_date=RUN_DATE, python=sys.executable, timeout_seconds=30, log_dir=tmp_path / "logs", concurrency=concurrency)
        assert all(r.ok for r in results)
        return time.monotonic() - started

    assert elapsed(1) > 2.3  # one after the other
    assert elapsed(3) < 2.0  # all three together


def test_the_end_of_a_failed_notebooks_output_is_shown_with_secrets_hidden(tmp_path, caplog):
    nb = write(tmp_path / "nb", "leaks.py", "print('connecting with key sb_secret_abcdef0123456789')\nraise RuntimeError('rejected')")
    with caplog.at_level(logging.INFO):
        run_notebooks([nb], run_date=RUN_DATE, python=sys.executable, timeout_seconds=30, log_dir=tmp_path / "logs",
                      redact=lambda text: text.replace("sb_secret_abcdef0123456789", "[REDACTED]"))
    assert "RuntimeError: rejected" in caplog.text and "connecting with key [REDACTED]" in caplog.text
    assert "sb_secret_abcdef0123456789" not in caplog.text  # the log file keeps the raw output, the console does not


# ───────────────────────── the whole command ─────────────────────────


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """A project folder with notebooks and everything the LLM step needs, and a spy standing in for the LLM step."""
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "service-role-key-0123456789", "INSIGHTS_TABLE": "ML_Notebook_Insights", "REPORTS_TABLE": "LLM_Reports",
        "LLM_CHAIN": "gemini/gemini-a", "GEMINI_API_KEY": "gemini-key-1234567890",
    }.items():
        monkeypatch.setenv(name, value)
    order = tmp_path / "order.txt"
    llm_calls: list[tuple[list[str], str]] = []

    def spy(argv):
        llm_calls.append((argv, order.read_text() if order.exists() else ""))  # what the notebooks had written when the LLM step began
        return 0

    monkeypatch.setattr(pipeline, "orchestrate", spy)
    notebooks = tmp_path / "notebooks"
    for name in ("rcm", "onb2", "ofb2"):
        write(notebooks, f"{name}.py", f"open(r'{order}', 'a').write('{name}\\n')")
    return type("Project", (), {"path": tmp_path, "notebooks": notebooks, "order": order, "llm_calls": llm_calls})


def test_all_notebooks_run_first_and_then_the_llm_step_for_that_date(project):
    assert pipeline.main(["--run-date", RUN_DATE]) == 0
    assert project.llm_calls == [(["--run-date", RUN_DATE], "ofb2\nonb2\nrcm\n")]  # all three had finished, in name order
    assert sorted(p.name for p in (project.path / "logs" / RUN_DATE).iterdir()) == ["ofb2.log", "onb2.log", "rcm.log"]


def test_when_one_notebook_fails_the_llm_step_is_not_run_but_the_others_still_are(project, caplog):
    write(project.notebooks, "onb2.py", "raise RuntimeError('no data for onboarding')")
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE]) == 1
    assert project.llm_calls == []
    assert project.order.read_text() == "ofb2\nrcm\n"  # the other two ran
    assert "The LLM step was NOT run because 1 notebook(s) failed: onb2" in caplog.text
    assert "RuntimeError: no data for onboarding" in caplog.text and "Notebooks: 2 of 3 succeeded" in caplog.text


def test_a_notebook_that_times_out_blocks_the_llm_step_too(project, monkeypatch, caplog):
    monkeypatch.setenv("NOTEBOOK_TIMEOUT_MINUTES", "0.03")
    write(project.notebooks, "rcm.py", "import time\ntime.sleep(60)")
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE]) == 1
    assert project.llm_calls == [] and "timed out" in caplog.text and "NOT run" in caplog.text


def test_force_and_the_default_date_are_passed_on_to_the_llm_step(project):
    assert pipeline.main(["--force"]) == 0
    argv, _ = project.llm_calls[0]
    assert argv[0] == "--run-date" and argv[2:] == ["--force"] and len(argv[1]) == 10


def test_the_exit_code_of_the_llm_step_is_the_exit_code_of_the_pipeline(project, monkeypatch):
    monkeypatch.setattr(pipeline, "orchestrate", lambda argv: 1)
    assert pipeline.main(["--run-date", RUN_DATE]) == 1


def test_skip_llm_runs_the_notebooks_only(project):
    assert pipeline.main(["--run-date", RUN_DATE, "--skip-llm"]) == 0
    assert project.llm_calls == [] and project.order.read_text() == "ofb2\nonb2\nrcm\n"


def test_only_runs_the_named_notebooks(project):
    assert pipeline.main(["--run-date", RUN_DATE, "--only", "rcm", "--skip-llm"]) == 0
    assert project.order.read_text() == "rcm\n"


def test_a_notebook_added_to_the_folder_is_run_without_any_change_to_the_program(project):
    write(project.notebooks, "ec.py", f"open(r'{project.order}', 'a').write('ec\\n')")
    assert pipeline.main(["--run-date", RUN_DATE]) == 0
    assert project.llm_calls[0][1] == "ec\nofb2\nonb2\nrcm\n"


def test_dry_run_lists_the_notebooks_and_runs_nothing(project, caplog):
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE, "--dry-run"]) == 0
    assert not project.order.exists() and project.llm_calls == [] and not (project.path / "logs").exists()
    assert "3 notebook(s): ofb2, onb2, rcm" in caplog.text and "Would run: rcm.py" in caplog.text


def test_dry_run_and_skip_llm_do_not_need_any_keys(project, monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "INSIGHTS_TABLE", "REPORTS_TABLE", "LLM_CHAIN", "GEMINI_API_KEY"):
        monkeypatch.delenv(name)
    assert pipeline.main(["--run-date", RUN_DATE, "--dry-run"]) == 0
    assert pipeline.main(["--run-date", RUN_DATE, "--skip-llm"]) == 0


def test_missing_settings_for_the_llm_step_are_found_before_any_notebook_runs(project, monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert pipeline.main(["--run-date", RUN_DATE]) == 2
    assert not project.order.exists() and project.llm_calls == []  # no notebook was started
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_no_notebooks_is_a_configuration_error(project, caplog):
    for p in project.notebooks.glob("*.py"):
        p.unlink()
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE]) == 2
    assert "No notebook (.py file) found" in caplog.text and project.llm_calls == []


def test_an_unknown_only_name_stops_before_anything_runs(project, caplog):
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE, "--only", "nope"]) == 2
    assert "No notebook named nope" in caplog.text and not project.order.exists()


def test_a_missing_interpreter_stops_before_anything_runs(project, monkeypatch, caplog):
    monkeypatch.setenv("NOTEBOOK_PYTHON", str(project.path / "no-such-python"))
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE]) == 2
    assert "interpreter for the notebooks was not found" in caplog.text and not project.order.exists()


def test_another_interpreter_and_another_folder_can_be_chosen(project, monkeypatch):
    other = project.path / "ml_notebooks"
    write(other, "special.py", f"open(r'{project.order}', 'a').write('special\\n')")
    monkeypatch.setenv("NOTEBOOK_PYTHON", sys.executable)
    assert pipeline.main(["--run-date", RUN_DATE, "--notebooks-dir", str(other)]) == 0
    assert project.llm_calls[0][1] == "special\n"


def test_a_bad_run_date_is_rejected(project, capsys):
    assert pipeline.main(["--run-date", "06-10-2026"]) == 2 and "YYYY-MM-DD" in capsys.readouterr().err


def test_the_settings_have_sensible_defaults_and_refuse_nonsense():
    s = Settings(_env_file=None)
    assert (s.notebooks_dir, s.notebook_timeout_minutes, s.notebook_concurrency, s.notebook_python, s.logs_dir) == ("notebooks", 60, 1, None, "logs")
    for bad in ({"notebook_concurrency": 0}, {"notebook_timeout_minutes": 0}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **bad)


# ───────────────────────── the notebooks get the settings of .env ─────────────────────────


ENV_RUN_DATE = "2026-10-09"


SHOW = (
    "import os\n"
    "for name in ('SUPABASE_BUCKET', 'ACCESS_TARGET_HOURS', 'ANALYSIS_START', 'FF_SETTLEMENT_DATE_FIELD', 'INDUSTRY_STANDARDS_FILE_PATH', 'ONLY_IN_ENV'):\n"
    "    print(name + '=' + str(os.environ.get(name)))\n"
)


ENV = (
    "SUPABASE_BUCKET=SF_Health_Raw_Data\n"
    "INDUSTRY_STANDARDS_FILE_PATH=SF Health Monitoring Industry Standards.xlsx\n"
    "ANALYSIS_START=2024-10-01\n"
    "ACCESS_TARGET_HOURS=24\n"
    "FF_SETTLEMENT_DATE_FIELD=settlementDisbursementDate\n"
    "# a comment\n"
    "\n"
)


def run_notebook_with_env(tmp_path: Path):
    notebooks = tmp_path / "notebooks"
    notebooks.mkdir()
    nb = notebooks / "show.py"
    nb.write_text(SHOW, encoding="utf-8")
    result = run_notebook(nb, run_date=ENV_RUN_DATE, python=sys.executable, timeout_seconds=30, log_dir=tmp_path / "logs")
    return result, result.log_path.read_text(encoding="utf-8")


def clean(monkeypatch):
    for name in ("SUPABASE_BUCKET", "ACCESS_TARGET_HOURS", "ANALYSIS_START", "FF_SETTLEMENT_DATE_FIELD", "INDUSTRY_STANDARDS_FILE_PATH", "ONLY_IN_ENV"):
        monkeypatch.delenv(name, raising=False)


def test_a_notebook_gets_every_setting_of_the_env_file(tmp_path, monkeypatch):
    clean(monkeypatch)
    (tmp_path / ".env").write_text(ENV, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result, log = run_notebook_with_env(tmp_path)
    assert result.ok
    assert "SUPABASE_BUCKET=SF_Health_Raw_Data" in log
    assert "ACCESS_TARGET_HOURS=24" in log and "ANALYSIS_START=2024-10-01" in log
    assert "FF_SETTLEMENT_DATE_FIELD=settlementDisbursementDate" in log
    assert "INDUSTRY_STANDARDS_FILE_PATH=SF Health Monitoring Industry Standards.xlsx" in log  # spaces in a value are kept


def test_a_real_environment_variable_wins_over_the_env_file(tmp_path, monkeypatch):
    clean(monkeypatch)
    (tmp_path / ".env").write_text(ENV, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ACCESS_TARGET_HOURS", "48")
    _, log = run_notebook_with_env(tmp_path)
    assert "ACCESS_TARGET_HOURS=48" in log and "ACCESS_TARGET_HOURS=24" not in log


def test_without_an_env_file_the_notebook_still_runs(tmp_path, monkeypatch):
    clean(monkeypatch)
    monkeypatch.chdir(tmp_path)
    result, log = run_notebook_with_env(tmp_path)
    assert result.ok and "ACCESS_TARGET_HOURS=None" in log


# ───────────────────────── custom standards ─────────────────────────


HEADER = ["Module", "Metric Name", "Industry Benchmark", "Unit"]


def workbook(rows, header=HEADER) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def standards_of(*rows) -> StandardsCheck:
    return StandardsCheck(found=True, standards=parse_standards(workbook(rows)))


# ───────────────────────── reading the file ─────────────────────────


def test_a_metric_with_a_benchmark_has_a_value_and_one_without_has_none():
    check = standards_of(["RCM", "Time to Hire (TTH)", 25, "Days"], ["RCM", "Offer Acceptance Rate", None, "Percentage"], ["EC", "X", "  ", "Days"])
    assert [(s.module, s.metric, s.has_value) for s in check.standards] == [
        ("RCM", "Time to Hire (TTH)", True), ("RCM", "Offer Acceptance Rate", False), ("EC", "X", False),
    ]
    assert check.modules_with_values == {"RCM"} and [s.metric for s in check.blank] == ["Offer Acceptance Rate", "X"]


@pytest.mark.parametrize("cell", ["", "   ", "N/A", "n/a", "nan", "-", "null", None, float("nan")])
def test_empty_looking_cells_are_not_values(cell):
    assert not standards_of(["RCM", "A", cell, "Days"]).ready


@pytest.mark.parametrize("cell", [0, 5, 4.5, "95", "30 to 60", ">= 5"])
def test_numbers_and_texts_are_values(cell):
    assert standards_of(["RCM", "A", cell, "Days"]).ready  # zero is a value too


def test_a_number_that_excel_turned_into_a_date_is_a_value_and_is_reported_with_the_number_behind_it():
    check = standards_of(["EC", "Workflow Approval Cycle Time", datetime(1900, 1, 2), "Days"], ["ONB2", "Onboarding Cycle Time", datetime(1900, 1, 5), "Days"])
    assert all(s.has_value and s.stored_as_date for s in check.standards)
    assert [s.number_behind_date for s in check.standards] == [2, 5]
    lines = describe(check)
    assert "EC / Workflow Approval Cycle Time: the benchmark cell is formatted as a DATE; it holds the number 2" in lines[0]


def test_the_columns_may_be_in_any_order_and_any_capitals():
    book = workbook([[25, "Days", "RCM", "Time to Hire"]], header=["industry benchmark", "Unit", "MODULE", "metric name"])
    assert [(s.module, s.metric, s.has_value) for s in parse_standards(book)] == [("RCM", "Time to Hire", True)]


def test_rows_without_a_module_or_a_metric_are_ignored_and_modules_are_upper_cased():
    check = standards_of([None, None, None, None], [" ec ", "  Data   Sync  ", 2, "Percentage"], ["RCM", None, 5, "Days"])
    assert [(s.module, s.metric) for s in check.standards] == [("EC", "Data Sync")]


def test_describe_lists_the_skipped_metrics():
    lines = describe(standards_of(["RCM", "A", 1, "Days"], ["RCM", "B", None, "Days"], ["EC", "C", None, "Days"]))
    assert lines == ["No benchmark value for 2 metric(s), they are skipped: RCM / B; EC / C"]


def test_a_file_without_the_columns_or_that_is_not_an_xlsx_is_explained():
    with pytest.raises(StandardsError, match="Module, Metric Name and Industry Benchmark"):
        parse_standards(workbook([["a", "b"]], header=["Name", "Value"]))
    with pytest.raises(StandardsError, match="cannot be opened as an Excel"):
        parse_standards(b"this is not a spreadsheet")


# ───────────────────────── fetching it ─────────────────────────


class FakeStorage:
    def __init__(self, result):
        self.result, self.asked = result, []

    def from_(self, bucket):
        self.bucket = bucket
        return self

    def download(self, path):
        self.asked.append(path)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeClient:
    def __init__(self, result):
        self.storage = FakeStorage(result)


def test_the_file_is_downloaded_from_the_bucket_and_parsed():
    client = FakeClient(workbook([["RCM", "A", 1, "Days"]]))
    check = fetch_standards("u", "k", "SF_Health_Raw_Data", "SF Health Monitoring Custom Standards.xlsx", client=client)
    assert check.ready and client.storage.bucket == "SF_Health_Raw_Data" and client.storage.asked == ["SF Health Monitoring Custom Standards.xlsx"]


@pytest.mark.parametrize("message", ["Object not found", "{'statusCode': 404, 'error': 'not_found'}"])
def test_a_file_that_is_not_there_means_nothing_was_uploaded_and_is_no_error(message):
    check = fetch_standards("u", "k", "b", "f.xlsx", client=FakeClient(RuntimeError(message)))
    assert not check.found and not check.ready


def test_any_other_problem_with_the_bucket_is_an_error():
    with pytest.raises(StandardsError, match="could not be read from the bucket 'b'"):
        fetch_standards("u", "k", "b", "f.xlsx", client=FakeClient(RuntimeError("connection reset")))


@pytest.mark.parametrize(
    "name,module",
    [("EC Notebook1.py", "EC"), ("rcm_time_to_hire.py", "RCM"), ("ONB2-cycle.py", "ONB2"), ("ecp.py", "ECP"), ("ofb2.py", "OFB2"),
     ("EC1.py", None), ("Notebook.py", None), ("ecommerce.py", None)],
)
def test_a_notebook_belongs_to_the_module_its_name_starts_with(name, module):
    assert notebook_module(Path(name)) == module


# ───────────────────────── wording ─────────────────────────


@pytest.mark.parametrize("load", [load_system_prompt, load_healthy_prompt, load_setup_prompt])
def test_the_custom_prompts_call_the_standard_your_custom_standard(load):
    industry, custom = load(), load("custom")
    assert "custom standard" not in industry.text and industry.sha != custom.sha
    body = custom.text.split("# Which standard is used")[0]
    assert "industry standard" not in body.lower() and "your custom standard" in custom.text
    assert "never write \"industry standard\" or \"industry benchmark\"" in custom.text
    assert "`industryStandardValue`" in custom.text  # the JSON field keeps its name


# ───────────────────────── settings ─────────────────────────

BASE = dict(
    _env_file=None, supabase_url="https://abc.supabase.co", supabase_service_role_key="service-role-key-0123456789",
    insights_table="ML_Notebook_Insights", reports_table="LLM_Reports", llm_chain="gemini/gemini-a", gemini_api_key="gemini-key-1234567890",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("REPORTS_TABLE", "INSIGHTS_TABLE", "CUSTOM_INSIGHTS_TABLE", "CUSTOM_REPORTS_TABLE", "CUSTOM_STANDARDS_FILE_PATH", "CUSTOM_NOTEBOOKS_DIR"):
        monkeypatch.delenv(name, raising=False)


def test_the_custom_settings_have_the_defaults_of_the_project():
    s = load_settings(**BASE)
    assert (s.custom_standards_bucket, s.custom_standards_file_path, s.custom_notebooks_dir) == (
        "SF_Health_Raw_Data", "SF Health Monitoring Custom Standards.xlsx", "notebooks_custom")
    assert not s.custom_configured


def test_both_custom_tables_are_needed_together():
    assert load_settings(**BASE, custom_insights_table="ML_Notebook_Custom_Insights", custom_reports_table="LLM_Reports_Custom").custom_configured
    with pytest.raises(ConfigError, match="must be set together"):
        load_settings(**BASE, custom_insights_table="ML_Notebook_Custom_Insights")
    with pytest.raises(ConfigError, match="CUSTOM_INSIGHTS_TABLE"):
        load_settings(**BASE, require_custom=True)
    with pytest.raises(ConfigError, match="CUSTOM_REPORTS_TABLE"):
        load_settings(**BASE, custom_insights_table="ML_Notebook_Custom_Insights", custom_reports_table="bad name")


# ───────────────────────── sf-orchestrate --standards custom ─────────────────────────


def test_the_custom_llm_step_reads_and_writes_the_custom_tables(monkeypatch, tmp_path):
    seen = {}

    class Insights:
        def __init__(self, url, key, table):
            seen["insights"] = table

        def check(self, write_test=False):
            pass

        def list_insights(self, *a, **k):
            return []

    class Reports(Insights):
        def __init__(self, url, key, table):
            seen["reports"] = table

    monkeypatch.chdir(tmp_path)
    for name, value in dict(SUPABASE_URL="https://abc.supabase.co", SUPABASE_SERVICE_ROLE_KEY="service-role-key-0123456789",
                            INSIGHTS_TABLE="ML_Notebook_Insights", REPORTS_TABLE="LLM_Reports",
                            CUSTOM_INSIGHTS_TABLE="ML_Notebook_Custom_Insights", CUSTOM_REPORTS_TABLE="LLM_Reports_Custom").items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(store_module, "TableInsights", Insights)
    monkeypatch.setattr(store_module, "TableReports", Reports)
    pipeline.orchestrate(["--standards", "custom", "--dry-run", "--run-date", RUN_DATE])
    assert seen == {"insights": "ML_Notebook_Custom_Insights", "reports": "LLM_Reports_Custom"}


def test_the_custom_llm_step_needs_the_custom_tables(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    for name, value in dict(SUPABASE_URL="https://abc.supabase.co", SUPABASE_SERVICE_ROLE_KEY="service-role-key-0123456789",
                            INSIGHTS_TABLE="ML_Notebook_Insights", REPORTS_TABLE="LLM_Reports").items():
        monkeypatch.setenv(name, value)
    assert pipeline.orchestrate(["--standards", "custom", "--dry-run", "--run-date", RUN_DATE]) == 2
    assert "CUSTOM_INSIGHTS_TABLE" in capsys.readouterr().err


# ───────────────────────── sf-pipeline ─────────────────────────


@pytest.fixture()
def custom_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "service-role-key-0123456789", "INSIGHTS_TABLE": "ML_Notebook_Insights", "REPORTS_TABLE": "LLM_Reports",
        "LLM_CHAIN": "gemini/gemini-a", "GEMINI_API_KEY": "gemini-key-1234567890",
        "CUSTOM_INSIGHTS_TABLE": "ML_Notebook_Custom_Insights", "CUSTOM_REPORTS_TABLE": "LLM_Reports_Custom",
    }.items():
        monkeypatch.setenv(name, value)
    order = tmp_path / "order.txt"
    llm_calls: list[list[str]] = []
    monkeypatch.setattr(pipeline, "orchestrate", lambda argv: llm_calls.append(argv) or 0)
    note = lambda tag: f"import os\nopen(r'{order}', 'a').write('{tag}:' + os.environ['PIPELINE_STANDARDS'] + '\\n')"  # noqa: E731
    write(tmp_path / "notebooks", "rcm.py", note("rcm"))
    write(tmp_path / "notebooks_custom", "EC custom.py", note("ec"))
    write(tmp_path / "notebooks_custom", "RCM custom.py", note("rcm"))
    write(tmp_path / "notebooks_custom", "misc.py", note("misc"))
    state = {"check": standards_of(["RCM", "A", 25, "Days"], ["EC", "B", 2, "Percentage"])}

    def fetch(url, key, bucket, path, client=None):
        state["asked"] = (bucket, path)
        if isinstance(state["check"], Exception):
            raise state["check"]
        return state["check"]

    monkeypatch.setattr(pipeline, "fetch_standards", fetch)
    return type("Project", (), {"path": tmp_path, "order": order, "llm_calls": llm_calls, "state": state})


def lines(custom_project):
    return custom_project.order.read_text().splitlines() if custom_project.order.exists() else []


def test_by_default_the_industry_part_runs_first_and_then_the_custom_part_with_its_own_llm_step(custom_project):
    assert pipeline.main(["--run-date", RUN_DATE]) == 0
    assert lines(custom_project) == ["rcm:industry", "ec:custom", "misc:custom", "rcm:custom"]
    assert custom_project.llm_calls == [["--run-date", RUN_DATE], ["--run-date", RUN_DATE, "--standards", "custom"]]
    assert custom_project.state["asked"] == ("SF_Health_Raw_Data", "SF Health Monitoring Custom Standards.xlsx")
    logs = custom_project.path / "logs" / RUN_DATE
    assert (logs / "rcm.log").exists() and sorted(p.name for p in (logs / "custom").iterdir()) == ["EC custom.log", "RCM custom.log", "misc.log"]


def test_the_custom_part_alone(custom_project):
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom", "--force"]) == 0
    assert lines(custom_project) == ["ec:custom", "misc:custom", "rcm:custom"]
    assert custom_project.llm_calls == [["--run-date", RUN_DATE, "--force", "--standards", "custom"]]


def test_the_industry_part_alone_never_reads_the_standards_file(custom_project):
    custom_project.state["check"] = RuntimeError("must not be read")
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "industry"]) == 0
    assert lines(custom_project) == ["rcm:industry"] and custom_project.llm_calls == [["--run-date", RUN_DATE]]


@pytest.mark.parametrize("check", [StandardsCheck(found=False), standards_of(["RCM", "A", None, "Days"], ["EC", "B", "", "Days"])])
def test_without_a_file_or_without_any_value_no_custom_notebook_and_no_custom_llm_step_runs(custom_project, check, caplog):
    custom_project.state["check"] = check
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE]) == 0
        assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom"]) == 0
    assert lines(custom_project) == ["rcm:industry"]  # only the industry notebook, from the first command
    assert custom_project.llm_calls == [["--run-date", RUN_DATE]]
    assert "The custom notebooks and the LLM step are not run" in caplog.text


def test_a_module_without_a_value_is_skipped_and_a_notebook_without_a_module_always_runs(custom_project, caplog):
    custom_project.state["check"] = standards_of(["EC", "B", 2, "Percentage"], ["RCM", "A", None, "Days"])
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom"]) == 0
    assert lines(custom_project) == ["ec:custom", "misc:custom"]
    assert "RCM custom.py is skipped, the file has no benchmark value for module RCM" in caplog.text
    assert "No benchmark value for 1 metric(s), they are skipped: RCM / A" in caplog.text


def test_when_no_custom_notebook_belongs_to_a_module_with_values_nothing_is_run(custom_project):
    for p in (custom_project.path / "notebooks_custom").glob("misc.py"):
        p.unlink()
    custom_project.state["check"] = standards_of(["OFB2", "A", 1, "Days"])
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom"]) == 0
    assert lines(custom_project) == [] and custom_project.llm_calls == []


def test_a_failing_industry_notebook_does_not_stop_the_custom_part_and_the_exit_code_tells(custom_project):
    write(custom_project.path / "notebooks", "rcm.py", "raise RuntimeError('industry broke')")
    assert pipeline.main(["--run-date", RUN_DATE]) == 1
    assert lines(custom_project) == ["ec:custom", "misc:custom", "rcm:custom"]  # the custom part still ran
    assert custom_project.llm_calls == [["--run-date", RUN_DATE, "--standards", "custom"]]  # but the industry LLM step did not


def test_a_failing_custom_notebook_blocks_only_the_custom_llm_step(custom_project):
    write(custom_project.path / "notebooks_custom", "misc.py", "raise RuntimeError('custom broke')")
    assert pipeline.main(["--run-date", RUN_DATE]) == 1
    assert custom_project.llm_calls == [["--run-date", RUN_DATE]]  # the industry LLM step ran, the custom one did not


def test_an_unreadable_standards_file_fails_the_custom_part_but_not_the_industry_part(custom_project, caplog):
    custom_project.state["check"] = StandardsError("The custom standards file cannot be opened as an Excel (.xlsx) file: BadZipFile")
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE]) == 1
    assert lines(custom_project) == ["rcm:industry"] and custom_project.llm_calls == [["--run-date", RUN_DATE]]
    assert "cannot be opened as an Excel" in caplog.text


def test_without_the_custom_tables_the_pipeline_is_the_industry_pipeline_it_was(custom_project, monkeypatch, caplog):
    monkeypatch.delenv("CUSTOM_INSIGHTS_TABLE")
    monkeypatch.delenv("CUSTOM_REPORTS_TABLE")
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE]) == 0
    assert lines(custom_project) == ["rcm:industry"] and "Custom standards are not set up" in caplog.text
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom"]) == 2  # asking for them explicitly is a configuration error


def test_a_missing_custom_notebooks_folder_is_a_configuration_error_found_before_anything_runs(custom_project):
    for p in (custom_project.path / "notebooks_custom").glob("*.py"):
        p.unlink()
    (custom_project.path / "notebooks_custom").rmdir()
    assert pipeline.main(["--run-date", RUN_DATE]) == 2
    assert lines(custom_project) == []


def test_only_and_notebooks_dir_mean_the_industry_notebooks(custom_project):
    assert pipeline.main(["--run-date", RUN_DATE, "--only", "rcm", "--skip-llm"]) == 0
    assert lines(custom_project) == ["rcm:industry"]
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "all", "--only", "rcm"]) == 2
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom", "--notebooks-dir", "x"]) == 2


def test_the_custom_notebooks_can_be_in_another_folder(custom_project):
    write(custom_project.path / "elsewhere", "EC mine.py", f"open(r'{custom_project.order}', 'a').write('mine\\n')")
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom", "--custom-notebooks-dir", str(custom_project.path / "elsewhere")]) == 0
    assert lines(custom_project) == ["mine"]


def test_skip_llm_runs_the_custom_notebooks_without_the_llm_step(custom_project):
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom", "--skip-llm"]) == 0
    assert len(lines(custom_project)) == 3 and custom_project.llm_calls == []


def test_dry_run_lists_both_parts_and_runs_nothing(custom_project, caplog):
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE, "--dry-run"]) == 0
    assert lines(custom_project) == [] and custom_project.llm_calls == []
    assert "Pipeline for 2026-10-06: 1 notebook(s): rcm" in caplog.text and "Custom standards: Pipeline for 2026-10-06: 3 notebook(s)" in caplog.text


def test_dry_run_without_supabase_settings_lists_every_custom_notebook(custom_project, monkeypatch, caplog):
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "INSIGHTS_TABLE", "REPORTS_TABLE", "LLM_CHAIN", "GEMINI_API_KEY"):
        monkeypatch.delenv(name)
    with caplog.at_level(logging.INFO):
        assert pipeline.main(["--run-date", RUN_DATE, "--dry-run"]) == 0
    assert "cannot be checked without SUPABASE_URL" in caplog.text and "3 notebook(s)" in caplog.text


def test_the_custom_part_needs_supabase_even_when_only_the_notebooks_run(custom_project, monkeypatch, capsys):
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name)
    assert pipeline.main(["--run-date", RUN_DATE, "--standards", "custom", "--skip-llm"]) == 2
    assert "SUPABASE_URL" in capsys.readouterr().err and lines(custom_project) == []


def test_the_backend_can_start_the_same_run_as_a_function(custom_project):
    assert pipeline.run_pipeline("custom", run_date=RUN_DATE, force=True) == 0
    assert custom_project.llm_calls == [["--run-date", RUN_DATE, "--force", "--standards", "custom"]]
