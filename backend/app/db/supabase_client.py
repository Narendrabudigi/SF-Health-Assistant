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


class SupabaseStorageService:
    CACHE_TTL_SECONDS = 0  # 0 TTL disables caching so live edits in Supabase reflect immediately!

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

        # Also query Supabase LLM_Reports table to catch live pipeline generations!
        if supabase_client:
            try:
                llm_res = supabase_client.table("LLM_Reports").select("*").order("generated_at", desc=True).limit(50).execute()
                llm_rows = llm_res.data or []
                for row in llm_rows:
                    mod_raw = row.get("module") or "rcm"
                    m_name_raw = row.get("metric_name") or ""
                    rep_payload = row.get("report") if isinstance(row.get("report"), dict) else {}
                    
                    # Merge row metadata with report payload
                    combined = {**row, **rep_payload}
                    combined["_source"] = "supabase_llm_reports_table"
                    combined["_table"] = "LLM_Reports"
                    
                    mod_k = mod_raw.lower().strip()
                    k_clean = alphanumeric_key(mod_k)
                    if k_clean in {"rcm", "recruitment", "recruiting"}:
                        mod_aliases = ["rcm", "recruitment", "recruiting"]
                    elif k_clean in {"ec", "employeecentral", "employee_central"}:
                        mod_aliases = ["ec", "employeecentral", "employee_central"]
                    elif k_clean in {"onb", "onb2", "onboarding"}:
                        mod_aliases = ["onb", "onb2", "onboarding"]
                    elif k_clean in {"ofb", "ofb2", "offboarding"}:
                        mod_aliases = ["ofb", "ofb2", "offboarding"]
                    else:
                        mod_aliases = [mod_k, normalize_slug(mod_k), alphanumeric_key(mod_k)]

                    mod_dict = all_overrides.get(mod_k, {})
                    for alias in set(mod_aliases):
                        if alias:
                            all_overrides[alias] = mod_dict

                    # Find existing entry (from storage file or earlier row)
                    current_entry = mod_dict.get(m_name_raw) or mod_dict.get(m_name_raw.lower()) or mod_dict.get(alphanumeric_key(m_name_raw))
                    if not current_entry:
                        register_metric_data(mod_dict, m_name_raw, combined)
                    else:
                        # CRITICAL: Always preserve and prioritize user-defined moduleOverview!
                        cur_overview = current_entry.get("moduleOverview") or current_entry.get("module_overview")
                        comb_overview = combined.get("moduleOverview") or combined.get("module_overview")
                        
                        merged_overview = {}
                        if isinstance(cur_overview, dict):
                            merged_overview.update(cur_overview)
                        if isinstance(comb_overview, dict):
                            for k, v in comb_overview.items():
                                if v:  # only overwrite if non-empty
                                    merged_overview[k] = v

                        # Compare timestamps
                        cur_ts = str(current_entry.get("generated_at") or current_entry.get("updated_at") or "")
                        new_ts = str(row.get("generated_at") or "")
                        
                        if new_ts >= cur_ts:
                            final_item = {**current_entry, **combined}
                        else:
                            final_item = {**combined, **current_entry}

                        if merged_overview:
                            final_item["moduleOverview"] = merged_overview

                        register_metric_data(mod_dict, m_name_raw, final_item)
            except Exception as e:
                logger.warning(f"Could not load LLM_Reports from Supabase: {e}")

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
        mod_keys = [module_identifier.lower().strip()] if module_identifier and module_identifier.lower().strip() in all_overrides else list(all_overrides.keys())

        for m_key in mod_keys:
            mod_dict = all_overrides.get(m_key, {})
            # 1. Exact match
            if metric_identifier in mod_dict:
                return mod_dict[metric_identifier]
            # 2. Slug match
            if target_slug in mod_dict:
                return mod_dict[target_slug]
            # 3. Alphanumeric match (case & whitespace insensitive)
            if target_alpha in mod_dict:
                return mod_dict[target_alpha]
            # 4. Partial / flexible match
            for k, val in mod_dict.items():
                k_slug = normalize_slug(k)
                k_alpha = alphanumeric_key(k)
                if (len(k_slug) > 4 and (k_slug in target_slug or target_slug in k_slug)):
                    return val
                if (len(k_alpha) >= 4 and (k_alpha in target_alpha or target_alpha in k_alpha)):
                    return val

        # Fallback to pre-seeded defaults
        fb = DEFAULT_ML_INSIGHTS.get(metric_identifier)
        if fb:
            res = dict(fb)
            res["_source"] = "preseeded_dataset"
            return res

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
