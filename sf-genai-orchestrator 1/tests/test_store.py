"""The tables the program reads and writes: the ML notebooks' insights (ML_Notebook_Insights) and the reports (LLM_Reports).

The tests run the REAL supabase client against a small fake of Supabase's table API (PostgREST) over HTTP. The fake knows the
tables' columns and unique rule, applies the date window, the ordering and the paging like the real service, and answers a missing
table, a missing column or a missing rule with the real error codes.
"""
import json
import logging
import threading
import urllib.parse
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import sf_orchestrator.pipeline as pipeline
import sf_orchestrator.store as store_module
from sf_orchestrator.reports import Orchestrator, Prompt
from sf_orchestrator.store import CombinedStore, InsightRecord, ReportRecord, TableInsights, TableReports

from helpers import BREACH_PROMPT, HEALTHY_PROMPT, RUN_DATE, FakeLlm, MemStore, SpyLlm, insight, rec


# ───────────────────────── reading the insights ─────────────────────────


KEY = "sb_secret_0123456789abcdef"


TABLE = "ML_Notebook_Insights"


INSIGHT_COLUMNS = ["execution_id", "created_at", "Module_Name", "Metric_Name", "JSON_Result"]


class _Supabase:
    tables: dict[str, list[dict]] = {}
    columns: dict[str, list[str]] = {}
    requests: list[dict[str, list[str]]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, code, message):
            self._send(status, {"code": code, "details": None, "hint": None, "message": message})

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            name = urllib.parse.unquote(url.path.removeprefix("/rest/v1/"))
            query = urllib.parse.parse_qs(url.query)
            _Supabase.requests.append(query)
            if name not in _Supabase.tables:  # exactly like PostgREST: names are case-sensitive
                return self._error(404, "PGRST205", f"Could not find the table 'public.{name}' in the schema cache")
            wanted = query.get("select", ["*"])[0].split(",")
            missing = [c for c in wanted if c != "*" and c not in _Supabase.columns[name]]
            if missing:
                return self._error(400, "42703", f"column {name}.{missing[0]} does not exist")
            rows = _Supabase.tables[name]
            for column, values in query.items():
                if column not in _Supabase.columns[name]:
                    continue
                for value in values:
                    op, _, operand = value.partition(".")
                    rows = [r for r in rows if _compare(r.get(column), op, operand)]
            if "order" in query:
                column, _, direction = query["order"][0].partition(".")
                rows = sorted(rows, key=lambda r: _sortable(r.get(column)), reverse=direction == "desc")
            offset, limit = int(query.get("offset", ["0"])[0]), query.get("limit", [None])[0]
            rows = rows[offset : offset + int(limit)] if limit else rows[offset:]
            self._send(200, [{c: r.get(c) for c in wanted if c != "*"} if wanted != ["*"] else r for r in rows])


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _sortable(value):
    return _when(value) if isinstance(value, str) and "T" in value else value


def _compare(have, op: str, operand: str) -> bool:
    if isinstance(have, str) and "T" in have:
        have, operand = _when(have), _when(operand)
    elif op == "eq":
        operand = type(have)(operand) if have is not None else operand
    return {"eq": have == operand, "gte": have >= operand, "lt": have < operand}[op]


@pytest.fixture()
def insights_url():
    _Supabase.tables, _Supabase.columns, _Supabase.requests = {TABLE: []}, {TABLE: list(INSIGHT_COLUMNS)}, []
    server = HTTPServer(("127.0.0.1", 0), _Supabase.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def store(url: str, table: str = TABLE) -> TableInsights:
    return TableInsights(url, KEY, table)


def employee_data_accuracy() -> dict:
    """The row the notebook really wrote (shortened only where it repeats): a metric it could not calculate."""
    return {
        "rca": {"factors": [], "applicable": False, "breachValue": None}, "unit": "percentage", "module": "EC",
        "forecast": {"nextYear": None, "nextMonth": None, "nextQuarter": None}, "variance": {"value": None, "percentage": None},
        "metricName": "EmployeeDataAccuracy",
        "dataQuality": {
            "checks": [
                {"category": "Completeness", "checkName": "MissingValues", "failedPct": 100.0, "staleRange": None, "affectedCells": 25129,
                 "failedRecords": 4487, "checkedRecords": 4487, "affectedColumns": ["middleName", "auditStatus"]},
                {"category": "Schema", "checkName": "RequiredColumns", "failedPct": 0.0, "staleRange": None, "failedRecords": 0, "checkedRecords": 4487, "affectedColumns": []},
                {"category": "Staleness", "checkName": "StalenessAndIncompleteData", "failedPct": 70.98, "staleRange": "> 3 years old",
                 "failedRecords": 3185, "checkedRecords": 4487, "affectedColumns": ["originalStartDate", "lastAuditDate"]},
            ],
            "dataPeriod": {"to": "2026-09-26", "from": "1969-12-31"}, "overallRating": "poor", "recordsAnalysed": 4487,
        },
        "generatedAt": "2026-10-07T06:41:53Z", "healthState": "Unknown", "companyValue": None,
        "modelAccuracy": {"rcaModel": {}, "forecastModel": {"r2": None, "mae": None, "rmse": None, "rating": "not_assessed", "modelName": "Not available"}},
        "trendAnalysis": {"periods": [], "direction": "flat", "granularity": "yearly"}, "higherIsBetter": True,
        "missingConfiguration": {"normalFields": ["middleName"], "mandatoryFields": ["auditStatus"]},
        "industryStandardValue": 98.5, "missingConfigurations": ["auditStatus", "middleName"],
    }


def row(execution_id: int, module: str, metric: str, payload, created: str = "2026-10-07T06:41:53+00:00") -> dict:
    return {"execution_id": execution_id, "created_at": created, "Module_Name": module, "Metric_Name": metric, "JSON_Result": payload}


def real_rows() -> list[dict]:
    return [
        row(96, "EC", "EmployeeDataAccuracy", employee_data_accuracy()),
        row(97, "EC", "PositionAccuracy", {**insight("PositionAccuracy", "critical"), "module": "EC"}),
        row(98, "EC", "DataSyncErrorRate", {**insight("DataSyncErrorRate", "healthy"), "module": "EC"}),
    ]


# ───────────────────────── reading the rows ─────────────────────────


def test_the_rows_created_on_the_run_date_are_the_insights_of_that_run(insights_url):
    _Supabase.tables[TABLE] = real_rows() + [row(50, "EC", "OldMetric", insight("OldMetric", "critical"), created="2026-10-06T06:00:00+00:00")]
    records = store(insights_url).list_insights("2026-10-07")
    assert [(r.module, r.metric_name) for r in records] == [("EC", "EmployeeDataAccuracy"), ("EC", "PositionAccuracy"), ("EC", "DataSyncErrorRate")]
    assert [r.metric_name for r in store(insights_url).list_insights("2026-10-06")] == ["OldMetric"]  # the day before has its own row


def test_the_day_is_a_utc_day_with_exact_edges(insights_url):
    _Supabase.tables[TABLE] = [
        row(1, "EC", "A", insight("A", "critical"), created="2026-10-06T23:59:59+00:00"),
        row(2, "EC", "B", insight("B", "critical"), created="2026-10-07T00:00:00+00:00"),
        row(3, "EC", "C", insight("C", "critical"), created="2026-10-07T23:59:59+00:00"),
        row(4, "EC", "D", insight("D", "critical"), created="2026-10-08T00:00:00+00:00"),
    ]
    assert [r.metric_name for r in store(insights_url).list_insights("2026-10-07")] == ["B", "C"]


def test_a_record_carries_the_module_the_metric_key_the_insight_and_where_it_came_from(insights_url):
    _Supabase.tables[TABLE] = real_rows()
    first = store(insights_url).list_insights("2026-10-07")[0]
    assert (first.run_date, first.module, first.metric_name, first.id) == ("2026-10-07", "EC", "EmployeeDataAccuracy", "ML_Notebook_Insights#96")
    assert first.payload["healthState"] == "Unknown" and first.payload["module"] == "EC"


def test_the_metric_key_follows_the_name_inside_the_json_and_a_module_is_added_if_the_json_has_none(insights_url):
    payload = {k: v for k, v in insight("X", "critical").items() if k != "module"}
    payload["metricName"] = "Full & Final Settlement Timeliness"
    _Supabase.tables[TABLE] = [row(7, "ECP", "something else", payload)]
    [r] = store(insights_url).list_insights("2026-10-07")
    assert (r.module, r.metric_name, r.payload["module"]) == ("ECP", "FullAndFinalSettlementTimeliness", "ECP")


def test_a_metric_with_several_rows_on_the_same_day_uses_the_newest(insights_url, caplog):
    _Supabase.tables[TABLE] = [
        row(10, "EC", "PositionAccuracy", {**insight("PositionAccuracy", "critical"), "module": "EC", "companyValue": 11}),
        row(12, "EC", "PositionAccuracy", {**insight("PositionAccuracy", "critical"), "module": "EC", "companyValue": 33}),
        row(11, "EC", "PositionAccuracy", {**insight("PositionAccuracy", "critical"), "module": "EC", "companyValue": 22}),
        row(13, "RCM", "PositionAccuracy", {**insight("PositionAccuracy", "critical"), "module": "RCM", "companyValue": 44}),  # another module
    ]
    with caplog.at_level(logging.INFO):
        records = store(insights_url).list_insights("2026-10-07")
    assert sorted((r.module, r.payload["companyValue"], r.id) for r in records) == [("EC", 33, "ML_Notebook_Insights#12"), ("RCM", 44, "ML_Notebook_Insights#13")]
    assert "2 older row(s) ignored" in caplog.text


def test_the_filters_see_module_and_metric(insights_url):
    _Supabase.tables[TABLE] = real_rows() + [row(99, "RCM", "TimeToHire", {**insight("TimeToHire", "critical"), "module": "RCM"})]
    assert [r.metric_name for r in store(insights_url).list_insights("2026-10-07", module="rcm")] == ["TimeToHire"]
    assert [r.metric_name for r in store(insights_url).list_insights("2026-10-07", metric="PositionAccuracy")] == ["PositionAccuracy"]


def test_json_stored_as_text_is_read_and_something_that_is_not_an_object_fails_alone(insights_url, caplog):
    _Supabase.tables[TABLE] = [
        row(1, "EC", "AsText", json.dumps({**insight("AsText", "critical"), "module": "EC"})),
        row(2, "EC", "Broken", "{not json"),
        row(3, "EC", "AList", [1, 2]),
        row(4, "EC", "Fine", {**insight("Fine", "critical"), "module": "EC"}),
    ]
    with caplog.at_level(logging.INFO):
        records = {r.metric_name: r for r in store(insights_url).list_insights("2026-10-07")}
    assert records["AsText"].payload["metricName"] == "AsText" and records["Fine"].payload is not None
    assert records["Broken"].payload is None and records["AList"].payload is None  # they fail validation one by one, nothing else stops
    assert "JSON_Result is not a JSON object" in caplog.text


def test_more_rows_than_one_page_are_all_read(insights_url):
    _Supabase.tables[TABLE] = [row(i, "EC", f"Metric{i}", {**insight("M", "critical"), "metricName": f"Metric{i}", "module": "EC"}) for i in range(1, 2501)]
    assert len(store(insights_url).list_insights("2026-10-07")) == 2500
    assert len([q for q in _Supabase.requests if "offset" in q]) == 3  # 1000 + 1000 + 500


def test_the_request_asks_for_the_five_columns_and_exactly_the_day(insights_url):
    _Supabase.tables[TABLE] = real_rows()
    store(insights_url).list_insights("2026-10-07")
    query = _Supabase.requests[0]
    assert query["select"] == ["execution_id,created_at,Module_Name,Metric_Name,JSON_Result"]
    assert query["created_at"] == ["gte.2026-10-07T00:00:00Z", "lt.2026-10-08T00:00:00Z"]


# ───────────────────────── when there is nothing to read ─────────────────────────


def test_an_empty_table_is_explained(insights_url, caplog):
    with caplog.at_level(logging.INFO):
        assert store(insights_url).list_insights("2026-10-07") == []
    assert "The insights table 'ML_Notebook_Insights' is empty" in caplog.text


def test_a_table_with_rows_of_other_days_says_which_day_it_has(insights_url, caplog):
    _Supabase.tables[TABLE] = real_rows()
    with caplog.at_level(logging.INFO):
        assert store(insights_url).list_insights("2026-09-29") == []
    assert "no row created on 2026-09-29 (UTC). The newest row was created 2026-10-07T06:41:53+00:00" in caplog.text


# ───────────────────────── the check before any model is called ─────────────────────────


def test_the_check_passes_for_a_good_table_and_never_writes(insights_url):
    store(insights_url).check()
    store(insights_url).check(write_test=True)
    assert _Supabase.tables[TABLE] == []


@pytest.mark.parametrize("wrong_name", ["ml_notebook_insights", "ML_Notebook_Insight"])
def test_a_wrong_insights_table_name_is_explained_with_a_hint_about_capital_letters(insights_url, wrong_name):
    with pytest.raises(RuntimeError) as err:
        store(insights_url, wrong_name).check()
    assert f"Cannot read the insights table '{wrong_name}'" in str(err.value) and "INSIGHTS_TABLE" in str(err.value) and "case-sensitive" in str(err.value)


def test_a_missing_column_is_named(insights_url):
    _Supabase.columns[TABLE].remove("JSON_Result")
    with pytest.raises(RuntimeError) as err:
        store(insights_url).check()
    assert "JSON_Result does not exist" in str(err.value) and "must have these columns" in str(err.value)


# ───────────────────────── in the pipeline ─────────────────────────


async def test_the_unknown_metric_is_skipped_and_the_others_get_their_reports(insights_url):
    _Supabase.tables[TABLE] = real_rows()
    reports = MemStore([])
    combined = CombinedStore(store(insights_url), reports)
    llm = SpyLlm()  # answers the healthy prompt with a summary and the other prompt with a diagnosis
    summary = await Orchestrator(store=combined, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=HEALTHY_PROMPT).run("2026-10-07")
    assert (summary.total_insights, summary.skipped_no_data, summary.failed) == (3, 1, 0)  # EmployeeDataAccuracy: no model call
    assert summary.generated == 2 and llm.calls == 2
    assert sorted(k[2] for k in reports.reports) == ["DataSyncErrorRate", "PositionAccuracy"]
    saved = reports.reports[("2026-10-07", "EC", "PositionAccuracy")]
    assert saved.insight_id == "ML_Notebook_Insights#97" and saved.status == "succeeded"


# ───────────────────────── the command line ─────────────────────────


def test_the_cli_reads_the_insights_table_and_writes_the_reports_table(monkeypatch, tmp_path, caplog):
    seen = {}

    class FakeInsights(MemStore):
        def __init__(self, url, key, table):
            super().__init__([])
            seen["insights_table"] = table

    class FakeReports(MemStore):
        def __init__(self, url, key, table):
            super().__init__([])
            seen["reports_table"] = table

    monkeypatch.setattr(store_module, "TableInsights", FakeInsights)
    monkeypatch.setattr(store_module, "TableReports", FakeReports)
    monkeypatch.chdir(tmp_path)
    env = {
        "SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "service-role-key-0123456789",
        "INSIGHTS_TABLE": "ML_Notebook_Insights", "REPORTS_TABLE": "LLM_Reports",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with caplog.at_level(logging.INFO):
        pipeline.orchestrate(["--run-date", RUN_DATE, "--dry-run"])
    assert (seen["insights_table"], seen["reports_table"]) == ("ML_Notebook_Insights", "LLM_Reports")
    assert "Insights: read from the table 'ML_Notebook_Insights'" in caplog.text and "Reports: saved as rows of the table 'LLM_Reports'" in caplog.text


# ───────────────────────── saving the reports ─────────────────────────


REPORT_COLUMNS = ["id", *TableReports.COLUMNS]  # the 12 columns of the table


UNIQUE = "module,metric_name"


class _Postgrest:
    tables: dict[str, list[dict]] = {}
    columns: dict[str, list[str]] = {}
    unique: dict[str, str] = {}
    reject: str | None = None  # a PostgreSQL error code that every write is answered with (a violated table rule)
    requests: list[tuple[str, str, dict[str, list[str]]]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, code, message):
            self._send(status, {"code": code, "details": None, "hint": None, "message": message})

        def _table(self):
            url = urllib.parse.urlparse(self.path)
            name = urllib.parse.unquote(url.path.removeprefix("/rest/v1/"))
            query = urllib.parse.parse_qs(url.query)
            _Postgrest.requests.append((self.command, name, query))
            if name not in _Postgrest.tables:  # exactly like PostgREST: names are case-sensitive
                self._error(404, "PGRST205", f"Could not find the table 'public.{name}' in the schema cache")
                return None, {}
            return name, query

        @staticmethod
        def _filter(rows, query):
            for column, values in query.items():
                if values[0].startswith("eq."):
                    rows = [r for r in rows if str(r.get(column)) == values[0][3:]]
            return rows

        def do_GET(self):
            name, query = self._table()
            if name is None:
                return
            wanted = query.get("select", ["*"])[0]
            missing = [c for c in wanted.split(",") if c != "*" and c not in _Postgrest.columns[name]]
            if missing:
                return self._error(400, "42703", f"column {name}.{missing[0]} does not exist")
            rows = self._filter(_Postgrest.tables[name], query)
            self._send(200, rows[: int(query["limit"][0])] if "limit" in query else rows)

        def do_DELETE(self):
            name, query = self._table()
            if name is None:
                return
            gone = self._filter(_Postgrest.tables[name], query)
            _Postgrest.tables[name] = [r for r in _Postgrest.tables[name] if r not in gone]
            self._send(200, gone)

        def do_POST(self):
            name, query = self._table()
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            if name is None:
                return
            rows = body if isinstance(body, list) else [body]
            unknown = sorted({k for row in rows for k in row} - set(_Postgrest.columns[name]))
            if unknown:
                return self._error(400, "PGRST204", f"Could not find the '{unknown[0]}' column of '{name}' in the schema cache")
            conflict = query.get("on_conflict", [""])[0]
            if conflict and conflict != _Postgrest.unique[name]:
                return self._error(400, "42P10", "there is no unique or exclusion constraint matching the ON CONFLICT specification")
            if _Postgrest.reject:
                return self._error(400, _Postgrest.reject, f'new row for relation "{name}" violates check constraint "llm_reports_report_matches_status"')
            saved, keys = [], conflict.split(",") if conflict else []
            for row in rows:
                existing = next((r for r in _Postgrest.tables[name] if keys and all(r.get(k) == row.get(k) for k in keys)), None)
                if existing is not None:
                    existing.update(row)
                    saved.append(existing)
                else:
                    _Postgrest.tables[name].append({"id": f"id-{len(_Postgrest.tables[name]) + 1}", **row})
                    saved.append(_Postgrest.tables[name][-1])
            self._send(201, saved)


@pytest.fixture()
def reports_url():
    _Postgrest.tables, _Postgrest.columns, _Postgrest.unique = {"LLM_Reports": []}, {"LLM_Reports": list(REPORT_COLUMNS)}, {"LLM_Reports": UNIQUE}
    _Postgrest.reject, _Postgrest.requests = None, []
    server = HTTPServer(("127.0.0.1", 0), _Postgrest.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def methods() -> list[str]:
    return [m for m, _, _ in _Postgrest.requests]


REPORT = {
    "metricName": "Time To Hire", "healthState": "critical",
    "aFieldAFutureVersionAdds": {"nested": [1, 2, {"deep": True}]},
}


def record(status="succeeded", module="RCM", metric="TimeToHire", run_date="2026-10-04") -> ReportRecord:
    ok = status == "succeeded"
    return ReportRecord(
        run_date=run_date, module=module, metric_name=metric, input_hash="h" * 8 if ok else "", prompt_sha="p" * 6, status=status,
        generated_at="2026-10-04T10:00:00+00:00", insight_id=f"insights/{run_date}/{module}/{metric}.json",
        provider="gemini" if ok else None, model="gemini-3.5-flash" if ok else None,
        report=REPORT if ok else None, error=None if ok else "boom", llm_meta={"fallbacks": 1} if ok else {},
    )


# ───────────────────────── what is written ─────────────────────────


def test_a_report_becomes_one_row_with_exactly_the_twelve_columns(reports_url):
    TableReports(reports_url, KEY, "LLM_Reports").save_report(record())
    [row] = _Postgrest.tables["LLM_Reports"]
    assert set(row) == set(REPORT_COLUMNS)  # nothing else is sent: a table with just these columns is enough
    assert (row["run_date"], row["module"], row["metric_name"], row["status"]) == ("2026-10-04", "RCM", "TimeToHire", "succeeded")
    assert (row["provider"], row["model"], row["error"], row["prompt_sha"]) == ("gemini", "gemini-3.5-flash", None, "p" * 6)
    assert row["generated_at"] == "2026-10-04T10:00:00+00:00"


def test_the_whole_report_json_goes_into_the_report_column_as_it_is(reports_url):
    """Whatever a report version contains, including fields that do not exist yet, is stored untouched."""
    TableReports(reports_url, KEY, "LLM_Reports").save_report(record())
    assert _Postgrest.tables["LLM_Reports"][0]["report"] == REPORT


def test_the_fingerprint_and_the_insight_path_travel_inside_llm_meta_and_come_back_out(reports_url):
    store = TableReports(reports_url, KEY, "LLM_Reports")
    store.save_report(record())
    assert _Postgrest.tables["LLM_Reports"][0]["llm_meta"] == {
        "fallbacks": 1, "inputHash": "h" * 8, "insightId": "insights/2026-10-04/RCM/TimeToHire.json",
    }
    assert store.find_report("2026-10-04", "RCM", "TimeToHire") == record()  # the extra keys are taken out again


def test_the_table_name_is_used_exactly_and_the_upsert_is_on_the_two_key_columns(reports_url):
    TableReports(reports_url, KEY, "LLM_Reports").save_report(record())
    method, table, query = _Postgrest.requests[-1]
    assert (method, table, query["on_conflict"]) == ("POST", "LLM_Reports", [UNIQUE])  # capital letters kept


def test_a_new_day_replaces_the_row_of_the_metric_instead_of_adding_one(reports_url):
    """One row per metric: the newest. The reports of earlier days are not kept."""
    store = TableReports(reports_url, KEY, "LLM_Reports")
    store.save_report(record(run_date="2026-10-04"))
    store.save_report(record(run_date="2026-10-05"))
    store.save_report(record(metric="OfferAcceptance", run_date="2026-10-05"))
    rows = _Postgrest.tables["LLM_Reports"]
    assert sorted((r["metric_name"], r["run_date"]) for r in rows) == [("OfferAcceptance", "2026-10-05"), ("TimeToHire", "2026-10-05")]
    assert store.find_report("2026-10-09", "RCM", "TimeToHire").run_date == "2026-10-05"  # found whatever day is asked for


def test_saving_again_replaces_the_row_instead_of_adding_a_second_one(reports_url):
    store = TableReports(reports_url, KEY, "LLM_Reports")
    store.save_report(record())
    store.save_report(ReportRecord(**{**asdict(record()), "model": "gemini-3.6-flash"}))
    assert len(_Postgrest.tables["LLM_Reports"]) == 1 and _Postgrest.tables["LLM_Reports"][0]["model"] == "gemini-3.6-flash"


def test_a_failed_report_is_a_row_without_report_and_with_the_error(reports_url):
    store = TableReports(reports_url, KEY, "LLM_Reports")
    store.save_report(record(status="failed"))
    [row] = _Postgrest.tables["LLM_Reports"]
    assert (row["status"], row["report"], row["error"]) == ("failed", None, "boom")
    assert store.find_report("2026-10-04", "RCM", "TimeToHire") == record(status="failed")


def test_a_saved_report_is_found_again_and_a_missing_one_is_none(reports_url):
    store = TableReports(reports_url, KEY, "LLM_Reports")
    assert store.find_report("2026-10-04", "RCM", "TimeToHire") is None
    store.save_report(record())
    assert store.find_report("2026-10-04", "RCM", "TimeToHire") == record()
    assert store.find_report("2026-10-04", "EC", "TimeToHire") is None
    assert store.find_report("2026-10-04", "RCM", "OfferAcceptance") is None


def test_a_table_with_more_columns_than_needed_works_too(reports_url):
    _Postgrest.columns["LLM_Reports"] += ["metric_title", "health_state", "created_at"]
    store = TableReports(reports_url, KEY, "LLM_Reports")
    store.save_report(record())
    assert store.find_report("2026-10-04", "RCM", "TimeToHire") == record()


# ───────────────────────── the check before any model is called ─────────────────────────


def test_the_check_passes_for_a_good_table_and_a_dry_run_check_writes_nothing(reports_url):
    TableReports(reports_url, KEY, "LLM_Reports").check()
    assert methods() == ["GET"] and _Postgrest.tables["LLM_Reports"] == []


def test_the_write_check_rehearses_the_save_twice_on_two_days_removes_its_row_and_leaves_real_rows_alone(reports_url):
    store = TableReports(reports_url, KEY, "LLM_Reports")
    store.save_report(record())
    before = list(_Postgrest.tables["LLM_Reports"])
    _Postgrest.requests.clear()
    store.check(write_test=True)
    assert methods() == ["GET", "POST", "POST", "GET", "DELETE"]  # the second write proves that a row is REPLACED
    assert _Postgrest.tables["LLM_Reports"] == before


@pytest.mark.parametrize("wrong_name", ["llm_reports", "LLM_reports", "LLM_Report"])
def test_a_wrong_reports_table_name_is_explained_with_a_hint_about_capital_letters(reports_url, wrong_name):
    with pytest.raises(RuntimeError) as err:
        TableReports(reports_url, KEY, wrong_name).check()
    assert f"Cannot use the reports table '{wrong_name}'" in str(err.value) and "PGRST205" in str(err.value)
    assert "sql/llm_reports.sql" in str(err.value) and "case-sensitive" in str(err.value)


def test_a_missing_column_is_named_before_any_model_is_called(reports_url):
    _Postgrest.columns["LLM_Reports"].remove("llm_meta")
    with pytest.raises(RuntimeError) as err:
        TableReports(reports_url, KEY, "LLM_Reports").check()
    assert "llm_meta does not exist" in str(err.value) and "must have these columns" in str(err.value) and "sql/llm_reports.sql" in str(err.value)


def test_a_missing_one_row_rule_is_found_by_the_write_check_and_the_probe_row_is_cleaned_up(reports_url):
    _Postgrest.unique["LLM_Reports"] = ""  # the table has no unique rule on the three columns
    store = TableReports(reports_url, KEY, "LLM_Reports")
    store.check()  # reading cannot see a missing rule, which is why a real run rehearses the save
    with pytest.raises(RuntimeError) as err:
        store.check(write_test=True)
    assert "no rule 'one row per module and metric_name'" in str(err.value) and "sql/llm_reports.sql" in str(err.value)
    assert _Postgrest.tables["LLM_Reports"] == []


def test_a_table_rule_that_rejects_the_rehearsal_is_reported(reports_url):
    _Postgrest.reject = "23514"
    with pytest.raises(RuntimeError, match="A rule of the table rejected the test row"):
        TableReports(reports_url, KEY, "LLM_Reports").check(write_test=True)


# ───────────────────────── insights in, reports to the table ─────────────────────────


def _row(day="2026-10-04", **over):
    return InsightRecord(
        run_date=day, module="RCM", metric_name="TimeToHire", id=f"{day}/TimeToHire",
        payload={**insight("TimeToHire", "critical"), "module": "RCM", **over},
    )


async def test_end_to_end_the_insights_in_and_the_table_out(reports_url):
    store = CombinedStore(MemStore([_row()]), TableReports(reports_url, KEY, "LLM_Reports"))
    llm = FakeLlm()
    orchestrator = Orchestrator(store=store, llm=llm, prompt=Prompt("system", "abc123"))

    summary = await orchestrator.run("2026-10-04")
    assert (summary.generated, summary.failed) == (1, 0)
    [row] = _Postgrest.tables["LLM_Reports"]
    assert (row["metric_name"], row["status"], row["provider"]) == ("TimeToHire", "succeeded", "gemini")
    assert set(row["report"]) == {"metricName", "healthState", "factors", "diagnosis", "businessImpact", "workstreams", "plan", "assumptionsAndRisks"}
    assert row["llm_meta"]["insightId"] == "2026-10-04/TimeToHire" and row["llm_meta"]["inputHash"]

    assert (await orchestrator.run("2026-10-04")).skipped_cached == 1 and llm.calls == 1  # the cache is read from the table


async def test_a_changed_input_replaces_the_row_of_the_same_day(reports_url):
    insights = MemStore([_row()])
    store = CombinedStore(insights, TableReports(reports_url, KEY, "LLM_Reports"))
    orchestrator = Orchestrator(store=store, llm=FakeLlm(), prompt=Prompt("system", "abc123"))
    await orchestrator.run("2026-10-04")
    insights.rows[0] = _row(companyValue=40)
    assert (await orchestrator.run("2026-10-04")).generated == 1
    assert len(_Postgrest.tables["LLM_Reports"]) == 1  # replaced, not added


async def test_a_failure_never_replaces_a_good_row(reports_url):
    store = CombinedStore(MemStore([_row()]), TableReports(reports_url, KEY, "LLM_Reports"))
    await Orchestrator(store=store, llm=FakeLlm(), prompt=Prompt("system", "abc123")).run("2026-10-04")
    await Orchestrator(store=store, llm=FakeLlm([RuntimeError("all models down")]), prompt=Prompt("system", "abc123")).run("2026-10-04", force=True)
    assert [r["status"] for r in _Postgrest.tables["LLM_Reports"]] == ["succeeded"]


async def test_a_new_day_keeps_one_row_and_a_failed_day_keeps_the_last_good_row(reports_url):
    insights = MemStore([_row("2026-10-04"), _row("2026-10-05")])
    store = CombinedStore(insights, TableReports(reports_url, KEY, "LLM_Reports"))
    llm = FakeLlm()
    orchestrator = Orchestrator(store=store, llm=llm, prompt=Prompt("system", "abc123"))
    await orchestrator.run("2026-10-04")
    assert (await orchestrator.run("2026-10-05")).skipped_cached == 1 and llm.calls == 1  # the same insight and prompt: still current
    insights.rows[1] = _row("2026-10-05", companyValue=40)
    await Orchestrator(store=store, llm=FakeLlm([RuntimeError("all models down")]), prompt=Prompt("system", "abc123")).run("2026-10-05")
    assert [(r["status"], r["run_date"]) for r in _Postgrest.tables["LLM_Reports"]] == [("succeeded", "2026-10-04")]  # the good row stays
    assert (await orchestrator.run("2026-10-05")).generated == 1
    assert [(r["status"], r["run_date"]) for r in _Postgrest.tables["LLM_Reports"]] == [("succeeded", "2026-10-05")]  # replaced, not added


# ───────────────────────── one failed save must not stop the others ─────────────────────────


class FlakyStore(MemStore):
    """Saving the first metric fails (for example the table was dropped), the others work."""

    def save_report(self, record):
        if record.metric_name == "Alpha":
            raise ConnectionError("the table is unreachable")
        super().save_report(record)


async def test_a_report_that_cannot_be_saved_is_counted_as_failed_and_the_run_goes_on(caplog):
    store = FlakyStore([rec("RCM", "Alpha", insight("Alpha", "critical")), rec("RCM", "Beta", insight("Beta", "critical"))])
    with caplog.at_level(logging.INFO):
        summary = await Orchestrator(store=store, llm=FakeLlm(), prompt=Prompt("system", "abc123")).run(RUN_DATE)
    assert (summary.generated, summary.failed) == (1, 1)
    assert [k[2] for k in store.reports] == ["Beta"]
    assert "RCM/Alpha: the report was generated but could not be saved: ConnectionError: the table is unreachable" in caplog.text
    assert summary.failures[0]["reason"].startswith("the report could not be saved")


# ───────────────────────── the CLI ─────────────────────────


def _cli_env(monkeypatch, tmp_path, **extra):
    monkeypatch.chdir(tmp_path)  # so a developer's real .env is not picked up
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "LLM_CHAIN", "REPORTS_TABLE", "INSIGHTS_TABLE"):
        monkeypatch.delenv(name, raising=False)
    env = {
        "SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "service-role-key-0123456789",
        "INSIGHTS_TABLE": "ML_Notebook_Insights", "REPORTS_TABLE": "LLM_Reports", **extra,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_the_cli_sends_the_reports_to_the_table_and_rehearses_the_save_only_in_a_real_run(monkeypatch, tmp_path, caplog):
    seen = {"checks": []}

    class FakeTable(MemStore):
        def __init__(self, url, key, table):
            super().__init__([])
            seen["table"] = table

        def check(self, write_test=False):
            seen["checks"].append(write_test)

    monkeypatch.setattr(store_module, "TableInsights", lambda *a: MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))]))
    monkeypatch.setattr(store_module, "TableReports", FakeTable)
    _cli_env(monkeypatch, tmp_path)
    with caplog.at_level(logging.INFO):
        assert pipeline.orchestrate(["--run-date", RUN_DATE, "--dry-run"]) == 0
    assert seen["table"] == "LLM_Reports" and "saved as rows of the table 'LLM_Reports'" in caplog.text
    assert seen["checks"] == [False]  # a dry run only reads

    seen["checks"].clear()
    monkeypatch.setattr(pipeline, "LlmClient", lambda *a, **k: FakeLlm(draft_factors=2))
    _cli_env(monkeypatch, tmp_path, LLM_CHAIN="gemini/gemini-a", GEMINI_API_KEY="gemini-key-1234567890")
    assert pipeline.orchestrate(["--run-date", RUN_DATE]) == 0
    assert seen["checks"] == [True]  # a real run rehearses the save before any model is called


def test_the_cli_stops_before_any_model_call_when_the_table_cannot_be_used(monkeypatch, tmp_path, caplog):
    class BrokenTable(MemStore):
        def __init__(self, url, key, table):
            super().__init__([])

        def check(self, write_test=False):
            raise RuntimeError("Cannot use the reports table 'LLM_Reports' (42P10: no unique rule). Run sql/llm_reports.sql")

    monkeypatch.setattr(store_module, "TableInsights", lambda *a: MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))]))
    monkeypatch.setattr(store_module, "TableReports", BrokenTable)
    monkeypatch.setattr(pipeline, "LlmClient", lambda *a, **k: pytest.fail("a model must not be called when the table is unusable"))
    _cli_env(monkeypatch, tmp_path, LLM_CHAIN="gemini/gemini-a", GEMINI_API_KEY="gemini-key-1234567890")
    with caplog.at_level(logging.INFO):
        assert pipeline.orchestrate(["--run-date", RUN_DATE]) == 2
    assert "Cannot use the reports table 'LLM_Reports'" in caplog.text
