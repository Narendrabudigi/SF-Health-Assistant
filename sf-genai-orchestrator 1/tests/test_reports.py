"""One run, end to end, with a fake store and a fake model: a diagnosis for a breached metric, a summary for a healthy one, a set-up
plan for a metric that could not be calculated, readable metric names, and the glossary.
"""
import copy
import json
import logging
import re
from datetime import date
from importlib import resources
from pathlib import Path
from types import SimpleNamespace

import pytest
import sf_orchestrator.pipeline as pipeline
from sf_orchestrator import reports as glossary
from sf_orchestrator.config import Settings
from sf_orchestrator.reports import (
    PHASES,
    PHASES_SETUP,
    Orchestrator,
    Prompt,
    build_factors,
    build_healthy_report,
    build_report,
    build_user_prompt,
    glossary_for,
    label_for,
    load_healthy_prompt,
    load_setup_prompt,
    load_system_prompt,
)
from sf_orchestrator.schemas import FORECAST_NOT_USABLE, MetricInsight, ReportError, _cut_by_the_data, ignored_fields, parse_summary, round_floats
from sf_orchestrator.store import metric_key

from helpers import BREACH_PROMPT, HEALTHY_PROMPT, P1, P2, RUN_DATE, SUMMARY, FakeLlm, MemStore, SpyLlm, insight, rec


# ───────────────────────── the run ─────────────────────────


PROMPT = Prompt(text="system", sha="abc123")


def make(llm: FakeLlm, store: MemStore, **kw) -> Orchestrator:
    return Orchestrator(store=store, llm=llm, prompt=PROMPT, concurrency=2, **kw)


def rows():
    """Breached metrics across four different modules, plus one healthy metric."""
    return [
        rec("RCM", "TimeToHire", insight("TimeToHire", "critical")),
        rec("ONB2", "OnboardingCompletionDays", insight("OnboardingCompletionDays", "at-risk")),
        rec("OFB2", "ExitTaskOverdueRate", insight("ExitTaskOverdueRate", "at-risk", unit="percent")),
        rec("EC", "DataCompletenessScore", insight("DataCompletenessScore", "critical", higherIsBetter=True)),
        rec("ECP", "PayrollRunDuration", insight("PayrollRunDuration", "healthy")),
    ]


async def test_handles_any_metric_in_any_module_and_skips_healthy_ones():
    llm, store = FakeLlm(), MemStore(rows())
    s = await make(llm, store).run(RUN_DATE)
    assert (s.total_insights, s.generated, s.skipped_healthy, s.failed) == (5, 4, 1, 0)
    assert sorted(k[1] for k in store.reports) == ["EC", "OFB2", "ONB2", "RCM"]
    assert llm.calls == 4


async def test_tells_the_model_which_module_and_metric_it_is_looking_at():
    llm = FakeLlm()
    await make(llm, MemStore(rows())).run(RUN_DATE, module="ONB2")
    assert "<module>ONB2</module>" in llm.last_user_prompt and "OnboardingCompletionDays" in llm.last_user_prompt


async def test_stamps_metric_name_and_health_state_from_the_ml_input_not_the_model():
    store = MemStore(rows())
    await make(FakeLlm(), store).run(RUN_DATE, module="EC")
    saved = store.reports[(RUN_DATE, "EC", "DataCompletenessScore")]
    assert saved.report["metricName"] == "DataCompletenessScore" and saved.report["healthState"] == "critical"
    assert saved.provider == "gemini" and saved.llm_meta["fallbacks"] == 0


async def test_the_stored_report_has_the_model_text_plus_lifted_factors_and_code_totals():
    store = MemStore(rows())
    await make(FakeLlm(), store).run(RUN_DATE, module="RCM")
    r = store.reports[(RUN_DATE, "RCM", "TimeToHire")].report
    assert [f["id"] for f in r["factors"]] == ["F1", "F2"] and r["factors"][0]["impactPct"] == 54.4
    assert r["plan"]["totalHours"] == 42 and r["plan"]["durationWeeks"] == 4
    assert r["plan"]["roles"][0]["role"] == "SAP SuccessFactors Recruiting Lead Functional Consultant"
    assert not {"trend", "snapshot", "targetOutcome", "successCriteria"} & set(r)


async def test_is_idempotent_reruns_reuse_cached_reports_and_force_regenerates():
    llm, store = FakeLlm(), MemStore(rows())
    o = make(llm, store)
    await o.run(RUN_DATE)
    second = await o.run(RUN_DATE)
    assert (second.skipped_cached, second.generated, llm.calls) == (4, 0, 4)
    assert (await o.run(RUN_DATE, force=True)).generated == 4


async def test_regenerates_when_the_ml_output_changes():
    store = MemStore(rows())
    o = make(FakeLlm(), store)
    await o.run(RUN_DATE, metric="TimeToHire")
    store.rows[0] = rec("RCM", "TimeToHire", insight("TimeToHire", "critical", companyValue=35))
    assert (await o.run(RUN_DATE, metric="TimeToHire")).generated == 1


async def test_a_changed_prompt_regenerates_cached_reports():
    store = MemStore(rows())
    await make(FakeLlm(), store).run(RUN_DATE)
    llm2 = FakeLlm()
    o2 = Orchestrator(store=store, llm=llm2, prompt=Prompt("system v2", "def456"), concurrency=2)
    assert (await o2.run(RUN_DATE)).generated == 4


async def test_records_failures_keeps_going_and_a_later_run_replaces_them():
    store = MemStore(rows())
    s = await make(FakeLlm([RuntimeError("all models exhausted")]), store).run(RUN_DATE)
    assert s.failed == 4 and len(s.failures) == 4
    assert all(r.status == "failed" for r in store.reports.values())

    await make(FakeLlm(), store).run(RUN_DATE)
    assert all(r.status == "succeeded" for r in store.reports.values())


async def test_a_failure_never_overwrites_a_good_report():
    store = MemStore(rows())
    await make(FakeLlm(), store).run(RUN_DATE, metric="TimeToHire")
    await make(FakeLlm([RuntimeError("boom")]), store).run(RUN_DATE, metric="TimeToHire", force=True)
    assert store.reports[(RUN_DATE, "RCM", "TimeToHire")].status == "succeeded"


async def test_rejects_an_invalid_ml_payload_without_calling_the_llm():
    llm = FakeLlm()
    s = await make(llm, MemStore([rec("RCM", "Broken", {"metricName": "Broken"})])).run(RUN_DATE)
    assert s.failed == 1 and llm.calls == 0


async def test_sends_the_full_contract_to_the_llm_but_never_undeclared_fields():
    llm = FakeLlm()
    payload = insight("TimeToHire", "critical", rawRecords=[{"candidateId": "C-1"}], recordCount=999)
    await make(llm, MemStore([rec("RCM", "TimeToHire", payload)])).run(RUN_DATE)
    p = llm.last_user_prompt
    assert "industryStandardValue" in p and "predictedValue" in p and "lowerBound" in p and "SIGNING_BONUS" in p
    assert "checkName" in p and "rcaModel" not in p  # data quality reaches the model, the accuracy of the models does not
    assert '"id":"F1"' in p and "impactPct" in p  # factor ids added by code, shares from the notebook
    assert '"yearly"' in p and '"equalPeriodComparisons"' in p and '"children"' not in p  # the trend tree is sent flattened
    assert '"monthly"' not in p and '"quarterly"' not in p  # a diagnosis never quotes these series, so they cost no tokens
    assert "generatedAt" not in p  # a timestamp must not reach the model or break the cache
    assert "C-1" not in p and "recordCount" not in p


async def test_secrets_are_redacted_from_stored_failure_reasons():
    store = MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))])
    o = make(FakeLlm([RuntimeError("401 for key sk-SECRET-12345")]), store, redact=lambda t: t.replace("sk-SECRET-12345", "[REDACTED]"))
    await o.run(RUN_DATE)
    err = store.reports[(RUN_DATE, "RCM", "TimeToHire")].error
    assert "sk-SECRET" not in err and "[REDACTED]" in err


async def test_dry_run_prints_prompts_and_writes_nothing(capsys):
    store = MemStore(rows())
    o = Orchestrator(store=store, llm=None, prompt=PROMPT)
    s = await o.run(RUN_DATE, dry_run=True)
    assert s.dry_run == 4 and store.reports == {}
    assert "DRY RUN RCM/TimeToHire" in capsys.readouterr().out


async def test_a_module_mismatch_between_the_row_and_the_json_is_rejected_without_calling_the_llm():
    llm = FakeLlm()
    payload = {**insight("TimeToHire", "critical"), "module": "EC"}
    s = await make(llm, MemStore([rec("RCM", "TimeToHire", payload)])).run(RUN_DATE)
    assert s.failed == 1 and llm.calls == 0 and "module" in s.failures[0]["reason"]


async def test_fields_the_orchestrator_does_not_use_are_reported_in_the_log(caplog):
    payload = insight("TimeToHire", "critical", dataQualityAssessment={"x": 1})
    with caplog.at_level(logging.WARNING):
        await make(FakeLlm(), MemStore([rec("RCM", "TimeToHire", payload)])).run(RUN_DATE)
    assert "dataQualityAssessment" in caplog.text


async def test_a_healthy_metric_in_the_notebook_format_is_skipped_without_a_call():
    llm = FakeLlm()
    s = await make(llm, MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "healthy"))])).run(RUN_DATE)
    assert s.skipped_healthy == 1 and llm.calls == 0


async def test_a_dry_run_writes_nothing_even_when_a_metric_is_invalid():
    store = MemStore([rec("RCM", "Broken", {"metricName": "Broken"})])
    s = await Orchestrator(store=store, llm=None, prompt=PROMPT).run(RUN_DATE, dry_run=True)
    assert s.failed == 1 and store.reports == {}


async def test_the_log_says_which_model_answered_and_what_it_took(caplog):
    with caplog.at_level(logging.INFO):
        await make(FakeLlm(retries=2, fallbacks=1), MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))])).run(RUN_DATE)
    assert "RCM/TimeToHire: report generated by gemini/gemini-a (after 2 retries, 1 fallback)" in caplog.text


async def test_a_clean_run_logs_just_the_model_that_answered(caplog):
    with caplog.at_level(logging.INFO):
        await make(FakeLlm(), MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))])).run(RUN_DATE)
    line = next(r.getMessage() for r in caplog.records if "report generated" in r.getMessage())
    assert line == "RCM/TimeToHire: report generated by gemini/gemini-a"


async def test_the_stored_report_records_retries_and_fallbacks():
    store = MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))])
    await make(FakeLlm(retries=2, fallbacks=1), store).run(RUN_DATE)
    meta = store.reports[(RUN_DATE, "RCM", "TimeToHire")].llm_meta
    assert (meta["retries"], meta["fallbacks"], meta["repairs"]) == (2, 1, 0)


# ───────────────────────── healthy metrics get a summary ─────────────────────────


FILLER = (
    "The metric is reported for every complete period that the data covers, and the same checks were applied to all of "
    "the records that were analysed for this summary."
)  # 29 plain words: lets a short sentence under test reach the minimum length, so the rule under test is the one that fires


def month(period: str, m: int, average: float) -> dict:
    return {"period": period, "month": m, "average": average, "isPartial": False}


def offboarding_metric() -> dict:
    """The healthy metric as the notebook wrote it: no partial flags where the data is cut, long decimals, impossible forecast."""
    return {
        "metricName": "Offboarding Cycle Time", "unit": "days", "higherIsBetter": False, "companyValue": 44.283266678292,
        "industryStandardValue": "30 to 60", "healthState": "Healthy", "variance": {"value": 0.0, "percentage": 0.0},
        "trendAnalysis": {"direction": "down", "granularity": "yearly", "periods": [
            {"period": "2024", "year": 2024, "average": 51.54740063525884, "isPartial": False, "children": {"granularity": "quarterly", "periods": [
                {"period": "2024-Q4", "quarter": 4, "average": 51.54740063525884, "isPartial": False, "children": {"granularity": "monthly", "periods": [
                    month("2024-10", 10, 51.90909090909091), month("2024-11", 11, 54.499101065495644), month("2024-12", 12, 48.861063212099815)]}}]}},
            {"period": "2025", "year": 2025, "average": 43.20309097502755, "isPartial": False, "children": {"granularity": "quarterly", "periods": [
                {"period": "2025-Q1", "quarter": 1, "average": 40.50581739258593, "isPartial": False},
                {"period": "2025-Q2", "quarter": 2, "average": 45.64429477145522, "isPartial": False},
                {"period": "2025-Q3", "quarter": 3, "average": 42.784037421085856, "isPartial": False},
                {"period": "2025-Q4", "quarter": 4, "average": 42.96027300029437, "isPartial": False}]}},
            {"period": "2026", "year": 2026, "average": 43.586433487478956, "isPartial": True, "children": {"granularity": "quarterly", "periods": [
                {"period": "2026-Q1", "quarter": 1, "average": 46.110274625865706, "isPartial": False},
                {"period": "2026-Q2", "quarter": 2, "average": 44.498998214746514, "isPartial": False},
                {"period": "2026-Q3", "quarter": 3, "average": 36.8917452851264, "isPartial": False, "children": {"granularity": "monthly", "periods": [
                    month("2026-07", 7, 40.083624547534455), month("2026-08", 8, 31.865783189943418), month("2026-09", 9, 13.5)]}}]}}]},
        "forecast": {
            "nextMonth": {"period": "2026-10", "predictedValue": -4.773953914468283, "lowerBound": -22.363913233897456, "upperBound": 12.81600540496089, "predictedHealthState": "At-risk"},
            "nextQuarter": {"period": "2026-Q4", "predictedValue": -41.04820958491885, "lowerBound": -58.63816890434802, "upperBound": -23.458250265489678, "predictedHealthState": "At-risk"},
            "nextYear": {"period": "2027", "predictedValue": -199.85642884137727, "lowerBound": -217.44638816080644, "upperBound": -182.2664695219481, "predictedHealthState": "At-risk"}},
        "rca": {"applicable": True, "breachValue": None, "factors": [
            {"rank": 1, "factorName": "num__noticeServedDays", "segment": None, "avgFactorValue": None, "segmentAvgValue": None, "impactValue": 8.16310411403343, "impactPct": 12.926360035092074}]},
        "dataQuality": {"overallRating": "fair", "dataPeriod": {"from": "2024-10-14", "to": "2026-09-06"}, "recordsAnalysed": 1129, "checks": [
            {"checkName": "MandatoryFieldsMissing", "category": "Completeness", "checkedRecords": 1129, "failedRecords": 17, "failedPct": 1.5057573073516386, "affectedColumns": ["offboardingCompletionDate"], "staleRange": None},
            {"checkName": "InvalidValues", "category": "Validity", "checkedRecords": 1129, "failedRecords": 0, "failedPct": 0.0, "affectedColumns": ["offboardingCompletionDate"], "staleRange": None},
            {"checkName": "PotentiallyStaleOrIncomplete", "category": "Staleness", "checkedRecords": 1129, "failedRecords": 17, "failedPct": 1.5057573073516386, "affectedColumns": ["offboardingCompletionDate"], "staleRange": {"from": "2026-07-06", "to": "2026-09-08"}}]},
        "modelAccuracy": {
            "rcaModel": {"modelName": "Ridge Regression", "r2": 0.5717897102560313, "mae": 8.511331755504544, "rmse": 11.573338495938385, "rating": "No strong overfit signal"},
            "forecastModel": {"modelName": "DampedTrend", "r2": 0.7608196568091625, "mae": 7.303660063119179, "rmse": 8.974469040525088, "rating": "not_assessed"}},
        "missingConfigurations": {"mandatory": [], "other": []},
    }


def module_file(*metrics: dict, module: str = "OFB2", generated: str = "2026-10-06T07:01:51.030658+00:00") -> dict:
    return {"generatedAt": generated, "module": module, "metrics": list(metrics) or [offboarding_metric()]}


def as_insight(metric: dict | None = None) -> MetricInsight:
    return MetricInsight.model_validate({**(metric or offboarding_metric()), "module": "OFB2"})


# ───────────────────────── a file that holds a module's metrics ─────────────────────────


# ───────────────────────── reading the metric ─────────────────────────


def test_the_healthy_metric_of_the_module_file_is_accepted():
    m = as_insight()
    assert m.health_state == "healthy" and m.industry_standard_value == "30 to 60" and m.forecast.next_month.predicted_health_state == "at-risk"
    assert m.missing_configurations == {"mandatory": [], "other": []} and m.missing_fields() == []


def test_missing_fields_are_the_same_whether_a_list_or_groups_are_sent():
    grouped = {**offboarding_metric(), "missingConfigurations": {"mandatory": ["A_FIELD"], "other": ["B_FIELD", "C_FIELD"]}}
    assert as_insight(grouped).missing_fields() == ["A_FIELD", "B_FIELD", "C_FIELD"]
    assert as_insight({**offboarding_metric(), "missingConfigurations": ["X_FIELD"]}).missing_fields() == ["X_FIELD"]
    assert as_insight(grouped).for_prompt()["missingConfigurations"] == {"mandatory": ["A_FIELD"], "other": ["B_FIELD", "C_FIELD"]}


def test_a_period_the_data_cuts_is_marked_partial_even_when_the_notebook_did_not_flag_it():
    trend = as_insight().for_prompt(summary=True)["trendAnalysis"]  # a summary quotes every series; a diagnosis gets only the yearly one
    flagged = lambda level: {e["period"] for e in trend[level] if e.get("partial")}
    assert flagged("yearly") == {"2024", "2026"}  # the data starts on 2024-10-14 and ends on 2026-09-06
    assert flagged("quarterly") == {"2024-Q4", "2026-Q3"}
    assert flagged("monthly") == {"2024-10", "2026-09"}  # 2026-09 holds six days: its 13.5 is not a month's average


def test_only_complete_same_quarters_are_compared_so_the_cut_quarter_is_not():
    pairs = as_insight().for_prompt()["trendAnalysis"]["equalPeriodComparisons"]
    assert [(p["earlierPeriod"], p["earlierAverage"], p["laterPeriod"], p["laterAverage"]) for p in pairs] == [
        ("2025-Q1", 40.51, "2026-Q1", 46.11),
        ("2025-Q2", 45.64, "2026-Q2", 44.5),
    ]


@pytest.mark.parametrize(
    "period,first,last,cut",
    [
        ("2025-Q2", date(2024, 10, 14), date(2026, 9, 6), False),  # inside the data
        ("2024-Q4", date(2024, 10, 14), date(2026, 9, 6), True),   # the data starts inside it
        ("2026-09", date(2024, 10, 14), date(2026, 9, 6), True),   # the data ends inside it
        ("2026-09", date(2024, 10, 14), date(2026, 9, 30), False),  # the data ends on its last day
        ("2030", date(2024, 10, 14), date(2026, 9, 6), False),     # outside the data altogether
        ("2025", None, None, False),                               # no data period known
        ("not a period", date(2024, 1, 1), date(2026, 1, 1), False),
    ],
)
def test_when_a_period_is_cut_by_the_data(period, first, last, cut):
    assert _cut_by_the_data(period, (first, last) if first or last else None) is cut


def test_a_forecast_of_negative_days_is_replaced_by_a_note_the_model_can_repeat():
    forecast = as_insight().for_prompt()["forecast"]
    assert forecast == {"notUsable": FORECAST_NOT_USABLE}


def test_a_usable_forecast_and_a_unit_that_may_be_negative_are_left_alone():
    ok = {**offboarding_metric(), "forecast": {"nextMonth": {"period": "2026-10", "predictedValue": 40.0, "lowerBound": 30.0, "upperBound": 50.0}}}
    assert as_insight(ok).for_prompt()["forecast"]["nextMonth"]["predictedValue"] == 40.0
    score = {**offboarding_metric(), "unit": "points"}  # the program cannot know that this unit is never negative
    assert as_insight(score).for_prompt()["forecast"]["nextMonth"]["predictedValue"] == -4.77


def test_numbers_are_rounded_to_two_decimals_for_the_model_and_whole_numbers_stay():
    data = as_insight().for_prompt()
    assert data["companyValue"] == 44.28 and data["dataQuality"]["checks"][0]["failedPct"] == 1.51
    assert data["dataQuality"]["recordsAnalysed"] == 1129 and data["dataQuality"]["checks"][0]["failedRecords"] == 17
    assert round_floats({"a": 1.005, "b": 2, "c": "3.14159", "d": [0.12345, True]}) == {"a": 1.0, "b": 2, "c": "3.14159", "d": [0.12, True]}


def test_a_summary_prompt_has_no_root_cause_factors_and_no_accuracy_of_the_model_behind_them():
    m = as_insight()
    summary = m.for_prompt(summary=True)
    assert "rca" not in summary and "modelAccuracy" not in summary
    full = m.for_prompt()
    assert "rca" in full and "modelAccuracy" not in full
    text = build_user_prompt("OFB2", RUN_DATE, m, [], summary=True)
    assert text.startswith("Write the summary for the metric below.") and "num__noticeServedDays" not in text and '"rca"' not in text


# ───────────────────────── the summary itself ─────────────────────────


def test_the_summary_is_one_or_two_paragraphs_of_50_to_200_words():
    assert len(parse_summary(json.dumps({"summary": [P1]})).summary) == 1
    assert len(parse_summary(SUMMARY).summary) == 2
    with pytest.raises(ReportError, match="summary"):
        parse_summary(json.dumps({"summary": []}))
    with pytest.raises(ReportError, match="summary"):
        parse_summary(json.dumps({"summary": [P1, P2, P1]}))
    exactly = lambda n: " ".join(["word"] * n)
    assert parse_summary(json.dumps({"summary": [exactly(50), exactly(200)]})).summary
    with pytest.raises(ReportError, match="a paragraph has 49 words, the minimum is 50"):
        parse_summary(json.dumps({"summary": [exactly(49)]}))
    with pytest.raises(ReportError, match="a paragraph has 201 words, the limit is 200"):
        parse_summary(json.dumps({"summary": [exactly(201)]}))
    assert all(50 <= len(paragraph.split()) <= 200 for paragraph in (P1, P2))  # the paragraphs used in these tests are full paragraphs


def test_the_healthy_report_has_the_summary_under_the_module_overview():
    report = build_healthy_report(SUMMARY, as_insight())
    assert report == {"metricName": "Offboarding Cycle Time", "healthState": "healthy", "moduleOverview": {"summary": [P1, P2]}}


def test_paragraphs_start_with_a_capital_letter():
    lower = json.dumps({"summary": [P1[0].lower() + P1[1:]]})
    assert build_healthy_report(lower, as_insight())["moduleOverview"]["summary"][0] == P1


@pytest.mark.parametrize(
    "bad",
    [
        "The metric has the lowest cycle time in the whole period that the data covers, which is good news for the offboarding process overall here.",
        "According to the JSON the metric is healthy and the company value of 44.28 days lies within the industry standard range of 30 to 60 days.",
    ],
)
def test_the_summary_gets_the_same_wording_checks_as_a_diagnosis(bad):
    with pytest.raises(ReportError, match="internal wording|rank items"):
        build_healthy_report(json.dumps({"summary": [bad + " " + FILLER]}), as_insight())


def test_copied_names_in_a_summary_are_replaced_by_plain_words_not_rejected():
    copied = "The offboardingCompletionDate field is empty for 17 of the 1129 records, and the PotentiallyStaleOrIncomplete check found 17 records. " + FILLER + " " + FILLER
    out = build_healthy_report(json.dumps({"summary": [copied]}), as_insight())["moduleOverview"]["summary"][0]
    assert "offboardingCompletionDate" not in out and "PotentiallyStaleOrIncomplete" not in out
    assert "offboarding completion date" in out


def test_the_readable_metric_name_and_plain_field_names_are_fine():
    ok = "Offboarding Cycle Time is healthy at 44.28 days, and the offboarding completion date field is empty for 17 of 1129 records, which is 1.51%. " + FILLER
    assert build_healthy_report(json.dumps({"summary": [ok]}), as_insight())["moduleOverview"]["summary"] == [ok]


# ───────────────────────── in the pipeline ─────────────────────────


def healthy_rows(*extra):
    return [rec("OFB2", "OffboardingCycleTime", {**offboarding_metric(), "module": "OFB2"}), *extra]


async def test_a_healthy_metric_gets_a_summary_written_from_the_healthy_prompt():
    store, llm = MemStore(healthy_rows()), SpyLlm()
    summary = await Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=HEALTHY_PROMPT).run(RUN_DATE)
    assert (summary.generated, summary.skipped_healthy, summary.failed) == (1, 0, 0)
    assert llm.system_prompts == [HEALTHY_PROMPT.text] and llm.last_user_prompt.startswith("Write the summary")
    saved = store.reports[(RUN_DATE, "OFB2", "OffboardingCycleTime")]
    assert saved.status == "succeeded" and saved.prompt_sha == "h1"
    assert saved.report == {"metricName": "Offboarding Cycle Time", "healthState": "healthy", "moduleOverview": {"summary": [P1, P2]}}


async def test_without_the_healthy_prompt_healthy_metrics_are_still_skipped():
    store, llm = MemStore(healthy_rows()), SpyLlm()
    summary = await Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT).run(RUN_DATE)
    assert (summary.skipped_healthy, summary.generated, llm.calls) == (1, 0, 0) and store.reports == {}


async def test_every_state_gets_the_right_treatment_in_one_run():
    rows = healthy_rows(
        rec("RCM", "TimeToHire", insight("TimeToHire", "critical")),
        rec("EC", "Settlement", {**offboarding_metric(), "metricName": "Settlement", "healthState": "Unknown", "companyValue": None, "module": "EC"}),
    )
    store, llm = MemStore(rows), SpyLlm()
    summary = await Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=HEALTHY_PROMPT).run(RUN_DATE)
    assert (summary.generated, summary.skipped_no_data, summary.failed) == (2, 1, 0)
    assert sorted(llm.system_prompts) == sorted([HEALTHY_PROMPT.text, BREACH_PROMPT.text])
    assert store.reports[(RUN_DATE, "RCM", "TimeToHire")].prompt_sha == "b1" and "plan" in store.reports[(RUN_DATE, "RCM", "TimeToHire")].report


async def test_a_summary_is_cached_and_a_new_healthy_prompt_regenerates_only_the_summaries():
    rows = healthy_rows(rec("RCM", "TimeToHire", insight("TimeToHire", "critical")))
    store, llm = MemStore(rows), SpyLlm()
    first = Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=HEALTHY_PROMPT)
    await first.run(RUN_DATE)
    assert (await first.run(RUN_DATE)).skipped_cached == 2 and llm.calls == 2
    second = Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=Prompt(HEALTHY_PROMPT.text, "h2"))
    again = await second.run(RUN_DATE)
    assert (again.generated, again.skipped_cached) == (1, 1) and llm.calls == 3


async def test_a_summary_the_checks_reject_is_recorded_as_failed_with_the_healthy_prompt_version():
    store, llm = MemStore(healthy_rows()), SpyLlm(summary_text=json.dumps({"summary": ["Too short."]}))
    summary = await Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=HEALTHY_PROMPT).run(RUN_DATE)
    assert summary.failed == 1
    failed = store.reports[(RUN_DATE, "OFB2", "OffboardingCycleTime")]
    assert failed.status == "failed" and failed.prompt_sha == "h1" and "minimum is 50" in failed.error


async def test_a_diagnosis_still_keeps_the_exact_numbers_in_the_stored_factors_while_the_model_sees_them_rounded():
    long = {**insight("TimeToHire", "critical"), "module": "RCM"}
    long["rca"]["factors"][0]["impactPct"] = 54.4123456789
    store, llm = MemStore([rec("RCM", "TimeToHire", long)]), SpyLlm()
    await Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=HEALTHY_PROMPT).run(RUN_DATE)
    assert "54.41" in llm.last_user_prompt and "54.4123456789" not in llm.last_user_prompt
    assert store.reports[(RUN_DATE, "RCM", "TimeToHire")].report["factors"][0]["impactPct"] == 54.4123456789


# ───────────────────────── the switch ─────────────────────────


def test_healthy_summaries_are_on_by_default_and_can_be_switched_off():
    assert Settings(_env_file=None).healthy_summaries is True
    assert Settings(_env_file=None, healthy_summaries="false").healthy_summaries is False


@pytest.mark.parametrize("value,expect_prompt", [(None, True), ("false", False)])
def test_the_cli_gives_the_orchestrator_the_healthy_prompt_unless_switched_off(monkeypatch, tmp_path, value, expect_prompt):
    seen = {}

    class SpyOrchestrator:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        async def run(self, *a, **k):
            return SimpleNamespace(failed=0, total_insights=1)

    monkeypatch.setattr(pipeline, "Orchestrator", SpyOrchestrator)
    monkeypatch.setattr(pipeline, "build_store", lambda *a, **k: MemStore([]))
    monkeypatch.chdir(tmp_path)
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "LLM_CHAIN", "HEALTHY_SUMMARIES"):
        monkeypatch.delenv(name, raising=False)
    for k, v in {"SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "service-role-key-0123456789", "INSIGHTS_TABLE": "ML_Notebook_Insights", "REPORTS_TABLE": "LLM_Reports"}.items():
        monkeypatch.setenv(k, v)
    if value:
        monkeypatch.setenv("HEALTHY_SUMMARIES", value)
    assert pipeline.orchestrate(["--run-date", RUN_DATE, "--dry-run"]) == 0
    assert (seen["healthy_prompt"] is not None) is expect_prompt
    if expect_prompt:
        assert seen["healthy_prompt"].sha == load_healthy_prompt().sha != load_system_prompt().sha


# ───────────────────────── metrics that could not be calculated get a plan ─────────────────────────


SETUP_PROMPT = Prompt("setup prompt", "s1")


def month_row(period, m, average, partial=False):
    return {"period": period, "month": m, "average": average, "isPartial": partial}


def quarter(period, q, average, months, partial=False):
    return {"period": period, "quarter": q, "average": average, "isPartial": partial, "children": {"granularity": "monthly", "periods": months}}


DATA_QUALITY = {
    "overallRating": "poor", "dataPeriod": {"from": "2012-07-09", "to": "2026-10-11"}, "recordsAnalysed": 22474,
    "checks": [
        {"checkName": "MissingValues", "category": "Completeness", "failedRecords": 4487, "failedPct": 100.0,
         "affectedColumns": ["middleName", "nationality", "emailAddress", "auditStatus"], "affectedCells": 25129},
        {"checkName": "InvalidValues", "category": "Validity", "checkedRecords": 4487, "failedRecords": 0, "failedPct": 0.0, "affectedColumns": None},
        {"checkName": "DuplicateRecords", "category": "Uniqueness", "checkedRecords": 4487, "failedRecords": 0, "failedPct": 0.0, "affectedColumns": None},
        {"checkName": "Staleness", "category": "Staleness", "checkedRecords": 4487, "failedRecords": 3193, "failedPct": 71.16,
         "affectedColumns": ["originalStartDate", "lastAuditDate"], "staleRange": "> 3 years old"},
    ],
}


def sample_a() -> dict:
    """Healthy. Note the notebook marks the months of 2024 as partial, but not the quarters and the year above them."""
    return {
        "generatedAt": "2026-10-06T09:42:14.602167Z", "module": "RCM", "reportVersion": "2.2", "metricName": "SourceOfHireEffectiveness",
        "unit": "percent", "higherIsBetter": False, "companyValue": 3.45, "industryStandardValue": 20.0, "healthState": "healthy",
        "variance": {"value": -16.54, "percentage": -82.72},
        "trendAnalysis": {"direction": "down", "granularity": "yearly", "periods": [
            {"period": "2024", "year": 2024, "average": 47.73, "isPartial": False, "children": {"granularity": "quarterly", "periods": [
                quarter("2024-Q1", 1, None, [month_row("2024-01", 1, None, True), month_row("2024-02", 2, None, True), month_row("2024-03", 3, None, True)], True),
                quarter("2024-Q2", 2, None, [month_row("2024-04", 4, None, True), month_row("2024-05", 5, None, True), month_row("2024-06", 6, None, True)], True),
                quarter("2024-Q3", 3, None, [month_row("2024-07", 7, None, True), month_row("2024-08", 8, None, True), month_row("2024-09", 9, None, True)], True),
                quarter("2024-Q4", 4, 47.73, [month_row("2024-10", 10, None, True), month_row("2024-11", 11, 75.0), month_row("2024-12", 12, 20.46)])]}},
            {"period": "2025", "year": 2025, "average": 4.45, "isPartial": False, "children": {"granularity": "quarterly", "periods": [
                quarter("2025-Q1", 1, 7.02, [month_row("2025-01", 1, 8.58), month_row("2025-02", 2, 9.38), month_row("2025-03", 3, 3.09)]),
                quarter("2025-Q2", 2, 4.36, [month_row("2025-04", 4, 4.81), month_row("2025-05", 5, 4.87), month_row("2025-06", 6, 3.41)]),
                quarter("2025-Q3", 3, 3.73, [month_row("2025-07", 7, 3.44), month_row("2025-08", 8, 3.29), month_row("2025-09", 9, 4.45)]),
                quarter("2025-Q4", 4, 2.71, [month_row("2025-10", 10, 1.52), month_row("2025-11", 11, 2.83), month_row("2025-12", 12, 3.78)])]}},
            {"period": "2026", "year": 2026, "average": 3.14, "isPartial": True, "children": {"granularity": "quarterly", "periods": [
                quarter("2026-Q1", 1, 3.36, [month_row("2026-01", 1, 3.45), month_row("2026-02", 2, 3.46), month_row("2026-03", 3, 3.16)]),
                quarter("2026-Q2", 2, 4.60, [month_row("2026-04", 4, 3.85), month_row("2026-05", 5, 4.47), month_row("2026-06", 6, 5.49)]),
                quarter("2026-Q3", 3, 1.48, [month_row("2026-07", 7, 2.96), month_row("2026-08", 8, 0.92), month_row("2026-09", 9, 0.55)]),
                quarter("2026-Q4", 4, None, [month_row("2026-10", 10, None, True), month_row("2026-11", 11, None, True), month_row("2026-12", 12, None, True)], True)]}}]},
        "forecast": {
            "nextMonth": {"period": "2026-10", "predictedValue": -0.12, "lowerBound": 0.0, "upperBound": 14.87, "predictedHealthState": "healthy"},
            "nextQuarter": {"period": "2026-12", "predictedValue": -1.10, "lowerBound": 0.0, "upperBound": 13.89, "predictedHealthState": "healthy"},
            "nextYear": {"period": "2027-09", "predictedValue": -2.60, "lowerBound": 0.0, "upperBound": 12.39, "predictedHealthState": "healthy"}},
        "rca": {"applicable": True, "breachValue": 0.0, "factors": [
            {"rank": 1, "factorName": "screeningDate__month", "avgFactorValue": None, "impactValue": 0.12, "impactPct": 39.47},
            {"rank": 2, "factorName": "noOfPositionsFilled", "avgFactorValue": None, "impactValue": 0.05, "impactPct": 19.41},
            {"rank": 3, "factorName": "appExpCtc", "avgFactorValue": None, "impactValue": 0.05, "impactPct": 16.42}]},
        "dataQuality": copy.deepcopy(DATA_QUALITY),
        "selectedTrainingModel": {
            "rcaModel": {"modelName": "Logistic Regression", "r2": 0.17, "mae": 6.39, "rmse": 16.32, "rating": "poor"},
            "forecastModel": {"modelName": "DampedTrend", "r2": None, "mae": 3.88, "rmse": 7.65, "rating": "fair"}},
        "missingConfigurations": {"mandatoryFieldsMissing": [], "otherFieldsMissing": []},
    }


def sample_b(mandatory=(), other=()) -> dict:
    """Mandatory fields missing: the metric could not be calculated. (The notebooks' sample lists no field; real files do.)"""
    return {
        "generatedAt": "2026-10-06T09:42:14.602167Z", "module": "RCM", "reportVersion": "2.2", "metricName": "SourceOfHireEffectiveness",
        "unit": "percent", "higherIsBetter": None, "companyValue": None, "industryStandardValue": None, "healthState": None,
        "variance": {"value": None, "percentage": None}, "trendAnalysis": None,
        "forecast": {"applicable": False, "status": "Data Missing", "message": "Forecast was not performed because essential metric data is incomplete."},
        "rca": {"applicable": False, "status": "Data Missing", "message": "RCA was not performed because essential metric data is incomplete.", "breachValue": None, "factors": []},
        "dataQuality": copy.deepcopy(DATA_QUALITY),
        "selectedTrainingModel": {"rcaModel": {"status": "Data Missing", "trainingPerformed": False}, "forecastModel": {"status": "Data Missing", "trainingPerformed": False}},
        "missingConfigurations": {"mandatoryFieldsMissing": list(mandatory), "otherFieldsMissing": list(other)},
    }


FIELDS = ["screeningDate", "noOfPositionsFilled"]


def b_with_fields() -> dict:
    return sample_b(mandatory=FIELDS, other=["appExpCtc"])


def parsed(payload: dict) -> MetricInsight:
    return MetricInsight.model_validate(payload)


# ───────────────────────── the healthy sample ─────────────────────────


def test_the_healthy_sample_is_accepted_and_none_of_its_fields_is_called_unused():
    m = parsed(sample_a())
    assert m.health_state == "healthy" and m.report_version == "2.2" and ignored_fields(sample_a()) == []


def test_the_notebooks_new_name_for_model_accuracy_is_read_but_never_sent_to_the_model():
    m = parsed(sample_a())
    assert "selectedTrainingModel" not in m.for_prompt() and "modelAccuracy" not in m.for_prompt()
    assert "modelAccuracy" in m.model_dump(by_alias=True) and "selectedTrainingModel" not in m.model_dump(by_alias=True)
    old = {k: v for k, v in sample_a().items() if k != "selectedTrainingModel"} | {"modelAccuracy": sample_a()["selectedTrainingModel"]}
    assert parsed(old).model_accuracy == m.model_accuracy  # older files keep working


@pytest.mark.parametrize("kwargs", [{}, {"summary": True}, {"setup": True}])
def test_the_format_version_is_never_sent_to_the_model(kwargs):
    assert "reportVersion" not in parsed(sample_a()).for_prompt(**kwargs)


def test_periods_with_an_empty_month_are_not_compared_even_though_the_notebook_did_not_flag_them():
    trend = parsed(sample_a()).for_prompt(summary=True)["trendAnalysis"]
    flagged = lambda level: {e["period"] for e in trend[level] if e.get("partial")}
    assert flagged("yearly") == {"2024", "2026"} and flagged("quarterly") == {"2024-Q4"}
    assert [(p["earlierPeriod"], p["laterPeriod"]) for p in trend["equalPeriodComparisons"]] == [
        ("2025-Q1", "2026-Q1"), ("2025-Q2", "2026-Q2"), ("2025-Q3", "2026-Q3"),
    ]  # not 2024 against 2025, which would set two months against twelve


def test_a_forecast_of_negative_percent_is_not_usable():
    assert parsed(sample_a()).for_prompt()["forecast"] == {"notUsable": FORECAST_NOT_USABLE}


# ───────────────────────── the sample with mandatory fields missing ─────────────────────────


def test_a_metric_that_could_not_be_calculated_is_accepted_and_its_null_health_state_means_unknown():
    m = parsed(sample_b())
    assert m.health_state == "unknown" and m.company_value is None and m.trend_analysis.direction is None and ignored_fields(sample_b()) == []


def test_the_health_state_key_itself_is_still_required():
    payload = sample_b()
    del payload["healthState"]
    with pytest.raises(ValueError, match="healthState"):
        parsed(payload)


@pytest.mark.parametrize("block", ["trendAnalysis", "variance", "rca", "missingConfigurations"])
def test_a_block_the_notebook_writes_as_null_is_simply_no_block(block):
    assert parsed({**sample_b(), block: None}).health_state == "unknown"


def test_a_forecast_that_was_not_performed_gives_the_notebooks_own_message():
    assert parsed(sample_b()).for_prompt()["forecast"] == {"notUsable": "Forecast was not performed because essential metric data is incomplete."}


@pytest.mark.parametrize(
    "missing,expected",
    [
        ({"mandatoryFieldsMissing": ["a", "b"], "otherFieldsMissing": ["c"]}, ["a", "b"]),
        ({"mandatory": ["a"], "other": ["c"]}, ["a"]),  # the earlier names
        ({"otherFieldsMissing": ["c"]}, []),
        ({"mandatoryFieldsMissing": [], "otherFieldsMissing": []}, []),
        (["a", "b"], []),  # a plain list does not say which fields are mandatory
        ([], []),
    ],
)
def test_the_mandatory_fields_are_those_in_a_group_whose_name_says_so(missing, expected):
    assert parsed({**sample_b(), "missingConfigurations": missing}).mandatory_missing_fields() == expected


# ───────────────────────── what the model is given for the plan ─────────────────────────


def test_for_the_plan_the_model_is_given_only_the_metric_the_missing_fields_and_the_data_checks():
    data = parsed(b_with_fields()).for_prompt(setup=True)
    assert sorted(data) == ["dataQuality", "healthState", "metricName", "missingConfigurations", "unit"]
    assert data["missingConfigurations"] == {"mandatoryFieldsMissing": FIELDS, "otherFieldsMissing": ["appExpCtc"]}
    assert data["healthState"] == "unknown" and data["dataQuality"]["checks"][1]["staleRange"] == "> 3 years old"
    assert "higherIsBetter" in parsed({**b_with_fields(), "higherIsBetter": True}).for_prompt(setup=True)


def test_the_request_for_the_plan_has_its_own_instruction_and_no_analysis_blocks():
    text = build_user_prompt("RCM", RUN_DATE, parsed(b_with_fields()), [], setup=True)
    assert text.startswith("Write the data-readiness plan for the metric below.") and "screeningDate" in text
    for block in ('"rca"', '"forecast"', '"trendAnalysis"', '"modelAccuracy"', '"variance"'):
        assert block not in text


# ───────────────────────── in the pipeline ─────────────────────────


def setup_draft() -> dict:
    return {
        "diagnosis": {
            "headline": "The metric could not be calculated because mandatory fields are missing",
            "narrative": [
                "The screening date and the number of positions filled fields are missing.",
                "The value, health state, trend, forecast and root cause could not be calculated.",
                "The plan sets the fields up and then runs the analysis again.",
            ],
        },
        "businessImpact": {
            "overview": "The value, health state, trend, forecast and root cause are not available.",
            "financialImpact": [
                "The financial impact cannot be quantified from the available data.",
                "Collecting the missing data by hand may take staff effort.",
                "Decisions that need the metric could wait until it is available.",
            ],
            "slaAndTurnaround": "The turnaround cannot be assessed until the metric can be calculated from the two missing fields.",
            "governanceAndAudit": "One check found records with empty fields, and one check found stale records.",
        },
        "workstreams": [
            {"id": "W1", "kind": "data", "step": "Set up the screening date field", "fixesFactors": []},
            {"id": "W2", "kind": "data", "step": "Set up the number of positions filled field", "fixesFactors": []},
            {"id": "W3", "kind": "data", "step": "Run the analysis again and confirm the metric is calculated", "fixesFactors": []},
        ],
        "activities": [
            {"phase": "architecture", "activity": "Confirm the meaning and the source of each field", "role": "processOwner", "workstream": None, "week": 1, "hours": 6},
            {"phase": "configuration", "activity": "Set up the screening date field", "role": "consultant", "workstream": "W1", "week": 2, "hours": 8},
            {"phase": "configuration", "activity": "Set up the number of positions filled field", "role": "consultant", "workstream": "W2", "week": 2, "hours": 8},
            {"phase": "configuration", "activity": "Staging environment test", "role": "qaUat", "workstream": None, "week": 3, "hours": 6},
            {"phase": "rollout", "activity": "Run the analysis again and confirm the metric", "role": "consultant", "workstream": "W3", "week": 4, "hours": 4},
        ],
        "assumptionsAndRisks": [
            {"type": "Risk", "description": "The metric stays unavailable until its mandatory fields are filled.", "mitigation": "Set up the mandatory fields first, then run the analysis again."},
            {"type": "Assumption", "description": "The values of both fields can be captured for the existing records.", "mitigation": "Confirm the source of each field in the first week."},
        ],
    }


class Llm(FakeLlm):
    """Answers each kind of prompt with the right kind of answer, and remembers which prompts it was given."""

    def __init__(self, setup_text: str | None = None):
        super().__init__()
        self.setup_text, self.diagnosis_text, self.system_prompts = setup_text or json.dumps(setup_draft()), self.draft_text, []

    async def generate(self, system_prompt, user_prompt, parse, *, run_key=""):
        self.system_prompts.append(system_prompt)
        self.draft_text = {SETUP_PROMPT.text: self.setup_text, HEALTHY_PROMPT.text: SUMMARY}.get(system_prompt, self.diagnosis_text)
        return await super().generate(system_prompt, user_prompt, parse, run_key=run_key)


def orchestrator(store, llm, setup=True):
    return Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=HEALTHY_PROMPT, setup_prompt=SETUP_PROMPT if setup else None)


KEY = ("2026-09-29", "RCM", "SourceOfHireEffectiveness")


async def test_a_metric_missing_mandatory_fields_gets_a_plan_to_set_them_up():
    store, llm = MemStore([rec("RCM", "SourceOfHireEffectiveness", b_with_fields())]), Llm()
    summary = await orchestrator(store, llm).run(RUN_DATE)
    assert (summary.generated, summary.skipped_no_data, summary.failed) == (1, 0, 0)
    assert llm.system_prompts == [SETUP_PROMPT.text] and llm.last_user_prompt.startswith("Write the data-readiness plan")
    saved = store.reports[KEY]
    assert saved.status == "succeeded" and saved.prompt_sha == "s1"
    report = saved.report
    assert report["healthState"] == "unknown" and report["factors"] == []
    assert [w["kind"] for w in report["workstreams"]] == ["data", "data", "data"] and all(w["fixesFactors"] == [] for w in report["workstreams"])
    assert report["plan"]["totalHours"] == 32 and report["plan"]["durationWeeks"] == 4
    assert isinstance(report["diagnosis"]["narrative"], list)


async def test_without_the_setup_prompt_such_a_metric_is_skipped_as_before():
    store, llm = MemStore([rec("RCM", "SourceOfHireEffectiveness", b_with_fields())]), Llm()
    summary = await orchestrator(store, llm, setup=False).run(RUN_DATE)
    assert (summary.skipped_no_data, summary.generated, llm.calls) == (1, 0, 0) and store.reports == {}


async def test_when_no_mandatory_field_is_named_there_is_nothing_to_set_up(caplog):
    """The notebooks' own sample lists no field: without names a plan would be vague, so nothing is written."""
    store, llm = MemStore([rec("RCM", "SourceOfHireEffectiveness", sample_b())]), Llm()
    with caplog.at_level(logging.INFO):
        summary = await orchestrator(store, llm).run(RUN_DATE)
    assert (summary.skipped_no_data, summary.generated, llm.calls) == (1, 0, 0)
    assert "RCM/SourceOfHireEffectiveness: health state is unknown" in caplog.text


async def test_a_plain_list_of_missing_fields_does_not_say_which_are_mandatory():
    payload = {**sample_b(), "missingConfigurations": ["screeningDate", "noOfPositionsFilled"]}
    store, llm = MemStore([rec("RCM", "SourceOfHireEffectiveness", payload)]), Llm()
    assert (await orchestrator(store, llm).run(RUN_DATE)).skipped_no_data == 1 and llm.calls == 0


async def test_the_plan_is_cached_and_written_again_when_the_fields_or_the_prompt_change():
    rows = [rec("RCM", "SourceOfHireEffectiveness", b_with_fields())]
    store, llm = MemStore(rows), Llm()
    first = orchestrator(store, llm)
    await first.run(RUN_DATE)
    assert (await first.run(RUN_DATE)).skipped_cached == 1 and llm.calls == 1
    rows[0] = rec("RCM", "SourceOfHireEffectiveness", sample_b(mandatory=FIELDS + ["sourceName"], other=["appExpCtc"]))
    assert (await first.run(RUN_DATE)).generated == 1 and llm.calls == 2  # one more field to set up
    again = Orchestrator(store=store, llm=llm, prompt=BREACH_PROMPT, healthy_prompt=HEALTHY_PROMPT, setup_prompt=Prompt(SETUP_PROMPT.text, "s2"))
    assert (await again.run(RUN_DATE)).generated == 1 and llm.calls == 3


async def test_a_plan_that_mentions_the_json_is_sent_back_and_a_failure_keeps_the_setup_prompt_version():
    draft = setup_draft()
    draft["diagnosis"]["narrative"][0] = "The JSON shows that the screening date and the number of positions filled fields are missing."
    store, llm = MemStore([rec("RCM", "SourceOfHireEffectiveness", b_with_fields())]), Llm(setup_text=json.dumps(draft))
    summary = await orchestrator(store, llm).run(RUN_DATE)
    failed = store.reports[KEY]
    assert summary.failed == 1 and failed.status == "failed" and failed.prompt_sha == "s1" and "internal wording" in failed.error


async def test_every_kind_of_metric_gets_the_right_treatment_in_one_run():
    rows = [
        rec("RCM", "SourceOfHireEffectiveness", b_with_fields()),
        rec("RCM", "TimeToHire", insight("TimeToHire", "critical")),
        rec("RCM", "OfferAcceptance", insight("OfferAcceptance", "healthy")),
        rec("RCM", "NothingListed", {**sample_b(), "metricName": "NothingListed"}),
    ]
    store, llm = MemStore(rows), Llm()
    summary = await orchestrator(store, llm).run(RUN_DATE)
    assert (summary.generated, summary.skipped_no_data, summary.failed) == (3, 1, 0)
    assert sorted(llm.system_prompts) == sorted([SETUP_PROMPT.text, HEALTHY_PROMPT.text, BREACH_PROMPT.text])


# ───────────────────────── the switch ─────────────────────────


def test_setup_plans_are_on_by_default_and_can_be_switched_off():
    assert Settings(_env_file=None).setup_reports is True
    assert Settings(_env_file=None, setup_reports="false").setup_reports is False


@pytest.mark.parametrize("value,expect_prompt", [(None, True), ("false", False)])
def test_the_cli_gives_the_orchestrator_the_setup_prompt_unless_switched_off(monkeypatch, tmp_path, value, expect_prompt):
    seen = {}

    class SpyOrchestrator:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        async def run(self, *a, **k):
            return SimpleNamespace(failed=0, total_insights=1)

    monkeypatch.setattr(pipeline, "Orchestrator", SpyOrchestrator)
    monkeypatch.setattr(pipeline, "build_store", lambda *a, **k: MemStore([]))
    monkeypatch.chdir(tmp_path)
    for k, v in {"SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "service-role-key-0123456789", "INSIGHTS_TABLE": "ML_Notebook_Insights", "REPORTS_TABLE": "LLM_Reports"}.items():
        monkeypatch.setenv(k, v)
    if value:
        monkeypatch.setenv("SETUP_REPORTS", value)
    assert pipeline.orchestrate(["--run-date", RUN_DATE, "--dry-run"]) == 0
    assert (seen["setup_prompt"] is not None) is expect_prompt
    if expect_prompt:
        assert seen["setup_prompt"].sha == load_setup_prompt().sha


# ───────────────────────── the prompts ─────────────────────────


# ───────────────────────── a smaller prompt, the same report ─────────────────────────


def test_checks_that_found_nothing_stay_out_of_a_breach_or_setup_prompt_but_stay_in_a_healthy_summary():
    m = parsed(b_with_fields())
    names = lambda d: [c["checkName"] for c in d["dataQuality"]["checks"]]  # noqa: E731
    assert names(m.for_prompt(setup=True)) == ["MissingValues", "Staleness"]
    assert names(m.for_prompt()) == ["MissingValues", "Staleness"]
    assert names(m.for_prompt(summary=True)) == ["MissingValues", "InvalidValues", "DuplicateRecords", "Staleness"]


def test_empty_values_inside_the_data_checks_are_left_out():
    checks = parsed(b_with_fields()).for_prompt(summary=True)["dataQuality"]["checks"]
    assert all(v is not None for c in checks for v in c.values()) and "affectedColumns" not in checks[1]


def test_old_quarters_and_months_are_left_out_but_the_comparisons_use_the_whole_history():
    from sf_orchestrator.schemas import TrendAnalysis, _equal_period_comparisons

    quarters = [{"period": f"{y}-Q{n}", "average": 10 + y - 2020 + n} for y in range(2020, 2026) for n in range(1, 5)]
    full = _equal_period_comparisons({"quarterly": quarters, "yearly": []})
    assert len(full) == 20  # 24 quarters give 20 pairs one year apart
    ta = TrendAnalysis.model_validate({"direction": "up", "granularity": "yearly", "periods": [
        {"period": str(y), "average": 10.0 + y - 2020, "isPartial": False, "children": {"granularity": "quarterly", "periods": [
            {"period": f"{y}-Q{n}", "average": 10.0 + y - 2020 + n, "isPartial": False, "children": {"granularity": "monthly", "periods": [
                {"period": f"{y}-{m:02d}", "average": 5.0 + m, "isPartial": False} for m in range(3 * n - 2, 3 * n + 1)]}}
            for n in range(1, 5)]}} for y in range(2020, 2026)]})
    out = ta.compact()
    assert len(out["yearly"]) == 6 and len(out["quarterly"]) == 8 and len(out["monthly"]) == 12
    assert out["quarterly"][-1]["period"] == "2025-Q4" and out["monthly"][-1]["period"] == "2025-12"
    assert len(out["equalPeriodComparisons"]) == 5 + 20  # all yearly and quarterly pairs, whatever the window


# ───────────────────────── metric names and standards written as text ─────────────────────────


READABLE = "Full & Final Settlement Timeliness"


# what the notebook writes when the data needed to calculate a metric is missing
NO_DATA = {
    "metricName": READABLE,
    "unit": "days",
    "higherIsBetter": False,
    "companyValue": None,
    "industryStandardValue": "Against statutory/company SLA",
    "healthState": "Unknown",
    "variance": {"value": None, "percentage": None},
    "trendAnalysis": {"direction": "flat", "granularity": "yearly", "periods": []},
    "forecast": {"nextMonth": None, "nextQuarter": None, "nextYear": None},
    "rca": {"applicable": False, "breachValue": None, "factors": []},
    "dataQuality": {
        "overallRating": "poor",
        "dataPeriod": {"from": None, "to": None},
        "recordsAnalysed": 0,
        "checks": [
            {"checkName": "MandatoryFieldsMissing", "category": "Completeness", "checkedRecords": 0, "failedRecords": 1146,
             "failedPct": None, "affectedColumns": ["settlementDisbursementDate"], "staleRange": None},
            {"checkName": "InvalidValues", "category": "Validity", "checkedRecords": 0, "failedRecords": 0,
             "failedPct": None, "affectedColumns": None, "staleRange": None},
        ],
    },
    "modelAccuracy": {"rcaModel": {}, "forecastModel": {"modelName": "Not available", "r2": None, "mae": None, "rmse": None, "rating": "not_assessed"}},
    "missingConfigurations": ["settlementDisbursementDate"],
}


def no_data() -> dict:
    return {**insight("Placeholder", "healthy"), **NO_DATA, "module": "OFB2"}


# ───────────────────────── a metric that could not be calculated ─────────────────────────


def test_the_no_data_file_is_accepted():
    m = MetricInsight.model_validate(no_data())
    assert m.health_state == "unknown" and m.company_value is None and m.variance.value is None
    assert m.industry_standard_value == "Against statutory/company SLA"
    assert m.trend_analysis.direction == "stable" and m.forecast.next_month is None  # "flat" is read as "stable"


async def test_an_unknown_metric_gets_no_model_call_and_no_report(caplog):
    store, llm = MemStore([rec("OFB2", metric_key(READABLE), no_data())]), FakeLlm()
    with caplog.at_level(logging.INFO):
        summary = await Orchestrator(store=store, llm=llm, prompt=PROMPT).run(RUN_DATE)
    assert (summary.total_insights, summary.skipped_no_data, summary.generated, summary.failed) == (1, 1, 0, 0)
    assert llm.calls == 0 and store.reports == {}
    assert "OFB2/FullAndFinalSettlementTimeliness: health state is unknown" in caplog.text


async def test_a_mixed_run_handles_every_case_and_one_bad_file_does_not_stop_the_others():
    rows = [
        rec("RCM", "TimeToHire", insight("TimeToHire", "critical")),
        rec("RCM", "OfferAcceptance", insight("OfferAcceptance", "healthy")),
        rec("OFB2", metric_key(READABLE), no_data()),
        rec("EC", "Broken", {"metricName": "Broken"}),
    ]
    store, llm = MemStore(rows), FakeLlm()
    summary = await Orchestrator(store=store, llm=llm, prompt=PROMPT).run(RUN_DATE)
    assert (summary.generated, summary.skipped_healthy, summary.skipped_no_data, summary.failed) == (1, 1, 1, 1)
    assert llm.calls == 1  # only the breached metric reaches a model


async def test_a_run_where_everything_is_skipped_is_not_a_failure():
    store = MemStore([rec("OFB2", metric_key(READABLE), no_data()), rec("RCM", "OfferAcceptance", insight("OfferAcceptance", "healthy"))])
    summary = await Orchestrator(store=store, llm=FakeLlm(), prompt=PROMPT).run(RUN_DATE)
    assert summary.failed == 0 and summary.total_insights == 2


# ───────────────────────── tolerant reading of the notebook's values ─────────────────────────


@pytest.mark.parametrize(
    "written,expected",
    [("Unknown", "unknown"), ("UNKNOWN", "unknown"), (" unknown ", "unknown"), ("At Risk", "at-risk"), ("AT_RISK", "at-risk"), ("Critical", "critical"), ("Healthy", "healthy")],
)
def test_health_state_is_read_whatever_the_capitalisation(written, expected):
    over = {"healthState": written, "companyValue": 25.6}
    assert MetricInsight.model_validate({**insight("TimeToHire", "critical"), **over}).health_state == expected


@pytest.mark.parametrize("written", ["flat", "Flat", "stable"])
def test_flat_is_read_as_stable(written):
    payload_ = insight("TimeToHire", "critical")
    payload_["trendAnalysis"]["direction"] = written
    assert MetricInsight.model_validate(payload_).trend_analysis.direction == "stable"


def test_a_breached_metric_without_a_company_value_is_rejected_with_a_clear_reason():
    with pytest.raises(ValueError, match="companyValue is required when healthState is at-risk or critical"):
        MetricInsight.model_validate({**insight("TimeToHire", "at-risk"), "companyValue": None})


def test_a_standard_written_as_text_reaches_the_model_unchanged_and_numbers_stay_numbers():
    text = MetricInsight.model_validate({**insight("TimeToHire", "critical"), "industryStandardValue": "Against statutory/company SLA"})
    assert text.for_prompt()["industryStandardValue"] == "Against statutory/company SLA"
    number = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    assert number.for_prompt()["industryStandardValue"] == 20 and isinstance(number.industry_standard_value, float)


# ───────────────────────── readable metric names, file-safe report names ─────────────────────────


@pytest.mark.parametrize(
    "name,key",
    [
        ("TimeToHire", "TimeToHire"),
        (READABLE, "FullAndFinalSettlementTimeliness"),
        ("time to hire", "TimeToHire"),
        ("Offer/Acceptance Rate (%)", "OfferAcceptanceRate"),
        ("  Onboarding  Completion Days ", "OnboardingCompletionDays"),
        ("   ", "Metric"),
    ],
)
def test_the_metric_key_is_file_safe_and_leaves_pascal_case_names_alone(name, key):
    assert metric_key(name) == key


async def test_the_report_is_stored_under_the_key_and_keeps_the_readable_name():
    store = MemStore([rec("OFB2", metric_key(READABLE), {**insight(READABLE, "critical"), "module": "OFB2"})])
    summary = await Orchestrator(store=store, llm=FakeLlm(), prompt=PROMPT).run(RUN_DATE)
    saved = store.reports[(RUN_DATE, "OFB2", "FullAndFinalSettlementTimeliness")]
    assert summary.generated == 1 and saved.report["metricName"] == READABLE


# ───────────────────────── the glossary and American spelling ─────────────────────────


PROMPTS = ["system", "healthy", "setup"]


def text_of(name: str) -> str:
    return resources.files("sf_orchestrator").joinpath("prompts", f"{name}.md").read_text(encoding="utf-8")


# ───────── the glossary ─────────


@pytest.mark.parametrize(
    "name,label",
    [
        ("appExpCtc", "applicant expected CTC"),
        ("APP_EXP_CTC", "applicant expected CTC"),  # the same field however the notebook spells it
        ("noOfPositionsFilled", "number of positions filled"),
        ("offerExpCtc", "offer expected CTC"),
        ("hiringMgrEmpId", "hiring manager employee ID"),
        ("applicationId", "application ID"),
        ("EMPLOYEE_ID", "employee ID"),
    ],
)
def test_known_abbreviations_get_their_plain_words(name, label):
    assert label_for(name) == label


@pytest.mark.parametrize("name", ["screeningDate", "ApplicationToInterviewDuration", "DataEngineer", "appDate", "xyzCode", "paidDate"])
def test_a_name_without_a_known_abbreviation_gets_no_label_so_the_model_is_not_given_a_guess(name):
    assert label_for(name) is None


def test_app_alone_is_not_expanded_because_it_could_mean_applicant_or_application():
    assert "app" not in glossary.TOKENS


def test_only_names_that_are_in_the_data_and_known_are_listed():
    data = {"missingConfigurations": {"mandatoryFieldsMissing": ["screeningDate"], "otherFieldsMissing": ["appExpCtc"]}, "note": "Some text"}
    assert glossary_for(data) == {"appExpCtc": "applicant expected CTC", "screeningDate": "screening date"}  # every code-style name is labeled
    assert glossary_for({"metricName": "TimeToHire"}) == {"TimeToHire": "time to hire"}


def test_the_glossary_reaches_the_model_in_its_own_block_after_the_data():
    insight = parsed(b_with_fields())
    prompt = build_user_prompt("RCM", "2026-10-09", insight, [], setup=True)
    block = prompt[prompt.index("<glossary>"):prompt.index("</glossary>")]
    for line in ("MissingValues = missing values", "appExpCtc = applicant expected CTC", "noOfPositionsFilled = number of positions filled", "screeningDate = screening date"):
        assert line in block
    assert prompt.index("</ml_insight>") < prompt.index("<glossary>")


def test_a_metric_with_nothing_to_look_up_has_no_glossary_block():
    prompt = build_user_prompt("RCM", "2026-10-09", parsed(sample_b(mandatory=["screeningDate"])), [], setup=True)
    assert "appExpCtc" not in prompt and "noOfPositionsFilled" not in prompt  # only the data-check name is listed


def test_data_check_names_get_their_words_as_a_label():
    data = {"dataQuality": {"checks": [{"checkName": "MissingValues"}, {"checkName": "DuplicateRecords"}, {"checkName": "Plain"}]}}
    assert glossary_for(data) == {"DuplicateRecords": "duplicate records", "MissingValues": "missing values"}  # a one-word name needs none


def test_the_glossary_also_covers_root_cause_factors_in_a_diagnosis_and_a_summary():
    insight = parsed(sample_a())
    assert "appExpCtc = applicant expected CTC" in build_user_prompt("RCM", "2026-10-09", insight, build_factors(insight), summary=False)
    assert "appExpCtc" not in build_user_prompt("RCM", "2026-10-09", insight, [], summary=True)  # a summary is given no factors


async def test_changing_the_glossary_makes_the_cached_report_stale(monkeypatch):
    store, llm = MemStore([rec("RCM", "SourceOfHireEffectiveness", b_with_fields())]), Llm()
    orch = orchestrator(store, llm)
    await orch.run(RUN_DATE)
    await orch.run(RUN_DATE)
    assert len(llm.system_prompts) == 1  # unchanged input: the saved report is reused
    monkeypatch.setitem(glossary.FIELDS, "appExpCtc", "applicant expected cost to company")
    await orch.run(RUN_DATE)
    assert len(llm.system_prompts) == 2


# ───────── phases of a setup plan ─────────


def plan(setup: bool):
    insight = parsed(b_with_fields())
    return build_report(json.dumps(setup_draft()), insight, [], "RCM", setup=setup)


def test_a_setup_plan_has_its_own_milestones_and_deliverables():
    phases = plan(True)["plan"]["phases"]
    assert [(p["phase"], p["title"], p["milestone"], p["deliverable"]) for p in phases] == [
        ("architecture", "Phase 1: Architecture", "Field Requirements & BRD Sign-Off", "Approved Field Requirements & Setup Specification"),
        ("configuration", "Phase 2: Configuration", "Field Setup & Staging Environment Test", "Configuration & UAT Sign-Off"),
        ("rollout", "Phase 3: Rollout", "Production Cutover & Metric Calculation", "First Calculated Health Report"),
    ]


def test_a_diagnosis_keeps_the_wording_it_always_had():
    phases = plan(False)["plan"]["phases"]
    assert phases[0]["milestone"] == "Root Cause Validation & BRD Sign-Off"
    assert phases[2]["deliverable"] == "Weekly Health Monitoring Report"


def test_both_wordings_use_the_same_three_phases_in_the_same_order():
    assert [p[0] for p in PHASES] == [p[0] for p in PHASES_SETUP] == ["architecture", "configuration", "rollout"]


async def test_the_saved_setup_report_has_the_setup_phases():
    store, llm = MemStore([rec("RCM", "SourceOfHireEffectiveness", b_with_fields())]), Llm()
    await orchestrator(store, llm).run(RUN_DATE)
    saved = store.reports[("2026-09-29", "RCM", "SourceOfHireEffectiveness")].report
    assert saved["plan"]["phases"][2]["milestone"] == "Production Cutover & Metric Calculation"


async def test_a_diagnosis_run_through_the_orchestrator_keeps_the_diagnosis_phases():
    from helpers import insight as make_insight

    store, llm = MemStore([rec("RCM", "TimeToHire", make_insight("TimeToHire", "at-risk"))]), Llm()
    llm.diagnosis_text = llm.draft_text
    await orchestrator(store, llm).run(RUN_DATE)
    saved = store.reports[("2026-09-29", "RCM", "TimeToHire")].report
    assert saved["plan"]["phases"][0]["milestone"] == "Root Cause Validation & BRD Sign-Off"


# ───────── American spelling ─────────

BRITISH = re.compile(
    r"\b(organis\w*|summaris\w*|analys(?:e|ed|ing)|recognis\w*|behaviour\w*|colour\w*|labell\w*|prioritis\w*|minimis\w*|"
    r"standardis\w*|utilis\w*|cancell\w*|programme\w*|normalis\w*|finalis\w*|optimis\w*|favour\w*|centre\w*|licence\w*|"
    r"catalogue\w*|whilst|learnt|judgement|modelling|fulfil|enrol|agree a)\b",
    re.IGNORECASE,
)


def sources():
    root = Path(__file__).resolve().parent.parent
    for folder, pattern in (("src/sf_orchestrator", "*.py"), ("src/sf_orchestrator/prompts", "*.md")):
        yield from sorted((root / folder).glob(pattern))
    yield root / "README.md"


@pytest.mark.parametrize("path", list(sources()), ids=lambda p: p.name)
def test_no_british_spelling_in_the_code_the_prompts_or_the_readme(path):
    found = [m.group(0) for m in BRITISH.finditer(path.read_text(encoding="utf-8"))]
    assert found == []


@pytest.mark.parametrize(
    "name,label",
    [
        ("ktRequiredFlag", "knowledge transfer required flag"),
        ("ktScheduledDate", "knowledge transfer scheduled date"),
        ("ktActualCompletionDate", "knowledge transfer actual completion date"),
        ("ktDocumentAndDeliverablesTracking", "knowledge transfer documents and deliverables tracking"),
        ("ktRecipientSuccessorEmpId", "knowledge transfer recipient (successor) employee ID"),
        ("ktOtherThing", "knowledge transfer other thing"),  # "kt" alone always means knowledge transfer
    ],
)
def test_kt_means_knowledge_transfer(name, label):
    assert label_for(name) == label
