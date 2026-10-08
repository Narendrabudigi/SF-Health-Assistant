import json
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from app.db.supabase_client import supabase_storage

router = APIRouter()


@router.get("/user-tables")
def get_user_tables():
    from app.db.supabase_client import supabase_client
    if not supabase_client:
        return {"error": "supabase_client not active"}
    res = {}
    for tbl in ["LLM_Reports_Latest", "ML_Notebook_Insights"]:
        try:
            q = supabase_client.table(tbl).select("*").order("created_at" if tbl == "ML_Notebook_Insights" else "generated_at", desc=True).limit(50).execute()
            rows_summary = []
            for r in (q.data or []):
                mod = r.get("Module_Name") or r.get("module") or r.get("Module")
                metric = r.get("Metric_Name") or r.get("metric_name") or r.get("MetricName")
                jr = r.get("JSON_Result") or r.get("report") or {}
                rows_summary.append({
                    "id": r.get("execution_id") or r.get("id"),
                    "module": mod,
                    "metric": metric,
                    "health": jr.get("healthState") or jr.get("health_state") or r.get("status"),
                    "companyValue": jr.get("companyValue") or jr.get("company_value"),
                    "standardValue": jr.get("industryStandardValue") or jr.get("standard")
                })
            res[tbl] = {
                "total": len(q.data or []),
                "keys": list((q.data[0] if q.data else {}).keys()),
                "first_row_sample": {k: (v if k != "report" and k != "JSON_Result" else list((v or {}).keys())) for k, v in (q.data[0] if q.data else {}).items()},
                "summary": rows_summary
            }
        except Exception as e:
            res[tbl] = {"error": str(e)}
    return res




@router.get("/status")
def get_supabase_storage_status():
    """
    Check the health of the connection to Supabase and inspect the metric folders under report/latest.
    """
    return supabase_storage.check_connection()

@router.get("/hierarchy")
def list_storage_hierarchy():
    """
    Inspect the full report/latest/{module}/{metric} hierarchy.
    """
    if not supabase_storage.is_active():
        return {
            "status": "unconfigured",
            "message": "Supabase client not configured in backend/.env",
            "modules": []
        }

    root = supabase_storage.get_latest_root()
    modules = supabase_storage.list_available_modules()
    details = []

    for mod in modules:
        metrics = supabase_storage.list_metrics_for_module(mod)
        metric_list = []
        for m in metrics:
            m_name = m.get("name", "")
            if not m_name or m_name.startswith("."):
                continue
            
            # Check files inside the metric folder
            m_files = supabase_storage.list_items(f"{root}/{mod}/{m_name}")
            metric_list.append({
                "metric_folder": m_name,
                "path": f"{root}/{mod}/{m_name}",
                "files_count": len(m_files),
                "files": [f.get("name") for f in m_files if isinstance(f, dict)]
            })

        details.append({
            "module_folder": mod,
            "module_path": f"{root}/{mod}",
            "metrics_count": len(metric_list),
            "metrics": metric_list
        })

    return {
        "bucket": supabase_storage.bucket_name,
        "latest_root": root,
        "modules_found": len(modules),
        "modules": details
    }

@router.get("/metric/{metric_identifier}")
def preview_metric_supabase_data(
    metric_identifier: str,
    module: Optional[str] = Query(None)
):
    """
    Test preview of what data is loaded from the Supabase folder for a specific metric.
    Usage: /api/v1/insights/metric/Average Time-to-Fill (Requisition Aging)?module=rcm
    """
    data = supabase_storage.get_metric_data(metric_identifier, module_identifier=module)
    return {
        "metric_searched": metric_identifier,
        "module": module,
        "data": data
    }

@router.get("/all-llm-reports")
def list_all_llm_reports():
    """
    List all reports currently stored in the Supabase LLM_Reports table.
    """
    from app.db.supabase_client import supabase_client
    if not supabase_client:
        return {"error": "Supabase client not initialized", "reports": []}
    try:
        res = supabase_client.table("LLM_Reports").select("id,module,metric_name,status,generated_at,report").order("generated_at", desc=True).limit(50).execute()
        return {"count": len(res.data or []), "reports": res.data or []}
    except Exception as e:
        return {"error": str(e), "reports": []}

@router.get("/debug-all")
def debug_all_supabase():
    """
    Explore all buckets, tables, and files in Supabase to see what is currently in Supabase.
    """
    from app.db.supabase_client import supabase_client
    if not supabase_client:
        return {"error": "Supabase client not initialized"}
    
    result = {"buckets": [], "tables": {}}
    try:
        buckets = supabase_client.storage.list_buckets()
        for b in buckets:
            b_name = b.name if hasattr(b, "name") else (b.get("name") if isinstance(b, dict) else str(b))
            files = []
            try:
                raw_files = supabase_client.storage.from_(b_name).list()
                files = [f.get("name") for f in raw_files if isinstance(f, dict)]
            except Exception as fe:
                files = [f"Error listing: {fe}"]
            result["buckets"].append({"name": b_name, "files": files})
    except Exception as be:
        result["buckets_error"] = str(be)

    # List detailed storage contents for Insights and Reports
    try:
        detailed_files = {}
        for b in ["Insights and Reports", "SF_Health_Raw_Data"]:
            try:
                tree = {}
                root_items = supabase_client.storage.from_(b).list()
                for item in (root_items or []):
                    iname = item.get("name") if isinstance(item, dict) else str(item)
                    if iname and not iname.startswith("."):
                        try:
                            sub_items = supabase_client.storage.from_(b).list(iname)
                            tree[iname] = [s.get("name") for s in (sub_items or []) if isinstance(s, dict)]
                            # If sub_item has folders, list one more level
                            for sub in (sub_items or []):
                                sname = sub.get("name")
                                if sname and not sname.endswith(".json") and not sname.endswith(".xlsx"):
                                    try:
                                        sub2 = supabase_client.storage.from_(b).list(f"{iname}/{sname}")
                                        tree[f"{iname}/{sname}"] = [s2.get("name") for s2 in (sub2 or []) if isinstance(s2, dict)]
                                    except Exception:
                                        pass
                        except Exception as se:
                            tree[iname] = str(se)
                detailed_files[b] = tree
            except Exception as be:
                detailed_files[b] = str(be)
        result["storage_tree"] = detailed_files
    except Exception as te:
        result["storage_tree_error"] = str(te)

    # Check tables
    candidate_tables = [
        "LLM_Reports_Latest", "llm_reports_latest",
        "ML_Notebook_Insights", "ml_notebook_insights",
        "LLM_Reports", "ml_insights", "benchmarks"
    ]
    for table_name in candidate_tables:
        try:
            res = supabase_client.table(table_name).select("*").limit(10).execute()
            if res.data:
                result["tables"][table_name] = res.data
        except Exception as e:
            result["tables"][f"{table_name}_error"] = str(e)

    return result


