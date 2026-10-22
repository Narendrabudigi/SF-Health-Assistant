"""The checks and the completion of the model's draft: what code adds (factors, roles, hours, risk rows) and what it rejects or
repairs (internal wording, rankings, long narratives, unknown references).
"""
import json
import re

import pytest
from sf_orchestrator.reports import PHASES, Orchestrator, Prompt, build_factors, build_report, data_risk_rows, role_names
from sf_orchestrator.schemas import MAX_WORDS_POINT, MetricInsight, ReportError, parse_draft

from helpers import OK, RUN_DATE, FakeLlm, MemStore, ask, insight, make_draft, points, rec, with_fake_router


# ───────────────────────── factors, totals and references ─────────────────────────


def parsed(**over) -> MetricInsight:
    return MetricInsight.model_validate(insight("TimeToHire", "critical", **over))


def build_draft(draft: dict, module: str = "RCM", **insight_over) -> dict:
    ins = parsed(**insight_over)
    return build_report(json.dumps(draft), ins, build_factors(ins), module)


# ── factors lifted from the ML JSON ──


def test_factors_are_lifted_in_rank_order_with_ids_added_and_the_notebooks_own_numbers():
    f = build_factors(parsed())
    assert [x["id"] for x in f] == ["F1", "F2"]
    assert f[0]["factorName"] == "InterviewToOfferReleaseDuration" and f[0]["avgFactorValue"] == 11.2 and f[0]["impactPct"] == 54.4
    assert f[1]["segment"] == "Engineering" and f[1]["segmentAvgValue"] == 41.3 and f[1]["impactPct"] == 45.6
    assert "segment" not in f[0]  # a stage factor has no segment


def test_factors_follow_the_notebooks_rank_even_if_listed_out_of_order():
    factors = [
        {"rank": 3, "factorName": "A", "impactValue": 1.0, "impactPct": 9.0},
        {"rank": 1, "factorName": "B", "impactValue": 9.0, "impactPct": 80.0},
        {"rank": 2, "factorName": "C", "impactValue": 4.0, "impactPct": 11.0},
    ]
    f = build_factors(parsed(rca={"applicable": True, "breachValue": 14.0, "factors": factors}))
    assert [(x["id"], x["factorName"]) for x in f] == [("F1", "B"), ("F2", "C"), ("F3", "A")]


def test_impact_pct_is_calculated_only_when_the_notebook_leaves_it_out():
    factors = [{"rank": 1, "factorName": "A", "impactValue": 2.8, "impactPct": 99.0}, {"rank": 2, "factorName": "B", "impactValue": 2.8}]
    f = build_factors(parsed(rca={"applicable": True, "breachValue": 5.6, "factors": factors}))
    assert f[0]["impactPct"] == 99.0 and f[1]["impactPct"] == 50.0


def test_no_factors_when_rca_is_not_applicable():
    assert build_factors(parsed(rca={"applicable": False, "factors": [{"rank": 1, "factorName": "A", "impactValue": 1.0}]})) == []


def test_factor_keeps_extra_notebook_fields():
    f = build_factors(parsed(rca={"applicable": True, "factors": [{"rank": 1, "factorName": "Dept", "impactValue": 3.0, "note": "x"}]}))
    assert f[0]["note"] == "x"


# ── roles ──


def test_role_names_follow_the_sample_brd_for_rcm_and_the_same_pattern_elsewhere():
    assert role_names("RCM") == {
        "consultant": "SAP SuccessFactors Recruiting Lead Functional Consultant",
        "processOwner": "Talent Acquisition Operations & Process Governance Lead",
        "qaUat": "Quality Assurance & UAT Specialist",
    }
    assert role_names("ECP")["consultant"] == "SAP SuccessFactors Employee Central Payroll Lead Functional Consultant"
    assert role_names("ECP")["processOwner"] == "Payroll Operations & Process Governance Lead"
    assert role_names("ONB2")["processOwner"] == "HR Operations & Process Governance Lead"
    assert role_names("TEST")["consultant"] == "SAP SuccessFactors Lead Functional Consultant"


# ── assembly: what code adds ──


def test_totals_phases_roles_and_identity_come_from_code():
    r = build_draft(make_draft(2))
    assert r["metricName"] == "TimeToHire" and r["healthState"] == "critical"
    assert [p["phase"] for p in r["plan"]["phases"]] == [k for k, *_ in PHASES]
    assert [p["hours"] for p in r["plan"]["phases"]] == [8, 22, 12]
    assert r["plan"]["totalHours"] == 42 and r["plan"]["durationWeeks"] == 4
    assert r["plan"]["roles"] == [
        {"role": "SAP SuccessFactors Recruiting Lead Functional Consultant", "hours": 32},
        {"role": "Quality Assurance & UAT Specialist", "hours": 10},
    ]
    assert r["plan"]["phases"][0]["milestone"] == "Root Cause Validation & BRD Sign-Off"
    assert r["plan"]["phases"][1]["activities"][0]["role"] == "SAP SuccessFactors Recruiting Lead Functional Consultant"
    assert [f["id"] for f in r["factors"]] == ["F1", "F2"]


def test_report_contains_only_what_the_model_writes_plus_lifted_and_calculated_parts():
    r = build_draft(make_draft(2))
    assert set(r) == {
        "metricName", "healthState", "factors", "diagnosis", "businessImpact", "workstreams", "plan", "assumptionsAndRisks",
    }
    for lifted_from_the_ml_json in ("trend", "snapshot", "targetOutcome", "successCriteria", "rootCauseTable"):
        assert lifted_from_the_ml_json not in r


# ── what is rejected (and sent back to the model as the reason) ──


def bad(**edits):
    d = make_draft(2)
    for path, value in edits.items():
        node = d
        *parents, last = path.split("__")
        for p in parents:
            node = node[int(p)] if p.isdigit() else node[p]
        if last.isdigit():
            node[int(last)] = value
        else:
            node[last] = value
    return d


@pytest.mark.parametrize(
    "text",
    [
        "The ML insight shows that hiring is slow because of the process.",
        "According to the JSON, hiring is slower than the benchmark overall.",
    ],
)
def test_internal_wording_is_rejected_in_any_text_field(text):
    with pytest.raises(ReportError, match="internal wording"):
        build_draft(bad(diagnosis__narrative=points(text)))
    with pytest.raises(ReportError, match="internal wording"):
        build_draft(bad(assumptionsAndRisks__0__description=text))


@pytest.mark.parametrize(
    "text,plain",
    [
        ("Average hiring time is high (see rootCauseAnalysis for details).", "root cause analysis"),
        ("The hiringManagerEmployeeId column is empty for every requisition.", "hiring manager employee ID"),
        ("Delays in InterviewToOfferReleaseDuration are the driver of the breach.", "interview to offer release duration"),
        ("The INTERVIEW_DATE field is empty for several requisitions.", "interview date"),
        ("The SIGNING_BONUS field was left out because it is fully empty.", "signing bonus"),
        ("TimeToHire is well above the benchmark and still rising.", "time to hire"),
        ("StaleApplicationsInOpenRequisitions affects many records.", "stale applications in open requisitions"),
    ],
)
def test_copied_names_are_replaced_by_plain_words_in_any_text_field(text, plain):
    for out in (
        build_draft(bad(diagnosis__narrative=points(text)))["diagnosis"]["narrative"][0],
        build_draft(bad(assumptionsAndRisks__0__description=text))["assumptionsAndRisks"][0]["description"],
    ):
        assert plain.lower() in out.lower()
        assert not re.search(r"[a-z][A-Z]|[A-Z]{2,}_[A-Z]", out.replace("TimeTo", ""))


def test_role_keys_in_text_become_plain_words():
    out = build_draft(bad(diagnosis__narrative=points("The qaUat specialist and the processOwner sign off the plan together.")))["diagnosis"]["narrative"][0]
    assert "qaUat" not in out and "processOwner" not in out
    assert "quality assurance and UAT" in out and "process owner" in out


def test_an_algorithm_name_is_still_rejected():
    with pytest.raises(ReportError):
        build_draft(bad(diagnosis__narrative=points("The HistGradientBoostingRegressor behind the analysis is accurate.")))


def test_code_style_segment_values_become_plain_words():
    factors = [{"rank": 1, "factorName": "JobRole", "segment": "DataEngineer", "segmentAvgValue": 31.0, "impactValue": 11.4, "impactPct": 100.0}]
    d = make_draft(1)
    d["diagnosis"]["narrative"] = points("Hiring is slow, and the affected roles are the DataEngineer requisitions in particular.")
    out = build_draft(d, rca={"applicable": True, "factors": factors})["diagnosis"]["narrative"][0]
    assert "DataEngineer" not in out and "Data Engineer".lower() in out.lower()


def test_idle_workstreams_are_dropped_and_renumbered_by_code():
    d = make_draft(2)
    d["workstreams"].append({"id": "W3", "kind": "data", "step": "Review the data checks once more.", "fixesFactors": []})
    d["activities"] = [a for a in d["activities"] if a["workstream"] != "W3"]
    r = build_draft(d)
    assert [w["id"] for w in r["workstreams"]] == ["W1", "W2"]


def test_a_workstream_that_is_the_only_cover_for_a_factor_is_not_dropped():
    d = make_draft(2)
    d["activities"] = [a for a in d["activities"] if a["workstream"] != "W2"]
    with pytest.raises(ReportError, match="none for W2"):
        build_draft(d)


def test_the_week_above_twelve_is_capped_not_rejected():
    d = make_draft(2)
    d["activities"][-1]["week"] = 15
    r = build_draft(d)
    assert r["plan"]["durationWeeks"] <= 12


def test_plain_words_for_the_same_things_are_accepted():
    ok = [
        "Time to Hire is well above the benchmark.",
        "The interview-to-offer-release stage takes 11.2 days on average.",
        "The interview date and signing bonus fields are empty.",
        "Some applications in open requisitions are stale.",
    ]
    assert build_draft(bad(diagnosis__narrative=ok))["diagnosis"]["narrative"] == ok


def test_a_plain_single_word_factor_name_does_not_make_normal_prose_unusable():
    """'Department' is a real word: the model may write it, including at the start of a sentence."""
    ok = "Department level differences matter here, and the Engineering department is the largest contributor to the breach."
    assert build_draft(bad(diagnosis__narrative=points(ok)))["diagnosis"]["narrative"][0] == ok


def test_normal_product_and_module_names_are_not_mistaken_for_internal_wording():
    ok = "SAP SuccessFactors Employee Central and Onboarding 2.0 reminders help the UAT specialist and the HR team."
    assert build_draft(bad(diagnosis__narrative=points(ok)))["diagnosis"]["narrative"][0] == ok


def test_unknown_factor_id_is_rejected():
    with pytest.raises(ReportError, match="unknown factor.*F9"):
        build_draft(bad(workstreams__0__fixesFactors=["F9"]))


def test_an_uncovered_factor_is_rejected():
    d = make_draft(2)
    d["workstreams"][1]["fixesFactors"] = ["F1"]
    with pytest.raises(ReportError, match="not covered: F2"):
        build_draft(d)


def test_a_workstream_must_fix_something_and_have_activities():
    with pytest.raises(ReportError, match="at least one factor"):
        build_draft(bad(workstreams__0__fixesFactors=[]))
    d = make_draft(2)
    d["activities"] = [a for a in d["activities"] if a["workstream"] != "W2"]
    with pytest.raises(ReportError, match="none for W2"):
        build_draft(d)


def test_activity_pointing_at_an_unknown_workstream_is_rejected():
    with pytest.raises(ReportError, match="unknown workstream.*W7"):
        build_draft(bad(activities__1__workstream="W7"))


def test_every_phase_must_be_used():
    d = make_draft(2)
    d["activities"] = [a for a in d["activities"] if a["phase"] != "rollout"]
    with pytest.raises(ReportError, match="none for rollout"):
        build_draft(d)


def test_duplicate_workstream_ids_are_rejected():
    d = make_draft(2)
    d["workstreams"][1]["id"] = "W1"
    with pytest.raises(ReportError, match="unique"):
        build_draft(d)


def test_a_breached_metric_with_no_factors_does_not_force_invented_factor_links():
    d = make_draft(1)
    d["workstreams"][0]["fixesFactors"] = []
    r = build_draft(d, rca={"applicable": False, "factors": []})
    assert r["factors"] == [] and r["workstreams"][0]["fixesFactors"] == []


def test_special_hyphens_and_spaces_are_replaced_by_plain_ones():
    text = "The application\u2011to\u2011interview stage takes 18.4 days (forecast range 23.8\u201128.0), with\u00a0no change."
    out = build_draft(bad(diagnosis__narrative=points(text)))["diagnosis"]["narrative"][0]
    assert "\u2011" not in out and "\u00a0" not in out
    assert "application-to-interview" in out and "23.8-28.0" in out


def test_the_configuration_phase_needs_a_staging_or_uat_activity_by_the_qa_role():
    # activity 3 of make_draft is the staging test in the configuration phase
    with pytest.raises(ReportError, match="staging test or user acceptance testing"):
        build_draft(bad(activities__3__role="consultant"))


def test_a_qa_activity_in_the_rollout_phase_alone_does_not_satisfy_the_testing_rule():
    d = make_draft(2)
    d["activities"][3]["phase"] = "rollout"
    with pytest.raises(ReportError, match="staging test or user acceptance testing"):
        build_draft(d)


# ───────────────────────── the narrative is a short list of points ─────────────────────────


def words(n: int) -> str:
    """A plain sentence of exactly n words."""
    return " ".join(["metric"] * n) + "."


def draft_text(narrative) -> str:
    d = make_draft(2)
    d["diagnosis"]["narrative"] = narrative
    return json.dumps(d)


def build_narrative(narrative) -> dict:
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    return build_report(draft_text(narrative), ins, build_factors(ins), "RCM")


def sentence(*numbers: str) -> list[str]:
    """Two points that together hold exactly these numbers."""
    first = "The value is " + " and ".join(numbers) + " here." if numbers else "The value is above the standard."
    return [first, "The forecast expects it to stay above the standard."]


# ───────────────────────── a list of points ─────────────────────────


def test_the_report_carries_the_narrative_as_a_list_of_points():
    report = build_narrative(make_draft()["diagnosis"]["narrative"])
    assert report["diagnosis"]["narrative"] == [
        "Time to hire is above the industry standard, at 31.4 days against 20 days.",
        "Compared with the same quarter a year earlier, the average rose.",
        "The forecast expects it to stay above the standard.",
        "The interview-to-offer stage and Engineering requisitions lead the breach.",
    ]
    assert isinstance(report["diagnosis"]["headline"], str)  # only the narrative became a list


ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth"]


def plain_points(count: int) -> list[str]:
    return [f"The {ORDINALS[i]} point says something plain here." for i in range(count)]  # words only, no digits


@pytest.mark.parametrize("count", [2, 3, 4, 5])
def test_two_to_five_points_are_accepted(count):
    assert len(build_narrative(plain_points(count))["diagnosis"]["narrative"]) == count


@pytest.mark.parametrize("count,message", [(1, "at least 2 items"), (6, "at most 5 items")])
def test_fewer_than_two_or_more_than_five_points_are_sent_back(count, message):
    with pytest.raises(ReportError, match=message):
        parse_draft(draft_text(plain_points(count)))


def test_a_paragraph_instead_of_a_list_is_sent_back():
    with pytest.raises(ReportError, match="valid list"):
        parse_draft(draft_text("Time to hire is above the standard. It has risen. The forecast stays above the standard."))


def test_each_point_is_a_short_sentence():
    assert build_narrative([words(4), words(MAX_WORDS_POINT)])["diagnosis"]["narrative"]  # the limits themselves are fine
    with pytest.raises(ReportError, match="at least 4 words"):
        parse_draft(draft_text([words(3), words(6)]))
    with pytest.raises(ReportError, match=f"{MAX_WORDS_POINT + 1} words, the limit is {MAX_WORDS_POINT}"):
        parse_draft(draft_text([words(MAX_WORDS_POINT + 1), words(6)]))


def test_every_point_starts_with_a_capital_letter():
    out = build_narrative(["the value is above the standard here.", "the forecast expects it to stay above."])["diagnosis"]["narrative"]
    assert out == ["The value is above the standard here.", "The forecast expects it to stay above."]


# ───────────────────────── numbers: a warning, never a rejection ─────────────────────────


def test_an_answer_within_the_ask_is_accepted_without_a_warning(caplog):
    with caplog.at_level("WARNING"):
        assert build_narrative(sentence("31.4 days", "20 days"))["diagnosis"]["narrative"]
    assert "numbers" not in caplog.text


@pytest.mark.parametrize("count", [3, 5, 8, 11])
def test_too_many_numbers_are_accepted_and_only_logged(count, caplog):
    values = [f"{i + 1}.5" for i in range(count)]
    with caplog.at_level("WARNING"):
        out = build_narrative(sentence(*values))["diagnosis"]["narrative"]
    assert out[0].count(".5") == count
    assert f"contain {count} numbers" in caplog.text


def test_the_other_fields_keep_their_numbers():
    """Only the narrative is limited; the business impact still quotes the input's numbers exactly."""
    d = make_draft(2)
    d["businessImpact"]["overview"] = "The value of 31.4 days exceeds the 20 day standard by 11.4 days, and the forecast stays above it."
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    report = build_report(json.dumps(d), ins, build_factors(ins), "RCM")
    assert "11.4 days" in report["businessImpact"]["overview"]


# ───────────────────────── the same wording checks, for every point ─────────────────────────


def test_internal_wording_is_found_in_any_point_not_only_the_first():
    with pytest.raises(ReportError, match="internal wording"):
        build_narrative(["The value is above the standard here.", "The ML insight lists the factors behind it."])


def test_a_ranking_the_input_does_not_give_is_found_in_any_point():
    with pytest.raises(ReportError, match="rank items the input does not rank"):
        build_narrative(["The value is above the standard here.", "The slowest stage is the interview step in particular."])


# ───────────────────────── asking again, and the prompt ─────────────────────────


async def test_internal_wording_makes_the_model_write_the_points_again():
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    factors = build_factors(ins)
    bad = draft_text(["The value is above the standard here.", "The ML insight lists the factors behind it."])
    c, router = with_fake_router([(bad, "stop"), (OK, "stop")])
    result = await ask(c, lambda text: build_report(text, ins, factors, "RCM"))
    assert result.repairs == 1 and "internal wording" in router.calls[1][-1]["content"]
    assert isinstance(result.value["diagnosis"]["narrative"], list)


async def test_the_stored_report_has_the_points_and_nothing_else_changed():
    store = MemStore([rec("RCM", "TimeToHire", insight("TimeToHire", "critical"))])
    await Orchestrator(store=store, llm=FakeLlm(), prompt=Prompt("breach", "b1")).run(RUN_DATE)
    report = store.reports[(RUN_DATE, "RCM", "TimeToHire")].report
    assert report["diagnosis"]["narrative"] == make_draft()["diagnosis"]["narrative"] and report["diagnosis"]["headline"]
    assert set(report) >= {"factors", "diagnosis", "businessImpact", "workstreams", "plan", "assumptionsAndRisks"}


def test_equal_period_comparisons_is_replaced_in_code_not_rejected():
    out = build_narrative(["The value is above the standard, as the Equal Period Comparisons show.", "The forecast expects it to stay above."])
    assert "same-period comparisons" in out["diagnosis"]["narrative"][0]
    assert "qual period" not in out["diagnosis"]["narrative"][0]


async def test_when_the_re_ask_meets_a_provider_problem_the_failure_says_what_was_wrong_with_the_answer():
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    factors = build_factors(ins)
    bad = draft_text(["The value is above the standard here.", "The ML insight lists the factors behind it."])
    c, router = with_fake_router([(bad, "stop"), (OK, "stop")])
    original = router.acompletion
    calls = {"n": 0}

    async def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("all providers are in cooldown")
        return await original(**kwargs)

    router.acompletion = flaky
    with pytest.raises(ReportError, match="internal wording.*re-ask failed.*cooldown"):
        await ask(c, lambda text: build_report(text, ins, factors, "RCM"))


# ───────────────────────── rankings and internal names ─────────────────────────


def build_with(field_path: tuple[str, ...], text: str) -> dict:
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    draft = make_draft(2)
    node = draft
    for key in field_path[:-1]:
        node = node[int(key)] if key.isdigit() else node[key]
    last = field_path[-1]
    node[int(last) if last.isdigit() else last] = points(text) if field_path == ("diagnosis", "narrative") else text
    return build_report(json.dumps(draft), ins, build_factors(ins), "RCM")


@pytest.mark.parametrize(
    "path,text",
    [
        (("businessImpact", "slaAndTurnaround"), "The longest segment is the Data Engineer roles, which average 41.3 days."),
        (("diagnosis", "narrative"), "Engineering is the slowest segment, averaging 41.3 days, so it needs the most attention here."),
        (("businessImpact", "overview"), "The highest contribution to the breach of 11.4 days comes from the first stage."),
        (("assumptionsAndRisks", "0", "description"), "The worst data finding is the stale records, which affect the analysis."),
    ],
)
def test_rankings_the_input_does_not_give_are_rejected(path, text):
    with pytest.raises(ReportError, match="rank items the input does not rank"):
        build_with(path, text)


def test_the_rank_one_factor_may_be_called_the_largest_contributor():
    text = "The application-to-interview stage is the largest contributor, with 6.2 days or 54.4% of the breach of 11.4 days."
    assert build_with(("diagnosis", "narrative"), text)["diagnosis"]["narrative"][0] == text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Equal period comparisons show an upward trend, with the average rising from 24.1 days to 24.6 days.", "Same-period comparisons show"),
        ("The equal-period comparisons list shows the same quarters one year apart, rising from 24.1 days to 24.6 days.", "The same-period comparisons list shows"),
    ],
)
def test_the_name_of_the_comparison_field_is_replaced_in_code_not_rejected(text, expected):
    assert build_with(("diagnosis", "narrative"), text)["diagnosis"]["narrative"][0].startswith(expected)


def test_a_plain_description_of_the_same_comparison_is_accepted():
    text = "Comparing the same quarters a year apart shows a rise from 24.1 days to 24.6 days in the first quarter."
    assert build_with(("diagnosis", "narrative"), text)["diagnosis"]["narrative"][0] == text


# ───────────────────────── ordinary phrases are not internal wording ─────────────────────────


def build_with_narrative(text: str) -> dict:
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    draft = make_draft(2)
    draft["diagnosis"]["narrative"] = points(text)
    return build_report(json.dumps(draft), ins, build_factors(ins), "RCM")


@pytest.mark.parametrize(
    "phrase",
    [
        "Trend analysis shows that the average rose from 2025 to 2026, comparing full years with full years only.",
        "The root cause analysis points to the interview-to-offer-release stage as the largest contributor to the breach.",
        "A root cause analysis of the three leading factors explains the whole gap of 11.4 days against the standard.",
    ],
)
def test_ordinary_business_phrases_are_not_rejected(phrase):
    assert build_with_narrative(phrase)["diagnosis"]["narrative"][0] == phrase


@pytest.mark.parametrize(
    "phrase",
    [
        "The ML insight shows that the average rose over the period shown in the input.",
        "According to the JSON, the average rose over the period shown in the input data.",
    ],
)
def test_internal_terms_are_still_rejected(phrase):
    with pytest.raises(ReportError, match="internal wording"):
        build_with_narrative(phrase)


# ───────────────────────── data workstreams ─────────────────────────


def draft_with_data_workstream(**override) -> dict:
    d = make_draft(2)
    d["workstreams"].append(
        {"id": "W3", "kind": "data", "step": "Address the failed data checks by validating the interview date field.", "fixesFactors": [], **override}
    )
    d["activities"].append(
        {"phase": "configuration", "activity": "Configure validation for the interview date field", "role": "consultant", "workstream": "W3", "week": 3, "hours": 6}
    )
    return d


def build_workstream(draft: dict) -> dict:
    ins = MetricInsight.model_validate(insight("TimeToHire", "critical"))
    return build_report(json.dumps(draft), ins, build_factors(ins), "RCM")


def test_a_data_workstream_without_factors_is_accepted_and_marked_in_the_report():
    r = build_workstream(draft_with_data_workstream())
    assert [(w["id"], w["kind"], w["fixesFactors"]) for w in r["workstreams"]] == [
        ("W1", "factor", ["F1"]),
        ("W2", "factor", ["F2"]),
        ("W3", "data", []),
    ]
    assert r["plan"]["totalHours"] == 48  # the data activity (6 h) is part of the plan


def test_a_data_workstream_that_claims_to_fix_a_factor_is_rejected():
    with pytest.raises(ReportError, match='W3 is a data workstream.*fixesFactors must be empty'):
        build_workstream(draft_with_data_workstream(fixesFactors=["F1"]))


def test_a_data_workstream_does_not_count_as_fixing_a_factor():
    d = draft_with_data_workstream()
    d["workstreams"][1]["fixesFactors"] = ["F1"]  # nothing fixes F2 any more
    with pytest.raises(ReportError, match="not covered: F2"):
        build_workstream(d)


def test_a_factor_workstream_still_needs_a_factor():
    d = make_draft(2)
    d["workstreams"][0]["fixesFactors"] = []
    with pytest.raises(ReportError, match="at least one factor"):
        build_workstream(d)


def test_kind_defaults_to_factor_when_the_model_leaves_it_out():
    assert parse_draft(json.dumps(make_draft(2))).workstreams[0].kind == "factor"


def test_an_unknown_kind_is_rejected():
    d = make_draft(2)
    d["workstreams"][0]["kind"] = "other"
    with pytest.raises(ReportError):
        parse_draft(json.dumps(d))


# ───────────────────────── risk rows written by code ─────────────────────────


def make(**extra):
    return MetricInsight.model_validate(insight("TimeToHire", "critical", **extra))


def check(**kw):
    return {"checkName": "MissingValues", "category": "Completeness", "checkedRecords": 980, "failedRecords": 9, "failedPct": 0.9, **kw}


def test_a_failed_check_gets_the_fixed_sentence():
    ins = make(dataQuality={"checks": [check(affectedColumns=["INTERVIEW_DATE"])]}, missingConfigurations=[])
    (row,) = data_risk_rows(ins)
    assert row["type"] == "Risk"
    assert row["description"] == "9 of 980 records (0.9%) failed the check for missing values (interview date). This may affect the reliability of the analysis."


def test_a_check_that_found_nothing_is_not_a_finding():
    ins = make(dataQuality={"checks": [check(failedRecords=0, failedPct=0.0)]}, missingConfigurations=[])
    assert data_risk_rows(ins) == []


def test_without_the_number_checked_or_the_percentage_the_sentence_has_neither():
    ins = make(dataQuality={"checks": [check(checkedRecords=0, failedPct=None)]}, missingConfigurations=[])
    assert data_risk_rows(ins)[0]["description"].startswith("9 records failed the check for missing values.")


def test_stale_records_name_their_dates_or_their_age():
    dated = make(dataQuality={"checks": [check(checkName="StaleApplications", category="Staleness", staleRange={"from": "2024-12-03", "to": "2026-06-14"})]}, missingConfigurations=[])
    text = make(dataQuality={"checks": [check(checkName="Staleness", category="Staleness", staleRange="> 3 years old")]}, missingConfigurations=[])
    assert "The stale records date from 2024-12-03 to 2026-06-14." in data_risk_rows(dated)[0]["description"]
    assert "The stale records are > 3 years old." in data_risk_rows(text)[0]["description"]


def test_at_most_five_fields_are_named():
    cols = [f"field{i}Name" for i in range(7)]
    desc = data_risk_rows(make(dataQuality={"checks": [check(affectedColumns=cols)]}, missingConfigurations=[]))[0]["description"]
    assert "and other fields" in desc and "field5 name" not in desc


def test_every_empty_field_gets_a_row_in_a_diagnosis():
    ins = make(missingConfigurations={"mandatoryFieldsMissing": ["screeningDate"], "otherFieldsMissing": ["appExpCtc"]}, dataQuality={"checks": []})
    assert [r["description"] for r in data_risk_rows(ins)] == [
        "The screening date field is completely empty in the client's data, so it was left out of the analysis.",
        "The applicant expected CTC field is completely empty in the client's data, so it was left out of the analysis.",
    ]


def test_a_setup_plan_lists_only_the_other_fields_and_always_says_the_metric_stays_unavailable():
    ins = make(missingConfigurations={"mandatoryFieldsMissing": ["screeningDate"], "otherFieldsMissing": ["appExpCtc"]}, dataQuality={"checks": []})
    rows = data_risk_rows(ins, setup=True)
    assert rows[0]["description"] == "The applicant expected CTC field is also empty in the client's data. The metric does not need it, so it does not block the calculation."
    assert rows[-1] == {"type": "Risk", "description": "The metric stays unavailable until its mandatory fields are filled.", "mitigation": "Set up the mandatory fields first, then run the analysis again."}
    assert len(rows) == 2


def test_the_report_has_the_models_rows_and_the_code_rows_and_no_repeat():
    ins = make(missingConfigurations=["SIGNING_BONUS"], dataQuality={"checks": [check()]})
    draft = make_draft(2)
    draft["assumptionsAndRisks"] = [
        {"type": "Assumption", "description": "The factors stay valid during the plan.", "mitigation": "Confirm them in the first week."},
        {"type": "Risk", "description": "The signing bonus field is completely empty in the client's data, so it was left out of the analysis.", "mitigation": "Maintain the field."},
    ]
    rows = build_report(json.dumps(draft), ins, build_factors(ins), "RCM")["assumptionsAndRisks"]
    assert [r["type"] for r in rows] == ["Assumption", "Risk", "Risk"]
    assert rows[0]["description"].startswith("The factors stay valid")
    assert sum("signing bonus" in r["description"].lower() for r in rows) == 1


def test_a_model_that_writes_no_risk_rows_at_all_is_accepted():
    ins = make(missingConfigurations=[], dataQuality={"checks": []})
    draft = make_draft(2)
    draft["assumptionsAndRisks"] = []
    assert build_report(json.dumps(draft), ins, build_factors(ins), "RCM")["assumptionsAndRisks"] == []
