import re
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from app.db.mock_data import DEFAULT_MODULES
from app.db.supabase_client import supabase_storage, normalize_slug, alphanumeric_key, normalize_missing_configurations, extract_accuracy_score

router = APIRouter()
logger = logging.getLogger("sf_health.modules")

ENTERPRISE_MODULE_NAMES = {
    "ec": "Employee Central",
    "rcm": "Recruitment",
    "onb": "Onboarding",
    "ofb": "Offboarding",
    "ecp": "Employee Central Payroll"
}


def find_nested_val(data: Any, *keys: str) -> Optional[Any]:
    """Recursively search dictionary for any matching key, case-insensitive, ignoring underscores/hyphens."""
    if not isinstance(data, dict):
        return None
    normalized = {k.lower().replace("_", "").replace("-", "") for k in keys}
    
    # 1. Direct key match
    for k, v in data.items():
        if k.lower().replace("_", "").replace("-", "") in normalized and v is not None and v != "":
            return v

    # 2. Priority containers
    for container_key in ["moduleOverview", "module_overview", "overview", "report", "detailedAnalysis", "detailed_analysis"]:
        if container_key in data and isinstance(data[container_key], dict):
            found = find_nested_val(data[container_key], *keys)
            if found is not None and found != "":
                return found

    # 3. Recursive sub-dict search
    for v in data.values():
        if isinstance(v, dict):
            found = find_nested_val(v, *keys)
            if found is not None and found != "":
                return found
    return None


def normalize_confidence_score(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        m = re.search(r"[-+]?\d*\.?\d+", str(value))
        if not m:
            return None
        try:
            n = float(m.group(0))
        except ValueError:
            return None
    if 0 <= n <= 1:
        n *= 100
    return round(max(0, min(100, n)), 1)


def extract_confidence_score(data: Dict[str, Any]) -> Optional[float]:
    if not isinstance(data, dict):
        return None
    candidates = [
        data.get("confidenceScore"), data.get("confidence_score"), data.get("confidence"),
        data.get("diagnosisConfidence"), data.get("diagnosis_confidence"),
        data.get("modelConfidence"), data.get("model_confidence")
    ]
    for container_key in ("diagnosis", "report", "metric", "dataQuality", "data_quality", "trendAnalysis", "trend_analysis"):
        container = data.get(container_key)
        if isinstance(container, dict):
            candidates.extend([
                container.get("confidenceScore"), container.get("confidence_score"),
                container.get("confidence"), container.get("diagnosisConfidence"),
                container.get("diagnosis_confidence"), container.get("modelConfidence"),
                container.get("model_confidence")
            ])
    for candidate in candidates:
        score = normalize_confidence_score(candidate)
        if score is not None:
            return score
    return None


def extract_metric_fields(override: Dict[str, Any], default_b: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extracts company, standard, status, variance, moduleOverview, and detailedAnalysis from
    the Supabase JSON payload (supporting flat schemas, nested report schemas, and moduleOverview).
    Guarantees that user's word-to-word text from Supabase moduleOverview (rootCause, affectedArea, suggestions)
    is strictly used and never overwritten by generic narratives.
    """
    rep_nested = override.get("report") if isinstance(override.get("report"), dict) else {}
    rep = {**rep_nested, **override}

    def first_value(*values):
        """Keep valid numeric zeroes while skipping unset text fields."""
        for value in values:
            if value is not None and not (isinstance(value, str) and not value.strip()):
                return value
        return None

    diag = rep.get("diagnosis") if isinstance(rep.get("diagnosis"), dict) else {}
    # Keep structured diagnosis points intact for the deep dive UI.
    narrative = diag.get("narrative") or rep.get("diagnosis_narrative") or ""
    headline = str(diag.get("headline", "") or "")
    biz_impact = rep.get("businessImpact") if isinstance(rep.get("businessImpact"), dict) else {}
    impact_overview = str(biz_impact.get("overview", "") or "")

    # Combine text sources for pattern extraction
    full_context_text = f"{headline} {narrative} {impact_overview}".strip()

    # Explicit extraction of moduleOverview fields from Supabase JSON
    overview = (
        override.get("moduleOverview") or
        override.get("module_overview") or
        (rep.get("moduleOverview") if isinstance(rep, dict) else None) or
        (rep.get("module_overview") if isinstance(rep, dict) else None) or
        {}
    )
    
    root_cause = (
        (overview.get("rootCause") if isinstance(overview, dict) else None) or
        (overview.get("root_cause") if isinstance(overview, dict) else None) or
        find_nested_val(override, "rootCause", "root_cause")
    )
    affected_area = (
        (overview.get("affectedArea") if isinstance(overview, dict) else None) or
        (overview.get("affected_area") if isinstance(overview, dict) else None) or
        find_nested_val(override, "affectedArea", "affected_area")
    )

    # Dynamic workstreams remediation steps from Supabase
    raw_ws = override.get("workstreams") or rep.get("workstreams") or []
    ws_steps = []
    if isinstance(raw_ws, list) and raw_ws:
        ws_steps = [
            w.get("step") or w.get("remediationStep") or w.get("title")
            for w in raw_ws
            if isinstance(w, dict) and (w.get("step") or w.get("remediationStep") or w.get("title")) and w.get("kind") != "data"
        ]
        if not ws_steps:
            ws_steps = [
                w.get("step") or w.get("remediationStep") or w.get("title")
                for w in raw_ws
                if isinstance(w, dict) and (w.get("step") or w.get("remediationStep") or w.get("title"))
            ]

    suggestions_val = (
        (ws_steps if ws_steps and len(ws_steps) > 0 else None) or
        (override.get("suggestions") if isinstance(override.get("suggestions"), list) and len(override["suggestions"]) > 0 else None) or
        (rep_nested.get("suggestions") if isinstance(rep_nested.get("suggestions"), list) and len(rep_nested["suggestions"]) > 0 else None) or
        (diag.get("suggestions") if isinstance(diag.get("suggestions"), list) and len(diag["suggestions"]) > 0 else None) or
        (overview.get("suggestions") if isinstance(overview, dict) and isinstance(overview.get("suggestions"), list) and len(overview["suggestions"]) > 0 else None) or
        find_nested_val(override, "suggestions")
    )

    if not root_cause:
        root_cause = find_nested_val(override, "whyItHappens", "why_it_happens")
    if not root_cause and isinstance(overview, dict):
        raw_summary = overview.get("summary")
        if isinstance(raw_summary, list) and len(raw_summary) > 0:
            root_cause = " ".join(str(s) for s in raw_summary)
        elif isinstance(raw_summary, str) and raw_summary.strip():
            root_cause = raw_summary.strip()
    if not affected_area:
        affected_area = find_nested_val(override, "whereItHappens", "where_it_happens")
    if not suggestions_val:
        suggestions_val = find_nested_val(override, "howToOvercome", "how_to_overcome", "suggestions_to_improve", "recommendations")

    # 1. Health Status
    health_raw = (
        rep.get("healthState") or
        rep.get("health_state") or
        override.get("health_state") or
        override.get("healthState")
    )
    raw_status = override.get("status")
    if raw_status and str(raw_status).lower() in ("succeeded", "completed", "success", "done", "finished", "ok"):
        raw_status = None

    status_candidate = str(health_raw or raw_status or "").lower()
    if not status_candidate and full_context_text:
        # Check text if health state was not directly in key
        if re.search(r'\bcritical\b', full_context_text, re.IGNORECASE):
            status_candidate = "critical"
        elif re.search(r'\b(?:at-risk|at_risk|at risk|warning)\b', full_context_text, re.IGNORECASE):
            status_candidate = "at-risk"
        elif re.search(r'\b(?:healthy|on-track|on track)\b', full_context_text, re.IGNORECASE):
            status_candidate = "healthy"

    if "crit" in status_candidate:
        status_val = "Critical"
    elif "risk" in status_candidate or "warn" in status_candidate or "breach" in status_candidate:
        status_val = "At Risk"
    elif "health" in status_candidate or "target" in status_candidate or "good" in status_candidate:
        status_val = "Healthy"
    elif "unknown" in status_candidate or (isinstance(override.get("dataQuality"), dict) and override.get("dataQuality", {}).get("overallRating") == "poor"):
        status_val = "At Risk"
    elif override.get("isSupabaseLive") or override.get("_source", "").startswith("supabase"):
        status_val = "At Risk" if (isinstance(override.get("dataQuality"), dict) and override.get("dataQuality", {}).get("recordsAnalysed") == 0) else "Healthy"
    else:
        status_val = "Not yet fetched"

    def clean_val(v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, dict):
            val = v.get("value")
            pct = v.get("percentage")
            if val is not None and pct is not None:
                try:
                    sign = "+" if float(val) > 0 else ""
                    return f"{sign}{val} ({sign}{pct}%)"
                except Exception:
                    return f"{val} ({pct}%)"
            elif val is not None:
                try:
                    sign = "+" if float(val) > 0 else ""
                    return f"{sign}{val}"
                except Exception:
                    return str(val)
            return None
        s = str(v).strip()
        if s.lower() in ("not yet fetched", "data not yet fetched from supabase", "--", "-", "none", "null", ""):
            return None
        return s

    # 2. Company Actual Value
    raw_company = first_value(
        override.get("company_actual"), override.get("companyValue"),
        override.get("company"), override.get("company_value"),
        override.get("actualValue"), override.get("actual"),
        override.get("actual_value"), override.get("current_value"),
        override.get("actual_days"), override.get("current_days"),
        rep.get("company_actual"), rep.get("companyValue"),
        rep.get("company"), rep.get("actualValue"), rep.get("actual"),
        rep.get("current_value"), diag.get("current_value"), diag.get("actual"),
        find_nested_val(override, "company_actual", "companyValue", "company", "actual", "actualValue", "company_value")
    )
    company_val = clean_val(raw_company)
    if not company_val and full_context_text:
        # Pattern A: "stands at 25.6 days", "reaching 25.6 days", "reaches 25.6 days"
        m1 = re.search(r'(?:stands\s+at|is\s+currently|currently\s+stands\s+at|actual\s+is|is\s+at|reaching|reaches)\s+([0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)', full_context_text, re.IGNORECASE)
        if m1:
            company_val = m1.group(1).strip()
        else:
            # Pattern B: "Current Time to Hire is 34.2 days", "current Time to Hire stands at 25.6 days"
            m2 = re.search(r'current\s+[a-zA-Z\s_-]+?\s+(?:is|stands\s+at|at)\s+([0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)', full_context_text, re.IGNORECASE)
            if m2:
                company_val = m2.group(1).strip()

    # 3. Benchmark Standard Target
    raw_target = first_value(
        override.get("benchmark_target"), override.get("industryStandardValue"),
        override.get("benchmarkTarget"), override.get("standard"),
        override.get("standard_value"), override.get("targetValue"),
        override.get("target"), rep.get("benchmark_target"),
        rep.get("industryStandardValue"), rep.get("benchmarkTarget"),
        rep.get("standard"), rep.get("target"), rep.get("targetValue"),
        diag.get("standard"), diag.get("target"),
        find_nested_val(override, "benchmark_target", "industryStandardValue", "benchmarkTarget", "standard", "standard_value", "target", "targetValue")
    )
    target_val = clean_val(raw_target)
    if not target_val and full_context_text:
        m_t = re.search(r'(?:industry\s+standard|standard|benchmark|target)\s*(?:of|is|at|≤|≥)?\s*([≤≥<>~]?\s*[0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)', full_context_text, re.IGNORECASE)
        if m_t:
            raw_target_str = m_t.group(1).strip()
            if not raw_target_str.startswith(('≤', '≥', '<', '>', '~')):
                # Infer operator based on unit: days/hours/latency/attrition -> <= ; rates/accuracy -> >=
                if any(u in raw_target_str.lower() for u in ['day', 'hour', 'week', 'month', 'turnaround', 'latency', 'attrition']):
                    target_val = f"≤ {raw_target_str}"
                else:
                    target_val = f"≥ {raw_target_str}"
            else:
                target_val = raw_target_str

    # 4. Variance Gap
    raw_var = first_value(
        override.get("actual_variance"), override.get("variance"),
        override.get("variance_percentage"), override.get("gap"),
        rep.get("actual_variance"), rep.get("variance"), diag.get("gap"),
        find_nested_val(override, "actual_variance", "variance", "variance_percentage")
    )
    variance_val = clean_val(raw_var)
    if not variance_val and full_context_text:
        # Pattern A: "which is 5.6 days (or 28.0%) above the industry standard"
        m_v1 = re.search(r'which\s+is\s+([0-9.]+\s*(?:days|hours|weeks|%)?)(?:\s*\((?:or\s*)?([0-9.]+%)\))?\s*(above|below)', full_context_text, re.IGNORECASE)
        if m_v1:
            diff_num = m_v1.group(1).strip()
            pct_val = m_v1.group(2)
            direction = "+" if m_v1.group(3).lower() == "above" else "-"
            if pct_val:
                variance_val = f"{direction}{diff_num} ({direction}{pct_val})"
            else:
                variance_val = f"{direction}{diff_num}"
        else:
            # Pattern B: "exceeding the industry standard of 20.0 days by 5.6 days"
            m_v2 = re.search(r'(?:exceeding|exceeds|above|below)\s+[^,.]*?\s+by\s+([0-9.]+\s*(?:days|hours|weeks|%)?)', full_context_text, re.IGNORECASE)
            if m_v2:
                variance_val = f"+{m_v2.group(1).strip()}"

    # Calculate variance mathematically if company and target numbers exist and variance still missing
    if not variance_val and company_val and target_val:
        m_c_num = re.search(r'([0-9.]+)', str(company_val))
        m_t_num = re.search(r'([0-9.]+)', str(target_val))
        if m_c_num and m_t_num:
            try:
                c_f = float(m_c_num.group(1))
                t_f = float(m_t_num.group(1))
                diff = c_f - t_f
                unit = " days" if "day" in str(company_val).lower() else ("%" if "%" in str(company_val) else "")
                pct_diff = (diff / t_f * 100) if t_f != 0 else 0
                sign = "+" if diff > 0 else "-"
                variance_val = f"{sign}{abs(diff):.1f}{unit} ({sign}{abs(pct_diff):.1f}%)"
            except Exception:
                pass

    # Ensure formatted strings
    if isinstance(company_val, (int, float)):
        company_val = f"{company_val}%"
    if isinstance(target_val, (int, float)):
        target_val = f"{target_val}%"
    if isinstance(variance_val, (int, float)):
        variance_val = f"{variance_val}%"

    # Default fallbacks if not found
    is_live_supa = bool(override.get("isSupabaseLive") or override.get("_source", "").startswith("supabase"))
    if not company_val and is_live_supa:
        rec_count = override.get("dataQuality", {}).get("recordsAnalysed", 0) if isinstance(override.get("dataQuality"), dict) else 0
        final_company = f"No Data ({rec_count} Records)" if rec_count == 0 else "N/A"
    else:
        final_company = str(company_val) if company_val else "Not yet fetched"

    final_target = str(target_val) if target_val else "Not yet fetched"
    if not variance_val and is_live_supa:
        final_variance = "N/A (Data Gap)"
    else:
        final_variance = str(variance_val) if variance_val else "Not yet fetched"

    # 5. Word-to-word Detailed Analysis & moduleOverview Structure
    why_happens = (
        root_cause or
        narrative or
        override.get("diagnosis_narrative") or
        "Data not yet fetched"
    )
    where_happens = (
        affected_area or
        "Data not yet fetched"
    )
    if suggestions_val:
        suggestions_list = suggestions_val if isinstance(suggestions_val, list) else [suggestions_val]
    else:
        suggestions_list = []

    trend = (
        rep.get("trendAnalysis") or
        override.get("trendAnalysis") or
        {"summary": "Data not yet fetched", "points": []}
    )
    raw_missing = override.get("missingConfigurations") or override.get("missingConfiguration") or []
    dq_checks = override.get("dataQuality", {}).get("checks", []) if isinstance(override.get("dataQuality"), dict) else []
    mod_raw = (
        override.get("Module_Name") or
        override.get("module") or
        override.get("_module") or
        (default_b.get("code", "")[:2] if default_b and default_b.get("code") else "EC")
    )
    missing_cfg = normalize_missing_configurations(raw_missing, mod_name=mod_raw, dq_checks=dq_checks)
    how_effects = (
        rep.get("businessImpact", {}).get("overview") if isinstance(rep.get("businessImpact"), dict) else (
            override.get("howItEffects") or "Data not yet fetched"
        )
    )

    module_overview = {
        "rootCause": root_cause or why_happens,
        "affectedArea": affected_area or where_happens,
        "suggestions": suggestions_list
    }

    diagnosis_obj = {
        "headline": headline,
        "narrative": narrative
    } if (headline or narrative) else {}

    final_why_it_happens = narrative if narrative else (root_cause or why_happens)

    biz_impact_full = (
        rep.get("businessImpact") if isinstance(rep.get("businessImpact"), dict) else (
            override.get("businessImpact") if isinstance(override.get("businessImpact"), dict) else {}
        )
    )
    business_impact_obj = {
        "overview": biz_impact_full.get("overview") or (how_effects if how_effects not in ("Data not yet fetched", "Data not yet fetched from Supabase") else ""),
        "financialExposure": biz_impact_full.get("financialExposure") or biz_impact_full.get("financial_exposure", ""),
        "slaAndTurnaround": biz_impact_full.get("slaAndTurnaround") or biz_impact_full.get("sla_and_turnaround", ""),
        "governanceAndAudit": biz_impact_full.get("governanceAndAudit") or biz_impact_full.get("governance_and_audit", "")
    }

    confidence_score = extract_confidence_score(rep) or extract_confidence_score(override)
    accuracy_score = extract_accuracy_score(rep)
    if accuracy_score is None:
        accuracy_score = extract_accuracy_score(override)

    return {
        "company": final_company,
        "standard": final_target,
        "status": status_val,
        "variance": final_variance,
        "confidenceScore": confidence_score,
        "accuracyScore": accuracy_score,
        "missingConfigurations": missing_cfg,
        "moduleOverview": module_overview,
        "diagnosis": diagnosis_obj,
        "businessImpact": business_impact_obj,
        "detailedAnalysis": {
            "whyItHappens": final_why_it_happens,
            "whereItHappens": affected_area or where_happens,
            "trendAnalysis": trend,
            "missingConfigurations": missing_cfg,
            "howItEffects": business_impact_obj["overview"] or how_effects,
            "businessImpact": business_impact_obj,
            "howToOvercome": suggestions_list
        }
    }


MODULE_ALIASES = {
    "ec": {"ec", "employeecentral", "employee_central", "employee-central"},
    "rcm": {"rcm", "recruitment", "recruiting"},
    "onb": {"onb", "onb2", "onboarding"},
    "ofb": {"ofb", "ofb2", "offboarding"},
    "ecp": {"ecp", "payroll", "employeecentralpayroll", "employee_central_payroll"}
}


def apply_module_metric_overrides(
    mod_id: str,
    benchmarks: List[Dict[str, Any]],
    module_overrides_map: Dict[str, Dict[str, Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """
    Merge the static metric catalogue with every live metric payload available in
    Supabase.  A metric is considered LIVE when *any* usable Supabase payload is
    found, even when that payload also contains missing configuration fields.

    Important distinction:
      - metric data present + missing fields -> show the metric data AND list gaps
      - no metric payload at all -> show "Not yet fetched"
    """
    mod_key = str(mod_id or "").lower().strip()
    valid_aliases = MODULE_ALIASES.get(mod_key, {mod_key, alphanumeric_key(mod_key)})

    mod_overrides = module_overrides_map.get(mod_key)
    if not mod_overrides:
        for k, val in module_overrides_map.items():
            clean_k = alphanumeric_key(k)
            if clean_k in {alphanumeric_key(a) for a in valid_aliases} or k.lower() in valid_aliases or normalize_slug(k) in valid_aliases:
                mod_overrides = val
                break
    mod_overrides = mod_overrides or {}

    def identifiers(value: Any) -> set:
        if value is None:
            return set()
        text = str(value).strip()
        if not text:
            return set()
        return {
            text.lower(),
            normalize_slug(text),
            alphanumeric_key(text),
        }

    def override_identifiers(payload: Dict[str, Any]) -> set:
        ids = set()
        if not isinstance(payload, dict):
            return ids
        for value in (
            payload.get("metric"),
            payload.get("metric_name"),
            payload.get("Metric_Name"),
            payload.get("metricName"),
            payload.get("MetricName"),
            payload.get("metric_code"),
            payload.get("Metric_Code"),
            payload.get("_metric_folder"),
            payload.get("_metric_name"),
            (payload.get("report") or {}).get("metricName") if isinstance(payload.get("report"), dict) else None,
            (payload.get("report") or {}).get("metric_name") if isinstance(payload.get("report"), dict) else None,
        ):
            ids.update(identifiers(value))
        return {x for x in ids if x}

    def find_override(default_b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        target_ids = identifiers(default_b.get("metric")) | identifiers(default_b.get("code"))
        if not target_ids:
            return None

        # Fast path: all aliases generated by register_metric_data().
        for key in (
            default_b.get("metric"),
            default_b.get("code"),
            normalize_slug(default_b.get("metric", "")),
            normalize_slug(default_b.get("code", "")),
            alphanumeric_key(default_b.get("metric", "")),
            alphanumeric_key(default_b.get("code", "")),
        ):
            if key and key in mod_overrides and isinstance(mod_overrides[key], dict):
                return mod_overrides[key]

        # Robust fallback: compare the actual metric identifiers contained in
        # each Supabase payload. This handles renamed folders / display names.
        best = None
        best_score = 0
        seen_payload_ids = set()
        for payload in mod_overrides.values():
            if not isinstance(payload, dict):
                continue
            marker = id(payload)
            if marker in seen_payload_ids:
                continue
            seen_payload_ids.add(marker)
            p_ids = override_identifiers(payload)
            if not p_ids:
                continue
            exact = target_ids & p_ids
            if exact:
                return payload
            # Allow strong substring matching only for sufficiently specific keys.
            for t in target_ids:
                if len(t) < 8:
                    continue
                for q in p_ids:
                    if len(q) < 8:
                        continue
                    if t == q:
                        return payload
                    if len(t) >= 12 and (t in q or q in t):
                        score = min(len(t), len(q))
                        if score > best_score:
                            best = payload
                            best_score = score
        return best

    def merge_live_metric(default_b: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        extracted = extract_metric_fields(override, default_b=default_b)

        result = dict(default_b)
        result["company"] = extracted["company"]
        result["status"] = extracted["status"]
        result["variance"] = extracted["variance"]
        result["confidenceScore"] = extracted.get("confidenceScore")
        result["accuracyScore"] = extracted.get("accuracyScore")
        result["missingConfigurations"] = extracted.get("missingConfigurations", [])
        result["moduleOverview"] = extracted["moduleOverview"]
        result["diagnosis"] = extracted.get("diagnosis") or default_b.get("diagnosis", {})
        result["businessImpact"] = extracted.get("businessImpact", {})
        result["detailedAnalysis"] = extracted["detailedAnalysis"]

        # Industry standard is extracted from the ML Insights payload.
        result["standard"] = extracted["standard"]

        result["_source"] = override.get("_source", "supabase")
        result["_storage_path"] = override.get("_storage_path")
        result["isSupabaseLive"] = True
        return result

    updated_benchmarks = []
    matched_payload_ids = set()

    # 1. Merge every default metric with its live Supabase payload when one exists.
    for default_b in benchmarks:
        b_copy = dict(default_b)
        override = find_override(default_b)

        if override:
            matched_payload_ids.add(id(override))
            updated_benchmarks.append(merge_live_metric(b_copy, override))
            continue

        # No payload at all: this is genuinely not fetched. Do not manufacture
        # a data gap from missing fields; gaps only come from a live payload.
        b_copy["company"] = "Not yet fetched"
        b_copy["standard"] = "Not yet fetched"
        b_copy["status"] = "Not yet fetched"
        b_copy["variance"] = "Not yet fetched"
        b_copy["missingConfigurations"] = []
        b_copy["moduleOverview"] = {
            "rootCause": "Data not yet fetched",
            "affectedArea": "Data not yet fetched",
            "suggestions": []
        }
        b_copy["detailedAnalysis"] = {
            "whyItHappens": "Data not yet fetched",
            "whereItHappens": "Data not yet fetched",
            "trendAnalysis": {"summary": "Data not yet fetched", "points": []},
            "missingConfigurations": [],
            "howItEffects": "Data not yet fetched",
            "howToOvercome": []
        }
        b_copy["_source"] = "static_baseline"
        b_copy["isSupabaseLive"] = False
        updated_benchmarks.append(b_copy)

    # 2. Preserve additional live metrics that are not part of the static catalogue.
    seen_ids = set()
    for b in updated_benchmarks:
        seen_ids.update(identifiers(b.get("metric")))
        seen_ids.update(identifiers(b.get("code")))

    seen_payloads = set()
    for override in mod_overrides.values():
        if not isinstance(override, dict):
            continue
        payload_id = id(override)
        if payload_id in seen_payloads or payload_id in matched_payload_ids:
            continue
        seen_payloads.add(payload_id)

        m_folder_name = (
            override.get("_metric_folder") or
            override.get("metric_name") or
            override.get("Metric_Name") or
            override.get("metric") or
            override.get("metricName")
        )
        if not m_folder_name:
            continue
        if identifiers(m_folder_name) & seen_ids:
            continue

        metric_code = override.get("metric_code") or override.get("Metric_Code") or f"{mod_id}_{normalize_slug(m_folder_name)}"
        default_like = {
            "code": metric_code,
            "metric": override.get("metric_name") or override.get("Metric_Name") or m_folder_name,
            "category": override.get("category") or "Operational KPI"
        }
        merged = merge_live_metric(default_like, override)
        updated_benchmarks.append(merged)
        seen_ids.update(identifiers(merged.get("metric")))
        seen_ids.update(identifiers(merged.get("code")))

    return updated_benchmarks


@router.get("", response_model=List[Dict[str, Any]])
def get_all_modules(refresh: bool = Query(True)):
    """
    Returns modules overview with real-time values from Supabase Storage:
    report/latest/{module}/{metric}/
    Always fresh so live pipeline updates reflect instantly.
    """
    try:
        module_overrides_map = supabase_storage.get_all_module_metric_overrides(force_refresh=True)
    except Exception as e:
        logger.error(f"Error fetching Supabase overrides: {e}", exc_info=True)
        module_overrides_map = {}

    enriched = []
    for mod in DEFAULT_MODULES:
        mod_id = mod["id"]
        raw_benchmarks = mod.get("benchmarks", [])
        
        benchmarks = apply_module_metric_overrides(mod_id, raw_benchmarks, module_overrides_map)

        crit_count = sum(1 for b in benchmarks if b.get("status") == "Critical")
        risk_count = sum(1 for b in benchmarks if b.get("status") == "At Risk")
        healthy_count = sum(1 for b in benchmarks if b.get("status") == "Healthy")

        clean_name = ENTERPRISE_MODULE_NAMES.get(mod_id.lower(), mod.get("name", "Recruitment"))

        has_live = any(b.get("isSupabaseLive") for b in benchmarks)
        if not has_live:
            mod_status = "Not yet fetched"
            mod_ai_report = {"summary": "Data not yet fetched."}
        else:
            if crit_count > 0:
                mod_status = "Critical"
            elif risk_count > 0:
                mod_status = "At Risk"
            else:
                mod_status = "Healthy"
            live_b = next((b for b in benchmarks if b.get("isSupabaseLive")), None)
            if live_b:
                root_c = live_b.get("moduleOverview", {}).get("rootCause", "")
                if live_b.get("company") != "Not yet fetched":
                    mod_ai_report = {
                        "summary": f"{clean_name} performance is at {live_b['company']} (standard {live_b['standard']}) with {live_b['variance']} variance gap. {root_c}".strip()
                    }
                else:
                    mod_ai_report = {
                        "summary": f"{clean_name} status is {mod_status}. {root_c}".strip()
                    }
            else:
                mod_ai_report = {"summary": "Data not yet fetched."}

        enriched.append({
            **mod,
            "name": clean_name,
            "status": mod_status,
            "aiReport": mod_ai_report,
            "benchmarks": benchmarks,
            "benchmarksCount": len(benchmarks),
            "criticalCount": crit_count,
            "atRiskCount": risk_count,
            "healthyCount": healthy_count
        })

    return enriched


@router.get("/{module_id}")
def get_module_details(module_id: str):
    """
    Returns single module with benchmarks and Supabase storage overrides applied.
    """
    all_mods = get_all_modules()
    matched = next((m for m in all_mods if m["id"].lower() == module_id.lower()), None)
    if not matched:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found.")
    return matched
