"""The input contract (the notebooks' insight JSON) and the model's answer contract, what the model is told about the trend and the
forecast, and how an insight with missing or empty parts is handled.
"""
import json
from pathlib import Path

import pytest
from sf_orchestrator.reports import Orchestrator, Prompt, build_factors, build_report
from sf_orchestrator.schemas import FORECAST_EMPTY, FORECAST_NOT_USABLE, MetricInsight, ReportError, TrendAnalysis, clean_text, ignored_fields, parse_draft

from helpers import OK, RUN_DATE, VALID_DRAFT_TEXT, FakeLlm, MemStore, ask, insight, make_draft, rec, with_fake_router


# ───────────────────────── the contracts ─────────────────────────


SAMPLE = Path(__file__).resolve().parent / "samples" / "TimeToHire.json"


def test_insight_accepts_the_notebook_format():
    m = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    assert m.industry_standard_value == 20 and m.module is None
    assert m.forecast and m.forecast.next_quarter and m.forecast.next_quarter.predicted_value == 32.5
    assert m.forecast.next_month and m.forecast.next_month.predicted_health_state == "at-risk"
    assert m.rca.factors[0].factor_name == "InterviewToOfferReleaseDuration" and m.rca.factors[1].segment == "Engineering"
    assert m.missing_configurations == ["SIGNING_BONUS"]
    assert m.data_quality and m.model_accuracy


def test_the_sample_file_is_in_the_notebook_format_and_nothing_in_it_is_ignored():
    payload = json.loads(SAMPLE.read_text())
    assert MetricInsight.model_validate(payload).health_state == "at-risk"
    assert ignored_fields(payload) == []


def test_the_trend_tree_is_flattened_for_the_prompt_without_null_periods():
    t = MetricInsight.model_validate(insight("TimeToHire", "critical")).trend_analysis.compact()
    assert t["direction"] == "up"
    # 2025-12 has no data, so 2025-Q4 is not a whole quarter and 2025 is not a whole year, whatever the notebook flagged on them
    assert t["yearly"] == [{"period": "2025", "average": 30.2, "partial": True}, {"period": "2026", "average": 33.0, "partial": True}]
    assert t["quarterly"] == [{"period": "2025-Q4", "average": 31.0, "partial": True}]
    assert t["monthly"] == [{"period": "2025-11", "average": 31.0}]  # 2025-12 has no average, so it is left out


def test_the_sample_trend_is_much_smaller_once_compacted():
    payload = json.loads(SAMPLE.read_text())
    compact = MetricInsight.model_validate(payload).trend_analysis.compact()
    assert len(compact["yearly"]) == 3 and len(compact["quarterly"]) == 8
    assert all(e["average"] is not None for level in ("yearly", "quarterly", "monthly") for e in compact[level])
    assert len(json.dumps(compact)) < len(json.dumps(payload["trendAnalysis"])) / 2


def test_the_prompt_copy_leaves_out_timestamps_and_the_module_but_keeps_the_rest():
    data = MetricInsight.model_validate(insight("TimeToHire", "critical")).for_prompt()
    assert "generatedAt" not in data and "module" not in data
    assert data["industryStandardValue"] == 20 and "predictedValue" in data["forecast"]["nextMonth"]
    assert data["dataQuality"]["checks"][0]["checkName"] == "StaleApplicationsInOpenRequisitions"
    assert "modelAccuracy" not in data  # which model was used and how accurate it is stays out of the prompt


def test_undeclared_top_level_fields_are_dropped_and_reported():
    payload = insight("TimeToHire", "critical", rawRecords=[{"candidateId": "C-1"}], recordCount=999)
    dumped = json.dumps(MetricInsight.model_validate(payload).for_prompt())
    assert "C-1" not in dumped and "recordCount" not in dumped
    assert ignored_fields(payload) == ["rawRecords", "recordCount"]
    assert ignored_fields(insight("TimeToHire", "critical")) == []


def test_extra_keys_inside_factors_are_kept():
    payload = insight("TimeToHire", "critical")
    payload["rca"]["factors"][0]["confidence"] = "high"
    assert "confidence" in json.dumps(MetricInsight.model_validate(payload).for_prompt())


def test_missing_rca_means_not_applicable():
    payload = insight("TimeToHire", "critical")
    del payload["rca"]
    assert MetricInsight.model_validate(payload).rca.applicable is False


@pytest.mark.parametrize("bad", [{"metricName": ""}, {"healthState": "ok"}, {"companyValue": "abc"}, {"trendAnalysis": {"direction": "sideways"}}])
def test_insight_rejects_invalid_values(bad):
    with pytest.raises(ValueError):
        MetricInsight.model_validate(insight("TimeToHire", "critical", **bad))


def test_insight_in_the_old_field_names_is_rejected_not_silently_misread():
    payload = insight("TimeToHire", "critical")
    payload["forecast"]["nextMonth"]["value"] = payload["forecast"]["nextMonth"].pop("predictedValue")
    with pytest.raises(ValueError):
        MetricInsight.model_validate(payload)


def test_parse_draft_accepts_fenced_json_and_rejects_the_rest():
    assert parse_draft("```json\n" + VALID_DRAFT_TEXT + "\n```").workstreams[0].id == "W1"
    with pytest.raises(ReportError, match="not valid JSON"):
        parse_draft("Sure! Here is your report")
    with pytest.raises(ReportError, match="required structure"):
        parse_draft('{"diagnosis": {}}')


def test_a_dash_or_empty_workstream_means_the_whole_plan():
    draft = make_draft(1)
    draft["activities"][0]["workstream"] = "-"
    assert parse_draft(json.dumps(draft)).activities[0].workstream is None


@pytest.mark.parametrize("field,value,expected", [("hours", 0, 1), ("hours", 41, 40), ("week", 0, 1), ("week", 13, 12)])
def test_activity_numbers_outside_the_range_are_clamped_not_rejected(field, value, expected):
    draft = make_draft(1)
    draft["activities"][0][field] = value
    assert getattr(parse_draft(json.dumps(draft)).activities[0], field) == expected


@pytest.mark.parametrize("field,value", [("role", "intern"), ("phase", "design")])
def test_activity_values_are_bounded(field, value):
    draft = make_draft(1)
    draft["activities"][0][field] = value
    with pytest.raises(ReportError):
        parse_draft(json.dumps(draft))


def _property_names(node, acc: set[str]) -> set[str]:
    if isinstance(node, dict):
        acc.update(node.get("properties", {}))
        for v in node.values():
            _property_names(v, acc)
    elif isinstance(node, list):
        for v in node:
            _property_names(v, acc)
    return acc


def test_clean_text_replaces_special_characters_everywhere_in_a_json_value():
    dirty = {"a": "x\u2011y\u00a0z", "b": ["1\u201122", {"c": "p\u202fq\u200br"}], "n": 5}
    assert clean_text(dirty) == {"a": "x-y z", "b": ["1-22", {"c": "p qr"}], "n": 5}


def test_financial_impact_is_a_list_and_the_old_name_and_a_single_sentence_are_still_read():
    from sf_orchestrator.schemas import BusinessImpact

    base = {"overview": "The metric is above the standard.", "slaAndTurnaround": "The process runs longer than the standard.", "governanceAndAudit": "No data findings were reported."}
    points = ["The financial impact cannot be quantified from the available data.", "Rework may take staff effort.", "Decisions could wait for better data."]
    assert BusinessImpact.model_validate({**base, "financialImpact": points}).model_dump(by_alias=True)["financialImpact"] == points
    old = BusinessImpact.model_validate({**base, "financialExposure": "The financial exposure cannot be quantified from the data."})
    assert old.model_dump(by_alias=True)["financialImpact"] == ["The financial exposure cannot be quantified from the data."]


# ───────────────────────── equal-period comparisons and sentence case ─────────────────────────


def test_the_sample_gets_only_complete_same_quarter_pairs():
    t = MetricInsight.model_validate(json.loads(SAMPLE.read_text())).trend_analysis.compact()
    assert t["equalPeriodComparisons"] == [
        {"earlierPeriod": "2025-Q1", "earlierAverage": 24.1, "laterPeriod": "2026-Q1", "laterAverage": 24.6},
        {"earlierPeriod": "2025-Q2", "earlierAverage": 26.1, "laterPeriod": "2026-Q2", "laterAverage": 26.4},
    ]


def test_partial_periods_are_never_paired():
    pairs = MetricInsight.model_validate(json.loads(SAMPLE.read_text())).trend_analysis.compact()["equalPeriodComparisons"]
    used = {p["earlierPeriod"] for p in pairs} | {p["laterPeriod"] for p in pairs}
    # 2024 and 2026 are partial years, 2024-Q4 and 2026-Q3 are partial quarters, 2026-Q4 has no data yet
    assert not used & {"2024", "2026", "2024-Q4", "2026-Q3", "2026-Q4"}


def test_two_consecutive_complete_years_are_paired():
    trend = TrendAnalysis.model_validate(
        {
            "direction": "up",
            "granularity": "yearly",
            "periods": [
                {"period": "2024", "average": 20.0, "isPartial": False},
                {"period": "2025", "average": 22.0, "isPartial": False},
                {"period": "2026", "average": 23.0, "isPartial": True},
            ],
        }
    )
    assert trend.compact()["equalPeriodComparisons"] == [
        {"earlierPeriod": "2024", "earlierAverage": 20.0, "laterPeriod": "2025", "laterAverage": 22.0}
    ]


def test_no_equal_complete_periods_gives_an_empty_list_not_a_missing_key():
    t = MetricInsight.model_validate(insight("TimeToHire", "critical")).trend_analysis.compact()
    assert t["equalPeriodComparisons"] == []


def test_the_comparisons_reach_the_prompt():
    data = MetricInsight.model_validate(json.loads(SAMPLE.read_text())).for_prompt()
    assert len(data["trendAnalysis"]["equalPeriodComparisons"]) == 2


def test_prose_fields_start_with_a_capital_letter_even_if_the_model_filled_in_a_template():
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    draft = make_draft(2)
    draft["assumptionsAndRisks"][0]["description"] = "managers may not adopt the new reminders."
    draft["assumptionsAndRisks"][0]["mitigation"] = "maintain the field so that future analyses can include it."
    draft["businessImpact"]["overview"] = "slow hiring is visible in the given numbers."
    draft["workstreams"][0]["step"] = "optimise the first stage of the process."
    draft["activities"][0]["activity"] = "validate the factors against the live process"
    report = build_report(json.dumps(draft), ins, build_factors(ins), "RCM")
    risk = report["assumptionsAndRisks"][0]
    assert risk["description"].startswith("Managers may not adopt")
    assert risk["mitigation"].startswith("Maintain the field")
    assert report["businessImpact"]["overview"].startswith("Slow hiring")
    assert report["workstreams"][0]["step"].startswith("Optimise")
    assert report["plan"]["phases"][0]["activities"][0]["activity"].startswith("Validate")


def test_ids_and_keys_are_never_changed_by_the_tidy_up():
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    report = build_report(json.dumps(make_draft(2)), ins, build_factors(ins), "RCM")
    assert [w["id"] for w in report["workstreams"]] == ["W1", "W2"]
    assert [p["phase"] for p in report["plan"]["phases"]] == ["architecture", "configuration", "rollout"]
    assert [w["fixesFactors"] for w in report["workstreams"]] == [["F1"], ["F2"]]


# ───────────────────────── a forecast that could not be calculated ─────────────────────────


PROMPT = Prompt("breach prompt", "b1")


def point(period: str, value=None, low=None, high=None, **extra) -> dict:
    return {"period": period, "predictedValue": value, "lowerBound": low, "upperBound": high, **extra}


def payload(forecast) -> dict:
    return {**insight("PositionManagementAccuracy", "critical"), "module": "EC", "forecast": forecast}


def prompt_forecast(forecast):
    return MetricInsight.model_validate(payload(forecast)).for_prompt().get("forecast", "no forecast")


# ───────────────────────── a forecast without values ─────────────────────────


def test_a_forecast_with_empty_numbers_is_accepted_and_the_model_is_told_it_cannot_be_used():
    empty = {"nextMonth": point("2026-10"), "nextQuarter": point("2026-Q4"), "nextYear": point("2027")}
    assert prompt_forecast(empty) == {"notUsable": FORECAST_EMPTY}


def test_a_forecast_whose_horizons_are_all_null_is_simply_no_forecast():
    assert prompt_forecast({"nextMonth": None, "nextQuarter": None, "nextYear": None}) == "no forecast"
    assert prompt_forecast(None) == "no forecast"


def test_only_the_complete_horizons_are_given_to_the_model():
    forecast = prompt_forecast({"nextMonth": point("2026-10", 30.5, 28.0, 33.0, predictedHealthState="At-risk"), "nextQuarter": point("2026-Q4"), "nextYear": None})
    assert forecast == {"nextMonth": {"period": "2026-10", "predictedValue": 30.5, "lowerBound": 28.0, "upperBound": 33.0, "predictedHealthState": "at-risk"}}


@pytest.mark.parametrize("missing", ["NaN", "nan", "N/A", "n/a", "", "  ", "-", "null", float("nan")])
def test_nan_and_words_for_a_number_count_as_missing(missing):
    assert prompt_forecast({"nextMonth": point("2026-10", missing, missing, missing)}) == {"notUsable": FORECAST_EMPTY}


def test_a_horizon_with_a_value_but_a_missing_bound_is_not_given_to_the_model():
    assert prompt_forecast({"nextMonth": point("2026-10", 30.0, None, 40.0)}) == {"notUsable": FORECAST_EMPTY}


def test_a_blank_predicted_health_state_is_fine():
    horizon = prompt_forecast({"nextMonth": point("2026-10", 30.0, 28.0, 33.0, predictedHealthState="")})["nextMonth"]
    assert horizon["predictedValue"] == 30.0 and "predictedHealthState" not in horizon


def test_a_renamed_field_is_still_rejected_and_not_read_as_no_forecast():
    renamed = {"nextMonth": {"period": "2026-10", "predictedValue": 30.0, "low": 28.0, "upperBound": 33.0}}
    with pytest.raises(ValueError, match="lowerBound"):
        MetricInsight.model_validate(payload(renamed))


def test_negative_values_still_make_the_forecast_unusable_and_missing_numbers_are_not_negative():
    assert prompt_forecast({"nextMonth": point("2026-10", 5.0, -2.0, 9.0)}) == {"notUsable": FORECAST_NOT_USABLE}
    assert prompt_forecast({"nextMonth": point("2026-10", None, None, 9.0)}) == {"notUsable": FORECAST_EMPTY}


async def test_a_critical_metric_with_an_empty_forecast_now_gets_its_report():
    """The case from the real run: the forecast numbers were empty and the whole metric was rejected."""
    empty = {"nextMonth": point("2026-10"), "nextQuarter": point("2026-Q4"), "nextYear": point("2027")}
    store, llm = MemStore([rec("EC", "PositionManagementAccuracy", payload(empty))]), FakeLlm()
    summary = await Orchestrator(store=store, llm=llm, prompt=PROMPT).run(RUN_DATE)
    assert (summary.generated, summary.failed) == (1, 0)
    assert '"notUsable"' in llm.last_user_prompt and FORECAST_EMPTY in llm.last_user_prompt


async def test_a_rejected_insight_lists_up_to_eight_problems_not_three():
    bad = {name: point(period, "abc", "abc", "abc") for name, period in (("nextMonth", "2026-10"), ("nextQuarter", "2026-Q4"), ("nextYear", "2027"))}
    store = MemStore([rec("EC", "PositionManagementAccuracy", payload(bad))])
    summary = await Orchestrator(store=store, llm=FakeLlm(), prompt=PROMPT).run(RUN_DATE)
    reason = summary.failures[0]["reason"]
    assert summary.failed == 1 and reason.startswith("Invalid ML insight:")
    assert "forecast.nextMonth.predictedValue" in reason and "forecast.nextYear.predictedValue" in reason  # the seventh problem shows too


# ───────────────────────── a re-ask that fits the provider's limit ─────────────────────────


async def test_the_re_ask_sends_back_only_the_beginning_of_a_long_rejected_answer():
    c, router = with_fake_router([("x" * 20000, "stop"), (OK, "stop")])
    result = await ask(c)
    first, second = router.calls
    echoed = second[-2]
    assert result.repairs == 1 and echoed["role"] == "assistant"
    assert len(echoed["content"]) < 1600 and echoed["content"].endswith("[the rest of the reply is left out]")
    assert "rejected" in second[-1]["content"]
    # the second request is about as big as the first, not 20,000 characters bigger
    assert sum(len(m["content"]) for m in second) < sum(len(m["content"]) for m in first) + 2000


async def test_a_short_rejected_answer_is_still_sent_back_whole():
    c, router = with_fake_router([("not json at all", "stop"), (OK, "stop")])
    await ask(c)
    assert router.calls[1][-2]["content"] == "not json at all"
