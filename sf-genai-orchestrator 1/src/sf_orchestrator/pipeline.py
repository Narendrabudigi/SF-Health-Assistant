"""Run all the ML notebooks, then (only if every one of them succeeded) the LLM step. Twice if you want both kinds of standards.

    sf-pipeline                       industry standards (the notebooks folder), then the custom standards if there are any
    sf-pipeline --standards industry  the industry standards only
    sf-pipeline --standards custom    the company's own standards only (the notebooks_custom folder)
    sf-pipeline --run-date 2026-10-06
    sf-pipeline --only rcm_time_to_hire --skip-llm      one notebook, no LLM step (to try a new notebook)
    sf-pipeline --dry-run                                list what would run

The custom standards are an xlsx file in a bucket. Nothing of the custom part runs when the file is missing or holds no value; a module
without a value is skipped; a metric without a value is skipped by the custom notebooks (see store.py).

A notebook is a .py file that runs on its own (`python notebook.py`) and writes its own output. The program starts each one as a
separate process, writes everything it prints to logs/<run-date>/<notebook>.log, and judges it by its exit code: 0 is success,
anything else (an uncaught error, a timeout) is a failure. Adding a notebook means putting its file in the folder; nothing here changes.

The LLM step on its own is `sf-orchestrate`: for every insight of the run date it asks the model for a report (see reports.py) and
saves it (see store.py). `sf-pipeline` runs it after the notebooks.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from dotenv import dotenv_values

from . import dashboard
from .config import ConfigError, Settings, load_settings
from .llm import LlmClient, quiet_litellm
from .reports import Orchestrator, load_healthy_prompt, load_setup_prompt, load_system_prompt
from .store import StandardsError, build_store, describe, fetch_standards, notebook_module

log = logging.getLogger(__name__)

EXIT_OK, EXIT_FAILED, EXIT_CONFIG = 0, 1, 2
TAIL_LINES = 15  # how many of a failed notebook's last lines are shown in the log


@dataclass
class NotebookResult:
    name: str
    ok: bool
    seconds: float
    exit_code: int | None  # None: it timed out or could not be started
    log_path: Path
    reason: str  # empty when ok


def find_notebooks(folder: Path, only: Sequence[str] = ()) -> list[Path]:
    """The .py files directly inside `folder`, in name order. Files starting with _ or . (helpers) are not notebooks."""
    if not folder.is_dir():
        raise ValueError(f"The notebooks folder '{folder}' does not exist")
    found = sorted(
        (p for p in folder.glob("*.py") if p.is_file() and not p.name.startswith(("_", "."))),
        key=lambda p: p.name.lower(),
    )
    if only:
        wanted = {name.strip().lower().removesuffix(".py") for name in only}
        unknown = sorted(wanted - {p.stem.lower() for p in found})
        if unknown:
            raise ValueError(
                f"No notebook named {', '.join(unknown)} in '{folder}'. Available: {', '.join(p.stem for p in found) or 'none'}"
            )
        found = [p for p in found if p.stem.lower() in wanted]
    return found


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop a notebook and everything it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.kill()


def _dotenv_settings() -> dict[str, str]:
    """Every NAME=value line of the .env file in the folder where the program was started (the same file the program reads its
    own settings from), so the notebooks get their settings from it too, whether or not they load a .env file themselves."""
    try:
        return {k: v for k, v in dotenv_values(".env").items() if v is not None}
    except OSError:
        return {}


def run_notebook(path: Path, *, run_date: str, python: str, timeout_seconds: float, log_dir: Path, standards: str = "industry") -> NotebookResult:
    """Run one notebook as its own process. Its output goes to <log_dir>/<name>.log; it is judged by its exit code."""
    log_path = log_dir / f"{path.stem}.log"
    # The notebook sees the settings of the .env file, your environment (which wins over the file) and the run date. UTF-8 is
    # forced so that printing accents or symbols cannot crash it on Windows. It gets no keyboard: a notebook that asks for
    # input fails instead of waiting for ever.
    env = {**_dotenv_settings(), **os.environ, "PIPELINE_RUN_DATE": run_date, "PIPELINE_STANDARDS": standards, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    started = time.monotonic()
    code: int | None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_path, "wb") as out:
            proc = subprocess.Popen(
                [python, "-u", str(path.resolve())],
                cwd=path.parent,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                **({} if os.name == "nt" else {"start_new_session": True}),
            )
            try:
                code = proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                _kill_tree(proc)
                proc.wait()
                code = None
    except OSError as err:
        return NotebookResult(path.stem, False, time.monotonic() - started, None, log_path, f"could not be started: {err}")
    seconds = time.monotonic() - started
    if code is None:
        return NotebookResult(path.stem, False, seconds, None, log_path, f"timed out after {timeout_seconds / 60:g} minutes and was stopped")
    if code != 0:
        return NotebookResult(path.stem, False, seconds, code, log_path, f"failed with exit code {code}")
    return NotebookResult(path.stem, True, seconds, 0, log_path, "")


def _tail(path: Path, lines: int = TAIL_LINES) -> list[str]:
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.strip()][-lines:]


def _duration(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


def _report(result: NotebookResult, redact: Callable[[str], str]) -> None:
    if result.ok:
        log.info("Notebook %s: finished in %s (output: %s)", result.name, _duration(result.seconds), result.log_path)
        return
    tail = "\n".join("    " + redact(line) for line in _tail(result.log_path))
    log.error(
        "Notebook %s: %s after %s. Last lines of its output (everything is in %s):\n%s",
        result.name, result.reason, _duration(result.seconds), result.log_path, tail or "    (it printed nothing)",
    )


def run_notebooks(
    paths: Sequence[Path],
    *,
    run_date: str,
    python: str,
    timeout_seconds: float,
    log_dir: Path,
    concurrency: int = 1,
    redact: Callable[[str], str] = lambda s: s,
    standards: str = "industry",
) -> list[NotebookResult]:
    """Run every notebook, whatever happens to the others: one failure never stops the rest. Results are in the notebooks' order."""
    total = len(paths)

    def one(item: tuple[int, Path]) -> NotebookResult:
        index, path = item
        log.info("Notebook %s: started (%d of %d)", path.stem, index, total)
        dashboard.current().event("notebook_started", f"Notebook {path.stem} started ({index} of {total})", stage=standards,
                                data={"name": path.stem, "index": index, "total": total})
        result = run_notebook(path, run_date=run_date, python=python, timeout_seconds=timeout_seconds, log_dir=log_dir, standards=standards)
        _report(result, redact)
        dashboard.current().event(
            "notebook_finished",
            f"Notebook {path.stem} {'finished' if result.ok else 'FAILED'} in {_duration(result.seconds)}" + ("" if result.ok else f": {result.reason}"),
            level="info" if result.ok else "error", stage=standards,
            data={"name": path.stem, "ok": result.ok, "seconds": round(result.seconds, 1), "exitCode": result.exit_code, "reason": result.reason,
                  "logPath": str(result.log_path), "tail": [redact(line) for line in _tail(result.log_path)] if not result.ok else []},
        )
        return result

    items = list(enumerate(paths, start=1))
    if concurrency <= 1:
        return [one(item) for item in items]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(one, items))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sf-pipeline",
        description="Run every ML notebook, then, only if all of them succeeded, generate the LLM insights. "
        "Exit codes: 0 ok | 1 a notebook or the LLM step failed | 2 configuration error.",
    )
    p.add_argument("--run-date", help="YYYY-MM-DD (default: today, UTC); the notebooks see it as PIPELINE_RUN_DATE")
    p.add_argument(
        "--standards", choices=("all", "industry", "custom"),
        help="which standards to run: industry, custom (the company's own) or all (default: all, except that --only or --notebooks-dir mean industry)",
    )
    p.add_argument("--only", action="append", metavar="NAME", help="run only this notebook (file name without .py); can be repeated")
    p.add_argument("--skip-llm", action="store_true", help="run the notebooks only, without the LLM step")
    p.add_argument("--force", action="store_true", help="regenerate the LLM reports even if they are current")
    p.add_argument("--dry-run", action="store_true", help="list the notebooks that would run, and run nothing")
    p.add_argument("--notebooks-dir", help="folder with the industry notebooks (default: NOTEBOOKS_DIR from .env, else ./notebooks)")
    p.add_argument("--custom-notebooks-dir", help="folder with the custom notebooks (default: CUSTOM_NOTEBOOKS_DIR from .env, else ./notebooks_custom)")
    p.add_argument("--python", help="Python interpreter for the notebooks (default: NOTEBOOK_PYTHON from .env, else the one running this program)")
    return p


@dataclass
class _Part:
    """One kind of standards to run."""

    kind: str  # "industry" | "custom"
    folder: Path
    notebooks: list[Path]
    log_dir_name: str  # sub folder of logs/<run-date>/ ("" for industry, so the old log locations stay as they were)


def _run_part(part: _Part, *, run_date: str, python: str, settings: Settings, args: argparse.Namespace, redact: Callable[[str], str]) -> int:
    label = "" if part.kind == "industry" else "Custom standards: "
    log.info("%sPipeline for %s: %d notebook(s): %s", label, run_date, len(part.notebooks), ", ".join(p.stem for p in part.notebooks))
    started = time.monotonic()
    dashboard.current().event("notebooks_planned", f"{label}{len(part.notebooks)} notebook(s) to run", stage=part.kind,
                            data={"names": [p.stem for p in part.notebooks]})
    results = run_notebooks(
        part.notebooks,
        run_date=run_date,
        python=python,
        timeout_seconds=settings.notebook_timeout_minutes * 60,
        log_dir=Path(settings.logs_dir) / run_date / part.log_dir_name,
        concurrency=settings.notebook_concurrency,
        redact=redact,
        standards=part.kind,
    )
    failed = [r for r in results if not r.ok]
    log.info("%sNotebooks: %d of %d succeeded in %s", label, len(results) - len(failed), len(results), _duration(time.monotonic() - started))
    for r in results:
        log.info("  %-32s %-7s %s", r.name, "OK" if r.ok else "FAILED", _duration(r.seconds))
    dashboard.current().event(
        "notebooks_finished", f"{label}Notebooks: {len(results) - len(failed)} of {len(results)} succeeded", stage=part.kind,
        level="error" if failed else "info", data={"ok": len(results) - len(failed), "failed": len(failed), "seconds": round(time.monotonic() - started, 1)},
    )
    if failed:
        log.error("%sThe LLM step was NOT run because %d notebook(s) failed: %s", label, len(failed), ", ".join(r.name for r in failed))
        dashboard.current().event("llm_step_skipped", f"{label}The LLM step was not run because {len(failed)} notebook(s) failed", stage=part.kind, level="error")
        return EXIT_FAILED
    if args.skip_llm:
        dashboard.current().event("llm_step_skipped", f"{label}The LLM step was skipped (--skip-llm)", stage=part.kind)
        return EXIT_OK
    log.info("%sAll notebooks succeeded. Starting the LLM step for %s", label, run_date)
    argv = ["--run-date", run_date] + (["--force"] if args.force else []) + (["--standards", "custom"] if part.kind == "custom" else [])
    return orchestrate(argv)


def _custom_part(settings: Settings, folder: Path, only: Sequence[str], args: argparse.Namespace, run_date: str) -> tuple[_Part | None, int]:
    """Decide what runs for the custom standards, from what the client has filled in. Returns (the part, or None when nothing runs; exit code)."""
    if not (settings.supabase_url and settings.supabase_service_role_key):
        log.warning("Custom standards: the file cannot be checked without SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (dry run), so every custom notebook is listed")
        check = None
    else:
        try:
            check = fetch_standards(
                settings.supabase_url, settings.supabase_service_role_key.get_secret_value(),
                settings.custom_standards_bucket, settings.custom_standards_file_path,
            )
        except StandardsError as err:
            log.error("Custom standards: %s", err)
            return None, EXIT_FAILED
        if not check.found:
            log.info(
                "Custom standards: '%s' is not in the bucket '%s' (nothing uploaded yet). The custom notebooks and the LLM step are not run",
                settings.custom_standards_file_path, settings.custom_standards_bucket,
            )
            return None, EXIT_OK
        for line in describe(check):
            log.warning("Custom standards: %s", line)
        if not check.ready:
            log.info("Custom standards: the file has no benchmark value at all. The custom notebooks and the LLM step are not run")
            return None, EXIT_OK
    notebooks = find_notebooks(folder, only)
    if not notebooks:
        log.error("Custom standards: no notebook (.py file) found in '%s'. Put the custom notebooks there, or point CUSTOM_NOTEBOOKS_DIR at their folder.", folder)
        return None, EXIT_CONFIG
    if check is not None:
        ready = check.modules_with_values
        kept = [p for p in notebooks if (notebook_module(p) or "") in ready or notebook_module(p) is None]
        for p in notebooks:
            if p not in kept:
                log.info("Custom standards: %s is skipped, the file has no benchmark value for module %s", p.name, notebook_module(p))
        notebooks = kept
        if not notebooks:
            log.info("Custom standards: no custom notebook belongs to a module that has values (%s). Nothing is run", ", ".join(sorted(ready)))
            return None, EXIT_OK
    return _Part("custom", folder, notebooks, "custom"), EXIT_OK


def main(argv: list[str] | None = None) -> int:
    began: list[bool] = []
    code = EXIT_FAILED
    try:
        code = _main(argv, began)
        return code
    finally:
        if began:  # the run was being recorded for the dashboard
            dashboard.end(code)


def _main(argv: list[str] | None, began: list[bool]) -> int:
    args = _parser().parse_args(argv)

    run_date = args.run_date or datetime.now(timezone.utc).date().isoformat()
    try:
        datetime.strptime(run_date, "%Y-%m-%d")
    except ValueError:
        print(f'--run-date must be YYYY-MM-DD, got "{run_date}"', file=sys.stderr)
        return EXIT_CONFIG

    explicit = args.standards
    if explicit == "all" and (args.only or args.notebooks_dir):
        print("--only and --notebooks-dir name industry notebooks: use them with --standards industry (or without --standards)", file=sys.stderr)
        return EXIT_CONFIG
    standards = explicit or ("industry" if (args.only or args.notebooks_dir) else "all")
    if explicit == "custom" and args.notebooks_dir:
        print("--notebooks-dir is for the industry notebooks; use --custom-notebooks-dir", file=sys.stderr)
        return EXIT_CONFIG

    # Check the settings of the LLM step BEFORE the notebooks run, which can take long: a missing key must not be found after.
    needs_llm = not (args.skip_llm or args.dry_run)
    wants_custom = standards in ("all", "custom")
    try:
        settings = load_settings(
            require_llm=needs_llm,
            require_supabase=needs_llm,
            require_custom=standards == "custom",
        )
    except ConfigError as err:
        print(f"{err}\nSee .env.example", file=sys.stderr)
        return EXIT_CONFIG

    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    secrets = settings.secret_values()

    def redact(text: str) -> str:
        for s in secrets:
            text = text.replace(s, "[REDACTED]")
        return text

    run_industry = standards in ("all", "industry")
    run_custom = wants_custom and (standards == "custom" or settings.custom_configured)
    if run_custom and not needs_llm and not args.dry_run and not (settings.supabase_url and settings.supabase_service_role_key):
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for the custom standards: the file with the standards is read from Supabase\nSee .env.example", file=sys.stderr)
        return EXIT_CONFIG
    if wants_custom and not run_custom:
        log.info("Custom standards are not set up (CUSTOM_INSIGHTS_TABLE and CUSTOM_REPORTS_TABLE are empty): only the industry standards run")

    parts: list[_Part] = []
    if run_industry:
        folder = Path(args.notebooks_dir or settings.notebooks_dir)
        try:
            notebooks = find_notebooks(folder, args.only or ())
        except ValueError as err:
            log.error("%s", err)
            return EXIT_CONFIG
        if not notebooks:
            log.error("No notebook (.py file) found in '%s'. Put the notebooks there, or point NOTEBOOKS_DIR at their folder.", folder)
            return EXIT_CONFIG
        parts.append(_Part("industry", folder, notebooks, ""))
    custom_folder = Path(args.custom_notebooks_dir or settings.custom_notebooks_dir)
    if run_custom and not custom_folder.is_dir():
        log.error("The custom notebooks folder '%s' does not exist. Create it, or point CUSTOM_NOTEBOOKS_DIR at it.", custom_folder)
        return EXIT_CONFIG

    python = args.python or settings.notebook_python or sys.executable
    if not (Path(python).exists() or shutil.which(python)):
        log.error("The Python interpreter for the notebooks was not found: %s", python)
        return EXIT_CONFIG

    if args.dry_run:
        for part in parts:
            log.info("Pipeline for %s: %d notebook(s): %s", run_date, len(part.notebooks), ", ".join(p.stem for p in part.notebooks))
            for path in part.notebooks:
                log.info("Would run: %s (interpreter: %s, folder: %s)", path.name, python, path.parent)
        if run_custom:
            part, code = _custom_part(settings, custom_folder, (), args, run_date)
            if part:
                log.info("Custom standards: Pipeline for %s: %d notebook(s): %s", run_date, len(part.notebooks), ", ".join(p.stem for p in part.notebooks))
                for path in part.notebooks:
                    log.info("Would run: %s (interpreter: %s, folder: %s)", path.name, python, path.parent)
            elif code:
                return code
        log.info("Dry run: nothing was run")
        return EXIT_OK

    dashboard.begin(
        settings, kind="pipeline", standards=standards, run_date=run_date, redact=redact,
        args={"standards": standards, "only": args.only or [], "skipLlm": args.skip_llm, "force": args.force},
    )
    began.append(True)
    dashboard.current().event("run_started", f"Pipeline started for {run_date} ({standards} standards)", data={"standards": standards, "runDate": run_date})

    exit_code = EXIT_OK
    for part in parts:
        exit_code = max(exit_code, _run_part(part, run_date=run_date, python=python, settings=settings, args=args, redact=redact))
    if run_custom:  # decided only now: the client may have uploaded the file while the industry part was running
        part, code = _custom_part(settings, custom_folder, (), args, run_date)
        exit_code = max(exit_code, code)
        if part:
            exit_code = max(exit_code, _run_part(part, run_date=run_date, python=python, settings=settings, args=args, redact=redact))
    return exit_code


def run_pipeline(standards: str = "all", run_date: str | None = None, force: bool = False) -> int:
    """The same as `sf-pipeline --standards ...`, as a function: what the backend (FastAPI) calls when the user presses refresh
    or has uploaded standards. Returns the exit code (0 ok, 1 something failed, 2 configuration error)."""
    argv = ["--standards", standards] + (["--run-date", run_date] if run_date else []) + (["--force"] if force else [])
    return main(argv)


# ── the LLM step: sf-orchestrate ──

def _orchestrate_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sf-orchestrate",
        description="Generate diagnosis + action-plan reports for breached metrics, summaries for healthy ones and set-up plans for "
        "metrics that could not be calculated. Exit codes: 0 ok | 1 failures or no insights found | 2 configuration error.",
    )
    p.add_argument("--run-date", help="YYYY-MM-DD (default: today, UTC)")
    p.add_argument("--module", help="limit to one module: RCM, ONB2, OFB2, EC, ECP")
    p.add_argument("--metric", help="limit to one metric (its name or its file-safe key)")
    p.add_argument(
        "--standards", choices=("industry", "custom"), default="industry",
        help="industry (default): the industry benchmarks; custom: the company's own standards (their own insights table, reports table and wording)",
    )
    p.add_argument("--force", action="store_true", help="regenerate even if a cached report is current")
    p.add_argument("--dry-run", action="store_true", help="print prompts only: no LLM calls, no writes, no LLM keys needed")
    return p


def orchestrate(argv: list[str] | None = None) -> int:
    """sf-orchestrate: the LLM step on its own."""
    began: list[bool] = []
    code = EXIT_FAILED
    try:
        code = _orchestrate(argv, began)
        return code
    finally:
        if began:  # the run was being recorded: finish it (inside a pipeline run this only leaves the LLM step)
            dashboard.end(code)


def _orchestrate(argv: list[str] | None, began: list[bool]) -> int:
    args = _orchestrate_parser().parse_args(argv)

    run_date = args.run_date or datetime.now(timezone.utc).date().isoformat()
    try:
        datetime.strptime(run_date, "%Y-%m-%d")
    except ValueError:
        print(f'--run-date must be YYYY-MM-DD, got "{run_date}"', file=sys.stderr)
        return EXIT_CONFIG

    try:
        settings = load_settings(require_llm=not args.dry_run, require_custom=args.standards == "custom")
    except ConfigError as err:
        print(f"{err}\nSee .env.example", file=sys.stderr)
        return EXIT_CONFIG

    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    quiet_litellm(debug=settings.log_level.upper() == "DEBUG")

    secrets = settings.secret_values()

    def redact(text: str) -> str:
        for s in secrets:
            text = text.replace(s, "[REDACTED]")
        return text

    if not args.dry_run:
        dashboard.begin(
            settings, kind="llm", standards=args.standards, run_date=run_date, redact=redact,
            args={"module": args.module, "metric": args.metric, "force": args.force, "standards": args.standards},
        )
        began.append(True)
        dashboard.current().event("llm_step_started", f"LLM step started ({args.standards} standards)", stage=args.standards,
                                data={"chain": settings.chain, "module": args.module, "metric": args.metric, "force": args.force})

    custom = args.standards == "custom"
    prompt = load_system_prompt(args.standards)
    healthy_prompt = load_healthy_prompt(args.standards) if settings.healthy_summaries else None
    setup_prompt = load_setup_prompt(args.standards) if settings.setup_reports else None
    logging.getLogger(__name__).info(
        "Starting (%s standards): run_date=%s chain=%s prompt=%s healthy_prompt=%s setup_prompt=%s dry_run=%s",
        args.standards, run_date, settings.chain, prompt.sha, healthy_prompt.sha if healthy_prompt else "off",
        setup_prompt.sha if setup_prompt else "off", args.dry_run,
    )

    store = build_store(settings, custom=custom)

    try:
        check = getattr(store, "check", None)
        if check is not None:
            check(write_test=not args.dry_run)  # a dry run only reads; a real run also rehearses the save
    except Exception as err:  # the destination cannot be used: stop before any model is called (and paid for)
        logging.getLogger(__name__).error("%s", redact(str(err))[:600])
        return EXIT_CONFIG

    try:
        orchestrator = Orchestrator(
            store=store,
            llm=None if args.dry_run else LlmClient(settings),
            prompt=prompt,
            concurrency=settings.orchestrator_concurrency,
            redact=redact,
            healthy_prompt=healthy_prompt,
            setup_prompt=setup_prompt,
        )
        summary = asyncio.run(
            orchestrator.run(run_date, module=args.module, metric=args.metric, force=args.force, dry_run=args.dry_run)
        )
    except Exception as err:  # e.g. Supabase unreachable: fail the job clearly, without leaking secrets
        logging.getLogger(__name__).error("Run aborted: %s: %s", type(err).__name__, redact(str(err))[:500])
        return EXIT_FAILED
    counts = dataclasses.asdict(summary) if dataclasses.is_dataclass(summary) else {}
    dashboard.current().event(
        "llm_step_finished",
        f"LLM step finished: {counts.get('generated', 0)} generated, {counts.get('skipped_cached', 0)} cached, {summary.failed} failed",
        stage=args.standards, level="error" if summary.failed else "info", data=counts,
    )
    return EXIT_FAILED if summary.failed > 0 or summary.total_insights == 0 else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())