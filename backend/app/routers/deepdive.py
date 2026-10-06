from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any, List
from app.db.supabase_client import supabase_storage, normalize_slug, alphanumeric_key
from app.db.mock_data import DEFAULT_MODULES
from app.routers.modules import extract_metric_fields

router = APIRouter()

def find_metric_by_code_or_name(identifier: str):
    """Search for a metric across default modules by code, name, slug, or alphanumeric key."""
    if not identifier:
        return None, None

    norm = identifier.lower().replace('-', '_').replace(' ', '_')
    slug = normalize_slug(identifier)
    alpha = alphanumeric_key(identifier)

    for mod in DEFAULT_MODULES:
        for b in mod.get("benchmarks", []):
            b_code = b.get("code", "").lower()
            b_name = b.get("metric", "").lower()
            b_slug = normalize_slug(b.get("metric", ""))
            b_alpha = alphanumeric_key(b.get("metric", ""))
            c_alpha = alphanumeric_key(b.get("code", ""))

            if (
                b_code == norm or
                b_name == identifier.lower() or
                b_slug == slug or
                b_alpha == alpha or
                c_alpha == alpha or
                (len(alpha) >= 4 and (alpha in b_alpha or b_alpha in alpha or alpha in c_alpha))
            ):
                return mod, b

    return None, None


@router.get("/{metric_code}/deep-dive")
def get_metric_deep_dive(
    metric_code: str,
    metric_name: Optional[str] = Query(None),
    module_id: Optional[str] = Query(None)
):
    """
    Returns the comprehensive 9-section diagnostic payload for a metric.
    Prioritizes loading whatever is inside the metric's folder in Supabase Storage.
    Any data present in the metric folder in Supabase will override and reflect in the frontend!
    """
    # 1. Find default metric template as base
    mod, metric_obj = find_metric_by_code_or_name(metric_name or metric_code)

    metric_title = metric_obj.get("metric", metric_name or metric_code.replace('_', ' ').title()) if metric_obj else (metric_name or metric_code)
    category_val = metric_obj.get("category", "Operational Quality") if metric_obj else "Operational Quality"

    # 2. Fetch data directly from the Supabase metric folder: report/latest/{module}/{metric}
    target_module = module_id or (mod.get("id") if mod else None)
    supabase_data = supabase_storage.get_metric_data(metric_title, module_identifier=target_module)
    if supabase_data.get("_source") == "none":
        supabase_data = supabase_storage.get_metric_data(metric_code, module_identifier=target_module)

    # 3. Dynamic overrides from Supabase folder:
    if supabase_data.get("_source") != "none":
        extracted = extract_metric_fields(supabase_data, default_b=metric_obj)
        company_val = extracted["company"]
        standard_val = extracted["standard"]
        status_val = extracted["status"]
        variance_val = extracted["variance"]
        detailed_analysis = extracted["detailedAnalysis"]
        module_overview = extracted.get("moduleOverview", {})
    else:
        company_val = metric_obj.get("company", "0%") if metric_obj else "0%"
        standard_val = metric_obj.get("standard", "≥ 90.0%") if metric_obj else "≥ 90.0%"
        status_val = metric_obj.get("status", "At Risk") if metric_obj else "At Risk"
        variance_val = metric_obj.get("variance", "0%") if metric_obj else "0%"
        detailed_analysis = metric_obj.get("detailedAnalysis", {}) if metric_obj else {}
        module_overview = metric_obj.get("moduleOverview", {}) if metric_obj else {}

    # Extract TreeSHAP factors and execution workstreams from Supabase JSON if available
    rep = supabase_data.get("report") if isinstance(supabase_data.get("report"), dict) else supabase_data
    factors_raw = rep.get("factors") or []
    stage_drivers = []
    segment_drivers = []
    shap_factors = []

    for f in factors_raw:
        if isinstance(f, dict):
            fname = f.get("factorName") or f.get("name") or "Operational Factor"
            pct = f.get("impactPct") or f.get("impact_pct") or 0
            val = f.get("avgFactorValue") or f.get("value") or ""
            entry = {
                "name": fname,
                "impact": f"+{pct}%" if "%" not in str(pct) else str(pct),
                "description": f"Contributes {pct}% to the variance gap (average {val})."
            }
            shap_factors.append(entry)
            if "Role" in fname or "Job" in fname or "Segment" in fname:
                segment_drivers.append(entry)
            else:
                stage_drivers.append(entry)

    # Fallback to direct keys if factors_raw was empty
    if not stage_drivers:
        stage_drivers = supabase_data.get("stageDrivers") or supabase_data.get("stage_drivers") or rep.get("stageDrivers") or rep.get("stage_drivers") or []
    if not segment_drivers:
        segment_drivers = supabase_data.get("segmentDrivers") or supabase_data.get("segment_drivers") or rep.get("segmentDrivers") or rep.get("segment_drivers") or []
    if not shap_factors:
        shap_factors = supabase_data.get("shapFactors") or supabase_data.get("shap_factors") or rep.get("shapFactors") or rep.get("shap_factors") or []

    raw_plan = (
        rep.get("plan") or
        rep.get("brdPlan") or
        rep.get("brd_plan") or
        supabase_data.get("plan") or
        supabase_data.get("brdPlan") or
        supabase_data.get("brd_plan") or
        {}
    )
    
    # 1. Map phases to phasedActivities
    raw_phases = raw_plan.get("phases") or raw_plan.get("phasedActivities") or []
    phased_activities = []
    for p_idx, p in enumerate(raw_phases):
        p_name = p.get("title") or p.get("phaseName") or p.get("phase") or f"Phase {p_idx + 1}"
        acts = []
        for a in p.get("activities", []):
            h = a.get("hours") or a.get("effort") or 8
            acts.append({
                "activity": a.get("activity") or a.get("title") or "",
                "owner": a.get("role") or a.get("owner") or "Specialist",
                "workstream": a.get("workstream") or a.get("id") or "-",
                "effort": f"{h} Hours" if isinstance(h, (int, float)) or "Hour" not in str(h) else str(h)
            })
        phased_activities.append({
            "phaseName": p_name,
            "milestone": p.get("milestone", ""),
            "deliverable": p.get("deliverable", ""),
            "activities": acts
        })

    # 2. Map roles to specialistManpower
    raw_roles = raw_plan.get("roles") or raw_plan.get("specialistManpower") or []
    specialist_manpower = []
    for r in raw_roles:
        h = r.get("hours") or r.get("effort") or 40
        specialist_manpower.append({
            "role": r.get("role") or "Specialist Consultant",
            "headcount": r.get("headcount") or r.get("count") or 1,
            "effort": f"{h} Person-Hours" if isinstance(h, (int, float)) or "Hour" not in str(h) else str(h)
        })

    tot_hours = raw_plan.get("totalHours") or raw_plan.get("totalEffortHours") or (
        sum(r.get("hours", 0) for r in raw_roles if isinstance(r.get("hours"), (int, float))) or 60
    )
    dur_weeks = raw_plan.get("durationWeeks") or raw_plan.get("timeline") or 5
    timeline_str = f"{dur_weeks} Weeks" if isinstance(dur_weeks, (int, float)) or "Week" not in str(dur_weeks) else str(dur_weeks)
    effort_str = f"{tot_hours} Total Hours" if isinstance(tot_hours, (int, float)) or "Hour" not in str(tot_hours) else str(tot_hours)

    # 3. Execution workstreams
    raw_ws = rep.get("workstreams") or supabase_data.get("workstreams") or raw_plan.get("executionWorkstreams") or []
    execution_workstreams = []
    if isinstance(raw_ws, list) and raw_ws:
        for i, ws in enumerate(raw_ws):
            fixes = ws.get("fixesFactors") or ws.get("fixesDrivers") or "Governance SLA"
            if isinstance(fixes, list):
                fixes = ", ".join(fixes) if fixes else "Operational SLA"
            execution_workstreams.append({
                "id": ws.get("id") or f"W{i + 1}",
                "remediationStep": ws.get("step") or ws.get("remediationStep") or "",
                "fixesDrivers": str(fixes)
            })
    else:
        for p in raw_phases:
            for a in p.get("activities", []):
                ws_id = a.get("workstream")
                if ws_id and ws_id != "-":
                    execution_workstreams.append({
                        "id": ws_id,
                        "remediationStep": a.get("activity") or a.get("title") or "",
                        "fixesDrivers": a.get("role") or "Operational Governance"
                    })

    # 4. Assumptions & Risks, Success Criteria, Target Outcome
    assumptions_and_risks = (
        rep.get("assumptionsAndRisks") or
        rep.get("assumptions_and_risks") or
        raw_plan.get("assumptionsAndRisks") or
        supabase_data.get("assumptionsAndRisks") or
        []
    )
    success_criteria = (
        rep.get("successCriteria") or
        rep.get("success_criteria") or
        raw_plan.get("successCriteria") or
        supabase_data.get("successCriteria") or
        []
    )
    target_outcome = (
        raw_plan.get("targetOutcome") or
        (module_overview.get("rootCause") if isinstance(module_overview, dict) else "") or
        (rep.get("diagnosis", {}).get("headline") if isinstance(rep.get("diagnosis"), dict) else "")
    )

    formatted_stage_drivers = [
        {
            "id": sd.get("id") or f"S{i + 1}",
            "driver": sd.get("driver") or sd.get("name") or f"Stage {i + 1}",
            "name": sd.get("name") or sd.get("driver") or f"Stage {i + 1}",
            "avgDays": sd.get("avgFactorValue") or sd.get("avgDays") or sd.get("impact") or "-",
            "share": sd.get("impact") or sd.get("share") or "-"
        }
        for i, sd in enumerate(stage_drivers)
    ]

    formatted_segment_drivers = [
        {
            "id": seg.get("id") or f"A{i + 1}",
            "driver": seg.get("driver") or seg.get("name") or f"Segment {i + 1}",
            "name": seg.get("name") or seg.get("driver") or f"Segment {i + 1}",
            "avgDays": seg.get("segmentAvgValue") or seg.get("avgDays") or seg.get("impact") or "-",
            "vsCompany": seg.get("impact") or seg.get("vsCompany") or "-"
        }
        for i, seg in enumerate(segment_drivers)
    ]

    normalized_brd = {
        **raw_plan,
        "specialistManpower": specialist_manpower,
        "phasedActivities": phased_activities,
        "executionWorkstreams": execution_workstreams,
        "stageDrivers": formatted_stage_drivers,
        "segmentDrivers": formatted_segment_drivers,
        "assumptionsAndRisks": assumptions_and_risks,
        "successCriteria": success_criteria,
        "timelineAndEffort": {
            "timeline": timeline_str,
            "totalEffort": effort_str
        },
        "timeline": timeline_str,
        "totalEffortHours": tot_hours,
        "totalEffortsDisplay": effort_str,
        "targetOutcome": target_outcome
    }

    return {
        "metric": {
            "metric": metric_title,
            "code": metric_code,
            "category": category_val,
            "company": str(company_val),
            "standard": str(standard_val),
            "status": status_val,
            "variance": str(variance_val),
            "moduleOverview": module_overview,
            "detailedAnalysis": detailed_analysis
        },
        "moduleOverview": module_overview,
        "stageDrivers": formatted_stage_drivers,
        "segmentDrivers": formatted_segment_drivers,
        "shapFactors": shap_factors,
        "brdPlan": normalized_brd,
        "source": supabase_data.get("_source", "supabase_storage"),
        "storageFolder": supabase_data.get("_metric_folder"),
        "storagePath": supabase_data.get("_storage_path"),
        "module": supabase_data.get("_module", target_module),
        "filesLoaded": supabase_data.get("_files_loaded", [])
    }

