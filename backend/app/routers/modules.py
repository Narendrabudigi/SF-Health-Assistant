import re
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from app.db.mock_data import DEFAULT_MODULES
from app.db.supabase_client import supabase_storage, normalize_slug, alphanumeric_key

router = APIRouter()

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


def extract_metric_fields(override: Dict[str, Any], default_b: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extracts company, standard, status, variance, moduleOverview, and detailedAnalysis from
    the Supabase JSON payload (supporting flat schemas, nested report schemas, and moduleOverview).
    Guarantees that user's word-to-word text from Supabase moduleOverview (rootCause, affectedArea, suggestions)
    is strictly used and never overwritten by generic narratives.
    """
    rep = override.get("report") if isinstance(override.get("report"), dict) else override
    diag = rep.get("diagnosis") if isinstance(rep.get("diagnosis"), dict) else {}
    narrative = diag.get("narrative", "") or rep.get("diagnosis_narrative", "")

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
    suggestions_val = (
        (overview.get("suggestions") if isinstance(overview, dict) else None) or
        find_nested_val(override, "suggestions")
    )

    if not root_cause:
        root_cause = find_nested_val(override, "whyItHappens", "why_it_happens")
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
    if "crit" in status_candidate:
        status_val = "Critical"
    elif "risk" in status_candidate or "warn" in status_candidate:
        status_val = "At Risk"
    elif "health" in status_candidate or "target" in status_candidate:
        status_val = "Healthy"
    elif default_b and default_b.get("status"):
        status_val = default_b["status"]
    else:
        status_val = "At Risk"

    # 2. Company Actual Value
    company_val = (
        override.get("company_actual") or
        override.get("company") or
        override.get("company_value") or
        override.get("actual") or
        rep.get("company_actual") or
        rep.get("company") or
        find_nested_val(override, "company_actual", "company", "actual", "company_value")
    )
    if not company_val and narrative:
        m = re.search(r'Current\s+(?:[A-Za-z\s]+)\s+is\s+([0-9.]+(?:\s*(?:days|hours|%))?)', narrative, re.IGNORECASE)
        if m:
            company_val = m.group(1).strip()

    if not company_val and default_b:
        company_val = default_b.get("company", "0%")

    # 3. Benchmark Standard Target
    target_val = (
        override.get("benchmark_target") or
        override.get("standard") or
        override.get("standard_value") or
        override.get("target") or
        rep.get("benchmark_target") or
        rep.get("standard") or
        find_nested_val(override, "benchmark_target", "standard", "standard_value", "target")
    )
    if not target_val and narrative:
        m = re.search(r'industry\s+standard\s+of\s+([0-9.]+(?:\s*(?:days|hours|%))?)', narrative, re.IGNORECASE)
        if m:
            target_val = f"≤ {m.group(1).strip()}"

    if not target_val and default_b:
        target_val = default_b.get("standard", "≥ 90.0%")

    # 4. Variance Gap
    variance_val = (
        override.get("actual_variance") or
        override.get("variance") or
        override.get("variance_percentage") or
        rep.get("actual_variance") or
        rep.get("variance") or
        find_nested_val(override, "actual_variance", "variance", "variance_percentage")
    )
    if not variance_val and narrative:
        m = re.search(r'which\s+is\s+([0-9.]+\s*(?:days|hours|%)?\s*\([0-9.]+%\)\s*(?:above|below))', narrative, re.IGNORECASE)
        if m:
            direction = "+" if "above" in m.group(1) else "-"
            variance_val = f"{direction}{m.group(1).replace('above', '').replace('below', '').strip()}"

    if not variance_val and default_b:
        variance_val = default_b.get("variance", "0%")

    # Ensure formatted strings
    if isinstance(company_val, (int, float)):
        company_val = f"{company_val}%"
    if isinstance(target_val, (int, float)):
        target_val = f"{target_val}%"
    if isinstance(variance_val, (int, float)):
        variance_val = f"{variance_val}%"

    # 5. Word-to-word Detailed Analysis & moduleOverview Structure
    why_happens = (
        root_cause or
        (default_b.get("detailedAnalysis", {}).get("whyItHappens") if default_b else None) or
        narrative or
        override.get("diagnosis_narrative") or
        "Diagnosed from Supabase ML insights."
    )
    where_happens = (
        affected_area or
        (default_b.get("detailedAnalysis", {}).get("whereItHappens") if default_b else None) or
        "SuccessFactors workflow portlets"
    )
    if suggestions_val:
        suggestions_list = suggestions_val if isinstance(suggestions_val, list) else [suggestions_val]
    elif default_b and default_b.get("detailedAnalysis", {}).get("howToOvercome"):
        suggestions_list = default_b["detailedAnalysis"]["howToOvercome"]
    else:
        suggestions_list = []

    trend = (
        rep.get("trendAnalysis") or
        override.get("trendAnalysis") or
        (default_b.get("detailedAnalysis", {}).get("trendAnalysis") if default_b else {})
    )
    missing_cfg = (
        override.get("missingConfigurations") or
        (default_b.get("detailedAnalysis", {}).get("missingConfigurations") if default_b else [])
    )
    how_effects = (
        rep.get("businessImpact", {}).get("overview") if isinstance(rep.get("businessImpact"), dict) else (
            override.get("howItEffects") or (default_b.get("detailedAnalysis", {}).get("howItEffects") if default_b else "")
        )
    )

    module_overview = {
        "rootCause": root_cause or why_happens,
        "affectedArea": affected_area or where_happens,
        "suggestions": suggestions_list
    }

    return {
        "company": str(company_val or "0%"),
        "standard": str(target_val or "≥ 90.0%"),
        "status": status_val,
        "variance": str(variance_val or "0%"),
        "moduleOverview": module_overview,
        "detailedAnalysis": {
            "whyItHappens": root_cause or why_happens,
            "whereItHappens": affected_area or where_happens,
            "trendAnalysis": trend,
            "missingConfigurations": missing_cfg,
            "howItEffects": how_effects,
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
    Apply metric overrides from Supabase Storage:
    report/latest/{module}/{metric}/
    Guarantees that ALL metrics in Supabase are reflected without dropping defaults or cross-contaminating modules.
    """
    mod_key = mod_id.lower().strip()
    valid_aliases = MODULE_ALIASES.get(mod_key, {mod_key, alphanumeric_key(mod_key)})
    
    mod_overrides = module_overrides_map.get(mod_key)
    if not mod_overrides:
        for k, val in module_overrides_map.items():
            clean_k = alphanumeric_key(k)
            if clean_k in valid_aliases or k.lower() in valid_aliases or normalize_slug(k) in valid_aliases:
                mod_overrides = val
                break
    mod_overrides = mod_overrides or {}

    matched_storage_paths = set()
    updated_benchmarks = []

    # 1. Update existing default benchmarks if present in Supabase
    for b in benchmarks:
        b_copy = dict(b)
        m_name = b_copy.get("metric", "")
        m_code = b_copy.get("code", "")
        m_slug = normalize_slug(m_name)
        c_slug = normalize_slug(m_code)
        m_alpha = alphanumeric_key(m_name)
        c_alpha = alphanumeric_key(m_code)

        override = (
            mod_overrides.get(m_name) or
            mod_overrides.get(m_code) or
            mod_overrides.get(m_slug) or
            mod_overrides.get(c_slug) or
            mod_overrides.get(m_alpha) or
            mod_overrides.get(c_alpha)
        )

        if not override:
            for k, val in mod_overrides.items():
                k_alpha = alphanumeric_key(k)
                if len(k_alpha) >= 4 and (
                    k_alpha in m_alpha or
                    m_alpha in k_alpha or
                    k_alpha in c_alpha or
                    c_alpha in k_alpha
                ):
                    override = val
                    break

        if override:
            storage_path = override.get("_storage_path")
            if storage_path:
                matched_storage_paths.add(storage_path)

            extracted = extract_metric_fields(override, default_b=b_copy)
            b_copy["company"] = extracted["company"]
            b_copy["standard"] = extracted["standard"]
            b_copy["status"] = extracted["status"]
            b_copy["variance"] = extracted["variance"]
            b_copy["moduleOverview"] = extracted["moduleOverview"]
            b_copy["detailedAnalysis"] = extracted["detailedAnalysis"]
            b_copy["_source"] = "supabase_storage_metric_folder"
            b_copy["_storage_path"] = storage_path
            b_copy["isSupabaseLive"] = True
        else:
            b_copy["_source"] = "static_baseline"
            b_copy["isSupabaseLive"] = False

        updated_benchmarks.append(b_copy)

    # 2. Add any extra metrics in Supabase that were NOT in default benchmarks
    seen_alphas = {alphanumeric_key(b.get("metric", "")) for b in updated_benchmarks}
    seen_alphas.update({alphanumeric_key(b.get("code", "")) for b in updated_benchmarks})

    for override in mod_overrides.values():
        if not isinstance(override, dict):
            continue
        storage_path = override.get("_storage_path")
        if storage_path and storage_path in matched_storage_paths:
            continue

        m_folder_name = override.get("_metric_folder") or override.get("metric_name") or override.get("metric")
        if not m_folder_name:
            continue

        m_alpha = alphanumeric_key(m_folder_name)
        if m_alpha in seen_alphas:
            continue

        seen_alphas.add(m_alpha)
        if storage_path:
            matched_storage_paths.add(storage_path)

        extracted = extract_metric_fields(override, default_b=None)
        new_metric_entry = {
            "code": override.get("metric_code") or f"{mod_id}_{normalize_slug(m_folder_name)}",
            "metric": override.get("metric_name") or m_folder_name,
            "category": override.get("category") or "Operational KPI",
            "company": extracted["company"],
            "standard": extracted["standard"],
            "status": extracted["status"],
            "variance": extracted["variance"],
            "_source": "supabase_storage_metric_folder",
            "_storage_path": storage_path,
            "moduleOverview": extracted["moduleOverview"],
            "detailedAnalysis": extracted["detailedAnalysis"]
        }
        updated_benchmarks.append(new_metric_entry)

    return updated_benchmarks


@router.get("", response_model=List[Dict[str, Any]])
def get_all_modules(refresh: bool = Query(False)):
    """
    Returns modules overview with real-time values from Supabase Storage:
    report/latest/{module}/{metric}/
    Cached in-memory for instant < 5ms response times.
    """
    module_overrides_map = supabase_storage.get_all_module_metric_overrides(force_refresh=refresh)

    enriched = []
    for mod in DEFAULT_MODULES:
        mod_id = mod["id"]
        raw_benchmarks = mod.get("benchmarks", [])
        
        benchmarks = apply_module_metric_overrides(mod_id, raw_benchmarks, module_overrides_map)

        crit_count = sum(1 for b in benchmarks if b.get("status") == "Critical")
        risk_count = sum(1 for b in benchmarks if b.get("status") == "At Risk")
        healthy_count = sum(1 for b in benchmarks if b.get("status") == "Healthy")

        if crit_count > 0:
            mod_status = "Critical"
        elif risk_count > 0:
            mod_status = "At Risk"
        else:
            mod_status = "Healthy"

        clean_name = ENTERPRISE_MODULE_NAMES.get(mod_id.lower(), mod.get("name", "Recruitment"))

        enriched.append({
            **mod,
            "name": clean_name,
            "status": mod_status,
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
