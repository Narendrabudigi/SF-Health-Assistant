# -*- coding: utf-8 -*-
"""SuccessFactors ONB2 health monitoring.

Run locally with a .env file saved in the same directory as this script.
Company and industry workbooks are read from Supabase Storage into memory;
source workbooks are not saved to the local filesystem. Metric JSON reports are pushed directly to Supabase; auxiliary CSV/model diagnostics remain local.
"""

import sys

import subprocess

import importlib.util

import os

import re

import json

import warnings
from datetime import datetime, timezone

import zipfile

import numpy as np

import pandas as pd
warnings.filterwarnings("ignore")

ONB2_BUILD_ID = "2026-10-13-supabase-json-only-descriptive-rca-factor-labels-v3"
print(f"ONB2 BUILD: {ONB2_BUILD_ID}")

SEED = 42

np.random.seed(SEED)



# ---------------------- 1. INSTALL LIBRARIES ----------------------



required = {

    "xgboost": "xgboost",

    "sklearn": "scikit-learn",

    "openpyxl": "openpyxl",

    "shap": "shap",

    "supabase": "supabase",

    "dotenv": "python-dotenv"

}



for module, package in required.items():

    if importlib.util.find_spec(module) is None:

        subprocess.check_call(

            [sys.executable, "-m", "pip", "install", "-q", package]

        )



# ----------------------------------------------------------------
# LOCAL EXECUTION SUPPORT
# ----------------------------------------------------------------
from supabase import create_client

try:
    from IPython.display import display, Markdown
except Exception:
    def display(obj):
        print(obj)
    class Markdown:
        def __init__(self, text):
            self.data = text

from sklearn.model_selection import (

    train_test_split, GroupShuffleSplit, KFold, GroupKFold,

    RandomizedSearchCV, cross_validate

)

from sklearn.compose import ColumnTransformer

from sklearn.pipeline import Pipeline

from sklearn.preprocessing import OneHotEncoder

from sklearn.impute import SimpleImputer

from sklearn.feature_selection import SelectPercentile, f_regression

from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

from sklearn.dummy import DummyRegressor

from sklearn.inspection import permutation_importance

from xgboost import XGBRegressor



# ---------------------- CONFIGURATION + IN-MEMORY SUPABASE INPUT ----------------------
# Load values from .env beside this script. Excel workbooks are read directly
# from Supabase Storage into memory; they are NOT saved to the local filesystem.
from dotenv import load_dotenv
from io import BytesIO
from supabase import create_client

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
ENV_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), ".env")
load_dotenv(ENV_PATH)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "SF_Health_Raw_Data").strip()
COMPANY_FILE_PATH = os.getenv("METRIC_FILE_PATH", "SF_Dataset_USA1.xlsx").strip()
INDUSTRY_FILE_PATH = os.getenv(
    "INDUSTRY_STANDARDS_FILE_PATH",
    "SF Health Monitoring Industry Standards.xlsx"
).strip()
ANALYSIS_START = os.getenv("ANALYSIS_START", "2024-10-01").strip()
SUPABASE_WRITE_ENABLED = os.getenv("SUPABASE_WRITE_ENABLED", "true").strip().lower() == "true"
REPORT_VERSION = os.getenv("REPORT_VERSION", "2.2").strip()
SEED = int(os.getenv("RANDOM_STATE", "42"))
np.random.seed(SEED)

if not SUPABASE_URL:
    raise RuntimeError(f"SUPABASE_URL is missing from {ENV_PATH}")
if not SUPABASE_KEY:
    raise RuntimeError(f"SUPABASE_KEY is missing from {ENV_PATH}")
if not SUPABASE_KEY.startswith("sb_secret_"):
    raise RuntimeError("SUPABASE_KEY must be your Supabase backend secret key (sb_secret_...).")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print("=" * 75)
print("LOADING COMPANY AND INDUSTRY DATA FROM SUPABASE")
print("=" * 75)
print("Input mode: in-memory; Excel files will not be saved locally.")

def read_storage_excel(bucket_name, object_path, label):
    """Read an Excel object from Supabase Storage into memory without saving it."""
    try:
        print(f"\nReading {label} from Supabase Storage...")
        workbook_bytes = supabase.storage.from_(bucket_name).download(object_path)
        if not workbook_bytes:
            raise ValueError("Supabase returned an empty file.")
        excel_buffer = BytesIO(workbook_bytes)
        # Validate that pandas can open it now; keep the bytes for later sheets.
        pd.ExcelFile(excel_buffer)
        print(f"{label} loaded into memory ({len(workbook_bytes):,} bytes).")
        return workbook_bytes
    except Exception as exc:
        raise RuntimeError(
            f"Could not read '{object_path}' from Supabase bucket '{bucket_name}'. "
            f"Check the .env file, bucket name, file path, and Storage permissions. Details: {exc}"
        ) from exc

COMPANY_WORKBOOK_BYTES = read_storage_excel(
    SUPABASE_BUCKET, COMPANY_FILE_PATH, "company workbook"
)
INDUSTRY_WORKBOOK_BYTES = read_storage_excel(
    SUPABASE_BUCKET, INDUSTRY_FILE_PATH, "industry benchmark workbook"
)

# ---------------------- SUPABASE ML INSIGHTS OUTPUT ----------------------
SUPABASE_INSIGHTS_TABLE = "ML_Notebook_Insights"
SUPABASE_MODULE_NAME = "ONB2"
SUPABASE_WRITE_MODE = "secret_key" if SUPABASE_WRITE_ENABLED else "disabled"
print("Supabase ML insights destination:", SUPABASE_INSIGHTS_TABLE)
print("Supabase module name:", SUPABASE_MODULE_NAME)
print("Supabase write mode:", SUPABASE_WRITE_MODE)

RLS_INSERT_POLICY_SQL = f"""CREATE POLICY \"Allow ML notebook inserts\"
ON public.\"{SUPABASE_INSIGHTS_TABLE}\"
FOR INSERT
TO anon, authenticated
WITH CHECK (true);"""


def _metric_pascal_case(metric_name):
    """Convert a metric label to PascalCase with no spaces or punctuation."""
    text_value = str(metric_name or "Metric").strip()
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", text_value)
    return "".join((part[0].upper() + part[1:]) if not part.isdigit() else part for part in parts) or "Metric"


def push_metric_json_to_supabase(report):
    """Replace only the existing ONB2 row for this metric, then insert the fresh JSON."""
    if not SUPABASE_WRITE_ENABLED:
        print(f"Supabase writes disabled; skipped upload for {report.get('metricName', 'Metric')}.")
        return {"status": "skipped_write_disabled", "metric_name": report.get("metricName")}
    report = json_safe(report)
    report["module"] = SUPABASE_MODULE_NAME
    metric_name = _metric_pascal_case(report.get("metricName", "Metric"))
    report["metricName"] = metric_name

    payload = {
        "Module_Name": SUPABASE_MODULE_NAME,
        "Metric_Name": metric_name,
        "JSON_Result": report,
    }

    try:
        # Scope deletion to ONB2 + exact PascalCase metric only.
        delete_response = (
            supabase
            .table(SUPABASE_INSIGHTS_TABLE)
            .delete()
            .eq("Module_Name", SUPABASE_MODULE_NAME)
            .eq("Metric_Name", metric_name)
            .execute()
        )
        deleted_rows = delete_response.data or []
        if isinstance(deleted_rows, dict):
            deleted_rows = [deleted_rows]
        print(f"Existing ONB2 rows replaced for {metric_name}: {len(deleted_rows)}")

        # Insert the fresh row and request database-generated execution_id/created_at.
        response = (
            supabase
            .table(SUPABASE_INSIGHTS_TABLE)
            .insert(payload)
            .select("execution_id,created_at,Module_Name,Metric_Name")
            .execute()
        )
        rows = response.data or []
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            raise RuntimeError("Supabase returned no inserted row.")

        inserted = rows[0]
        if inserted.get("execution_id") is None or inserted.get("created_at") is None:
            raise RuntimeError(f"Missing execution_id/created_at in insert response: {inserted}")

        print("\nSUPABASE INSERT SUCCESS")
        print("  execution_id:", inserted.get("execution_id"))
        print("  created_at:", inserted.get("created_at"))
        print("  Module_Name:", inserted.get("Module_Name"))
        print("  Metric_Name:", inserted.get("Metric_Name"))

        return {
            "execution_id": inserted.get("execution_id"),
            "created_at": inserted.get("created_at"),
            "module_name": inserted.get("Module_Name"),
            "metric_name": inserted.get("Metric_Name"),
            "status": "replaced_existing_and_inserted" if deleted_rows else "inserted",
        }
    except Exception as e:
        raise RuntimeError(
            f"Failed to replace/insert metric '{metric_name}' into public.\"{SUPABASE_INSIGHTS_TABLE}\": {e}"
        ) from e


# ----------------------------------------------------------------
# SHARED HELPERS REQUIRED BY THE ONBOARDING CYCLE-TIME FUNCTION
# ----------------------------------------------------------------
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LogisticRegression


def normalize_name(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def find_column(df_or_columns, aliases):
    """Return the first dataframe column matching one of the aliases."""
    columns = list(df_or_columns.columns) if hasattr(df_or_columns, "columns") else list(df_or_columns)
    normalized = {c: normalize_name(c) for c in columns}
    alias_norms = [normalize_name(a) for a in aliases]
    for alias in alias_norms:
        for col, norm in normalized.items():
            if norm == alias:
                return col
    for alias in alias_norms:
        for col, norm in normalized.items():
            if alias in norm or norm in alias:
                return col
    return None


def parse_dates(series):
    return pd.to_datetime(series, errors="coerce")


def numeric_duration(start, end):
    start = pd.to_datetime(start, errors="coerce")
    end = pd.to_datetime(end, errors="coerce")
    return (end - start).dt.total_seconds() / 86400.0


def safe_metrics(y_true, y_pred):
    yt = pd.to_numeric(pd.Series(y_true), errors="coerce").to_numpy(dtype=float)
    yp = pd.to_numeric(pd.Series(y_pred), errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(yt) & np.isfinite(yp)
    yt, yp = yt[mask], yp[mask]
    if len(yt) == 0:
        return {"R2": np.nan, "MAE_days": np.nan, "RMSE_days": np.nan}
    r2 = r2_score(yt, yp) if len(yt) >= 2 and len(np.unique(yt)) >= 2 else np.nan
    return {
        "R2": float(r2) if np.isfinite(r2) else np.nan,
        "MAE_days": float(mean_absolute_error(yt, yp)),
        "RMSE_days": float(np.sqrt(mean_squared_error(yt, yp))),
    }


def display_metrics(title, metrics):
    print("\\n" + "=" * 75)
    print(title)
    print("=" * 75)
    print(f"R²:   {metrics.get('R2'):.4f}" if pd.notna(metrics.get('R2')) else "R²:   unavailable")
    print(f"MAE:  {metrics.get('MAE_days'):.4f} days" if pd.notna(metrics.get('MAE_days')) else "MAE:  unavailable")
    print(f"RMSE: {metrics.get('RMSE_days'):.4f} days" if pd.notna(metrics.get('RMSE_days')) else "RMSE: unavailable")


_ONBOARDING_CYCLE_TIME_LEGACY_REPORT = None


def run_onboarding_cycle_time_analysis():
    global _ONBOARDING_CYCLE_TIME_LEGACY_REPORT
    # ---------------------- 4. DETECT TARGET FIELDS ----------------------



    hire_col = find_column(company_df, [

        "joiningDate", "hireDate", "startDate", "employmentStartDate",

        "newHireStartDate", "dateOfJoining"

    ])



    completion_col = find_column(company_df, [

        "onboardingCompletionDate", "onboardingCompletedDate",

        "completionDate", "onboardingEndDate", "processCompletionDate"

    ])



    employee_col = find_column(company_df, [

        "employeeId", "employeeID", "personId", "workerId", "newHireId"

    ])



    if hire_col is None or completion_col is None:

        missing_mandatory = []
        if hire_col is None:
            missing_mandatory.append({"field": "Hire/start date", "status": "MISSING"})
        if completion_col is None:
            missing_mandatory.append({"field": "Onboarding completion date", "status": "MISSING"})
        normal_missing = []
        if employee_col is None:
            normal_missing.append({"field": "Employee identifier", "status": "MISSING"})
        data_missing_report = {
            "generatedAt": datetime.now(timezone.utc).isoformat(), "module": "ONB2", "metricName": "Onboarding Cycle Time", "unit": "days",
            "higherIsBetter": False, "companyValue": None, "industryStandardValue": None, "healthState": "Data Missing",
            "variance": {"value": None, "percentage": None}, "trendAnalysis": None, "forecast": None,
            "rca": {"applicable": False, "status": "Data Missing", "message": "RCA was not performed because mandatory fields are missing.", "breachValue": None, "factors": []},
            "dataQuality": {"overallRating": "poor", "dataPeriod": {"from": None, "to": None}, "recordsAnalysed": 0, "checks": []},
            "modelAccuracy": {"rcaModel": {"modelName": "Regularized XGBoost Regression", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}, "forecastModel": {"modelName": "DampedTrend", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}},
            "missingConfigurations": {"mandatoryFieldsMissing": missing_mandatory, "normalFieldsMissing": normal_missing},
            "description": "Data Missing: mandatory onboarding cycle-time fields were not detected. RCA, training and forecasting were not performed."
        }
        data_missing_report["module"] = SUPABASE_MODULE_NAME
        data_missing_report["metricName"] = _metric_pascal_case(data_missing_report.get("metricName"))
        data_missing_report["rca"]["status"] = "FieldMissing"
        _ONBOARDING_CYCLE_TIME_LEGACY_REPORT = data_missing_report
        print("\nDATA MISSING — ONBOARDING CYCLE TIME")
        print("Mandatory fields missing:", [x["field"] for x in missing_mandatory])
        print("RCA: NOT PERFORMED")
        print("Report retained in memory; the strict JSON will be pushed directly to Supabase.")
        return



    print("\nTARGET FIELD MAPPING")

    print("Hire/start date:", hire_col)

    print("Completion date:", completion_col)

    print("Employee grouping field:", employee_col)



    company_df[hire_col] = parse_dates(company_df[hire_col])

    company_df[completion_col] = parse_dates(company_df[completion_col])



    company_df["target_cycle_time_days"] = numeric_duration(

        company_df[hire_col], company_df[completion_col]

    )



    # Invalid negative durations are not valid target observations.

    negative_count = int(

        (company_df["target_cycle_time_days"] < 0).fillna(False).sum()

    )



    # Never invent targets for incomplete records.

    completed_mask = (

        company_df[hire_col].notna()

        & company_df[completion_col].notna()

        & company_df["target_cycle_time_days"].notna()

        & (company_df["target_cycle_time_days"] >= 0)

    )



    model_df = company_df.loc[completed_mask].copy().reset_index(drop=True)



    missing_completion = int(company_df[completion_col].isna().sum())

    missing_hire = int(company_df[hire_col].isna().sum())

    zero_days = int((model_df["target_cycle_time_days"] == 0).sum())

    # ------------------------------------------------------------
    # ESSENTIAL DATA-QUALITY GATE
    # ------------------------------------------------------------
    # A mandatory field being present as a column is not enough.
    # If essential values are missing in any record, the metric is
    # considered incomplete and RCA/forecasting must not be generated.
    # Stale records are also treated as unusable for these outputs.
    # The stale threshold is intentionally explicit and conservative.
    STALE_MONTHS = 3

    incomplete_records = int(
        (company_df[hire_col].isna() | company_df[completion_col].isna()).sum()
    )

    missing_hire_records = int(company_df[hire_col].isna().sum())
    missing_completion_records = int(company_df[completion_col].isna().sum())

    essential_dates = pd.concat([
        company_df[hire_col].dropna(),
        company_df[completion_col].dropna()
    ], ignore_index=True)

    stale_cutoff = None
    stale_mask = pd.Series(False, index=company_df.index)
    stale_records = 0

    if not essential_dates.empty:
        latest_essential_date = essential_dates.max()
        stale_cutoff = latest_essential_date - pd.DateOffset(months=STALE_MONTHS)
        # Only complete records can be classified as stale; incomplete
        # records are already captured by the incomplete-data check.
        complete_for_stale = company_df[hire_col].notna() & company_df[completion_col].notna()
        record_latest_essential_date = company_df[[hire_col, completion_col]].max(axis=1)
        stale_mask = complete_for_stale & (
            record_latest_essential_date < stale_cutoff
        )
        stale_records = int(stale_mask.sum())

    mandatory_data_issues = []
    if missing_hire_records > 0:
        mandatory_data_issues.append({
            "fieldKey": "hire_start_date",
            "fieldName": "Hire/start date",
            "issueType": "INCOMPLETE_DATA",
            "affectedRecords": missing_hire_records,
            "status": "MISSING_VALUES"
        })
    if missing_completion_records > 0:
        mandatory_data_issues.append({
            "fieldKey": "onboarding_completion_date",
            "fieldName": "Onboarding completion date",
            "issueType": "INCOMPLETE_DATA",
            "affectedRecords": missing_completion_records,
            "status": "MISSING_VALUES"
        })
    if stale_records > 0:
        mandatory_data_issues.append({
            "fieldKey": "hire_start_date",
            "fieldName": "Hire/start date",
            "issueType": "STALE_RECORDS",
            "affectedRecords": stale_records,
            "staleThresholdMonths": STALE_MONTHS,
            "staleCutoff": stale_cutoff.strftime("%Y-%m-%d"),
            "status": "STALE_VALUES"
        })

    essential_data_blocked = False  # Record-level missing/stale data is reported, not a processing gate.

    print("\nESSENTIAL DATA-QUALITY GATE")
    print("Incomplete essential records:", incomplete_records)
    print("Stale essential records:", stale_records)
    if stale_cutoff is not None:
        print("Stale cutoff:", stale_cutoff.strftime("%Y-%m-%d"), f"({STALE_MONTHS} months)")

    if essential_data_blocked:
        # Build a complete JSON response WITHOUT running model training,
        # RCA, SHAP/permutation RCA, or forecasting.
        normal_missing_fields = []
        if employee_col is None:
            normal_missing_fields.append({
                "fieldKey": "employee_identifier",
                "fieldName": "Employee identifier",
                "status": "MISSING_CONFIGURATION"
            })

        gate_checks = [
            {
                "checkName": "Incomplete essential records",
                "category": "Completeness",
                "checkedRecords": int(len(company_df)),
                "failedRecords": int(incomplete_records),
                "failedPct": float(100.0 * incomplete_records / max(len(company_df), 1)),
                "affectedColumns": [str(hire_col), str(completion_col)],
                "staleRange": None
            },
            {
                "checkName": "Stale essential records",
                "category": "Freshness",
                "checkedRecords": int(len(company_df)),
                "failedRecords": int(stale_records),
                "failedPct": float(100.0 * stale_records / max(len(company_df), 1)),
                "affectedColumns": [str(hire_col), str(completion_col)],
                "staleRange": (
                    {
                        "thresholdMonths": STALE_MONTHS,
                        "cutoff": stale_cutoff.strftime("%Y-%m-%d") if stale_cutoff is not None else None
                    } if stale_cutoff is not None else None
                )
            },
            {
                "checkName": "Negative cycle time",
                "category": "Validity",
                "checkedRecords": int(len(company_df)),
                "failedRecords": int(negative_count),
                "failedPct": float(100.0 * negative_count / max(len(company_df), 1)),
                "affectedColumns": [str(hire_col), str(completion_col)],
                "staleRange": None
            }
        ]

        # Preserve every value that can legitimately be calculated before the
        # data-quality gate. The gate still prevents training, RCA and forecasting.
        gate_company_value = (
            float(model_df["target_cycle_time_days"].mean())
            if not model_df.empty else None
        )
        # Read the already-supplied industry benchmark without changing the
        # existing benchmark/model logic below.
        gate_benchmark_low = None
        gate_benchmark_high = None
        gate_benchmark_source = None
        try:
            metric_rows = industry_df[
                industry_df.astype(str).apply(
                    lambda row: row.str.contains(
                        "Onboarding Cycle Time", case=False, na=False
                    ).any(), axis=1
                )
            ]
            if not metric_rows.empty:
                benchmark_text = " ".join(map(str, metric_rows.iloc[0].tolist()))
                nums = [
                    float(x) for x in re.findall(
                        r"\d+(?:\.\d+)?", benchmark_text
                    )
                ][:2]
                if len(nums) >= 2:
                    gate_benchmark_low, gate_benchmark_high = min(nums), max(nums)
                gate_benchmark_source = benchmark_text
        except Exception:
            pass

        gate_benchmark_value = (
            float((gate_benchmark_low + gate_benchmark_high) / 2.0)
            if gate_benchmark_low is not None and gate_benchmark_high is not None
            else None
        )
        gate_variance = (
            gate_company_value - gate_benchmark_value
            if gate_company_value is not None and gate_benchmark_value is not None
            else None
        )
        gate_variance_pct = (
            100.0 * gate_variance / gate_benchmark_value
            if gate_variance is not None and gate_benchmark_value not in (None, 0)
            else None
        )
        if gate_company_value is None:
            gate_health_state = "Data Missing"
        elif gate_benchmark_low is None or gate_benchmark_high is None:
            gate_health_state = "Benchmark unavailable"
        elif gate_company_value <= gate_benchmark_high:
            gate_health_state = "Healthy"
        elif gate_company_value <= gate_benchmark_high * 1.20:
            gate_health_state = "At risk"
        else:
            gate_health_state = "Critical"

        mandatory_present = []
        if hire_col is not None:
            mandatory_present.append({"field": "Hire/start date", "status": "PRESENT"})
        if completion_col is not None:
            mandatory_present.append({"field": "Onboarding completion date", "status": "PRESENT"})
        normal_present = []
        if employee_col is not None:
            normal_present.append({"field": "Employee identifier", "status": "PRESENT"})

        gate_report = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "module": "ONB2",
            "metricName": "Onboarding Cycle Time",
            "unit": "days",
            "higherIsBetter": False,
            "companyValue": gate_company_value,
            "industryStandardValue": gate_benchmark_value,
            "healthState": gate_health_state,
            "variance": {"value": gate_variance, "percentage": gate_variance_pct},
            "trendAnalysis": None,
            "forecast": {
                "applicable": False,
                "status": "Data Missing",
                "message": "Forecast was not performed because essential onboarding data is incomplete or stale."
            },
            "rca": {
                "applicable": False,
                "status": "Data Missing",
                "message": "RCA was not performed because essential onboarding data is incomplete or stale.",
                "breachValue": None,
                "factors": []
            },
            "dataQuality": {
                "overallRating": "Poor",
                "dataPeriod": {
                    "from": company_df[hire_col].min().strftime("%Y-%m-%d") if company_df[hire_col].notna().any() else None,
                    "to": company_df[completion_col].max().strftime("%Y-%m-%d") if company_df[completion_col].notna().any() else None
                },
                "recordsAnalysed": int(len(company_df)),
                "incompleteRecords": int(incomplete_records),
                "staleRecords": int(stale_records),
                "checks": gate_checks
            },
            "modelAccuracy": {
                "trainingTestingModel": {
                    "modelName": "Not run",
                    "trainingR2": None,
                    "testingR2": None,
                    "selectionRule": "Model training was skipped because essential data-quality requirements were not met."
                },
                "rcaModel": {
                    "modelName": "Not run",
                    "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"
                },
                "forecastModel": {
                    "modelName": "Not run",
                    "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"
                }
            },
            "missingConfigurations": {
                "mandatoryFieldsMissing": [],
                "normalFieldsMissing": normal_missing_fields,
                "mandatoryFieldsPresent": mandatory_present,
                "normalFieldsPresent": normal_present,
                "mandatoryDataIssues": mandatory_data_issues
            },
            "description": "Data Missing: essential onboarding data contains incomplete or stale records. RCA, model training and forecasting were not performed because of these data-quality issues; the JSON report was still generated with the information available.",
            "modelSelection": {"status": "Data Missing", "trainingPerformed": False},
            "predictionModels": {
                "rca": {"algorithm": "HistGradientBoostingRegressor", "status": "Not run"},
                "forecast": {"algorithm": "DampedTrend", "status": "Not run"}
            },
            "featureInformation": {
                "dynamicallySelectedFeatures": [],
                "featureCount": 0,
                "leakageProtectionApplied": True,
                "featureEngineeringApplied": False,
                "dynamicFeatureSelectionApplied": False
            }
        }

        gate_report["module"] = SUPABASE_MODULE_NAME
        gate_report["metricName"] = _metric_pascal_case(gate_report.get("metricName"))
        _ONBOARDING_CYCLE_TIME_LEGACY_REPORT = gate_report

        print("\nDATA MISSING — ONBOARDING CYCLE TIME")
        print("Mandatory data issues:", [x["fieldName"] for x in mandatory_data_issues])
        print("RCA: NOT PERFORMED")
        print("FORECAST: NOT PERFORMED")
        print("MODEL TRAINING: NOT PERFORMED")
        print("Report retained in memory; the strict JSON will be pushed directly to Supabase.")
        return


    print("\n" + "=" * 75)

    print("DATA QUALITY REPORT")

    print("=" * 75)

    print("Total company records:", len(company_df))

    print("Missing hire/start dates:", missing_hire)

    print("Missing completion dates:", missing_completion)

    print("Negative duration records:", negative_count)

    print("Zero-day completed records:", zero_days)

    print("Completed records used for training:", len(model_df))

    print("Incomplete/invalid records excluded from target training:",

          len(company_df) - len(model_df))

    print("Percentage missing completion date:",

          round(100 * missing_completion / max(len(company_df), 1), 2), "%")



    if len(model_df) < 15:

        raise ValueError(

            "Too few completed records for a meaningful train/test model. "

            "At least 15 are required by this script, and more are preferable."

        )



    y = model_df["target_cycle_time_days"].astype(float)



    print("\nTARGET DISTRIBUTION — CYCLE TIME IN DAYS")

    print(y.describe().round(3).to_string())





    # ---------------------- 5. INDUSTRY BENCHMARK DETECTION ----------------------



    def get_benchmark(industry):

        """

        Search benchmark worksheet for an onboarding cycle-time row.

        Recognizes ranges such as '3-7 days', '3 to 7', or separate

        numeric lower/upper benchmark columns.

        """

        row_texts = []

        for idx, row in industry.iterrows():

            row_text = " ".join(

                [str(idx)] + [str(v) for v in row.values if pd.notna(v)]

            )

            row_texts.append((idx, row_text, row))



        candidates = [

            item for item in row_texts

            if ("onboarding" in item[1].lower()

                and ("cycle" in item[1].lower()

                     or "time" in item[1].lower()

                     or "duration" in item[1].lower()))

        ]



        for idx, text, row in candidates:

            # First try a range in any cell on the matching row.

            for value in row.values:

                if pd.isna(value):

                    continue

                s = str(value).lower()

                match = re.search(

                    r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*"

                    r"(\d+(?:\.\d+)?)", s

                )

                if match:

                    low, high = float(match.group(1)), float(match.group(2))

                    if low <= high:

                        return low, high, text



            # Then try separate columns containing lower/upper values.

            low_col = find_column(industry, [

                "lower bound", "minimum", "min benchmark", "benchmark min"

            ])

            high_col = find_column(industry, [

                "upper bound", "maximum", "max benchmark", "benchmark max"

            ])



            if low_col and high_col:

                try:

                    low = float(row[low_col])

                    high = float(row[high_col])

                    if low <= high:

                        return low, high, text

                except (TypeError, ValueError):

                    pass



        # As a fallback, search all cells for a range.

        for _, text, _ in row_texts:

            match = re.search(

                r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*"

                r"(\d+(?:\.\d+)?)\s*(?:days?|d)?", text.lower()

            )

            if match:

                low, high = float(match.group(1)), float(match.group(2))

                if low <= high:

                    return low, high, text



        return None, None, None





    benchmark_low, benchmark_high, benchmark_source = get_benchmark(industry_df)



    if benchmark_low is None:

        print("\nWARNING: Could not automatically extract an industry range.")

        print("Industry data preview:")

        display(industry_df.head(10))

        print("Benchmark comparison will be reported as unavailable.")

    else:

        print("\nINDUSTRY BENCHMARK DETECTED")

        print("Metric: Onboarding Cycle Time")

        print(f"Range: {benchmark_low:g} to {benchmark_high:g} days")

        print("Source row:", benchmark_source)





    # ---------------------- 6. DYNAMIC FEATURE ENGINEERING ----------------------



    def add_engineered_features(frame):

        data = frame.copy()



        # Calendar features based on the hire date.

        hire = data[hire_col]

        data["engineered_hire_month"] = hire.dt.month

        data["engineered_hire_quarter"] = hire.dt.quarter

        data["engineered_hire_weekday"] = hire.dt.dayofweek

        data["engineered_hire_year"] = hire.dt.year



        # Use only source dates that are found in this workbook.

        date_alias_sets = {

            "offerAcceptanceDate": [

                "offerAcceptanceDate", "offerAcceptedDate", "offerAcceptDate"

            ],

            "positionFilledDate": [

                "positionFilledDate", "filledDate", "requisitionFilledDate"

            ],

            "applicationDate": [

                "applicationDate", "candidateApplicationDate"

            ],

        }



        detected_dates = {}

        for logical_name, aliases in date_alias_sets.items():

            col = find_column(data, aliases)

            if col is not None:

                detected_dates[logical_name] = col

                data[col] = parse_dates(data[col])



        if "offerAcceptanceDate" in detected_dates:

            col = detected_dates["offerAcceptanceDate"]

            data["engineered_offer_acceptance_days"] = numeric_duration(

                data[col], data[hire_col]

            )



        if "positionFilledDate" in detected_dates:

            col = detected_dates["positionFilledDate"]

            data["engineered_filled_to_hire_days"] = numeric_duration(

                data[col], data[hire_col]

            )



        if "applicationDate" in detected_dates:

            col = detected_dates["applicationDate"]

            data["engineered_application_to_hire_days"] = numeric_duration(

                data[col], data[hire_col]

            )



        # We deliberately do NOT create a feature from the completion date.

        # This avoids directly revealing the target to the model.

        return data, detected_dates





    model_df, detected_date_fields = add_engineered_features(model_df)



    print("\nDYNAMIC FEATURE ENGINEERING")

    print("Detected additional date fields:", detected_date_fields)

    print("Engineered fields:")

    for col in model_df.columns:

        if col.startswith("engineered_"):

            print(" -", col)





    # ---------------------- 7. LEAKAGE-AWARE FEATURE SELECTION ----------------------



    target_col = "target_cycle_time_days"



    # Conservative exclusion list for a model intended to predict cycle time

    # before onboarding is complete. Review business availability before

    # adding any of these fields back into the model.

    leakage_aliases = [

        "onboardingDelayDays",

        "onboardingCompletionDate",

        "completionDate",

        "onboardingCompletedDate",

        "processCompletionDate",

        "target_cycle_time_days",

        "preDay1TasksCompletedCount",

        "engineered_task_completion_ratio",

        "day30MilestoneCompletion",

        "day60MilestoneCompletion",

        "day90MilestoneCompletion",

        "onboardingDelayReason",

        "hrDelayFlag",

    ]



    leakage_normalized = {normalize_name(c) for c in leakage_aliases}

    date_columns = set()



    for col in model_df.columns:

        normalized = normalize_name(col)

        if pd.api.types.is_datetime64_any_dtype(model_df[col]):

            date_columns.add(col)



    # Raw dates are excluded. Engineered calendar/duration features remain.

    date_columns.update(

        c for c in detected_date_fields.values() if c in model_df.columns

    )

    date_columns.add(completion_col)



    excluded_reasons = {}



    for col in model_df.columns:

        norm = normalize_name(col)



        if col == target_col:

            excluded_reasons[col] = "TARGET"

        elif col == employee_col:

            excluded_reasons[col] = "EMPLOYEE_GROUPING_ONLY"

        elif norm in leakage_normalized:

            excluded_reasons[col] = "POTENTIAL_TARGET_LEAKAGE"

        elif col in date_columns or col == hire_col:

            excluded_reasons[col] = "RAW_DATE_EXCLUDED"

        elif any(term in norm for term in [

            "completiondate", "completeddate", "enddate"

        ]):

            excluded_reasons[col] = "POTENTIAL_POST_OUTCOME_DATE"

        elif any(term in norm for term in [

            "employeeid", "personid", "workerid", "newhireid",

            "coordinatorid", "recruiteremployeeid", "managerid"

        ]):

            excluded_reasons[col] = "IDENTIFIER_OR_HIGH_CARDINALITY_RISK"



    excluded_audit = pd.DataFrame([

        {"Field": col, "Reason": reason}

        for col, reason in excluded_reasons.items()

    ])



    candidate_cols = [

        col for col in model_df.columns

        if col not in excluded_reasons and col != target_col

    ]



    # Dynamic quality filters: remove empty, constant and mostly-missing fields.

    feature_data = model_df[candidate_cols].copy()

    feature_data = feature_data.replace([np.inf, -np.inf], np.nan)



    for col in list(feature_data.columns):

        missing_fraction = feature_data[col].isna().mean()

        unique_count = feature_data[col].nunique(dropna=True)



        if missing_fraction > 0.65:

            excluded_reasons[col] = "MORE_THAN_65_PERCENT_MISSING"

            feature_data.drop(columns=[col], inplace=True)

        elif unique_count <= 1:

            excluded_reasons[col] = "CONSTANT_OR_EMPTY"

            feature_data.drop(columns=[col], inplace=True)

        elif (

            not pd.api.types.is_numeric_dtype(feature_data[col])

            and feature_data[col].nunique(dropna=True) > 40

            and feature_data[col].nunique(dropna=True) / len(feature_data) > 0.50

        ):

            excluded_reasons[col] = "HIGH_CARDINALITY_CATEGORICAL"

            feature_data.drop(columns=[col], inplace=True)



    if feature_data.shape[1] == 0:

        raise ValueError(

            "No usable features remain after leakage and quality checks. "

            "Review the detected columns and exclusion audit."

        )



    # Convert numeric-looking text columns dynamically when most non-missing

    # values can be converted safely.

    for col in feature_data.columns:

        if feature_data[col].dtype == "object":

            converted = pd.to_numeric(feature_data[col], errors="coerce")

            non_missing = feature_data[col].notna().sum()

            conversion_ratio = (

                converted.notna().sum() / non_missing if non_missing else 0

            )

            if conversion_ratio >= 0.85:

                feature_data[col] = converted



    # Avoid raw identifier-like fields and post-outcome features by default.

    # The target is kept separate from X.

    X = feature_data.copy()

    y = model_df[target_col].astype(float).reset_index(drop=True)

    X = X.reset_index(drop=True)



    numeric_features = X.select_dtypes(include=[np.number, "bool"]).columns.tolist()

    categorical_features = [

        c for c in X.columns if c not in numeric_features

    ]



    print("\n" + "=" * 75)

    print("LEAKAGE-AWARE DYNAMIC FEATURE SELECTION")

    print("=" * 75)

    print("Completed records:", len(X))

    print("Candidate features retained:", X.shape[1])

    print("Numeric features:", numeric_features)

    print("Categorical features:", categorical_features)

    print("\nExcluded feature audit:")

    display(pd.DataFrame([

        {"Field": col, "Reason": reason}

        for col, reason in excluded_reasons.items()

    ]).reset_index(drop=True))





    # ---------------------- 8. TRAIN/TEST SPLIT ----------------------



    groups = None

    if employee_col and employee_col in model_df.columns:

        groups = model_df[employee_col].reset_index(drop=True)



    if groups is not None and groups.nunique(dropna=True) >= 2:

        groups = groups.fillna("__MISSING_GROUP__").astype(str)

        splitter = GroupShuffleSplit(

            n_splits=1, test_size=0.20, random_state=SEED

        )

        train_idx, test_idx = next(splitter.split(X, y, groups=groups))

        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]

        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        groups_train = groups.iloc[train_idx].reset_index(drop=True)

        split_method = "Group holdout by employee"

    else:

        X_train, X_test, y_train, y_test = train_test_split(

            X, y, test_size=0.20, random_state=SEED

        )

        groups_train = None

        split_method = "Random holdout"



    print("\nTrain records:", len(X_train))

    print("Test records:", len(X_test))

    print("Split method:", split_method)



    if len(X_test) < 5:

        raise ValueError("Test set is too small to evaluate meaningfully.")





    # ---------------------- 9. PREPROCESSING PIPELINE ----------------------



    numeric_pipeline = Pipeline(steps=[

        ("imputer", SimpleImputer(strategy="median"))

    ])



    categorical_pipeline = Pipeline(steps=[

        ("imputer", SimpleImputer(strategy="most_frequent")),

        ("onehot", OneHotEncoder(handle_unknown="ignore"))

    ])



    transformers = []

    if numeric_features:

        transformers.append(("numeric", numeric_pipeline, numeric_features))

    if categorical_features:

        transformers.append(("categorical", categorical_pipeline, categorical_features))



    preprocessor = ColumnTransformer(

        transformers=transformers,

        remainder="drop"

    )



    model_pipeline = Pipeline(steps=[

        ("prep", preprocessor),

        ("select", SelectPercentile(score_func=f_regression, percentile=70)),

        ("model", XGBRegressor(

            objective="reg:squarederror",

            eval_metric="rmse",

            random_state=SEED,

            n_jobs=-1,

            tree_method="hist"

        ))

    ])





    # ---------------------- 10. CROSS-VALIDATION AND TUNING ----------------------



    unique_groups = (

        groups_train.nunique() if groups_train is not None else 0

    )



    if groups_train is not None and unique_groups >= 5:

        cv = GroupKFold(n_splits=min(5, unique_groups))

        fit_groups = groups_train

        print("\nCross-validation: GroupKFold")

    else:

        cv = KFold(

            n_splits=min(5, len(X_train)),

            shuffle=True,

            random_state=SEED

        )

        fit_groups = None

        print("\nCross-validation: shuffled KFold")



    if len(X_train) < 10:

        raise ValueError("Not enough training records for cross-validation.")



    # Search a small, regularized parameter space suited to limited data.

    param_distributions = {

        "select__percentile": [50, 70, 90, 100],

        "model__n_estimators": [80, 120, 180, 250],

        "model__max_depth": [1, 2, 3],

        "model__learning_rate": [0.015, 0.03, 0.05, 0.08],

        "model__min_child_weight": [3, 5, 8, 10],

        "model__subsample": [0.65, 0.8, 0.95],

        "model__colsample_bytree": [0.6, 0.8, 1.0],

        "model__reg_alpha": [0.1, 1.0, 5.0],

        "model__reg_lambda": [2.0, 5.0, 10.0],

        "model__gamma": [0.0, 0.1, 0.3]

    }



    search = RandomizedSearchCV(

        estimator=model_pipeline,

        param_distributions=param_distributions,

        n_iter=18,

        scoring="neg_mean_absolute_error",

        cv=cv,

        random_state=SEED,

        n_jobs=-1,

        refit=True,

        error_score="raise",

        verbose=0

    )



    print("\nTuning regularized XGBoost using training data only...")

    if fit_groups is not None:

        search.fit(X_train, y_train, groups=fit_groups)

    else:

        search.fit(X_train, y_train)



    best_model = search.best_estimator_



    print("\nSelected parameters:")

    print(json.dumps(search.best_params_, indent=2))

    print("Best CV MAE during tuning:",

          round(-search.best_score_, 4), "days")





    # ---------------------- 11. MODEL METRICS ----------------------



    train_pred = best_model.predict(X_train)

    test_pred = best_model.predict(X_test)



    train_metrics = safe_metrics(y_train, train_pred)

    test_metrics = safe_metrics(y_test, test_pred)



    display_metrics("TRAINING PERFORMANCE", train_metrics)

    display_metrics("HOLDOUT TEST PERFORMANCE — UNSEEN RECORDS", test_metrics)



    # Mean baseline: predict the training target mean for every test record.

    baseline_prediction = np.full(len(y_test), y_train.mean())

    baseline_test_metrics = safe_metrics(y_test, baseline_prediction)

    display_metrics("MEAN-PREDICTION TEST BASELINE", baseline_test_metrics)



    print("\n" + "=" * 75)

    print("REPEATED CROSS-VALIDATION RESULTS")

    print("=" * 75)



    # Cross-validation on the training set only, keeping the test set untouched.

    cv_results = cross_validate(

        best_model,

        X_train,

        y_train,

        cv=cv,

        groups=fit_groups,

        scoring={

            "r2": "r2",

            "mae": "neg_mean_absolute_error",

            "rmse": "neg_root_mean_squared_error"

        },

        return_train_score=False,

        n_jobs=1

    )



    cv_r2 = cv_results["test_r2"]

    cv_mae = -cv_results["test_mae"]

    cv_rmse = -cv_results["test_rmse"]



    mean_cv_r2 = float(np.mean(cv_r2))

    std_cv_r2 = float(np.std(cv_r2, ddof=1)) if len(cv_r2) > 1 else 0.0

    mean_cv_mae = float(np.mean(cv_mae))

    mean_cv_rmse = float(np.mean(cv_rmse))



    cv_report = pd.DataFrame({

        "Fold": np.arange(1, len(cv_r2) + 1),

        "R2": cv_r2,

        "MAE_days": cv_mae,

        "RMSE_days": cv_rmse

    })

    display(cv_report.round(4))



    print(f"\nMean CV R²: {mean_cv_r2:.4f}")

    print(f"CV R² standard deviation: {std_cv_r2:.4f}")

    print(f"Mean CV MAE: {mean_cv_mae:.4f} days")

    print(f"Mean CV RMSE: {mean_cv_rmse:.4f} days")



    # Baseline cross-validation using the same training folds.

    baseline_cv = cross_validate(

        DummyRegressor(strategy="mean"),

        np.zeros((len(y_train), 1)),

        y_train,

        cv=cv,

        groups=fit_groups,

        scoring={

            "r2": "r2",

            "mae": "neg_mean_absolute_error",

            "rmse": "neg_root_mean_squared_error"

        },

        n_jobs=1

    )



    baseline_cv_r2 = float(np.mean(baseline_cv["test_r2"]))

    baseline_cv_mae = float(np.mean(-baseline_cv["test_mae"]))

    baseline_cv_rmse = float(np.mean(-baseline_cv["test_rmse"]))



    print("\nBASELINE CROSS-VALIDATION")

    print(f"Baseline CV R²: {baseline_cv_r2:.4f}")

    print(f"Baseline CV MAE: {baseline_cv_mae:.4f} days")

    print(f"Baseline CV RMSE: {baseline_cv_rmse:.4f} days")





    # ---------------------- 12. CLEAR R-SQUARED SUMMARY ----------------------



    display(Markdown("# R-SQUARED RESULTS — ONBOARDING CYCLE TIME"))



    r2_summary = pd.DataFrame([

        {"Evaluation": "Training", "R2": train_metrics["R2"]},

        {"Evaluation": "Holdout test", "R2": test_metrics["R2"]},

        {"Evaluation": "Mean cross-validation", "R2": mean_cv_r2},

        {"Evaluation": "Baseline holdout test", "R2": baseline_test_metrics["R2"]},

        {"Evaluation": "Baseline cross-validation", "R2": baseline_cv_r2}

    ])

    display(r2_summary.round(4))



    print(f"""

    TRAINING R²:                 {train_metrics['R2']:.4f}

    HOLDOUT TEST R²:             {test_metrics['R2']:.4f}

    MEAN CROSS-VALIDATION R²:    {mean_cv_r2:.4f}

    CV R² STANDARD DEVIATION:    {std_cv_r2:.4f}

    BASELINE TEST R²:            {baseline_test_metrics['R2']:.4f}

    BASELINE CV R²:              {baseline_cv_r2:.4f}



    TEST MAE:                    {test_metrics['MAE_days']:.4f} days

    TEST RMSE:                   {test_metrics['RMSE_days']:.4f} days

    CV MAE:                      {mean_cv_mae:.4f} days

    CV RMSE:                     {mean_cv_rmse:.4f} days

    """)



    if test_metrics["R2"] < 0:

        print(

            "INTERPRETATION: Test R² is negative. On this test split, "

            "the model performs worse than the test-target mean reference."

        )

    else:

        print(

            "INTERPRETATION: Test R² is non-negative. The model explains "

            "some test-target variation relative to the test-target mean."

        )



    if train_metrics["R2"] - mean_cv_r2 > 0.20:

        print(

            "GENERALIZATION WARNING: Training R² is substantially higher "

            "than cross-validation R². Possible overfitting should be checked."

        )



    if mean_cv_r2 < 0:

        print(

            "CROSS-VALIDATION WARNING: Mean CV R² is negative. "

            "Performance is unstable or worse than a fold-specific mean baseline."

        )



    print(

        "\nR² is not classification accuracy and must not be interpreted "

        "as a percentage of predictions that are correct."

    )





    # ---------------------- 13. PERMUTATION IMPORTANCE / RCA ----------------------



    print("\n" + "=" * 75)

    print("CONTRIBUTING FACTORS — HOLDOUT PERMUTATION IMPORTANCE")

    print("=" * 75)



    importance_result = permutation_importance(

        best_model,

        X_test,

        y_test,

        scoring="neg_mean_absolute_error",

        n_repeats=20,

        random_state=SEED,

        n_jobs=-1

    )



    importance_df = pd.DataFrame({

        "Feature": X_test.columns,

        "Mean_MAE_Increase": importance_result.importances_mean,

        "Importance_SD": importance_result.importances_std

    }).sort_values("Mean_MAE_Increase", ascending=False)



    display(importance_df.round(4))



    print("""

    Interpretation:

    - Positive MAE increase: shuffling the field made predictions worse on this test set.

    - Near-zero importance: this test set provides little evidence that the field helps.

    - Negative importance: shuffling unexpectedly improved predictions on this test set.

    - Importance does not establish causation. Small test sets can produce unstable rankings.

    """)





    # ---------------------- 14. OPTIONAL SHAP ANALYSIS ----------------------



    shap_summary = None



    try:

        import shap



        print("\nCalculating SHAP values for model explanations...")

        X_train_transformed = best_model.named_steps["prep"].transform(X_train)

        X_train_selected = best_model.named_steps["select"].transform(

            X_train_transformed

        )



        try:

            transformed_names = best_model.named_steps["prep"].get_feature_names_out()

            selected_mask = best_model.named_steps["select"].get_support()
            source_columns_for_shap = list(X_train.columns)
            readable_transformed_names = [
                _humanize_factor_name(name, source_columns_for_shap)
                for name in transformed_names
            ]
            selected_names = np.asarray(readable_transformed_names, dtype=object)[selected_mask]

        except Exception:

            selected_names = np.array([

                f"transformed_feature_{i}"

                for i in range(X_train_selected.shape[1])

            ])



        # Explain a manageable sample of training data.

        n_explain = min(100, X_train_selected.shape[0])

        explainer = shap.TreeExplainer(best_model.named_steps["model"])

        shap_values = explainer.shap_values(X_train_selected[:n_explain])



        shap_summary = pd.DataFrame({
            "Feature": selected_names,
            "Mean_Absolute_SHAP": np.abs(shap_values).mean(axis=0)
        })
        shap_summary = shap_summary[shap_summary["Feature"].astype(str).str.strip().ne("")]
        shap_summary = (
            shap_summary.groupby("Feature", as_index=False)["Mean_Absolute_SHAP"].sum()
            .sort_values("Mean_Absolute_SHAP", ascending=False)
        )




        print("\nTOP SHAP CONTRIBUTING FEATURES")

        display(shap_summary.head(20).round(5))






    except Exception as e:

        print("SHAP analysis could not be completed:", str(e))

        print("Permutation importance remains available as a fallback.")





    # ---------------------- 15. DESCRIPTIVE GROUP ANALYSIS ----------------------



    print("\n" + "=" * 75)

    print("DESCRIPTIVE GROUP ANALYSIS")

    print("=" * 75)



    group_analysis_files = {}

    group_candidates = []



    for aliases in [

        ["locationId", "location"],

        ["departmentId", "departmentName", "department"],

        ["jobRoleId", "jobRole", "jobTitle"],

        ["complianceDocumentType"],

        ["onboardingCoordinatorId"],

        ["hrDelayFlag"],

    ]:

        col = find_column(model_df, aliases)

        if col and col not in group_candidates:

            group_candidates.append(col)



    for col in group_candidates:

        if col in [hire_col, completion_col, target_col, employee_col]:

            continue



        temp = model_df[[col, target_col]].copy()

        temp[col] = temp[col].fillna("Missing").astype(str)



        summary = (

            temp.groupby(col)[target_col]

            .agg(["count", "mean", "median", "std"])

            .reset_index()

            .sort_values("mean", ascending=False)

        )



        # Avoid noisy summaries of tiny categories.

        summary = summary[summary["count"] >= 3]



        if len(summary):

            print(f"\nGroup field: {col}")

            display(summary.round(3))

            filename = f"group_analysis_{normalize_name(col)}.csv"

            summary.to_csv(filename, index=False)

            group_analysis_files[filename] = filename



    print(

        "Group-level differences are descriptive, not proof that a person, "

        "location or department caused a longer cycle time."

    )





    # ---------------------- 16. MISSING-FIELD CONFIGURATION AUDIT ----------------------



    field_families = {

        "Hire/start date": [

            "joiningDate", "hireDate", "startDate", "employmentStartDate"

        ],

        "Onboarding completion date": [

            "onboardingCompletionDate", "completionDate",

            "onboardingCompletedDate"

        ],

        "Onboarding process start timestamp": [

            "onboardingProcessStartTimestamp", "processStartTimestamp"

        ],

        "Employee identifier": ["employeeId", "personId", "workerId"],

        "Department": ["departmentId", "departmentName", "department"],

        "Location": ["locationId", "location"],

        "Pre-Day-1 task due dates": [

            "taskDueDate", "dueDate", "preDay1TaskDueDate"

        ],

        "Pre-Day-1 task status": [

            "taskStatus", "status", "preDay1TaskStatus"

        ],

        "Pre-Day-1 task scheduled count": [

            "preDay1TasksScheduledCount"

        ],

        "Pre-Day-1 task completed count": [

            "preDay1TasksCompletedCount"

        ]

    }



    audit_rows = []

    for family, aliases in field_families.items():

        col = find_column(company_df, aliases)

        audit_rows.append({

            "Field_Family": family,

            "RequiredLevel": "MANDATORY" if family in ["Hire/start date", "Onboarding completion date"] else "NORMAL",

            "Detected_Field": col if col else "None",

            "Availability": "PRESENT" if col else "MISSING",

            "Non_Missing_Count": (

                int(company_df[col].notna().sum()) if col else 0

            )

        })



    configuration_audit = pd.DataFrame(audit_rows)

    print("\nMISSING CONFIGURATION / DATA FIELD AUDIT")

    display(configuration_audit)





    # ---------------------- 17. INDUSTRY COMPARISON ----------------------



    company_mean = float(y.mean())

    company_median = float(y.median())

    company_std = float(y.std(ddof=1)) if len(y) > 1 else 0.0



    print("\n" + "=" * 75)

    print("INDUSTRY BENCHMARK COMPARISON")

    print("=" * 75)

    print(f"Company mean cycle time: {company_mean:.2f} days")

    print(f"Company median: {company_median:.2f} days")

    print(f"Company standard deviation: {company_std:.2f} days")



    benchmark_summary = {

        "benchmark_low_days": benchmark_low,

        "benchmark_high_days": benchmark_high,

        "company_mean_days": company_mean,

        "company_median_days": company_median

    }



    if benchmark_low is not None:

        midpoint = (benchmark_low + benchmark_high) / 2

        variance_midpoint = company_mean - midpoint

        variance_upper = company_mean - benchmark_high

        variance_pct_midpoint = (

            100 * variance_midpoint / midpoint if midpoint != 0 else np.nan

        )

        variance_pct_upper = (

            100 * variance_upper / benchmark_high

            if benchmark_high != 0 else np.nan

        )



        below_pct = 100 * (y < benchmark_low).mean()

        within_pct = 100 * y.between(

            benchmark_low, benchmark_high, inclusive="both"

        ).mean()

        above_pct = 100 * (y > benchmark_high).mean()



        # Operational label based on the upper bound.

        if company_mean <= benchmark_high:

            health_state = "Healthy"

        elif company_mean <= benchmark_high * 1.20:

            health_state = "At risk"

        else:

            health_state = "Critical"



        benchmark_summary.update({

            "benchmark_midpoint_days": midpoint,

            "variance_vs_midpoint_days": variance_midpoint,

            "variance_pct_vs_midpoint": variance_pct_midpoint,

            "variance_vs_upper_days": variance_upper,

            "variance_pct_vs_upper": variance_pct_upper,

            "below_benchmark_pct": below_pct,

            "within_benchmark_pct": within_pct,

            "above_benchmark_pct": above_pct,

            "health_state": health_state

        })



        print(f"Industry benchmark: {benchmark_low:g}–{benchmark_high:g} days")

        print(f"Benchmark midpoint: {midpoint:.2f} days")

        print(f"Variance vs midpoint: {variance_midpoint:+.2f} days")

        print(f"Variance % vs midpoint: {variance_pct_midpoint:+.2f}%")

        print(f"Variance vs upper bound: {variance_upper:+.2f} days")

        print(f"Variance % vs upper bound: {variance_pct_upper:+.2f}%")

        print(f"Below range: {below_pct:.2f}%")

        print(f"Within range: {within_pct:.2f}%")

        print(f"Above range: {above_pct:.2f}%")

        print("Operational health state:", health_state)

        print(

            "Note: the health label follows this script's explicit rule; "

            "it is not automatically an industry-issued classification."

        )

    else:

        health_state = "Benchmark unavailable"

        print("Benchmark range was not parsed; health state cannot be assigned.")





    # ---------------------- 18. MONTHLY AND YEARLY TRENDS ----------------------



    trend_df = model_df[[hire_col, target_col]].dropna().copy()

    trend_df["month"] = trend_df[hire_col].dt.to_period("M").astype(str)

    trend_df["year"] = trend_df[hire_col].dt.year



    monthly_trend = (

        trend_df.groupby("month")[target_col]

        .agg(["mean", "median", "count", "std"])

        .reset_index()

    )

    yearly_trend = (

        trend_df.groupby("year")[target_col]

        .agg(["mean", "median", "count", "std"])

        .reset_index()

    )



    print("\nMONTHLY CYCLE TIME TREND")

    display(monthly_trend.round(3))

    print("\nYEARLY CYCLE TIME TREND")

    display(yearly_trend.round(3))



    monthly_trend.to_csv("monthly_trend.csv", index=False)

    yearly_trend.to_csv("yearly_trend.csv", index=False)








    # ---------------------- 19. HOLDOUT PREDICTIONS ----------------------



    holdout_predictions = pd.DataFrame({

        "Actual_Cycle_Time_Days": y_test.reset_index(drop=True),

        "Predicted_Cycle_Time_Days": test_pred,

    })

    holdout_predictions["Prediction_Error_Days"] = (

        holdout_predictions["Predicted_Cycle_Time_Days"]

        - holdout_predictions["Actual_Cycle_Time_Days"]

    )

    holdout_predictions.to_csv("holdout_predictions.csv", index=False)



    print("\nHOLDOUT PREDICTIONS — FIRST 15 RECORDS")

    display(holdout_predictions.head(15).round(3))





    # ---------------------- 20. EXPORT REPORTS ----------------------



    pd.DataFrame([train_metrics]).to_csv("training_metrics.csv", index=False)

    pd.DataFrame([test_metrics]).to_csv("test_metrics.csv", index=False)

    pd.DataFrame([baseline_test_metrics]).to_csv(

        "baseline_test_metrics.csv", index=False

    )

    r2_summary.to_csv("r_squared_summary.csv", index=False)

    cv_report.to_csv("cross_validation_results.csv", index=False)

    importance_df.to_csv("contributing_factors.csv", index=False)

    configuration_audit.to_csv("missing_configuration_audit.csv", index=False)

    excluded_audit = pd.DataFrame([

        {"Field": col, "Reason": reason}

        for col, reason in excluded_reasons.items()

    ])

    excluded_audit.to_csv("excluded_features_audit.csv", index=False)



    if shap_summary is not None:

        shap_summary.to_csv("shap_contributing_factors.csv", index=False)



    benchmark_summary.update({

        "metric_name": "Onboarding Cycle Time",

        "model_name": "Regularized XGBoost Regression",

        "training_r2": train_metrics["R2"],

        "test_r2": test_metrics["R2"],

        "mean_cv_r2": mean_cv_r2,

        "std_cv_r2": std_cv_r2,

        "mean_cv_mae_days": mean_cv_mae,

        "mean_cv_rmse_days": mean_cv_rmse,

        "baseline_test_r2": baseline_test_metrics["R2"],

        "baseline_cv_r2": baseline_cv_r2,

        "completed_records": len(y),

        "training_records": len(y_train),

        "test_records": len(y_test),

        "missing_completion_records": missing_completion,

        "selected_features": list(X.columns),

        "best_parameters": search.best_params_,

        "split_method": split_method

    })



    # Summary stays in memory; JSON output is sent only to Supabase.



    # Save model artifact.

    import joblib

    joblib.dump(best_model, "final_xgboost_model.joblib")



    report_files = [

        "training_metrics.csv",

        "test_metrics.csv",

        "baseline_test_metrics.csv",

        "r_squared_summary.csv",

        "cross_validation_results.csv",

        "contributing_factors.csv",

        "missing_configuration_audit.csv",

        "excluded_features_audit.csv",

        "monthly_trend.csv",

        "yearly_trend.csv",

        "holdout_predictions.csv",


        "final_xgboost_model.joblib"

    ]
    if os.path.exists("shap_contributing_factors.csv"):

        report_files.append("shap_contributing_factors.csv")



    for filename in group_analysis_files:

        if os.path.exists(filename):

            report_files.append(filename)



    zip_name = "onboarding_cycle_time_improved_report.zip"

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:

        for filename in report_files:

            if os.path.exists(filename):

                zf.write(filename)



    # ---------------------- 21. FINAL DESCRIPTIVE REPORT ----------------------



    display(Markdown("# Final Onboarding Cycle Time Report"))



    print(f"""

    METRIC: Onboarding Cycle Time

    MODEL: Regularized XGBoost Regression



    DATA COVERAGE

    - Total company records: {len(company_df)}

    - Completed target records: {len(y)}

    - Missing completion dates: {missing_completion}

    - Records in training set: {len(y_train)}

    - Records in test set: {len(y_test)}



    MODEL PERFORMANCE

    - Training R²: {train_metrics['R2']:.4f}

    - Holdout test R²: {test_metrics['R2']:.4f}

    - Mean cross-validation R²: {mean_cv_r2:.4f}

    - Cross-validation R² standard deviation: {std_cv_r2:.4f}

    - Test MAE: {test_metrics['MAE_days']:.4f} days

    - Test RMSE: {test_metrics['RMSE_days']:.4f} days

    - Mean CV MAE: {mean_cv_mae:.4f} days

    - Mean CV RMSE: {mean_cv_rmse:.4f} days

    - Baseline test R²: {baseline_test_metrics['R2']:.4f}

    - Baseline CV R²: {baseline_cv_r2:.4f}



    COMPANY CYCLE TIME

    - Mean: {company_mean:.2f} days

    - Median: {company_median:.2f} days

    - Standard deviation: {company_std:.2f} days



    INDUSTRY HEALTH STATE: {health_state}



    RCA STATUS: Exploratory; contributing factors are predictive associations,

    not confirmed causes.

    """)



    print("\nIMPORTANT LIMITATIONS")

    print("1. Missing completion dates were not fabricated.")

    print("2. Results are based only on completed records.")

    print("3. Small sample sizes make R² and feature importance uncertain.")

    print("4. Benchmark comparison does not improve model training targets.")

    print("5. Review the feature availability and exclusion audit before deployment.")


    # ---------------------- 20A. JSON OUTPUT FOR ONBOARDING CYCLE TIME ----------------------
    # This JSON is generated before the ONB2 multi-metric model starts.
    # It follows the same reporting style as the other metric JSON outputs.

    def _json_safe(value):
        if value is None:
            return None
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return None if np.isnan(value) else float(value)
        if isinstance(value, (pd.Timestamp,)):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, float) and np.isnan(value):
            return None
        return value

    def _health_from_cycle_time(value, low, high):
        if low is None or high is None or not np.isfinite(value):
            return "Benchmark unavailable"
        if value <= high:
            return "Healthy"
        if value <= high * 1.20:
            return "At risk"
        return "Critical"

    def _rating_from_r2(r2):
        if r2 >= 0.70:
            return "Good"
        if r2 >= 0.40:
            return "Moderate"
        if r2 >= 0:
            return "Weak"
        return "Poor"

    # Build hierarchical yearly -> quarterly -> monthly trend data.
    cycle_trend = trend_df.copy()
    cycle_trend["date"] = cycle_trend[hire_col]
    cycle_trend["month_period"] = cycle_trend["date"].dt.to_period("M").astype(str)

    yearly_json = build_trend_analysis(cycle_trend["date"], cycle_trend[target_col], higher_is_better=False)["periods"]

    # Forecast from the historical monthly series using BOTH requested models.
    from sklearn.ensemble import HistGradientBoostingRegressor
    monthly_series = cycle_trend.groupby("month_period")[target_col].mean().sort_index().astype(float)

    def _cycle_damped(series, steps=12):
        if len(series) == 0:
            return np.array([np.nan]*steps), np.array([np.nan]*steps), np.array([np.nan]*steps)
        if len(series) == 1:
            a=np.repeat(float(series.iloc[-1]),steps); return a.copy(),a.copy(),a.copy()
        try:
            model=ExponentialSmoothing(series,trend="add",damped_trend=True,seasonal=None,initialization_method="estimated").fit(optimized=True)
            pred=np.asarray(model.forecast(steps),dtype=float)
            resid=np.asarray(series,dtype=float)-np.asarray(model.fittedvalues,dtype=float)
            rs=float(np.nanstd(resid,ddof=1)) if len(resid)>1 else 0.0
            return pred,pred-1.96*rs,pred+1.96*rs
        except Exception:
            x=np.arange(len(series),dtype=float); yv=series.values.astype(float)
            slope,intercept=np.polyfit(x,yv,1) if len(series)>=2 else (0.0,yv[-1])
            fx=np.arange(len(series),len(series)+steps,dtype=float); pred=slope*fx+intercept
            rs=float(np.std(yv-(slope*x+intercept))) if len(yv)>1 else 0.0
            return pred,pred-1.96*rs,pred+1.96*rs

    def _cycle_hgb_one_step(series):
        series=pd.Series(series).dropna().astype(float).reset_index(drop=True)
        if len(series)<4: return None
        Xh=[]; yh=[]
        for i in range(2,len(series)):
            hist=series.iloc[:i]
            Xh.append([i,float(hist.iloc[-1]),float(hist.iloc[-2]),float(hist.tail(3).mean())]); yh.append(float(series.iloc[i]))
        if len(yh)<2: return None
        mdl=HistGradientBoostingRegressor(max_iter=100,learning_rate=0.05,max_leaf_nodes=6,min_samples_leaf=max(2,min(10,len(yh)//4)),l2_regularization=2.0,random_state=42)
        mdl.fit(np.asarray(Xh,dtype=float),np.asarray(yh,dtype=float))
        i=len(series); feat=np.array([[i,float(series.iloc[-1]),float(series.iloc[-2]),float(series.tail(3).mean())]],dtype=float)
        return float(mdl.predict(feat)[0])

    def _cycle_hgb(series,steps=12):
        series=pd.Series(series).dropna().astype(float).reset_index(drop=True)
        if len(series)<4: return np.array([np.nan]*steps),np.array([np.nan]*steps),np.array([np.nan]*steps)
        hist=list(series.values); pred=[]
        for _ in range(steps):
            p=_cycle_hgb_one_step(pd.Series(hist))
            if p is None: return np.array([np.nan]*steps),np.array([np.nan]*steps),np.array([np.nan]*steps)
            pred.append(p); hist.append(p)
        residuals=[]
        for i in range(3,len(series)):
            p=_cycle_hgb_one_step(series.iloc[:i])
            if p is not None: residuals.append(float(series.iloc[i]-p))
        rs=float(np.std(residuals,ddof=1)) if len(residuals)>1 else 0.0
        a=np.asarray(pred,dtype=float); return a,a-1.96*rs,a+1.96*rs

    def _cycle_backtest(series,name):
        actuals=[]; preds=[]; start=4 if name=="HistGradientBoosting" else 3
        for i in range(start,len(series)):
            hist=series.iloc[:i]
            try:
                p=_cycle_hgb_one_step(hist) if name=="HistGradientBoosting" else _cycle_damped(hist,1)[0][0]
                if p is not None and np.isfinite(p): actuals.append(float(series.iloc[i])); preds.append(float(p))
            except Exception: pass
        if not actuals: return {"r2":None,"mae":None,"rmse":None,"observations":0}
        r2=float(r2_score(actuals,preds)) if len(actuals)>=2 and len(np.unique(actuals))>=2 else None
        return {"r2":_json_safe(r2),"mae":_json_safe(mean_absolute_error(actuals,preds)),"rmse":_json_safe(np.sqrt(mean_squared_error(actuals,preds))),"observations":len(actuals)}

    forecast_candidates={"HistGradientBoosting":_cycle_backtest(monthly_series,"HistGradientBoosting"),"DampedTrend":_cycle_backtest(monthly_series,"DampedTrend")}
    eligible_fc=[(n,m) for n,m in forecast_candidates.items() if m["rmse"] is not None]
    if eligible_fc:
        forecast_model_name,best_fc=sorted(eligible_fc,key=lambda z:(z[1]["rmse"],z[1]["mae"] if z[1]["mae"] is not None else float("inf"),-(z[1]["r2"] if z[1]["r2"] is not None else -1e9)))[0]
    else:
        forecast_model_name="DampedTrend" if len(monthly_series)>=2 else "HistGradientBoosting"; best_fc=forecast_candidates[forecast_model_name]
    if forecast_model_name=="HistGradientBoosting":
        future_values,fc_lower,fc_upper=_cycle_hgb(monthly_series,12)
        if not np.isfinite(future_values).all():
            forecast_model_name="DampedTrend"; future_values,fc_lower,fc_upper=_cycle_damped(monthly_series,12)
    else:
        future_values,fc_lower,fc_upper=_cycle_damped(monthly_series,12)
    forecast_r2=best_fc.get("r2"); forecast_mae=best_fc.get("mae"); forecast_rmse=best_fc.get("rmse")
    next_month_value=float(future_values[0]) if len(future_values) else company_mean
    next_quarter_value=float(np.mean(future_values[:3])) if len(future_values)>=3 else next_month_value
    next_year_value=float(np.mean(future_values[:12])) if len(future_values) else next_month_value
    def _forecast_entry(period_label, value):
        if benchmark_low is not None and benchmark_high is not None:
            spread = max((benchmark_high - benchmark_low) * 0.25, 0.01)
            lower = max(0.0, value - spread)
            upper = value + spread
            state = _health_from_cycle_time(value, benchmark_low, benchmark_high)
        else:
            lower = max(0.0, value * 0.90)
            upper = value * 1.10
            state = "Benchmark unavailable"
        return {
            "period": period_label,
            "predictedValue": _json_safe(value),
            "lowerBound": _json_safe(lower),
            "upperBound": _json_safe(upper),
            "predictedHealthState": state
        }

    # RCA uses ONLY the selected model from XGBoost, Logistic Regression, Random Forest.
    # SHAP is the sole factor-attribution method; no segment contribution is calculated.
    cycle_selected_name = "Not run"
    cycle_rca_metrics = {"r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}
    cycle_rca_factors = []
    try:
        cycle_X = dynamic_features(model_df, target_col).reset_index(drop=True)
        cycle_y = model_df[target_col].astype(float).reset_index(drop=True)
        if cycle_X.shape[1] > 0 and len(cycle_y) >= 12 and cycle_y.nunique() >= 2:
            cycle_scores, cycle_fitted, cycle_feature_names, cycle_ytr, cycle_yte = train_three(cycle_X, cycle_y)
            cycle_eligible = cycle_scores[
                np.isfinite(cycle_scores['Testing R2']) &
                (cycle_scores['Testing R2'] < 0.9999) &
                (~cycle_scores['Overfitting Detected'].fillna(False))
            ].copy()
            if not cycle_eligible.empty:
                cycle_row = cycle_eligible.sort_values(['Testing R2','Testing MAE'], ascending=[False,True]).iloc[0]
                cycle_selected_name = str(cycle_row['Algorithm'])
                cycle_obj = cycle_fitted.get(cycle_selected_name)
                cycle_rca_metrics = evaluate_selected_model(cycle_obj.get('model'), cycle_obj.get('X_train'), cycle_ytr)
                cycle_rca_factors = calculate_shap_rca(cycle_obj.get('model'), cycle_obj.get('X_train'), cycle_feature_names, top_n=3)
    except Exception as e:
        print('Cycle-time SHAP RCA warning:', e)

    if benchmark_low is not None and benchmark_high is not None:

        company_value = float(company_mean)
        benchmark_value = float((benchmark_low + benchmark_high) / 2.0)
        variance_value = company_value - benchmark_value
        variance_percentage = (
            100.0 * variance_value / benchmark_value
            if benchmark_value != 0 else None
        )
    else:
        company_value = float(company_mean)
        benchmark_value = None
        variance_value = None
        variance_percentage = None

    cycle_time_json = {
        "generatedAt": pd.Timestamp.now().isoformat(),
        "module": "ONB2",
        "reportVersion": "2.2",
        "metricName": "Onboarding Cycle Time",
        "unit": "days",
        "higherIsBetter": False,
        "companyValue": _json_safe(company_value),
        "industryStandardValue": _json_safe(benchmark_value),
        "healthState": _health_from_cycle_time(company_value, benchmark_low, benchmark_high),
        "variance": {
            "value": _json_safe(variance_value),
            "percentage": _json_safe(variance_percentage)
        },
        "trendAnalysis": build_trend_analysis(cycle_trend["date"], cycle_trend[target_col], higher_is_better=False),
        "forecast": {
            "nextMonth": _forecast_entry("Next Month", next_month_value),
            "nextQuarter": _forecast_entry("Next Quarter", next_quarter_value),
            "nextYear": _forecast_entry("Next Year", next_year_value)
        },
        "rca": {
            "applicable": bool(len(cycle_rca_factors) > 0),
            "breachValue": _json_safe(benchmark_high),
            "factors": cycle_rca_factors
        },
        "dataQuality": {
            "overallRating": ("Good" if missing_completion / max(len(company_df), 1) < 0.10 else "Needs Review"),
            "dataPeriod": {
                "from": _json_safe(cycle_trend["date"].min()),
                "to": _json_safe(cycle_trend["date"].max())
            },
            "recordsAnalysed": int(len(y)),
            "checks": [
                {
                    "checkName": "Incomplete essential records",
                    "category": "Completeness",
                    "failedRecords": int(incomplete_records),
                    "failedPct": _json_safe(100.0 * incomplete_records / max(len(company_df), 1)),
                    "affectedColumns": [str(hire_col), str(completion_col)],
                    "affectedCells": None,
                    "staleRange": None
                },
                {
                    "checkName": "Stale essential records",
                    "category": "Staleness",
                    "failedRecords": int(stale_records),
                    "failedPct": _json_safe(100.0 * stale_records / max(len(company_df), 1)),
                    "affectedColumns": [str(hire_col), str(completion_col)],
                    "affectedCells": None,
                    "staleRange": {"thresholdMonths": STALE_MONTHS, "cutoff": stale_cutoff.strftime("%Y-%m-%d") if stale_cutoff is not None else None}
                },
                {
                    "checkName": "Negative cycle time",
                    "category": "Validity",
                    "failedRecords": int(negative_count),
                    "failedPct": _json_safe(100.0 * negative_count / max(len(company_df), 1)),
                    "affectedColumns": [str(hire_col), str(completion_col)],
                    "affectedCells": None,
                    "staleRange": None
                },
                {
                    "checkName": "Zero-day cycle time",
                    "category": "Validity",
                    "failedRecords": int(zero_days),
                    "failedPct": _json_safe(100.0 * zero_days / max(len(y), 1)),
                    "affectedColumns": [str(target_col)],
                    "affectedCells": None,
                    "staleRange": None
                }
            ]
        },
        "selectedTrainingModel": {
            "rcaModel": {
                "modelName": cycle_selected_name,
                "r2": cycle_rca_metrics["r2"],
                "mae": cycle_rca_metrics["mae"],
                "rmse": cycle_rca_metrics["rmse"],
                "rating": cycle_rca_metrics["rating"]
            },
            "forecastModel": {
                "modelName": forecast_model_name,
                "r2": _json_safe(forecast_r2),
                "mae": _json_safe(forecast_mae),
                "rmse": _json_safe(forecast_rmse),
                "rating": _rating_from_r2(forecast_r2) if forecast_r2 is not None else "Unavailable"
            }
        },
        "missingConfigurations": {
            "mandatoryFieldsMissing": [],
            "otherFieldsMissing": []
        }
    }

    cycle_time_json["module"] = SUPABASE_MODULE_NAME
    cycle_time_json["metricName"] = _metric_pascal_case(cycle_time_json.get("metricName"))
    # Enforce the supplied schema in memory before sending this report to Supabase.
    # This prevents legacy trend metadata from leaking into the cycle-time JSON.
    cycle_time_json = _strict_json_order(cycle_time_json, field_missing=False)
    _ONBOARDING_CYCLE_TIME_LEGACY_REPORT = cycle_time_json

    print("\n" + "=" * 75)
    print("ONBOARDING CYCLE TIME JSON OUTPUT")
    print("=" * 75)
    print("Report prepared in memory for direct Supabase upload.")
    print("Metric:", cycle_time_json["metricName"])
    print("Company value:", cycle_time_json["companyValue"])
    print("Industry standard:", cycle_time_json["industryStandardValue"])
    print("Health state:", cycle_time_json["healthState"])
    print("Test R²:", cycle_time_json["selectedTrainingModel"]["rcaModel"]["r2"])
    print("No local JSON file is created.")

    print("\nAnalysis completed. JSON reports will be pushed to Supabase only.")





# The cycle-time analysis is invoked after company/industry data and helpers are initialized.

# ================================================================
# STEP 2: RUN THE PREVIOUS SUCCESSFACTORS ONB2 MULTI-METRIC MODEL
# ================================================================

# ================================================================

# SUCCESSFACTORS ONB2 - 3 ALGORITHM MODEL SELECTION

# XGBoost + Logistic Regression + Random Forest

# Dynamic field discovery, feature engineering, feature selection,

# leakage protection, R2 comparison, SHAP RCA, trends and variance.

# Local Python execution using the adjacent .env file

# ================================================================



import sys, subprocess, importlib.util, warnings, re, math, os

warnings.filterwarnings('ignore')



# ---------- Install required packages ----------

for module, package in {

    'xgboost':'xgboost', 'shap':'shap', 'sklearn':'scikit-learn',

    'scipy':'scipy', 'statsmodels':'statsmodels', 'openpyxl':'openpyxl'

}.items():

    if importlib.util.find_spec(module) is None:

        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', package])



import numpy as np

import pandas as pd
# display is provided by the IPython/fallback compatibility layer above.

from sklearn.model_selection import train_test_split, KFold

from sklearn.compose import ColumnTransformer

from sklearn.pipeline import Pipeline

from sklearn.impute import SimpleImputer

from sklearn.preprocessing import OneHotEncoder, StandardScaler

from sklearn.feature_selection import mutual_info_regression

from sklearn.metrics import (

    r2_score, mean_absolute_error, mean_squared_error,

    roc_auc_score, average_precision_score, precision_score,

    recall_score, f1_score, brier_score_loss

)

from sklearn.linear_model import LogisticRegression

from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, HistGradientBoostingRegressor

from xgboost import XGBRegressor, XGBClassifier


from statsmodels.tsa.holtwinters import ExponentialSmoothing

import shap



print('='*80)

print('SUCCESSFACTORS ONB2 - DYNAMIC 3-ALGORITHM MODEL SELECTION')

print('='*80)

print('Algorithms: XGBoost | Logistic Regression | Random Forest')

print('Selection rule: highest eligible TEST R² below 0.9999, excluding models flagged by the requested CV overfitting rule.')

print('')



# ---------- Read company workbook from in-memory Supabase bytes ----------
company_xls = pd.ExcelFile(BytesIO(COMPANY_WORKBOOK_BYTES))

print('\nCompany sheets:')
for i, s in enumerate(company_xls.sheet_names, 1):
    print(i, s)

def sheet_score(sheet_name):
    s = sheet_name.lower()
    score = 0
    if 'onb2' in s: score += 100
    if 'onboarding' in s: score += 60
    if 'module' in s: score += 10
    if 'combined' in s: score += 5
    return score

onb_sheet = max(company_xls.sheet_names, key=sheet_score)
print('\nAutomatically selected company sheet:', onb_sheet)
company = pd.read_excel(BytesIO(COMPANY_WORKBOOK_BYTES), sheet_name=onb_sheet)
company.columns = [str(c).strip() for c in company.columns]
print('Company shape:', company.shape)
print('Detected fields:')
print(company.columns.tolist())

# ---------- Read industry workbook from in-memory Supabase bytes ----------
industry_xls = pd.ExcelFile(BytesIO(INDUSTRY_WORKBOOK_BYTES))
industry = None
industry_sheet = None

for s in industry_xls.sheet_names:
    temp = pd.read_excel(BytesIO(INDUSTRY_WORKBOOK_BYTES), sheet_name=s)
    temp.columns = [str(c).strip() for c in temp.columns]
    low = {c.lower().strip(): c for c in temp.columns}
    if 'metric name' in low and 'industry benchmark' in low:
        industry = temp.rename(columns={
            low['metric name']: 'Metric Name',
            low['industry benchmark']: 'Industry Benchmark'
        })
        industry_sheet = s
        break

if industry is None:
    raise ValueError("Industry workbook needs 'Metric Name' and 'Industry Benchmark' columns.")
print('Automatically selected industry sheet:', industry_sheet)
display(industry)

company_df = company.copy()
industry_df = industry.copy()

# ---------- Normalize data ----------

df = company.copy().drop_duplicates().reset_index(drop=True)

for c in df.columns:

    if 'date' in c.lower():

        df[c] = pd.to_datetime(df[c], errors='coerce')



# ---------- Dynamic field discovery ----------

def normalize_name(x):

    return re.sub(r'[^a-z0-9]', '', str(x).lower())



def find_field(columns, groups):

    # groups is a list of lists; all words in one group must be present.

    norm = {c: normalize_name(c) for c in columns}

    for group in groups:

        terms = [normalize_name(t) for t in group]

        hits = [c for c,n in norm.items() if all(t in n for t in terms)]

        if hits:

            return hits[0]

    return None



fields = {}

fields['pre_scheduled'] = find_field(df.columns, [['preday1','task','scheduled','count'], ['preday1','scheduled','count']])

fields['pre_completed'] = find_field(df.columns, [['preday1','task','completed','count'], ['preday1','completed','count']])

fields['m30'] = find_field(df.columns, [['day30','milestone','completion']])

fields['m60'] = find_field(df.columns, [['day60','milestone','completion']])

fields['m90'] = find_field(df.columns, [['day90','milestone','completion']])

fields['comp_due'] = find_field(df.columns, [['compliance','scheduled','date'], ['compliance','due','date']])

fields['comp_actual'] = find_field(df.columns, [['compliance','actual','completion','date'], ['compliance','completion','date']])

fields['join_date'] = find_field(df.columns, [['joining','date'], ['join','date']])

fields['status'] = find_field(df.columns, [['onboarding','status'], ['employment','status']])



print('\nDYNAMICALLY DISCOVERED METRIC FIELDS')

for k,v in fields.items():

    print(f'{k:18s}: {v}')



missing_core = [k for k in ['pre_scheduled','pre_completed','m30','m60','m90','comp_due','comp_actual'] if fields[k] is None]

if missing_core:

    print('\nWARNING: These concepts were not found:', missing_core)

    print('The program will run only metrics for which enough fields are available.')

# Metric-specific mandatory configuration. Missing mandatory fields stop training and RCA.
METRIC_MANDATORY_FIELDS = {
    'Pre-Day-1 Task Completion Rate': ['pre_scheduled', 'pre_completed'],
    'Day 30/60/90 Milestone Completion Rate': ['m30', 'm60', 'm90'],
    'Compliance Documentation Completion Rate': ['comp_due', 'comp_actual']
}
FIELD_LABELS = {
    'pre_scheduled': 'Pre-Day-1 scheduled task count', 'pre_completed': 'Pre-Day-1 completed task count',
    'm30': 'Day-30 milestone completion', 'm60': 'Day-60 milestone completion', 'm90': 'Day-90 milestone completion',
    'comp_due': 'Compliance scheduled/due date', 'comp_actual': 'Compliance actual completion date',
    'join_date': 'Joining/start date', 'status': 'Onboarding/employment status'
}

def get_missing_configuration(metric_name):
    mandatory_keys = METRIC_MANDATORY_FIELDS.get(metric_name, [])
    mandatory_missing = [{'fieldKey': k, 'fieldName': FIELD_LABELS.get(k, k), 'status': 'MISSING'} for k in mandatory_keys if fields.get(k) is None]
    normal_missing = [{'fieldKey': k, 'fieldName': FIELD_LABELS.get(k, k), 'status': 'MISSING'} for k in fields if k not in mandatory_keys and fields.get(k) is None]
    return mandatory_missing, normal_missing



# ---------- Build targets ----------

status = (df[fields['status']].astype('string').str.lower()

           if fields['status'] else pd.Series('', index=df.index, dtype='string'))

not_joined = pd.Series(False, index=df.index)

for key in ['m30','m60','m90']:

    if fields[key]:

        not_joined |= df[fields[key]].astype('string').str.lower().str.contains('not joined|n/a', na=False)

cancelled = status.str.contains('cancelled|canceled', na=False)

eligible_hire = ~(cancelled | not_joined)



# Pre-Day-1

if fields['pre_scheduled'] and fields['pre_completed']:

    scheduled = pd.to_numeric(df[fields['pre_scheduled']], errors='coerce')

    completed = pd.to_numeric(df[fields['pre_completed']], errors='coerce')

    valid_pre = eligible_hire & scheduled.notna() & completed.notna() & (scheduled > 0) & (completed >= 0) & (completed <= scheduled)

    df['__target_pre'] = np.nan

    df.loc[valid_pre, '__target_pre'] = completed.loc[valid_pre] / scheduled.loc[valid_pre] * 100

    pre_actual = 100 * completed.loc[valid_pre].sum() / scheduled.loc[valid_pre].sum() if valid_pre.any() else np.nan

else:

    df['__target_pre'] = np.nan; valid_pre = pd.Series(False, index=df.index); pre_actual = np.nan



# Milestones

milestone_success = pd.Series(0.0, index=df.index)

milestone_applicable = pd.Series(0.0, index=df.index)

for key in ['m30','m60','m90']:

    c = fields[key]

    if c:

        v = df[c].astype('string').str.strip().str.lower()

        ontime = v.str.contains('completed on time|on time', na=False) & ~v.str.contains('late', na=False)

        late = v.str.contains('completed late|late', na=False)

        applicable = ontime | late

        milestone_success += ontime.astype(float)

        milestone_applicable += applicable.astype(float)

valid_milestone = eligible_hire & (milestone_applicable > 0)

df['__target_milestone'] = np.nan

df.loc[valid_milestone, '__target_milestone'] = milestone_success.loc[valid_milestone] / milestone_applicable.loc[valid_milestone] * 100

milestone_actual = 100 * milestone_success.loc[eligible_hire].sum() / milestone_applicable.loc[eligible_hire].sum() if milestone_applicable.loc[eligible_hire].sum() > 0 else np.nan



# Compliance

if fields['comp_due'] and fields['comp_actual']:

    due = pd.to_datetime(df[fields['comp_due']], errors='coerce')

    actual_date = pd.to_datetime(df[fields['comp_actual']], errors='coerce')

    date_values = []

    for c in df.columns:

        if 'date' in c.lower():

            vals = pd.to_datetime(df[c], errors='coerce').dropna()

            if len(vals): date_values.extend(vals.tolist())

    snapshot = max(date_values).normalize() if date_values else pd.Timestamp.today().normalize()

    by_due = actual_date.notna() & due.notna() & (actual_date <= due)

    late = actual_date.notna() & due.notna() & (actual_date > due)

    overdue = actual_date.isna() & due.notna() & (due.dt.normalize() <= snapshot)

    known = eligible_hire & due.notna() & (by_due | late | overdue)

    df['__target_compliance'] = np.nan

    df.loc[known, '__target_compliance'] = np.where(by_due.loc[known], 100.0, 0.0)

    comp_valid = df['__target_compliance'].notna()

    comp_actual = df.loc[comp_valid, '__target_compliance'].mean() if comp_valid.any() else np.nan

else:

    df['__target_compliance'] = np.nan; comp_valid = pd.Series(False, index=df.index); comp_actual = np.nan



print('\nELIGIBLE RECORDS')

print('Pre-Day-1:', int(valid_pre.sum()))

print('Milestones:', int(valid_milestone.sum()))

print('Compliance:', int(comp_valid.sum()))



# ---------- Leakage protection ----------

IDENTITY_WORDS = ['employeeid','applicationid','onboardingid','candidateid','requisitionid','activityid','firstname','lastname','email','name']

LEAKAGE_WORDS = [

    'target','delaydays','delayreason','delayflag','completionflag',

    'actualcompletion','scheduledcompletion','complianceverification',

    'preday1taskscompleted','preday1taskscheduled',

    'day30milestone','day60milestone','day90milestone',

    'complianceactual','compliancescheduled','documentstatus','isdocumentpending'

]



def dynamic_features(frame, target_name):

    X = frame.copy()

    drop = {target_name}

    for c in list(X.columns):

        n = normalize_name(c)

        if n in {normalize_name(x) for x in drop}:

            X.drop(columns=c, inplace=True); continue

        if any(w in n for w in IDENTITY_WORDS):

            X.drop(columns=c, inplace=True); continue

        if any(w in n for w in LEAKAGE_WORDS):

            X.drop(columns=c, inplace=True); continue



    # Dynamic date engineering

    for c in list(X.columns):

        if 'date' in c.lower() or pd.api.types.is_datetime64_any_dtype(X[c]):

            d = pd.to_datetime(X[c], errors='coerce')

            if d.notna().sum() == 0:

                X.drop(columns=c, inplace=True); continue

            X[c+'_year'] = d.dt.year

            X[c+'_month'] = d.dt.month

            X[c+'_dayofweek'] = d.dt.dayofweek

            X[c+'_day'] = d.dt.day

            X.drop(columns=c, inplace=True)



    # Numeric sanitation and dynamic ratios

    numeric = X.select_dtypes(include=[np.number]).columns.tolist()

    for c in numeric:

        X[c] = pd.to_numeric(X[c], errors='coerce').replace([np.inf,-np.inf], np.nan)

    if len(numeric) >= 2:

        # Only add a small number of safe ratios; no target/outcome columns remain.

        added = 0

        for i in range(min(len(numeric), 8)):

            for j in range(i+1, min(len(numeric), 8)):

                a,b = numeric[i],numeric[j]

                if added >= 8: break

                denom = X[b].replace(0,np.nan)

                ratio = X[a] / denom

                if ratio.notna().sum() >= max(10, int(0.10*len(X))):

                    X[f'{str(a)}_to_{str(b)}_ratio'] = ratio.replace([np.inf,-np.inf],np.nan)

                    added += 1

            if added >= 8: break



    # Remove unusable/high-cardinality columns.

    n = max(len(X),1)

    for c in list(X.columns):

        miss = X[c].isna().mean()

        nunique = X[c].nunique(dropna=True)

        if miss > 0.85 or nunique <= 1:

            X.drop(columns=c,inplace=True); continue

        if not pd.api.types.is_numeric_dtype(X[c]) and nunique > 30 and nunique/n > 0.8:

            X.drop(columns=c,inplace=True)

    # Convert pandas NA to ordinary NaN before sklearn/XGBoost.

    for c in X.columns:

        if pd.api.types.is_numeric_dtype(X[c]):

            X[c] = pd.to_numeric(X[c], errors='coerce').astype(float)

        else:

            X[c] = X[c].astype(object).where(pd.notna(X[c]), np.nan)

    return X



# ---------- Industry benchmark ----------

def benchmark_for(metric):

    names = industry['Metric Name'].astype(str).str.strip()

    hit = industry[names.str.lower() == metric.lower()]

    if hit.empty:

        hit = industry[names.str.lower().str.contains(re.escape(metric.lower()), na=False)]

    if hit.empty: return None

    row = hit.iloc[0]

    nums = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', str(row['Industry Benchmark']))[:2]]

    if not nums:

        return {'text':str(row['Industry Benchmark']),'mid':None,'low':None,'high':None}

    lo,hi=min(nums),max(nums)

    return {'text':str(row['Industry Benchmark']),'mid':(lo+hi)/2,'low':lo,'high':hi}



def safe_r2(y_true, y_pred):

    y_true=np.asarray(y_true,dtype=float); y_pred=np.asarray(y_pred,dtype=float)

    if len(y_true)<2 or np.unique(y_true).size<2: return np.nan

    return float(r2_score(y_true,y_pred))



def clean_matrix(A):

    A = np.asarray(A, dtype=float)

    A[~np.isfinite(A)] = 0.0

    return A



def _humanize_factor_name(raw_name, source_columns=None):
    """Map encoded/model names to readable source fields; never invent placeholders."""
    if raw_name is None:
        return ""
    raw = str(raw_name).strip()
    if not raw or raw.lower() in {"none", "nan", "null"}:
        return ""

    body = raw
    prefix = ""
    for candidate in ("numeric__", "categorical__", "num__", "cat__", "remainder__", "numeric_", "categorical_", "num_", "cat_"):
        if body.lower().startswith(candidate):
            prefix = candidate
            body = body[len(candidate):]
            break

    # Map one-hot names like `cat__Manager Problem_Yes` to source field
    # `Manager Problem`. Longest-first matching supports underscores/spaces.
    columns = [str(c).strip() for c in (source_columns or []) if str(c).strip()]
    source_name = None
    for column in sorted(set(columns), key=len, reverse=True):
        if body == column or body.startswith(column + "_") or body.startswith(column + "="):
            source_name = column
            break

    if source_name is not None:
        body = source_name
    elif prefix in {"cat__", "categorical__", "cat_", "categorical_"}:
        # Never emit a category fragment as if it were a source-field name.
        return ""

    normalized_body = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", body)
    normalized_body = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", normalized_body)
    words = re.sub(r"[^A-Za-z0-9]+", " ", normalized_body).strip().split()
    if not words:
        return ""

    if re.fullmatch(r"engineered\s+ratio\s*\d*", " ".join(words), flags=re.I):
        return ""
    if re.fullmatch(r"(?:feature|transformed feature|x)\s*\d*", " ".join(words), flags=re.I):
        return ""
    if re.fullmatch(r"(?:\d+|x\d+)", " ".join(words), flags=re.I):
        return ""

    acronyms = {"hr", "id", "ctc", "sap", "kpi", "r2", "api", "url"}
    humanized = [w.upper() if w.lower() in acronyms else w[0].upper() + w[1:].lower() for w in words]
    result = " ".join(humanized).strip()
    if result.lower() in {"num", "cat", "numeric", "categorical", "feature", "unknown"}:
        return ""
    return result


def _shorten_rca_factor_name(label):
    """Create an understandable, descriptive RCA label without truncating meaningful words."""
    if label is None:
        return ""
    text_value = str(label).strip()
    if not text_value or text_value.lower() in {"none", "nan", "null", "unknown"}:
        return ""

    # These aliases use plain-language labels while preserving the full meaning
    # of the underlying field. Do not abbreviate or truncate labels to a fixed
    # number of words.
    key = normalize_name(text_value)
    aliases = {
        # HR / onboarding dimensions
        "managerproblem": "Manager Problem",
        "managerissue": "Manager Issue",
        "managerconcern": "Manager Concern",
        "managerfeedback": "Manager Feedback",
        "department": "Department",
        "departmentid": "Department ID",
        "departmentname": "Department Name",
        "location": "Location",
        "locationid": "Location ID",
        "locationname": "Location Name",
        "jobroleid": "Job Role ID",
        "jobrolename": "Job Role Name",
        "jobtitle": "Job Title",
        "onboardingcoordinatorid": "Onboarding Coordinator ID",
        "onboardingcoordinator": "Onboarding Coordinator",
        "onboardingcoordinatorname": "Onboarding Coordinator Name",
        "compliancedocumenttype": "Compliance Document Type",
        "hrdelayflag": "HR Delay Flag",
        "employeetype": "Employee Type",
        "employeeid": "Employee ID",
        "employeeidentifier": "Employee Identifier",
        "personid": "Person ID",
        "workerid": "Worker ID",
        "newhireid": "New Hire ID",
        # Calendar features derived from the hire/start date
        "engineeredhiremonth": "Month of Hire Date",
        "hiremonth": "Month of Hire Date",
        "engineeredhirequarter": "Quarter of Hire Date",
        "hirequarter": "Quarter of Hire Date",
        "engineeredhireweekday": "Weekday of Hire Date",
        "hireweekday": "Weekday of Hire Date",
        "engineeredhireyear": "Year of Hire Date",
        "hireyear": "Year of Hire Date",
        # Date intervals are described in the order they are calculated
        "engineeredofferacceptancedays": "Days from Offer Acceptance to Hire",
        "engineeredfilledtohiredays": "Days from Position Filled to Hire",
        "engineeredapplicationtohiredays": "Days from Application to Hire",
        # Task and onboarding fields
        "preday1taskduedates": "Pre-Day-1 Task Due Dates",
        "preday1taskduedate": "Pre-Day-1 Task Due Date",
        "taskduedate": "Task Due Date",
        "duedate": "Due Date",
        "preday1taskstatus": "Pre-Day-1 Task Status",
        "taskstatus": "Task Status",
        "preday1tasksscheduledcount": "Pre-Day-1 Tasks Scheduled Count",
        "preday1taskscompletedcount": "Pre-Day-1 Tasks Completed Count",
        "tasksscheduledcount": "Tasks Scheduled Count",
        "taskscompletedcount": "Tasks Completed Count",
        "onboardingcompletiondate": "Onboarding Completion Date",
        "onboardingcompleteddate": "Onboarding Completion Date",
        "completiondate": "Completion Date",
        "joiningdate": "Joining Date",
        "hiredate": "Hire Date",
        "startdate": "Start Date",
        "employmentstartdate": "Employment Start Date",
        # Recruitment / staffing dimensions if they appear in the selected features
        "numberofpositionsfilled": "Number of Positions Filled",
        "noofpositionsfilled": "Number of Positions Filled",
        "positionsfilled": "Positions Filled",
        "totalapplicants": "Total Applicants",
        "applicantsinterviewed": "Number of Applicants Interviewed",
        "offersextended": "Number of Offers Extended",
        "offersaccepted": "Number of Offers Accepted",
    }
    if key in aliases:
        return aliases[key]

    # Generic fallback: convert technical/camelCase names to a readable label.
    # Only remove the internal "engineered" prefix; preserve the rest of the
    # field name instead of arbitrarily taking its first two or three words.
    value = text_value
    value = re.sub(r"^(?:numeric|categorical|num|cat|remainder)__", "", value, flags=re.I)
    value = re.sub(r"^engineered[_\s]+", "", value, flags=re.I)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    value = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", value)
    tokens = re.sub(r"[^A-Za-z0-9]+", " ", value).strip().split()
    if not tokens:
        return ""

    # Do not expose transformer/index placeholders as business factors.
    normalized_tokens = " ".join(tokens).strip().lower()
    if re.fullmatch(r"(?:feature|transformed feature|x|numeric|categorical|num|cat)\s*\d*", normalized_tokens):
        return ""
    if re.fullmatch(r"(?:\d+|x\d+)", normalized_tokens):
        return ""

    acronyms = {"hr", "id", "ctc", "sap", "kpi", "r2", "api", "url"}
    return " ".join(
        token.upper() if token.lower() in acronyms else token[0].upper() + token[1:].lower()
        for token in tokens
    )


def prepare_features(X_train, X_test, y_train):
    num = X_train.select_dtypes(include=[np.number]).columns.tolist()
    cat = [c for c in X_train.columns if c not in num]
    transformers=[]
    if num:
        transformers.append(('num', Pipeline([('imp',SimpleImputer(strategy='median'))]), num))
    if cat:
        transformers.append(('cat', Pipeline([('imp',SimpleImputer(strategy='most_frequent')),('oh',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]), cat))
    prep=ColumnTransformer(transformers=transformers,remainder='drop')
    A=clean_matrix(prep.fit_transform(X_train)); B=clean_matrix(prep.transform(X_test))
    names=prep.get_feature_names_out()
    if A.shape[1] == 0: raise ValueError('No usable features after preprocessing.')
    # Dynamic selection using training data only.
    if A.shape[1] > 1 and len(y_train) >= 8:
        mi=mutual_info_regression(A,np.asarray(y_train,dtype=float),random_state=42)
        k=min(A.shape[1],max(5,min(30,int(np.sqrt(A.shape[1])*3))))
        idx=np.argsort(mi)[::-1][:k]
    else:
        idx=np.arange(A.shape[1])
    # Store source labels, not ColumnTransformer labels such as num__managerProblem.
    source_columns = list(X_train.columns)
    readable_names = [_humanize_factor_name(names[i], source_columns) for i in idx]
    return A[:,idx],B[:,idx],readable_names,prep

# ---------- Three algorithms ----------

# Logistic regression is a classifier, so for fair R2 comparison its predicted

# success probability is mapped to 0-100 and compared with the same completion-rate target.

# It also reports ROC-AUC/precision/recall/F1.



def train_three(X,y):
    """Train XGBoost, Logistic Regression and Random Forest with fold CV.

    The existing train/test split and dynamic feature preparation are preserved.
    CV is used only to quantify generalisation stability and apply the requested
    overfitting rule:
        train_cv_gap > cv_std AND (-test_cv_gap) > cv_std
    where train_cv_gap = train_R2 - mean_CV_R2 and
    test_cv_gap = test_R2 - mean_CV_R2.
    """
    test_n=max(2,int(np.ceil(len(y)*0.25)))
    test_n=min(test_n,len(y)-2)
    Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=test_n,random_state=42)
    A,B,feature_names,prep=prepare_features(Xtr,Xte,ytr)

    models={
        'XGBoost': XGBRegressor(
            n_estimators=120,max_depth=2,learning_rate=0.03,
            subsample=0.85,colsample_bytree=0.85,reg_lambda=8,
            min_child_weight=3,objective='reg:squarederror',
            random_state=42,n_jobs=-1
        ),
        'Random Forest': RandomForestRegressor(
            n_estimators=250,max_depth=6,min_samples_leaf=3,
            max_features='sqrt',random_state=42,n_jobs=-1
        ),
        'Logistic Regression': LogisticRegression(
            C=0.5,max_iter=2000,class_weight='balanced'
        )
    }

    rows=[]; fitted={}
    n_splits=min(5, len(ytr))

    def cv_scores_for_model(name):
        if n_splits < 3:
            return [], [], []
        kf=KFold(n_splits=n_splits,shuffle=True,random_state=42)
        cv_r2=[]; cv_mae=[]; cv_rmse=[]
        for tr_idx, val_idx in kf.split(A):
            m = models[name]
            try:
                if name=='Logistic Regression':
                    y_fold=np.asarray(ytr)[tr_idx]
                    y_val=np.asarray(ytr)[val_idx]
                    y_fold_bin=(y_fold>=50).astype(int)
                    if len(np.unique(y_fold_bin))<2:
                        continue
                    scaler=StandardScaler()
                    Atr=scaler.fit_transform(A[tr_idx]); Aval=scaler.transform(A[val_idx])
                    m_fold=LogisticRegression(C=0.5,max_iter=2000,class_weight='balanced')
                    m_fold.fit(Atr,y_fold_bin)
                    pred=m_fold.predict_proba(Aval)[:,1]*100
                else:
                    m_fold = XGBRegressor(
                        n_estimators=120,max_depth=2,learning_rate=0.03,
                        subsample=0.85,colsample_bytree=0.85,reg_lambda=8,
                        min_child_weight=3,objective='reg:squarederror',
                        random_state=42,n_jobs=-1
                    ) if name=='XGBoost' else RandomForestRegressor(
                        n_estimators=250,max_depth=6,min_samples_leaf=3,
                        max_features='sqrt',random_state=42,n_jobs=-1
                    )
                    m_fold.fit(A[tr_idx],np.asarray(ytr)[tr_idx])
                    pred=m_fold.predict(A[val_idx])
                    y_val=np.asarray(ytr)[val_idx]
                r=safe_r2(y_val,pred)
                if np.isfinite(r): cv_r2.append(float(r))
                cv_mae.append(float(mean_absolute_error(y_val,pred)))
                cv_rmse.append(float(np.sqrt(mean_squared_error(y_val,pred))))
            except Exception:
                continue
        return cv_r2,cv_mae,cv_rmse

    for name,model in models.items():
        try:
            if name=='Logistic Regression':
                ytr_bin=(np.asarray(ytr)>=50).astype(int)
                yte_bin=(np.asarray(yte)>=50).astype(int)
                if len(np.unique(ytr_bin))<2:
                    raise ValueError('training split contains only one class')
                scaler=StandardScaler()
                As=scaler.fit_transform(A); Bs=scaler.transform(B)
                model.fit(As,ytr_bin)
                p_tr=model.predict_proba(As)[:,1]*100
                p_te=model.predict_proba(Bs)[:,1]*100
                pred_bin=(p_te>=50).astype(int)
                Xtr_model,Xte_model=As,Bs
                roc=roc_auc_score(yte_bin,p_te/100) if len(np.unique(yte_bin))==2 else np.nan
                pra=average_precision_score(yte_bin,p_te/100) if len(np.unique(yte_bin))==2 else np.nan
                prec=precision_score(yte_bin,pred_bin,zero_division=0)
                rec=recall_score(yte_bin,pred_bin,zero_division=0)
                f1=f1_score(yte_bin,pred_bin,zero_division=0)
                brier=brier_score_loss(yte_bin,p_te/100)
            else:
                model.fit(A,ytr)
                p_tr=model.predict(A); p_te=model.predict(B)
                Xtr_model,Xte_model=A,B
                roc=pra=prec=rec=f1=brier=np.nan

            cv_r2,cv_mae,cv_rmse=cv_scores_for_model(name)
            mean_cv_r2=float(np.mean(cv_r2)) if cv_r2 else np.nan
            cv_std=float(np.std(cv_r2,ddof=1)) if len(cv_r2)>1 else 0.0
            mean_cv_mae=float(np.mean(cv_mae)) if cv_mae else np.nan
            mean_cv_rmse=float(np.mean(cv_rmse)) if cv_rmse else np.nan
            train_r2=safe_r2(ytr,p_tr); test_r2=safe_r2(yte,p_te)
            train_cv_gap=(train_r2-mean_cv_r2) if np.isfinite(train_r2) and np.isfinite(mean_cv_r2) else np.nan
            test_cv_gap=(test_r2-mean_cv_r2) if np.isfinite(test_r2) and np.isfinite(mean_cv_r2) else np.nan
            overfit=(
                np.isfinite(train_cv_gap) and np.isfinite(test_cv_gap) and
                train_cv_gap > cv_std and (-test_cv_gap) > cv_std
            )
            row={
                'Algorithm':name,
                'Training R2':train_r2,
                'Testing R2':test_r2,
                'Training MAE':mean_absolute_error(ytr,p_tr),
                'Testing MAE':mean_absolute_error(yte,p_te),
                'Testing RMSE':np.sqrt(mean_squared_error(yte,p_te)),
                'Mean CV R2':mean_cv_r2,
                'CV R2 Std':cv_std,
                'Mean CV MAE':mean_cv_mae,
                'Mean CV RMSE':mean_cv_rmse,
                'Train-CV Gap':train_cv_gap,
                'Test-CV Gap':test_cv_gap,
                'Overfitting Detected':bool(overfit),
                'Overfitting Rule':'train_cv_gap > cv_std AND (-test_cv_gap) > cv_std',
                'CV Folds':len(cv_r2),
                'ROC-AUC':roc,'PR-AUC':pra,'Precision':prec,'Recall':rec,'F1':f1,'Brier':brier,
                'model':model,'X_train':Xtr_model,'X_test':Xte_model
            }
            rows.append(row); fitted[name]=row
        except Exception as e:
            rows.append({
                'Algorithm':name,'Training R2':np.nan,'Testing R2':np.nan,
                'Training MAE':np.nan,'Testing MAE':np.nan,'Testing RMSE':np.nan,
                'Mean CV R2':np.nan,'CV R2 Std':np.nan,'Mean CV MAE':np.nan,
                'Mean CV RMSE':np.nan,'Train-CV Gap':np.nan,'Test-CV Gap':np.nan,
                'Overfitting Detected':False,
                'Overfitting Rule':'train_cv_gap > cv_std AND (-test_cv_gap) > cv_std',
                'CV Folds':0,'ROC-AUC':np.nan,'PR-AUC':np.nan,'Precision':np.nan,
                'Recall':np.nan,'F1':np.nan,'Brier':np.nan,'Error':str(e)
            })

    return pd.DataFrame(rows),fitted,feature_names,ytr,yte



# ---------- Selected-model RCA using SHAP ----------
def _selected_model_predictions(model, X_model):
    if model is None or X_model is None:
        return None
    if isinstance(model, LogisticRegression):
        return np.asarray(model.predict_proba(X_model)[:, 1] * 100.0, dtype=float)
    return np.asarray(model.predict(X_model), dtype=float)


def evaluate_selected_model(model, X_model, y):
    if model is None or X_model is None or len(y) < 2:
        return {"r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}
    try:
        pred = _selected_model_predictions(model, X_model)
        r2 = float(r2_score(y, pred)) if len(np.unique(y)) >= 2 else None
        mae = float(mean_absolute_error(y, pred))
        rmse = float(np.sqrt(mean_squared_error(y, pred)))
        return {"r2": fmt_num(r2, 4), "mae": fmt_num(mae, 4), "rmse": fmt_num(rmse, 4), "rating": model_rating(r2)}
    except Exception as e:
        print("Selected-model evaluation warning:", e)
        return {"r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}


def calculate_shap_rca(model, X_model, feature_names, top_n=3):
    """Return SHAP RCA with readable source-field labels only, no placeholder names."""
    if model is None or X_model is None or len(X_model) == 0:
        return []
    if not isinstance(feature_names, (list, tuple, np.ndarray)) or len(feature_names) == 0:
        print("SHAP RCA skipped: no source-field names are available.")
        return []
    try:
        import shap
        X_arr = np.asarray(X_model)
        if X_arr.ndim != 2 or X_arr.shape[1] == 0:
            return []
        names = [str(x).strip() if x is not None else "" for x in feature_names]
        if isinstance(model, LogisticRegression):
            explainer = shap.LinearExplainer(model, X_arr)
            shap_values = explainer.shap_values(X_arr)
        elif isinstance(model, (XGBRegressor, RandomForestRegressor)):
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X_arr)
        else:
            raise TypeError("RCA model must be XGBoost, Logistic Regression, or Random Forest.")
        if isinstance(shap_values, list):
            shap_values = shap_values[-1]
        shap_values = np.asarray(shap_values, dtype=float)
        if shap_values.ndim == 3:
            shap_values = shap_values[:, :, -1]
        if shap_values.ndim != 2 or shap_values.shape[1] != X_arr.shape[1]:
            print("SHAP RCA skipped: SHAP output did not align with selected features.")
            return []

        mean_abs = np.nanmean(np.abs(shap_values), axis=0)
        grouped_impacts = {}
        for idx, impact in enumerate(mean_abs):
            if idx >= len(names) or not np.isfinite(impact):
                continue
            label = _shorten_rca_factor_name(_humanize_factor_name(names[idx]))
            if not label:
                continue
            grouped_impacts[label] = grouped_impacts.get(label, 0.0) + float(impact)

        if not grouped_impacts:
            print("SHAP RCA returned no factors with valid source-field names; no placeholders were added.")
            return []

        total = float(sum(grouped_impacts.values()))
        ranked = sorted(grouped_impacts.items(), key=lambda item: item[1], reverse=True)[:max(0, int(top_n))]
        factors = []
        for rank, (label, impact) in enumerate(ranked, start=1):
            factors.append({
                "rank": rank,
                "factorName": label,
                "avgFactorValue": None,
                "impactValue": fmt_num(impact),
                "impactPct": fmt_num((impact / total * 100.0) if total > 0 else 0.0)
            })
        return factors
    except Exception as e:
        print("SHAP RCA warning:", e)
        return []


# ================================================================
# RESTORED SHARED REPORTING / TREND / FORECAST HELPERS
# Trend output intentionally follows only the supplied hierarchical JSON schema.
# ================================================================
STALE_MONTHS = 3

def json_safe(value):
    """Convert numpy/pandas values to JSON-safe Python values."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return None if not np.isfinite(value) else value
    if isinstance(value, (list, tuple)):
        return [json_safe(x) for x in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    return value

def fmt_num(x, digits=2):
    if x is None or pd.isna(x):
        return None
    return round(float(x), digits)

def health_state(actual, benchmark, higher_is_better=True):
    """
    Uses the company-vs-industry comparison to produce:
    healthy / at-risk / critical.
    """
    if actual is None or benchmark is None or pd.isna(actual) or pd.isna(benchmark):
        return "unavailable"

    actual = float(actual)
    benchmark = float(benchmark)

    if benchmark == 0:
        return "healthy" if actual == 0 else "at-risk"

    # For a rate where higher is better:
    # >= benchmark is healthy; moderate deterioration is at-risk;
    # large deterioration is critical.
    if higher_is_better:
        pct_gap = ((actual - benchmark) / abs(benchmark)) * 100
    else:
        pct_gap = ((benchmark - actual) / abs(benchmark)) * 100

    if pct_gap >= 0:
        return "healthy"
    elif pct_gap >= -20:
        return "at-risk"
    else:
        return "critical"

def model_rating(r2, mae=None, rmse=None):
    if r2 is None or pd.isna(r2):
        return "unavailable"
    if r2 >= 0.80:
        return "good"
    if r2 >= 0.60:
        return "fair"
    if r2 >= 0.40:
        return "weak"
    return "poor"

def prediction_health(value, benchmark, higher_is_better=True):
    return health_state(value, benchmark, higher_is_better)

def build_trend_analysis(dates, values, higher_is_better=True):
    trend = pd.DataFrame({
        "date": pd.to_datetime(dates, errors="coerce"),
        "value": pd.to_numeric(values, errors="coerce")
    }).dropna()

    if trend.empty:
        return {
            "direction": "unavailable",
            "granularity": "yearly",
            "periods": []
        }

    trend["year"] = trend["date"].dt.year
    trend["quarter"] = trend["date"].dt.quarter
    trend["month"] = trend["date"].dt.month

    yearly = trend.groupby("year")["value"].mean()
    monthly = trend.groupby(
        trend["date"].dt.to_period("M")
    )["value"].mean()

    # Determine trend direction from first/last available periods.
    if len(monthly) >= 2:
        first_v = float(monthly.iloc[0])
        last_v = float(monthly.iloc[-1])

        if abs(last_v - first_v) < 1e-9:
            direction = "stable"
        elif higher_is_better:
            direction = "up" if last_v > first_v else "down"
        else:
            # For metrics where lower is better, decreasing values are
            # directionally positive, but the JSON still reports the
            # actual mathematical direction.
            direction = "up" if last_v > first_v else "down"
    else:
        direction = "stable"

    yearly_periods = []

    for year, ygrp in trend.groupby("year"):
        q_periods = []

        for quarter in sorted(ygrp["quarter"].unique()):
            qgrp = ygrp[ygrp["quarter"] == quarter]
            q_avg = qgrp["value"].mean()

            month_periods = []

            for month in sorted(qgrp["month"].unique()):
                mgrp = qgrp[qgrp["month"] == month]
                month_value = mgrp["value"].mean()

                month_periods.append({
                    "period": f"{int(year):04d}-{int(month):02d}",
                    "month": int(month),
                    "average": fmt_num(month_value),
                    "isPartial": False
                })

            q_periods.append({
                "period": f"{int(year):04d}-Q{int(quarter)}",
                "quarter": int(quarter),
                "average": fmt_num(q_avg),
                "isPartial": False,
                "children": {
                    "granularity": "monthly",
                    "periods": month_periods
                }
            })

        yearly_periods.append({
            "period": str(int(year)),
            "year": int(year),
            "average": fmt_num(ygrp["value"].mean()),
            "isPartial": False,
            "children": {
                "granularity": "quarterly",
                "periods": q_periods
            }
        })

    return {
        "direction": direction,
        "granularity": "yearly",
        "periods": yearly_periods
    }

def damped_trend_forecast(monthly_series, steps):
    """
    Forecast using Holt-Winters ExponentialSmoothing with a damped trend.
    Falls back to a linear trend when the series is too short.
    """
    s = pd.Series(monthly_series).dropna().astype(float)

    if len(s) == 0:
        return [np.nan] * steps, [np.nan] * steps, [np.nan] * steps

    if len(s) == 1:
        pred = [float(s.iloc[-1])] * steps
        return pred, pred.copy(), pred.copy()

    try:
        # DampedTrend model requested by the supplied JSON format.
        model = ExponentialSmoothing(
            s,
            trend="add",
            damped_trend=True,
            seasonal=None,
            initialization_method="estimated"
        ).fit(optimized=True)

        pred = np.asarray(model.forecast(steps), dtype=float)

        # Approximate uncertainty using historical residual variation.
        fitted = np.asarray(model.fittedvalues, dtype=float)
        residuals = np.asarray(s, dtype=float) - fitted
        residual_std = float(np.nanstd(residuals, ddof=1)) if len(residuals) > 1 else 0.0

        lower = pred - 1.96 * residual_std
        upper = pred + 1.96 * residual_std

        return pred.tolist(), lower.tolist(), upper.tolist()

    except Exception:
        # Robust fallback: linear trend.
        x = np.arange(len(s), dtype=float)
        y = s.values.astype(float)

        if len(s) >= 2:
            slope, intercept = np.polyfit(x, y, 1)
            future_x = np.arange(len(s), len(s) + steps, dtype=float)
            pred = slope * future_x + intercept
        else:
            pred = np.repeat(y[-1], steps)

        residuals = y - (slope * x + intercept) if len(s) >= 2 else np.zeros(len(s))
        residual_std = float(np.std(residuals)) if len(residuals) else 0.0

        lower = pred - 1.96 * residual_std
        upper = pred + 1.96 * residual_std

        return pred.tolist(), lower.tolist(), upper.tolist()


def _stale_record_info(date_series):
    d=pd.to_datetime(date_series,errors='coerce')
    valid=d.dropna()
    if valid.empty:
        return pd.Series(False,index=d.index), None, None
    latest=valid.max()
    cutoff=latest-pd.DateOffset(months=STALE_MONTHS)
    mask=d.notna() & (d < cutoff)
    return mask, cutoff, latest

def _hgb_make_features(series):
    s=pd.Series(series).dropna().astype(float).reset_index(drop=True)
    rows=[]
    for i in range(2,len(s)):
        hist=s.iloc[:i]
        rows.append([i,float(hist.iloc[-1]),float(hist.iloc[-2]),float(hist.tail(3).mean())])
    if not rows:
        return np.empty((0,4)),np.empty((0,))
    return np.asarray([r[:4] for r in rows],dtype=float),np.asarray([s.iloc[r[0]] for r in rows],dtype=float)

def _hgb_one_step(history):
    s=pd.Series(history).dropna().astype(float).reset_index(drop=True)
    if len(s)<4: return None
    X,yv=_hgb_make_features(s)
    if len(yv)<2: return None
    model=HistGradientBoostingRegressor(max_iter=100,learning_rate=0.05,max_leaf_nodes=6,min_samples_leaf=max(2,min(10,len(yv)//4)),l2_regularization=2.0,random_state=42)
    model.fit(X,yv)
    i=len(s)
    feat=np.array([[i,float(s.iloc[-1]),float(s.iloc[-2]),float(s.tail(3).mean())]],dtype=float)
    return float(model.predict(feat)[0])

def hgb_forecast(monthly_series, steps):
    s=pd.Series(monthly_series).dropna().astype(float).reset_index(drop=True)
    if len(s)<4:
        return [np.nan]*steps,[np.nan]*steps,[np.nan]*steps
    hist=list(s.values.astype(float)); preds=[]
    for _ in range(steps):
        p=_hgb_one_step(pd.Series(hist))
        if p is None: return [np.nan]*steps,[np.nan]*steps,[np.nan]*steps
        preds.append(float(p)); hist.append(float(p))
    residuals=[]
    for i in range(3,len(s)):
        p=_hgb_one_step(s.iloc[:i])
        if p is not None: residuals.append(float(s.iloc[i]-p))
    rs=float(np.std(residuals,ddof=1)) if len(residuals)>1 else 0.0
    arr=np.asarray(preds,dtype=float)
    return arr.tolist(),(arr-1.96*rs).tolist(),(arr+1.96*rs).tolist()

def _forecast_backtest(monthly, model_name):
    s=pd.Series(monthly).dropna().astype(float)
    actuals=[]; preds=[]
    start=4 if model_name=='HistGradientBoosting' else 3
    for i in range(start,len(s)):
        hist=s.iloc[:i]
        try:
            if model_name=='HistGradientBoosting':
                p=_hgb_one_step(hist)
            else:
                p=damped_trend_forecast(hist,1)[0][0]
            if p is not None and np.isfinite(p):
                actuals.append(float(s.iloc[i])); preds.append(float(p))
        except Exception:
            continue
    if not actuals:
        return {'r2':None,'mae':None,'rmse':None,'observations':0}
    r2=float(r2_score(actuals,preds)) if len(actuals)>=2 and len(np.unique(actuals))>=2 else None
    return {'r2':fmt_num(r2,4),'mae':fmt_num(mean_absolute_error(actuals,preds),4),'rmse':fmt_num(np.sqrt(mean_squared_error(actuals,preds)),4),'observations':len(actuals)}

def build_forecast_json(dates,values,benchmark,higher_is_better=True):
    tmp=pd.DataFrame({'date':pd.to_datetime(dates,errors='coerce'),'value':pd.to_numeric(values,errors='coerce')}).dropna()
    if tmp.empty: return {'modelName':'Unavailable','modelSelection':'Unavailable','candidateModels':{},'nextMonth':None,'nextQuarter':None,'nextYear':None}
    monthly=tmp.groupby(tmp['date'].dt.to_period('M'))['value'].mean().sort_index()
    if monthly.empty: return {'modelName':'Unavailable','modelSelection':'Unavailable','candidateModels':{},'nextMonth':None,'nextQuarter':None,'nextYear':None}
    candidates={
        'HistGradientBoosting':_forecast_backtest(monthly,'HistGradientBoosting'),
        'DampedTrend':_forecast_backtest(monthly,'DampedTrend')
    }
    eligible=[(n,m) for n,m in candidates.items() if m.get('rmse') is not None]
    if eligible:
        best_name,best_metrics=sorted(eligible,key=lambda z:(z[1]['rmse'],z[1]['mae'] if z[1]['mae'] is not None else float('inf'),-(z[1]['r2'] if z[1]['r2'] is not None else -1e9)))[0]
    else:
        best_name='DampedTrend' if len(monthly)>=2 else 'HistGradientBoosting'
        best_metrics=candidates.get(best_name,{})
    if best_name=='HistGradientBoosting':
        preds,lower,upper=hgb_forecast(monthly,12)
        if not np.isfinite(preds).all():
            best_name='DampedTrend'; preds,lower,upper=damped_trend_forecast(monthly,12)
    else:
        preds,lower,upper=damped_trend_forecast(monthly,12)
    last=monthly.index[-1]
    future=pd.period_range(start=last+1,periods=12,freq='M')
    def obj(i,label):
        v=float(preds[i]); lo=float(lower[i]); hi=float(upper[i])
        return {'period':label,'predictedValue':fmt_num(v),'lowerBound':fmt_num(lo),'upperBound':fmt_num(hi),'predictedHealthState':prediction_health(v,benchmark,higher_is_better)}
    qv=float(np.mean(preds[:3])); ql=float(np.mean(lower[:3])); qu=float(np.mean(upper[:3]))
    yv=float(np.mean(preds[:12])); yl=float(np.mean(lower[:12])); yu=float(np.mean(upper[:12]))
    return {
        'modelName':best_name,
        'modelSelection':best_name,
        'candidateModels':candidates,
        'nextMonth':obj(0,str(future[0])),
        'nextQuarter':{'period':f'{future[0].year}-Q{future[0].quarter}','predictedValue':fmt_num(qv),'lowerBound':fmt_num(ql),'upperBound':fmt_num(qu),'predictedHealthState':prediction_health(qv,benchmark,higher_is_better)},
        'nextYear':{'period':str(future[-1].year),'predictedValue':fmt_num(yv),'lowerBound':fmt_num(yl),'upperBound':fmt_num(yu),'predictedHealthState':prediction_health(yv,benchmark,higher_is_better)}
    }


# ================================================================
# EXACT JSON SCHEMA FROM THE TWO UPLOADED REFERENCE FILES
# ================================================================
STANDARD_JSON_TOP_LEVEL_KEYS = [
    'generatedAt','module','reportVersion','metricName','unit','higherIsBetter',
    'companyValue','industryStandardValue','healthState','variance',
    'trendAnalysis','forecast','rca','dataQuality','selectedTrainingModel',
    'missingConfigurations'
]
STANDARD_JSON_NESTED_KEYS = {
    'variance':['value','percentage'],
    'forecast':['nextMonth','nextQuarter','nextYear'],
    'forecast.nextMonth':['period','predictedValue','lowerBound','upperBound','predictedHealthState'],
    'forecast.nextQuarter':['period','predictedValue','lowerBound','upperBound','predictedHealthState'],
    'forecast.nextYear':['period','predictedValue','lowerBound','upperBound','predictedHealthState'],
    'rca':['applicable','breachValue','factors'],
    'rca.factors':['rank','factorName','avgFactorValue','impactValue','impactPct'],
    'dataQuality':['overallRating','dataPeriod','recordsAnalysed','checks'],
    'dataQuality.dataPeriod':['from','to'],
    'dataQuality.checks':['checkName','category','failedRecords','failedPct','affectedColumns','affectedCells','staleRange'],
    'selectedTrainingModel':['rcaModel','forecastModel'],
    'selectedTrainingModel.rcaModel':['modelName','r2','mae','rmse','rating'],
    'selectedTrainingModel.forecastModel':['modelName','r2','mae','rmse','rating'],
    'missingConfigurations':['mandatoryFieldsMissing','otherFieldsMissing']
}
FIELDMISSING_JSON_NESTED_KEYS = {
    'variance':['value','percentage'],
    'forecast':['applicable','status','message'],
    'rca':['applicable','status','message','breachValue','factors'],
    'dataQuality':['overallRating','dataPeriod','recordsAnalysed','checks'],
    'dataQuality.dataPeriod':['from','to'],
    'dataQuality.checks':['checkName','category','failedRecords','failedPct','affectedColumns','affectedCells','staleRange'],
    'selectedTrainingModel':['rcaModel','forecastModel'],
    'selectedTrainingModel.rcaModel':['status','trainingPerformed'],
    'selectedTrainingModel.forecastModel':['status','trainingPerformed'],
    'missingConfigurations':['mandatoryFieldsMissing','otherFieldsMissing']
}

def _clean_trend_period(period, level):
    """Keep only the yearly/quarterly/monthly period keys in the supplied JSON schema."""
    if not isinstance(period, dict):
        return period
    allowed_by_level = {
        'year': ['period', 'year', 'average', 'isPartial', 'children'],
        'quarter': ['period', 'quarter', 'average', 'isPartial', 'children'],
        'month': ['period', 'month', 'average', 'isPartial'],
    }
    out = {}
    for key in allowed_by_level[level]:
        if key not in period:
            continue
        value = period[key]
        if key == 'children' and level in ('year', 'quarter') and isinstance(value, dict):
            next_level = 'quarter' if level == 'year' else 'month'
            children = {}
            if 'granularity' in value:
                children['granularity'] = value['granularity']
            if 'periods' in value:
                items = value['periods']
                children['periods'] = [_clean_trend_period(item, next_level) for item in items] if isinstance(items, list) else items
            value = children
        out[key] = value
    return out


def _clean_trend_analysis_schema(value):
    """Whitelist the exact trendAnalysis fields shown in the supplied JSON."""
    if not isinstance(value, dict):
        return value
    out = {}
    for key in ['direction', 'granularity', 'periods']:
        if key not in value:
            continue
        item = value[key]
        if key == 'periods' and isinstance(item, list):
            item = [_clean_trend_period(period, 'year') for period in item]
        out[key] = item
    return out


def _clean_json_to_supplied_schema(report, field_missing=False):
    nested = FIELDMISSING_JSON_NESTED_KEYS if field_missing else STANDARD_JSON_NESTED_KEYS

    def clean(obj, path=''):
        if not isinstance(obj, dict):
            return obj
        allowed = STANDARD_JSON_TOP_LEVEL_KEYS if path == '' else nested.get(path)
        if allowed is None:
            return obj
        out = {}
        for key in allowed:
            if key not in obj:
                continue
            value = obj[key]
            child = f'{path}.{key}' if path else key
            if child == 'trendAnalysis':
                value = _clean_trend_analysis_schema(value)
            elif isinstance(value, dict):
                value = clean(value, child)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                value = [clean(v, child) for v in value]
            out[key] = value
        return out

    return clean(report)

def _strict_json_order(report, field_missing=False):
    report=json_safe(_clean_json_to_supplied_schema(report,field_missing))
    if list(report.keys()) != STANDARD_JSON_TOP_LEVEL_KEYS:
        raise ValueError(f'JSON top-level schema mismatch: {list(report.keys())}')
    nested=FIELDMISSING_JSON_NESTED_KEYS if field_missing else STANDARD_JSON_NESTED_KEYS
    for path,expected in nested.items():
        obj=report; valid=True
        for part in path.split('.'):
            if not isinstance(obj,dict) or part not in obj: valid=False; break
            obj=obj[part]
        if valid and isinstance(obj,dict) and list(obj.keys()) != expected:
            raise ValueError(f'JSON schema mismatch at {path}: {list(obj.keys())}')
    trend = report.get('trendAnalysis')
    if isinstance(trend, dict):
        if list(trend.keys()) != ['direction', 'granularity', 'periods']:
            raise ValueError(f'trendAnalysis schema mismatch: {list(trend.keys())}')
        def _check_period_schema(period, level):
            if not isinstance(period, dict):
                return
            expected_by_level = {
                'year': ['period', 'year', 'average', 'isPartial', 'children'],
                'quarter': ['period', 'quarter', 'average', 'isPartial', 'children'],
                'month': ['period', 'month', 'average', 'isPartial'],
            }
            if any(key not in expected_by_level[level] for key in period):
                raise ValueError(f'trendAnalysis {level} period contains unsupported keys: {list(period.keys())}')
            children = period.get('children')
            next_level = 'quarter' if level == 'year' else 'month'
            if isinstance(children, dict):
                if any(key not in ['granularity', 'periods'] for key in children):
                    raise ValueError(f'trendAnalysis children contains unsupported keys: {list(children.keys())}')
                for child_period in children.get('periods', []) if isinstance(children.get('periods'), list) else []:
                    _check_period_schema(child_period, next_level)
        for year_period in trend.get('periods', []) if isinstance(trend.get('periods'), list) else []:
            _check_period_schema(year_period, 'year')
    for factor in ((report.get('rca') or {}).get('factors') or []):
        if list(factor.keys()) != ['rank','factorName','avgFactorValue','impactValue','impactPct']:
            raise ValueError(f'RCA factor schema mismatch: {list(factor.keys())}')
    return report

def _metric_json_filename(metric_name,module_code='ONB2'):
    return f"{module_code}_{_metric_pascal_case(metric_name)}.json"


def _remove_legacy_local_json_outputs():
    """Delete only known report JSON outputs created by earlier script versions."""
    known_metrics = [
        "Onboarding Cycle Time",
        "Pre-Day-1 Task Completion Rate",
        "Day 30/60/90 Milestone Completion Rate",
        "Compliance Documentation Completion Rate",
    ]
    stale_paths = ["analysis_summary.json"] + [_metric_json_filename(metric, "ONB2") for metric in known_metrics]
    for stale_path in stale_paths:
        try:
            if os.path.isfile(stale_path):
                os.remove(stale_path)
                print(f"Removed legacy local JSON output: {stale_path}")
        except OSError as exc:
            print(f"Could not remove old generated JSON {stale_path}: {exc}")


_remove_legacy_local_json_outputs()

def _write_metric_json(report,module_code='ONB2'):
    """Validate in memory and push directly to Supabase; never create a local JSON file."""
    field_missing=report.get('rca',{}).get('status')=='FieldMissing'
    report=dict(report); report['module']=module_code; report['reportVersion']='2.2'; report['metricName']=_metric_pascal_case(report.get('metricName','Metric'))
    report=_strict_json_order(report,field_missing)
    db_record=push_metric_json_to_supabase(report)
    print(f"JSON pushed directly to Supabase: {report['metricName']} | execution_id={db_record.get('execution_id')}")
    return {'metric_name':report['metricName'],'execution_id':db_record['execution_id'],'created_at':db_record['created_at']}

json_reports=[]; supabase_inserted_records=[]

# ---------- Metric specifications ----------

metrics=[

    ('Pre-Day-1 Task Completion Rate','__target_pre',fields['join_date'],pre_actual),

    ('Day 30/60/90 Milestone Completion Rate','__target_milestone',fields['join_date'],milestone_actual),

    ('Compliance Documentation Completion Rate','__target_compliance',fields['comp_due'],comp_actual)

]



results=[]

model_objects={}



for metric,target,date_col,actual in metrics:

    print('\n'+'='*80)

    print(metric.upper())

    print('='*80)

    mandatory_missing, normal_missing = get_missing_configuration(metric)
    if mandatory_missing:
        report={
            'generatedAt':datetime.now(timezone.utc).isoformat(),
            'module':'ONB2',
            'reportVersion':'2.2',
            'metricName':metric,
            'unit':'percent',
            'higherIsBetter':True,
            'companyValue':fmt_num(actual),
            'industryStandardValue':None,
            'healthState':'Data Missing',
            'variance':{'value':None,'percentage':None},
            'trendAnalysis':None,
            'forecast':{'applicable':False,'status':'Data Missing','message':'Forecast was not performed because essential metric data is incomplete.'},
            'rca':{'applicable':False,'status':'FieldMissing','message':'RCA was not performed because one or more mandatory fields are missing.','breachValue':None,'factors':[]},
            'dataQuality':{'overallRating':'poor','dataPeriod':{'from':None,'to':None},'recordsAnalysed':0,'checks':[]},
            'selectedTrainingModel':{'rcaModel':{'status':'Data Missing','trainingPerformed':False},'forecastModel':{'status':'Data Missing','trainingPerformed':False}},
            'missingConfigurations':{'mandatoryFieldsMissing':mandatory_missing,'otherFieldsMissing':normal_missing}
        }
        json_reports.append(json_safe(report)); u=_write_metric_json(report); supabase_inserted_records.append(u)
        print('Mandatory fields missing:',[x.get('fieldName') if isinstance(x,dict) else x for x in mandatory_missing]); continue

    # Standard JSON path: normal missing fields do NOT block analysis.
    valid=pd.to_numeric(df[target],errors='coerce').notna()
    mdf=df.loc[valid].copy().reset_index(drop=True)
    y=pd.to_numeric(mdf[target],errors='coerce').astype(float).reset_index(drop=True)

    bench=benchmark_for(metric); industry_value=bench['mid'] if bench else None
    variance=(float(actual-industry_value) if actual is not None and pd.notna(actual) and industry_value is not None else None)
    variance_pct=(float(variance/industry_value*100) if variance is not None and industry_value else None)
    higher_is_better=True; health=health_state(actual,industry_value,higher_is_better)

    # Stale records: 3 calendar months from the latest available metric date.
    if date_col and date_col in df.columns:
        stale_mask,stale_cutoff,latest_metric_date=_stale_record_info(df[date_col])
        stale_records=int(stale_mask.sum())
    else:
        stale_mask=pd.Series(False,index=df.index); stale_cutoff=None; latest_metric_date=None; stale_records=0

    # Existing dynamic features/model logic remains intact.
    existing_selected='Not available'; existing_train_r2=None; existing_test_r2=None
    existing_cv_r2=None; existing_cv_std=None; existing_train_cv_gap=None; existing_test_cv_gap=None; existing_overfit=None
    X=None; selected_train_object=None; feature_names=[]; score_df=pd.DataFrame()
    if len(y)>=12 and y.nunique()>=2:
        X=dynamic_features(mdf,target).reset_index(drop=True)
        if X.shape[1]>0:
            score_df,fitted,feature_names,ytr,yte=train_three(X,y)
            eligible=score_df[
                np.isfinite(score_df['Testing R2']) & (score_df['Testing R2']<0.9999) &
                (~score_df['Overfitting Detected'].fillna(False))
            ].copy()
            if not eligible.empty:
                selected_row=eligible.sort_values(['Testing R2','Testing MAE'],ascending=[False,True]).iloc[0]
                existing_selected=str(selected_row['Algorithm']); existing_train_r2=selected_row['Training R2']; existing_test_r2=selected_row['Testing R2']
                existing_cv_r2=selected_row['Mean CV R2']; existing_cv_std=selected_row['CV R2 Std']; existing_train_cv_gap=selected_row['Train-CV Gap']; existing_test_cv_gap=selected_row['Test-CV Gap']; existing_overfit=bool(selected_row['Overfitting Detected']); selected_train_object=fitted.get(existing_selected)
            else:
                print('No model passed both TEST R2 < 0.9999 and the requested overfitting rule.')

    # RCA uses the selected model from XGBoost, Logistic Regression, Random Forest only.
    rca_metrics={'r2':None,'mae':None,'rmse':None,'rating':'Unavailable'}
    factors=[]
    if selected_train_object is not None:
        selected_model_obj=selected_train_object.get('model')
        selected_X=selected_train_object.get('X_train')
        factors=calculate_shap_rca(selected_model_obj, selected_X, feature_names, top_n=3)
        rca_metrics=evaluate_selected_model(selected_model_obj, selected_X, ytr)

    breach_value=abs(float(variance)) if variance is not None else None

    if date_col and date_col in mdf.columns:
        trend_dates=pd.to_datetime(mdf[date_col],errors='coerce')
    else:
        trend_dates=pd.Series(pd.date_range(end=pd.Timestamp.today(),periods=len(y),freq='D'))

    # Trend and forecast remain unchanged: forecasting is the only place where
    # HistGradientBoosting and DampedTrend are used.
    trend_json=build_trend_analysis(trend_dates,y,higher_is_better)
    forecast_json=build_forecast_json(trend_dates,y,industry_value,higher_is_better)

    # Data quality: report missing values and stale records without blocking analysis.
    records_analysed=int(len(mdf)); checks=[]
    missing_counts=mdf.isna().sum() if records_analysed else pd.Series(dtype=int)
    failed_records=int(mdf.isna().any(axis=1).sum()) if records_analysed else 0
    affected_columns=[str(c) for c in missing_counts[missing_counts>0].index.tolist()]
    checks.append({'checkName':'MissingValues','category':'Completeness','failedRecords':int(failed_records),'failedPct':fmt_num(failed_records/max(len(mdf),1)*100),'affectedColumns':affected_columns or None,'affectedCells':int(missing_counts.sum()) if len(missing_counts) else 0,'staleRange':None})
    duplicate_records=int(mdf.duplicated().sum())
    checks.append({'checkName':'DuplicateRecords','category':'Uniqueness','failedRecords':duplicate_records,'failedPct':fmt_num(duplicate_records/max(records_analysed,1)*100),'affectedColumns':None,'affectedCells':None,'staleRange':None})
    stale_affected=[str(date_col)] if date_col else None
    checks.append({'checkName':'Staleness','category':'Staleness','failedRecords':stale_records,'failedPct':fmt_num(stale_records/max(len(df),1)*100),'affectedColumns':stale_affected,'affectedCells':None,'staleRange':{'thresholdMonths':STALE_MONTHS,'cutoff':stale_cutoff.date().isoformat() if stale_cutoff is not None else None,'latestDate':latest_metric_date.date().isoformat() if latest_metric_date is not None else None} if date_col else None})
    avg_failed=np.mean([c['failedPct'] or 0 for c in checks]) if checks else 100
    data_quality_rating='good' if avg_failed<=2 else 'fair' if avg_failed<=10 else 'poor'
    valid_dates=pd.to_datetime(trend_dates,errors='coerce').dropna()
    data_from=valid_dates.min().date().isoformat() if len(valid_dates) else None; data_to=valid_dates.max().date().isoformat() if len(valid_dates) else None

    forecast_metrics=(forecast_json.get('candidateModels',{}).get(forecast_json.get('modelName'),{}) or {})
    report={
        'generatedAt':datetime.now(timezone.utc).isoformat(),
        'module':'ONB2',
        'reportVersion':'2.2',
        'metricName':metric,
        'unit':'percent',
        'higherIsBetter':higher_is_better,
        'companyValue':fmt_num(actual),
        'industryStandardValue':fmt_num(industry_value),
        'healthState':health,
        'variance':{'value':fmt_num(variance),'percentage':fmt_num(variance_pct)},
        'trendAnalysis':trend_json,
        'forecast':{
            'nextMonth':forecast_json.get('nextMonth'),
            'nextQuarter':forecast_json.get('nextQuarter'),
            'nextYear':forecast_json.get('nextYear')
        },
        'rca':{'applicable':bool(len(factors)>0),'breachValue':fmt_num(breach_value),'factors':factors},
        'dataQuality':{'overallRating':data_quality_rating,'dataPeriod':{'from':data_from,'to':data_to},'recordsAnalysed':records_analysed,'checks':checks},
        'selectedTrainingModel':{
            'rcaModel':{'modelName':existing_selected,'r2':rca_metrics['r2'],'mae':rca_metrics['mae'],'rmse':rca_metrics['rmse'],'rating':rca_metrics['rating']},
            'forecastModel':{'modelName':forecast_json.get('modelName'),'r2':forecast_metrics.get('r2'),'mae':forecast_metrics.get('mae'),'rmse':forecast_metrics.get('rmse'),'rating':model_rating(forecast_metrics.get('r2')) if forecast_metrics.get('r2') is not None else 'fair'}
        },
        'missingConfigurations':{'mandatoryFieldsMissing':mandatory_missing,'otherFieldsMissing':normal_missing}
    }
    json_reports.append(json_safe(report)); u=_write_metric_json(report); supabase_inserted_records.append(u)

print('\n'+'='*90); print('INDIVIDUAL METRIC JSON REPORTS PUSHED TO SUPABASE'); print('='*90)
print('No metric JSON files were saved locally.')
print('\nSupabase rows created during this run:')
for r in supabase_inserted_records: print(f" - {r['metric_name']} -> execution_id={r['execution_id']}, created_at={r['created_at']}")


# ================================================================
# ONBOARDING CYCLE TIME - STRICT JSON OUTPUT
# ================================================================
# The dedicated cycle-time analysis above contains the actual target
# construction, data-quality checks, trend logic, forecasting and RCA.
# It is executed once here, after all required functions are defined.
# Its legacy JSON is then normalized to the exact Standard/FieldMissing
# schema supplied for this project.
# ================================================================

def _strict_cycle_time_json_from_legacy(legacy):
    """Return the dedicated cycle-time result in exactly the uploaded Standard/FieldMissing schema."""
    field_missing = (
        legacy.get("rca", {}).get("status") in {"FieldMissing", "Data Missing"}
        or bool((legacy.get("missingConfigurations") or {}).get("mandatoryFieldsMissing"))
    )
    if field_missing:
        report = {
            "generatedAt": legacy.get("generatedAt", datetime.now(timezone.utc).isoformat()),
            "module": "ONB2", "reportVersion": "2.2", "metricName": "Onboarding Cycle Time",
            "unit": "days", "higherIsBetter": False,
            "companyValue": legacy.get("companyValue"), "industryStandardValue": legacy.get("industryStandardValue"),
            "healthState": legacy.get("healthState", "Data Missing"),
            "variance": legacy.get("variance", {"value": None, "percentage": None}),
            "trendAnalysis": None,
            "forecast": {"applicable": False, "status": "Data Missing", "message": "Forecast was not performed because essential metric data is incomplete."},
            "rca": {"applicable": False, "status": "FieldMissing", "message": "RCA was not performed because one or more mandatory fields are missing.", "breachValue": None, "factors": []},
            "dataQuality": {"overallRating": "poor", "dataPeriod": {"from": None, "to": None}, "recordsAnalysed": 0, "checks": []},
            "selectedTrainingModel": {"rcaModel": {"status": "Data Missing", "trainingPerformed": False}, "forecastModel": {"status": "Data Missing", "trainingPerformed": False}},
            "missingConfigurations": {"mandatoryFieldsMissing": legacy.get("missingConfigurations", {}).get("mandatoryFieldsMissing", []), "otherFieldsMissing": legacy.get("missingConfigurations", {}).get("otherFieldsMissing", [])}
        }
    else:
        report = {
            "generatedAt": legacy.get("generatedAt", datetime.now(timezone.utc).isoformat()),
            "module": "ONB2", "reportVersion": "2.2", "metricName": "Onboarding Cycle Time",
            "unit": "days", "higherIsBetter": False,
            "companyValue": legacy.get("companyValue"), "industryStandardValue": legacy.get("industryStandardValue"),
            "healthState": legacy.get("healthState"), "variance": legacy.get("variance", {"value": None, "percentage": None}),
            "trendAnalysis": legacy.get("trendAnalysis"), "forecast": legacy.get("forecast"), "rca": legacy.get("rca", {"applicable": False, "breachValue": None, "factors": []}),
            "dataQuality": legacy.get("dataQuality", {"overallRating": "poor", "dataPeriod": {"from": None, "to": None}, "recordsAnalysed": 0, "checks": []}),
            "selectedTrainingModel": legacy.get("selectedTrainingModel", {"rcaModel": {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}, "forecastModel": {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}}),
            "missingConfigurations": {"mandatoryFieldsMissing": legacy.get("missingConfigurations", {}).get("mandatoryFieldsMissing", []), "otherFieldsMissing": legacy.get("missingConfigurations", {}).get("otherFieldsMissing", [])}
        }
    return _strict_json_order(report, field_missing=field_missing)


def _write_strict_cycle_time_json():
    """Generate, validate, and push the strict cycle-time JSON without local file I/O."""
    global _ONBOARDING_CYCLE_TIME_LEGACY_REPORT
    print("\n" + "=" * 90)
    print("GENERATING JSON REPORT: ONBOARDING CYCLE TIME")
    print("=" * 90)

    _ONBOARDING_CYCLE_TIME_LEGACY_REPORT = None
    try:
        run_onboarding_cycle_time_analysis()
        legacy_report = _ONBOARDING_CYCLE_TIME_LEGACY_REPORT
        if not isinstance(legacy_report, dict):
            raise RuntimeError("Cycle-time analysis did not return an in-memory report.")
        strict_report = _strict_cycle_time_json_from_legacy(legacy_report)
    except Exception as exc:
        hire_col = find_column(company_df, ["joiningDate", "hireDate", "startDate", "employmentStartDate", "newHireStartDate", "dateOfJoining"])
        completion_col = find_column(company_df, ["onboardingCompletionDate", "onboardingCompletedDate", "completionDate", "onboardingEndDate", "processCompletionDate"])
        if hire_col is None or completion_col is None:
            mandatory = []
            if hire_col is None:
                mandatory.append({"field": "Hire/start date", "status": "MISSING"})
            if completion_col is None:
                mandatory.append({"field": "Onboarding completion date", "status": "MISSING"})
            legacy = {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "rca": {"applicable": False, "status": "FieldMissing", "message": "RCA was not performed because mandatory fields are missing.", "breachValue": None, "factors": []},
                "missingConfigurations": {"mandatoryFieldsMissing": mandatory, "otherFieldsMissing": []},
                "companyValue": None,
                "industryStandardValue": None,
                "healthState": "Data Missing",
                "variance": {"value": None, "percentage": None}
            }
            strict_report = _strict_cycle_time_json_from_legacy(legacy)
        else:
            raise RuntimeError(f"Onboarding Cycle Time report generation failed: {exc}") from exc

    strict_report = json_safe(strict_report)
    strict_report["module"] = SUPABASE_MODULE_NAME
    strict_report["metricName"] = "OnboardingCycleTime"
    is_field_missing = (
        strict_report.get("rca", {}).get("status") == "FieldMissing"
        or bool((strict_report.get("missingConfigurations") or {}).get("mandatoryFieldsMissing"))
    )
    strict_report = _strict_json_order(strict_report, field_missing=is_field_missing)

    print("Prepared strict JSON in memory; no local JSON file will be created.")
    print("Metric:", strict_report["metricName"])
    print("Trend analysis:", "null" if strict_report.get("trendAnalysis") is None else "present")
    db_record = push_metric_json_to_supabase(strict_report)
    print("Supabase execution_id:", db_record.get("execution_id"))
    print("Supabase created_at:", db_record.get("created_at"))
    print("JSON pushed directly to Supabase and not saved locally.")
    return strict_report


# Execute the missing dedicated metric.
_onboarding_cycle_time_strict_report = _write_strict_cycle_time_json()

print('\nCompleted successfully.')

