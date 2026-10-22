import datetime
import io
import json
import math
import os
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
import xgboost as xgb

WORKSPACE_DIR = Path(__file__).resolve().parent

load_dotenv(WORKSPACE_DIR / ".env")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY", ""))
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "")
METRIC_FILE_PATH = os.getenv("METRIC_FILE_PATH", "")
CUSTOM_STANDARDS_FILE_PATH = os.getenv("CUSTOM_STANDARDS_FILE_PATH", "")
CUSTOM_INSIGHTS_TABLE = os.getenv("CUSTOM_INSIGHTS_TABLE", "")
SUPABASE_WRITE_ENABLED = os.getenv("SUPABASE_WRITE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
REPORT_VERSION = os.getenv("REPORT_VERSION", "2.2")
RANDOM_STATE = int(os.getenv("RANDOM_STATE", "42"))

try:
    from supabase import create_client
except ImportError:
    create_client = None

try:
    import shap
except ImportError:
    shap = None

METRICS: Dict[str, Dict[str, Any]] = {
    "EmployeeDataAccuracy": {"sheet": "Employee Data Accuracy"},
    "PositionManagementAccuracy": {"sheet": "Position Mgmt Accuracy"},
    "DataSyncErrorRate": {"sheet": "Data Sync Error Rate"},
}


def get_supabase_credentials() -> Tuple[str, str]:
    missing = [name for name, val in [("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_KEY)] if not val]
    if missing:
        raise RuntimeError(f"Missing required setting(s) in .env: {', '.join(missing)}.")
    return SUPABASE_URL, SUPABASE_KEY


def detect_metric_direction(
    metric_name: str,
    benchmark_str: Optional[str] = "",
    unit: Optional[str] = "",
) -> bool:
    bm, name = str(benchmark_str or "").strip(), str(metric_name or "").lower()
    if "<" in bm or any(k in name for k in ["error", "defect", "fail", "delay", "attrition"]):
        return False
    return True


def calculate_health_state(
    value: Optional[float],
    benchmark: Optional[float],
    higher_is_better: Optional[bool] = True,
    at_risk_threshold: Optional[float] = None,
) -> Tuple[Optional[str], Optional[float]]:
    if value is None or benchmark is None:
        return None, None
    try:
        val, bm = float(value), float(benchmark)
        if math.isnan(val) or math.isnan(bm):
            return None, None
    except (ValueError, TypeError):
        return None, None

    hib = True if higher_is_better is None else bool(higher_is_better)
    diff = (bm - val) if hib else (val - bm)
    breach_val = round(max(0.0, diff), 4)
    at_risk_band = at_risk_threshold if at_risk_threshold is not None else (5.0 if hib else 2.0)

    if breach_val == 0.0:
        return "healthy", 0.0
    return ("at-risk" if breach_val <= at_risk_band else "critical"), breach_val


def calculate_variance(
    value: Optional[float],
    benchmark: Optional[float],
    higher_is_better: Optional[bool] = True,
) -> Dict[str, Optional[float]]:
    if value is None or benchmark is None:
        return {"value": None, "percentage": None}

    try:
        val, bm = float(value), float(benchmark)

        if not math.isfinite(val) or not math.isfinite(bm):
            return {"value": None, "percentage": None}

        # Calculate the difference, accounting for metric direction.
        raw_diff = val - bm
        diff = -raw_diff if higher_is_better is False else raw_diff
        diff = round(diff, 2)

        # Calculate variance percentage relative to the benchmark.
        percentage = (
            round((diff / bm) * 100, 2)
            if bm != 0
            else None
        )

        return {
            "value": diff,
            "percentage": percentage,
        }

    except (ValueError, TypeError, OverflowError):
        return {"value": None, "percentage": None}


def preprocess_dataframe(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return df
    cleaned = df.copy()
    cleaned.columns = [str(c).strip() for c in cleaned.columns]
    null_strings = {"", "nan", "none", "null", "n/a", "na", "--", "-"}
    for col in cleaned.select_dtypes(include=["object", "string"]).columns:
        s_str = cleaned[col].astype(str).str.strip()
        cleaned[col] = cleaned[col].mask(s_str.str.lower().isin(null_strings), np.nan)
        non_null_mask = cleaned[col].notna()
        cleaned.loc[non_null_mask, col] = s_str[non_null_mask]
    return cleaned


def classify_outcome_label(val: Any) -> Optional[int]:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in {"1", "1.0", "true", "yes", "pass", "success", "accurate", "verified", "y", "t"}:
        return 1
    if s in {"0", "0.0", "false", "no", "fail", "failed", "error", "inaccurate", "n", "f"}:
        return 0
    if "resolved" in s:
        return 1
    if any(k in s for k in ["pass", "success", "accurate"]):
        return 1
    if any(k in s for k in ["fail", "error", "inaccurate"]):
        return 0
    return None


def is_historical_error_incident(val: Any) -> bool:
    if val is None or pd.isna(val):
        return False
    s = str(val).strip().lower()
    return s in {"0", "0.0", "false", "no", "fail", "failed", "error", "n", "f"} or any(k in s for k in ["fail", "error", "unsynced"])


def find_target_column(df: Optional[pd.DataFrame]) -> Optional[str]:
    if df is None or df.empty:
        return None
    excluded = ["requisition", "reqraised", "disability", "gender", "marital", "nationality", "citizen", "auth", "salary", "wage"]
    best_col, best_score = None, 0
    for col in df.columns:
        cl = str(col).strip().lower()
        if any(k in cl for k in excluded):
            continue
        is_target_kw = any(k in cl for k in ["accurate", "accuracy", "status", "result", "audit", "target", "flag"])
        s = df[col].dropna()
        if s.empty or not is_target_kw:
            continue
        unique_vals = list(s.unique())
        if 2 <= len(unique_vals) <= 20:
            mapped = [classify_outcome_label(v) for v in unique_vals]
            valid = [m for m in mapped if m is not None]
            pos, neg = sum(1 for m in valid if m == 1), sum(1 for m in valid if m == 0)
            if pos > 0 or neg > 0:
                score = len(valid) + (5 if (pos > 0 and neg > 0) else 0) + (10 if "accurate" in cl else 0)
                if score > best_score:
                    best_score, best_col = score, col
    return best_col


def get_date_columns(df: Optional[pd.DataFrame]) -> List[str]:
    if df is None or df.empty:
        return []
    return [c for c in df.columns if any(k in c.lower() for k in ["date", "time", "_at", "_dt", "timestamp"])]


def find_primary_date_column(df: Optional[pd.DataFrame]) -> Optional[str]:
    cols = get_date_columns(df)
    if not cols:
        return None
    valid_counts = {c: int(pd.to_datetime(df[c], errors="coerce").notna().sum()) for c in cols}
    best_col = max(valid_counts, key=valid_counts.get)
    return best_col if valid_counts[best_col] > 0 else None


def find_primary_entity_key(df: Optional[pd.DataFrame]) -> Optional[str]:
    if df is None or df.empty:
        return None
    id_cols = [c for c in df.columns if re.search(r"(?i)(?:^id$|[_\s]?id$|[_\s]?key$|[_\s]?code$)", str(c).strip())]
    return max(id_cols, key=lambda c: df[c].nunique()) if id_cols else df.columns[0]


def stage_1_load_data() -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any], Optional[pd.DataFrame]]:
    if create_client is None:
        raise ImportError("The 'supabase' package is required.")
    sb = create_client(*get_supabase_credentials())

    data_bytes = sb.storage.from_(SUPABASE_BUCKET).download(METRIC_FILE_PATH)
    sheets = pd.read_excel(io.BytesIO(data_bytes), sheet_name=None)
    raw_df_map = {m_id: sheets.get(cfg["sheet"]) for m_id, cfg in METRICS.items()}
    core_df = sheets.get("Core Fields")

    std_bytes = sb.storage.from_(SUPABASE_BUCKET).download(CUSTOM_STANDARDS_FILE_PATH)
    df_ind = pd.read_excel(io.BytesIO(std_bytes))

    standards = {}
    for m_id, cfg in METRICS.items():
        sheet_name = cfg.get("sheet", m_id)
        words = set(re.findall(r"\w+", sheet_name.lower()))
        scores = df_ind["Metric Name"].astype(str).str.lower().apply(
            lambda name: sum(w in set(re.findall(r"\w+", name)) for w in words)
        )
        if scores.max() >= 2:
            row = df_ind.loc[scores.idxmax()]
            bm = str(row["Industry Benchmark"])
            nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", bm)]
            metric_name = str(row["Metric Name"])
            unit = str(row.get("Unit", ""))
            standards[m_id] = {
                "value": round(sum(nums) / len(nums), 2) if nums else None,
                "higher_is_better": detect_metric_direction(metric_name, bm, unit),
                "unit": unit,
                "metric_name": metric_name,
            }
        else:
            standards[m_id] = {
                "value": None,
                "higher_is_better": detect_metric_direction(sheet_name, "", ""),
                "unit": "Percentage",
                "metric_name": sheet_name,
            }

    return raw_df_map, standards, core_df


def stage_2_data_quality_check(datasets_map: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    staleness_days = 1095
    now = pd.Timestamp.now()
    dq_report: Dict[str, Any] = {}

    for key, df in datasets_map.items():
        if df is None:
            continue

        n_rows = len(df)
        pk_col = find_primary_entity_key(df) or (df.columns[0] if n_rows else "id")
        target_col = find_target_column(df)

        null_counts = df.isna().sum()
        missing_by_col = {col: int(cnt) for col, cnt in null_counts[null_counts > 0].items()}
        total_missing_cells = int(null_counts.sum())
        affected_records = int(df.isna().any(axis=1).sum()) if n_rows else 0

        invalid_pattern = r"(?i)^(#value!|#ref!|#name\?|#n/a|undefined|\?+|error)$"
        invalid_by_col = {
            col: int(cnt) for col, cnt in df.select_dtypes(include=["object", "string"]).apply(
                lambda s: s.dropna().astype(str).str.strip().str.match(invalid_pattern).sum()
            ).items() if cnt > 0
        }
        tot_invalid = sum(invalid_by_col.values())
        pk_dups = int(df.duplicated(subset=[pk_col]).sum()) if (pk_col in df.columns and n_rows) else 0

        primary_date = find_primary_date_column(df)
        dates = pd.to_datetime(df[primary_date], errors="coerce").dropna() if primary_date else pd.Series(dtype="datetime64[ns]")
        stale_records = int(((now - dates[dates <= now]).dt.days > staleness_days).sum()) if not dates.empty else 0
        data_period = {
            "from": dates.min().strftime("%Y-%m-%d") if not dates.empty else None,
            "to": dates.max().strftime("%Y-%m-%d") if not dates.empty else None,
        }

        tot_issues = affected_records + tot_invalid + pk_dups + stale_records
        issue_ratio = tot_issues / max(1, n_rows * 4)
        overall_rating = "unknown" if n_rows == 0 else ("excellent" if tot_issues == 0 else ("good" if issue_ratio < 0.05 else ("fair" if issue_ratio < 0.25 else "poor")))

        def _chk(name: str, category: str, failed: int, cols: Optional[List[str]] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            chk = {
                "checkName": name,
                "category": category,
                "checkedRecords": n_rows,
                "failedRecords": int(failed),
                "failedPct": round(float(failed / max(1, n_rows) * 100), 2) if n_rows else 0.0,
                "affectedColumns": cols,
            }
            if extra:
                chk.update(extra)
            return chk

        mandatory_missing = []
        if pk_col and (pk_col not in df.columns or df[pk_col].dropna().empty):
            mandatory_missing.append(pk_col)

        if target_col is None:
            audit_candidates = [
                c for c in df.columns
                if any(k in c.lower() for k in ["audit", "status", "accuracy", "discrepancy"])
                and not any(k in c.lower() for k in ["date", "time", "id", "code", "middle", "auth", "class"])
            ]
            for c in audit_candidates:
                if df[c].dropna().empty and c not in mandatory_missing:
                    mandatory_missing.append(c)
        elif df[target_col].dropna().empty:
            mandatory_missing.append(target_col)

        dq_report[key] = {
            "dataQuality": {
                "overallRating": overall_rating,
                "dataPeriod": data_period,
                "recordsAnalysed": n_rows,
                "checks": [
                    _chk("MissingValues", "Completeness", affected_records, list(missing_by_col.keys()) or None, {"affectedCells": total_missing_cells}),
                    _chk("InvalidValues", "Validity", tot_invalid, list(invalid_by_col.keys()) or None),
                    _chk("DuplicateRecords", "Uniqueness", pk_dups, [pk_col] if pk_dups else None),
                    _chk("Staleness", "Staleness", stale_records, [primary_date] if primary_date else None, {"staleRange": "> 3 years old"}),
                ],
            },
            "missingConfigurations": {
                "mandatoryFieldsMissing": mandatory_missing,
                "otherFieldsMissing": [c for c in missing_by_col.keys() if c not in mandatory_missing],
            },
        }

    return dq_report


def stage_3_target_creation(
    df_map: Dict[str, pd.DataFrame],
    industry_standards: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any]]:
    merged_dfs = {}
    targets_summary = {}

    for m_id, df_raw in df_map.items():
        df = preprocess_dataframe(df_raw)
        if df is None:
            continue

        target_col = find_target_column(df)
        date_col = find_primary_date_column(df)
        std_info = (industry_standards or {}).get(m_id, {})
        std_val = std_info.get("value") if isinstance(std_info, dict) else std_info
        higher_better = std_info.get("higher_is_better") if isinstance(std_info, dict) and "higher_is_better" in std_info else detect_metric_direction(m_id)

        df_out = df.copy()
        anchor_date = None
        if date_col and date_col in df_out.columns and date_col != target_col:
            df_out[date_col] = pd.to_datetime(df_out[date_col], errors="coerce")
            valid_dates = df_out[date_col].dropna()
            if not valid_dates.empty:
                anchor_date = valid_dates.max()

        if target_col and df_out[target_col].notna().any():
            if not higher_better:
                error_mask = df_out[target_col].apply(is_historical_error_incident)
                valid_mask = df_out[target_col].notna()
                rate = round(float(error_mask[valid_mask].mean()) * 100.0, 2) if valid_mask.any() else None
                df_out["target"] = error_mask.astype(float)
            else:
                mapped = df_out[target_col].apply(classify_outcome_label)
                df_out["target"] = mapped.astype(float)
                valid_target = df_out["target"].dropna()
                rate = round(float(valid_target.mean()) * 100.0, 2) if not valid_target.empty else None
        else:
            df_out["target"] = np.nan
            rate = None

        merged_dfs[m_id] = df_out
        targets_summary[m_id] = {
            "target_col": target_col,
            "date_col": date_col,
            "anchor_date": anchor_date,
            "historical_rate_pct": rate,
            "std_val": std_val,
            "higher_is_better": higher_better,
        }

    return merged_dfs, targets_summary


def stage_4_feature_engineering(
    df_map: Dict[str, pd.DataFrame],
    core_df: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    def engineer_predictors(df: Optional[pd.DataFrame]) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        df_out = df.copy()
        if core_df is not None and not core_df.empty:
            for cand in ["employeeId", "employeeid", "emp_id", "userId"]:
                if cand in df_out.columns and cand in core_df.columns:
                    context_cols = [
                        c for c in [
                            "departmentName", "businessUnitName", "divisionName",
                            "jobRole", "jobLevel", "employeeGrade",
                            "locationCity", "employeeType", "employmentStatus"
                        ]
                        if c in core_df.columns and c not in df_out.columns
                    ]
                    if context_cols:
                        core_subset = core_df[[cand] + context_cols].drop_duplicates(subset=[cand])
                        df_out = df_out.merge(core_subset, on=cand, how="left")
                    break

        n_rows = len(df_out)
        for col in [c for c in get_date_columns(df_out) if c != "target"]:
            parsed_dt = df_out[col] if pd.api.types.is_datetime64_any_dtype(df_out[col]) else pd.to_datetime(df_out[col], errors="coerce")
            if parsed_dt.notna().sum() > 0.5 * n_rows:
                if parsed_dt.dt.hour.nunique() > 1:
                    df_out[f"{col}_hour"] = parsed_dt.dt.hour.fillna(-1).astype(int)
                dow = parsed_dt.dt.dayofweek.fillna(-1).astype(int)
                df_out[f"{col}_dayofweek"] = dow
                df_out[f"{col}_is_weekend"] = dow.isin([5, 6]).astype(int)

        return df_out

    return {m_id: engineer_predictors(df) for m_id, df in df_map.items()}


def _safe_split_train_val_test(
    data: Any,
    labels: Any,
    val_test_ratio: float,
    random_state: int = RANDOM_STATE,
) -> Tuple[Any, Any, Any]:
    strat = labels if (labels is not None and pd.Series(labels).value_counts().min() >= 2) else None
    try:
        tr, temp = train_test_split(data, test_size=val_test_ratio, random_state=random_state, stratify=strat)
    except Exception:
        tr, temp = train_test_split(data, test_size=val_test_ratio, random_state=random_state)

    if hasattr(labels, "loc"):
        temp_labels = labels.loc[temp].to_numpy()
    elif isinstance(data, pd.DataFrame) and isinstance(labels, pd.Series):
        temp_labels = temp[labels.name].to_numpy()
    else:
        temp_labels = None

    strat_temp = temp_labels if (temp_labels is not None and pd.Series(temp_labels).value_counts().min() >= 2) else None
    try:
        val, te = train_test_split(temp, test_size=0.5, random_state=random_state, stratify=strat_temp)
    except Exception:
        val, te = train_test_split(temp, test_size=0.5, random_state=random_state)

    return tr, val, te


def stage_5_train_val_test_split(
    df_map: Dict[str, pd.DataFrame],
    target_col: str = "target",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = RANDOM_STATE,
) -> Dict[str, Any]:
    splits: Dict[str, Any] = {}
    val_test_ratio = val_ratio + test_ratio

    for m_id, df in df_map.items():
        empty_split = {
            "df_tr": pd.DataFrame(), "df_val": pd.DataFrame(), "df_te": pd.DataFrame(),
            "y_tr": np.array([]), "y_val": np.array([]), "y_te": np.array([]),
        }
        if df is None or target_col not in df.columns:
            splits[m_id] = empty_split
            continue

        df_valid = df.dropna(subset=[target_col]).copy()
        if len(df_valid) < 10 or df_valid[target_col].nunique() < 2:
            splits[m_id] = empty_split
            continue

        df_valid[target_col] = df_valid[target_col].astype(int)
        entity_col = next((c for c in ["employeeId", "employeeid", "emp_id", "userId", "user_id"] if c in df_valid.columns), None)

        if entity_col is not None and df_valid[entity_col].nunique() < len(df_valid):
            entity_target = df_valid.groupby(entity_col)[target_col].max()
            unique_entities = entity_target.index.to_numpy()
            ent_tr, ent_val, ent_te = _safe_split_train_val_test(unique_entities, entity_target, val_test_ratio, random_state)
            df_tr = df_valid[df_valid[entity_col].isin(ent_tr)].copy()
            df_val = df_valid[df_valid[entity_col].isin(ent_val)].copy()
            df_te = df_valid[df_valid[entity_col].isin(ent_te)].copy()
        else:
            df_tr, df_val, df_te = _safe_split_train_val_test(df_valid, df_valid[target_col], val_test_ratio, random_state)

        splits[m_id] = {
            "df_tr": df_tr, "df_val": df_val, "df_te": df_te,
            "y_tr": df_tr[target_col].to_numpy(), "y_val": df_val[target_col].to_numpy(), "y_te": df_te[target_col].to_numpy(),
        }

    return splits


class LeakFreeFeaturePipeline:
    def __init__(self):
        self.numeric_cols: List[str] = []
        self.categorical_maps: Dict[str, Dict[str, float]] = {}
        self.feature_columns: List[str] = []

    def fit(self, df_train: pd.DataFrame, feature_cols: List[str]):
        self.feature_columns = list(feature_cols)
        self.numeric_cols = [c for c in self.feature_columns if c in df_train.columns and pd.api.types.is_numeric_dtype(df_train[c])]
        self.categorical_maps = {
            col: {val: float(i) for i, val in enumerate(sorted(df_train[col].dropna().astype(str).unique()))}
            for col in self.feature_columns if col in df_train.columns and col not in self.numeric_cols
        }
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        data_dict = {}
        n_rows = len(df)
        for col in self.feature_columns:
            if col not in df.columns:
                data_dict[col] = np.full(n_rows, -1.0, dtype=float)
            elif col in self.numeric_cols:
                data_dict[col] = pd.to_numeric(df[col], errors="coerce").fillna(-1.0)
            else:
                data_dict[col] = df[col].astype(str).map(self.categorical_maps.get(col, {})).fillna(-1.0)
        return pd.DataFrame(data_dict, index=df.index)[self.feature_columns]

    def fit_transform(self, df_train: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
        return self.fit(df_train, feature_cols).transform(df_train)


def stage_6_leakage_check(
    splits_dict: Dict[str, Any],
    target_col: str = "target",
    targets_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    LEAK_PATTERNS = [
        r"(?i)result", r"(?i)status", r"(?i)\btarget\b", r"(?i)accuracy",
        r"(?i)discrepancy", r"(?i)error", r"(?i)failure", r"(?i)severity",
        r"(?i)retry", r"(?i)audit"
    ]
    pipelines: Dict[str, Any] = {}

    for m_id, split in splits_dict.items():
        df_tr = split.get("df_tr")
        y_tr = split.get("y_tr", np.array([]))

        if df_tr is None or df_tr.empty or y_tr is None or len(y_tr) == 0:
            pipelines[m_id] = {"clean_features": [], "pipe": LeakFreeFeaturePipeline()}
            continue

        n_rows = len(df_tr)
        orig_target = (targets_summary or {}).get(m_id, {}).get("target_col")
        raw_date_cols = set(get_date_columns(df_tr))
        detected_entity = find_primary_entity_key(df_tr)

        candidate_features = []
        for col in df_tr.columns:
            col_s = str(col).strip()
            col_l = col_s.lower()
            if col == target_col or col == orig_target or col == detected_entity:
                continue
            if any(re.search(pat, col_s) for pat in LEAK_PATTERNS):
                continue
            uniqueness_ratio = df_tr[col].nunique() / max(1, n_rows)
            if re.search(r"\b(?:id|code|key)\b|[_\-](?:id|code|key)|(?:id|code|key)$", col_l) and uniqueness_ratio > 0.05:
                continue
            if (df_tr[col].dtype == "object" or pd.api.types.is_datetime64_any_dtype(df_tr[col])) and (uniqueness_ratio > 0.40 or col in raw_date_cols):
                continue
            candidate_features.append(col)

        feature_pipeline = LeakFreeFeaturePipeline()
        X_train_candidates = feature_pipeline.fit_transform(df_tr, candidate_features)

        leakage_free_candidates = []
        if len(y_tr) > 0 and len(candidate_features) > 0 and np.std(y_tr) > 0:
            for col in candidate_features:
                col_series = pd.to_numeric(X_train_candidates[col], errors="coerce").fillna(0)
                if col_series.nunique() > 1:
                    corr = np.corrcoef(col_series, y_tr)[0, 1]
                    if abs(corr) >= 0.90:
                        continue
                leakage_free_candidates.append(col)
        else:
            leakage_free_candidates = candidate_features

        variance_passed = []
        for col in leakage_free_candidates:
            s_col = X_train_candidates[col]
            top_val_pct = (s_col.value_counts(normalize=True, dropna=False).iloc[0] * 100) if not s_col.empty else 100
            if top_val_pct < 99.5:
                variance_passed.append(col)

        temp_df = X_train_candidates[variance_passed]
        corr_matrix = temp_df.corr().abs()
        dropped_collinear = set()
        for i in range(len(variance_passed)):
            col_a = variance_passed[i]
            if col_a in dropped_collinear:
                continue
            for j in range(i + 1, len(variance_passed)):
                col_b = variance_passed[j]
                if col_b in dropped_collinear:
                    continue
                if corr_matrix.loc[col_a, col_b] > 0.95:
                    dropped_collinear.add(col_b)

        clean_f = [c for c in variance_passed if c not in dropped_collinear]
        feature_pipeline.fit(df_tr, clean_f)
        pipelines[m_id] = {"clean_features": clean_f, "pipe": feature_pipeline}

    return pipelines


def stage_7_model_training_and_evaluation(
    splits_dict: Dict[str, Any],
    pipelines_dict: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    models_dict: Dict[str, Any] = {}
    eval_dict: Dict[str, Any] = {}

    for m_id, split in splits_dict.items():
        df_tr, df_val, df_te = split.get("df_tr"), split.get("df_val"), split.get("df_te")
        y_tr, y_val, y_te = split.get("y_tr"), split.get("y_val"), split.get("y_te")
        pipe = pipelines_dict.get(m_id, {}).get("pipe")

        if (
            df_tr is None or df_tr.empty or
            y_tr is None or len(y_tr) == 0 or
            pipe is None or len(np.unique(y_tr)) < 2
        ):
            models_dict[m_id], eval_dict[m_id] = None, {}
            continue

        X_tr = pipe.transform(df_tr)
        X_val = pipe.transform(df_val)
        X_te = pipe.transform(df_te) if df_te is not None else None

        pos_cnt = int(np.sum(y_tr))
        neg_cnt = len(y_tr) - pos_cnt
        total_cnt = len(y_tr)
        pos_ratio = pos_cnt / max(1, total_cnt)
        is_imbalanced = (pos_ratio < 0.20) or (pos_ratio > 0.80)

        minority_cnt = min(pos_cnt, neg_cnt)
        majority_cnt = max(pos_cnt, neg_cnt)
        scale_w = float(majority_cnt / max(1, minority_cnt)) if (is_imbalanced and minority_cnt > 0) else 1.0
        mod_scale_w = float(min(scale_w, np.sqrt(scale_w) * 2.5)) if is_imbalanced else scale_w

        candidate_models = {
            "Random Forest": RandomForestClassifier(
                n_estimators=120, max_depth=8, min_samples_leaf=2,
                class_weight="balanced" if scale_w > 1.5 else None, random_state=RANDOM_STATE,
            ),
            "XGBoost Classifier": xgb.XGBClassifier(
                n_estimators=160, max_depth=4, learning_rate=0.04, scale_pos_weight=mod_scale_w,
                subsample=0.85, colsample_bytree=0.85, min_child_weight=3, random_state=RANDOM_STATE, eval_metric="logloss",
            ),
            "Logistic Regression": LogisticRegression(
                max_iter=1000, class_weight="balanced" if scale_w > 1.5 else None, random_state=RANDOM_STATE,
            ),
        }

        best_m, selected_name, best_score, best_threshold = None, "Not available", (-1.0, -1.0), 0.5
        has_val_classes = len(np.unique(y_val)) > 1 if y_val is not None else False

        for name, clf in candidate_models.items():
            try:
                clf.fit(X_tr, y_tr)
                probs = clf.predict_proba(X_val)[:, 1] if hasattr(clf, "predict_proba") else clf.predict(X_val)
                if has_val_classes:
                    pr = float(average_precision_score(y_val, probs))
                    roc = float(roc_auc_score(y_val, probs))
                    cand_thresholds = np.linspace(0.05, 0.95, 91) if is_imbalanced else np.linspace(0.20, 0.80, 61)
                    opt_t, opt_score = 0.5, -1.0
                    for t in cand_thresholds:
                        preds_t = (probs >= t).astype(int)
                        p = precision_score(y_val, preds_t, zero_division=0)
                        r = recall_score(y_val, preds_t, zero_division=0)
                        beta = 1.15 if is_imbalanced else 1.0
                        b2 = beta ** 2
                        score_t = (1 + b2) * (p * r) / (b2 * p + r) if (b2 * p + r) > 0 else 0.0
                        if score_t > opt_score or (abs(score_t - opt_score) < 1e-4 and r > 0.40):
                            opt_score, opt_t = score_t, round(float(t), 3)

                    score = (round(pr, 4), roc) if is_imbalanced else (round(roc, 4), pr)
                else:
                    score = (round(float(f1_score(y_val, clf.predict(X_val), zero_division=0)), 3), 0.0)
                    opt_t = 0.5

                if score > best_score:
                    best_score, selected_name, best_m, best_threshold = score, name, clf, opt_t
            except Exception:
                continue

        models_dict[m_id] = best_m

        if best_m is not None and X_te is not None and y_te is not None and len(y_te) > 0:
            probs = best_m.predict_proba(X_te)[:, 1] if hasattr(best_m, "predict_proba") else best_m.predict(X_te)
            preds = (probs >= best_threshold).astype(int)
            has_te_classes = len(np.unique(y_te)) > 1

            eval_dict[m_id] = {
                "selected_best_model": selected_name,
                "accuracy_score": round(float(accuracy_score(y_te, preds)), 4),
                "precision": round(float(precision_score(y_te, preds, zero_division=0)), 4),
                "recall": round(float(recall_score(y_te, preds, zero_division=0)), 4),
                "f1_score": round(float(f1_score(y_te, preds, zero_division=0)), 4),
                "roc_auc": round(float(roc_auc_score(y_te, probs)), 4) if has_te_classes else None,
                "pr_auc": round(float(average_precision_score(y_te, probs)), 4) if has_te_classes else None,
                "is_imbalanced": is_imbalanced,
            }
        else:
            eval_dict[m_id] = {}

    return models_dict, eval_dict


def stage_8_shap_rca(
    models_dict: Dict[str, Any],
    pipelines_dict: Dict[str, Any],
    splits_dict: Dict[str, Any],
    targets_summary: Optional[Dict[str, Any]] = None,
    industry_standards: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    t_sum = targets_summary or {}
    shap_rca_dict: Dict[str, Any] = {}

    for m_id in (targets_summary.keys() if targets_summary else METRICS.keys()):
        t_meta = t_sum.get(m_id, {})
        hist_rate = t_meta.get("historical_rate_pct")
        ind_std = t_meta.get("std_val")
        if ind_std is None and industry_standards:
            std_entry = industry_standards.get(m_id, {})
            ind_std = std_entry.get("value") if isinstance(std_entry, dict) else std_entry
        higher_better = t_meta.get("higher_is_better")
        if higher_better is None:
            higher_better = detect_metric_direction(m_id)

        model = models_dict.get(m_id)
        pipe = pipelines_dict.get(m_id, {}).get("pipe")
        clean_f = pipelines_dict.get(m_id, {}).get("clean_features", [])
        df_val = splits_dict.get(m_id, {}).get("df_val")

        default_rca = {"applicable": False, "breachValue": None, "factors": []}
        health_state, breach_val = calculate_health_state(hist_rate, ind_std, higher_better)

        if health_state is None:
            shap_rca_dict[m_id] = {"rca": default_rca, "health_state": None}
            continue

        if breach_val <= 0 or model is None or not clean_f:
            shap_rca_dict[m_id] = {"rca": default_rca, "health_state": health_state}
            continue

        X_val = None
        if df_val is not None and not df_val.empty and pipe is not None:
            try:
                X_val = pipe.transform(df_val)
            except Exception:
                X_val = None

        mean_abs = None
        if X_val is not None and not X_val.empty and shap is not None:
            try:
                X_eval = X_val[:300] if not hasattr(X_val, "sample") else X_val.sample(min(len(X_val), 300), random_state=RANDOM_STATE)
                sv = shap.TreeExplainer(model).shap_values(X_eval)
                vals = sv[1] if isinstance(sv, list) and len(sv) >= 2 else (sv[:, :, 1] if isinstance(sv, np.ndarray) and sv.ndim == 3 else np.array(sv))
                mean_abs = np.abs(vals).mean(axis=0)
            except Exception:
                pass

        if mean_abs is None:
            fi = getattr(model, "feature_importances_", None)
            if fi is not None:
                mean_abs = np.abs(fi)
            else:
                coef = getattr(model, "coef_", None)
                if coef is not None and len(coef) > 0:
                    mean_abs = np.abs(coef[0])

        factors = []
        if mean_abs is not None and len(mean_abs) > 0:
            top_indices = np.argsort(mean_abs)[::-1][:3]
            top_importances = [float(mean_abs[i]) for i in top_indices]
            tot_imp = sum(top_importances) or 1.0
            df_ref = df_val if (df_val is not None and not df_val.empty) else splits_dict.get(m_id, {}).get("df_tr")

            for rank, (idx, imp) in enumerate(zip(top_indices, top_importances), 1):
                f_name = clean_f[idx] if idx < len(clean_f) else f"feature_{idx}"
                pct = round((imp / tot_imp) * 100.0, 1)
                avg_val = None
                if df_ref is not None and f_name in df_ref.columns:
                    if pd.api.types.is_numeric_dtype(df_ref[f_name]):
                        s = pd.to_numeric(df_ref[f_name], errors="coerce").dropna()
                        if not s.empty:
                            avg_val = round(float(s.mean()), 2)

                factors.append({
                    "rank": rank,
                    "factorName": f_name,
                    "avgFactorValue": avg_val,
                    "impactValue": round(breach_val * (pct / 100.0), 2),
                    "impactPct": pct,
                })

        shap_rca_dict[m_id] = {
            "rca": {
                "applicable": True,
                "breachValue": breach_val,
                "factors": factors,
            } if factors else default_rca,
            "health_state": health_state,
        }
    return shap_rca_dict


def mann_kendall_sens_slope(values: List[float]) -> str:
    n = len(values)
    if n < 3:
        return "stable"

    s, pairwise_slopes = 0, []
    for k in range(n - 1):
        for j in range(k + 1, n):
            diff = values[j] - values[k]
            s += int(np.sign(diff))
            pairwise_slopes.append(diff / (j - k))

    sens_slope = float(np.median(pairwise_slopes)) if pairwise_slopes else 0.0
    _, counts = np.unique(values, return_counts=True)
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in counts if t > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0

    z = (s - np.sign(s)) / np.sqrt(var_s) if (var_s > 0 and s != 0) else 0.0
    p_value = math.erfc(abs(z) / math.sqrt(2.0))
    is_sig = (abs(sens_slope) > 0.10) or (abs(sens_slope) > 0.05 and p_value < 0.15)
    return ("up" if sens_slope > 0 else "down") if is_sig else "stable"


def stage_9_trend_analysis(
    targets_summary: Optional[Dict[str, Any]],
    df_map: Dict[str, Optional[pd.DataFrame]],
) -> Dict[str, Any]:
    t_sum = targets_summary or {}
    results: Dict[str, Any] = {}

    for m_id in (targets_summary.keys() if targets_summary else (df_map.keys() if df_map else METRICS.keys())):
        df = df_map.get(m_id)
        t_meta = t_sum.get(m_id, {})
        date_col = t_meta.get("date_col")
        if df is None or t_meta.get("historical_rate_pct") is None or not date_col or "target" not in df.columns:
            results[m_id] = (None, [])
            continue

        parsed_dt = df[date_col] if pd.api.types.is_datetime64_any_dtype(df[date_col]) else pd.to_datetime(df[date_col], errors="coerce")
        valid_mask = parsed_dt.notna() & df["target"].notna()
        if valid_mask.sum() < 4:
            results[m_id] = (None, [])
            continue

        df_dated = df.loc[valid_mask].assign(
            _year=parsed_dt.loc[valid_mask].dt.year,
            _quarter=parsed_dt.loc[valid_mask].dt.quarter,
            _month=parsed_dt.loc[valid_mask].dt.month,
        )

        m_avg = (df_dated.groupby(["_year", "_quarter", "_month"])["target"].mean() * 100.0).round(2).to_dict()
        q_avg = (df_dated.groupby(["_year", "_quarter"])["target"].mean() * 100.0).round(2).to_dict()
        y_avg = (df_dated.groupby("_year")["target"].mean() * 100.0).round(2).to_dict()

        yearly_nodes, observed_quarters = [], []
        for yr in sorted(df_dated["_year"].unique()):
            q_nodes = []
            for q in range(1, 5):
                q_val = q_avg.get((yr, q))
                if q_val is not None:
                    observed_quarters.append(q_val)

                m_nodes = [
                    {"period": f"{yr}-{m:02d}", "month": m, "average": m_avg.get((yr, q, m)), "isPartial": m_avg.get((yr, q, m)) is None}
                    for m in range((q - 1) * 3 + 1, (q - 1) * 3 + 4)
                ]
                q_nodes.append({
                    "period": f"{yr}-Q{q}", "quarter": q, "average": q_val,
                    "isPartial": q_val is None, "children": {"granularity": "monthly", "periods": m_nodes},
                })

            yearly_nodes.append({
                "period": str(yr), "year": int(yr), "average": y_avg.get(yr),
                "isPartial": any(qn["average"] is None for qn in q_nodes),
                "children": {"granularity": "quarterly", "periods": q_nodes},
            })

        direction = mann_kendall_sens_slope(observed_quarters) if len(observed_quarters) >= 3 else "stable"

        results[m_id] = ({
            "direction": direction,
            "granularity": "yearly",
            "periods": yearly_nodes,
        }, observed_quarters)

    return results


def damped_trend_forecast(
    history: List[float],
    steps: int = 3,
    phi: float = 0.90,
    alpha: float = 0.35,
    beta: float = 0.20,
) -> Dict[str, Any]:
    n = len(history)
    if n < 2:
        return {"model_name": "Damped Holt Trend", "forecasts": [], "mae": None, "rmse": None}

    level = history[0]
    trend = history[1] - history[0]
    errors = []

    for t in range(1, n):
        y_hat = level + phi * trend
        e = history[t] - y_hat
        errors.append(e)
        level += phi * trend + alpha * e
        trend = phi * trend + alpha * beta * e

    abs_err = np.abs(errors)
    forecasts, cum_damp = [], 0.0
    for h in range(1, steps + 1):
        cum_damp += phi ** h
        proj = level + cum_damp * trend
        forecasts.append(round(max(0.0, min(100.0, proj)), 1))

    return {
        "model_name": "Damped Holt Trend",
        "forecasts": forecasts,
        "mae": round(float(np.mean(abs_err)), 2),
        "rmse": round(float(np.sqrt(np.mean(abs_err ** 2))), 2),
    }


def theil_sen_trend_forecast(history: List[float], steps: int = 3) -> Dict[str, Any]:
    n = len(history)
    if n < 2:
        return {"model_name": "Theil-Sen Robust Trend", "forecasts": [], "mae": None, "rmse": None}

    pairwise_slopes = [(history[j] - history[k]) / (j - k) for k in range(n - 1) for j in range(k + 1, n)]
    slope = float(np.median(pairwise_slopes)) if pairwise_slopes else 0.0
    intercept = float(np.median([history[t] - slope * t for t in range(n)]))

    preds = [intercept + slope * t for t in range(n)]
    errors = np.abs(np.array(history) - np.array(preds))
    forecasts = [round(max(0.0, min(100.0, intercept + slope * ((n - 1) + h))), 1) for h in range(1, steps + 1)]

    return {
        "model_name": "Theil-Sen Robust Trend",
        "forecasts": forecasts,
        "mae": round(float(np.mean(errors)), 2),
        "rmse": round(float(np.sqrt(np.mean(errors ** 2))), 2),
    }


def stage_10_forecast(
    targets_summary: Optional[Dict[str, Any]],
    trend_results: Dict[str, Any],
    industry_standards: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    t_sum = targets_summary or {}
    results = {}
    null_fc_payload = {
        "applicable": False, "status": "Data Missing",
        "message": "Forecast was not performed because essential metric data is incomplete.",
    }
    null_fc_eval = {"model_name": "Not available", "mae": None, "rmse": None, "rating": "not_assessed"}

    for m_id in (targets_summary.keys() if targets_summary else METRICS.keys()):
        t_meta = t_sum.get(m_id, {})
        hist_rate = t_meta.get("historical_rate_pct")
        _, series = trend_results.get(m_id, ({}, []))
        history = [v for v in (series or []) if v is not None]

        if hist_rate is None or len(history) < 2:
            results[m_id] = (null_fc_payload, null_fc_eval)
            continue

        m1 = damped_trend_forecast(history=history, steps=3)
        m2 = theil_sen_trend_forecast(history=history, steps=3)
        winner = min([m1, m2], key=lambda m: float(m.get("rmse") or float("inf")))
        fc_steps = winner.get("forecasts", [])
        sigma = max(0.3, float(winner.get("rmse") or 0.3))

        anchor = t_meta.get("anchor_date")
        if anchor is None or pd.isna(anchor):
            anchor = datetime.datetime.now(datetime.timezone.utc)

        next_month_dt = (anchor.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        cur_q = (anchor.month - 1) // 3 + 1
        next_q = (cur_q % 4) + 1
        q_year = anchor.year if next_q > cur_q else anchor.year + 1
        periods = [next_month_dt.strftime("%Y-%m"), f"{q_year}-Q{next_q}", str(anchor.year + 1)]

        target_val = float(t_meta.get("std_val")) if t_meta.get("std_val") is not None else None
        higher_better = t_meta.get("higher_is_better")
        if higher_better is None:
            higher_better = detect_metric_direction(m_id)

        keys = ["nextMonth", "nextQuarter", "nextYear"]
        fc_payload = {}
        for key, period, p_val, mult in zip(keys, periods, fc_steps, [1.0, math.sqrt(2.0), 2.0]):
            margin = round(1.96 * sigma * mult, 1)
            p_state, _ = calculate_health_state(p_val, target_val, higher_better)
            fc_payload[key] = {
                "period": period,
                "predictedValue": p_val,
                "lowerBound": round(max(0.0, p_val - margin), 1),
                "upperBound": round(min(100.0, p_val + margin), 1),
                "predictedHealthState": p_state,
            }

        results[m_id] = (fc_payload, winner)

    return results


def save_json(data: Any, filepath: Path) -> None:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def stage_11_build_final_json(
    dq_report: Dict[str, Any],
    eval_dict: Dict[str, Any],
    shap_rca_dict: Dict[str, Any],
    trend_results: Dict[str, Any],
    forecast_results: Dict[str, Any],
    targets_summary: Optional[Dict[str, Any]] = None,
    industry_standards: Optional[Dict[str, Any]] = None,
    push_to_supabase: bool = True,
) -> Dict[str, Any]:
    t_sum = targets_summary or {}
    gen_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    metrics_list = []

    for m_id in (targets_summary.keys() if targets_summary else METRICS.keys()):
        t_meta = t_sum.get(m_id, {})
        ind_std = t_meta.get("std_val")
        if ind_std is None and industry_standards:
            std_entry = industry_standards.get(m_id, {})
            ind_std = std_entry.get("value") if isinstance(std_entry, dict) else std_entry
        higher_better = t_meta.get("higher_is_better")
        if higher_better is None:
            higher_better = detect_metric_direction(m_id)
        hist_rate = t_meta.get("historical_rate_pct")

        m_dq = (dq_report or {}).get(m_id, {})
        trend, _ = (trend_results or {}).get(m_id, (None, []))
        forecast, fc_eval = (forecast_results or {}).get(m_id, ({}, {}))
        rca_entry = (shap_rca_dict or {}).get(m_id, {})
        ev = (eval_dict or {}).get(m_id, {})

        is_missing = hist_rate is None or ind_std is None
        val = float(hist_rate) if not is_missing else None

        if is_missing:
            fc_payload = {
                "applicable": False,
                "status": "Data Missing",
                "message": "Forecast was not performed because essential metric data is incomplete.",
            }
            rca_payload = {
                "applicable": False,
                "status": "Data Missing",
                "message": "RCA was not performed because essential metric data is incomplete.",
                "breachValue": None,
                "factors": [],
            }
            models_payload = {
                "rcaModel": {"status": "Data Missing", "trainingPerformed": False},
                "forecastModel": {"status": "Data Missing", "trainingPerformed": False},
            }
            health_state = None
            var_dict = {"value": None, "percentage": None}
            trend_payload = None
        else:
            is_imb = ev.get("is_imbalanced", not higher_better)
            pr_auc, roc_auc, f1 = ev.get("pr_auc"), ev.get("roc_auc"), ev.get("f1_score")
            if is_imb and pr_auc is not None:
                if (pr_auc >= 0.25 or (roc_auc is not None and roc_auc >= 0.80)) and (roc_auc is None or roc_auc >= 0.70):
                    rca_rating = "good"
                elif pr_auc >= 0.10 and (roc_auc is None or roc_auc >= 0.60):
                    rca_rating = "fair"
                else:
                    rca_rating = "poor"
            else:
                score = roc_auc if roc_auc is not None else f1
                rca_rating = ("good" if score >= 0.80 else ("fair" if score >= 0.65 else "poor")) if score is not None else None

            fc_mae = fc_eval.get("mae")
            fc_payload = forecast
            rca_payload = rca_entry.get("rca", {"applicable": False, "breachValue": None, "factors": []})
            models_payload = {
                "rcaModel": {
                    "modelName": ev.get("selected_best_model", "Not available"),
                    "accuracy": ev.get("accuracy_score"), "precision": ev.get("precision"),
                    "recall": ev.get("recall"), "f1": ev.get("f1_score"),
                    "rocAuc": ev.get("roc_auc"), "prAuc": ev.get("pr_auc"),
                    "rating": rca_rating,
                },
                "forecastModel": {
                    "modelName": fc_eval.get("model_name", "Damped Holt Trend"),
                    "r2": None, "mae": fc_mae, "rmse": fc_eval.get("rmse"),
                    "rating": ("excellent" if fc_mae <= 1.0 else ("good" if fc_mae <= 2.5 else "fair")) if fc_mae is not None else None,
                },
            }
            health_state = rca_entry.get("health_state")
            var_dict = calculate_variance(val, ind_std, higher_is_better=higher_better)
            trend_payload = trend

        m = {
            "metricName": m_id,
            "unit": "percent",
            "higherIsBetter": higher_better if not is_missing or ind_std is not None else None,
            "companyValue": val,
            "industryStandardValue": ind_std,
            "healthState": health_state,
            "variance": var_dict,
            "trendAnalysis": trend_payload,
            "forecast": fc_payload,
            "rca": rca_payload,
            "dataQuality": m_dq.get("dataQuality", {}),
            "selectedTrainingModel": models_payload,
            "missingConfigurations": m_dq.get("missingConfigurations", {"mandatoryFieldsMissing": [], "otherFieldsMissing": []}),
        }

        save_json({"generatedAt": gen_time, "module": "EC", "reportVersion": REPORT_VERSION, **m}, WORKSPACE_DIR / f"{m_id}.json")
        metrics_list.append(m)

    if push_to_supabase:
        push_to_ml_notebook_insights_table(metrics_list, gen_time=gen_time, table_name=CUSTOM_INSIGHTS_TABLE)
    return {"module": "EC", "reportVersion": REPORT_VERSION, "generatedAt": gen_time, "metrics": metrics_list}


def push_to_ml_notebook_insights_table(
    metrics_list: List[Dict[str, Any]],
    gen_time: Optional[str] = None,
    table_name: str = CUSTOM_INSIGHTS_TABLE,
) -> None:
    if create_client is None or not metrics_list:
        return

    created_at_val = gen_time or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        sb = create_client(*get_supabase_credentials())
        built_rows = [
            {
                "created_at": created_at_val,
                "Module_Name": "EC",
                "Metric_Name": m.get("metricName", "Metric"),
                "JSON_Result": {"generatedAt": created_at_val, "module": "EC", "reportVersion": REPORT_VERSION, **m},
            }
            for m in metrics_list
        ]
        metric_names = [r["Metric_Name"] for r in built_rows]
        try:
            sb.table(table_name).delete().eq("Module_Name", "EC").in_("Metric_Name", metric_names).execute()
        except Exception:
            pass

        try:
            sb.table(table_name).insert(built_rows).execute()
        except Exception:
            res = sb.table(table_name).select("execution_id").order("execution_id", desc=True).limit(1).execute()
            max_id = res.data[0]["execution_id"] if (res.data and isinstance(res.data[0].get("execution_id"), int)) else 0
            for i, r in enumerate(built_rows, start=max_id + 1):
                r["execution_id"] = i
            sb.table(table_name).insert(built_rows).execute()
    except Exception:
        pass


def execute_full_monitoring_pipeline(push_to_supabase: bool = SUPABASE_WRITE_ENABLED) -> Dict[str, Any]:
    raw_df_map, dynamic_standards, core_df = stage_1_load_data()
    dq_report = stage_2_data_quality_check(raw_df_map)

    df_map, targets_summary = stage_3_target_creation(raw_df_map, dynamic_standards)
    df_map = stage_4_feature_engineering(df_map, core_df=core_df)

    splits_dict = stage_5_train_val_test_split(df_map)
    pipelines_dict = stage_6_leakage_check(splits_dict, targets_summary=targets_summary)
    models_dict, eval_dict = stage_7_model_training_and_evaluation(splits_dict, pipelines_dict)
    shap_rca_dict = stage_8_shap_rca(models_dict, pipelines_dict, splits_dict, targets_summary)

    trend_results = stage_9_trend_analysis(targets_summary, df_map)
    forecast_results = stage_10_forecast(targets_summary, trend_results)

    return stage_11_build_final_json(
        dq_report=dq_report,
        eval_dict=eval_dict,
        shap_rca_dict=shap_rca_dict,
        trend_results=trend_results,
        forecast_results=forecast_results,
        targets_summary=targets_summary,
        push_to_supabase=push_to_supabase,
    )


if __name__ == "__main__":
    print("Pipeline started.", flush=True)
    try:
        execute_full_monitoring_pipeline()
    except Exception:
        print("Pipeline failed. See the traceback above for details.", flush=True)
        raise
    else:
        print("Pipeline completed successfully.", flush=True)