"""Both contracts in one place.

INPUT  (MetricInsight): the standard ML JSON, identical for every metric in every module
        (RCM, ONB2, OFB2, EC, ECP). The JSON names its module, and the stored row carries it too; they must match.
OUTPUT (BrdDraft): what the LLM writes. Only the parts of the BRD that cannot be lifted from the ML JSON.
        Everything that CAN be lifted (snapshot, trend, root-cause table, target, success criteria, totals)
        is never generated; see reports.py. Keep the "Output contract" in prompts/system.md in sync
        (a test guards this).

JSON keys are camelCase (aliases); Python attributes are snake_case.
"""
from __future__ import annotations

import calendar
import json
import logging
import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic.alias_generators import to_camel

log = logging.getLogger(__name__)


def _normalise_state(v: Any) -> Any:
    """'At Risk', 'AT_RISK' and 'Unknown' are read as 'at-risk' and 'unknown'."""
    return v.strip().lower().replace("_", "-").replace(" ", "-") if isinstance(v, str) else v


# "unknown" = the notebook could not calculate the metric (required data is missing); there is nothing to diagnose
HealthState = Annotated[Literal["healthy", "at-risk", "critical", "unknown"], BeforeValidator(_normalise_state)]


def _null_means_unknown(v: Any) -> Any:
    """A metric whose mandatory data is missing has no health state at all: null (or blank) is read as 'unknown'."""
    return "unknown" if v is None or (isinstance(v, str) and not v.strip()) else _normalise_state(v)


# For the metric itself: the same four states, and null means unknown. (A forecast horizon keeps HealthState: null stays null.)
MetricHealthState = Annotated[Literal["healthy", "at-risk", "critical", "unknown"], BeforeValidator(_null_means_unknown)]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ───────────────────────────── INPUT ─────────────────────────────
# The standard metric JSON written by every notebook. Undeclared TOP-LEVEL fields are dropped (allow-list), so raw
# records can never reach the LLM; ignored_fields() lets the orchestrator warn about them. dataQuality and
# modelAccuracy are passed through as they are, because their inner shape belongs to the notebooks.
# generatedAt and module are read but not sent to the LLM (module goes in as a tag, generatedAt would only break caching).


class TrendLevel(_Model):
    granularity: str  # "quarterly" | "monthly"
    periods: list["TrendPeriod"] = []


class TrendPeriod(_Model):
    model_config = ConfigDict(extra="allow")  # year / quarter / month numbers are ignored
    period: str  # "2025" | "2025-Q3" | "2025-09"
    average: float | None = None
    is_partial: bool = False
    children: TrendLevel | None = None


TrendPeriod.model_rebuild()


class TrendAnalysis(_Model):
    model_config = ConfigDict(extra="allow")
    direction: Literal["up", "down", "stable"] | None = None
    granularity: str = "yearly"
    periods: list[TrendPeriod] = []

    @field_validator("direction", mode="before")
    @classmethod
    def _flat_means_stable(cls, v: Any) -> Any:
        s = v.strip().lower() if isinstance(v, str) else v
        return "stable" if s == "flat" else s

    def compact(self, data_period: tuple[date | None, date | None] | None = None) -> dict[str, Any]:
        """The nested year > quarter > month tree as three short lists for the prompt: periods with no average are
        left out and `partial: true` marks incomplete periods. A period is also marked partial when the data period
        (first and last day of the data) starts inside it or ends inside it, whatever the notebook flagged. The website
        keeps using the original nested JSON."""
        lists: dict[str, list[dict[str, Any]]] = {}

        def incomplete(p: TrendPeriod) -> bool:
            """Incomplete: the notebook says so, or the data cuts the period, or a period inside it is incomplete or has no data
            (a quarter with an empty month is not a whole quarter, whatever the notebook flagged on the quarter itself)."""
            if p.is_partial or _cut_by_the_data(p.period, data_period):
                return True
            return bool(p.children) and any(c.average is None or incomplete(c) for c in p.children.periods)

        def walk(granularity: str, periods: list[TrendPeriod]) -> None:
            for p in periods:
                if p.average is not None:
                    entry: dict[str, Any] = {"period": p.period, "average": p.average}
                    if incomplete(p):
                        entry["partial"] = True
                    lists.setdefault(granularity, []).append(entry)
                if p.children:
                    walk(p.children.granularity, p.children.periods)

        walk(self.granularity, self.periods)
        out: dict[str, Any] = {} if self.direction is None else {"direction": self.direction}
        # The comparisons are taken from the full history, then the older quarters and months are left out of the lists:
        # the model describes the trend only with the comparisons, so this saves prompt size without changing the report.
        comparisons = _equal_period_comparisons(lists)
        out.update({level: entries[-PROMPT_WINDOW[level]:] if level in PROMPT_WINDOW else entries for level, entries in lists.items()})
        out["equalPeriodComparisons"] = comparisons
        return out


# How many of the most recent entries of each list go to the model (yearly is always complete).
PROMPT_WINDOW = {"quarterly": 8, "monthly": 12}


def _period_bounds(period: str) -> tuple[date, date] | None:
    """First and last day of '2025', '2025-Q3' or '2025-09'."""
    if m := re.fullmatch(r"(\d{4})", period):
        y = int(m.group(1))
        return date(y, 1, 1), date(y, 12, 31)
    if m := re.fullmatch(r"(\d{4})-Q([1-4])", period):
        y, q = int(m.group(1)), int(m.group(2))
        last = 3 * q
        return date(y, last - 2, 1), date(y, last, calendar.monthrange(y, last)[1])
    if m := re.fullmatch(r"(\d{4})-(\d{2})", period):
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return date(y, mo, 1), date(y, mo, calendar.monthrange(y, mo)[1])
    return None


def _cut_by_the_data(period: str, data_period: tuple[date | None, date | None] | None) -> bool:
    """True when the data starts after the period began or ends before it is over (so the average covers only part of it)."""
    bounds = _period_bounds(period)
    if not data_period or not bounds:
        return False
    first, last = data_period
    start, end = bounds
    if (last and last < start) or (first and first > end):
        return False  # the period lies outside the data altogether
    return bool((first and first > start) or (last and last < end))


def _equal_period_comparisons(lists: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Pairs of the SAME period one year apart (a year with the next year, a quarter with the same quarter a year later),
    taken only when both periods are complete. Chosen by code so the model never has to decide which periods may be
    compared; the averages are copied as given, no differences are calculated."""
    full = {
        level: {e["period"]: e["average"] for e in lists.get(level, []) if not e.get("partial")}
        for level in ("yearly", "quarterly")
    }
    pairs: list[dict[str, Any]] = []
    for period in sorted(full["yearly"]):
        later = str(int(period) + 1) if period.isdigit() else None
        if later in full["yearly"]:
            pairs.append(_pair(period, full["yearly"][period], later, full["yearly"][later]))
    for period in sorted(full["quarterly"]):
        m = re.fullmatch(r"(\d{4})-Q([1-4])", period)
        later = f"{int(m.group(1)) + 1}-Q{m.group(2)}" if m else None
        if later in full["quarterly"]:
            pairs.append(_pair(period, full["quarterly"][period], later, full["quarterly"][later]))
    return pairs


def _pair(earlier: str, earlier_avg: float, later: str, later_avg: float) -> dict[str, Any]:
    return {"earlierPeriod": earlier, "earlierAverage": earlier_avg, "laterPeriod": later, "laterAverage": later_avg}


_MISSING_WORDS = {"", "nan", "n/a", "na", "null", "none", "-"}


class ForecastPoint(_Model):
    """One forecast horizon. The three numbers must be present, so that a renamed field is noticed and not silently read as
    "no forecast"; but a notebook that could not calculate the horizon may send null, NaN or a word such as "N/A" for them:
    those count as missing."""

    period: str | None = None
    predicted_value: float | None
    lower_bound: float | None
    upper_bound: float | None
    predicted_health_state: HealthState | None = None

    @field_validator("predicted_value", "lower_bound", "upper_bound", "predicted_health_state", mode="before")
    @classmethod
    def _empty_means_missing(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip().lower() in _MISSING_WORDS:
            return None
        if isinstance(v, float) and v != v:  # NaN
            return None
        return v


class Forecast(_Model):
    applicable: bool | None = None  # false: the notebook did not perform it (essential data is missing)
    status: str | None = None
    message: str | None = None
    next_month: ForecastPoint | None = None
    next_quarter: ForecastPoint | None = None
    next_year: ForecastPoint | None = None


class Variance(_Model):
    value: float | None = None  # null when the metric could not be calculated
    percentage: float | None = None


class Factor(_Model):
    """One root-cause factor. No segment = a stage/step of the process (avgFactorValue is its average duration);
    with a segment = an attribute value (segmentAvgValue is the metric's average for that segment)."""

    model_config = ConfigDict(extra="allow")
    rank: int | None = None
    factor_name: str
    segment: str | None = None
    avg_factor_value: float | None = None
    segment_avg_value: float | None = None
    impact_value: float  # part of the breach attributed to this factor, in the metric's unit
    impact_pct: float | None = None  # its share of the breach


class RootCauseAnalysis(_Model):
    model_config = ConfigDict(extra="allow")
    applicable: bool = True
    breach_value: float | None = None
    factors: list[Factor] = []  # the notebooks send the top 3


_NEVER_NEGATIVE_UNITS = {"day", "days", "hour", "hours", "minute", "minutes", "week", "weeks", "percent", "%", "count"}
FORECAST_NOT_USABLE = "The forecast gives negative values, which are impossible for this metric, so it is not used."
FORECAST_EMPTY = "The forecast has no values, so it is not used."


def round_floats(node: Any, digits: int = 2) -> Any:
    """Rounds every decimal number in a JSON value (whole numbers, text and dates are left alone)."""
    if isinstance(node, float):
        return round(node, digits)
    if isinstance(node, list):
        return [round_floats(v, digits) for v in node]
    if isinstance(node, dict):
        return {k: round_floats(v, digits) for k, v in node.items()}
    return node


class MetricInsight(_Model):
    generated_at: str | None = None
    report_version: str | None = None  # the notebooks' format version; read, never sent to the model
    module: str | None = None
    metric_name: str = Field(min_length=1)  # a readable name, for example "Full & Final Settlement Timeliness"
    unit: str | None = None
    higher_is_better: bool | None = None
    company_value: float | None = None  # null when the metric could not be calculated
    industry_standard_value: float | str | None = None  # a number, or text such as "Against statutory/company SLA"
    health_state: MetricHealthState  # the key must be there; null means unknown
    variance: Variance = Field(default_factory=Variance)
    trend_analysis: TrendAnalysis = Field(default_factory=TrendAnalysis)
    forecast: Forecast | None = None
    rca: RootCauseAnalysis = Field(default_factory=lambda: RootCauseAnalysis(applicable=False))
    data_quality: dict[str, Any] | None = None  # checks on completeness and stale records
    # accuracy of the RCA and forecast models; the notebooks call it selectedTrainingModel, older files modelAccuracy
    model_accuracy: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("modelAccuracy", "selectedTrainingModel", "model_accuracy"))
    missing_configurations: list[str] | dict[str, list[str]] = []  # columns that are empty: a list, or groups (mandatoryFieldsMissing / otherFieldsMissing)

    @model_validator(mode="before")
    @classmethod
    def _null_objects_mean_nothing(cls, data: Any) -> Any:
        """When the metric could not be calculated the notebook writes null for whole blocks (trendAnalysis, ...): no block."""
        if isinstance(data, dict):
            blocks = {"trendAnalysis", "trend_analysis", "variance", "rca", "missingConfigurations", "missing_configurations"}
            return {k: v for k, v in data.items() if not (v is None and k in blocks)}
        return data

    def missing_fields(self) -> list[str]:
        """Every empty column, whether the notebook sent a plain list or groups."""
        if isinstance(self.missing_configurations, dict):
            return [name for names in self.missing_configurations.values() for name in names]
        return list(self.missing_configurations)

    def mandatory_missing_fields(self) -> list[str]:
        """The fields the metric NEEDS in order to be calculated: the groups whose name says mandatory (mandatoryFieldsMissing).
        A plain list does not say which fields are mandatory, so it gives none."""
        if not isinstance(self.missing_configurations, dict):
            return []
        return [name for group, names in self.missing_configurations.items() if "mandatory" in group.lower() for name in names]

    @model_validator(mode="after")
    def _a_breach_needs_a_value(self) -> "MetricInsight":
        if self.health_state in ("at-risk", "critical") and self.company_value is None:
            raise ValueError("companyValue is required when healthState is at-risk or critical")
        return self

    def _data_period(self) -> tuple[date | None, date | None] | None:
        period = (self.data_quality or {}).get("dataPeriod")
        if not isinstance(period, dict):
            return None

        def day(value: Any) -> date | None:
            try:
                return date.fromisoformat(str(value)[:10])
            except ValueError:
                return None

        first, last = day(period.get("from")), day(period.get("to"))
        return (first, last) if first or last else None

    def _forecast_is_impossible(self) -> bool:
        """A duration, a count or a percentage cannot be negative: such a forecast is the model failing, not a prediction."""
        if not self.forecast or (self.unit or "").strip().lower() not in _NEVER_NEGATIVE_UNITS:
            return False
        points = (self.forecast.next_month, self.forecast.next_quarter, self.forecast.next_year)
        return any(v < 0 for p in points if p for v in (p.predicted_value, p.lower_bound, p.upper_bound) if v is not None)

    @staticmethod
    def _horizon_is_complete(point: Any) -> bool:
        return isinstance(point, dict) and {"predictedValue", "lowerBound", "upperBound"} <= point.keys()

    def _tidy_forecast(self, data: dict[str, Any]) -> None:
        """The model is given only the horizons that have their value and both bounds. If the notebook sent a forecast but
        nothing in it is usable, a note says so; if it sent no forecast at all, there is simply none."""
        forecast = data.get("forecast")
        if forecast is None:
            return
        if self.forecast is not None and self.forecast.applicable is False:  # the notebook says why in its own words
            data["forecast"] = {"notUsable": self.forecast.message or FORECAST_EMPTY}
        elif self._forecast_is_impossible():
            data["forecast"] = {"notUsable": FORECAST_NOT_USABLE}
        elif usable := {name: point for name, point in forecast.items() if self._horizon_is_complete(point)}:
            data["forecast"] = usable
        elif any(isinstance(point, dict) for point in forecast.values()):  # a horizon was sent, but nothing in it is usable
            data["forecast"] = {"notUsable": FORECAST_EMPTY}
        else:
            del data["forecast"]

    @staticmethod
    def _tidy_data_quality(data: dict[str, Any], keep_passed_checks: bool) -> dict[str, Any]:
        """Empty values are left out (the instructions treat an absent value and a null the same way). For a metric with a
        breach, checks that found nothing are left out too: the instructions say they are not a finding. A healthy metric's
        summary reports them ("found no problems"), so they stay there."""
        quality = data.get("dataQuality")
        if not isinstance(quality, dict):
            return data
        quality = {k: v for k, v in quality.items() if v is not None}
        checks = quality.get("checks")
        if isinstance(checks, list):
            kept = [c for c in checks if keep_passed_checks or not (isinstance(c, dict) and c.get("failedRecords") == 0)]
            quality["checks"] = [{k: v for k, v in c.items() if v is not None} if isinstance(c, dict) else c for c in kept]
        return {**data, "dataQuality": quality}

    def for_prompt(self, summary: bool = False, setup: bool = False) -> dict[str, Any]:
        """What the model is given. `summary=True` is for a healthy metric: there is no breach, so the root-cause
        factors (and the accuracy of the model behind them) are left out. `setup=True` is for a metric that could not be
        calculated because mandatory fields are missing: nothing was calculated, so only the identity of the metric, the
        missing fields and the data checks are given. Numbers are rounded to 2 decimals, so the text quotes "44.28" and
        not "44.283266678292"."""
        if setup:
            keep = {"metric_name", "unit", "higher_is_better", "health_state", "missing_configurations", "data_quality"}
            data = self.model_dump(by_alias=True, exclude_none=True, mode="json", include=keep)
            return round_floats(self._tidy_data_quality(data, keep_passed_checks=False))
        exclude = {"generated_at", "report_version", "module", "trend_analysis"} | ({"rca"} if summary else set())
        data = self.model_dump(by_alias=True, exclude_none=True, mode="json", exclude=exclude)
        data["trendAnalysis"] = self.trend_analysis.compact(self._data_period())
        if not summary:
            # A diagnosis describes the trend only with the equal-period comparisons (and the direction); the quarterly and monthly
            # series are never quoted, so sending them only costs input tokens. A summary still quotes the yearly averages.
            for series in ("quarterly", "monthly"):
                data["trendAnalysis"].pop(series, None)
        self._tidy_forecast(data)
        data.pop("modelAccuracy", None)  # which model was used and how accurate it is does not change the report
        data = self._tidy_data_quality(data, keep_passed_checks=summary)
        return round_floats(data)


def ignored_fields(payload: Any) -> list[str]:
    """Top-level keys in the notebook JSON that MetricInsight does not declare (and so never reach the LLM)."""
    if not isinstance(payload, dict):
        return []
    known: set[str] = set()
    for name, f in MetricInsight.model_fields.items():
        known.add(f.alias or name)
        if isinstance(f.validation_alias, AliasChoices):
            known.update(choice for choice in f.validation_alias.choices if isinstance(choice, str))
    return sorted(set(payload) - known)


# ───────────────────────────── OUTPUT (written by the LLM) ─────────────────────────────

PhaseKey = Literal["architecture", "configuration", "rollout"]
RoleKey = Literal["consultant", "processOwner", "qaUat"]


# The diagnosis is a few short points, not a paragraph, and it is light on numbers: the page shows the exact values anyway.
# The prompt asks for at most 25 words per point; the limit enforced here leaves a margin of 5 words. The prompt also asks for
# at most 2 numbers in all, but that is only a request: a good answer is never thrown away for its numbers, the log just notes it.
MAX_WORDS_POINT, NUMBERS_ASKED_FOR = 30, 2
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


class DiagnosisText(_Model):
    headline: str = Field(min_length=10)
    narrative: list[str] = Field(min_length=2, max_length=5)

    @field_validator("narrative")
    @classmethod
    def _points_are_short_and_light_on_numbers(cls, v: list[str]) -> list[str]:
        for point in v:
            if len(point.split()) < 4:
                raise ValueError("each point must be a short sentence of at least 4 words")
            _short(point, MAX_WORDS_POINT)
        numbers = sum(len(_NUMBER.findall(point)) for point in v)
        if numbers > NUMBERS_ASKED_FOR:
            log.warning("accepted: the diagnosis points contain %d numbers, the prompt asks for at most %d", numbers, NUMBERS_ASKED_FOR)
        return v


class BusinessImpact(_Model):
    overview: str = Field(min_length=10)
    # A few points: the first says the impact cannot be quantified from the data, the others say what it MAY involve.
    # (The earlier name financialExposure, and a single sentence, are still read.)
    financial_impact: list[str] = Field(
        min_length=1, max_length=5, validation_alias=AliasChoices("financialImpact", "financialExposure", "financial_impact")
    )
    sla_and_turnaround: str = Field(min_length=10)
    governance_and_audit: str = Field(min_length=10)

    @field_validator("financial_impact", mode="before")
    @classmethod
    def _one_sentence_is_one_point(cls, v: Any) -> Any:
        return [v] if isinstance(v, str) else v

    @field_validator("financial_impact")
    @classmethod
    def _points_are_short(cls, v: list[str]) -> list[str]:
        for point in v:
            if len(point.split()) < 4:
                raise ValueError("each point must be a short sentence of at least 4 words")
            _short(point, MAX_WORDS_POINT)
        return v


def _short(text: str, limit: int) -> str:
    words = len(text.split())
    if words > limit:
        raise ValueError(f"too long: {words} words, the limit is {limit}. Shorten it")
    return text


class Workstream(_Model):
    id: str = Field(pattern=r"^W\d+$")
    step: str = Field(min_length=10)
    kind: Literal["factor", "data"] = "factor"  # "data" = addresses a data finding (failed check, empty field), not a factor
    fixes_factors: list[str] = []


def _clamp(v: Any, low: int, high: int) -> Any:
    """A number outside the allowed range is brought to the nearest limit (a plan that starts in week 13 is not worth another model
    call); anything that is not a number is left for the normal validation."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
        return int(min(max(round(v), low), high))
    return v


class Activity(_Model):
    phase: PhaseKey
    activity: str = Field(min_length=5)
    role: RoleKey
    workstream: str | None = None
    week: int = Field(ge=1, le=12)  # the prompt says 1 to 12; a value outside is brought to the limit
    hours: int = Field(ge=1, le=40)

    @field_validator("week", mode="before")
    @classmethod
    def _week_within_the_plan(cls, v: Any) -> Any:
        return _clamp(v, 1, 12)

    @field_validator("hours", mode="before")
    @classmethod
    def _hours_within_the_limit(cls, v: Any) -> Any:
        return _clamp(v, 1, 40)

    @field_validator("workstream", mode="before")
    @classmethod
    def _dash_means_none(cls, v: Any) -> Any:
        return None if isinstance(v, str) and v.strip() in {"", "-", "none", "null"} else v


class RiskRow(_Model):
    type: Literal["Assumption", "Risk"]
    description: str = Field(min_length=10)
    mitigation: str = Field(min_length=5)


class BrdDraft(_Model):
    diagnosis: DiagnosisText
    business_impact: BusinessImpact
    workstreams: list[Workstream] = Field(min_length=1)
    activities: list[Activity] = Field(min_length=3)
    assumptions_and_risks: list[RiskRow] = Field(default_factory=list)  # the data findings are added by code (brd.data_risk_rows)


# The summary of a healthy metric: one or two paragraphs. The prompt asks for about 100 to 150 words each; these are the
# hard limits, wide enough that a metric with little data still passes with a shorter paragraph.
MIN_WORDS_PARAGRAPH, MAX_WORDS_PARAGRAPH = 50, 200


class HealthySummary(_Model):
    summary: list[str] = Field(min_length=1, max_length=2)

    @field_validator("summary")
    @classmethod
    def _paragraph_lengths(cls, v: list[str]) -> list[str]:
        for paragraph in v:
            n = len(paragraph.split())
            if n < MIN_WORDS_PARAGRAPH:
                raise ValueError(f"a paragraph has {n} words, the minimum is {MIN_WORDS_PARAGRAPH}")
            if n > MAX_WORDS_PARAGRAPH:
                raise ValueError(f"a paragraph has {n} words, the limit is {MAX_WORDS_PARAGRAPH}. Shorten it")
        return v


# ───────────────────────── parsing helpers ─────────────────────────


class ReportError(ValueError):
    """The model's answer was not usable. The message is safe to send back to the model."""


def format_errors(err: ValidationError, limit: int = 4) -> str:
    """Location + message only: pydantic's default text would echo (possibly long) input values."""
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()[:limit])


def extract_json(text: str) -> Any:
    """Tolerates ```json fences and stray prose around the object."""
    t = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else t
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(candidate[start : end + 1])


# Models often emit non-breaking hyphens and spaces, which can show as boxes in some fonts and PDFs.
_PLAIN = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u200b": None})


# The instructions use this phrase internally; if a model repeats it, it is swapped for plain wording instead of failing the report.
_INTERNAL_PHRASE = re.compile(r"equal[ -]?period[ -]?comparison(s?)", re.IGNORECASE)


def clean_text(node: Any) -> Any:
    """Replaces special hyphens and spaces by plain ones, and an internal phrase by plain wording, in every string of a parsed JSON value."""
    if isinstance(node, str):
        return _INTERNAL_PHRASE.sub(r"same-period comparison\1", node.translate(_PLAIN))
    if isinstance(node, list):
        return [clean_text(v) for v in node]
    if isinstance(node, dict):
        return {k: clean_text(v) for k, v in node.items()}
    return node


def _parse(text: str, model: type[BaseModel]) -> Any:
    try:
        obj = clean_text(extract_json(text))
    except json.JSONDecodeError:
        raise ReportError("the reply was not valid JSON") from None
    try:
        return model.model_validate(obj)
    except ValidationError as err:
        raise ReportError(f"the JSON did not match the required structure: {format_errors(err)}") from None


def parse_draft(text: str) -> BrdDraft:
    return _parse(text, BrdDraft)


def parse_summary(text: str) -> HealthySummary:
    return _parse(text, HealthySummary)