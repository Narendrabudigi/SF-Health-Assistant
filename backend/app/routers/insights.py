from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from app.db.supabase_client import supabase_storage

router = APIRouter()

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
