from __future__ import annotations

import json
from typing import Any, Callable

from types import SimpleNamespace

from sf_orchestrator.config import Settings
from sf_orchestrator.llm import LlmClient
from sf_orchestrator.reports import Prompt
from sf_orchestrator.schemas import parse_draft
from sf_orchestrator.llm import LlmResult
from sf_orchestrator.store import InsightRecord, ReportRecord

RUN_DATE = "2026-09-29"
CHAIN = "gemini/gemini-a,gemini/gemini-b,groq/openai/gpt-a,groq/openai/gpt-b"


def make_settings(**over: Any) -> Settings:
    base = dict(
        _env_file=None,
        supabase_url="https://abc.supabase.co",
        supabase_service_role_key="service-role-key-0123456789",
        gemini_api_key="gemini-key-1234567890",
        groq_api_key="groq-key-1234567890",
        llm_chain=CHAIN,
        llm_cooldown_seconds=30,
        # no waiting in tests; the tests that check waiting set these themselves
        llm_num_retries=0,
        llm_rate_limit_retries=0,
        llm_retry_wait_seconds=0,
    )
    base.update(over)
    return Settings(**base)


def _fp(period: str, v: float) -> dict[str, Any]:
    return {"period": period, "predictedValue": v, "lowerBound": v - 2, "upperBound": v + 2, "predictedHealthState": "at-risk"}


def _trend() -> dict[str, Any]:
    """The notebook's nested year > quarter > month tree, with null averages and partial periods."""
    return {
        "direction": "up",
        "granularity": "yearly",
        "periods": [
            {
                "period": "2025", "year": 2025, "average": 30.2, "isPartial": False,
                "children": {
                    "granularity": "quarterly",
                    "periods": [
                        {
                            "period": "2025-Q4", "quarter": 4, "average": 31.0, "isPartial": False,
                            "children": {
                                "granularity": "monthly",
                                "periods": [
                                    {"period": "2025-11", "month": 11, "average": 31.0, "isPartial": False},
                                    {"period": "2025-12", "month": 12, "average": None, "isPartial": True},
                                ],
                            },
                        }
                    ],
                },
            },
            {"period": "2026", "year": 2026, "average": 33.0, "isPartial": True},
        ],
    }


def insight(metric: str, health: str, **over: Any) -> dict[str, Any]:
    """A valid ML insight in the notebook's format, for ANY metric: only names and numbers change between modules.
    Two factors (impact 6.2 + 5.2 = the 11.4 breach); one stage factor and one attribute factor."""
    body: dict[str, Any] = {
        "generatedAt": "2026-09-29T02:00:00Z",
        "metricName": metric,
        "unit": "days",
        "higherIsBetter": False,
        "companyValue": 31.4,
        "industryStandardValue": 20,
        "healthState": health,
        "variance": {"value": 11.4, "percentage": 57.0},
        "trendAnalysis": _trend(),
        "forecast": {"nextMonth": _fp("2026-10", 33), "nextQuarter": _fp("2026-Q4", 32.5), "nextYear": _fp("2027", 31)},
        "rca": {
            "applicable": True,
            "breachValue": 11.4,
            "factors": [
                {"rank": 1, "factorName": "InterviewToOfferReleaseDuration", "segment": None, "avgFactorValue": 11.2, "segmentAvgValue": None, "impactValue": 6.2, "impactPct": 54.4},
                {"rank": 2, "factorName": "Department", "segment": "Engineering", "avgFactorValue": None, "segmentAvgValue": 41.3, "impactValue": 5.2, "impactPct": 45.6},
            ],
        },
        "dataQuality": {
            "overallRating": "fair",
            "dataPeriod": {"from": "2024-11-23", "to": "2026-09-21"},
            "recordsAnalysed": 980,
            "checks": [
                {"checkName": "StaleApplicationsInOpenRequisitions", "category": "Staleness", "checkedRecords": 410, "failedRecords": 63, "failedPct": 15.4,
                 "affectedColumns": None, "staleRange": {"from": "2024-12-03", "to": "2026-06-14"}},
                {"checkName": "MandatoryFieldsMissing", "category": "Completeness", "checkedRecords": 980, "failedRecords": 9, "failedPct": 0.9,
                 "affectedColumns": ["INTERVIEW_DATE"], "staleRange": None},
            ],
        },
        "modelAccuracy": {
            "rcaModel": {"modelName": "HistGradientBoostingRegressor", "r2": 0.9, "mae": 3.7, "rmse": 4.6, "rating": "good"},
            "forecastModel": {"modelName": "DampedTrend", "r2": None, "mae": 2.1, "rmse": 2.6, "rating": "fair"},
        },
        "missingConfigurations": ["SIGNING_BONUS"],
    }
    body.update(over)
    return body


def rec(module: str, metric: str, payload: Any) -> InsightRecord:
    """Stored row. Like the real ML job, the JSON carries the same module as the row unless a test says otherwise."""
    if isinstance(payload, dict) and "module" not in payload:
        payload = {**payload, "module": module}
    return InsightRecord(run_date=RUN_DATE, module=module, metric_name=metric, payload=payload)


PAD_POINT = "Nothing else in the data changes this picture."


def points(text: str) -> list[str]:
    """A narrative of two points whose second point is harmless filler: lets a test put one sentence of its own under test."""
    return [text, PAD_POINT]


def make_draft(n: int = 2) -> dict[str, Any]:
    """A valid LLM answer covering factors F1..Fn, one workstream per factor.
    n=2 -> consultant 32 h, qaUat 10 h, total 42 h over 4 weeks."""
    return {
        "diagnosis": {
            "headline": "Time to hire is far above the industry standard",
            "narrative": [
                "Time to hire is above the industry standard, at 31.4 days against 20 days.",
                "Compared with the same quarter a year earlier, the average rose.",
                "The forecast expects it to stay above the standard.",
                "The interview-to-offer stage and Engineering requisitions lead the breach.",
            ],
        },
        "businessImpact": {
            "overview": "Slow hiring keeps critical roles vacant for longer.",
            "financialImpact": [
                "The financial impact cannot be quantified from the available data.",
                "Open roles may keep costing effort while they stay unfilled.",
                "Decisions that depend on hiring speed could wait longer.",
            ],
            "slaAndTurnaround": "Requisitions stay open longer and candidates drop out.",
            "governanceAndAudit": "Inconsistent approval timelines weaken process governance.",
        },
        "workstreams": [
            {"id": f"W{i}", "step": f"Remediation step number {i}", "fixesFactors": [f"F{i}"]} for i in range(1, n + 1)
        ],
        "activities": [
            {"phase": "architecture", "activity": "Validate the factors against the live process", "role": "consultant", "workstream": None, "week": 1, "hours": 8},
            *[
                {"phase": "configuration", "activity": f"Configure remediation {i}", "role": "consultant", "workstream": f"W{i}", "week": i + 1, "hours": 8}
                for i in range(1, n + 1)
            ],
            {"phase": "configuration", "activity": "Staging environment test", "role": "qaUat", "workstream": None, "week": n + 1, "hours": 6},
            {"phase": "rollout", "activity": "Production cutover", "role": "consultant", "workstream": None, "week": n + 2, "hours": 8},
            {"phase": "rollout", "activity": "Re-measure against the standard", "role": "qaUat", "workstream": None, "week": n + 2, "hours": 4},
        ],
        "assumptionsAndRisks": [
            {"type": "Assumption", "description": "A staging system mirrors production.", "mitigation": "Confirm before the first phase."},
            {"type": "Risk", "description": "Managers may not adopt the new reminders.", "mitigation": "Weekly review with leadership."},
        ],
    }


VALID_DRAFT_TEXT = json.dumps(make_draft(2))


class FakeLlm:
    """Scripted stand-in for LlmClient. Each step is an Exception to raise or anything else for success
    (the model then 'answers' with a valid draft, which goes through the real parse function); the last step repeats."""

    def __init__(self, steps: list[Any] | None = None, draft_factors: int = 2, retries: int = 0, fallbacks: int = 0):
        self.retries, self.fallbacks = retries, fallbacks
        self.steps = steps or ["ok"]
        self.draft_text = json.dumps(make_draft(draft_factors))
        self.calls = 0
        self.last_user_prompt = ""

    async def generate(self, system_prompt: str, user_prompt: str, parse: Callable[[str], Any], *, run_key: str = "") -> LlmResult:
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        self.last_user_prompt = user_prompt
        if isinstance(step, Exception):
            raise step
        return LlmResult(
            value=parse(self.draft_text),
            provider="gemini",
            model="gemini-a",
            fallbacks=self.fallbacks,
            retries=self.retries,
            repairs=0,
            input_tokens=10,
            output_tokens=20,
            latency_ms=5,
        )


class HttpErr(Exception):
    """Mock provider failure with an HTTP status. Deep-copyable, which LiteLLM requires of mock_response."""

    def __init__(self, status_code: int, text: str):
        super().__init__(text)
        self.status_code, self.text = status_code, text

    def __reduce__(self):
        return (HttpErr, (self.status_code, self.text))


class MemStore:
    def __init__(self, rows: list[InsightRecord]):
        self.rows = rows
        self.reports: dict[tuple[str, str, str], ReportRecord] = {}

    def list_insights(self, run_date: str, module: str | None = None, metric: str | None = None) -> list[InsightRecord]:
        return [
            r
            for r in self.rows
            if r.run_date == run_date and (not module or r.module == module) and (not metric or r.metric_name == metric)
        ]

    def find_report(self, run_date: str, module: str, metric_name: str) -> ReportRecord | None:
        return self.reports.get((run_date, module, metric_name))

    def save_report(self, record: ReportRecord) -> None:
        self.reports[(record.run_date, record.module, record.metric_name)] = record


OK = VALID_DRAFT_TEXT


def client(*mocks, **settings_over) -> LlmClient:
    """One mock per model in the chain (gemini-a, gemini-b, groq openai/gpt-a, groq openai/gpt-b)."""
    return LlmClient(make_settings(**settings_over), [{"mock_response": m} for m in mocks])


async def ask(c: LlmClient, parse=parse_draft):
    return await c.generate("system", "user", parse, run_key="RCM/TimeToHire")


# ── schema-validity handling (ours, not LiteLLM's): re-ask once, then give up ──


class FakeRouter:
    def __init__(self, replies: list[tuple[str, str]]):
        self.replies, self.calls = replies, []

    async def acompletion(self, **kw):
        self.calls.append(kw["messages"])
        content, finish = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
            model="gemini-a",
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=7),
            _hidden_params={"custom_llm_provider": "gemini", "additional_headers": {}},
        )


def with_fake_router(replies, **settings_over) -> tuple[LlmClient, FakeRouter]:
    c = client(OK, OK, OK, OK, **settings_over)
    c._router = FakeRouter(replies)  # type: ignore[assignment]
    return c, c._router  # type: ignore[return-value]


BREACH_PROMPT = Prompt("breach prompt", "b1")


HEALTHY_PROMPT = Prompt("healthy prompt", "h1")


P1 = (
    "Offboarding Cycle Time stands at 44.28 days and is healthy, within the industry standard of 30 to 60 days. "
    "A lower value is better for this metric. The full year 2025 averaged 43.2 days. Comparing the same quarters in 2025 and 2026, "
    "the first quarter rose from 40.51 days to 46.11 days, while the second quarter fell from 45.64 days to 44.5 days. "
    "The periods that cover only part of their time, including the most recent months, were left out of these comparisons "
    "because they are incomplete."
)


P2 = (
    "The analysis covers 1129 records from 2024-10-14 to 2026-09-06, and the overall data rating is fair. "
    "The completeness check found 17 of 1129 records, 1.51%, with an empty offboarding completion date field. "
    "The staleness check also flagged 17 of 1129 records, 1.51%, dated from 2026-07-06 to 2026-09-08. "
    "The validity check found no problems. No field is completely empty. "
    "The forecast could not be used because it gave impossible negative values."
)


SUMMARY = json.dumps({"summary": [P1, P2]})


# ───────────────────────── in the pipeline ─────────────────────────


class SpyLlm(FakeLlm):
    """Answers a healthy prompt with a summary and any other prompt with a diagnosis, and remembers which prompt it got."""

    def __init__(self, summary_text: str = SUMMARY):
        super().__init__()
        self.summary_text, self.diagnosis_text, self.system_prompts = summary_text, self.draft_text, []

    async def generate(self, system_prompt, user_prompt, parse, *, run_key=""):
        self.system_prompts.append(system_prompt)
        self.draft_text = self.summary_text if system_prompt == HEALTHY_PROMPT.text else self.diagnosis_text
        return await super().generate(system_prompt, user_prompt, parse, run_key=run_key)
