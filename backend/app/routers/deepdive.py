from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any, List
from app.db.supabase_client import supabase_storage, normalize_slug, alphanumeric_key
from app.db.mock_data import DEFAULT_MODULES
from app.routers import modules

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
        extracted = modules.extract_metric_fields(supabase_data, default_b=metric_obj)
        company_val = supabase_data.get("company") if supabase_data.get("company") and supabase_data.get("company") != "Not yet fetched" else extracted["company"]
        standard_val = supabase_data.get("standard") if supabase_data.get("standard") and supabase_data.get("standard") != "Not yet fetched" else extracted["standard"]
        status_val = supabase_data.get("status") if supabase_data.get("status") and supabase_data.get("status") != "Not yet fetched" else extracted["status"]
        variance_val = supabase_data.get("variance") if supabase_data.get("variance") and supabase_data.get("variance") != "Not yet fetched" else extracted["variance"]
        detailed_analysis = extracted["detailedAnalysis"]
        supa_cfgs = supabase_data.get("missingConfigurations") or []
        ext_cfgs = detailed_analysis.get("missingConfigurations") or []
        chosen_cfgs = supa_cfgs if len(supa_cfgs) >= len(ext_cfgs) else ext_cfgs
        detailed_analysis["missingConfigurations"] = chosen_cfgs
        module_overview = extracted.get("moduleOverview", {})
        if supabase_data.get("moduleOverview") and isinstance(supabase_data["moduleOverview"], dict):
            module_overview = {**module_overview, **supabase_data["moduleOverview"]}
        is_live_supabase = True
    else:
        company_val = "Not yet fetched"
        standard_val = "Not yet fetched"
        status_val = "Not yet fetched"
        variance_val = "Not yet fetched"
        detailed_analysis = {
            "whyItHappens": "Data not yet fetched",
            "whereItHappens": "Data not yet fetched",
            "trendAnalysis": {"summary": "Data not yet fetched", "points": []},
            "missingConfigurations": [],
            "howItEffects": "Data not yet fetched",
            "howToOvercome": []
        }
        module_overview = {
            "rootCause": "Data not yet fetched",
            "affectedArea": "Data not yet fetched",
            "suggestions": []
        }
        is_live_supabase = False

    # Extract TreeSHAP factors and execution workstreams from Supabase JSON if available
    rep_nested = supabase_data.get("report") if isinstance(supabase_data.get("report"), dict) else {}
    rep = {**rep_nested, **supabase_data}
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

    # Prioritize top-level plan (e.g. 114 hours, 6 weeks) from Supabase over nested report plan
    raw_plan = (
        supabase_data.get("plan") or
        supabase_data.get("brdPlan") or
        supabase_data.get("brd_plan") or
        rep_nested.get("plan") or
        rep_nested.get("brdPlan") or
        rep_nested.get("brd_plan") or
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
        h = r.get("hours") or r.get("effort") or 0
        specialist_manpower.append({
            "role": r.get("role") or "Specialist Consultant",
            "headcount": r.get("headcount") or r.get("count") or 1,
            "effort": f"{h} Person-Hours" if isinstance(h, (int, float)) or "Hour" not in str(h) else str(h)
        })

    tot_hours = raw_plan.get("totalHours") or raw_plan.get("totalEffortHours")
    if not tot_hours and raw_roles:
        calculated_hours = sum(r.get("hours", 0) for r in raw_roles if isinstance(r.get("hours"), (int, float)))
        if calculated_hours > 0:
            tot_hours = calculated_hours

    dur_weeks = raw_plan.get("durationWeeks") or raw_plan.get("timeline")

    timeline_str = f"{dur_weeks} Weeks" if (isinstance(dur_weeks, (int, float)) and dur_weeks > 0) else (str(dur_weeks) if dur_weeks else "Not yet fetched")
    effort_str = f"{tot_hours} Total Hours" if (isinstance(tot_hours, (int, float)) and tot_hours > 0) else (str(tot_hours) if tot_hours else "Not yet fetched")

    # 3. Execution workstreams
    raw_ws = supabase_data.get("workstreams") or rep.get("workstreams") or raw_plan.get("executionWorkstreams") or []
    execution_workstreams = []
    ws_steps = []
    if isinstance(raw_ws, list) and raw_ws:
        for i, ws in enumerate(raw_ws):
            fixes = ws.get("fixesFactors") or ws.get("fixesDrivers") or "Governance SLA"
            if isinstance(fixes, list):
                fixes = ", ".join(fixes) if fixes else "Operational SLA"
            step_text = ws.get("step") or ws.get("remediationStep") or ws.get("title") or ""
            execution_workstreams.append({
                "id": ws.get("id") or f"W{i + 1}",
                "remediationStep": step_text,
                "fixesDrivers": str(fixes)
            })
            if step_text and ws.get("kind") != "data":
                ws_steps.append(step_text)
        if not ws_steps:
            ws_steps = [ws.get("remediationStep") for ws in execution_workstreams if ws.get("remediationStep")]
    elif is_live_supabase:
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
        (module_overview.get("rootCause") if isinstance(module_overview, dict) and module_overview.get("rootCause") not in ("Data not yet fetched", "Data not yet fetched from Supabase") else "") or
        (rep.get("diagnosis", {}).get("headline") if isinstance(rep.get("diagnosis"), dict) else "") or
        "Data not yet fetched"
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

    biz_impact = (
        rep.get("businessImpact") or
        supabase_data.get("businessImpact") or
        rep.get("business_impact") or
        supabase_data.get("business_impact") or
        detailed_analysis.get("businessImpact") or
        {}
    )
    business_impact_obj = {
        "overview": biz_impact.get("overview") or detailed_analysis.get("howItEffects", ""),
        "financialExposure": biz_impact.get("financialExposure") or biz_impact.get("financial_exposure", ""),
        "slaAndTurnaround": biz_impact.get("slaAndTurnaround") or biz_impact.get("sla_and_turnaround", ""),
        "governanceAndAudit": biz_impact.get("governanceAndAudit") or biz_impact.get("governance_and_audit", "")
    }
    detailed_analysis["businessImpact"] = business_impact_obj
    if business_impact_obj.get("overview"):
        detailed_analysis["howItEffects"] = business_impact_obj["overview"]

    normalized_brd = {
        **raw_plan,
        "phases": raw_phases,
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

    raw_diag = rep.get("diagnosis") or supabase_data.get("diagnosis") or {}
    headline_raw = raw_diag.get("headline", "")
    narrative_raw = raw_diag.get("narrative", "")

    # If headline contains "Not yet fetched" or is missing, regenerate it dynamically
    if not headline_raw or "Not yet fetched" in headline_raw:
        headline_raw = f"{metric_title} is {status_val} at {company_val} (Standard: {standard_val})."

    # If narrative was generic fallback, use moduleOverview root cause
    if narrative_raw in ("Data analyzed from Supabase ML pipeline.", "Data analyzed from ML pipeline.", "") and module_overview.get("rootCause") and module_overview.get("rootCause") not in ("Data not yet fetched", "Data not yet fetched from Supabase"):
        narrative_raw = module_overview.get("rootCause")

    diagnosis_obj = {
        "headline": headline_raw,
        "narrative": narrative_raw
    }

    if diagnosis_obj.get("narrative"):
        detailed_analysis["whyItHappens"] = diagnosis_obj["narrative"]
    if diagnosis_obj.get("headline"):
        detailed_analysis["headline"] = diagnosis_obj["headline"]

    raw_suggestions = (
        (ws_steps if ws_steps and len(ws_steps) > 0 else None) or
        (supabase_data.get("suggestions") if isinstance(supabase_data.get("suggestions"), list) and len(supabase_data["suggestions"]) > 0 else None) or
        (rep_nested.get("suggestions") if isinstance(rep_nested.get("suggestions"), list) and len(rep_nested["suggestions"]) > 0 else None) or
        (raw_diag.get("suggestions") if isinstance(raw_diag.get("suggestions"), list) and len(raw_diag["suggestions"]) > 0 else None) or
        module_overview.get("suggestions") or
        detailed_analysis.get("howToOvercome") or
        []
    )
    if raw_suggestions:
        module_overview["suggestions"] = raw_suggestions
        detailed_analysis["howToOvercome"] = raw_suggestions

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
            "detailedAnalysis": detailed_analysis,
            "diagnosis": diagnosis_obj,
            "suggestions": raw_suggestions,
            "businessImpact": business_impact_obj
        },
        "diagnosis": diagnosis_obj,
        "suggestions": raw_suggestions,
        "moduleOverview": module_overview,
        "businessImpact": business_impact_obj,
        "stageDrivers": formatted_stage_drivers,
        "segmentDrivers": formatted_segment_drivers,
        "shapFactors": shap_factors,
        "brdPlan": normalized_brd,
        "missingConfigurations": detailed_analysis.get("missingConfigurations", []),
        "dataQuality": supabase_data.get("dataQuality") or {},
        "source": supabase_data.get("_source", "supabase_storage"),
        "storageFolder": supabase_data.get("_metric_folder"),
        "storagePath": supabase_data.get("_storage_path"),
        "module": supabase_data.get("_module", target_module),
        "filesLoaded": supabase_data.get("_files_loaded", [])
    }


