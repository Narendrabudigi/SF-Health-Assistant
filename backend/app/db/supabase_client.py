import json
import logging
import re
import time
from typing import Optional, Dict, Any, List, Tuple
from app.config import settings
from app.db.mock_data import DEFAULT_ML_INSIGHTS, DEFAULT_MODULES

logger = logging.getLogger("sf_health.supabase")

# Initialize Supabase client
supabase_client = None
is_configured = False

resolved_url = settings.RESOLVED_SUPABASE_URL
if resolved_url and settings.SUPABASE_KEY and "your-project" not in resolved_url:
    try:
        from supabase import create_client, Client
        supabase_client = create_client(resolved_url, settings.SUPABASE_KEY)
        is_configured = True
        logger.info(f"Supabase client initialized successfully for URL: {resolved_url}")
    except Exception as e:
        logger.warning(f"Could not initialize Supabase client with URL '{resolved_url}': {e}")
        supabase_client = None
        is_configured = False
else:
    logger.info("Supabase credentials not configured or placeholder detected. Operating in local mode.")


def normalize_slug(text: str) -> str:
    """Normalize string into a clean lowercase slug for flexible matching."""
    if not text:
        return ""
    # Remove content inside parentheses (e.g. 'Attrition Rate (90-day)' -> 'attrition_rate')
    clean = re.sub(r'\(.*?\)', '', str(text))
    clean = re.sub(r'[^a-zA-Z0-9]+', '_', clean).strip('_').lower()
    return clean


def alphanumeric_key(text: str) -> str:
    """Strip all non-alphanumeric characters for whitespace/casing/hyphen-agnostic matching."""
    if not text:
        return ""
    clean = re.sub(r'\(.*?\)', '', str(text))
    return re.sub(r'[^a-zA-Z0-9]', '', clean).lower()


def normalize_missing_configurations(raw_cfgs: Any, mod_name: str = "EC", dq_checks: list = None) -> List[Dict[str, Any]]:
    """
    Normalizes any format of missing configuration / fields from Supabase ML pipeline:
    - dict with 'mandatoryFields' and 'normalFields' (e.g. EmployeeDataAccuracy)
    - dict with 'mandatory' and 'other' (e.g. FullFinalSettlementTimeliness)
    - list of dicts or field names
    - dataQuality.checks with affectedColumns for Completeness / MissingValues
    Maps every field into a structured specification with ID, Configuration Component,
    Missing Field Deficit, Severity, and Target Setting.
    """
    if isinstance(raw_cfgs, list) and raw_cfgs and isinstance(raw_cfgs[0], dict) and "setting" in raw_cfgs[0]:
        return raw_cfgs

    cfgs = []
    seen = set()
    mod_clean = str(mod_name or "EC").upper()
    mod_prefix = mod_clean[:2] if len(mod_clean) >= 2 else "EC"

    def get_component(field: str) -> str:
        f_low = field.lower()
        if any(k in f_low for k in ["name", "nationality", "authorization", "email", "gender", "dob", "birth", "personal"]):
            return "Employee Central Personal Information Portlet"
        if any(k in f_low for k in ["startdate", "hire", "class", "position", "unit", "division", "company", "legal", "cost", "job", "manager", "reportsto"]):
            return "Employee Central Job Information & Org Structures"
        if any(k in f_low for k in ["audit", "checked", "discrepancy", "accuracy", "rate", "status"]):
            return "Employee Central Data Quality & Audit Framework"
        if any(k in f_low for k in ["settle", "disburse", "exit", "terminat", "offboard", "fas"]):
            return "Offboarding Settlement & Payroll SLA"
        if any(k in f_low for k in ["onboard", "task", "milestone", "day1"]):
            return "Onboarding Journey Governance"
        return f"{mod_clean} Data Architecture"

    def add_cfg(field: Any, is_mandatory: bool):
        f_clean = str(field.get("field") if isinstance(field, dict) else field).strip()
        if not f_clean or f_clean.lower() in seen:
            return
        seen.add(f_clean.lower())
        idx = len(cfgs) + 1
        comp = get_component(f_clean)
        sev = "Critical" if is_mandatory else "Medium"
        title = f"Mandatory Field Missing: {f_clean}" if is_mandatory else f"Missing Field: {f_clean}"
        status = "Unpopulated Mandatory Field" if is_mandatory else "Unpopulated Field"
        setting = (
            f"Manage Business Configuration (BCUI) > Enable mandatory validation and data cleansing for '{f_clean}'"
            if is_mandatory else
            f"Manage Business Configuration (BCUI) > Configure attribute mapping and historical data migration for '{f_clean}'"
        )
        cfgs.append({
            "id": f"CFG-{mod_prefix}{idx:02d}",
            "component": comp,
            "field": f_clean,
            "fieldName": f_clean,
            "title": title,
            "status": status,
            "severity": sev,
            "setting": setting
        })

    # Case 1: Dict with categorization
    if isinstance(raw_cfgs, dict):
        # Prioritize mandatory lists first
        for cat, flist in raw_cfgs.items():
            if "mandat" in cat.lower() and isinstance(flist, list):
                for item in flist:
                    add_cfg(item, is_mandatory=True)
        # Then normal/other lists
        for cat, flist in raw_cfgs.items():
            if "mandat" not in cat.lower() and isinstance(flist, list):
                for item in flist:
                    add_cfg(item, is_mandatory=False)

    # Case 2: List of strings or dicts
    elif isinstance(raw_cfgs, list):
        for item in raw_cfgs:
            is_mand = bool(isinstance(item, dict) and item.get("severity") in ("Critical", "High"))
            add_cfg(item, is_mandatory=is_mand)

    # Case 3: Completeness checks from dataQuality if raw_cfgs had few or no fields
    if dq_checks and isinstance(dq_checks, list):
        for chk in dq_checks:
            if isinstance(chk, dict) and chk.get("category") in ("Completeness", "Schema", "MissingValues"):
                cols = chk.get("affectedColumns") or []
                if isinstance(cols, list):
                    for c in cols:
                        add_cfg(c, is_mandatory=False)

    return cfgs


class SupabaseStorageService:
    CACHE_TTL_SECONDS = 30  # 30-second cache prevents repeated round-trip scans; makes page reloads and navigation instant (2-5ms)

    def __init__(self):
        self.bucket_name = settings.SUPABASE_BUCKET_NAME or "Insights and Reports"
        self._cached_latest_root = None
        # In-memory cache: { cache_key: (timestamp, data) }
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def is_active(self) -> bool:
        return bool(supabase_client and is_configured)

    def invalidate_cache(self):
        """Clear all in-memory caches to force a fresh fetch from Supabase."""
        self._cache.clear()
        self._cached_latest_root = None
        logger.info("Supabase in-memory storage cache invalidated.")

    def _get_from_cache(self, key: str) -> Optional[Any]:
        if self.CACHE_TTL_SECONDS <= 0:
            return None
        if key in self._cache:
            ts, data = self._cache[key]
            if time.time() - ts < self.CACHE_TTL_SECONDS:
                return data
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Any):
        if self.CACHE_TTL_SECONDS > 0:
            self._cache[key] = (time.time(), data)

    def list_items(self, folder_path: str = "") -> List[Dict[str, Any]]:
        """List files and folders at given bucket path with caching."""
        if not self.is_active():
            return []
        
        path = folder_path.strip().strip('/')
        cache_key = f"list:{path}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        try:
            res = supabase_client.storage.from_(self.bucket_name).list(path)
            items = res or []
            self._set_cache(cache_key, items)
            return items
        except Exception as e:
            logger.warning(f"Failed to list Supabase path '{self.bucket_name}/{path}': {e}")
            return []

    def download_json(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Download and parse a JSON file directly without stale cache."""
        if not self.is_active():
            return None
        
        clean_path = file_path.strip().strip('/')
        cache_key = f"json:{clean_path}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        try:
            data_bytes = supabase_client.storage.from_(self.bucket_name).download(clean_path)
            if data_bytes:
                parsed = json.loads(data_bytes.decode('utf-8'))
                self._set_cache(cache_key, parsed)
                return parsed
        except Exception as e:
            logger.warning(f"Failed to download/parse '{clean_path}' from bucket '{self.bucket_name}': {e}")
        return None

    def get_latest_root(self) -> str:
        """
        Locates the 'latest' folder inside 'report' or 'reports'.
        Hierarchy expected: {bucket}/report/latest/ or {bucket}/reports/latest/
        """
        if self._cached_latest_root:
            return self._cached_latest_root

        candidates = [
            "report/latest",
            "reports/latest",
            "report",
            "reports",
            "latest"
        ]

        for path in candidates:
            items = self.list_items(path)
            if items:
                has_latest_sub = any(i.get("name") == "latest" for i in items)
                if has_latest_sub:
                    self._cached_latest_root = f"{path}/latest"
                    return self._cached_latest_root
                if path.endswith("latest"):
                    self._cached_latest_root = path
                    return self._cached_latest_root

        self._cached_latest_root = "report/latest"
        return self._cached_latest_root

    def list_available_modules(self) -> List[str]:
        """Lists all module folders found inside 'latest' (e.g. ['rcm'])."""
        root = self.get_latest_root()
        items = self.list_items(root)
        modules = [
            item.get("name") for item in items 
            if isinstance(item, dict) and item.get("name") and not item.get("name").startswith(".")
        ]
        return modules

    def find_module_folder(self, module_identifier: str) -> Optional[str]:
        """Finds the matching module folder inside 'latest/'."""
        if not module_identifier:
            return None

        available_modules = self.list_available_modules()
        target_norm = module_identifier.lower().strip()
        target_slug = normalize_slug(module_identifier)

        for mod_folder in available_modules:
            mf_norm = mod_folder.lower().strip()
            mf_slug = normalize_slug(mod_folder)

            if target_norm == mf_norm or target_slug == mf_slug or target_norm in mf_norm or mf_norm in target_norm:
                return mod_folder

        return None

    def list_metrics_for_module(self, module_folder: str) -> List[Dict[str, Any]]:
        """Lists all metric folders/files inside '{latest_root}/{module_folder}'."""
        root = self.get_latest_root()
        module_path = f"{root}/{module_folder}"
        return self.list_items(module_path)

    def get_all_module_metric_overrides(self, force_refresh: bool = False) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Fast in-memory cached scan of all modules under 'report/latest/'.
        Extracts every metric folder and file inside each module!
        Returns: { module_id: { metric_identifier: data } }
        """
        if force_refresh:
            self.invalidate_cache()

        cache_key = "all_module_overrides"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        if not self.is_active():
            return {}

        root = self.get_latest_root()
        module_folders = self.list_available_modules()
        all_overrides = {}

        for mod_folder in module_folders:
            mod_key = mod_folder.lower().strip()
            k_clean = alphanumeric_key(mod_key)
            
            # Module aliases: strictly check exact tokens so 'ec' is never confused with 'recruitment'
            if k_clean in {"rcm", "recruitment", "recruiting"}:
                mod_aliases = ["rcm", "recruitment", "recruiting"]
            elif k_clean in {"ec", "employeecentral", "employee_central"}:
                mod_aliases = ["ec", "employeecentral", "employee_central"]
            elif k_clean in {"onb", "onb2", "onboarding"}:
                mod_aliases = ["onb", "onb2", "onboarding"]
            elif k_clean in {"ofb", "ofb2", "offboarding"}:
                mod_aliases = ["ofb", "ofb2", "offboarding"]
            else:
                mod_aliases = [mod_key, normalize_slug(mod_key), alphanumeric_key(mod_key)]

            mod_dict = all_overrides.get(mod_key, {})
            for alias in set(mod_aliases):
                if alias:
                    all_overrides[alias] = mod_dict

            metric_items = self.list_metrics_for_module(mod_folder)
            for m_item in metric_items:
                m_name = m_item.get("name", "")
                if not m_name or m_name.startswith("."):
                    continue

                item_path = f"{root}/{mod_folder}/{m_name}"

                def register_metric_data(dict_target: dict, raw_k: str, payload: dict):
                    clean_k = raw_k.replace('.json', '').strip()
                    dict_target[clean_k] = payload
                    dict_target[clean_k.lower()] = payload
                    dict_target[normalize_slug(clean_k)] = payload
                    dict_target[alphanumeric_key(clean_k)] = payload
                    
                    rep_inner = payload.get("report") if isinstance(payload.get("report"), dict) else {}
                    for alt_name in [
                        payload.get("metric_name"),
                        payload.get("metric"),
                        rep_inner.get("metricName"),
                        rep_inner.get("metric_name"),
                        payload.get("metric_code")
                    ]:
                        if alt_name:
                            alt_str = str(alt_name).strip()
                            dict_target[alt_str] = payload
                            dict_target[alt_str.lower()] = payload
                            dict_target[normalize_slug(alt_str)] = payload
                            dict_target[alphanumeric_key(alt_str)] = payload

                # Case A: m_item is directly a .json file (e.g. "TimeToHire.json")
                if m_name.lower().endswith(".json"):
                    data = self.download_json(item_path)
                    if data and isinstance(data, dict):
                        data["_storage_path"] = item_path
                        data["_metric_folder"] = m_name.replace('.json', '')
                        data["_module"] = mod_folder
                        data["_source"] = "supabase_storage_metric_folder"
                        if m_item.get("updated_at"):
                            data["updated_at"] = m_item.get("updated_at")
                            data["generated_at"] = m_item.get("updated_at")
                        register_metric_data(mod_dict, m_name, data)
                    continue

                # Case B: m_item is a folder named after the metric (e.g. "Time to hire")
                files = self.list_items(item_path)
                merged_data: Dict[str, Any] = {}
                loaded_files = []

                for f in files:
                    fname = f.get("name", "")
                    if fname.lower().endswith(".json"):
                        f_path = f"{item_path}/{fname}"
                        f_data = self.download_json(f_path)
                        if f_data and isinstance(f_data, dict):
                            merged_data.update(f_data)
                            loaded_files.append(fname)
                            if f.get("updated_at") and not merged_data.get("updated_at"):
                                merged_data["updated_at"] = f.get("updated_at")
                                merged_data["generated_at"] = f.get("updated_at")

                if merged_data:
                    merged_data["_storage_path"] = item_path
                    merged_data["_metric_folder"] = m_name
                    merged_data["_module"] = mod_folder
                    merged_data["_files_loaded"] = loaded_files
                    merged_data["_source"] = "supabase_storage_metric_folder"
                    register_metric_data(mod_dict, m_name, merged_data)

        def get_mod_aliases(mod_raw: str) -> List[str]:
            mod_k = str(mod_raw or "").lower().strip()
            k_clean = alphanumeric_key(mod_k)
            if k_clean in {"rcm", "recruitment", "recruiting"}:
                return ["rcm", "recruitment", "recruiting"]
            elif k_clean in {"ec", "employeecentral", "employee_central", "hr"}:
                return ["ec", "employeecentral", "employee_central", "hr"]
            elif k_clean in {"onb", "onb2", "onboarding"}:
                return ["onb", "onb2", "onboarding"]
            elif k_clean in {"ofb", "ofb2", "offboarding"}:
                return ["ofb", "ofb2", "offboarding"]
            elif k_clean in {"ecp", "payroll"}:
                return ["ecp", "payroll"]
            return [mod_k, normalize_slug(mod_k), alphanumeric_key(mod_k)]

        def get_mod_dict(mod_raw: str) -> dict:
            aliases = get_mod_aliases(mod_raw)
            primary = aliases[0]
            if primary not in all_overrides:
                new_dict = {}
                for a in aliases:
                    all_overrides[a] = new_dict
                return new_dict
            mod_dict = all_overrides[primary]
            for a in aliases:
                all_overrides[a] = mod_dict
            return mod_dict

        # 1. Query ML_Notebook_Insights (with fallback to ml_insights)
        if supabase_client:
            for tbl_name in ["ML_Notebook_Insights", "ml_insights"]:
                try:
                    ml_res = supabase_client.table(tbl_name).select("*").order("created_at", desc=True).limit(50).execute()
                    ml_rows = ml_res.data or []
                    if not ml_rows:
                        continue
                    logger.info(f"Loaded {len(ml_rows)} rows from Supabase table '{tbl_name}'")
                    for row in ml_rows:
                        mod_raw = row.get("Module_Name") or row.get("module") or "EC"
                        m_name_raw = row.get("Metric_Name") or row.get("metric_name") or ""
                        if not m_name_raw:
                            continue
                        
                        jr = row.get("JSON_Result") or row.get("insight_data") or {}
                        
                        # Process ML Notebook JSON_Result fields
                        company_val = jr.get("companyValue")
                        std_val = jr.get("industryStandardValue")
                        health_state = jr.get("healthState")
                        unit_str = str(jr.get("unit") or "").strip()
                        higher_is_better = jr.get("higherIsBetter", False)
                        variance_obj = jr.get("variance") or {}
                        rca_obj = jr.get("rca") or {}
                        factors_raw = rca_obj.get("factors") or []
                        data_qual = jr.get("dataQuality") or {}
                        trend_obj = jr.get("trendAnalysis") or {}
                        forecast_obj = jr.get("forecast") or {}
                        missing_cfgs = jr.get("missingConfigurations") or jr.get("missingConfiguration") or {}

                        # Older ml_insights schema fallback (executive_summary)
                        exec_summ = jr.get("executive_summary") or {}
                        if company_val is None and exec_summ:
                            company_val = exec_summ.get("actual_cycle_time") or exec_summ.get("actual_time_to_hire")
                        if std_val is None and exec_summ:
                            std_val = exec_summ.get("company_standard") or exec_summ.get("industry_benchmark")
                        if not health_state and exec_summ:
                            health_state = exec_summ.get("actual_health_status")
                        if not variance_obj and exec_summ:
                            variance_obj = exec_summ.get("prediction_variance")

                        # Format company display value
                        if company_val is not None:
                            c_str = str(company_val).strip()
                            if "%" in unit_str or unit_str.lower() == "percentage":
                                company_display = f"{c_str}%" if "%" not in c_str else c_str
                            elif unit_str:
                                company_display = f"{c_str} {unit_str}" if unit_str not in c_str else c_str
                            else:
                                company_display = c_str
                        else:
                            rec_analyzed = data_qual.get("recordsAnalysed", 0)
                            company_display = f"No Data ({rec_analyzed} Records)" if rec_analyzed == 0 else "N/A"

                        # Format standard display value
                        if std_val is not None:
                            s_str = str(std_val).strip()
                            if "%" in unit_str or unit_str.lower() == "percentage":
                                std_clean = f"{s_str}%" if "%" not in s_str else s_str
                            elif unit_str:
                                std_clean = f"{s_str} {unit_str}" if unit_str not in s_str else s_str
                            else:
                                std_clean = s_str
                            op = "≥" if higher_is_better else "≤"
                            standard_display = f"{op} {std_clean}" if not std_clean.startswith(('≤', '≥', '<', '>')) else std_clean
                        else:
                            standard_display = "Not yet fetched"

                        # Status formatting
                        h_lower = str(health_state or "").lower()
                        if "crit" in h_lower:
                            status_display = "Critical"
                        elif "risk" in h_lower or "warn" in h_lower or "breach" in h_lower:
                            status_display = "At Risk"
                        elif "health" in h_lower or "track" in h_lower or "ok" in h_lower or "good" in h_lower:
                            status_display = "Healthy"
                        elif "unknown" in h_lower or company_val is None:
                            status_display = "At Risk" if data_qual.get("overallRating") == "poor" else "Unknown"
                        else:
                            status_display = "Healthy"

                        # Variance formatting
                        if isinstance(variance_obj, dict):
                            v_val = variance_obj.get("value")
                            v_pct = variance_obj.get("percentage")
                            if v_val is not None and v_pct is not None:
                                try:
                                    sign = "+" if float(v_val) > 0 else ""
                                    variance_display = f"{sign}{v_val} ({sign}{v_pct}%)"
                                except Exception:
                                    variance_display = f"{v_val} ({v_pct}%)"
                            elif v_val is not None:
                                try:
                                    sign = "+" if float(v_val) > 0 else ""
                                    variance_display = f"{sign}{v_val}"
                                except Exception:
                                    variance_display = str(v_val)
                            else:
                                variance_display = "N/A (Data Gap)"
                        elif variance_obj:
                            variance_display = str(variance_obj)
                        else:
                            variance_display = "N/A (Data Gap)"

                        # Normalize missingConfigurations / missingConfiguration using unified multi-format normalizer
                        normalized_missing_cfgs = normalize_missing_configurations(
                            missing_cfgs,
                            mod_name=mod_raw,
                            dq_checks=data_qual.get("checks")
                        )

                        # Extract suggestions ONLY if explicitly present in Supabase JSON
                        raw_sug = jr.get("suggestions") or row.get("suggestions") or []
                        suggestions = list(raw_sug) if isinstance(raw_sug, list) else ([raw_sug] if raw_sug else [])

                        factor_summaries = []
                        for f in factors_raw:
                            if isinstance(f, dict):
                                fname = f.get("factorName") or f.get("name")
                                fpct = f.get("impactPct")
                                if fname:
                                    factor_summaries.append(f"{fname} ({fpct}%)" if fpct else str(fname))
                        
                        dq_checks = data_qual.get("checks") or []
                        dq_failures = [c for c in dq_checks if isinstance(c, dict) and c.get("failedRecords")]

                        if factor_summaries:
                            root_cause_display = f"Primary drivers: {', '.join(factor_summaries[:3])}."
                        elif dq_failures:
                            fail_reasons = [f"{c.get('failedRecords')} records missing '{', '.join(c.get('affectedColumns') or [])}'" for c in dq_failures]
                            root_cause_display = f"Data completeness breach: {'; '.join(fail_reasons)}. 0 records could be evaluated against the benchmark standard."
                        elif exec_summ.get("primary_root_cause"):
                            root_cause_display = exec_summ.get("primary_root_cause")
                        elif data_qual.get("recordsAnalysed") is not None:
                            root_cause_display = f"Evaluated across {data_qual.get('recordsAnalysed')} records (Data Quality: {data_qual.get('overallRating', 'fair')})."
                        else:
                            root_cause_display = "Data analyzed from live telemetry pipeline."

                        trend_summary_text = trend_obj.get("summary") or trend_obj.get("macro_trajectory") or f"Trend direction is {trend_obj.get('direction', 'flat')}."
                        affected_area_display = jr.get("affectedArea") or jr.get("affected_area") or (f"SuccessFactors {mod_raw} architecture touchpoints ({len(normalized_missing_cfgs)} unmapped fields flagged)." if normalized_missing_cfgs else "")

                        parsed_ml_entry = {
                            **row,
                            "company": company_display,
                            "standard": standard_display,
                            "status": status_display,
                            "variance": variance_display,
                            "moduleOverview": {
                                "rootCause": root_cause_display,
                                "affectedArea": affected_area_display,
                                "suggestions": suggestions
                            },
                            "detailedAnalysis": {
                                "whyItHappens": root_cause_display,
                                "whereItHappens": affected_area_display,
                                "howToOvercome": suggestions,
                                "trendAnalysis": {
                                    "summary": trend_summary_text,
                                    "points": trend_obj.get("periods") or []
                                },
                                "missingConfigurations": normalized_missing_cfgs
                            },
                            "missingConfigurations": normalized_missing_cfgs,
                            "factors": factors_raw,
                            "stageDrivers": factors_raw,
                            "dataQuality": data_qual,
                            "trendAnalysis": trend_obj,
                            "forecast": forecast_obj,
                            "report": {
                                "metricName": m_name_raw,
                                "healthState": status_display.lower(),
                                "factors": factors_raw,
                                "moduleOverview": {
                                    "rootCause": root_cause_display,
                                    "affectedArea": affected_area_display,
                                    "suggestions": suggestions
                                },
                                "diagnosis": {
                                    "headline": f"{m_name_raw} is {status_display} at {company_display} (Standard: {standard_display}).",
                                    "narrative": root_cause_display
                                }
                            },
                            "_source": "supabase_ml_notebook_insights_table",
                            "_table": tbl_name,
                            "isSupabaseLive": True
                        }

                        mod_dict = get_mod_dict(mod_raw)
                        register_metric_data(mod_dict, m_name_raw, parsed_ml_entry)
                    break
                except Exception as e:
                    logger.warning(f"Could not load ML table '{tbl_name}' from Supabase: {e}")

        # 2. Query LLM_Reports_Latest (with fallback to LLM_Reports)
        if supabase_client:
            for tbl_name in ["LLM_Reports_Latest", "LLM_Reports"]:
                try:
                    llm_res = supabase_client.table(tbl_name).select("*").order("generated_at", desc=True).limit(50).execute()
                    llm_rows = llm_res.data or []
                    if not llm_rows:
                        continue
                    logger.info(f"Loaded {len(llm_rows)} rows from Supabase table '{tbl_name}'")
                    for row in llm_rows:
                        mod_raw = row.get("module") or row.get("Module") or row.get("Module_Name") or "rcm"
                        m_name_raw = row.get("metric_name") or row.get("Metric_Name") or row.get("metric") or row.get("MetricName") or ""
                        rep_payload = row.get("report") if isinstance(row.get("report"), dict) else {}
                        
                        # Merge row metadata with report payload
                        combined = {**row, **rep_payload}
                        combined["_source"] = "supabase_llm_reports_table"
                        combined["_table"] = tbl_name
                        combined["isSupabaseLive"] = True

                        mod_dict = get_mod_dict(mod_raw)

                        # Find existing entry (from storage file or ML Notebook Insights)
                        current_entry = mod_dict.get(m_name_raw) or mod_dict.get(m_name_raw.lower()) or mod_dict.get(alphanumeric_key(m_name_raw))
                        if not current_entry:
                            register_metric_data(mod_dict, m_name_raw, combined)
                        else:
                            # Intelligently merge LLM plan and ML notebook insights, giving precedence to direct storage files
                            cur_rep = current_entry.get("report") if isinstance(current_entry.get("report"), dict) else current_entry
                            comb_rep = combined.get("report") if isinstance(combined.get("report"), dict) else combined

                            cur_overview = cur_rep.get("moduleOverview") or cur_rep.get("module_overview") or current_entry.get("moduleOverview") or {}
                            comb_overview = comb_rep.get("moduleOverview") or comb_rep.get("module_overview") or combined.get("moduleOverview") or {}

                            # Extract dynamic workstreams from storage and table
                            cur_ws = current_entry.get("workstreams") or cur_rep.get("workstreams") or []
                            cur_ws_steps = []
                            if isinstance(cur_ws, list) and cur_ws:
                                cur_ws_steps = [
                                    w.get("step") or w.get("remediationStep") or w.get("title")
                                    for w in cur_ws
                                    if isinstance(w, dict) and (w.get("step") or w.get("remediationStep") or w.get("title")) and w.get("kind") != "data"
                                ]
                                if not cur_ws_steps:
                                    cur_ws_steps = [
                                        w.get("step") or w.get("remediationStep") or w.get("title")
                                        for w in cur_ws
                                        if isinstance(w, dict) and (w.get("step") or w.get("remediationStep") or w.get("title"))
                                    ]

                            comb_ws = combined.get("workstreams") or comb_rep.get("workstreams") or []
                            comb_ws_steps = []
                            if isinstance(comb_ws, list) and comb_ws:
                                comb_ws_steps = [
                                    w.get("step") or w.get("remediationStep") or w.get("title")
                                    for w in comb_ws
                                    if isinstance(w, dict) and (w.get("step") or w.get("remediationStep") or w.get("title")) and w.get("kind") != "data"
                                ]
                                if not comb_ws_steps:
                                    comb_ws_steps = [
                                        w.get("step") or w.get("remediationStep") or w.get("title")
                                        for w in comb_ws
                                        if isinstance(w, dict) and (w.get("step") or w.get("remediationStep") or w.get("title"))
                                    ]

                            cur_sug = (
                                (cur_ws_steps if cur_ws_steps else None) or
                                current_entry.get("suggestions") or
                                cur_rep.get("suggestions") or
                                cur_overview.get("suggestions")
                            )
                            comb_sug = (
                                (comb_ws_steps if comb_ws_steps else None) or
                                combined.get("suggestions") or
                                comb_rep.get("suggestions") or
                                comb_overview.get("suggestions")
                            )

                            merged_overview = {**comb_overview, **cur_overview}
                            if cur_sug:
                                merged_overview["suggestions"] = cur_sug
                            elif comb_sug:
                                merged_overview["suggestions"] = comb_sug

                            final_item = {**combined, **current_entry}
                            if merged_overview:
                                final_item["moduleOverview"] = merged_overview
                            if cur_sug:
                                final_item["suggestions"] = cur_sug
                                if isinstance(final_item.get("report"), dict):
                                    final_item["report"]["suggestions"] = cur_sug
                            elif comb_sug:
                                final_item["suggestions"] = comb_sug
                                if isinstance(final_item.get("report"), dict):
                                    final_item["report"]["suggestions"] = comb_sug

                            # Preserve ML factors, workstreams, data quality, businessImpact & plan
                            if current_entry.get("workstreams"):
                                final_item["workstreams"] = current_entry.get("workstreams")
                            if current_entry.get("plan"):
                                final_item["plan"] = current_entry.get("plan")
                            if not final_item.get("businessImpact") and current_entry.get("businessImpact"):
                                final_item["businessImpact"] = current_entry.get("businessImpact")
                            if not final_item.get("factors") and current_entry.get("factors"):
                                final_item["factors"] = current_entry.get("factors")
                            if not final_item.get("trendAnalysis") and current_entry.get("trendAnalysis"):
                                final_item["trendAnalysis"] = current_entry.get("trendAnalysis")
                            if not final_item.get("dataQuality") and current_entry.get("dataQuality"):
                                final_item["dataQuality"] = current_entry.get("dataQuality")

                            final_item["isSupabaseLive"] = True
                            register_metric_data(mod_dict, m_name_raw, final_item)
                    break
                except Exception as e:
                    logger.warning(f"Could not load LLM table '{tbl_name}' from Supabase: {e}")

        # Store in cache
        self._set_cache(cache_key, all_overrides)
        return all_overrides

    def get_metric_data(
        self,
        metric_identifier: str,
        module_identifier: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves metric data from cache or Supabase hierarchy:
        report/latest/{module}/{metric}/
        """
        # Fast path: check module overrides cache
        all_overrides = self.get_all_module_metric_overrides()
        
        target_norm = metric_identifier.lower().strip()
        target_slug = normalize_slug(metric_identifier)
        target_alpha = alphanumeric_key(metric_identifier)

        # Check in specified module or across all modules
        mod_keys = []
        if module_identifier:
            m_id = str(module_identifier).lower().strip()
            aliases = [m_id, normalize_slug(m_id), alphanumeric_key(m_id)]
            k_clean = alphanumeric_key(m_id)
            if k_clean in {"rcm", "recruitment", "recruiting"}:
                aliases = ["rcm", "recruitment", "recruiting"]
            elif k_clean in {"ec", "employeecentral", "employee_central", "hr"}:
                aliases = ["ec", "employeecentral", "employee_central", "hr"]
            elif k_clean in {"onb", "onb2", "onboarding"}:
                aliases = ["onb", "onb2", "onboarding"]
            elif k_clean in {"ofb", "ofb2", "offboarding"}:
                aliases = ["ofb", "ofb2", "offboarding"]
            elif k_clean in {"ecp", "payroll"}:
                aliases = ["ecp", "payroll"]

            for a in aliases:
                if a in all_overrides and a not in mod_keys:
                    mod_keys.append(a)

        # If module was specified but not found in Supabase, do NOT leak other modules
        if not mod_keys:
            if not module_identifier:
                mod_keys = list(all_overrides.keys())
            else:
                return {
                    "_source": "none",
                    "metric_name": metric_identifier,
                    "_note": f"Module '{module_identifier}' has no data in Supabase."
                }

        for m_key in mod_keys:
            mod_dict = all_overrides.get(m_key, {})
            # 1. Exact match
            if metric_identifier in mod_dict:
                return mod_dict[metric_identifier]
            if target_norm in mod_dict:
                return mod_dict[target_norm]
            # 2. Slug match
            if target_slug in mod_dict:
                return mod_dict[target_slug]
            # 3. Alphanumeric match (case & whitespace insensitive)
            if target_alpha in mod_dict:
                return mod_dict[target_alpha]
            # 4. High-confidence specific match
            for k, val in mod_dict.items():
                k_slug = normalize_slug(k)
                k_alpha = alphanumeric_key(k)
                if k_alpha == target_alpha or k_slug == target_slug:
                    return val
                if len(k_alpha) >= 10 and (
                    target_alpha.startswith(k_alpha) or
                    target_alpha.endswith(k_alpha) or
                    k_alpha.startswith(target_alpha) or
                    k_alpha.endswith(target_alpha)
                ):
                    return val

        return {
            "_source": "none",
            "metric_name": metric_identifier,
            "_note": f"Metric '{metric_identifier}' not found in Supabase Storage."
        }

    def check_connection(self) -> Dict[str, Any]:
        """Diagnostic summary of connection and discovered modules/metrics under report/latest."""
        if not self.is_active():
            return {
                "status": "unconfigured",
                "message": "Supabase credentials are not configured in backend/.env",
                "configured": False,
                "bucket_name": self.bucket_name,
                "latest_root": self.get_latest_root(),
                "modules": []
            }

        try:
            root = self.get_latest_root()
            modules = self.list_available_modules()
            module_summary = []
            total_metrics_count = 0

            for mod in modules:
                metrics = self.list_metrics_for_module(mod)
                metric_names = [m.get("name") for m in metrics if isinstance(m, dict) and not m.get("name", "").startswith(".")]
                m_count = len(metric_names)
                total_metrics_count += m_count
                module_summary.append({
                    "module": mod,
                    "metrics_count": m_count,
                    "metrics": metric_names
                })

            return {
                "status": "connected",
                "message": f"Connected to Supabase bucket '{self.bucket_name}'. Found {len(modules)} module(s) under '{root}'.",
                "configured": True,
                "bucket_name": self.bucket_name,
                "latest_root": root,
                "modules_count": len(modules),
                "files_count": total_metrics_count,
                "modules": module_summary
            }
        except Exception as e:
            logger.error(f"Supabase connection test failed: {e}")
            return {
                "status": "error",
                "message": f"Error communicating with Supabase Storage: {str(e)}",
                "configured": True,
                "bucket_name": self.bucket_name,
                "latest_root": self.get_latest_root(),
                "modules": []
            }


# Singleton service instance
supabase_storage = SupabaseStorageService()
