# -*- coding: utf-8 -*-
"""SuccessFactors Recruitment (RCM) health monitoring.

Uses a local .env file for Supabase configuration, reads company and industry
workbooks from Supabase Storage into memory, and pushes strict per-metric JSON
reports directly to ML_Notebook_Insights. No workbook or report is saved locally.
"""

# ================================================================
# SF HEALTH MONITORING - RCM RECRUITMENT ML
# Uses adjacent .env; reads both workbooks from Supabase Storage in memory.
#
# Design notes:
# - Generic column discovery + editable CONFIG aliases (not customer-specific engine logic).
# - Five RCM metrics, hierarchical trends, benchmark variance, 3-model SHAP RCA,
#   and two-candidate forecasting (HistGradientBoosting and DampedTrend).
# - Leakage filter is explicit and runs before feature selection.
# - Numeric KPI training compares Ridge, Random Forest and XGBoost regression models.
#   RCA independently compares those same three model families and aggregates SHAP
#   attributions; forecasting compares HistGradientBoosting with DampedTrend.
# - Tiny samples will be reported honestly; the script will not manufacture valid R².
# ================================================================

import sys, warnings, re, os, math, json, textwrap, hashlib
from io import BytesIO
from datetime import datetime, timezone
warnings.filterwarnings("ignore")

RCM_BUILD_ID = "2026-10-13-reference-json-contract-v10-dq-mandatory-failure-gate"
print(f"\nRCM BUILD: {RCM_BUILD_ID}")
print(f"RCM SCRIPT PATH: {os.path.abspath(__file__) if '__file__' in globals() else os.path.abspath(os.getcwd())}")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split, KFold, cross_val_score, StratifiedKFold, cross_validate, cross_val_predict
from sklearn.base import clone
from sklearn.metrics import (r2_score, mean_absolute_error, mean_squared_error,
                             accuracy_score, precision_score, recall_score, f1_score,
                             roc_auc_score, balanced_accuracy_score)
from sklearn.inspection import permutation_importance
from xgboost import XGBRegressor, XGBClassifier
try:
    from supabase import create_client
except ImportError as exc:
    raise RuntimeError("Install dependencies first: python -m pip install supabase pandas openpyxl numpy scikit-learn xgboost scipy matplotlib shap") from exc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
ENV_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), ".env")

def load_env_file(env_path):
    """Load KEY=VALUE pairs from the adjacent .env without overriding OS variables."""
    if not os.path.isfile(env_path):
        raise FileNotFoundError(
            f"The .env file was not found at: {env_path}. Copy .env.example to .env and configure it."
        )
    with open(env_path, "r", encoding="utf-8-sig") as env_file:
        for line_number, raw_line in enumerate(env_file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                raise ValueError(f"Invalid .env format on line {line_number}: expected KEY=VALUE.")
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            elif " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            if key and key not in os.environ:
                os.environ[key] = value

load_env_file(ENV_PATH)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "SF_Health_Raw_Data").strip()
COMPANY_FILE_PATH = os.getenv("RCM_FILE_PATH", "SF_Dataset_USA1.xlsx").strip()
INDUSTRY_FILE_PATH = os.getenv("INDUSTRY_STANDARDS_FILE_PATH", "SF Health Monitoring Industry Standards.xlsx").strip()
SUPABASE_WRITE_ENABLED = os.getenv("SUPABASE_WRITE_ENABLED", "true").strip().lower() == "true"
REPORT_VERSION = os.getenv("REPORT_VERSION", "2.2").strip()
ANALYSIS_START = pd.Timestamp(os.getenv("ANALYSIS_START", "2024-10-01")).normalize()

if not SUPABASE_URL:
    raise RuntimeError(f"SUPABASE_URL is missing from {ENV_PATH}")
if not SUPABASE_SECRET_KEY:
    raise RuntimeError(f"SUPABASE_SECRET_KEY is missing from {ENV_PATH}")
if not SUPABASE_SECRET_KEY.startswith("sb_secret_"):
    raise RuntimeError("SUPABASE_SECRET_KEY must be a backend sb_secret_... key. Do not use a publishable key.")
supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)


def read_storage_excel(bucket_name, object_path, label):
    """Download a workbook from Storage into memory only."""
    print(f"Reading {label} from Supabase Storage: {object_path}")
    try:
        workbook_bytes = supabase.storage.from_(bucket_name).download(object_path)
        if not workbook_bytes:
            raise ValueError("Supabase returned an empty workbook.")
        workbook = pd.ExcelFile(BytesIO(workbook_bytes))
        print(f"Loaded {label} into memory ({len(workbook_bytes):,} bytes).")
        return workbook
    except Exception as exc:
        raise RuntimeError(
            f"Could not read '{object_path}' from Supabase bucket '{bucket_name}'. "
            f"Check .env paths and Storage permissions. Details: {exc}"
        ) from exc

print("Input mode: Supabase Storage in-memory; no local workbook copies.")
company_xl = read_storage_excel(SUPABASE_BUCKET, COMPANY_FILE_PATH, "company workbook")
industry_xl = read_storage_excel(SUPABASE_BUCKET, INDUSTRY_FILE_PATH, "industry benchmark workbook")

# --------------------------- CONFIG --------------------------------
CONFIG = {
    # Edit these aliases only if a future customer export uses unusual field names.
    "aliases": {
        "application_date": ["applicationDate", "application_date", "appliedDate", "dateApplied"],
        "requisition_created_date": ["requisitionCreatedDate", "requisition_created_date", "createdDate"],
        "interview_date": ["interviewDate", "interview_date", "dateInterviewed"],
        "offer_release_date": ["offerReleaseDate", "offerDate", "offer_release_date", "offerExtendedDate"],
        "offer_accepted_date": ["offerAcceptedDate", "offer_accepted_date", "acceptedDate"],
        "filled_date": ["requisitionFilledDate", "positionFilledDate", "requisition_filled_date", "filledDate"],
        "requisition_closed_date": ["requisitionClosedDate", "requisition_closed_date", "closedDate"],
        "joining_date": ["joiningDate", "joining_date", "startDate"],
        "application_status": ["applicationStatus", "application_status", "status", "candidateStatus"],
        "source": ["source", "sourceOfHire", "sourcingChannel", "candidateSource"],
        "requisition_status": ["requisitionStatus", "requisition_status", "status"],
        "open_flag": ["openFlag", "open_flag", "isOpen"],
        "total_applicants": ["totalApplicants", "total_applicants", "applicantCount"],
        "applicants_interviewed": ["applicantsInterviewed", "applicants_interviewed", "interviewedCount"],
        "offers_extended": ["offersExtended", "offers_extended", "offerCount"],
        "offers_accepted": ["offersAccepted", "offers_accepted", "acceptedOfferCount"],
        "requisition_age_days": ["requisitionAgeDays", "requisition_age_days", "ageDays"],
        "stored_tth": ["timeToHireDays", "time_to_hire_days", "timeToHire"],
        "filled_positions": ["noOfPositionsFilled", "positionsFilled", "filledCount"],
        "opened_positions": ["noOfPositionsOpened", "positionsOpened", "openPositions"],
    },
    "benchmarks_fallback": {
        "Time to Hire (TTH)": 20.0,                         # lower is better
        "Offer Acceptance Rate": 80.0,                     # higher is better
        "Applicant-to-Interview Conversion Rate": 15.0,    # healthy at or below 15%
        "Requisition Aging": 30.0,                         # lower is better
        "Source of Hire Effectiveness": 20.0,              # reference value
    },
    "metric_directions": {
        "Time to Hire (TTH)": "lower",
        "Offer Acceptance Rate": "higher",
        "Applicant-to-Interview Conversion Rate": "lower",
        "Requisition Aging": "lower",
        "Source of Hire Effectiveness": "band",
    },
    "stale_requisition_days": 90,
    "forecast_horizon_months": 1,
    "test_size": 0.25,
    "random_state": 42,
    "minimum_rows_for_train_test": 8,
    "minimum_rows_for_cv": 12,
    "overfit_gap_threshold": 0.20,
    "minimum_months_for_forecast": 6,
    "minimum_rows_for_shap": 30,
    "exclude_sensitive_features": False,  # set True if your governance rules require it
    "sensitive_columns": ["gender"],
}
# ---------------------- SUPABASE OUTPUT CONFIG -----------------------
SUPABASE_INSIGHTS_TABLE = "ML_Notebook_Insights"
SUPABASE_MODULE_NAME = "RCM"
print("Supabase output table:", SUPABASE_INSIGHTS_TABLE)
print("Supabase module:", SUPABASE_MODULE_NAME)
print("Supabase writes enabled:", SUPABASE_WRITE_ENABLED)
print(f"RCM JSON contract enforcement: {RCM_BUILD_ID}")
print("Company Storage object:", COMPANY_FILE_PATH)
print("Industry Storage object:", INDUSTRY_FILE_PATH)


def metric_pascal_case(metric_name):
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", str(metric_name or "Metric").strip())
    return "".join((part[0].upper() + part[1:]) if not part.isdigit() else part for part in parts) or "Metric"


def push_metric_json_to_supabase(report):
    """Replace only this RCM metric's previous row, then insert the latest JSON."""
    if not SUPABASE_WRITE_ENABLED:
        print(f"Supabase writes disabled; skipped {report.get('metricName', 'Metric')}.")
        return {"status": "skipped_write_disabled", "Metric_Name": report.get("metricName")}
    report = json_clean(report)
    report["module"] = SUPABASE_MODULE_NAME
    metric_name = metric_pascal_case(report.get("metricName", "Metric"))
    report["metricName"] = metric_name

    # Last line of defence at the database boundary: use JSON null explicitly and
    # round-trip the exact string that is about to be stored as JSONB.
    missing_config = report.get("missingConfigurations") or {}
    # Independently recover the missing calculation field names at the final upload
    # boundary. This prevents a stale/partially built report from uploading the
    # Standard schema when its mandatory completeness check already identifies gaps.
    if not isinstance(missing_config, dict):
        missing_config = {"mandatoryFieldsMissing": [], "otherFieldsMissing": []}
    inferred_missing = mandatory_field_names_from_report(report, report.get("metricName"))
    existing_missing = missing_config.get("mandatoryFieldsMissing") or []

    # CRITICAL FINAL GATE: a positive MandatoryFieldsMissing data-quality check is
    # authoritative evidence of missing mandatory data, even if an earlier schema
    # conversion accidentally put the field names in otherFieldsMissing or lost them.
    # Recover affectedColumns when present; otherwise use the metric's known mandatory
    # field names. This gate runs immediately before JSON serialization and upload.
    dq = report.get("dataQuality") if isinstance(report.get("dataQuality"), dict) else {}
    dq_checks = dq.get("checks", []) if isinstance(dq, dict) else []
    dq_mandatory_fields = []
    positive_mandatory_check = False
    mandatory_check_names = {
        "mandatoryfieldsmissing", "mandatoryvaluesmissing", "mandatoryfieldvaluesmissing",
        "mandatoryconfigurationmissing", "essentialfieldsmissing",
    }
    for check in dq_checks if isinstance(dq_checks, list) else []:
        if not isinstance(check, dict):
            continue
        check_name_norm = norm(check.get("checkName", ""))
        category_norm = norm(check.get("category", ""))
        try:
            failed_records = float(check.get("failedRecords") or 0)
        except (TypeError, ValueError):
            failed_records = 0.0
        try:
            failed_pct = float(check.get("failedPct") or 0)
        except (TypeError, ValueError):
            failed_pct = 0.0
        is_mandatory_check = check_name_norm in mandatory_check_names
        if is_mandatory_check and (failed_records > 0 or failed_pct > 0):
            positive_mandatory_check = True
            affected = check.get("affectedColumns")
            if isinstance(affected, (list, tuple, set)):
                dq_mandatory_fields.extend(str(x).strip() for x in affected if x is not None and str(x).strip())
            elif affected is not None and str(affected).strip():
                dq_mandatory_fields.append(str(affected).strip())

    if positive_mandatory_check and not dq_mandatory_fields and not existing_missing and not inferred_missing:
        dq_mandatory_fields.extend(mandatory_fields_when_schema_unavailable(report.get("metricName", "")))
    merged_missing = list(dict.fromkeys(
        [str(x).strip() for x in existing_missing if x is not None and str(x).strip()]
        + [str(x).strip() for x in inferred_missing if x is not None and str(x).strip()]
        + [str(x).strip() for x in dq_mandatory_fields if x is not None and str(x).strip()]
    ))
    merged_norms = {norm(x) for x in merged_missing}
    existing_other = missing_config.get("otherFieldsMissing", missing_config.get("normalFieldsMissing", [])) or []
    other_fields = list(dict.fromkeys(
        str(x).strip() for x in existing_other
        if x is not None and str(x).strip() and norm(x) not in merged_norms
    ))
    report["missingConfigurations"] = {
        "mandatoryFieldsMissing": merged_missing,
        "otherFieldsMissing": other_fields,
    }
    missing_fields = report["missingConfigurations"]["mandatoryFieldsMissing"]
    # Absolute last-resort invariant: if the public JSON says mandatory fields are
    # missing, trendAnalysis can never remain a Standard object at the DB boundary.
    if missing_fields:
        report["trendAnalysis"] = None
        report["higherIsBetter"] = None
        report["companyValue"] = None
        report["industryStandardValue"] = None
        report["healthState"] = None
        report["variance"] = {"value": None, "percentage": None}
        report["forecast"] = {"applicable": False, "status": "Data Missing", "message": "Forecast was not performed because essential metric data is incomplete."}
        report["rca"] = {"applicable": False, "status": "Data Missing", "message": "RCA was not performed because essential metric data is incomplete.", "breachValue": None, "factors": []}
        report["selectedTrainingModel"] = {
            "rcaModel": {"status": "Data Missing", "trainingPerformed": False},
            "forecastModel": {"status": "Data Missing", "trainingPerformed": False},
        }
    else:
        # Make sure otherFieldsMissing exists even for fallback reports.
        report["missingConfigurations"]["otherFieldsMissing"] = report["missingConfigurations"].get("otherFieldsMissing", [])
    if "trendAnalysis" not in report:
        raise ValueError(f"Refusing to push {metric_name}: required trendAnalysis key is absent")
    serialized_json = json.dumps(report, ensure_ascii=False, allow_nan=False)
    report = json.loads(serialized_json)
    # Final database-boundary guard: no report is uploaded unless it obeys the
    # exact top-level and nested key order from the supplied DOCX templates.
    if list(report.keys()) != STANDARD_JSON_TOP_LEVEL_KEYS:
        raise ValueError(f"Refusing to push {metric_name}: top-level JSON keys/order do not match the reference template")
    if list(report.get("variance", {}).keys()) != ["value", "percentage"]:
        raise ValueError(f"Refusing to push {metric_name}: variance schema does not match the reference template")
    if list(report.get("dataQuality", {}).keys()) != ["overallRating", "dataPeriod", "recordsAnalysed", "checks"]:
        raise ValueError(f"Refusing to push {metric_name}: dataQuality schema does not match the reference template")
    if list(report.get("dataQuality", {}).get("dataPeriod", {}).keys()) != ["from", "to"]:
        raise ValueError(f"Refusing to push {metric_name}: dataQuality.dataPeriod schema mismatch")
    if list(report.get("missingConfigurations", {}).keys()) != ["mandatoryFieldsMissing", "otherFieldsMissing"]:
        raise ValueError(f"Refusing to push {metric_name}: missingConfigurations schema/order does not match the reference template")
    for check in report.get("dataQuality", {}).get("checks", []):
        validate_reference_data_quality_check(check)
    if missing_fields:
        if '"trendAnalysis": null' not in serialized_json:
            raise ValueError(f"Refusing to push {metric_name}: FieldMissing JSON must contain exact \"trendAnalysis\": null")
        if list(report.get("forecast", {}).keys()) != ["applicable", "status", "message"]:
            raise ValueError(f"Refusing to push {metric_name}: FieldMissing forecast schema mismatch")
        if list(report.get("rca", {}).keys()) != ["applicable", "status", "message", "breachValue", "factors"]:
            raise ValueError(f"Refusing to push {metric_name}: FieldMissing RCA schema mismatch")
        expected_model_keys = ["status", "trainingPerformed"]
        if list(report.get("selectedTrainingModel", {}).get("rcaModel", {}).keys()) != expected_model_keys or list(report.get("selectedTrainingModel", {}).get("forecastModel", {}).keys()) != expected_model_keys:
            raise ValueError(f"Refusing to push {metric_name}: FieldMissing model schema mismatch")
        print(f"FieldMissing JSON enforced for {metric_name}: \"trendAnalysis\": null; missing fields={missing_fields}; positive mandatory DQ check={positive_mandatory_check}")
    else:
        if not isinstance(report.get("trendAnalysis"), dict):
            raise ValueError(f"Refusing to push {metric_name}: Standard JSON requires trendAnalysis object")
        if list(report.get("forecast", {}).keys()) != ["nextMonth", "nextQuarter", "nextYear"]:
            raise ValueError(f"Refusing to push {metric_name}: Standard forecast schema mismatch")
        if list(report.get("rca", {}).keys()) != ["applicable", "breachValue", "factors"]:
            raise ValueError(f"Refusing to push {metric_name}: Standard RCA schema mismatch")
        expected_model_keys = ["modelName", "r2", "mae", "rmse", "rating"]
        if list(report.get("selectedTrainingModel", {}).get("rcaModel", {}).keys()) != expected_model_keys or list(report.get("selectedTrainingModel", {}).get("forecastModel", {}).keys()) != expected_model_keys:
            raise ValueError(f"Refusing to push {metric_name}: Standard model schema mismatch")
        for forecast_node in report.get("forecast", {}).values():
            if list(forecast_node.keys()) != ["period", "predictedValue", "lowerBound", "upperBound", "predictedHealthState"]:
                raise ValueError(f"Refusing to push {metric_name}: Standard forecast node schema mismatch")
    # The printed object below is the exact validated JSON object placed in JSON_Result.
    # This is deliberately the only full JSON report printed by the script; internal
    # pre-normalization reports are not presented as final output.
    output_mode = "FieldMissing" if missing_fields else "Standard"
    print(f"\nFINAL JSON READY FOR SUPABASE | build={RCM_BUILD_ID} | metric={metric_name} | format={output_mode}")
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))

    payload = {"Module_Name": SUPABASE_MODULE_NAME, "Metric_Name": metric_name, "JSON_Result": report}

    def canonical_json_hash(value):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    expected_hash = canonical_json_hash(payload["JSON_Result"])
    print(f"UPLOAD CHECK | metric={metric_name} | build={RCM_BUILD_ID} | payload_sha256={expected_hash}")
    deleted = (supabase.table(SUPABASE_INSIGHTS_TABLE).delete()
               .eq("Module_Name", SUPABASE_MODULE_NAME)
               .eq("Metric_Name", metric_name).execute())
    # Supabase may return no deleted rows unless the delete explicitly requests them;
    # the inserted row and JSON read-back below are the authoritative verification.
    print(f"Delete request completed for {metric_name}; delete response rows={len(deleted.data or [])}")
    response = (supabase.table(SUPABASE_INSIGHTS_TABLE).insert(payload)
                .select("execution_id,created_at,Module_Name,Metric_Name,JSON_Result").execute())
    rows = response.data or []
    if not rows or rows[0].get("execution_id") is None:
        raise RuntimeError(f"Supabase did not confirm insertion for {metric_name}.")

    inserted_json = rows[0].get("JSON_Result")
    if not isinstance(inserted_json, dict):
        raise RuntimeError(
            f"Supabase inserted {metric_name}, but JSON_Result was not returned as an object. "
            "Cannot verify that the stored JSON matches the generated payload."
        )
    inserted_hash = canonical_json_hash(inserted_json)
    print(f"SUPABASE READ-BACK | metric={metric_name} | execution_id={rows[0].get('execution_id')} | stored_sha256={inserted_hash}")
    if inserted_hash != expected_hash:
        raise RuntimeError(
            f"Supabase JSON verification failed for {metric_name}: "
            f"payload_sha256={expected_hash}, stored_sha256={inserted_hash}."
        )
    print(f"SUPABASE JSON VERIFIED | metric={metric_name} | hash={expected_hash}")
    # Do not return the full JSON in the summary; the exact stored JSON was verified above.
    return {key: rows[0].get(key) for key in ["execution_id", "created_at", "Module_Name", "Metric_Name"]}

# ------------------------------------------------------------------

def read_sheets(xl):
    result = {}
    for sheet in xl.sheet_names:
        try:
            df = pd.read_excel(xl, sheet_name=sheet)
            df.columns = [str(c).strip() for c in df.columns]
            result[sheet] = df
        except Exception as e:
            print(f"Could not read sheet {sheet}: {e}")
    return result

company_sheets = read_sheets(company_xl)
industry_sheets = read_sheets(industry_xl)

def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())

def find_col(df, standard_name, extra_aliases=None):
    aliases = CONFIG["aliases"].get(standard_name, []) + (extra_aliases or [])
    norm_cols = {norm(c): c for c in df.columns}
    for alias in aliases:
        if norm(alias) in norm_cols:
            return norm_cols[norm(alias)]
    # relaxed exact token search only; avoids guessing across unrelated fields
    for alias in aliases:
        a = norm(alias)
        if len(a) >= 6:
            matches = [c for c in df.columns if a in norm(c) or norm(c) in a]
            if len(matches) == 1:
                return matches[0]
    return None

def find_sheet(sheets, preferred_terms):
    for term in preferred_terms:
        for name, df in sheets.items():
            if term in norm(name):
                return df.copy(), name
    return pd.DataFrame(), None

apps, apps_sheet_name = find_sheet(company_sheets, ["rcmmodule", "applications", "jobapplication", "candidateapplication"])
reqs, reqs_sheet_name = find_sheet(company_sheets, ["rcmrequsitions", "rcmrequisitions", "requisitions", "jobrequisition"])
if apps.empty:
    # Fallback: choose the sheet containing the most application-like columns.
    candidates = []
    for name, df in company_sheets.items():
        score = sum(find_col(df, x) is not None for x in ["application_date", "application_status", "source", "offer_accepted_date"])
        candidates.append((score, name, df))
    if candidates and max(candidates)[0] >= 2:
        _, apps_sheet_name, apps = max(candidates, key=lambda z:z[0])
if reqs.empty:
    candidates = []
    for name, df in company_sheets.items():
        score = sum(find_col(df, x) is not None for x in ["requisition_created_date", "requisition_status", "total_applicants", "requisition_age_days"])
        candidates.append((score, name, df))
    if candidates and max(candidates)[0] >= 2:
        _, reqs_sheet_name, reqs = max(candidates, key=lambda z:z[0])

print("\nCOMPANY SHEET SELECTION")
print(f"Applications-like sheet: {apps_sheet_name or 'NOT FOUND'} | shape={apps.shape}")
print(f"Requisitions-like sheet: {reqs_sheet_name or 'NOT FOUND'} | shape={reqs.shape}")
print("\nIndustry workbook sheets:", [(k, v.shape) for k,v in industry_sheets.items()])

if apps.empty and reqs.empty:
    # Do not abort the entire run just because neither business sheet is recognizable.
    # The report generator must still emit one FieldMissing JSON report per metric and
    # attempt to push each report to Supabase, with unavailable data represented as null.
    print("WARNING: Applications and Requisitions sheets were not identifiable. ")
    print("The run will continue; mandatory-field checks will choose the FieldMissing JSON schema where required.")

# Parse dates generically for fields whose names contain date, month, or time.
def parse_dates(df):
    df = df.copy()
    for c in df.columns:
        if any(t in norm(c) for t in ["date", "datetime", "month"]):
            try:
                parsed = pd.to_datetime(df[c], errors="coerce")
                if parsed.notna().sum() > 0:
                    df[c] = parsed
            except Exception:
                pass
    return df

apps = parse_dates(apps)
reqs = parse_dates(reqs)


def filter_from_analysis_start(frame, date_column, label):
    if frame.empty or not date_column or date_column not in frame.columns:
        print(f"{label}: no usable primary date column; date-window filter not applied.")
        return frame
    parsed = pd.to_datetime(frame[date_column], errors="coerce")
    keep = parsed.isna() | (parsed >= ANALYSIS_START)
    removed = int((~keep).sum())
    filtered = frame.loc[keep].copy()
    print(f"{label}: kept records dated on/after {ANALYSIS_START.date()} plus missing-date rows; removed older records: {removed}.")
    return filtered

apps_date_for_filter = find_col(apps, "application_date")
reqs_date_for_filter = find_col(reqs, "requisition_created_date")
apps = filter_from_analysis_start(apps, apps_date_for_filter, "Applications")
reqs = filter_from_analysis_start(reqs, reqs_date_for_filter, "Requisitions")

# Data-quality profile, visible before modeling.
print("\nDATA QUALITY PROFILE")
for label, df in [("Applications", apps), ("Requisitions", reqs)]:
    if df.empty:
        continue
    print(f"\n{label}: {len(df):,} rows x {len(df.columns)} columns")
    print("Columns:", list(df.columns))
    print("High missingness (>50%):", [c for c in df.columns if df[c].isna().mean() > .50])
    print("Constant columns:", [c for c in df.columns if df[c].nunique(dropna=True) <= 1])

# --------- Industry benchmark extraction (no benchmark file hardcoding) --------
def parse_benchmark_number(v):
    if pd.isna(v):
        return np.nan
    nums = re.findall(r"\d+(?:\.\d+)?", str(v).replace(",", ""))
    if not nums:
        return np.nan
    vals = [float(n) for n in nums]
    # For a range such as 20-30, use the conservative boundary from CONFIG later.
    return vals[0]

def load_benchmarks(industry_sheets):
    benchmarks = {}
    for _, df in industry_sheets.items():
        cols = {norm(c): c for c in df.columns}
        metric_col = next((cols[k] for k in cols if k in ["metricname", "metric", "kpiname"]), None)
        value_col = next((cols[k] for k in cols if k in ["industrybenchmark", "benchmark", "benchmarkvalue", "industrystandard"]), None)
        module_col = next((cols[k] for k in cols if k in ["module", "modulename"]), None)
        if not metric_col or not value_col:
            continue
        for _, row in df.iterrows():
            metric_name = str(row[metric_col]).strip()
            if pd.isna(row[metric_col]) or pd.isna(row[value_col]):
                continue
            if module_col and "rcm" not in norm(row[module_col]) and "recruit" not in norm(row[module_col]):
                continue
            val = parse_benchmark_number(row[value_col])
            if np.isfinite(val):
                benchmarks[norm(metric_name)] = val
    return benchmarks

industry_benchmarks_raw = load_benchmarks(industry_sheets)

def benchmark_for(metric):
    aliases = {
        "Time to Hire (TTH)": ["timetohire", "tth"],
        "Offer Acceptance Rate": ["offeracceptancerate"],
        "Applicant-to-Interview Conversion Rate": ["applicanttointerviewconversionrate", "applicationtointerviewconversionrate", "applicanttointerviewratio"],
        "Requisition Aging": ["requisitionaging", "openrequisitionbacklog"],
        "Source of Hire Effectiveness": ["sourceofhireeffectiveness"],
    }
    for key, value in industry_benchmarks_raw.items():
        if any(a in key or key in a for a in aliases.get(metric, [])):
            # For ranges, fallback config values are used for selected metrics as documented.
            return float(value), "industry workbook"
    return float(CONFIG["benchmarks_fallback"][metric]), "CONFIG fallback"

# Explicit leakage filter. Exclude identifiers, target components, post-outcome fields,
# free-text reason fields, and any feature whose name suggests it encodes the target.
LEAKAGE_TOKENS = [
    "timetohire", "time_to_hire", "requisitionagedays", "requisition_age_days",
    "offeraccepteddate", "offeraccepted", "accepteddate", "interviewdate",
    "applicationstatus", "requisitionstatus", "requisitionfilleddate",
    "requisitionclosedate", "requisitionclosed", "joiningdate", "positionfilleddate",
    "rejectionreason", "terminationreason", "outcome", "target", "label",
    "daysbetween", "duration", "hiredate", "filleddate", "actualresult",
]
ID_TOKENS = ["employeeid", "candidateid", "applicationid", "requisitionid", "email", "firstname", "lastname"]

def leak_reason(col, target_related_cols=None):
    n = norm(col)
    if any(t in n for t in ID_TOKENS):
        return "identifier / memorization risk"
    if any(t in n for t in LEAKAGE_TOKENS):
        return "target leakage / post-outcome field"
    if target_related_cols and col in target_related_cols:
        return "target construction field"
    if n.endswith("id") or n in ["id", "recordid"]:
        return "identifier"
    return None

def make_preprocessor(X):
    cat_cols = X.select_dtypes(include=["object", "category", "bool"]).columns.tolist()
    num_cols = [c for c in X.columns if c not in cat_cols]
    try:
        ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        ohe = OneHotEncoder(handle_unknown="ignore", sparse=False)
    transformers = []
    if num_cols:
        transformers.append(("num", Pipeline([("imputer", SimpleImputer(strategy="median")),
                                               ("scale", StandardScaler())]), num_cols))
    if cat_cols:
        transformers.append(("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                                               ("onehot", ohe)]), cat_cols))
    return ColumnTransformer(transformers, remainder="drop")

def engineer_features(df, date_columns=None):
    X = df.copy()
    # Convert datetimes into calendar features, never retain raw timestamps as numeric magnitudes.
    for c in list(X.columns):
        if pd.api.types.is_datetime64_any_dtype(X[c]):
            X[c + "__year"] = X[c].dt.year
            X[c + "__month"] = X[c].dt.month
            X[c + "__quarter"] = X[c].dt.quarter
            X = X.drop(columns=[c])
    # Numeric feature engineering: ratios and differences only when both source columns exist.
    lowmap = {norm(c): c for c in X.columns}
    pairs = [
        ("appCtcPa", "appExpCtc", "current_to_expected_ctc_ratio"),
        ("noOfPositionsFilled", "noOfPositionsOpened", "positions_fill_ratio"),
        ("offersAccepted", "offersExtended", "offer_acceptance_ratio_feature"),
        ("applicantsInterviewed", "totalApplicants", "interview_conversion_ratio_feature"),
    ]
    for left, right, out in pairs:
        lc, rc = lowmap.get(norm(left)), lowmap.get(norm(right))
        if lc and rc:
            a = pd.to_numeric(X[lc], errors="coerce")
            b = pd.to_numeric(X[rc], errors="coerce").replace(0, np.nan)
            X[out] = a / b
    # Remove all-null and constant fields dynamically.
    X = X.loc[:, [c for c in X.columns if X[c].notna().any() and X[c].nunique(dropna=True) > 1]]
    return X

def make_monthly(series_df, date_col, value_col, agg="mean"):
    tmp = series_df[[date_col, value_col]].copy()
    tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
    tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
    tmp = tmp.dropna()
    if tmp.empty:
        return pd.Series(dtype=float, name=value_col)
    tmp["month"] = tmp[date_col].dt.to_period("M").dt.to_timestamp()
    if agg == "sum":
        s = tmp.groupby("month")[value_col].sum()
    elif agg == "rate":
        s = tmp.groupby("month")[value_col].mean()
    else:
        s = tmp.groupby("month")[value_col].mean()
    return s.sort_index()

def trend_description(s):
    s = s.dropna()
    if len(s) < 2:
        return "Insufficient history to determine trend."
    slope = np.polyfit(np.arange(len(s)), s.values, 1)[0]
    if abs(slope) < 1e-8:
        direction = "flat"
    else:
        direction = "upward" if slope > 0 else "downward"
    return f"{direction.capitalize()} trend; simple linear slope {slope:.3f} units/month across {len(s)} observed months."

def forecast_next_month(s):
    s = s.dropna().astype(float)
    if len(s) < CONFIG["minimum_months_for_forecast"]:
        return None, "insufficient history for prediction", np.nan
    # Rolling-origin evaluation for a small, robust candidate set: naive, linear trend, Ridge lags.
    values = s.values
    errors = {"Last-value baseline": [], "Linear trend": [], "Lag-1 mean": []}
    for end in range(3, len(values)):
        train = values[:end]
        actual = values[end]
        errors["Last-value baseline"].append(abs(actual - train[-1]))
        xx = np.arange(len(train)).reshape(-1, 1)
        coef = np.polyfit(xx.ravel(), train, 1)
        pred = np.polyval(coef, len(train))
        errors["Linear trend"].append(abs(actual - pred))
        errors["Lag-1 mean"].append(abs(actual - np.mean(train[-min(3,len(train)):])) )
    scores = {k: float(np.mean(v)) for k,v in errors.items() if v}
    winner = min(scores, key=scores.get)
    if winner == "Last-value baseline":
        pred = values[-1]
    elif winner == "Linear trend":
        pred = np.polyval(np.polyfit(np.arange(len(values)), values, 1), len(values))
    else:
        pred = float(np.mean(values[-min(3,len(values)):]))
    return float(pred), winner, scores[winner]

def plot_trend(metric, s, benchmark):
    if s.empty:
        return
    plt.figure(figsize=(9,3.5))
    plt.plot(s.index, s.values, marker="o", label="Company monthly value")
    plt.axhline(benchmark, linestyle="--", label=f"Industry benchmark ({benchmark:g})")
    plt.title(metric + " — monthly trend")
    plt.xlabel("Month"); plt.ylabel("Metric value"); plt.grid(True, alpha=.25); plt.legend()
    plt.tight_layout(); plt.show()

def benchmark_status(metric, value, benchmark):
    if not np.isfinite(value):
        return "Not computable"
    direction = CONFIG["metric_directions"][metric]
    if direction == "higher":
        return "Healthy" if value >= benchmark else "At Risk / below benchmark"
    if direction == "band":
        return "Healthy" if value <= benchmark else "At Risk / outside reference band"
    return "Healthy" if value <= benchmark else "At Risk / above benchmark"

def variance_text(value, benchmark):
    if not np.isfinite(value) or not np.isfinite(benchmark):
        return "Variance unavailable"
    diff = value - benchmark
    pct = (diff / benchmark * 100.0) if benchmark != 0 else np.nan
    return f"Absolute variance: {diff:+.2f}; variance vs benchmark: {pct:+.2f}%"

# -------------------- Metric calculations ---------------------------
def get_status_series(df):
    c = find_col(df, "application_status")
    return df[c].astype(str).str.lower() if c else pd.Series("", index=df.index)

def compute_metrics(apps, reqs):
    out = {}
    # Time to Hire: target is computed fresh as accepted date minus requisition created date.
    if not apps.empty:
        ac = find_col(apps, "offer_accepted_date")
        rc = find_col(apps, "requisition_created_date")
        stored = find_col(apps, "stored_tth")
        if ac and rc:
            tth = (pd.to_datetime(apps[ac], errors="coerce") - pd.to_datetime(apps[rc], errors="coerce")).dt.total_seconds()/86400
            apps["__metric_tth_days"] = tth.where(tth >= 0)
            out["Time to Hire (TTH)"] = {"df": apps.copy(), "target": "__metric_tth_days", "date": ac, "grain":"application", "unit":"days"}
        elif stored:
            apps["__metric_tth_days"] = pd.to_numeric(apps[stored], errors="coerce")
            out["Time to Hire (TTH)"] = {"df": apps.copy(), "target":"__metric_tth_days", "date": find_col(apps,"application_date"), "grain":"application", "unit":"days (stored fallback)"}
        else:
            out["Time to Hire (TTH)"] = {"status":"not_computable: missing raw offer-accepted and requisition-created dates"}

        # Offer acceptance rate: accepted / decided offers, pending excluded.
        status = get_status_series(apps)
        accepted = status.str.contains(r"offer accepted|hired|pending start|no show|onboarding cancelled|joined", regex=True)
        declined = status.str.contains(r"offer declined|declined|rejected after offer", regex=True)
        offer_date_col = find_col(apps, "offer_release_date")
        accepted_date_col = find_col(apps, "offer_accepted_date")
        if offer_date_col:
            extended = pd.to_datetime(apps[offer_date_col], errors="coerce").notna()
        else:
            extended = status.str.contains("offer", regex=False)
        decided = accepted | declined
        rate_rows = apps.loc[extended & decided].copy()
        rate_rows["__metric_offer_acceptance_pct"] = np.where(accepted.loc[rate_rows.index], 100.0, 0.0)
        date_col = offer_date_col or find_col(apps, "application_date")
        out["Offer Acceptance Rate"] = {"df": rate_rows, "target":"__metric_offer_acceptance_pct", "date":date_col, "grain":"application decision", "unit":"percent"}
        if not len(rate_rows) and not reqs.empty:
            # Fallback to requisition-level accepted / extended counts when application-level
            # offer decisions are absent. This fallback cannot remove pending offers unless
            # the source export provides separate pending/decision fields.
            ext_col = find_col(reqs, "offers_extended")
            acc_col = find_col(reqs, "offers_accepted")
            req_date = find_col(reqs, "requisition_created_date")
            if ext_col and acc_col:
                fallback = reqs.copy()
                ext_n = pd.to_numeric(fallback[ext_col], errors="coerce").replace(0, np.nan)
                fallback["__metric_offer_acceptance_pct"] = pd.to_numeric(fallback[acc_col], errors="coerce") / ext_n * 100.0
                out["Offer Acceptance Rate"] = {"df": fallback, "target": "__metric_offer_acceptance_pct",
                                                "date": req_date, "grain": "requisition count fallback",
                                                "unit": "percent",
                                                "status": "computed_with_fallback: requisition accepted/extended counts; pending decisions cannot be excluded without decision-level data"}
            else:
                out["Offer Acceptance Rate"]["status"] = "not_computable: no explicit decided offers and no requisition offer counts"

        # Applicant-to-interview conversion: requisition-level interviewed / total applicants.
        total = find_col(reqs, "total_applicants") if not reqs.empty else None
        interviewed = find_col(reqs, "applicants_interviewed") if not reqs.empty else None
        req_date = find_col(reqs, "requisition_created_date") if not reqs.empty else None
        if total and interviewed:
            denom = pd.to_numeric(reqs[total], errors="coerce").replace(0, np.nan)
            reqs["__metric_interview_conversion_pct"] = pd.to_numeric(reqs[interviewed], errors="coerce") / denom * 100
            out["Applicant-to-Interview Conversion Rate"] = {"df":reqs.copy(), "target":"__metric_interview_conversion_pct", "date":req_date, "grain":"requisition", "unit":"percent"}
        elif not apps.empty:
            interview_date = find_col(apps, "interview_date")
            app_date = find_col(apps, "application_date")
            if interview_date and app_date:
                temp = apps.copy()
                temp["__interview_reached"] = pd.to_datetime(temp[interview_date], errors="coerce").notna().astype(int)
                temp["__metric_interview_conversion_pct"] = temp["__interview_reached"] * 100.0
                out["Applicant-to-Interview Conversion Rate"] = {"df":temp, "target":"__metric_interview_conversion_pct", "date":app_date, "grain":"application proxy", "unit":"percent"}
            else:
                out["Applicant-to-Interview Conversion Rate"] = {"status":"not_computable: missing applicant and interview stage fields"}
        else:
            out["Applicant-to-Interview Conversion Rate"] = {"status":"not_computable: missing requisition counts"}

    # Requisition Aging: only currently open requisitions are included.
    if not reqs.empty:
        status_col = find_col(reqs, "requisition_status")
        open_col = find_col(reqs, "open_flag")
        created = find_col(reqs, "requisition_created_date")
        age_col = find_col(reqs, "requisition_age_days")
        if status_col:
            open_mask = reqs[status_col].astype(str).str.lower().str.strip().eq("open - approved")
        elif open_col:
            open_mask = reqs[open_col].astype(str).str.upper().str.strip().isin(["Y","YES","TRUE","1"])
        else:
            open_mask = pd.Series(False, index=reqs.index)
        open_reqs = reqs.loc[open_mask].copy()
        if created:
            asof = pd.Timestamp.today().normalize()
            open_reqs["__metric_requisition_age_days"] = (asof - pd.to_datetime(open_reqs[created], errors="coerce")).dt.total_seconds()/86400
        elif age_col:
            open_reqs["__metric_requisition_age_days"] = pd.to_numeric(open_reqs[age_col], errors="coerce")
        else:
            open_reqs["__metric_requisition_age_days"] = np.nan
        out["Requisition Aging"] = {"df":open_reqs, "target":"__metric_requisition_age_days", "date":created, "grain":"currently open requisition", "unit":"days"}
        out["Requisition Aging"]["stale_count"] = int((open_reqs["__metric_requisition_age_days"] > CONFIG["stale_requisition_days"]).sum())
        if open_reqs.empty:
            out["Requisition Aging"]["status"] = "not_computable: no requisitions meet the configured open-status rule"

    # Source of Hire Effectiveness: per-source hired yield, company value = mean of source yields.
    if not apps.empty:
        source_col = find_col(apps, "source")
        status_col = find_col(apps, "application_status")
        app_date = find_col(apps, "application_date")
        if source_col and status_col:
            temp = apps.copy()
            st = temp[status_col].astype(str).str.lower()
            temp["__hired_binary"] = st.str.contains(r"\bhired\b|joined|pending start|no show|onboarding cancelled", regex=True).astype(int)
            temp["__metric_source_hire_pct"] = temp["__hired_binary"] * 100.0
            out["Source of Hire Effectiveness"] = {"df":temp, "target":"__metric_source_hire_pct", "date":app_date, "grain":"application grouped by source", "unit":"percent", "source_col":source_col}
        else:
            out["Source of Hire Effectiveness"] = {"status":"not_computable: missing source or application status"}
    return out

metric_data = compute_metrics(apps, reqs)

# ---------------- Dynamic field selection + regression models ----------------
def build_feature_frame(df, target, date_col=None, target_components=None):
    if target not in df.columns:
        return None, [], {"reason":"target column missing"}
    y = pd.to_numeric(df[target], errors="coerce")
    valid = y.notna() & np.isfinite(y)
    work = df.loc[valid].copy()
    y = y.loc[valid].astype(float)
    if len(work) < 2:
        return None, [], {"reason":"fewer than 2 valid target rows"}
    excluded = set([target])
    # Exclude date fields used to create the target, plus outcome dates/statuses and IDs.
    target_components = target_components or []
    excluded.update(target_components)
    selected, dropped = [], {}
    for c in work.columns:
        if c in excluded:
            dropped[c] = "target or target construction field"; continue
        reason = leak_reason(c, target_components)
        if reason:
            dropped[c] = reason; continue
        if c == date_col:
            # Calendar features from a known prediction-time date are allowed; raw date is transformed.
            pass
        if pd.api.types.is_datetime64_any_dtype(work[c]):
            # Keep date only when it is not a post-outcome or target-component date.
            if any(t in norm(c) for t in ["accepted","filled","joined","closed","interview","offerrelease"]):
                dropped[c] = "post-outcome date"; continue
        if CONFIG["exclude_sensitive_features"] and norm(c) in [norm(x) for x in CONFIG["sensitive_columns"]]:
            dropped[c] = "excluded by governance config"; continue
        if work[c].notna().sum() == 0 or work[c].nunique(dropna=True) <= 1:
            dropped[c] = "all-null or constant"; continue
        selected.append(c)
    X = work[selected].copy()
    # Target date itself is never a feature. We add only calendar parts if the date is known at prediction time.
    if date_col and date_col in X.columns:
        X = X.drop(columns=[date_col])
    X = engineer_features(X)
    # A final leakage sweep catches generated features and aliases.
    safe_cols = []
    for c in X.columns:
        reason = leak_reason(c, target_components)
        if reason:
            dropped[c] = reason
        else:
            safe_cols.append(c)
    X = X[safe_cols]
    return X, y, {"selected":safe_cols, "dropped":dropped, "rows":len(y)}

def regression_model_candidates(preprocessor, n_rows):
    # Ridge is the correct linear-regression counterpart; LogisticRegression is classification-only.
    models = {
        "Ridge Regression": Ridge(alpha=2.0),
        "Random Forest Regressor": RandomForestRegressor(
            n_estimators=250, max_depth=3 if n_rows < 80 else 6,
            min_samples_leaf=max(2, int(n_rows*0.05)), max_features=0.8,
            random_state=CONFIG["random_state"], n_jobs=-1),
        "XGBoost Regressor": XGBRegressor(
            n_estimators=120, max_depth=2 if n_rows < 80 else 3,
            learning_rate=0.03, subsample=0.8, colsample_bytree=0.8,
            reg_lambda=8.0, reg_alpha=0.5, min_child_weight=3,
            objective="reg:squarederror", random_state=CONFIG["random_state"],
            n_jobs=2, verbosity=0),
    }
    return {name: Pipeline([("prep", preprocessor), ("model", model)]) for name,model in models.items()}

def evaluate_regression(X, y, metric_name):
    print(f"\n--- REGRESSION MODEL EVALUATION: {metric_name} ---")
    if X is None or len(y) < CONFIG["minimum_rows_for_train_test"] or X.shape[1] == 0:
        print(f"Insufficient data for defensible train/validation/test R² (rows={0 if y is None else len(y)}, features={0 if X is None else X.shape[1]}).")
        return {"status":"insufficient_data", "train_r2":np.nan, "validation_r2":np.nan,
                "test_r2":np.nan, "winner":None, "all_results":[]}

    # Hold out the test set until the final, one-time evaluation. Model selection uses
    # out-of-fold validation predictions made only within the training partition.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=CONFIG["test_size"], random_state=CONFIG["random_state"])
    if len(y_train) < 4 or len(y_test) < 2:
        print("Insufficient rows after split for meaningful train/validation/test evaluation.")
        return {"status":"insufficient_data_after_split", "train_r2":np.nan,
                "validation_r2":np.nan, "test_r2":np.nan, "winner":None, "all_results":[]}

    pre = make_preprocessor(X_train)
    candidates = regression_model_candidates(pre, len(X_train))
    n_splits = min(5, max(2, len(y_train) // 2))
    cv = KFold(n_splits=n_splits, shuffle=True, random_state=CONFIG["random_state"])
    results = []

    for name, model in candidates.items():
        try:
            # Out-of-fold predictions provide a validation estimate for each training row.
            # The test partition is not used to select the model.
            val_pred = cross_val_predict(clone(model), X_train, y_train, cv=cv, n_jobs=None)
            val_r2 = r2_score(y_train, val_pred) if len(y_train) >= 2 else np.nan
            val_mae = mean_absolute_error(y_train, val_pred)

            # Fit once on all training rows; evaluate train and held-out test metrics.
            model.fit(X_train, y_train)
            train_pred = model.predict(X_train)
            test_pred = model.predict(X_test)
            tr2 = r2_score(y_train, train_pred) if len(y_train) >= 2 else np.nan
            te2 = r2_score(y_test, test_pred) if len(y_test) >= 2 else np.nan
            test_mae = mean_absolute_error(y_test, test_pred)
            test_rmse = mean_squared_error(y_test, test_pred) ** 0.5
            generalization_gap = tr2 - val_r2 if np.isfinite(tr2) and np.isfinite(val_r2) else np.nan

            # Selection uses validation MAE plus a penalty for a large train-validation gap.
            # R² is reported, but we do NOT target a specific value such as 0.99 or 1.00.
            penalty = max(0.0, generalization_gap - CONFIG["overfit_gap_threshold"]) * (np.std(y_train) + 1e-8)
            selection_score = val_mae + penalty
            status = "possible overfit" if np.isfinite(generalization_gap) and generalization_gap > CONFIG["overfit_gap_threshold"] else "no large train-validation R² gap detected"
            results.append({"name":name, "pipeline":model, "train_r2":tr2,
                            "validation_r2":val_r2, "test_r2":te2,
                            "validation_mae":val_mae, "test_mae":test_mae,
                            "test_rmse":test_rmse, "gap":generalization_gap,
                            "selection_score":selection_score, "fit_status":status})
            print(f"{name}: Train R²={tr2:.4f} | Validation R²={val_r2:.4f} | Test R²={te2:.4f} | "
                  f"Validation MAE={val_mae:.3f} | Test MAE={test_mae:.3f} | Test RMSE={test_rmse:.3f} | "
                  f"Train-validation gap={generalization_gap:.3f} | {status}")
        except Exception as e:
            print(f"{name} failed: {e}")

    if not results:
        return {"status":"all_models_failed", "train_r2":np.nan, "validation_r2":np.nan,
                "test_r2":np.nan, "winner":None}

    # R² eligibility rule requested for this project:
    # - A training R² of 1.00 is allowed and is reported, not used to disqualify a model.
    # - Validation R² and holdout-test R² must both be strictly below 1.00.
    # - Do not round before checking; values such as 0.9999 remain eligible.
    # - Among eligible candidates, select the highest validation R².
    # - Holdout test R² is used only as a pass/fail guard against a perfect score, not to rank models.
    eligible = []
    excluded_perfect = []
    for r in results:
        validation_is_100 = np.isfinite(r["validation_r2"]) and float(r["validation_r2"]) >= 1.0 - 1e-12
        test_is_100 = np.isfinite(r["test_r2"]) and float(r["test_r2"]) >= 1.0 - 1e-12
        if validation_is_100 or test_is_100:
            excluded_perfect.append(r)
        else:
            eligible.append(r)

    if excluded_perfect:
        print("\nExcluded models because Validation R² or Test R² is 1.00 or higher:")
        for r in excluded_perfect:
            print(f"  - {r['name']}: Train R²={r['train_r2']:.4f}, Validation R²={r['validation_r2']:.4f}, Test R²={r['test_r2']:.4f}")

    if not eligible:
        print("\nNo candidate remains after the strict R² filter.")
        print("No model is selected only when every candidate has actual Training or Validation R² >= 1.0000.")
        print("Review target leakage, target construction, sample size, or feature availability.")
        return {"status":"no_eligible_model_after_r2_filter", "train_r2":np.nan,
                "validation_r2":np.nan, "test_r2":np.nan, "winner":None,
                "all_results":results}

    winner = max(
        eligible,
        key=lambda r: (
            float(r["validation_r2"]) if np.isfinite(r["validation_r2"]) else -np.inf,
            -float(r["validation_mae"]) if np.isfinite(r["validation_mae"]) else -np.inf,
            -abs(float(r["gap"])) if np.isfinite(r["gap"]) else -np.inf
        )
    )
    print(f"\nSelected model: {winner['name']} (highest eligible Validation R²; Training R² may be 1.00, but Validation/Test R² may not).")
    print("\nALL REGRESSION R² VALUES")
    print("Model                         Train R²      Validation R²      Test R²")
    print("-" * 78)
    for r in results:
        print(f"{r['name']:<29} {r['train_r2']:>9.4f}      {r['validation_r2']:>14.4f}      {r['test_r2']:>8.4f}")
    print(f"\nSelected Train R²={winner['train_r2']:.4f}; Validation R²={winner['validation_r2']:.4f}; Test R²={winner['test_r2']:.4f}.")
    if len(y) < 30:
        print("CAUTION: Very small sample. All split/CV R² values may be highly unstable; they are not proof of reliable future accuracy.")
    return {"status":"evaluated", "winner":winner["name"], "pipeline":winner["pipeline"],
            "train_r2":winner["train_r2"], "validation_r2":winner["validation_r2"],
            "test_r2":winner["test_r2"], "validation_mae":winner["validation_mae"],
            "mae":winner["test_mae"], "rmse":winner["test_rmse"], "gap":winner["gap"],
            "selection_score":winner["selection_score"], "all_results":results,
            "excluded_r2_100_models":[r["name"] for r in excluded_perfect]}

# Binary classification comparison. Logistic Regression is included only where target is genuinely binary.
def evaluate_classification(X, y_binary, label):
    print(f"\n--- CLASSIFICATION MODEL COMPARISON: {label} ---")
    y_binary = pd.Series(y_binary).astype(int)
    if X is None or X.shape[1] == 0 or len(y_binary) < 12 or y_binary.nunique() < 2 or y_binary.value_counts().min() < 2:
        print("Classification comparison skipped: too few rows or only one class.")
        return {"status":"insufficient_class_data"}
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_binary, test_size=CONFIG["test_size"], random_state=CONFIG["random_state"], stratify=y_binary)
    pre = make_preprocessor(X_train)
    candidates = {
        "Logistic Regression": LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000),
        "Random Forest Classifier": RandomForestClassifier(n_estimators=250, max_depth=4,
            min_samples_leaf=2, class_weight="balanced", random_state=CONFIG["random_state"], n_jobs=-1),
        "XGBoost Classifier": XGBClassifier(n_estimators=100, max_depth=2, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8, reg_lambda=8, min_child_weight=3,
            eval_metric="logloss", random_state=CONFIG["random_state"], n_jobs=2, verbosity=0),
    }
    rows = []
    for name, estimator in candidates.items():
        pipe = Pipeline([("prep",pre),("model",estimator)])
        try:
            pipe.fit(X_train,y_train)
            p_train = pipe.predict(X_train); p_test = pipe.predict(X_test)
            prob = pipe.predict_proba(X_test)[:,1] if hasattr(pipe,"predict_proba") else p_test
            auc = roc_auc_score(y_test, prob) if len(np.unique(y_test)) == 2 else np.nan
            tr_acc = accuracy_score(y_train,p_train); te_acc = accuracy_score(y_test,p_test)
            gap = tr_acc-te_acc
            rows.append((name,pipe,te_acc,auc,gap))
            print(f"{name}: train accuracy={tr_acc:.3f} | test accuracy={te_acc:.3f} | test ROC-AUC={auc:.3f} | accuracy gap={gap:.3f}")
        except Exception as e:
            print(f"{name} failed: {e}")
    if not rows:
        return {"status":"all_models_failed"}
    stable = [r for r in rows if r[4] <= 0.20]
    pool = stable if stable else rows
    winner = max(pool, key=lambda r: (np.nan_to_num(r[3],nan=-1),r[2]))
    print("Selected classification model:",winner[0],"(ROC-AUC prioritized, with overfit-gap guard).")
    return {"status":"evaluated","winner":winner[0],"pipeline":winner[1],"test_accuracy":winner[2],"test_auc":winner[3],"gap":winner[4]}

def contribution_analysis(df, target, segment_col, metric_name):
    if segment_col not in df.columns or target not in df.columns or df.empty:
        print("Contribution RCA unavailable: segment or target missing.")
        return
    temp = df[[segment_col,target]].copy()
    temp[target] = pd.to_numeric(temp[target],errors="coerce")
    temp = temp.dropna()
    if temp.empty:
        print("Contribution RCA unavailable: no valid records.")
        return
    overall = temp[target].mean()
    grp = temp.groupby(segment_col, dropna=False)[target].agg(["mean","count"])
    grp["segment_share"] = grp["count"]/grp["count"].sum()
    grp["contribution_pp"] = grp["segment_share"]*(grp["mean"]-overall)
    grp = grp.sort_values("contribution_pp",ascending=False)
    print(f"\nCONTRIBUTION-BASED RCA — {metric_name} (overall={overall:.2f})")
    print("Contribution = segment share × (segment rate − overall rate). Positive values pull metric upward.")
    print(grp.to_string())

def show_feature_importance(model_result, X, y, metric_name):
    if not model_result or model_result.get("status") != "evaluated" or model_result.get("pipeline") is None:
        print("Feature-level RCA not produced because a defensible fitted model is unavailable.")
        return
    pipe = model_result["pipeline"]
    if len(y) < CONFIG["minimum_rows_for_shap"]:
        print(f"SHAP/ensemble RCA caution: only {len(y)} valid rows. Using permutation importance as a tentative diagnostic; not a causal claim.")
    try:
        imp = permutation_importance(pipe, X, y, scoring="r2", n_repeats=8,
                                     random_state=CONFIG["random_state"])
        names = X.columns.tolist()
        vals = imp.importances_mean
        result = pd.DataFrame({"feature":names[:len(vals)],"permutation_importance":vals[:len(names)]})
        result = result.sort_values("permutation_importance",ascending=False).head(10)
        print(f"\nTOP CONTRIBUTING PREDICTORS — {metric_name}")
        print(result.to_string(index=False))
        print("Interpretation: these are predictive associations, not proof of causation.")
    except Exception as e:
        print("Feature importance unavailable:",e)


# =====================================================================
# JSON OUTPUT / PREDICTION LAYER
# IMPORTANT:
# - The training/testing logic above is NOT changed.
# - Training/evaluation still uses the existing 3 models:
#       Ridge Regression, Random Forest Regressor, XGBoost Regressor
# - The prediction/reporting layer compares three RCA models with SHAP attribution,
#   and compares HistGradientBoostingRegressor against DampedTrend for forecasts.
# - The JSON structure below follows metric_output_sample.json.
# =====================================================================

from datetime import datetime, timezone

OUTPUT_JSON_FILE = None  # Reports are pushed directly to Supabase; no local JSON output.

# ----------------------------- JSON helpers ---------------------------
def json_safe(v):
    """Convert numpy/pandas objects into JSON-safe Python values."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v) if np.isfinite(v) else None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, float):
        return v if np.isfinite(v) else None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v

def json_clean(obj):
    if isinstance(obj, dict):
        return {str(k): json_clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_clean(v) for v in obj]
    return json_safe(obj)

def fmt_metric_name(metric_name):
    return {
        "Time to Hire (TTH)": "TimeToHire",
        "Offer Acceptance Rate": "OfferAcceptanceRate",
        "Applicant-to-Interview Conversion Rate": "ApplicantToInterviewConversionRate",
        "Requisition Aging": "RequisitionAging",
        "Source of Hire Effectiveness": "SourceOfHireEffectiveness",
    }.get(metric_name, re.sub(r"[^A-Za-z0-9]+", "", metric_name))

def higher_is_better(metric_name):
    return CONFIG["metric_directions"].get(metric_name) == "higher"

def health_state_json(metric_name, value, benchmark):
    if value is None or benchmark is None:
        return "not-computable"
    direction = CONFIG["metric_directions"].get(metric_name)
    if direction == "higher":
        return "healthy" if value >= benchmark else "at-risk"
    # For lower-is-better and band metrics, use the existing benchmark logic.
    return "healthy" if value <= benchmark else "at-risk"

def rating_from_model_metrics(r2, mae, rmse):
    if r2 is None:
        return "not-available"
    if r2 >= 0.80:
        return "good"
    if r2 >= 0.60:
        return "fair"
    return "poor"

# -------------------------- Trend JSON --------------------------------
def monthly_series_for_metric(df, target, date_col, metric_name, info):
    if not date_col or date_col not in df.columns:
        return pd.Series(dtype=float)

    dated = df.copy()
    dated["__json_date"] = pd.to_datetime(dated[date_col], errors="coerce")
    dated["__json_target"] = pd.to_numeric(dated[target], errors="coerce")
    dated = dated.dropna(subset=["__json_date", "__json_target"])

    if dated.empty:
        return pd.Series(dtype=float)

    dated["__month"] = dated["__json_date"].dt.to_period("M").dt.to_timestamp()

    if metric_name == "Applicant-to-Interview Conversion Rate":
        total_col = find_col(dated, "total_applicants")
        interviewed_col = find_col(dated, "applicants_interviewed")
        if total_col and interviewed_col:
            dated["__total"] = pd.to_numeric(dated[total_col], errors="coerce")
            dated["__interviewed"] = pd.to_numeric(dated[interviewed_col], errors="coerce")
            g = dated.groupby("__month")[["__total", "__interviewed"]].sum(min_count=1)
            return (g["__interviewed"] / g["__total"].replace(0, np.nan) * 100).dropna()

    if metric_name == "Source of Hire Effectiveness" and info.get("source_col") in dated.columns:
        by_source = dated.groupby(["__month", info["source_col"]])["__json_target"].mean()
        return by_source.groupby(level=0).mean().sort_index()

    return dated.groupby("__month")["__json_target"].mean().sort_index()

def make_period_node(period, value, is_partial, granularity, **extra):
    node = {
        "period": str(period),
        **extra,
        "average": json_safe(value),
        "isPartial": bool(is_partial),
    }
    return node

def build_hierarchical_trend(monthly, metric_name):
    """
    Builds:
      yearly -> quarterly -> monthly
    in the same nested style as the supplied JSON.
    """
    if monthly is None or len(monthly) == 0:
        return {
            "direction": "unknown",
            "granularity": "yearly",
            "periods": []
        }

    s = monthly.copy().dropna()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()

    # Trend direction is based on a simple regression over observed months.
    if len(s) >= 2:
        slope = np.polyfit(np.arange(len(s)), s.values.astype(float), 1)[0]
        direction = "up" if slope > 1e-8 else ("down" if slope < -1e-8 else "flat")
    else:
        direction = "unknown"

    today = pd.Timestamp.today().normalize()
    latest_observed_period = s.index.max().to_period("M")
    current_month_period = today.to_period("M")

    years = sorted(set(s.index.year.tolist()))
    year_nodes = []

    for year in years:
        year_s = s[s.index.year == year]
        year_partial = year == current_month_period.year and latest_observed_period < current_month_period

        quarter_nodes = []
        for q in range(1, 5):
            q_s = year_s[year_s.index.quarter == q]
            months = []
            for m in range(1, 4):
                month_num = (q - 1) * 3 + m
                vals = year_s[year_s.index.month == month_num]
                value = float(vals.mean()) if len(vals) else None

                # A month is partial if it is the current month or if it is
                # in the future relative to the available dataset.
                month_period = pd.Period(f"{year}-{month_num:02d}", freq="M")
                is_partial = (
                    value is None
                    or month_period == current_month_period
                    or month_period > latest_observed_period
                )

                months.append(
                    make_period_node(
                        f"{year}-{month_num:02d}",
                        value,
                        is_partial,
                        "monthly",
                        month=month_num,
                    )
                )

            q_value = float(q_s.mean()) if len(q_s) else None
            q_period_end = pd.Period(f"{year}-Q{q}", freq="Q").end_time.to_period("M")
            q_partial = (
                q_value is None
                or q_period_end > latest_observed_period
                or (year == current_month_period.year and q_period_end >= current_month_period)
            )

            quarter_nodes.append({
                "period": f"{year}-Q{q}",
                "quarter": q,
                "average": json_safe(q_value),
                "isPartial": bool(q_partial),
                "children": {
                    "granularity": "monthly",
                    "periods": months,
                },
            })

        year_value = float(year_s.mean()) if len(year_s) else None
        year_nodes.append({
            "period": str(year),
            "year": year,
            "average": json_safe(year_value),
            "isPartial": bool(year_partial),
            "children": {
                "granularity": "quarterly",
                "periods": quarter_nodes,
            },
        })

    return {
        "direction": direction,
        "granularity": "yearly",
        "periods": year_nodes,
    }

# ------------------------- DampedTrend --------------------------------
def damped_trend_forecast(series, periods_ahead=1, damping=0.80):
    """
    DampedTrend implementation used ONLY by the prediction/reporting layer.
    It is intentionally separate from the training/evaluation models above.

    The last observed level and recent trend are projected forward while the
    trend contribution is progressively damped:
        forecast(h) = level + trend * sum(damping^1 ... damping^h)
    """
    s = pd.Series(series).dropna().astype(float)
    if len(s) == 0:
        return None
    if len(s) == 1:
        return float(s.iloc[-1])

    # Use a short robust recent window so old history does not dominate.
    window = min(6, len(s))
    recent = s.iloc[-window:].values.astype(float)
    x = np.arange(len(recent), dtype=float)

    try:
        slope, intercept = np.polyfit(x, recent, 1)
        level = float(recent[-1])
        trend = float(slope)
    except Exception:
        level = float(recent[-1])
        trend = float(recent[-1] - recent[-2])

    damp_sum = sum(damping ** i for i in range(1, periods_ahead + 1))
    prediction = level + trend * damp_sum

    return float(prediction)

def damped_trend_error(series):
    """
    Rolling-origin MAE/RMSE for the DampedTrend prediction model.
    This is forecast-model evaluation and is deliberately separate from
    the 3-model training/testing stage.
    """
    s = pd.Series(series).dropna().astype(float).reset_index(drop=True)
    if len(s) < 4:
        return np.nan, np.nan

    actuals, preds = [], []
    for i in range(3, len(s)):
        train = s.iloc[:i]
        pred = damped_trend_forecast(train, periods_ahead=1)
        if pred is not None:
            actuals.append(float(s.iloc[i]))
            preds.append(float(pred))

    if not actuals:
        return np.nan, np.nan

    mae = mean_absolute_error(actuals, preds)
    rmse = mean_squared_error(actuals, preds) ** 0.5
    return float(mae), float(rmse)

def _hgb_one_step_forecast(history):
    """One-step time-series forecast using HistGradientBoosting and lag features."""
    values = np.asarray(pd.Series(history).dropna(), dtype=float)
    if len(values) < 6:
        return None
    X_rows, y_rows = [], []
    for idx in range(3, len(values)):
        X_rows.append([idx, values[idx-1], values[idx-2], values[idx-3], np.mean(values[max(0, idx-3):idx])])
        y_rows.append(values[idx])
    if len(y_rows) < 3:
        return None
    model = HistGradientBoostingRegressor(max_iter=100, learning_rate=0.05, max_leaf_nodes=7,
                                          l2_regularization=2.0, random_state=CONFIG["random_state"])
    model.fit(np.asarray(X_rows, dtype=float), np.asarray(y_rows, dtype=float))
    idx = len(values)
    row = np.asarray([[idx, values[-1], values[-2], values[-3], np.mean(values[-3:])]], dtype=float)
    return float(model.predict(row)[0])


def _hgb_forecast(series, periods_ahead=1):
    values = list(np.asarray(pd.Series(series).dropna(), dtype=float))
    if len(values) < 6:
        return None
    pred = None
    for _ in range(int(periods_ahead)):
        pred = _hgb_one_step_forecast(values)
        if pred is None or not np.isfinite(pred):
            return None
        values.append(float(pred))
    return float(pred)


def _forecast_candidate_errors(series, model_name):
    s = pd.Series(series).dropna().astype(float).reset_index(drop=True)
    actuals, preds = [], []
    min_train = 6 if model_name == "HistGradientBoostingRegressor" else 3
    for idx in range(min_train, len(s)):
        train = s.iloc[:idx]
        if model_name == "DampedTrend":
            pred = damped_trend_forecast(train, 1)
        else:
            pred = _hgb_forecast(train, 1)
        if pred is not None and np.isfinite(pred):
            actuals.append(float(s.iloc[idx])); preds.append(float(pred))
    if not actuals:
        return {"mae": None, "rmse": None, "r2": None, "n": 0}
    mae = float(mean_absolute_error(actuals, preds))
    rmse = float(np.sqrt(mean_squared_error(actuals, preds)))
    r2 = float(r2_score(actuals, preds)) if len(actuals) >= 2 and len(set(actuals)) > 1 else None
    return {"mae": mae, "rmse": rmse, "r2": r2, "n": len(actuals)}


def build_forecast_json(monthly, metric_name, benchmark):
    global FORECAST_MODEL_RESULT
    FORECAST_MODEL_RESULT = {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "not-available"}
    empty = {key: {"period": None, "predictedValue": None, "lowerBound": None, "upperBound": None,
                   "predictedHealthState": "not-computable"}
             for key in ("nextMonth", "nextQuarter", "nextYear")}
    if monthly is None or len(monthly) == 0:
        return empty
    s = pd.Series(monthly).dropna().astype(float).sort_index()
    if len(s) < 4:
        return empty
    scores = {
        "DampedTrend": _forecast_candidate_errors(s, "DampedTrend"),
        "HistGradientBoostingRegressor": _forecast_candidate_errors(s, "HistGradientBoostingRegressor"),
    }
    eligible = [(name, result) for name, result in scores.items() if result.get("rmse") is not None and np.isfinite(result["rmse"])]
    if eligible:
        winner_name, winner_metrics = min(eligible, key=lambda item: (item[1]["rmse"], item[1]["mae"]))
    else:
        # When there is not enough history to validate HGB, DampedTrend is the transparent fallback.
        winner_name, winner_metrics = "DampedTrend", scores["DampedTrend"]
    print("\nFORECAST MODEL COMPARISON (rolling-origin backtest)")
    for candidate_name, candidate_metrics in scores.items():
        print(f"  {candidate_name}: MAE={candidate_metrics.get('mae')} | RMSE={candidate_metrics.get('rmse')} | R2={candidate_metrics.get('r2')} | folds={candidate_metrics.get('n')}")
    print("Selected forecast model:", winner_name)
    FORECAST_MODEL_RESULT = {
        "modelName": winner_name, "r2": winner_metrics.get("r2"),
        "mae": winner_metrics.get("mae"), "rmse": winner_metrics.get("rmse"),
        "rating": rating_from_model_metrics(winner_metrics.get("r2"), winner_metrics.get("mae"), winner_metrics.get("rmse")),
        "candidateModels": scores,
    }
    last_period = pd.Period(pd.to_datetime(s.index.max()), freq="M")
    uncertainty = winner_metrics.get("rmse")
    if uncertainty is None or not np.isfinite(uncertainty):
        uncertainty = winner_metrics.get("mae")
    uncertainty = float(uncertainty) if uncertainty is not None and np.isfinite(uncertainty) else 0.0
    result = {}
    for key, horizon, target_period in [("nextMonth", 1, last_period + 1),
                                         ("nextQuarter", 3, last_period + 3),
                                         ("nextYear", 12, last_period + 12)]:
        if winner_name == "HistGradientBoostingRegressor":
            pred = _hgb_forecast(s, horizon)
            if pred is None:
                pred = damped_trend_forecast(s, horizon)
        else:
            pred = damped_trend_forecast(s, horizon)
        margin = 1.96 * uncertainty
        lower = max(0.0, float(pred) - margin) if pred is not None else None
        upper = float(pred) + margin if pred is not None else None
        result[key] = {"period": str(target_period), "predictedValue": json_safe(pred),
                       "lowerBound": json_safe(lower), "upperBound": json_safe(upper),
                       "predictedHealthState": health_state_json(metric_name, pred, benchmark)}
    return result

# ----------------------- Prediction RCA model --------------------------
def fit_prediction_rca_model(X, y, metric_name):
    """Compare Ridge, Random Forest and XGBoost for RCA; explain all fitted models with SHAP.

    Model selection excludes an exact/perfect test R² >= 1.0, then selects the highest
    remaining test R². SHAP absolute impacts are averaged across the fitted candidates.
    """
    result = {"modelName": "Not run", "r2": None, "mae": None, "rmse": None,
              "rating": "not-available", "feature_importance": [], "candidateModels": [], "status": "not-available"}
    if X is None or y is None or len(y) < 8 or X.shape[1] == 0:
        result["status"] = "insufficient_data"
        return result
    try:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=CONFIG["test_size"], random_state=CONFIG["random_state"])
        if len(y_train) < 4 or len(y_test) < 2:
            result["status"] = "insufficient_data_after_split"; return result
        pre = make_preprocessor(X_train)
        A = np.asarray(pre.fit_transform(X_train), dtype=float)
        B = np.asarray(pre.transform(X_test), dtype=float)
        try:
            feature_names = [str(x) for x in pre.get_feature_names_out()]
        except Exception:
            feature_names = [f"feature_{i}" for i in range(A.shape[1])]
        models = {
            "Ridge Regression": Ridge(alpha=10.0),
            "Random Forest Regressor": RandomForestRegressor(n_estimators=220, max_depth=6, min_samples_leaf=3,
                                                               random_state=CONFIG["random_state"], n_jobs=-1),
            "XGBoost Regressor": XGBRegressor(n_estimators=140, max_depth=2, learning_rate=0.04,
                                               subsample=0.85, colsample_bytree=0.85, reg_lambda=8,
                                               min_child_weight=3, objective="reg:squarederror",
                                               random_state=CONFIG["random_state"], n_jobs=2, verbosity=0),
        }
        fitted, candidate_rows, shap_impacts = {}, [], []
        for name, model in models.items():
            try:
                model.fit(A, y_train)
                pred = np.asarray(model.predict(B), dtype=float)
                tr_pred = np.asarray(model.predict(A), dtype=float)
                r2 = float(r2_score(y_test, pred)) if len(y_test) >= 2 and len(np.unique(y_test)) > 1 else None
                train_r2 = float(r2_score(y_train, tr_pred)) if len(y_train) >= 2 and len(np.unique(y_train)) > 1 else None
                mae = float(mean_absolute_error(y_test, pred))
                rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
                row = {"name": name, "r2": r2, "trainR2": train_r2, "mae": mae, "rmse": rmse}
                candidate_rows.append(row); fitted[name] = (model, pred, row)
                try:
                    import shap
                    sample = A[:min(len(A), 150)]
                    if name == "Ridge Regression":
                        explainer = shap.LinearExplainer(model, sample)
                        values = explainer.shap_values(sample)
                    else:
                        explainer = shap.TreeExplainer(model)
                        values = explainer.shap_values(sample)
                    values = np.asarray(values, dtype=float)
                    if values.ndim == 3:
                        values = values[:, :, -1]
                    if values.ndim == 2 and values.shape[1] == len(feature_names):
                        mean_abs = np.nanmean(np.abs(values), axis=0)
                        shap_impacts.append(mean_abs)
                except Exception as shap_exc:
                    print(f"SHAP warning for {name}: {shap_exc}")
            except Exception as model_exc:
                candidate_rows.append({"name": name, "r2": None, "trainR2": None, "mae": None, "rmse": None, "error": str(model_exc)})
        if not fitted:
            result["status"] = "all_models_failed"; result["candidateModels"] = candidate_rows; return result
        eligible = [(name, tup) for name, tup in fitted.items()
                    if tup[2]["r2"] is not None and np.isfinite(tup[2]["r2"])
                    and tup[2]["r2"] < 1.0 - 1e-12]
        # Do not select an RCA model if every candidate has a perfect/over-perfect test R².
        winner_name, (winner_model, winner_pred, winner_row) = max(eligible, key=lambda item: item[1][2]["r2"]) if eligible else (None, (None, None, {}))
        print("\nRCA MODEL COMPARISON (held-out test set)")
        for candidate in candidate_rows:
            print(f"  {candidate.get('name')}: Test R2={candidate.get('r2')} | MAE={candidate.get('mae')} | RMSE={candidate.get('rmse')}")
        if winner_name is None:
            print("No RCA model selected: every valid candidate had R2 >= 1.0 or unavailable R2.")
            result["status"] = "no_valid_test_r2"; result["candidateModels"] = candidate_rows; return result
        print("Selected RCA model:", winner_name)
        if shap_impacts:
            mean_importance = np.nanmean(np.vstack(shap_impacts), axis=0)
            attribution_method = "Mean absolute SHAP across fitted Ridge, Random Forest and XGBoost candidates"
        else:
            # Deterministic fallback if SHAP cannot run: permutation importance on the held-out set for each candidate.
            imp_arrays = []
            for name, (model, _, _) in fitted.items():
                try:
                    imp = permutation_importance(model, B, y_test, scoring="neg_mean_absolute_error", n_repeats=8,
                                                 random_state=CONFIG["random_state"], n_jobs=1)
                    imp_arrays.append(np.abs(imp.importances_mean))
                except Exception:
                    pass
            mean_importance = np.nanmean(np.vstack(imp_arrays), axis=0) if imp_arrays else np.zeros(len(feature_names))
            attribution_method = "Permutation importance fallback; SHAP unavailable"
        order = np.argsort(np.nan_to_num(mean_importance, nan=0.0))[::-1][:10]
        total = float(np.sum(np.maximum(np.nan_to_num(mean_importance, nan=0.0), 0.0)))
        for idx in order:
            imp = float(mean_importance[idx]) if np.isfinite(mean_importance[idx]) else 0.0
            result["feature_importance"].append({"feature": feature_names[idx], "importance": imp,
                                                "impactPct": (100.0 * imp / total if total > 0 else None),
                                                "method": attribution_method})
        print("SHAP attribution method:", attribution_method)
        result.update({"modelName": winner_name, "r2": json_safe(winner_row.get("r2")),
                       "mae": json_safe(winner_row.get("mae")), "rmse": json_safe(winner_row.get("rmse")),
                       "rating": rating_from_model_metrics(winner_row.get("r2"), winner_row.get("mae"), winner_row.get("rmse")),
                       "status": "evaluated", "candidateModels": candidate_rows, "attributionMethod": attribution_method})
    except Exception as exc:
        result["status"] = "failed"; result["error"] = str(exc)
    return result

# ----------------------- Detailed RCA output ----------------------------
def build_rca_json(df, target, metric_name, info, rca_model_result,
                   company_value, benchmark):
    breach_value = None
    if np.isfinite(company_value) and np.isfinite(benchmark):
        if CONFIG["metric_directions"].get(metric_name) == "higher":
            breach_value = max(0.0, benchmark - company_value)
        else:
            breach_value = max(0.0, company_value - benchmark)

    factors = []

    # 1. Model-based predictive factors.
    rank = 1
    for item in rca_model_result.get("feature_importance", [])[:10]:
        imp = item.get("importance")
        if imp is None:
            continue

        factors.append({
            "rank": rank,
            "factorName": str(item["feature"]),
            "segment": None,
            "avgFactorValue": None,
            "segmentAvgValue": None,
            "impactValue": json_safe(abs(float(imp))),
            "impactPct": None,
            "description": (
                "Predictive SHAP contribution aggregated across Ridge, Random Forest and XGBoost; "
                "this indicates association, not causation."
            ),
        })
        rank += 1

    # 2. Segment contribution for rate metrics.
    segment_col = None
    if metric_name == "Source of Hire Effectiveness":
        segment_col = info.get("source_col")
    elif metric_name == "Offer Acceptance Rate":
        segment_col = find_col(df, "source")
    elif metric_name == "Applicant-to-Interview Conversion Rate":
        for c in [
            find_col(df, "departmentName"),
            find_col(df, "departmentId"),
            find_col(df, "jobRole"),
            find_col(df, "requisition_status"),
        ]:
            if c and c in df.columns and df[c].nunique(dropna=True) > 1:
                segment_col = c
                break

    if segment_col and segment_col in df.columns and target in df.columns:
        try:
            tmp = df[[segment_col, target]].copy()
            tmp[target] = pd.to_numeric(tmp[target], errors="coerce")
            tmp = tmp.dropna()

            if len(tmp) > 0 and tmp[segment_col].nunique(dropna=True) > 1:
                overall = float(tmp[target].mean())
                grp = tmp.groupby(segment_col, dropna=False)[target].agg(["mean", "count"])
                grp["share"] = grp["count"] / grp["count"].sum()
                grp["impact"] = grp["share"] * (grp["mean"] - overall)

                # Add the strongest segments after model factors.
                for seg_value, row in grp.reindex(
                    grp["impact"].abs().sort_values(ascending=False).index
                ).head(5).iterrows():
                    if rank > 10:
                        break

                    seg_avg = float(row["mean"])
                    impact = float(row["impact"])
                    factors.append({
                        "rank": rank,
                        "factorName": str(segment_col),
                        "segment": json_safe(seg_value),
                        "avgFactorValue": None,
                        "segmentAvgValue": json_safe(seg_avg),
                        "impactValue": json_safe(abs(impact)),
                        "impactPct": None,
                        "description": (
                            "Segment contribution based on segment share and "
                            "difference from the overall metric."
                        ),
                    })
                    rank += 1
        except Exception:
            pass

    # Normalize impact percentages across returned factors.
    numeric_impacts = [
        abs(float(x["impactValue"]))
        for x in factors
        if x.get("impactValue") is not None
    ]
    total_impact = sum(numeric_impacts)

    if total_impact > 0:
        for x in factors:
            if x.get("impactValue") is not None:
                x["impactPct"] = round(
                    abs(float(x["impactValue"])) / total_impact * 100.0, 2
                )

    return {
        "applicable": bool(len(factors) > 0),
        "breachValue": json_safe(breach_value),
        "factors": factors,
        "description": (
            "Root-cause analysis uses the final prediction-stage "
            "Three-model SHAP-based predictive attribution and segment contribution analysis. "
            "Factors indicate predictive association, not proven causation."
        ),
    }

# ------------------------- Data quality --------------------------------
def date_range_for_df(df):
    date_values = []
    for c in df.columns:
        if any(t in norm(c) for t in ["date", "datetime", "month"]):
            try:
                s = pd.to_datetime(df[c], errors="coerce").dropna()
                if len(s):
                    date_values.extend(s.tolist())
            except Exception:
                pass

    if not date_values:
        return None, None

    return min(date_values), max(date_values)

def build_data_quality(df, info, metric_name):
    """
    Produces the JSON dataQuality object from the actual metric data.
    Mandatory fields are metric-dependent and are reported explicitly.
    """
    if df is None:
        df = pd.DataFrame()

    records = int(len(df))
    start_date, end_date = date_range_for_df(df)

    checks = []
    mandatory = []

    # Metric-specific mandatory configuration.
    if metric_name == "Time to Hire (TTH)":
        mandatory = [
            find_col(df, "requisition_created_date"),
            find_col(df, "offer_accepted_date"),
        ]
    elif metric_name == "Offer Acceptance Rate":
        mandatory = [
            find_col(df, "offer_release_date"),
            find_col(df, "application_status"),
        ]
    elif metric_name == "Applicant-to-Interview Conversion Rate":
        mandatory = [
            find_col(df, "total_applicants"),
            find_col(df, "applicants_interviewed"),
        ]
    elif metric_name == "Requisition Aging":
        mandatory = [
            find_col(df, "requisition_created_date") or find_col(df, "requisition_age_days"),
            find_col(df, "requisition_status") or find_col(df, "open_flag"),
        ]
    elif metric_name == "Source of Hire Effectiveness":
        mandatory = [
            find_col(df, "source"),
            find_col(df, "application_status"),
        ]

    mandatory = [c for c in mandatory if c]

    missing_fields = []
    for c in mandatory:
        if c not in df.columns:
            missing_fields.append(c)

    # Completeness check for mandatory fields.
    if mandatory:
        missing_mask = pd.Series(False, index=df.index)
        affected = []

        for c in mandatory:
            if c in df.columns:
                m = df[c].isna() | df[c].astype(str).str.strip().eq("")
                missing_mask = missing_mask | m
                if m.any():
                    affected.append(c)

        failed = int(missing_mask.sum())
        checks.append({
            "checkName": "MandatoryFieldsMissing",
            "category": "Completeness",
            "checkedRecords": records,
            "failedRecords": failed,
            "failedPct": round(failed / records * 100, 2) if records else 0.0,
            "affectedColumns": affected if affected else None,
            "staleRange": None,
            "description": (
                "Checks whether mandatory fields required for this metric "
                "contain missing or blank values."
            ),
        })

    # Generic incomplete-data check.
    if records:
        incomplete_mask = df.isna().any(axis=1)
        incomplete_count = int(incomplete_mask.sum())
        incomplete_cols = [
            c for c in df.columns
            if df[c].isna().any()
        ]
        checks.append({
            "checkName": "IncompleteRecords",
            "category": "Completeness",
            "checkedRecords": records,
            "failedRecords": incomplete_count,
            "failedPct": round(incomplete_count / records * 100, 2),
            "affectedColumns": incomplete_cols[:50] if incomplete_cols else None,
            "staleRange": None,
            "description": (
                "Counts records containing one or more incomplete fields."
            ),
        })

    # Staleness check for requisitions.
    if metric_name == "Requisition Aging" and "__metric_requisition_age_days" in df.columns:
        stale = pd.to_numeric(df["__metric_requisition_age_days"], errors="coerce") > CONFIG["stale_requisition_days"]
        stale_count = int(stale.sum())

        stale_dates = pd.Series(dtype="datetime64[ns]")
        created = find_col(df, "requisition_created_date")
        if created:
            stale_dates = pd.to_datetime(
                df.loc[stale, created], errors="coerce"
            ).dropna()

        checks.append({
            "checkName": "StaleRequisitions",
            "category": "Staleness",
            "checkedRecords": records,
            "failedRecords": stale_count,
            "failedPct": round(stale_count / records * 100, 2) if records else 0.0,
            "affectedColumns": [created] if created else None,
            "staleRange": (
                {
                    "from": stale_dates.min().date().isoformat(),
                    "to": stale_dates.max().date().isoformat(),
                }
                if len(stale_dates) else None
            ),
            "description": (
                f"Open requisitions older than "
                f"{CONFIG['stale_requisition_days']} days."
            ),
        })

    failed_total = sum(int(c["failedRecords"]) for c in checks)
    failed_pct = (failed_total / max(records, 1)) * 100

    if failed_pct == 0:
        rating = "good"
    elif failed_pct <= 10:
        rating = "fair"
    else:
        rating = "poor"

    return {
        "overallRating": rating,
        "dataPeriod": {
            "from": start_date.date().isoformat() if start_date is not None else None,
            "to": end_date.date().isoformat() if end_date is not None else None,
        },
        "recordsAnalysed": records,
        "checks": checks,
        "description": (
            "Data-quality assessment covering mandatory-field completeness, "
            "incomplete records, and staleness checks where applicable."
        ),
    }

# -------------------- Missing configuration ----------------------------
def resolve_metric_label(metric_name):
    """Resolve standard labels and compact JSON metric names to one canonical label."""
    supplied = norm(metric_name)
    for canonical in CONFIG["benchmarks_fallback"]:
        accepted = {
            norm(canonical),
            norm(fmt_metric_name(canonical)),
            norm(metric_pascal_case(canonical)),
        }
        if supplied in accepted:
            return canonical
    return str(metric_name or "").strip()


def configuration_schema_for_metric(metric_name, fallback_df=None):
    """Return columns from the exact source table(s) used by a metric formula.

    Schema detection intentionally uses the original input tables, even when they have
    zero rows, because configuration means column presence rather than cell completeness.
    """
    metric_name = resolve_metric_label(metric_name)
    source_map = {
        "Time to Hire (TTH)": ["apps"],
        "Offer Acceptance Rate": ["apps", "reqs"],
        "Applicant-to-Interview Conversion Rate": ["reqs", "apps"],
        "Requisition Aging": ["reqs"],
        "Source of Hire Effectiveness": ["apps"],
    }
    columns = []
    for source_name in source_map.get(metric_name, []):
        frame = globals().get(source_name)
        if isinstance(frame, pd.DataFrame):
            for column in frame.columns:
                if str(column) not in columns:
                    columns.append(str(column))

    # If the named sheet was not detected, retain the workbook's columns for diagnosis.
    # The field checks below remain source-specific, so a similarly named field on the
    # wrong sheet cannot falsely satisfy a metric's calculation requirements.
    if not columns:
        for frame in globals().get("company_sheets", {}).values():
            if isinstance(frame, pd.DataFrame):
                for column in frame.columns:
                    if str(column) not in columns:
                        columns.append(str(column))
    if not columns and isinstance(fallback_df, pd.DataFrame):
        columns = [str(c) for c in fallback_df.columns]
    return pd.DataFrame(columns=columns)


def missing_configurations_for_metric(df, metric_name, info=None):
    """Audit the exact source fields required by each RCM KPI formula.

    A metric is FieldMissing only if *none* of its supported calculation routes is
    available. The JSON lists absent source-column names (not internal alias keys).
    Missing alternative/optional columns are still listed in otherFieldsMissing.
    """
    metric_name = resolve_metric_label(metric_name)
    source_for_field = {
        "application_date": "apps",
        "requisition_created_date": "apps" if metric_name == "Time to Hire (TTH)" else "reqs",
        "interview_date": "apps",
        "offer_release_date": "apps",
        "offer_accepted_date": "apps",
        "filled_date": "reqs",
        "requisition_closed_date": "reqs",
        "joining_date": "apps",
        "application_status": "apps",
        "source": "apps",
        "requisition_status": "reqs",
        "open_flag": "reqs",
        "total_applicants": "reqs",
        "applicants_interviewed": "reqs",
        "offers_extended": "reqs",
        "offers_accepted": "reqs",
        "requisition_age_days": "reqs",
        "stored_tth": "apps",
    }
    canonical_names = {
        "application_date": "applicationDate",
        "requisition_created_date": "requisitionCreatedDate",
        "interview_date": "interviewDate",
        "offer_release_date": "offerReleaseDate",
        "offer_accepted_date": "offerAcceptedDate",
        "filled_date": "requisitionFilledDate",
        "requisition_closed_date": "requisitionClosedDate",
        "joining_date": "joiningDate",
        "application_status": "applicationStatus",
        "source": "source",
        "requisition_status": "requisitionStatus",
        "open_flag": "openFlag",
        "total_applicants": "totalApplicants",
        "applicants_interviewed": "applicantsInterviewed",
        "offers_extended": "offersExtended",
        "offers_accepted": "offersAccepted",
        "requisition_age_days": "requisitionAgeDays",
        "stored_tth": "timeToHireDays",
    }

    def actual_column(logical_name):
        source_name = source_for_field.get(logical_name)
        source_df = globals().get(source_name) if source_name else None
        if not isinstance(source_df, pd.DataFrame):
            return None
        return find_col(source_df, logical_name)

    def present(logical_name):
        return actual_column(logical_name) is not None

    # Each route represents a complete calculation method supported by compute_metrics().
    route_sets = {
        "Time to Hire (TTH)": [
            ["requisition_created_date", "offer_accepted_date"],
            ["stored_tth"],
        ],
        "Offer Acceptance Rate": [
            ["application_status"],
            ["offers_extended", "offers_accepted"],
        ],
        "Applicant-to-Interview Conversion Rate": [
            ["total_applicants", "applicants_interviewed"],
            ["application_date", "interview_date"],
        ],
        "Source of Hire Effectiveness": [
            ["source", "application_status"],
        ],
    }

    absent_mandatory = []
    if metric_name == "Requisition Aging":
        # Age can be derived from requisitionCreatedDate or read from requisitionAgeDays;
        # open status can come from requisitionStatus or openFlag.
        if not (present("requisition_created_date") or present("requisition_age_days")):
            absent_mandatory.extend(["requisition_created_date", "requisition_age_days"])
        if not (present("requisition_status") or present("open_flag")):
            absent_mandatory.extend(["requisition_status", "open_flag"])
    else:
        routes = route_sets.get(metric_name, [])
        if not any(all(present(field) for field in route) for route in routes):
            # No complete formula is possible: give all missing source inputs from the
            # alternative routes, so the user can see what must be configured.
            for route in routes:
                for logical_name in route:
                    if not present(logical_name):
                        absent_mandatory.append(logical_name)

    absent_mandatory = list(dict.fromkeys(absent_mandatory))

    # Expose all missing candidate source fields, even when one alternative route lets
    # the KPI run. Do not duplicate items that are already in mandatoryFieldsMissing.
    candidate_specs = {
        "Time to Hire (TTH)": ["requisition_created_date", "offer_accepted_date", "stored_tth", "application_date", "interview_date", "offer_release_date", "joining_date"],
        "Offer Acceptance Rate": ["application_status", "offer_release_date", "offers_extended", "offers_accepted", "offer_accepted_date", "application_date", "requisition_created_date"],
        "Applicant-to-Interview Conversion Rate": ["total_applicants", "applicants_interviewed", "application_date", "interview_date", "application_status"],
        "Requisition Aging": ["requisition_created_date", "requisition_age_days", "requisition_status", "open_flag", "filled_date", "requisition_closed_date", "application_status"],
        "Source of Hire Effectiveness": ["source", "application_status", "application_date", "joining_date", "requisition_created_date"],
    }
    mandatory_missing = [canonical_names[x] for x in absent_mandatory]
    other_missing = [
        canonical_names[x]
        for x in candidate_specs.get(metric_name, [])
        if not present(x) and x not in absent_mandatory
    ]

    required_present_specs = {
        "Time to Hire (TTH)": ["requisition_created_date", "offer_accepted_date", "stored_tth"],
        "Offer Acceptance Rate": ["application_status", "offers_extended", "offers_accepted", "offer_release_date"],
        "Applicant-to-Interview Conversion Rate": ["total_applicants", "applicants_interviewed", "application_date", "interview_date"],
        "Requisition Aging": ["requisition_created_date", "requisition_age_days", "requisition_status", "open_flag"],
        "Source of Hire Effectiveness": ["source", "application_status"],
    }.get(metric_name, [])
    mandatory_present = []
    for logical_name in required_present_specs:
        actual = actual_column(logical_name)
        if actual and actual not in mandatory_present:
            mandatory_present.append(actual)

    optional_present = []
    for logical_name in candidate_specs.get(metric_name, []):
        actual = actual_column(logical_name)
        if actual and actual not in optional_present:
            optional_present.append(actual)

    return {
        "mandatoryFieldsMissing": mandatory_missing,
        "normalFieldsMissing": list(dict.fromkeys(other_missing)),
        "mandatoryFieldsPresent": mandatory_present,
        "normalFieldsPresent": optional_present,
    }

def mandatory_fields_when_schema_unavailable(metric_name):
    """Conservative field names to show if a schema audit itself fails."""
    metric_name = resolve_metric_label(metric_name)
    fallback = {
        "Time to Hire (TTH)": ["requisitionCreatedDate", "offerAcceptedDate", "timeToHireDays"],
        "Offer Acceptance Rate": ["applicationStatus", "offersExtended", "offersAccepted"],
        "Applicant-to-Interview Conversion Rate": ["totalApplicants", "applicantsInterviewed", "applicationDate", "interviewDate"],
        "Requisition Aging": ["requisitionCreatedDate", "requisitionAgeDays", "requisitionStatus", "openFlag"],
        "Source of Hire Effectiveness": ["source", "applicationStatus"],
    }
    return fallback.get(metric_name, ["Metric calculation fields"])

def configuration_source_for_metric(metric_name, fallback_df=None, info=None):
    """Return the original source table used by this metric's calculation route.

    This deliberately does not return only the filtered metric result. Missing
    required source values must be visible even when downstream filtering removed
    those rows before the KPI report was assembled.
    """
    metric_name = resolve_metric_label(metric_name)
    info = info if isinstance(info, dict) else {}
    grain = str(info.get("grain", "")).lower()

    if metric_name == "Time to Hire (TTH)":
        source_df = globals().get("apps")
    elif metric_name == "Offer Acceptance Rate":
        source_df = globals().get("reqs") if "requisition count fallback" in grain else globals().get("apps")
    elif metric_name == "Applicant-to-Interview Conversion Rate":
        source_df = globals().get("apps") if "application proxy" in grain else globals().get("reqs")
    elif metric_name == "Requisition Aging":
        source_df = globals().get("reqs")
    elif metric_name == "Source of Hire Effectiveness":
        source_df = globals().get("apps")
    else:
        source_df = None

    if isinstance(source_df, pd.DataFrame) and len(source_df.columns) > 0:
        return source_df.copy()
    if isinstance(fallback_df, pd.DataFrame):
        return fallback_df.copy()
    return pd.DataFrame()


def mandatory_field_names_from_report(report, metric_name=None):
    """Collect mandatory metric-calculation fields from config, data-quality checks,
    and the raw source table. This runs both before serialization and immediately
    before the Supabase insert so a previous empty config cannot erase missing fields.
    """
    report = report if isinstance(report, dict) else {}
    metric = resolve_metric_label(metric_name or report.get("metricName", ""))
    cfg = report.get("missingConfigurations") or {}
    collected = []

    def add(value):
        if isinstance(value, dict):
            # For structured issues, extract the user-facing field name only.
            add(value.get("fieldName") or value.get("field"))
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
        elif value is not None and str(value).strip():
            name = str(value).strip()
            if name.lower() not in {"none", "null", "nan"}:
                collected.append(name)

    if isinstance(cfg, dict):
        add(cfg.get("mandatoryFieldsMissing", []))
        for issue in cfg.get("mandatoryDataIssues", []) or []:
            if isinstance(issue, dict) and str(issue.get("issue", "")).upper() in {
                "MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"
            }:
                add(issue.get("fieldName") or issue.get("fieldKey"))

    mandatory_candidates = {
        "Time to Hire (TTH)": {
            "requisitioncreateddate", "offeraccepteddate", "timetohiredays", "storedtth",
        },
        "Offer Acceptance Rate": {
            "offerreleasedate", "applicationstatus", "offersextended", "offersaccepted", "offeraccepteddate",
        },
        "Applicant-to-Interview Conversion Rate": {
            "totalapplicants", "applicantsinterviewed", "applicationdate", "interviewdate",
        },
        "Requisition Aging": {
            "requisitioncreateddate", "requisitionagedays", "requisitionstatus", "openflag",
        },
        "Source of Hire Effectiveness": {"source", "applicationstatus"},
    }.get(metric, set())

    dq = report.get("dataQuality") or {}
    checks = dq.get("checks", []) if isinstance(dq, dict) else []
    dedicated_mandatory_check_found = False
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        check_name = norm(check.get("checkName", ""))
        category = norm(check.get("category", ""))
        try:
            failed_records = int(float(check.get("failedRecords") or 0))
        except Exception:
            failed_records = 0
        try:
            failed_pct = float(check.get("failedPct") or 0)
        except Exception:
            failed_pct = 0.0
        if failed_records <= 0 and failed_pct <= 0:
            continue

        affected = check.get("affectedColumns")
        if check_name in {
            "mandatoryfieldsmissing", "mandatoryvaluesmissing", "mandatoryfieldvaluesmissing",
            "mandatoryconfigurationmissing", "essentialfieldsmissing",
        }:
            # A named mandatory-field check is direct evidence of a mandatory data gap.
            # Preserve its affected source-column names even if another stage omitted
            # or reset missingConfigurations.
            dedicated_mandatory_check_found = True
            add(affected)
            if not affected:
                # Recover the actual required source fields from the current workbook.
                try:
                    source_df = configuration_source_for_metric(metric, report.get("df"), report)
                    issues, _, _ = mandatory_data_quality_issues(source_df, metric, report)
                    for issue in issues:
                        if isinstance(issue, dict) and str(issue.get("issue", "")).upper() in {
                            "MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"
                        }:
                            add(issue.get("fieldName") or issue.get("fieldKey"))
                except Exception as audit_exc:
                    print(f"Mandatory-field source re-audit warning for {metric}: {audit_exc}")
            continue

        # A completeness check is often named generically (for example
        # "MissingValues"), while the actual missing field is listed in
        # affectedColumns. Inspect those columns directly; checking only whether
        # checkName equals a field name misses this common shape and incorrectly
        # leaves mandatoryFieldsMissing empty.
        if category == "completeness":
            affected_items = affected if isinstance(affected, (list, tuple, set)) else [affected]
            matched_mandatory = []
            for item in affected_items:
                if item is None:
                    continue
                item_name = str(item).strip()
                if norm(item_name) in mandatory_candidates:
                    matched_mandatory.append(item_name)
            if matched_mandatory:
                add(matched_mandatory)
            elif check_name in mandatory_candidates:
                # Some templates use the actual field name as checkName and omit
                # affectedColumns, so retain that supported representation too.
                add(affected if affected else check.get("checkName"))

    # If the dedicated mandatory check reports failures but has no affectedColumns,
    # run the metric-specific source-value audit to recover exact field names.
    if dedicated_mandatory_check_found and not collected:
        try:
            source_df = configuration_source_for_metric(metric, report.get("df"), report)
            issues, _, _ = mandatory_data_quality_issues(source_df, metric, report)
            for issue in issues:
                if isinstance(issue, dict) and str(issue.get("issue", "")).upper() in {
                    "MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"
                }:
                    add(issue.get("fieldName") or issue.get("fieldKey"))
        except Exception as audit_exc:
            print(f"Mandatory-field source re-audit warning for {metric}: {audit_exc}")

    # If a positive mandatory check carries no field names and source inspection is
    # also unavailable, fail closed instead of producing a Standard JSON with an
    # empty mandatoryFieldsMissing list.
    if dedicated_mandatory_check_found and not collected:
        collected.extend(mandatory_fields_when_schema_unavailable(metric))

    out = []
    seen = set()
    for field in collected:
        key = norm(field)
        if key and key not in seen:
            out.append(field)
            seen.add(key)
    return out


def has_missing_mandatory_configuration(report_or_config):
    """Return True when mandatory calculation inputs are absent or incomplete.

    Missing required values are included in missingConfigurations so the output uses
    the user's FieldMissing template and contains trendAnalysis: null. Staleness alone
    does not trigger FieldMissing.
    """
    cfg = (report_or_config.get("missingConfigurations", report_or_config)
           if isinstance(report_or_config, dict) else {})
    missing = cfg.get("mandatoryFieldsMissing", []) if isinstance(cfg, dict) else []
    return any(str(field).strip() for field in (missing or []))


def mandatory_data_quality_issues(df, metric_name, info=None):
    """Return mandatory calculation fields with missing values, plus stale-row info.

    FieldMissing reports use the actual source-column names in
    missingConfigurations.mandatoryFieldsMissing. Which source fields are required
    depends on the calculation route chosen by compute_metrics().
    """
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame()
    metric_name = resolve_metric_label(metric_name)
    info = info if isinstance(info, dict) else {}
    grain = str(info.get("grain", "")).lower()

    # Follow the actual metric formula rather than requiring every optional alias.
    required_columns = []
    if metric_name == "Time to Hire (TTH)":
        created = find_col(df, "requisition_created_date")
        accepted = find_col(df, "offer_accepted_date")
        stored = find_col(df, "stored_tth")
        if created and accepted:
            required_columns = [created, accepted]
        elif stored:
            required_columns = [stored]
    elif metric_name == "Offer Acceptance Rate":
        if "requisition count fallback" in grain:
            required_columns = [find_col(df, "offers_extended"), find_col(df, "offers_accepted")]
        else:
            # If offer release date exists, compute_metrics uses it to determine
            # whether an offer was extended; application status determines outcome.
            release_date = find_col(df, "offer_release_date")
            status = find_col(df, "application_status")
            required_columns = [release_date, status]
            required_columns = [c for c in required_columns if c]
    elif metric_name == "Applicant-to-Interview Conversion Rate":
        if "application proxy" in grain:
            required_columns = [find_col(df, "application_date"), find_col(df, "interview_date")]
        else:
            required_columns = [find_col(df, "total_applicants"), find_col(df, "applicants_interviewed")]
    elif metric_name == "Requisition Aging":
        created = find_col(df, "requisition_created_date")
        age_days = find_col(df, "requisition_age_days")
        open_status = find_col(df, "requisition_status")
        open_flag = find_col(df, "open_flag")
        age_field = created or age_days
        status_field = open_status or open_flag
        required_columns = [age_field, status_field]
    elif metric_name == "Source of Hire Effectiveness":
        required_columns = [find_col(df, "source"), find_col(df, "application_status")]

    required_columns = list(dict.fromkeys(c for c in required_columns if c and c in df.columns))
    issues = []
    missing_rows = pd.Series(False, index=df.index)
    for col in required_columns:
        values = df[col]
        missing_mask = values.isna() | values.astype(str).str.strip().str.lower().isin({"", "nan", "none", "nat", "null"})
        if missing_mask.any():
            missing_rows |= missing_mask
            issues.append({
                "fieldKey": norm(col),
                "fieldName": str(col),
                "issue": "MANDATORY_VALUES_MISSING",
                "affectedRecords": int(missing_mask.sum()),
            })

    stale_count = 0
    date_cols = [c for c in df.columns if any(t in norm(c) for t in ["date", "datetime"]) ]
    date_series = []
    for col in date_cols:
        parsed = pd.to_datetime(df[col], errors="coerce").dropna()
        if not parsed.empty:
            date_series.extend(parsed.tolist())
    if date_series and len(df):
        latest = max(date_series)
        cutoff = latest - pd.DateOffset(months=3)
        record_dates = pd.DataFrame(index=df.index)
        for col in date_cols:
            record_dates[col] = pd.to_datetime(df[col], errors="coerce")
        row_latest = record_dates.max(axis=1)
        complete = ~missing_rows
        stale_mask = complete & row_latest.notna() & (row_latest < cutoff)
        stale_count = int(stale_mask.sum())
        if stale_count:
            issues.append({
                "fieldKey": "record_freshness",
                "fieldName": "Stale records",
                "issue": "STALE_RECORDS",
                "affectedRecords": stale_count,
                "staleCutoff": cutoff.date().isoformat(),
            })
    return issues, int(missing_rows.sum()), stale_count


# ------------------------- Model accuracy ------------------------------
def build_model_accuracy(reg_result, rca_prediction_result, monthly):
    # Existing 3-model training/test winner.
    training_models = []
    for r in reg_result.get("all_results", []) if reg_result else []:
        training_models.append({
            "modelName": r.get("name"),
            "trainR2": json_safe(r.get("train_r2")),
            "validationR2": json_safe(r.get("validation_r2")),
            "testR2": json_safe(r.get("test_r2")),
            "validationMAE": json_safe(r.get("validation_mae")),
            "testMAE": json_safe(r.get("test_mae")),
            "testRMSE": json_safe(r.get("test_rmse")),
            "generalizationGap": json_safe(r.get("gap")),
            "status": r.get("fit_status"),
        })

    # Prediction-stage RCA model selected from the three-model RCA comparison.
    rca_model = {
        "modelName": rca_prediction_result.get("modelName", "Not run"),
        "r2": rca_prediction_result.get("r2"),
        "mae": rca_prediction_result.get("mae"),
        "rmse": rca_prediction_result.get("rmse"),
        "rating": rca_prediction_result.get("rating"),
    }

    # Forecast model selected from the two forecast candidates.
    forecast_info = globals().get("FORECAST_MODEL_RESULT", {}) or {}
    forecast_model = {
        "modelName": forecast_info.get("modelName", "Not run"),
        "r2": json_safe(forecast_info.get("r2")),
        "mae": json_safe(forecast_info.get("mae")),
        "rmse": json_safe(forecast_info.get("rmse")),
        "rating": forecast_info.get("rating", "not-available"),
    }

    return {
        "trainingModels": training_models,
        "selectedTrainingModel": (
            reg_result.get("winner") if reg_result else None
        ),
        "rcaModel": rca_model,
        "forecastModel": forecast_model,
        "description": (
            "The trainingModels section records the unchanged three-model "
            "training/testing stage. rcaModel and forecastModel are the "
            "separate prediction algorithms used for the final output."
        ),
    }

# --------------------- Detailed metric description ---------------------
def metric_description(metric_name):
    descriptions = {
        "Time to Hire (TTH)": (
            "Average number of days from requisition creation to offer acceptance. "
            "Lower values indicate faster hiring."
        ),
        "Offer Acceptance Rate": (
            "Percentage of extended offers that were accepted among decisions "
            "available in the source data. Higher values are better."
        ),
        "Applicant-to-Interview Conversion Rate": (
            "Percentage of applicants who progressed to interview. "
            "The configured benchmark determines the health interpretation."
        ),
        "Requisition Aging": (
            "Average age in days of currently open requisitions. "
            "Lower values indicate a healthier recruitment pipeline."
        ),
        "Source of Hire Effectiveness": (
            "Average hired-yield percentage across available recruitment sources. "
            "The result is compared with the configured industry reference."
        ),
    }
    return descriptions.get(metric_name, "")

# ------------------ Exact reference JSON schema ------------------
STANDARD_JSON_TOP_LEVEL_KEYS = [
    "generatedAt", "module", "reportVersion", "metricName", "unit", "higherIsBetter",
    "companyValue", "industryStandardValue", "healthState", "variance",
    "trendAnalysis", "forecast", "rca", "dataQuality", "selectedTrainingModel",
    "missingConfigurations"
]


def _schema_factor(factor, rank, total_impact):
    impact = factor.get("impactValue", factor.get("impact", factor.get("importance")))
    try:
        impact = float(impact) if impact is not None and np.isfinite(float(impact)) else None
    except Exception:
        impact = None
    pct = (impact / total_impact * 100.0) if impact is not None and total_impact > 0 else None
    avg = factor.get("avgFactorValue", factor.get("averageValue"))
    try:
        avg = float(avg) if avg is not None and np.isfinite(float(avg)) else None
    except Exception:
        avg = None
    return {"rank": int(rank), "factorName": str(factor.get("factorName", factor.get("feature", "Unknown"))),
            "avgFactorValue": json_safe(avg), "impactValue": json_safe(impact), "impactPct": json_safe(pct)}


def reference_data_quality_check(check, records_analysed=0):
    """Return a data-quality check using the field set shown for its check type in the reference JSON."""
    check = check if isinstance(check, dict) else {}
    name = str(check.get("checkName", check.get("fieldName", "DataQualityCheck")))
    category = str(check.get("category", "Completeness"))
    normalized_name = norm(name)
    failed_records = check.get("failedRecords", check.get("affectedRecords", 0))
    try:
        failed_records = int(float(failed_records or 0))
    except (TypeError, ValueError):
        failed_records = 0
    failed_pct = check.get("failedPct")
    if failed_pct is None:
        try:
            denominator = int(check.get("checkedRecords", records_analysed) or 0)
            failed_pct = (failed_records / denominator * 100.0) if denominator else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            failed_pct = None
    common = {
        "checkName": name,
        "category": category,
    }
    if normalized_name in {"missingvalues", "mandatoryfieldsmissing", "mandatoryvaluesmissing", "mandatoryfieldvaluesmissing", "incompleterecords"}:
        return {
            **common,
            "failedRecords": failed_records,
            "failedPct": json_safe(failed_pct),
            "affectedColumns": check.get("affectedColumns"),
            "affectedCells": check.get("affectedCells"),
        }
    if normalized_name == "staleness" or "stale" in normalized_name or norm(category) == "staleness":
        return {
            **common,
            "checkedRecords": int(check.get("checkedRecords", records_analysed) or 0),
            "failedRecords": failed_records,
            "failedPct": json_safe(failed_pct),
            "affectedColumns": check.get("affectedColumns"),
            "staleRange": check.get("staleRange"),
        }
    return {
        **common,
        "checkedRecords": int(check.get("checkedRecords", records_analysed) or 0),
        "failedRecords": failed_records,
        "failedPct": json_safe(failed_pct),
        "affectedColumns": check.get("affectedColumns"),
    }


def validate_reference_data_quality_check(check):
    """Validate check-specific keys without adding fields absent from the reference example."""
    name = norm(check.get("checkName", ""))
    category = norm(check.get("category", ""))
    if name in {"missingvalues", "mandatoryfieldsmissing", "mandatoryvaluesmissing", "mandatoryfieldvaluesmissing", "incompleterecords"}:
        expected = ["checkName", "category", "failedRecords", "failedPct", "affectedColumns", "affectedCells"]
    elif name == "staleness" or "stale" in name or category == "staleness":
        expected = ["checkName", "category", "checkedRecords", "failedRecords", "failedPct", "affectedColumns", "staleRange"]
    else:
        expected = ["checkName", "category", "checkedRecords", "failedRecords", "failedPct", "affectedColumns"]
    if list(check.keys()) != expected:
        raise ValueError(f"Data-quality check schema mismatch for {check.get('checkName')}: {list(check.keys())}; expected {expected}")


def _to_reference_schema(report):
    """Serialize one report to the user's exact Standard/FieldMissing JSON contract."""
    report = json_clean(report if isinstance(report, dict) else {})
    raw_metric_name = report.get("metricName", "Metric")
    display_metric = resolve_metric_label(raw_metric_name)
    metric = metric_pascal_case(fmt_metric_name(display_metric))
    cfg = dict(report.get("missingConfigurations") or {})
    dq = report.get("dataQuality") or {}
    rca_old = report.get("rca") or {}
    model_acc = report.get("modelAccuracy") or {}

    # Re-audit source columns immediately before serialization. This is the source of
    # truth for absent mandatory inputs and the names that must appear in the output.
    try:
        schema_df = configuration_schema_for_metric(display_metric, report.get("df"))
        detected_cfg = missing_configurations_for_metric(schema_df, display_metric, report)
        mandatory_missing = list(detected_cfg.get("mandatoryFieldsMissing", []) or [])
        other_missing = list(detected_cfg.get("normalFieldsMissing", []) or [])
    except Exception as config_exc:
        print(f"Configuration audit failed for {display_metric}: {config_exc}")
        mandatory_missing = mandatory_fields_when_schema_unavailable(display_metric)
        other_missing = list(cfg.get("normalFieldsMissing", cfg.get("otherFieldsMissing", [])) or [])

    # Final recovery from report diagnostics. This must not depend on the earlier
    # metric loop having populated missingConfigurations correctly. In particular,
    # a dataQuality MandatoryFieldsMissing check with affectedColumns=['offerAcceptedDate']
    # is decisive evidence that this required calculation field is missing/incomplete.
    value_issues = list(cfg.get("mandatoryDataIssues", []) or [])
    field_name_candidates = mandatory_field_names_from_report(report, display_metric)

    # IMPORTANT: audit actual source values as well as column names. The previous
    # version mainly checked whether a column existed in the workbook schema. If the
    # column existed but its required values were blank, the report could still be
    # classified as Standard and the old-looking JSON would be uploaded again.
    # Run the metric-specific audit immediately before schema selection so any
    # mandatory field with missing values forces the FieldMissing template.
    try:
        mandatory_source_df = configuration_source_for_metric(
            display_metric, report.get("df"), report
        )
        source_value_issues, _, _ = mandatory_data_quality_issues(
            mandatory_source_df, display_metric, report
        )
        for issue in source_value_issues:
            if not isinstance(issue, dict):
                continue
            issue_type = str(issue.get("issue", "")).upper()
            if issue_type in {
                "MANDATORY_VALUES_MISSING",
                "MANDATORY_FIELD_UNAVAILABLE",
                "MANDATORY_FIELD_MISSING",
            }:
                value_issues.append(issue)
                field_name = issue.get("fieldName") or issue.get("fieldKey")
                if field_name:
                    field_name_candidates.append(str(field_name).strip())
    except Exception as audit_exc:
        print(f"Mandatory source-value audit warning for {display_metric}: {audit_exc}")

    # Normalize and de-duplicate source-value issue fields before the final mode
    # decision. Stale-record issues are deliberately excluded: staleness by itself
    # does not mean a mandatory calculation field is missing.
    field_name_candidates = list(dict.fromkeys(
        str(name).strip() for name in field_name_candidates
        if name is not None and str(name).strip()
    ))
    # Hard assertion against the exact regression reported by the user: a positive
    # dataQuality.MandatoryFieldsMissing check cannot be converted into Standard JSON.
    for dq_check in (dq.get("checks", []) if isinstance(dq, dict) else []):
        if not isinstance(dq_check, dict) or norm(dq_check.get("checkName", "")) != "mandatoryfieldsmissing":
            continue
        try:
            has_failures = int(float(dq_check.get("failedRecords") or 0)) > 0 or float(dq_check.get("failedPct") or 0) > 0
        except Exception:
            has_failures = False
        if has_failures and not field_name_candidates:
            # First re-check current source values; only use conservative schema names
            # if the source audit itself cannot identify a field.
            try:
                source_df = configuration_source_for_metric(display_metric, report.get("df"), report)
                raw_issues, _, _ = mandatory_data_quality_issues(source_df, display_metric, report)
                field_name_candidates.extend(
                    str(issue.get("fieldName") or issue.get("fieldKey"))
                    for issue in raw_issues
                    if isinstance(issue, dict)
                    and str(issue.get("issue", "")).upper() in {"MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"}
                    and (issue.get("fieldName") or issue.get("fieldKey"))
                )
            except Exception as audit_exc:
                print(f"Final mandatory field recovery warning for {display_metric}: {audit_exc}")
            if not field_name_candidates:
                field_name_candidates.extend(mandatory_fields_when_schema_unavailable(display_metric))
    # A mandatory-data issue generated earlier in the metric loop is also direct
    # evidence. Recover its source field name even if an intermediate config object
    # was rebuilt or missingConfigurations was reset.
    issue_field_names = []
    for issue in value_issues:
        if isinstance(issue, dict) and str(issue.get("issue", "")).upper() in {
            "MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"
        }:
            field_name = issue.get("fieldName") or issue.get("fieldKey")
            if field_name:
                issue_field_names.append(str(field_name).strip())
    # Do not lose a mandatory-field list that was already produced by the
    # metric-processing stage. This is an explicit final merge (in addition to the
    # data-quality/source audits above) because the report is converted to the public
    # schema after some internal branches have short-circuited.
    original_mandatory_missing = cfg.get("mandatoryFieldsMissing", []) if isinstance(cfg, dict) else []
    if not isinstance(original_mandatory_missing, (list, tuple, set)):
        original_mandatory_missing = [original_mandatory_missing]
    mandatory_missing = list(dict.fromkeys(
        [str(x).strip() for x in mandatory_missing if x is not None and str(x).strip()]
        + [str(x).strip() for x in original_mandatory_missing if x is not None and str(x).strip()]
        + field_name_candidates
        + issue_field_names
    ))
    mandatory_norms = {norm(x) for x in mandatory_missing}
    other_missing = [
        str(x).strip() for x in other_missing
        if x is not None and str(x).strip() and norm(x) not in mandatory_norms
    ]
    # A data-missing report with missing-configuration entries must not fall through
    # to the Standard trend object merely because an earlier stage placed the field in
    # normalFieldsMissing/otherFieldsMissing instead of mandatoryFieldsMissing. When
    # the metric has already been marked DATA_MISSING, promote those visible entries
    # into the FieldMissing contract. Do not do this for healthy reports, where those
    # entries can simply be optional alternative fields.
    if str(report.get("dataStatus", "")).upper() == "DATA_MISSING" and not mandatory_missing:
        visible_config_missing = []
        for key in ("mandatoryFieldsMissing", "normalFieldsMissing", "otherFieldsMissing"):
            values = cfg.get(key, []) if isinstance(cfg, dict) else []
            if not isinstance(values, (list, tuple, set)):
                values = [values]
            visible_config_missing.extend(
                str(x).strip() for x in values if x is not None and str(x).strip()
            )
        mandatory_missing = list(dict.fromkeys(visible_config_missing))

    field_missing = has_missing_mandatory_configuration({"mandatoryFieldsMissing": mandatory_missing})
    # Missing required values are treated exactly like a missing mandatory field.
    # A non-empty diagnostic list must never be downgraded to Standard JSON.
    mandatory_value_gap = any(
        isinstance(issue, dict) and str(issue.get("issue", "")).upper() in {
            "MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"
        }
        for issue in value_issues
    )
    if mandatory_value_gap and not mandatory_missing:
        mandatory_missing = list(dict.fromkeys(
            str(issue.get("fieldName") or issue.get("fieldKey")).strip()
            for issue in value_issues
            if isinstance(issue, dict)
            and str(issue.get("issue", "")).upper() in {
                "MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"
            }
            and (issue.get("fieldName") or issue.get("fieldKey"))
        ))
        field_missing = bool(mandatory_missing)
    blocked_by_values = bool(value_issues or report.get("dataStatus") == "DATA_MISSING")
    blocked = field_missing or blocked_by_values
    if field_name_candidates:
        print(
            f"Mandatory metric-calculation fields missing for {metric}: "
            + ", ".join(dict.fromkeys(field_name_candidates))
            + ". Selecting FieldMissing JSON and setting trendAnalysis=null."
        )

    forecast_old = report.get("forecast") or {}
    if field_missing:
        forecast = {"applicable": False, "status": "Data Missing",
                    "message": "Forecast was not performed because mandatory fields required for this metric calculation are missing."}
        rca = {"applicable": False, "status": "Data Missing",
               "message": "RCA was not performed because mandatory fields required for this metric calculation are missing.",
               "breachValue": None, "factors": []}
        rca_model = {"status": "Data Missing", "trainingPerformed": False}
        forecast_model = {"status": "Data Missing", "trainingPerformed": False}
        # FieldMissing template: this value must be JSON null, not an absent key or object.
        trend = None
    elif blocked:
        forecast = {
            "nextMonth": {"period": None, "predictedValue": None, "lowerBound": None, "upperBound": None, "predictedHealthState": "not-computable"},
            "nextQuarter": {"period": None, "predictedValue": None, "lowerBound": None, "upperBound": None, "predictedHealthState": "not-computable"},
            "nextYear": {"period": None, "predictedValue": None, "lowerBound": None, "upperBound": None, "predictedHealthState": "not-computable"},
        }
        rca = {"applicable": False, "breachValue": None, "factors": []}
        rca_model = {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}
        forecast_model = {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"}
        trend = {"direction": "unknown", "granularity": "yearly", "periods": []}
    else:
        forecast = {}
        for key in ("nextMonth", "nextQuarter", "nextYear"):
            node = forecast_old.get(key) if isinstance(forecast_old, dict) else None
            if not isinstance(node, dict):
                node = {}
            forecast[key] = {"period": node.get("period"), "predictedValue": json_safe(node.get("predictedValue")),
                             "lowerBound": json_safe(node.get("lowerBound")), "upperBound": json_safe(node.get("upperBound")),
                             "predictedHealthState": node.get("predictedHealthState", "not-computable")}
        raw_factors = list(rca_old.get("factors", [])) if isinstance(rca_old, dict) else []
        raw_impacts = []
        for factor in raw_factors:
            try:
                impact = factor.get("impactValue", factor.get("importance", factor.get("impact")))
                raw_impacts.append(abs(float(impact)) if impact is not None and np.isfinite(float(impact)) else 0.0)
            except Exception:
                raw_impacts.append(0.0)
        total_impact = float(sum(raw_impacts))
        factors = [_schema_factor(factor, index + 1, total_impact) for index, factor in enumerate(raw_factors)]
        rca = {"applicable": bool(rca_old.get("applicable", bool(factors))),
               "breachValue": json_safe(rca_old.get("breachValue")), "factors": factors}
        trend = report.get("trendAnalysis")
        if not isinstance(trend, dict):
            trend = {"direction": "unknown", "granularity": "yearly", "periods": []}
        else:
            trend = dict(trend)
            trend.setdefault("direction", "unknown")
            trend.setdefault("granularity", "yearly")
            trend.setdefault("periods", [])
        rca_model_old = model_acc.get("rcaModel", {}) if isinstance(model_acc, dict) else {}
        forecast_model_old = model_acc.get("forecastModel", {}) if isinstance(model_acc, dict) else {}
        rca_model = {"modelName": rca_model_old.get("modelName", "Not run"),
                     "r2": json_safe(rca_model_old.get("r2")), "mae": json_safe(rca_model_old.get("mae")),
                     "rmse": json_safe(rca_model_old.get("rmse")), "rating": rca_model_old.get("rating", "Unavailable")}
        forecast_model = {"modelName": forecast_model_old.get("modelName", "Not run"),
                          "r2": json_safe(forecast_model_old.get("r2")), "mae": json_safe(forecast_model_old.get("mae")),
                          "rmse": json_safe(forecast_model_old.get("rmse")), "rating": forecast_model_old.get("rating", "Unavailable")}

    checks = []
    old_checks = dq.get("checks", []) if isinstance(dq, dict) else []
    for check in old_checks if isinstance(old_checks, list) else []:
        if isinstance(check, dict):
            checks.append(reference_data_quality_check(check, dq.get("recordsAnalysed", 0)))

    for issue in value_issues:
        if not isinstance(issue, dict):
            continue
        checks.append(reference_data_quality_check({
            "checkName": str(issue.get("fieldName", issue.get("fieldKey", "MandatoryDataIssue"))),
            "category": "Staleness" if "STALE" in str(issue.get("issue", "")).upper() else "Completeness",
            "checkedRecords": dq.get("recordsAnalysed", 0),
            "failedRecords": int(issue.get("affectedRecords", 0) or 0),
            "failedPct": json_safe(issue.get("affectedPct")),
            "affectedColumns": [issue.get("fieldName")] if issue.get("fieldName") else None,
            "affectedCells": None,
            "staleRange": issue.get("staleCutoff"),
        }, dq.get("recordsAnalysed", 0)))

    dq_period = (dq.get("dataPeriod") or {"from": None, "to": None}) if isinstance(dq, dict) else {"from": None, "to": None}
    data_quality = {"overallRating": dq.get("overallRating", "not-available") if isinstance(dq, dict) else "not-available",
                    "dataPeriod": {"from": dq_period.get("from"), "to": dq_period.get("to")},
                    "recordsAnalysed": int(dq.get("recordsAnalysed", 0) or 0) if isinstance(dq, dict) else 0,
                    "checks": checks}

    # The FieldMissing JSON explicitly lists the missing source fields for calculating
    # this metric. Do not leave this list empty when the schema audit found absent fields.
    # Use the current source-schema audit so field lists reflect the workbook for this run.
    other_missing_source = other_missing
    missing_configs = {
        "mandatoryFieldsMissing": mandatory_missing,
        "otherFieldsMissing": list(dict.fromkeys(str(x).strip() for x in other_missing_source if x is not None and str(x).strip())),
    }

    report_variance = report.get("variance") or {"value": None, "percentage": None}
    company_value = None if blocked else report.get("companyValue")
    industry_value = None if blocked else report.get("industryStandardValue")
    variance = {"value": None, "percentage": None} if blocked else {
        "value": json_safe(report_variance.get("value")),
        "percentage": json_safe(report_variance.get("percentage")),
    }
    result = {
        "generatedAt": report.get("generatedAt") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "module": SUPABASE_MODULE_NAME,
        "reportVersion": REPORT_VERSION,
        "metricName": metric,
        "unit": report.get("unit"),
        "higherIsBetter": None if field_missing else bool(report.get("higherIsBetter", False)),
        "companyValue": json_safe(company_value),
        "industryStandardValue": json_safe(industry_value),
        "healthState": None if field_missing else ("Data Missing" if blocked else report.get("healthState", "not-computable")),
        "variance": variance,
        # This key is a mandatory part of both schemas. FieldMissing uses explicit null.
        "trendAnalysis": None if field_missing else trend,
        "forecast": forecast,
        "rca": rca,
        "dataQuality": data_quality,
        "selectedTrainingModel": {"rcaModel": rca_model, "forecastModel": forecast_model},
        "missingConfigurations": missing_configs,
    }
    result = json_clean(result)

    # FINAL TEMPLATE ENFORCEMENT. This is deliberately done after assembling the JSON,
    # so later branches cannot accidentally omit trendAnalysis or overwrite it with an
    # object. FieldMissing is used only when the KPI's mandatory configuration inputs
    # are absent from the source schema.
    result["missingConfigurations"] = {
        "mandatoryFieldsMissing": list(mandatory_missing),
        "otherFieldsMissing": list(missing_configs["otherFieldsMissing"]),
    }
    if field_missing:
        result["higherIsBetter"] = None
        result["companyValue"] = None
        result["industryStandardValue"] = None
        result["healthState"] = None
        result["variance"] = {"value": None, "percentage": None}
        result["trendAnalysis"] = None
        result["forecast"] = {
            "applicable": False,
            "status": "Data Missing",
            "message": "Forecast was not performed because essential metric data is incomplete.",
        }
        result["rca"] = {
            "applicable": False,
            "status": "Data Missing",
            "message": "RCA was not performed because essential metric data is incomplete.",
            "breachValue": None,
            "factors": [],
        }
        result["selectedTrainingModel"] = {
            "rcaModel": {"status": "Data Missing", "trainingPerformed": False},
            "forecastModel": {"status": "Data Missing", "trainingPerformed": False},
        }
    else:
        if not isinstance(result.get("trendAnalysis"), dict):
            result["trendAnalysis"] = {"direction": "unknown", "granularity": "yearly", "periods": []}

    # Rebuild using the reference's exact top-level order. In particular, the key must
    # exist between variance and forecast, even when the required value is JSON null.
    result = {key: result.get(key) for key in STANDARD_JSON_TOP_LEVEL_KEYS}
    if "trendAnalysis" not in result:
        raise ValueError("Required key trendAnalysis is missing from generated JSON")

    # Validate the actual JSON serialization, not only the Python dictionary.
    serialized_result = json.dumps(result, ensure_ascii=False, allow_nan=False)
    roundtrip_result = json.loads(serialized_result)
    if field_missing and '"trendAnalysis": null' not in serialized_result:
        raise ValueError("FieldMissing JSON must serialize exactly with \"trendAnalysis\": null")
    if field_missing and not roundtrip_result["missingConfigurations"]["mandatoryFieldsMissing"]:
        raise ValueError("FieldMissing JSON requires missing metric-calculation field names")
    result = roundtrip_result

    expected_nested = {
        "variance": ["value", "percentage"],
        "forecast": (["applicable", "status", "message"] if field_missing else ["nextMonth", "nextQuarter", "nextYear"]),
        "rca": (["applicable", "status", "message", "breachValue", "factors"] if field_missing else ["applicable", "breachValue", "factors"]),
        "dataQuality": ["overallRating", "dataPeriod", "recordsAnalysed", "checks"],
        "dataQuality.dataPeriod": ["from", "to"],
        "selectedTrainingModel": ["rcaModel", "forecastModel"],
        "selectedTrainingModel.rcaModel": (["status", "trainingPerformed"] if field_missing else ["modelName", "r2", "mae", "rmse", "rating"]),
        "selectedTrainingModel.forecastModel": (["status", "trainingPerformed"] if field_missing else ["modelName", "r2", "mae", "rmse", "rating"]),
        "missingConfigurations": ["mandatoryFieldsMissing", "otherFieldsMissing"],
    }
    for path, expected in expected_nested.items():
        obj = result
        for part in path.split("."):
            obj = obj.get(part, {}) if isinstance(obj, dict) else {}
        if isinstance(obj, dict) and list(obj.keys()) != expected:
            raise ValueError(f"JSON schema mismatch at {path}: {list(obj.keys())}; expected {expected}")
    for node in result.get("forecast", {}).values() if not field_missing else []:
        expected_forecast_keys = ["period", "predictedValue", "lowerBound", "upperBound", "predictedHealthState"]
        if isinstance(node, dict) and list(node.keys()) != expected_forecast_keys:
            raise ValueError(f"JSON schema mismatch in forecast node: {list(node.keys())}")
    for factor in result.get("rca", {}).get("factors", []):
        if list(factor.keys()) != ["rank", "factorName", "avgFactorValue", "impactValue", "impactPct"]:
            raise ValueError(f"RCA factor schema mismatch: {list(factor.keys())}")
    for check in result.get("dataQuality", {}).get("checks", []):
        validate_reference_data_quality_check(check)

    if field_missing:
        if result["trendAnalysis"] is not None:
            raise ValueError("FieldMissing template requires the trendAnalysis key to be present and null")
        if not result["missingConfigurations"]["mandatoryFieldsMissing"]:
            raise ValueError("FieldMissing template requires at least one missing mandatory field name")
    else:
        if not isinstance(result["trendAnalysis"], dict):
            raise ValueError("Standard template requires trendAnalysis to be an object")
    return result

def build_fallback_internal_report(metric_name, info=None, error=None):
    """Build a schema-ready report even when a metric cannot be fully calculated."""
    info = info if isinstance(info, dict) else {}
    df = info.get("df")
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame()
    target = info.get("target")
    unit = info.get("unit") or {
        "Time to Hire (TTH)": "days",
        "Offer Acceptance Rate": "percent",
        "Applicant-to-Interview Conversion Rate": "percent",
        "Requisition Aging": "days",
        "Source of Hire Effectiveness": "percent",
    }.get(metric_name, "not-available")

    try:
        config_df = configuration_source_for_metric(metric_name, df, info)
        config_schema_df = configuration_schema_for_metric(metric_name, df)
        cfg = missing_configurations_for_metric(config_schema_df, metric_name, info)
    except Exception as config_exc:
        # Fail closed: an unavailable schema is treated as absent mandatory fields,
        # and the exact user-facing field names are listed in FieldMissing JSON.
        print(f"Configuration audit warning for {metric_name}: {config_exc}")
        config_df = pd.DataFrame()
        config_schema_df = pd.DataFrame()
        cfg = missing_configurations_for_metric(config_schema_df, metric_name, info)
    try:
        value_check_df = df if isinstance(df, pd.DataFrame) and len(df.columns) else config_df
        value_issues, incomplete_count, stale_count = mandatory_data_quality_issues(value_check_df, metric_name, info)
    except Exception:
        value_issues, incomplete_count, stale_count = [], 0, 0
    cfg["mandatoryDataIssues"] = value_issues
    value_missing_names = [
        str(issue.get("fieldName")).strip()
        for issue in value_issues
        if isinstance(issue, dict)
        and str(issue.get("issue", "")).upper() in {"MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"}
        and issue.get("fieldName")
    ]
    cfg["mandatoryFieldsMissing"] = list(dict.fromkeys(
        list(cfg.get("mandatoryFieldsMissing", []) or []) + value_missing_names
    ))
    cfg.setdefault("normalFieldsMissing", cfg.get("otherFieldsMissing", []))
    cfg.setdefault("mandatoryFieldsPresent", [])
    cfg.setdefault("normalFieldsPresent", [])

    try:
        dq = build_data_quality(df, info, metric_name)
    except Exception:
        start_date, end_date = date_range_for_df(df) if isinstance(df, pd.DataFrame) else (None, None)
        dq = {
            "overallRating": "poor" if df.empty else "not-available",
            "dataPeriod": {
                "from": start_date.date().isoformat() if start_date is not None else None,
                "to": end_date.date().isoformat() if end_date is not None else None,
            },
            "recordsAnalysed": int(len(df)), "checks": [],
        }
    dq["incompleteRecords"] = int(incomplete_count)
    dq["staleRecords"] = int(stale_count)

    benchmark = CONFIG.get("benchmarks_fallback", {}).get(metric_name)
    fallback_forecast = {
        key: {"period": None, "predictedValue": None, "lowerBound": None,
              "upperBound": None, "predictedHealthState": "not-computable"}
        for key in ("nextMonth", "nextQuarter", "nextYear")
    }
    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "module": "RCM", "reportVersion": REPORT_VERSION,
        "metricName": fmt_metric_name(metric_name), "unit": unit,
        "higherIsBetter": higher_is_better(metric_name),
        "companyValue": None, "industryStandardValue": json_safe(benchmark),
        "healthState": "not-computable",
        "variance": {"value": None, "percentage": None},
        "trendAnalysis": None,
        "forecast": fallback_forecast,
        "rca": {"applicable": False, "breachValue": None, "factors": []},
        "dataQuality": dq,
        "modelAccuracy": {
            "trainingModels": [], "selectedTrainingModel": None,
            "rcaModel": {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"},
            "forecastModel": {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"},
        },
        "missingConfigurations": cfg,
        "dataStatus": "DATA_MISSING" if cfg.get("mandatoryFieldsMissing") or value_issues else "DATA_AVAILABLE",
        "predictionStatus": {
            "forecastGenerated": False, "rcaGenerated": False,
            "status": "fallback-report",
            "message": f"A report was generated despite a processing error: {str(error)[:500]}" if error else "Metric was not computable from available data.",
        },
    }
    # Include a concise diagnostic in the console, not as an extra JSON top-level field.
    return json_clean(result)


# =====================================================================
# MAIN JSON REPORT GENERATION - ALL METRICS AUTOMATICALLY
# =====================================================================

# Process every RCM metric automatically, one after another.
# No metric selection/input is requested from the user.
AVAILABLE_METRICS = list(CONFIG["benchmarks_fallback"].keys())

print("\n" + "=" * 100)
print("RCM METRIC JSON GENERATOR - AUTOMATIC ALL-METRIC RUN")
print("=" * 100)
print("Company and industry workbooks are loaded from the configured Supabase Storage paths.")
print("All configured RCM metrics will now be processed continuously, one after another.")
print("Template rule: Standard JSON by default; FieldMissing when a required metric-calculation field is absent or has missing required values.")

all_json_reports = []

for metric_index, metric_name in enumerate(AVAILABLE_METRICS, 1):
    try:
        info = metric_data.get(metric_name, {"status": "not_computable: metric was not derived from available source data", "df": pd.DataFrame(), "target": None, "unit": None})

        print("\n\n" + "#" * 100)
        print(f"PROCESSING METRIC {metric_index}/{len(AVAILABLE_METRICS)}: {metric_name.upper()}")
        print("#" * 100)

        print("#" * 100)

        report = {
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "module": "RCM",
            "reportVersion": "2.2",
            "metricName": fmt_metric_name(metric_name),
            "description": metric_description(metric_name),
            "unit": info.get("unit"),
            "higherIsBetter": higher_is_better(metric_name),
            "companyValue": None,
            "industryStandardValue": None,
            "healthState": "not-computable",
            "variance": {
                "value": None,
                "percentage": None,
            },
            "trendAnalysis": {
                "direction": "unknown",
                "granularity": "yearly",
                "periods": [],
            },
            "forecast": {
                "nextMonth": {
                    "period": None,
                    "predictedValue": None,
                    "lowerBound": None,
                    "upperBound": None,
                    "predictedHealthState": "not-computable",
                },
                "nextQuarter": {
                    "period": None,
                    "predictedValue": None,
                    "lowerBound": None,
                    "upperBound": None,
                    "predictedHealthState": "not-computable",
                },
                "nextYear": {
                    "period": None,
                    "predictedValue": None,
                    "lowerBound": None,
                    "upperBound": None,
                    "predictedHealthState": "not-computable",
                },
            },
            "rca": {
                "applicable": False,
                "breachValue": None,
                "factors": [],
                "description": "",
            },
            "dataQuality": {
                "overallRating": "not-available",
                "dataPeriod": {
                    "from": None,
                    "to": None,
                },
                "recordsAnalysed": 0,
                "checks": [],
                "description": "",
            },
            "modelAccuracy": {
                "trainingModels": [],
                "selectedTrainingModel": None,
                "rcaModel": {
                    "modelName": "HistGradientBoostingRegressor",
                    "r2": None,
                    "mae": None,
                    "rmse": None,
                    "rating": "not-available",
                },
                "forecastModel": {
                    "modelName": "DampedTrend",
                    "r2": None,
                    "mae": None,
                    "rmse": None,
                    "rating": "not-available",
                },
            },
            "missingConfigurations": {
                "mandatoryFieldsMissing": [],
                "normalFieldsMissing": [],
                "mandatoryFieldsPresent": [],
                "normalFieldsPresent": [],
                "mandatoryDataIssues": [],
            },
            "dataStatus": "DATA_AVAILABLE",
            "predictionStatus": {
                "forecastGenerated": False,
                "rcaGenerated": False,
                "status": "not-started",
                "message": None,
            },
        }

        df = info.get("df", pd.DataFrame()).copy()
        target = info.get("target")
        date_col = info.get("date")

        # Determine whether mandatory CONFIGURATION COLUMNS exist before any
        # forecast/RCA call. Inspect the original source table, not just the derived
        # metric subset, because subsets can be empty or filtered.
        config_df = configuration_source_for_metric(metric_name, df, info)
        config_schema_df = configuration_schema_for_metric(metric_name, df)
        config_status = missing_configurations_for_metric(config_schema_df, metric_name, info)
        # Inspect the original source table for required-value gaps. The derived KPI
        # dataframe may already exclude rows with missing dates/statuses and would hide
        # the very field names the FieldMissing JSON must report.
        value_issues, incomplete_mandatory_records, stale_records = mandatory_data_quality_issues(
            config_df, metric_name, info
        )
        value_missing_names = [
            str(issue.get("fieldName")).strip()
            for issue in value_issues
            if isinstance(issue, dict)
            and str(issue.get("issue", "")).upper() in {"MANDATORY_VALUES_MISSING", "MANDATORY_FIELD_UNAVAILABLE", "MANDATORY_FIELD_MISSING"}
            and issue.get("fieldName")
        ]
        config_status["mandatoryFieldsMissing"] = list(dict.fromkeys(
            list(config_status.get("mandatoryFieldsMissing", []) or []) + value_missing_names
        ))
        # Keep diagnostics internally; the public JSON is normalized to the exact
        # two-key missingConfigurations schema before pushing to Supabase.
        config_status["mandatoryDataIssues"] = value_issues
        report["missingConfigurations"] = config_status
        if config_status.get("mandatoryFieldsMissing"):
            print("MANDATORY CONFIGURATION FIELDS MISSING:", ", ".join(config_status["mandatoryFieldsMissing"]))
        else:
            print("Mandatory configuration fields: present")
        if config_status.get("normalFieldsMissing"):
            print("Other optional fields missing:", ", ".join(config_status["normalFieldsMissing"]))
        report["dataQuality"] = build_data_quality(df, info, metric_name)
        report["dataQuality"]["incompleteRecords"] = int(df.isna().any(axis=1).sum()) if not df.empty else 0
        report["dataQuality"]["staleRecords"] = int(stale_records)

        if info.get("status", "").startswith("not_computable"):
            report["description"] += " Data is missing or the metric is not computable from the supplied data."
            report["dataStatus"] = "DATA_MISSING"
            report["predictionStatus"] = {
                "forecastGenerated": False,
                "rcaGenerated": False,
                "status": "data-missing",
                "message": "Data is missing. Forecast and RCA were not performed."
            }
            all_json_reports.append(report)
            print("Internal report staged; final schema conversion and contract validation occur before Supabase upload.")
            continue

        if df.empty or not target or target not in df.columns:
            report["description"] += " Data is missing because no valid metric target records were found."
            report["dataStatus"] = "DATA_MISSING"
            report["predictionStatus"] = {
                "forecastGenerated": False,
                "rcaGenerated": False,
                "status": "data-missing",
                "message": "Data is missing. Forecast and RCA were not performed."
            }
            all_json_reports.append(report)
            print("Internal report staged; final schema conversion and contract validation occur before Supabase upload.")
            continue

        mandatory_missing = report["missingConfigurations"]["mandatoryFieldsMissing"]

        if mandatory_missing:
            report["dataStatus"] = "DATA_MISSING"
            report["description"] += (
                " Data is missing because one or more mandatory fields are unavailable. "
                "RCA and forecast are intentionally not performed."
            )
            report["predictionStatus"] = {
                "forecastGenerated": False,
                "rcaGenerated": False,
                "status": "data-missing",
                "message": "Data is missing. Mandatory fields are unavailable, so forecast and RCA were not performed.",
            }
            # Do not calculate a potentially misleading company KPI, trend, forecast,
            # training-stage prediction result, or RCA from an invalid configuration.
            all_json_reports.append(json_clean(report))
            print("Internal report staged; final schema conversion and contract validation occur before Supabase upload.")
            continue

        # Match the completed onboarding module's strict data-quality gate:
        # mandatory value gaps or stale records block training, RCA, and forecasting.
        if value_issues:
            report["dataStatus"] = "DATA_MISSING"
            report["healthState"] = "Data Missing"
            report["description"] += (
                " Data is incomplete or stale in mandatory fields. Model training, RCA, "
                "and forecasting were not performed; this report will still be pushed to Supabase."
            )
            report["predictionStatus"] = {
                "forecastGenerated": False,
                "rcaGenerated": False,
                "status": "data-missing",
                "message": "Mandatory values are incomplete or records are stale. Forecast and RCA were not performed.",
            }
            report["forecast"] = {k: {"period": None, "predictedValue": None, "lowerBound": None, "upperBound": None, "predictedHealthState": "not-computable"} for k in ["nextMonth", "nextQuarter", "nextYear"]}
            report["rca"] = {"applicable": False, "status": "Data Missing", "breachValue": None, "factors": [], "description": "RCA was not performed because mandatory values are incomplete or stale records were detected."}
            report["modelAccuracy"] = {
                "trainingModels": [], "selectedTrainingModel": None,
                "rcaModel": {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"},
                "forecastModel": {"modelName": "Not run", "r2": None, "mae": None, "rmse": None, "rating": "Unavailable"},
            }
            report["trendAnalysis"] = {"direction": "unknown", "granularity": "yearly", "periods": []}
            report["companyValue"] = None
            report["variance"] = {"value": None, "percentage": None}
            report["industryStandardValue"] = None
            all_json_reports.append(json_clean(report))
            print("DATA QUALITY GATE: RCA, training, and forecasting skipped.")
            print("Internal report staged; final schema conversion and contract validation occur before Supabase upload.")
            continue

        yvals = pd.to_numeric(df[target], errors="coerce")

        # Company value: preserve the original metric logic.
        benchmark, benchmark_source = benchmark_for(metric_name)

        if metric_name == "Source of Hire Effectiveness" and info.get("source_col") in df.columns:
            per_source_rates = (
                df.assign(__target_numeric=yvals)
                .groupby(info["source_col"], dropna=False)["__target_numeric"]
                .mean()
            )
            company_value = float(per_source_rates.mean()) if len(per_source_rates) else np.nan

        elif metric_name == "Applicant-to-Interview Conversion Rate":
            total_col = find_col(df, "total_applicants")
            interviewed_col = find_col(df, "applicants_interviewed")

            if total_col and interviewed_col:
                total_n = pd.to_numeric(df[total_col], errors="coerce").sum(min_count=1)
                interviewed_n = pd.to_numeric(df[interviewed_col], errors="coerce").sum(min_count=1)
                company_value = (
                    float(interviewed_n / total_n * 100)
                    if pd.notna(total_n) and total_n > 0 else np.nan
                )
            else:
                company_value = float(yvals.mean()) if yvals.notna().any() else np.nan

        elif metric_name == "Offer Acceptance Rate" and info.get("grain") == "requisition count fallback":
            ext_col = find_col(df, "offers_extended")
            acc_col = find_col(df, "offers_accepted")
            ext_n = (
                pd.to_numeric(df[ext_col], errors="coerce").sum(min_count=1)
                if ext_col else np.nan
            )
            acc_n = (
                pd.to_numeric(df[acc_col], errors="coerce").sum(min_count=1)
                if acc_col else np.nan
            )
            company_value = (
                float(acc_n / ext_n * 100)
                if pd.notna(ext_n) and ext_n > 0 else np.nan
            )

        else:
            company_value = float(yvals.mean()) if yvals.notna().any() else np.nan

        # Variance.
        variance_value = (
            company_value - benchmark
            if np.isfinite(company_value) and np.isfinite(benchmark)
            else np.nan
        )
        variance_pct = (
            variance_value / benchmark * 100
            if np.isfinite(variance_value) and benchmark != 0
            else np.nan
        )

        report["companyValue"] = json_safe(company_value)
        report["industryStandardValue"] = json_safe(benchmark)
        report["industryBenchmarkSource"] = benchmark_source
        report["healthState"] = health_state_json(
            metric_name,
            company_value,
            benchmark
        )
        report["variance"] = {
            "value": json_safe(variance_value),
            "percentage": json_safe(variance_pct),
        }

        # ------------------------- Trend -------------------------
        monthly = monthly_series_for_metric(
            df, target, date_col, metric_name, info
        )

        report["trendAnalysis"] = build_hierarchical_trend(
            monthly,
            metric_name
        )

        # ------------------------ Forecast ------------------------
        report["forecast"] = build_forecast_json(
            monthly,
            metric_name,
            benchmark
        )

        # --------------------- Training lane ----------------------
        # UNCHANGED training logic result from evaluate_regression().
        target_components = []
        if metric_name == "Time to Hire (TTH)":
            target_components = [
                find_col(df, "offer_accepted_date"),
                find_col(df, "requisition_created_date"),
                find_col(df, "stored_tth"),
            ]
        elif metric_name == "Requisition Aging":
            target_components = [
                find_col(df, "requisition_created_date"),
                find_col(df, "requisition_age_days"),
            ]
        target_components = [c for c in target_components if c]

        X, y, selection_info = build_feature_frame(
            df,
            target,
            date_col,
            target_components
        )

        if X is None:
            reg_result = {
                "status": "insufficient_data",
                "winner": None,
                "all_results": [],
            }
        else:
            reg_result = evaluate_regression(
                X,
                y,
                metric_name
            )

        # ------------------ Prediction RCA lane ------------------
        # IMPORTANT: this is a separate prediction model and does not
        # replace or alter the three-model training/testing stage.
        rca_prediction_result = fit_prediction_rca_model(
            X,
            y,
            metric_name
        )

        report["rca"] = build_rca_json(
            df=df,
            target=target,
            metric_name=metric_name,
            info=info,
            rca_model_result=rca_prediction_result,
            company_value=company_value,
            benchmark=benchmark,
        )

        # -------------------- Data quality -------------------------
        report["dataQuality"] = build_data_quality(
            df,
            info,
            metric_name
        )

        # ---------------- Prediction status -----------------------
        # Reaching this point means all mandatory configuration fields are present.
        report["predictionStatus"] = {
            "forecastGenerated": True,
            "rcaGenerated": bool(report["rca"]["applicable"]),
            "status": "generated",
            "message": None,
        }

        # -------------------- Model accuracy -----------------------
        report["modelAccuracy"] = build_model_accuracy(
            reg_result,
            rca_prediction_result,
            monthly
        )

        # Detailed values that are useful to the UI/report consumer.
        report["metricDetails"] = {
            "recordsAvailable": int(len(df)),
            "validMetricRecords": int(yvals.notna().sum()),
            "metricDefinition": metric_description(metric_name),
            "grain": info.get("grain"),
            "benchmarkDirection": CONFIG["metric_directions"].get(metric_name),
            "selectedFeatures": (
                selection_info.get("selected", [])
                if isinstance(selection_info, dict)
                else []
            ),
            "excludedFeatures": (
                selection_info.get("dropped", {})
                if isinstance(selection_info, dict)
                else {}
            ),
        }

        report = json_clean(report)
        all_json_reports.append(report)

        print("\nInternal metric report assembled; final reference JSON will be printed at the Supabase boundary.")

    except Exception as metric_exc:
        print(f"\nERROR while processing {metric_name}: {metric_exc}")
        # Replace any partially assembled report for this metric with one valid fallback.
        all_json_reports = [r for r in all_json_reports if r.get("metricName") != fmt_metric_name(metric_name)]
        fallback_report = build_fallback_internal_report(metric_name, info, metric_exc)
        all_json_reports.append(fallback_report)
        print(f"Fallback JSON report generated for {metric_name}; processing will continue.")

# =====================================================================
# PUSH EACH METRIC JSON DIRECTLY TO SUPABASE (NO LOCAL JSON FILES)
# =====================================================================
if not all_json_reports:
    raise RuntimeError("No RCM JSON reports were generated.")

print("\n" + "=" * 100)
print("PUSHING ALL RCM METRIC REPORTS TO SUPABASE")
print("=" * 100)
print("JSON reports are sent directly to ML_Notebook_Insights in the exact reference schema.")
print(f"Build verification: {RCM_BUILD_ID}; the same build id is printed with each final JSON payload.")
print("No local JSON files are created and no downloads are triggered.")

supabase_results = []
upload_failures = []
for internal_report in all_json_reports:
    metric_label = internal_report.get("metricName", "Metric")
    try:
        report = _to_reference_schema(internal_report)
    except Exception as schema_exc:
        print(f"Schema mapping failed for {metric_label}: {schema_exc}. Building a fallback report.")
        canonical_metric = next((m for m in AVAILABLE_METRICS if metric_pascal_case(m) == metric_pascal_case(metric_label)), metric_label)
        report = _to_reference_schema(build_fallback_internal_report(canonical_metric, metric_data.get(canonical_metric), schema_exc))
    print("Validated strict JSON schema for:", report["metricName"])
    try:
        result = push_metric_json_to_supabase(report)
        supabase_results.append(result)
        print(f"Pushed: {report['metricName']} | execution_id={result.get('execution_id')} | created_at={result.get('created_at')}")
    except Exception as upload_exc:
        upload_failures.append({"metricName": report["metricName"], "error": str(upload_exc)})
        print(f"SUPABASE PUSH FAILED for {report['metricName']}: {upload_exc}")
        # Continue attempting the remaining metric reports.

print("\nRCM processing completed.")
print(f"Reports generated: {len(all_json_reports)}")
print(f"Reports successfully pushed to Supabase: {len(supabase_results)}")
print(f"Reports that failed to push: {len(upload_failures)}")
if upload_failures:
    print("Upload failures:")
    for failure in upload_failures:
        print(f" - {failure['metricName']}: {failure['error']}")
print("No JSON files were saved or downloaded locally.")
