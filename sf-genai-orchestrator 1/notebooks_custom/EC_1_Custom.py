# -*- coding: utf-8 -*-
"""
Employee Central (EC) Analytics Pipeline
Features: Supabase workbook ingestion, local JSON exports, leakage-safe RCA tuning
          with a holdout evaluation, SHAP analysis, Mann-Kendall trend auditing,
          and damped-vs-linear Holt forecast validation.
"""

import os
import io
import re
import json
import warnings
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
import shap
import pymannkendall as mk
from dotenv import load_dotenv
from supabase import create_client, Client
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# Suppress operational and framework warning arrays
warnings.filterwarnings('ignore')

# ==============================================================================
# PART 1: SECURE CONFIGURATION & CLOUD STORAGE INFRASTRUCTURE SETUP
# ==============================================================================
# Load environment credentials securely from local hidden files
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.ec"), override=True)

# ==============================================================================
# UNIFIED INITIALIZATION LAYER
# ==============================================================================
import os
from supabase import create_client, Client

# Extract configurations from your saved environment file parameters
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "SF_Health_Raw_Data")
CUSTOM_INSIGHTS_TABLE = os.getenv("CUSTOM_INSIGHTS_TABLE", "ML_Notebook_Custom_Insights")
FILE_PATH = os.getenv("METRIC_FILE_PATH", "SF_Dataset_USA1.xlsx")
OFB2_FILE_PATH = FILE_PATH
CUSTOM_STANDARDS_FILE_PATH = os.getenv("CUSTOM_STANDARDS_FILE_PATH", "SF Health Monitoring Custom Standards.xlsx")
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

supabase_client: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase client successfully initialized.")
    except Exception as e:
        print(f"⚠️ Supabase initialization failed: {e}")
else:
    print("ℹ️ Supabase credentials are not configured; local output requires local workbooks.")

# PART 2: LEAKAGE-FREE ML PROCESSORS & K-FOLD SELECTION TOURNAMENT
# ==============================================================================
def pipeline_feature_processor(clean_model_df, drop_features, whitelist_features=None):
    """Select raw features; all learned preprocessing is fitted inside each training fold."""
    if whitelist_features:
        available_features = [column for column in whitelist_features if column in clean_model_df.columns]
        X_raw = clean_model_df[available_features].copy()
    else:
        X_raw = clean_model_df.drop(columns=drop_features, errors='ignore')
    return X_raw

def select_best_model_cv(X, target_values, breach_labels, dates, benchmark_available=True):
    """Tune against benchmark breaches, falling back to a training-period median label if rare."""
    def choose_metric_threshold(values, min_per_class=1):
        values = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
        unique_values = np.sort(values.unique())
        median_value = float(values.median())
        candidate_thresholds = (unique_values[:-1] + unique_values[1:]) / 2.0
        viable = [
            float(threshold) for threshold in candidate_thresholds
            if min(int((values <= threshold).sum()), int((values > threshold).sum())) >= min_per_class
        ]
        return min(viable, key=lambda threshold: abs(threshold - median_value)) if viable else median_value

    date_values = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    order = np.argsort(date_values.to_numpy())
    X = X.iloc[order].reset_index(drop=True)
    target_values = pd.to_numeric(pd.Series(target_values).iloc[order], errors='coerce').reset_index(drop=True)
    breach_labels = pd.to_numeric(pd.Series(breach_labels).iloc[order], errors='coerce').fillna(0).astype(int).reset_index(drop=True)
    date_values = date_values.iloc[order].reset_index(drop=True)
    unique_dates = pd.Index(date_values.drop_duplicates())
    split_index = int(len(unique_dates) * 0.8)
    if split_index < 2 or len(unique_dates) - split_index < 1:
        raise ValueError("Not enough chronologically ordered records for RCA train/test evaluation.")

    # Keep records from the same timestamp together across every split.
    test_start_date = unique_dates[split_index]
    dev_mask = date_values < test_start_date
    test_mask = ~dev_mask
    dev_idx = np.flatnonzero(dev_mask.to_numpy())
    test_idx = np.flatnonzero(test_mask.to_numpy())
    X_dev, X_test = X.iloc[dev_idx], X.iloc[test_idx]
    target_dev, target_test = target_values.iloc[dev_idx], target_values.iloc[test_idx]
    breach_dev, breach_test = breach_labels.iloc[dev_idx], breach_labels.iloc[test_idx]
    dates_dev = date_values.iloc[dev_idx].reset_index(drop=True)
    use_benchmark_target = (
        benchmark_available and breach_dev.nunique() == 2
        and int(breach_dev.value_counts().min()) >= 5
    )
    if use_benchmark_target:
        y_dev, y_test = breach_dev, breach_test
        rca_label_source = "custom standards breach"
    else:
        # Keep RCA available when breaches are too rare or no benchmark is configured.
        fallback_threshold = choose_metric_threshold(target_dev, min_per_class=5)
        y_dev = (target_dev > fallback_threshold).astype(int)
        y_test = (target_test > fallback_threshold).astype(int)
        rca_label_source = "development-period outcome threshold fallback"
    if y_dev.nunique() < 2 or int(y_dev.value_counts().min()) < 5:
        raise ValueError("The metric has too little outcome variation to train a meaningful RCA model.")
    unique_dev_dates = pd.Index(dates_dev.drop_duplicates())
    if len(unique_dev_dates) < 4:
        raise ValueError("At least four distinct training dates are needed for chronological cross-validation.")
    cv = TimeSeriesSplit(n_splits=min(4, max(2, len(unique_dev_dates) // 4)))
    cv_splits = []
    for train_date_idx, valid_date_idx in cv.split(unique_dev_dates):
        train_dates = unique_dev_dates[train_date_idx]
        valid_dates = unique_dev_dates[valid_date_idx]
        train_idx = np.flatnonzero(dates_dev.isin(train_dates).to_numpy())
        valid_idx = np.flatnonzero(dates_dev.isin(valid_dates).to_numpy())
        cv_splits.append((train_idx, valid_idx))
    search_space = {
        "XGBClassifier": [
            {"n_estimators": 100, "max_depth": 3, "learning_rate": 0.05},
            {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.05},
        ],
        "LGBMClassifier": [
            {"n_estimators": 100, "max_depth": 4, "num_leaves": 15, "learning_rate": 0.05},
            {"n_estimators": 200, "max_depth": 5, "num_leaves": 31, "learning_rate": 0.05},
        ],
        "RandomForestClassifier": [
            {"n_estimators": 100, "max_depth": 4, "min_samples_leaf": 1},
            {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 3},
        ],
        "HistGradientBoostingClassifier": [
            {"max_iter": 100, "max_depth": 3, "learning_rate": 0.05, "l2_regularization": 1.0},
            {"max_iter": 200, "max_depth": 4, "learning_rate": 0.05, "l2_regularization": 0.0},
        ],
    }

    def build_model(name, params, y_train):
        spw = max(1, int((y_train == 0).sum())) / max(1, int((y_train == 1).sum()))
        if name == "XGBClassifier":
            return xgb.XGBClassifier(subsample=0.85, colsample_bytree=0.85, scale_pos_weight=spw,
                eval_metric="logloss", random_state=42, n_jobs=-1, **params)
        if name == "LGBMClassifier":
            return lgb.LGBMClassifier(class_weight="balanced", random_state=42, verbose=-1, n_jobs=-1, **params)
        if name == "RandomForestClassifier":
            return RandomForestClassifier(class_weight="balanced", random_state=42, n_jobs=-1, **params)
        return HistGradientBoostingClassifier(random_state=42, **params)

    def encode(train, valid):
        train, valid = train.copy(), valid.copy()
        train = train.replace([np.inf, -np.inf], np.nan)
        valid = valid.replace([np.inf, -np.inf], np.nan)
        # Numeric values sometimes arrive from Excel as strings. Convert a column
        # only when nearly all nonblank training values parse as numbers.
        for col in train.columns:
            if not pd.api.types.is_numeric_dtype(train[col]):
                nonblank = train[col].notna() & train[col].astype(str).str.strip().ne("")
                parsed = pd.to_numeric(train[col], errors="coerce")
                if nonblank.any() and parsed[nonblank].notna().mean() >= 0.9:
                    train[col] = parsed
                    valid[col] = pd.to_numeric(valid[col], errors="coerce")
        cats = [c for c in train.columns if not pd.api.types.is_numeric_dtype(train[c])]
        nums = [c for c in train.columns if pd.api.types.is_numeric_dtype(train[c])]
        if cats:
            train_cats = train[cats].fillna("<missing>").astype(str)
            valid_cats = valid[cats].fillna("<missing>").astype(str)
            train_encoded = pd.get_dummies(train_cats, prefix=cats, prefix_sep="=", dtype=float)
            valid_encoded = pd.get_dummies(valid_cats, prefix=cats, prefix_sep="=", dtype=float)
            valid_encoded = valid_encoded.reindex(columns=train_encoded.columns, fill_value=0.0)
            train = pd.concat([train.drop(columns=cats), train_encoded], axis=1)
            valid = pd.concat([valid.drop(columns=cats), valid_encoded], axis=1)
        for col in nums:
            median = train[col].median()
            fill = median if pd.notna(median) else -1
            train[col] = train[col].fillna(fill)
            valid[col] = valid[col].fillna(fill)
        train = train.apply(pd.to_numeric)
        valid = valid.apply(pd.to_numeric)
        # XGBoost rejects feature names containing brackets or angle brackets;
        # apply the same deterministic, collision-safe names to both matrices.
        safe_columns = []
        used_columns = set()
        for index, column in enumerate(train.columns):
            base = re.sub(r"[\[\]<>]", "_", str(column)).strip() or "feature"
            candidate = base
            suffix = 1
            while candidate in used_columns:
                candidate = f"{base}_{suffix}"
                suffix += 1
            safe_columns.append(candidate)
            used_columns.add(candidate)
        train.columns = safe_columns
        valid.columns = safe_columns
        return train, valid

    best = None
    for name, configs in search_space.items():
        for params in configs:
            scores = []
            auc_scores = []
            for train_idx, valid_idx in cv_splits:
                X_train, X_valid = encode(X_dev.iloc[train_idx], X_dev.iloc[valid_idx])
                if use_benchmark_target:
                    y_train = y_dev.iloc[train_idx]
                    y_valid = y_dev.iloc[valid_idx]
                else:
                    fold_threshold = choose_metric_threshold(target_dev.iloc[train_idx], min_per_class=1)
                    y_train = (target_dev.iloc[train_idx] > fold_threshold).astype(int)
                    y_valid = (target_dev.iloc[valid_idx] > fold_threshold).astype(int)
                if y_train.nunique() < 2:
                    continue
                try:
                    model = build_model(name, params, y_train)
                    model.fit(X_train, y_train)
                    scores.append(f1_score(y_valid, model.predict(X_valid), zero_division=0))
                    try:
                        positive_class_index = list(model.classes_).index(1)
                        auc_scores.append(roc_auc_score(
                            y_valid, model.predict_proba(X_valid)[:, positive_class_index]
                        ))
                    except (ValueError, IndexError):
                        pass  # Keep F1-based model selection if AUC is undefined in a fold.
                except Exception as e:
                    print(f"   ⚠️ RCA candidate {name} {params} failed: {e}")
                    scores = []
                    break
            if len(scores) >= 2:
                mean_f1 = float(np.mean(scores))
                if best is None or mean_f1 > best["cv_f1"]:
                    best = {
                        "name": name, "params": params, "cv_f1": mean_f1,
                        "cv_f1_scores": scores, "cv_auc_scores": auc_scores,
                    }
    if best is None:
        raise RuntimeError("All RCA parameter configurations failed during cross-validation.")

    # The latest chronological block remains untouched during parameter selection.
    X_dev_encoded, X_test_encoded = encode(X_dev, X_test)
    holdout_model = build_model(best["name"], best["params"], y_dev)
    holdout_model.fit(X_dev_encoded, y_dev)
    test_preds = holdout_model.predict(X_test_encoded)
    test_f1 = float(f1_score(y_test, test_preds, zero_division=0))
    train_f1 = float(f1_score(y_dev, holdout_model.predict(X_dev_encoded), zero_division=0))
    baseline_model = DummyClassifier(strategy="most_frequent")
    baseline_model.fit(X_dev_encoded, y_dev)
    baseline_preds = baseline_model.predict(X_test_encoded)
    baseline_f1 = float(f1_score(y_test, baseline_preds, zero_division=0))
    try:
        positive_class_index = list(holdout_model.classes_).index(1)
        test_auc = float(roc_auc_score(
            y_test, holdout_model.predict_proba(X_test_encoded)[:, positive_class_index]
        ))
    except (ValueError, IndexError):
        test_auc = None  # ROC AUC is undefined if the holdout contains only one class.

    cv_f1_std = float(np.std(best["cv_f1_scores"], ddof=1)) if len(best["cv_f1_scores"]) > 1 else 0.0
    cv_auc_mean = (
        float(np.mean(best["cv_auc_scores"]))
        if len(best["cv_auc_scores"]) == len(best["cv_f1_scores"])
        else None
    )
    # Heuristic: require both gaps to exceed two CV standard deviations and 0.05 F1.
    gap_threshold = max(0.05, 2.0 * cv_f1_std)
    train_cv_gap = train_f1 - best["cv_f1"]
    cv_test_gap = best["cv_f1"] - test_f1
    potential_overfit = train_cv_gap > gap_threshold and cv_test_gap > gap_threshold
    metrics_summary = {
        "modelName": best["name"], "bestParams": best["params"],
        "crossValidationF1": round(best["cv_f1"], 3),
        "accuracy": round(float(accuracy_score(y_test, test_preds)), 2),
        "precision": round(float(precision_score(y_test, test_preds, zero_division=0)), 2),
        "recall": round(float(recall_score(y_test, test_preds, zero_division=0)), 2),
        "f1_score": round(test_f1, 2),
        "evaluation": "chronological 20% holdout; expanding-window cross-validation",
        "rating": "excellent" if test_f1 > 0.85 else "good" if test_f1 > 0.7 else "fair",
    }
    auc_summary = (
        f"ROC AUC CV={cv_auc_mean:.3f}/holdout={test_auc:.3f}"
        if test_auc is not None and cv_auc_mean is not None
        else f"ROC AUC CV={cv_auc_mean}/holdout unavailable"
    )
    print(
        f"🏆 RCA [{rca_label_source}]: {best['name']}; F1 train/CV±SD/holdout="
        f"{train_f1:.3f}/{best['cv_f1']:.3f}±{cv_f1_std:.3f}/{test_f1:.3f}; "
        f"baseline={baseline_f1:.3f} ({'beats' if test_f1 > baseline_f1 else 'does not beat'}); "
        f"overfit={'potential' if potential_overfit else 'no strong signal'} "
        f"(gap threshold={gap_threshold:.3f}); {auc_summary}"
    )
    
    # Refit preprocessing and the selected model on all available history for SHAP.
    X_full_encoded, _ = encode(X, X)
    final_labels = breach_labels if use_benchmark_target else (
        target_values > choose_metric_threshold(target_values, min_per_class=1)
    ).astype(int)
    final_model = build_model(best["name"], best["params"], final_labels)
    final_model.fit(X_full_encoded, final_labels)
    
    return final_model, X_full_encoded, metrics_summary

# ==============================================================================
# PART 3: DATA QUALITY VALIDATION FIREWALL
# ==============================================================================
def validate_sheet_quality(workbook_obj, sheet_name, required_cols, metric_label):
    """Scans sheet coordinates and structural constraints before passing data blocks downstream."""
    print(f"🔍 [DQ Pre-Check] Validating structural integrity for: {metric_label}...")
    if sheet_name not in workbook_obj.sheet_names:
        return False, None, f"❌ DQ Failure: Target sheet '{sheet_name}' is missing from the workbook."
        
    try:
        preview_df = pd.read_excel(workbook_obj, sheet_name=sheet_name, nrows=5)
        preview_df.columns = preview_df.columns.str.strip()
    except Exception as e:
        return False, None, f"❌ DQ Failure: Unable to parse layout on sheet '{sheet_name}': {e}"
        
    missing_cols = [col for col in required_cols if col not in preview_df.columns]
    if missing_cols:
        return False, None, f"❌ DQ Failure: Required tracking headers missing in sheet '{sheet_name}': {missing_cols}"
        
    try:
        full_df = pd.read_excel(workbook_obj, sheet_name=sheet_name)
        full_df.columns = full_df.columns.str.strip()
    except Exception as e:
        return False, None, f"❌ DQ Failure: Failed loading complete matrix from sheet '{sheet_name}': {e}"
        
    if full_df.empty or len(full_df.dropna(subset=required_cols)) == 0:
        return False, None, f"❌ DQ Failure: Target sheet '{sheet_name}' has zero rows filled with valid target data."
        
    print(f"   🟢 Structural DQ Passed: Sheet '{sheet_name}' is healthy ({len(full_df)} records found).")
    return True, full_df, "Success"

def parse_benchmark(value):
    """Extracts boundary numbers from benchmark description strings."""
    val_str = str(value).strip().lower()
    if 'to' in val_str or '-' in val_str:
        numbers = [float(s) for s in re.findall(r'\d+\.\d+|\d+', val_str)]
        if len(numbers) >= 2: return numbers, numbers
    numbers = [float(s) for s in re.findall(r'\d+\.\d+|\d+', val_str)]
    if len(numbers) == 1: return numbers, numbers
    return None, None


def safe_json_number(value, digits=1):
    try:
        value = float(value)
        return round(value, digits) if np.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def forecast_health_state(value, benchmark):
    return "healthy" if value is not None and value <= benchmark else "at-risk"


def build_trend_periods(monthly_series):
    """Return the yearly > quarterly > monthly series structure for the JSON contract."""
    if monthly_series.empty:
        return []
    series = monthly_series.copy()
    series.index = series.index.to_period("M")
    series = series.groupby(level=0).mean()
    now_period = pd.Period(datetime.now(), freq="M")
    result = []
    for year in range(int(series.index.min().year), datetime.now().year + 1):
        quarters, year_values = [], []
        for quarter in range(1, 5):
            months, quarter_values = [], []
            for month in range((quarter - 1) * 3 + 1, quarter * 3 + 1):
                month_period = pd.Period(year=year, month=month, freq="M")
                value = safe_json_number(series.get(month_period))
                partial = month_period >= now_period or value is None
                months.append({"period": str(month_period), "month": month, "average": value, "isPartial": bool(partial)})
                if value is not None:
                    quarter_values.append(value)
                    year_values.append(value)
            q_end = pd.Period(year=year, month=quarter * 3, freq="M")
            quarters.append({
                "period": f"{year}-Q{quarter}", "quarter": quarter,
                "average": safe_json_number(np.mean(quarter_values)) if quarter_values else None,
                "isPartial": bool(q_end >= now_period or len(quarter_values) < 3),
                "children": {"granularity": "monthly", "periods": months},
            })
        year_end = pd.Period(year=year, month=12, freq="M")
        result.append({
            "period": str(year), "year": year,
            "average": safe_json_number(np.mean(year_values)) if year_values else None,
            "isPartial": bool(year_end >= now_period or len(year_values) < 12),
            "children": {"granularity": "quarterly", "periods": quarters},
        })
    return result

# ==============================================================================
# PART 4: PAST TREND AUDITOR & DUAL-FORECASTING ORCHESTRA
# ==============================================================================
def run_metric_pipeline(metric_idx, sheet_name, company_file, benchmark_df, target_col, date_col, metric_key_name, whitelist=None):
    print(f"\n⚡Processing Pipeline Stage for Metric {metric_idx}: [{metric_key_name}]")
    
    # Run data quality check firewall pass
    required_keys = [target_col, date_col]
    dq_passed, company_df, error_log = validate_sheet_quality(company_file, sheet_name, required_keys, metric_key_name)
    if not dq_passed:
        print(f"   ⚠️ Pipeline Halted due to Quality Constraints:\n      {error_log}")
        return None

    # Benchmark Extraction
    benchmark_missing = False
    try:
        metric_names = benchmark_df['Metric Name'].astype(str).str.strip()
        matches = benchmark_df.loc[metric_names == metric_key_name]
        if matches.empty:
            raise KeyError(f"No benchmark row found for '{metric_key_name}'")
        target_row = matches.iloc[0]
        _, bench_max = parse_benchmark(target_row['Industry Benchmark'])
        if bench_max is None:
            raise ValueError(f"No numeric benchmark is configured for '{metric_key_name}'")
        company_std = bench_max[-1] if isinstance(bench_max, (list, np.ndarray)) else bench_max
    except Exception as e:
        company_std = 5.0
        benchmark_missing = True
        print(f"   ⚠️ Benchmark configuration missing: {e}")

    clean_metric_df = company_df.dropna(subset=[target_col, date_col]).copy()
    clean_metric_df[date_col] = pd.to_datetime(clean_metric_df[date_col], errors='coerce')
    clean_metric_df = clean_metric_df.dropna(subset=[date_col])
    
    clean_metric_df[target_col] = pd.to_numeric(
        clean_metric_df[target_col].astype(str).str.replace(r'[%\s]', '', regex=True),
        errors='coerce',
    )
    # Invalid numeric strings can survive dropna() above; exclude them before
    # calculating health, trends, and forecasts so NaNs cannot contaminate results.
    clean_metric_df = clean_metric_df.dropna(subset=[target_col])
    clean_metric_df = clean_metric_df[
        np.isfinite(clean_metric_df[target_col].astype(float))
    ].copy()
    if clean_metric_df.empty:
        print(f"   ⚠️ Pipeline halted: no valid numeric values remain for '{target_col}'.")
        return None
    clean_metric_df = clean_metric_df.sort_values(date_col).reset_index(drop=True)
    
    clean_metric_df['metric_value'] = (clean_metric_df[target_col] > company_std).astype(int)

    # Core Health Engine
    total_cases = len(clean_metric_df)
    compliant_cases = (clean_metric_df['metric_value'] == 0).sum()
    company_val = clean_metric_df[target_col].mean() if total_cases > 0 else 0.0
    variance_val = company_val - company_std
    variance_pct = (variance_val / company_std) * 100 if company_std != 0 else 0
    
    compliance_pct = (compliant_cases / total_cases) * 100 if total_cases > 0 else 0.0
    health_state = "healthy" if compliance_pct >= 95.0 else "at-risk" if compliance_pct >= 85.0 else "critical"

    # Leakage Pruning and Matrix Isolation
    drop_keywords = ['ID', 'DATE', 'EMAIL', 'NAME', 'FIRST', 'LAST', 'DELAY', 'DURATION', 'METRIC', 'STATUS', 'HOURS', 'SLA', 'REVOKED', 'CALENDAR_YEAR', 'CYCLETIPEDAYS', 'METRIC_VALUE', 'DECISION', 'STEP', 'ROUTEMAP']
    drop_features = [c for c in clean_metric_df.columns if any(kw in c.upper() for kw in drop_keywords)]
    for col in [target_col, 'metric_value', 'finalDecision', 'currentStep', 'routeMap', 'approvalStepCountCompleted']:
        if col in clean_metric_df.columns and col not in drop_features: drop_features.append(col)

    X_raw = pipeline_feature_processor(clean_metric_df, drop_features, whitelist_features=whitelist)
    
    # Execute Model Tournament 
    # Keep the RCA object shape stable so consumers can use the same contract
    # whether the model trained successfully or the available data was insufficient.
    rca_model_info = {
        "modelName": None, "bestParams": None, "crossValidationF1": None,
        "accuracy": None, "precision": None, "recall": None, "f1_score": None,
        "evaluation": None, "rating": "N/A",
    }
    factors = []
    if len(X_raw) > 10 and X_raw.shape[1] > 0 and clean_metric_df[target_col].nunique() > 1:
        try:
            final_model, X_full_encoded, rca_model_info = select_best_model_cv(
                X_raw, clean_metric_df[target_col], clean_metric_df['metric_value'],
                clean_metric_df[date_col], benchmark_available=not benchmark_missing,
            )
            explainer = shap.TreeExplainer(final_model)
            raw_shap_values = explainer.shap_values(X_full_encoded)
            positive_class_index = list(final_model.classes_).index(1)
            if isinstance(raw_shap_values, list):
                raw_shap_values = raw_shap_values[positive_class_index]
            raw_shap_values = np.asarray(raw_shap_values)
            if raw_shap_values.ndim == 3:
                if raw_shap_values.shape[:2] == (len(X_full_encoded), len(X_full_encoded.columns)):
                    class_index = min(positive_class_index, raw_shap_values.shape[2] - 1)
                    raw_shap_values = raw_shap_values[:, :, class_index]
                elif raw_shap_values.shape[1:] == (len(X_full_encoded), len(X_full_encoded.columns)):
                    class_index = min(positive_class_index, raw_shap_values.shape[0] - 1)
                    raw_shap_values = raw_shap_values[class_index, :, :]
            if raw_shap_values.ndim != 2:
                raise ValueError(f"Unsupported SHAP output shape: {raw_shap_values.shape}")
            if raw_shap_values.shape == (len(X_full_encoded.columns), len(X_full_encoded)):
                raw_shap_values = raw_shap_values.T
            if raw_shap_values.shape != (len(X_full_encoded), len(X_full_encoded.columns)):
                raise ValueError(f"SHAP output does not match input shape: {raw_shap_values.shape}")
            shap_values = np.abs(raw_shap_values).mean(axis=0)
            if len(shap_values) == len(X_full_encoded.columns):
                total_impact = float(np.sum(shap_values))
                top_indices = np.argsort(shap_values)[::-1][:3]
                for rank, idx in enumerate(top_indices):
                    col_name = str(X_full_encoded.columns[idx])
                    impact_val = float(shap_values[idx])
                    pct = float((impact_val / total_impact * 100)) if total_impact > 0 else 0.0
                    factors.append({
                        "rank": int(rank + 1), "factorName": col_name, "segment": None,
                        "avgFactorValue": round(float(X_full_encoded[col_name].mean()), 1), "segmentAvgValue": None,
                        "impactValue": round(impact_val, 2), "impactPct": round(pct, 1)
                    })
        except Exception as e:
            if rca_model_info.get("modelName") in (None, "N/A"):
                print(f"   ⚠️ RCA model could not be trained: {e}")
                rca_model_info = {
                    "modelName": None, "bestParams": None, "crossValidationF1": None,
                    "accuracy": None, "precision": None, "recall": None, "f1_score": None,
                    "evaluation": None, "rating": "N/A",
                }
            else:
                print(f"   ⚠️ SHAP explanation failed; trained RCA metrics retained: {e}")

    # Historical Trend Auditing via Mann-Kendall Test
    monthly_series = clean_metric_df.set_index(date_col)[target_col].resample('ME').mean().dropna().astype(float)
    trend_direction = "no trend"
    if len(monthly_series) >= 4:
        try:
            mk_test = mk.original_test(monthly_series.values)
            trend_direction = str(mk_test.trend).lower() if mk_test.p < 0.05 else "no trend"
            print(f"   📊 [Mann-Kendall] {trend_direction}; p={mk_test.p:.4f}, tau={mk_test.Tau:.3f}")
        except Exception as e:
            print(f"   ⚠️ Mann-Kendall trend test failed: {e}")

    # Tune between damped and undamped Holt using rolling validation, then evaluate on a held-out tail.
    forecast_model_name = "DampedTrendRegression"
    forecast_accuracy = None
    forecast_values = pd.Series(dtype=float)
    model_specs = {"DampedTrendRegression": True, "LinearHoltTrend": False}
    if len(monthly_series) >= 4:
        try:
            holdout_size = min(3, len(monthly_series) // 4) if len(monthly_series) >= 8 else 0
            development = monthly_series.iloc[:-holdout_size] if holdout_size else monthly_series
            holdout = monthly_series.iloc[-holdout_size:] if holdout_size else pd.Series(dtype=float)
            origins = range(max(4, len(development) - 6), len(development))
            scores = {}
            naive_errors = [
                abs(float(development.iloc[origin]) - float(development.iloc[origin - 1]))
                for origin in origins
            ]
            for name, damped in model_specs.items():
                errors = []
                for origin in origins:
                    fit = ExponentialSmoothing(
                        development.iloc[:origin], trend="add", damped_trend=damped,
                        seasonal=None, initialization_method="estimated",
                    ).fit()
                    errors.append(abs(float(development.iloc[origin]) - float(fit.forecast(1).iloc[0])))
                if errors:
                    scores[name] = float(np.mean(errors))
            if scores:
                best_trend_name = min(scores, key=scores.get)
                naive_rolling_mae = float(np.mean(naive_errors)) if naive_errors else float("inf")
                forecast_model_name = best_trend_name
                baseline_result = "beats" if scores[best_trend_name] < naive_rolling_mae else "does not beat"
                print(
                    f"   🏁 Forecast candidate: {forecast_model_name} "
                    f"(rolling MAE={scores[forecast_model_name]:.3f}; naive MAE={naive_rolling_mae:.3f}; "
                    f"trend {baseline_result} baseline)"
                )
            if holdout_size and scores:
                check_fit = ExponentialSmoothing(
                    development, trend="add", damped_trend=model_specs[forecast_model_name],
                    seasonal=None, initialization_method="estimated",
                ).fit()
                holdout_predictions = check_fit.forecast(holdout_size).to_numpy()
                holdout_actuals = holdout.to_numpy()
                holdout_mae = float(np.mean(np.abs(holdout_actuals - holdout_predictions)))
                holdout_scale = float(np.mean(np.abs(holdout_actuals)))
                if holdout_scale > 1e-9:
                    forecast_accuracy = round(max(0.0, min(1.0, 1.0 - holdout_mae / holdout_scale)), 2)
                print(f"   📏 Forecast holdout MAE={holdout_mae:.3f}; normalized accuracy={forecast_accuracy}")
            elif not holdout_size:
                print("   ℹ️ Too little history for an independent forecast holdout; accuracy remains null.")
            winner_fit = ExponentialSmoothing(
                monthly_series, trend="add", damped_trend=model_specs[forecast_model_name],
                seasonal=None, initialization_method="estimated",
            ).fit()
            forecast_values = winner_fit.forecast(steps=12)
        except Exception as e:
            print(f"   ⚠️ Forecast selection/fit failed; forecast accuracy remains null: {e}")

    fallback_forecast = float(monthly_series.iloc[-1]) if len(monthly_series) else float(company_val)
    nm_val = max(0.0, float(forecast_values.iloc[0])) if len(forecast_values) >= 1 else fallback_forecast
    nq_step = min(3, len(forecast_values))
    nq_val = max(0.0, float(forecast_values.iloc[nq_step - 1])) if nq_step else fallback_forecast
    ny_val = max(0.0, float(forecast_values.iloc[11])) if len(forecast_values) >= 12 else fallback_forecast
    std_val = float(monthly_series.std()) if len(monthly_series) > 1 else abs(fallback_forecast) * 0.15

    now = pd.Timestamp.now()
    quarter_step = 3 - ((now.month - 1) % 3)
    next_quarter = now.to_period("Q") + 1

    def make_forecast_item(period, value):
        return {
            "period": period,
            "predictedValue": safe_json_number(value),
            "lowerBound": safe_json_number(max(0.0, value - 1.5 * std_val)),
            "upperBound": safe_json_number(value + 1.5 * std_val),
            "predictedHealthState": forecast_health_state(value, company_std),
        }

    forecast_payload = {
        "applicable": bool(len(forecast_values) > 0),
        "status": "Available" if len(forecast_values) > 0 else "Data Missing",
        "message": None if len(forecast_values) > 0 else "Forecast was not performed because essential metric data is incomplete.",
        "nextMonth": make_forecast_item((now.to_period("M") + 1).strftime("%Y-%m"), nm_val),
        "nextQuarter": make_forecast_item(f"{next_quarter.year}-Q{next_quarter.quarter}", nq_val),
        "nextYear": make_forecast_item(str(now.year + 1), ny_val),
    }

    # Configuration reports describe absent columns. Blank or invalid cell
    # values are reported by the data-quality checks below, not as missing fields.
    mandatory_fields_missing = [col for col in required_keys if col not in company_df.columns]
    other_fields_missing = [
        str(col) for col in (whitelist or [])
        if col not in company_df.columns and col not in mandatory_fields_missing
    ]
    missing_value_columns = []
    # Keep the record-level completeness count consistent with the column-level
    # missing-configuration list. A target containing "abc" or an invalid date
    # is unusable even though it is not technically NaN in the source workbook.
    mandatory_failure_mask = pd.Series(False, index=company_df.index)
    for col in required_keys:
        values = company_df[col]
        missing = values.isna() | values.astype(str).str.strip().eq("")
        if col == target_col:
            numeric = pd.to_numeric(values.astype(str).str.replace(r"[%\s]", "", regex=True), errors="coerce")
            missing |= numeric.isna()
        elif col == date_col:
            missing |= pd.to_datetime(values, errors="coerce").isna()
        mandatory_failure_mask |= missing
        if missing.any():
            missing_value_columns.append(col)
    missing_value_columns.extend(
        str(col) for col in company_df.columns
        if col not in missing_value_columns
        and (company_df[col].isna() | company_df[col].astype(str).str.strip().eq("")).any()
    )
    missing_count = int(mandatory_failure_mask.sum())
    records_analysed = int(len(clean_metric_df))
    data_quality_rating = "excellent" if missing_count == 0 else "good" if missing_count / max(1, len(company_df)) < 0.05 else "fair"
    trend_direction = {"increasing": "up", "decreasing": "down"}.get(trend_direction, trend_direction)

    json_output = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "module": "EC", "reportVersion": "2.2", "metricName": metric_key_name,
        "unit": "percent" if "Frequency" in metric_key_name else "days",
        "higherIsBetter": False, "companyValue": round(float(company_val), 1), "customStandardValue": round(float(company_std), 1),
        "healthState": health_state, "variance": {"value": round(float(variance_val), 1), "percentage": round(float(variance_pct), 1)},
        "trendAnalysis": {"direction": trend_direction, "granularity": "yearly", "periods": build_trend_periods(monthly_series)},
        "forecast": forecast_payload,
        "rca": {
            "applicable": len(factors) > 0,
            "status": "Available" if factors else "Data Missing",
            "message": None if factors else "RCA was not performed because essential metric data is incomplete.",
            "breachValue": round(float(variance_val), 1), "factors": factors,
        },
        "dataQuality": {
            "overallRating": data_quality_rating,
            "dataPeriod": {
                "from": clean_metric_df[date_col].min().strftime("%Y-%m-%d") if records_analysed else None,
                "to": clean_metric_df[date_col].max().strftime("%Y-%m-%d") if records_analysed else None,
            },
            "recordsAnalysed": records_analysed,
            "checks": [
                {
                    "checkName": "MissingValues", "category": "Completeness",
                    "checkedRecords": int(len(company_df)), "failedRecords": missing_count,
                    "failedPct": round(missing_count / max(1, len(company_df)) * 100, 2),
                    "affectedColumns": missing_value_columns,
                    "affectedCells": int(sum(
                        int(company_df[col].isna().sum())
                        for col in company_df.columns
                    )),
                },
                {
                    "checkName": "InvalidValues", "category": "Validity",
                    "checkedRecords": int(len(company_df)),
                    "failedRecords": int(len(company_df) - len(clean_metric_df)),
                    "failedPct": round(max(0, len(company_df) - len(clean_metric_df)) / max(1, len(company_df)) * 100, 2),
                    "affectedColumns": [target_col, date_col],
                },
                {
                    "checkName": "DuplicateRecords", "category": "Uniqueness",
                    "checkedRecords": int(len(company_df)), "failedRecords": int(company_df.duplicated().sum()),
                    "failedPct": round(int(company_df.duplicated().sum()) / max(1, len(company_df)) * 100, 2),
                    "affectedColumns": None,
                },
                {
                    "checkName": "Staleness", "category": "Staleness",
                    "checkedRecords": int(len(clean_metric_df)),
                    "failedRecords": int((clean_metric_df[date_col] < pd.Timestamp.now().normalize() - pd.DateOffset(years=3)).sum()),
                    "failedPct": round(int((clean_metric_df[date_col] < pd.Timestamp.now().normalize() - pd.DateOffset(years=3)).sum()) / max(1, len(clean_metric_df)) * 100, 2),
                    "affectedColumns": [date_col],
                    "staleRange": "> 3 years old",
                },
            ],
        },
        "selectedTrainingModel": {
            "rcaModel": {
                "modelName": rca_model_info.get("modelName"),
                "status": "Available" if rca_model_info.get("modelName") else "Data Missing",
                "trainingPerformed": bool(rca_model_info.get("modelName")),
            },
            "forecastModel": {
                "modelName": forecast_model_name if len(forecast_values) > 0 else None,
                "status": "Available" if len(forecast_values) > 0 else "Data Missing",
                "trainingPerformed": bool(len(forecast_values) > 0),
            },
        },
        "missingConfigurations": {
            "mandatoryFieldsMissing": mandatory_fields_missing,
            "otherFieldsMissing": other_fields_missing,
        },
    }

    safe_metric_filename = re.sub(r'[<>:"/\\|?*]', "_", metric_key_name).strip().rstrip(".")
    output_path = os.path.join(OUTPUT_DIR, f"{safe_metric_filename}.json")
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(json_output, output_file, indent=2, ensure_ascii=False, allow_nan=False)
        output_file.write("\n")
    print(f"   💾 Local JSON saved: {os.path.basename(output_path)}")
    
    # Cloud DB Streaming Execution Block
    if supabase_client is not None:
        try:
            pascal_case_metric_name = "".join(w.capitalize() for w in re.findall(r'[a-zA-Z0-9]+', metric_key_name))
            db_row = {
                "Module_Name": "EC",
                "Metric_Name": pascal_case_metric_name,
                "JSON_Result": json_output
            }
            # Keep one current result per module/metric instead of adding a row
            # every time this script runs. If this metric has not been saved
            # before, create its first row.
            result_table = supabase_client.table(CUSTOM_INSIGHTS_TABLE)
            update_result = (
                result_table.update({"JSON_Result": json_output})
                .eq("Module_Name", "EC")
                .eq("Metric_Name", pascal_case_metric_name)
                .execute()
            )
            if not update_result.data:
                result_table.insert(db_row).execute()
            print(f"   🚀 Live Cloud Sync: Successfully saved [{pascal_case_metric_name}] to table [{CUSTOM_INSIGHTS_TABLE}].")
        except Exception as sb_err:
            print(f"   ❌ Cloud Data Write Failure: {sb_err}")
            
    return json_output

# ==============================================================================
# PART 5: STREAMING CLOUD CONSOLE EXECUTION CORE LOOP
# ==============================================================================
if __name__ == "__main__":
    print("🎬 Starting Optimized Enterprise Cloud Workflow Ingestion Loop...")

    try:
        if supabase_client is not None:
            print(f"📥 Fetching workbooks from Supabase Storage bucket [{SUPABASE_BUCKET}]...")
            benchmark_bytes = supabase_client.storage.from_(SUPABASE_BUCKET).download(CUSTOM_STANDARDS_FILE_PATH)
            benchmark_df = pd.read_excel(io.BytesIO(benchmark_bytes))
            company_bytes = supabase_client.storage.from_(SUPABASE_BUCKET).download(OFB2_FILE_PATH)
            company_workbook = pd.ExcelFile(io.BytesIO(company_bytes))
        else:
            benchmark_path = CUSTOM_STANDARDS_FILE_PATH
            if not os.path.isfile(benchmark_path) or not os.path.isfile(OFB2_FILE_PATH):
                raise FileNotFoundError(
                    "Without Supabase credentials, place both Excel workbooks locally or configure .env paths."
                )
            benchmark_df = pd.read_excel(benchmark_path)
            company_workbook = pd.ExcelFile(OFB2_FILE_PATH)
        print("   ✅ Input workbooks are ready.")
    except Exception as e:
        print(f"❌ Critical Ingestion Error: Unable to load input workbooks: {e}")
        exit(1)

    # Launch Segment: Sequential Execution of Core Matrix Targets
    # Metric 1: Cycle Time Analytics
    m1_rca_fields = [
        "workflowType", "transactionType", "numberOfApprovalSteps",
        "approverRole", "positionCode", "workflowPriority", "approvalLevel", "sourceModule",
    ]
    run_metric_pipeline(
        metric_idx=1, sheet_name='Workflow Approval Cycle Time', company_file=company_workbook,
        benchmark_df=benchmark_df, target_col='cycleTimeDays', date_col='workflowInitiatedDateTime',
        metric_key_name='Workflow Approval Cycle Time', whitelist=m1_rca_fields
    )
    
    # Metric 2: Change Request Duration Telemetry
    m2_sheet = 'Avg Time Data Change Req' if 'Avg Time Data Change Req' in company_workbook.sheet_names else 'Avg_Time_Process_Change_Requests'
    m2_rca_fields = ["changeDetail", "requestType"]
    run_metric_pipeline(
        metric_idx=2, sheet_name=m2_sheet, company_file=company_workbook,
        benchmark_df=benchmark_df, target_col='processingTimeDays', date_col='requestDate',
        metric_key_name='Avg. Time to Process Data Change Requests', whitelist=m2_rca_fields
    )
    
    # Metric 3: Retroactive Changes Frequency Analysis (RDC Layout Mapping)
    m3_sheet = 'Retroactive Data Changes' if 'Retroactive Data Changes' in company_workbook.sheet_names else 'Retroactive Data Changes Frequency'
    m3_whitelist = ["numberOfApprovalSteps", "workflowType", "transactionType", "workflowPriority", "approvalLevel", "changeType", "changeInitiator"]
        
    run_metric_pipeline(
        metric_idx=3, sheet_name=m3_sheet, company_file=company_workbook,
        benchmark_df=benchmark_df, 
        target_col='backdatedDays',  # Dynamically points to your explicit RDC numerical parameter
        date_col='entryDate',        # Dynamically points to your explicit RDC chronology anchor
        metric_key_name='Retroactive Data Changes Frequency',
        whitelist=m3_whitelist
    )

    print("\n🚀 Pipeline completed. JSON summaries were saved.")
