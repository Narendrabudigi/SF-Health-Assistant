"""From one ML insight to one finished report: the glossary, the checks and completion of the model's draft, and the run itself.

1. Glossary: plain-words labels for field names that contain abbreviations. The notebooks send names in code style
   (`appExpCtc`, `noOfPositionsFilled`); the model rewrites them in business words, and with an abbreviation it can guess wrong
   (`appExpCtc` came out as "applicant expected contact"). So code decides the wording for the names it knows and hands it to
   the model in a <glossary> block. To teach the program a new abbreviation, edit FIELDS or TOKENS below:
   - FIELDS: a whole field name and its label (use it when the name is ambiguous, for example `app` could mean applicant or application).
   - TOKENS: a short part of a name that has only one meaning. It is expanded wherever it appears in a name.
2. Draft to report: everything around the model's draft that must NOT be left to the model.
   - build_factors: root-cause factors lifted from the ML JSON (rca.factors), with stable IDs (F1, F2, ...).
   - role_names / PHASES / PHASES_SETUP: fixed staffing roles and phase wording, so every module's BRD looks the same.
   - build_report: validates the draft (no internal wording, valid IDs, full traceability) and adds the totals (hours per phase and
     role, total hours, duration in weeks) by code. Failures raise ReportError, whose message is sent back to the model so it can correct itself.
   Not produced here, on purpose: snapshot, trend, root-cause table, target outcome and success criteria. The website renders those
   straight from the ML JSON.
3. The run: for every insight of the run date, build the prompt, ask the model, check the answer and save the report.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from typing import Any, Callable, Iterable, Iterator, Protocol

from pydantic import ValidationError

from . import dashboard
from .llm import LlmResult
from .schemas import BrdDraft, MetricInsight, ReportError, format_errors, ignored_fields, parse_draft, parse_summary, round_floats
from .store import InsightRecord, ReportRecord, Store

log = logging.getLogger(__name__)

# ── 1. the glossary ──

# Whole field names (compared without case, underscores or hyphens) -> plain-words label.
FIELDS: dict[str, str] = {
    "appExpCtc": "applicant expected CTC",
    # Knowledge transfer (offboarding)
    "ktRequiredFlag": "knowledge transfer required flag",
    "ktScheduledDate": "knowledge transfer scheduled date",
    "ktActualCompletionDate": "knowledge transfer actual completion date",
    "ktDocumentAndDeliverablesTracking": "knowledge transfer documents and deliverables tracking",
    "ktRecipientSuccessorEmpId": "knowledge transfer recipient (successor) employee ID",
}

# Parts of a name -> plain words. Only parts with a single, certain meaning belong here.
TOKENS: dict[str, str] = {
    "exp": "expected",
    "ctc": "CTC",
    "req": "requisition",
    "emp": "employee",
    "id": "ID",
    "mgr": "manager",
    "dept": "department",
    "pct": "percentage",
    "avg": "average",
    "kt": "knowledge transfer",
}

_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_{1,2}[A-Za-z0-9]+)*$")


def _key(name: str) -> str:
    return re.sub(r"[_\-\s]", "", name).lower()


def label_for(name: str) -> str | None:
    """The plain-words label of a field name, or None when the program knows nothing about its parts (the model then
    rewrites it itself and is told not to guess abbreviations)."""
    whole = {_key(k): v for k, v in FIELDS.items()}
    if _key(name) in whole:
        return whole[_key(name)]
    parts = [p.lower() for p in _PARTS.findall(name.replace("_", " "))]
    words: list[str] = []
    known = False
    i = 0
    while i < len(parts):
        if parts[i] == "no" and i + 1 < len(parts) and parts[i + 1] == "of":  # noOfPositionsFilled -> number of positions filled
            words.append("number")
            known = True
        elif parts[i] in TOKENS:
            words.append(TOKENS[parts[i]])
            known = True
        else:
            words.append(parts[i])
        i += 1
    return " ".join(words) if known else None


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def _check_names(data: Any) -> Iterator[str]:
    quality = data.get("dataQuality") if isinstance(data, dict) else None
    for check in (quality.get("checks") if isinstance(quality, dict) else None) or []:
        if isinstance(check, dict) and isinstance(check.get("checkName"), str):
            yield check["checkName"]


def _words(name: str) -> str:
    return " ".join(p.lower() for p in _PARTS.findall(name.replace("_", " ")))


def plain_label(name: str) -> str:
    """The plain words for ANY code-style name: the label the program knows, else the name split into its words
    (`offboardingCompletionDate` becomes "offboarding completion date"). An abbreviation the program does not know stays as it is."""
    return label_for(name) or _words(name)


def glossary_for(data: Any) -> dict[str, str]:
    """name -> label for every code-style name (camelCase, PascalCase or snake_case) that appears in the data given to the model:
    the metric, the columns, the data checks and the factors. The label is the one the program knows, else the name split into its
    words in lower case; the model then never needs to rewrite a name itself, and the program uses the same label when it replaces
    a name the model copied by mistake."""
    found: dict[str, str] = {}
    for name in _check_names(data):
        if re.search(r"[a-z][A-Z]|_", name):
            found[name] = plain_label(name)
    for text in _strings(data):
        if _NAME.match(text) and re.search(r"[a-z][A-Z]|_", text) and text not in found:
            found[text] = plain_label(text)
    return dict(sorted(found.items()))


def glossary_block(labels: dict[str, str]) -> list[str]:
    """The lines of the <glossary> block (empty when there is nothing to say)."""
    if not labels:
        return []
    return ["<glossary>", *(f"{name} = {label}" for name, label in labels.items()), "</glossary>"]


# ── 2. from the model's draft to the finished report ──

# module code -> (SuccessFactors area, business function). One place to edit role names.
MODULES: dict[str, tuple[str, str]] = {
    "RCM": ("Recruiting", "Talent Acquisition"),
    "ONB2": ("Onboarding", "HR"),
    "OFB2": ("Offboarding", "HR"),
    "EC": ("Employee Central", "HR"),
    "ECP": ("Employee Central Payroll", "Payroll"),
}

# key used by the LLM, title, milestone, deliverable (fixed wording, same for every metric)
PHASES: tuple[tuple[str, str, str, str], ...] = (
    ("architecture", "Phase 1: Architecture", "Root Cause Validation & BRD Sign-Off", "Approved BRD & Architecture Specification"),
    ("configuration", "Phase 2: Configuration", "Rule Build & Staging Environment Test", "Configuration & UAT Sign-Off"),
    ("rollout", "Phase 3: Rollout", "Production Cutover & Exception Monitoring", "Weekly Health Monitoring Report"),
)

# A setup plan (a metric that could not be calculated) is about getting fields ready, not about validating a root cause.
PHASES_SETUP: tuple[tuple[str, str, str, str], ...] = (
    ("architecture", "Phase 1: Architecture", "Field Requirements & BRD Sign-Off", "Approved Field Requirements & Setup Specification"),
    ("configuration", "Phase 2: Configuration", "Field Setup & Staging Environment Test", "Configuration & UAT Sign-Off"),
    ("rollout", "Phase 3: Rollout", "Production Cutover & Metric Calculation", "First Calculated Health Report"),
)

ROLE_ORDER = ("consultant", "processOwner", "qaUat")


def role_names(module: str) -> dict[str, str]:
    area, function = MODULES.get(module.upper(), ("", "HR"))
    return {
        "consultant": f"SAP SuccessFactors {area} Lead Functional Consultant".replace("  ", " "),
        "processOwner": f"{function} Operations & Process Governance Lead",
        "qaUat": "Quality Assurance & UAT Specialist",
    }


def build_factors(insight: MetricInsight) -> list[dict[str, Any]]:
    """Root-cause factors lifted from rca.factors, in the notebook's rank order. The code only adds the ids
    (F1, F2, ...) and, if the notebook left it out, impactPct. Empty when the notebook says RCA is not applicable."""
    rca = insight.rca
    if not rca.applicable:
        return []
    ordered = sorted(rca.factors, key=lambda f: (f.rank if f.rank is not None else 10**6, -abs(f.impact_value)))
    breach = rca.breach_value if rca.breach_value is not None else insight.variance.value
    factors: list[dict[str, Any]] = []
    for i, f in enumerate(ordered, start=1):
        dumped = f.model_dump(by_alias=True, exclude_none=True, mode="json")
        item: dict[str, Any] = {"id": f"F{i}"}
        item.update({k: v for k, v in dumped.items() if k != "id"})
        if "impactPct" not in item and breach:
            item["impactPct"] = round(f.impact_value / breach * 100, 1)
        factors.append(item)
    return factors


# ───────────────────────────── validation ─────────────────────────────

# "trend analysis" and "root cause analysis" are ordinary business terms (the BRD itself has sections of those names), so only
# the field-name forms (trendAnalysis, rootCauseAnalysis) are caught, by _CAMEL_CASE below.
_INTERNAL_TERMS = re.compile(r"ml[ _-]?insights?|ml analysis|\bjson\b|\bpayload\b|equal[ -]?period[ -]?comparisons?", re.IGNORECASE)
# The input ranks only the root-cause factors (rank 1 = largest contributor). Anything else must not be ranked.
_SUPERLATIVES = re.compile(r"\b(longest|slowest|highest|lowest|fastest|shortest|worst)\b", re.IGNORECASE)
_CAMEL_CASE = re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b")  # e.g. hiringManagerEmployeeId
_UPPER_SNAKE = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")  # e.g. INTERVIEW_DATE
_CODE_STYLE = re.compile(r"[a-z][A-Z]|_")  # PascalCase / camelCase / snake_case names, not plain words like "Source"


def _internal_names(insight: MetricInsight) -> set[str]:
    """Code-style names from THIS insight (factor, segment, metric, column, check and model names) that must be rewritten in
    plain words. Plain single words such as "Department" are not included, so normal prose is never flagged."""
    names: set[str] = {insight.metric_name, *insight.missing_fields()}
    for f in insight.rca.factors:
        names.add(f.factor_name)
        names.add(f.segment or "")  # segment values can be code style too, for example DataEngineer
    for check in (insight.data_quality or {}).get("checks") or []:
        if isinstance(check, dict):
            names.add(str(check.get("checkName", "")))
            names.update(str(c) for c in check.get("affectedColumns") or [])
    for model in (insight.model_accuracy or {}).values():
        if isinstance(model, dict):
            names.add(str(model.get("modelName", "")))
    return {n for n in names if n and _CODE_STYLE.search(n)}


def _labels(insight: MetricInsight, names: set[str]) -> dict[str, str]:
    """name -> plain words. An algorithm name maps to itself: it is never to be written at all, so it is left in the text
    for the wording check to reject (the model is then asked once more)."""
    algorithms = {str(m.get("modelName", "")) for m in (insight.model_accuracy or {}).values() if isinstance(m, dict)}
    return {name: name if name in algorithms else plain_label(name) for name in names}


# Role keys of the plan; the model sometimes writes them in a sentence. ("consultant" is an ordinary word and needs no help.)
_ROLE_KEY_WORDS = {"qaUat": "quality assurance and UAT", "processOwner": "process owner"}
_CURRENCY = re.compile(r"[$€£₹]|\b(?:USD|EUR|GBP|INR)\b|\b(?:dollars?|euros?|pounds sterling|rupees?)\b", re.IGNORECASE)


def _plain(text: str, labels: dict[str, str]) -> str:
    """Code-style names that the model copied into a sentence are replaced by plain words, so the report is not rejected (and the
    model not asked again) for it: first the names of this insight, with the same labels the model was given in the glossary, then
    the role keys, then any other camelCase or UPPER_SNAKE word, split into its words."""
    for name in sorted(labels, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(name)}\b", lambda _m, v=labels[name]: v, text)
    text = _CAMEL_CASE.sub(lambda m: m.group(0) if labels.get(m.group(0)) == m.group(0) else _ROLE_KEY_WORDS.get(m.group(0)) or _words(m.group(0)), text)
    return _UPPER_SNAKE.sub(lambda m: _words(m.group(0)), text)


def _plain_draft(draft: BrdDraft, labels: dict[str, str]) -> None:

    def fix(text: str) -> str:
        return _plain(text, labels)

    draft.diagnosis.headline = fix(draft.diagnosis.headline)
    draft.diagnosis.narrative = [fix(p) for p in draft.diagnosis.narrative]
    impact = draft.business_impact
    impact.overview = fix(impact.overview)
    impact.financial_impact = [fix(p) for p in impact.financial_impact]
    impact.sla_and_turnaround = fix(impact.sla_and_turnaround)
    impact.governance_and_audit = fix(impact.governance_and_audit)
    for w in draft.workstreams:
        w.step = fix(w.step)
    for a in draft.activities:
        a.activity = fix(a.activity)
    for r in draft.assumptions_and_risks:
        r.description, r.mitigation = fix(r.description), fix(r.mitigation)


def _drop_idle_workstreams(draft: BrdDraft) -> None:
    """A workstream without any activity has no work, no hours and no week: it is dropped when every root-cause factor it fixes is
    also fixed by a workstream that has activities (so nothing is lost), and the rest are renumbered W1, W2, ... A workstream that
    is the only one to fix a factor stays, and the report is then sent back."""
    used = {a.workstream for a in draft.activities if a.workstream}
    kept = [w for w in draft.workstreams if w.id in used]
    idle = [w for w in draft.workstreams if w.id not in used]
    if not idle or not kept:
        return
    covered = {f for w in kept for f in w.fixes_factors}
    dropped = {w.id for w in idle if set(w.fixes_factors) <= covered}
    if not dropped:
        return
    remaining = [w for w in draft.workstreams if w.id not in dropped]
    new_ids = {w.id: f"W{i}" for i, w in enumerate(remaining, start=1)}
    log.info("Left out %d workstream(s) without any activity: %s", len(dropped), ", ".join(sorted(dropped)))
    for w in remaining:
        w.id = new_ids[w.id]
    for a in draft.activities:
        if a.workstream:
            a.workstream = new_ids.get(a.workstream, a.workstream)
    draft.workstreams = remaining


def _free_text(draft: BrdDraft) -> Iterator[str]:
    """Only the sentences a reader sees; ids, phase keys and role keys are not prose."""
    yield draft.diagnosis.headline
    yield from draft.diagnosis.narrative
    yield from (
        draft.business_impact.overview,
        *draft.business_impact.financial_impact,
        draft.business_impact.sla_and_turnaround,
        draft.business_impact.governance_and_audit,
    )
    yield from (w.step for w in draft.workstreams)
    yield from (a.activity for a in draft.activities)
    for r in draft.assumptions_and_risks:
        yield r.description
        yield r.mitigation


def _language_problems(texts: Iterable[str], internal_names: set[str]) -> list[str]:
    """The rules about wording that apply to every sentence a reader sees, in a diagnosis and in a summary alike."""
    problems: list[str] = []
    texts = list(texts)

    # Plain business language only: the reader never sees the analysis, the JSON or field names.
    for text in texts:
        found = _INTERNAL_TERMS.search(text) or _CAMEL_CASE.search(text) or _UPPER_SNAKE.search(text)
        leaked = found.group(0) if found else next((n for n in sorted(internal_names) if re.search(rf"\b{re.escape(n)}\b", text)), None)
        if leaked:
            problems.append(f'the text must not contain internal wording such as "{leaked}"; use plain business language')
            break

    # No rankings that the input does not give.
    for text in texts:
        ranked = _SUPERLATIVES.search(text)
        if ranked:
            problems.append(
                f'the text must not rank items the input does not rank (found "{ranked.group(0)}"); '
                "state the given numbers without superlatives. Only the factor with rank 1 may be called the largest contributor"
            )
            break
    return problems


def _problems(draft: BrdDraft, factor_ids: set[str], internal_names: set[str]) -> list[str]:
    problems: list[str] = _language_problems(_free_text(draft), internal_names)

    # The financial impact may say what a gap could involve, but never an amount: the input has no cost data.
    if any(_CURRENCY.search(p) for p in draft.business_impact.financial_impact):
        problems.append("the financial impact must not contain amounts or currencies: the input has no cost data; word the points as possibilities")

    # 2. Traceability: workstreams fix known factors, every factor is fixed, every workstream has activities.
    ws_ids = [w.id for w in draft.workstreams]
    if len(set(ws_ids)) != len(ws_ids):
        problems.append("workstream ids must be unique")
    covered: set[str] = set()
    for w in draft.workstreams:
        unknown = sorted(set(w.fixes_factors) - factor_ids)
        if unknown:
            problems.append(f"{w.id} refers to unknown factor(s) {', '.join(unknown)}; valid ids are {', '.join(sorted(factor_ids))}")
        if w.kind == "data":
            if w.fixes_factors:
                problems.append(f'{w.id} is a data workstream (kind "data"), so fixesFactors must be empty')
        elif factor_ids and not w.fixes_factors:
            problems.append(f'{w.id} must list at least one factor it fixes, or be a workstream of kind "data" that addresses a data finding')
        covered.update(w.fixes_factors)
    missing = sorted(factor_ids - covered)
    if missing:
        problems.append(f"every factor must be fixed by at least one workstream; not covered: {', '.join(missing)}")

    used = {a.workstream for a in draft.activities if a.workstream}
    bad = sorted(used - set(ws_ids))
    if bad:
        problems.append(f"activities refer to unknown workstream(s) {', '.join(bad)}; use a workstream id or null")
    idle = sorted(set(ws_ids) - used)
    if idle:
        problems.append(f"every workstream needs at least one activity; none for {', '.join(idle)}")

    # 3. All three fixed phases must be used.
    phases_used = {a.phase for a in draft.activities}
    absent = [key for key, *_ in PHASES if key not in phases_used]
    if absent:
        problems.append(f"every phase needs at least one activity; none for {', '.join(absent)}")

    # 4. Testing belongs to the configuration phase (as in the BRD template): staging test and user acceptance testing.
    if "configuration" in phases_used and not any(a.phase == "configuration" and a.role == "qaUat" for a in draft.activities):
        problems.append('the configuration phase needs a staging test or user acceptance testing activity with the role "qaUat"')
    return problems


# ───────────────────────────── data findings, written by code ─────────────────────────────

# Rows with this wording are written by code. A model that still writes one (an older prompt, a habit) is not repeated.
_CODE_WRITTEN = re.compile(r"completely empty in the client's data|also empty in the client's data|failed the check for|metric stays unavailable", re.IGNORECASE)


def _count(value: Any) -> str:
    return str(int(value)) if isinstance(value, (int, float)) and float(value).is_integer() else str(value)


def _fields_text(columns: Iterable[Any]) -> str:
    labels = [plain_label(str(c)) for c in columns]
    return ", ".join(labels[:5]) + (" and other fields" if len(labels) > 5 else "")


def data_risk_rows(insight: MetricInsight, setup: bool = False) -> list[dict[str, str]]:
    """One Risk row for every empty field and every failed data check, in fixed wording (nothing for the model to decide, so
    the model is not asked to write them). A setup plan is about the mandatory fields: only the other empty fields are listed,
    plus the row that says the metric stays unavailable until the mandatory fields are filled."""
    rows: list[dict[str, str]] = []

    def risk(description: str, mitigation: str) -> None:
        rows.append({"type": "Risk", "description": description, "mitigation": mitigation})

    mandatory = set(insight.mandatory_missing_fields()) if setup else set()
    for name in insight.missing_fields():
        if name in mandatory:
            continue
        label = plain_label(name)
        risk(
            f"The {label} field is also empty in the client's data. The metric does not need it, so it does not block the calculation."
            if setup
            else f"The {label} field is completely empty in the client's data, so it was left out of the analysis.",
            "Maintain the field so that future analyses can include it.",
        )

    for check in (insight.data_quality or {}).get("checks") or []:
        if not isinstance(check, dict):
            continue
        failed = check.get("failedRecords")
        if not isinstance(failed, (int, float)) or isinstance(failed, bool) or failed <= 0:
            continue  # a check that found nothing is not a finding
        checked, pct = check.get("checkedRecords"), check.get("failedPct")
        what = plain_label(str(check.get("checkName") or "data quality"))
        if check.get("affectedColumns"):
            what += f" ({_fields_text(check['affectedColumns'])})"
        if checked and pct is not None:
            text = f"{_count(failed)} of {_count(checked)} records ({_count(pct)}%) failed the check for {what}."
        else:
            text = f"{_count(failed)} records failed the check for {what}."
        stale = check.get("staleRange")
        if isinstance(stale, dict) and stale.get("from") and stale.get("to"):
            text += f" The stale records date from {stale['from']} to {stale['to']}."
        elif isinstance(stale, str) and stale.strip():
            text += f" The stale records are {stale.strip()}."
        risk(text + " This may affect the reliability of the analysis.", "Review the affected records and correct them at the source, then run the analysis again.")

    if setup:
        risk("The metric stays unavailable until its mandatory fields are filled.", "Set up the mandatory fields first, then run the analysis again.")
    return rows


# ───────────────────────────── assembly ─────────────────────────────


def _up(text: str) -> str:
    """The models sometimes start a sentence in lower case when they fill in a wording template."""
    return text[:1].upper() + text[1:]


def build_healthy_report(text: str, insight: MetricInsight) -> dict[str, Any]:
    """The report of a healthy metric: one or two paragraphs on how well it is doing. Nothing else is generated."""
    draft = parse_summary(text)
    names = _internal_names(insight)
    labels = _labels(insight, names)
    draft.summary = [_plain(p, labels) for p in draft.summary]
    problems = _language_problems(draft.summary, names)
    if problems:
        raise ReportError("; ".join(problems))
    return {
        "metricName": insight.metric_name,
        "healthState": insight.health_state,
        "moduleOverview": {"summary": [_up(paragraph) for paragraph in draft.summary]},
    }


def build_report(text: str, insight: MetricInsight, factors: list[dict[str, Any]], module: str, setup: bool = False) -> dict[str, Any]:
    """Parse and check the model's answer, then add the code-calculated parts. Returns the report to store."""
    draft = parse_draft(text)
    names = _internal_names(insight)
    _plain_draft(draft, _labels(insight, names))  # a copied name is replaced by plain words, not rejected
    _drop_idle_workstreams(draft)  # a workstream with no work is left out, not rejected
    problems = _problems(draft, {f["id"] for f in factors}, names)
    if problems:
        raise ReportError("; ".join(problems[:5]))

    roles = role_names(module)
    phases: list[dict[str, Any]] = []
    for key, title, milestone, deliverable in (PHASES_SETUP if setup else PHASES):
        acts = sorted((a for a in draft.activities if a.phase == key), key=lambda a: a.week)
        phases.append(
            {
                "phase": key,
                "title": title,
                "milestone": milestone,
                "deliverable": deliverable,
                "hours": sum(a.hours for a in acts),
                "activities": [
                    {"activity": _up(a.activity), "role": roles[a.role], "workstream": a.workstream, "week": a.week, "hours": a.hours}
                    for a in acts
                ],
            }
        )
    role_hours = [
        {"role": roles[k], "hours": sum(a.hours for a in draft.activities if a.role == k)}
        for k in ROLE_ORDER
        if any(a.role == k for a in draft.activities)
    ]

    return {
        # identity, factors and totals come from code, never from the model
        "metricName": insight.metric_name,
        "healthState": insight.health_state,
        "factors": factors,
        "diagnosis": {"headline": _up(draft.diagnosis.headline), "narrative": [_up(point) for point in draft.diagnosis.narrative]},
        "businessImpact": {
            k: [_up(p) for p in v] if isinstance(v, list) else _up(v) for k, v in draft.business_impact.model_dump(by_alias=True).items()
        },
        "workstreams": [{**w.model_dump(by_alias=True), "step": _up(w.step)} for w in draft.workstreams],
        "plan": {
            "phases": phases,
            "roles": role_hours,
            "totalHours": sum(a.hours for a in draft.activities),
            "durationWeeks": max(a.week for a in draft.activities),
        },
        "assumptionsAndRisks": [
            {**r.model_dump(by_alias=True), "description": _up(r.description), "mitigation": _up(r.mitigation)}
            for r in draft.assumptions_and_risks
            if not _CODE_WRITTEN.search(r.description)
        ]
        + data_risk_rows(insight, setup),
    }


# ── 3. the run ──

class LlmGenerator(Protocol):
    async def generate(
        self, system_prompt: str, user_prompt: str, parse: Callable[[str], Any], *, run_key: str = ""
    ) -> LlmResult: ...


@dataclass(frozen=True)
class Prompt:
    text: str
    sha: str  # part of the cache key: editing the prompt regenerates reports


# The prompts are written for the industry standards. For the company's own standards the same text is used, with the wording
# changed by code, so that there is one set of prompt files to maintain. The JSON is the same: `industryStandardValue` then holds
# the custom standard.
CUSTOM_NOTE = (
    "\n\n# Which standard is used\n\n"
    "In this report the standard is NOT an industry benchmark. It is the custom standard that the client uploaded for its own company; "
    "the field `industryStandardValue` holds it. Call it \"your custom standard\" (plural: \"your custom standards\"), and never write "
    "\"industry standard\" or \"industry benchmark\". All the rules about the standard apply to it unchanged."
)


def _custom_wording(text: str) -> str:
    return text.replace("the industry standard", "your custom standard").replace("industry standard", "custom standard") + CUSTOM_NOTE


def _load_prompt(name: str, standards: str = "industry") -> Prompt:
    text = (resources.files("sf_orchestrator") / "prompts" / name).read_text(encoding="utf-8").strip()
    if standards == "custom":
        text = _custom_wording(text)
    return Prompt(text=text, sha=hashlib.sha256(text.encode()).hexdigest()[:12])


def load_system_prompt(standards: str = "industry") -> Prompt:
    """The prompt for a metric outside its healthy range: diagnosis and action plan."""
    return _load_prompt("system.md", standards)


def load_healthy_prompt(standards: str = "industry") -> Prompt:
    """The prompt for a healthy metric: a short summary of how well it is doing."""
    return _load_prompt("healthy.md", standards)


def load_setup_prompt(standards: str = "industry") -> Prompt:
    """The prompt for a metric that could not be calculated because mandatory fields are missing: the plan to set them up."""
    return _load_prompt("setup.md", standards)


@dataclass
class RunSummary:
    run_date: str
    total_insights: int = 0
    skipped_healthy: int = 0
    skipped_no_data: int = 0
    skipped_cached: int = 0
    generated: int = 0
    failed: int = 0
    dry_run: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)


def build_user_prompt(
    module: str, run_date: str, insight: MetricInsight, factors: list[dict[str, Any]], summary: bool = False, setup: bool = False
) -> str:
    """The insight sits in a delimited block; the system prompt says to treat it strictly as data.
    The notebook's root-cause factors are replaced by the same factors with F-ids added by code.
    `summary=True` is for a healthy metric: no root-cause factors, and the model is asked for a summary.
    `setup=True` is for a metric that could not be calculated: only the missing fields and the data checks are given."""
    data = insight.for_prompt(summary=summary, setup=setup)
    if not summary and not setup:
        data["rca"] = {**data.get("rca", {}), "factors": factors}
    data = round_floats(data)
    intro = (
        "Write the data-readiness plan for the metric below."
        if setup
        else "Write the summary for the metric below." if summary else "Write the diagnosis and action plan for the metric below."
    )
    return "\n".join(
        [
            intro,
            "",
            f"<module>{module}</module>",
            f"<run_date>{run_date}</run_date>",
            "<ml_insight>",
            json.dumps(data, separators=(",", ":")),
            "</ml_insight>",
            *glossary_block(glossary_for(data)),
            "",
            'Return ONLY the JSON object defined in the "Output contract" section of your instructions.',
        ]
    )


class Orchestrator:
    """Module- and metric-agnostic pipeline. Nothing here knows what 'TimeToHire' or 'RCM' means:
    every insight that follows the standard JSON contract goes through the same steps."""

    def __init__(
        self,
        store: Store,
        llm: LlmGenerator | None,
        prompt: Prompt,
        concurrency: int = 2,
        redact: Callable[[str], str] = lambda s: s,
        healthy_prompt: Prompt | None = None,
        setup_prompt: Prompt | None = None,
    ):
        """`healthy_prompt` switches on the summaries of healthy metrics, `setup_prompt` the plans for metrics that could not be
        calculated because mandatory fields are missing; without them those metrics are skipped."""
        self._store, self._llm, self._prompt, self._healthy_prompt = store, llm, prompt, healthy_prompt
        self._setup_prompt = setup_prompt
        self._sem = asyncio.Semaphore(concurrency)
        self._redact = redact
        self._detail: dict[str, dict[str, Any]] = {}  # what to tell the dashboard about a generated report

    async def run(
        self,
        run_date: str,
        module: str | None = None,
        metric: str | None = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> RunSummary:
        records = await asyncio.to_thread(self._store.list_insights, run_date, module, metric)
        log.info("Loaded %d ML insight(s) for %s", len(records), run_date)
        dashboard.current().event("insights_loaded", f"Loaded {len(records)} ML insight(s) for {run_date}", data={"count": len(records), "runDate": run_date})
        if not records:
            log.warning("No insights found. Has the ML run finished for this date?")

        summary = RunSummary(run_date=run_date, total_insights=len(records))
        counter = {
            "healthy": "skipped_healthy",
            "no_data": "skipped_no_data",
            "cached": "skipped_cached",
            "generated": "generated",
            "failed": "failed",
            "dry_run": "dry_run",
        }

        meaning = {
            "healthy": "Skipped: the metric is healthy and summaries are switched off",
            "no_data": "Skipped: not enough data to calculate the metric",
            "cached": "Skipped: the saved report is still current",
            "generated": "Report generated",
            "failed": "Report not generated",
            "dry_run": "Dry run: prompt printed",
        }

        async def one(rec: InsightRecord) -> None:
            async with self._sem:
                dashboard.current().event("metric_started", f"{rec.module}/{rec.metric_name} started", module=rec.module, metric=rec.metric_name)
                failures_before = len(summary.failures)
                outcome = await self._process(rec, force, dry_run, summary)
            setattr(summary, counter[outcome], getattr(summary, counter[outcome]) + 1)
            data: dict[str, Any] = {"outcome": outcome, **self._detail.pop(f"{rec.module}/{rec.metric_name}", {})}
            message = f"{rec.module}/{rec.metric_name}: {meaning[outcome]}"
            if outcome == "failed" and len(summary.failures) > failures_before:
                data["reason"] = summary.failures[-1]["reason"]
                message += f": {data['reason'][:300]}"
            dashboard.current().event(
                f"metric_{outcome}", message, module=rec.module, metric=rec.metric_name, data=data,
                level="error" if outcome == "failed" else "warning" if (data.get("retries") or data.get("fallbacks") or data.get("repairs")) else "info",
            )

        await asyncio.gather(*(one(r) for r in records))
        log.info("Run complete: %s", summary)
        return summary

    async def _process(self, rec: InsightRecord, force: bool, dry_run: bool, summary: RunSummary) -> str:
        key = f"{rec.module}/{rec.metric_name}"

        # 1. Validate the ML output (undeclared top-level fields are dropped, but never silently).
        try:
            insight = MetricInsight.model_validate(rec.payload)
        except ValidationError as err:
            return await self._fail(rec, "", f"Invalid ML insight: {format_errors(err, 8)}", summary, dry_run)
        if ignored := ignored_fields(rec.payload):
            log.warning("%s: these fields in the ML JSON are not used: %s", key, ", ".join(ignored))
        if insight.module and insight.module.upper() != rec.module.upper():
            return await self._fail(
                rec, "", f"The ML JSON says module {insight.module} but it is stored under module {rec.module}", summary, dry_run
            )

        # 2. A metric the notebook could not calculate ("unknown": required data is missing) has nothing to diagnose or to
        #    summarize, and asking a model to write about missing numbers would only invite invention. When the notebook names
        #    the MANDATORY fields that are missing there is something to write, though: the steps to set those fields up.
        setup = False
        if insight.health_state == "unknown":
            if self._setup_prompt is None or not insight.mandatory_missing_fields():
                log.info("%s: health state is unknown (not enough data to calculate the metric): no report, no model call", key)
                return "no_data"
            setup = True
        #    A breached metric gets the diagnosis and action plan, a healthy one a short summary (when that is switched on).
        summarize = insight.health_state == "healthy"
        if summarize and self._healthy_prompt is None:
            return "healthy"
        prompt = self._setup_prompt if setup else self._healthy_prompt if summarize else self._prompt
        assert prompt is not None

        # 3. Same input + same prompt => reuse the cached report.
        digest = hashlib.sha256(
            json.dumps(
                {
                    "prompt": prompt.sha,
                    "module": rec.module,
                    "insight": (data := insight.for_prompt(summary=summarize, setup=setup)),
                    "glossary": glossary_for(data),  # editing the glossary regenerates the reports it affects
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if not force and not dry_run:
            existing = await asyncio.to_thread(self._store.find_report, rec.run_date, rec.module, rec.metric_name)
            if existing and existing.status == "succeeded" and existing.input_hash == digest:
                log.info("%s: cached report is current; skipping", key)
                return "cached"

        factors = [] if summarize or setup else build_factors(insight)  # lifted from the ML JSON; only the F-ids are added by code
        user_prompt = build_user_prompt(rec.module, rec.run_date, insight, factors, summary=summarize, setup=setup)
        if dry_run:
            print(f"\n---- DRY RUN {key} (prompt {prompt.sha}) ----\n{user_prompt}")
            return "dry_run"

        # 4. LLM through LiteLLM (retries, cooldowns and fallbacks happen inside). The model only writes the
        #    narrative parts; build_report validates them and adds everything that code can calculate.
        assert self._llm is not None, "an LLM client is required unless dry_run"
        try:
            res = await self._llm.generate(
                prompt.text,
                user_prompt,
                (lambda text: build_healthy_report(text, insight)) if summarize else (lambda text: build_report(text, insight, factors, rec.module, setup=setup)),
                run_key=key,
            )
        except Exception as err:  # LiteLLM raises many exception types; all mean "no report"
            return await self._fail(rec, digest, f"{type(err).__name__}: {err}", summary, dry_run, prompt.sha)

        record = ReportRecord(
            run_date=rec.run_date,
            module=rec.module,
            metric_name=rec.metric_name,
            insight_id=rec.id,
            input_hash=digest,
            prompt_sha=prompt.sha,
            status="succeeded",
            provider=res.provider,
            model=res.model,
            report=res.value,
            llm_meta={
                "fallbacks": res.fallbacks,
                "retries": res.retries,
                "repairs": res.repairs,
                "inputTokens": res.input_tokens,
                "outputTokens": res.output_tokens,
                "latencyMs": res.latency_ms,
            },
            generated_at=_now(),
        )
        try:
            await asyncio.to_thread(self._store.save_report, record)
        except Exception as err:  # noqa: BLE001  (one failed write must not stop the other metrics)
            reason = self._redact(f"{type(err).__name__}: {err}")[:1000]
            log.error("%s: the report was generated but could not be saved: %s", key, reason[:300])
            summary.failures.append({"module": rec.module, "metric": rec.metric_name, "reason": f"the report could not be saved: {reason}"})
            return "failed"
        extras = [
            f"{n} {one if n == 1 else many}"
            for n, one, many in ((res.retries, "retry", "retries"), (res.fallbacks, "fallback", "fallbacks"), (res.repairs, "re-ask", "re-asks"))
            if n
        ]
        self._detail[key] = {
            "provider": res.provider, "model": res.model, "fallbacks": res.fallbacks, "retries": res.retries, "repairs": res.repairs,
            "inputTokens": res.input_tokens, "outputTokens": res.output_tokens, "latencyMs": res.latency_ms,
            "kind": "summary" if summarize else "setup" if setup else "diagnosis",
        }
        message = f"{key}: report generated by {res.provider}/{res.model}"
        if extras:
            log.warning("%s (after %s)", message, ", ".join(extras))
        else:
            log.info(message)
        return "generated"

    async def _fail(
        self, rec: InsightRecord, digest: str, reason: str, summary: RunSummary, dry_run: bool = False, prompt_sha: str | None = None
    ) -> str:
        reason = self._redact(reason)[:1000]
        log.error("%s/%s: report not generated: %s", rec.module, rec.metric_name, reason[:300])
        summary.failures.append({"module": rec.module, "metric": rec.metric_name, "reason": reason})
        if dry_run:  # a dry run never writes anything
            return "failed"
        # Never overwrite a good report for the same day with a failure record.
        existing = await asyncio.to_thread(self._store.find_report, rec.run_date, rec.module, rec.metric_name)
        if not (existing and existing.status == "succeeded"):
            await asyncio.to_thread(
                self._store.save_report,
                ReportRecord(
                    run_date=rec.run_date,
                    module=rec.module,
                    metric_name=rec.metric_name,
                    insight_id=rec.id,
                    input_hash=digest,
                    prompt_sha=prompt_sha or self._prompt.sha,
                    status="failed",
                    error=reason,
                    generated_at=_now(),
                ),
            )
        return "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()