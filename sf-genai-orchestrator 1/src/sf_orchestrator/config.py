from __future__ import annotations

import re

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """Raised at startup with every configuration problem listed. Never contains secret values."""


# Vendor prefix used in LLM_CHAIN -> the Settings field that holds its API key.
VENDOR_KEY_FIELDS = {"gemini": "gemini_api_key", "groq": "groq_api_key"}


class Settings(BaseSettings):
    """Read from real environment variables first, then from .env in the working directory."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    log_level: str = "INFO"

    # Record the runs for the dashboard (the tables of sql/dashboard.sql). Set DASHBOARD_TRACKING=false to switch it off.
    dashboard_tracking: bool = True

    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    # The tables of the industry standards: the ML notebooks write the insights to INSIGHTS_TABLE (for example ML_Notebook_Insights),
    # and the orchestrator saves the reports to REPORTS_TABLE (for example LLM_Reports, created by sql/llm_reports.sql).
    # Table names are case-sensitive.
    insights_table: str | None = None
    reports_table: str | None = None

    # A healthy metric gets a short summary of how well it is doing. Set HEALTHY_SUMMARIES=false to skip healthy metrics.
    healthy_summaries: bool = True
    # A metric the notebook could not calculate because mandatory fields are missing gets a plan to set those fields up.
    # Set SETUP_REPORTS=false to skip such metrics.
    setup_reports: bool = True

    # The ML notebooks (.py files) that `sf-pipeline` runs before the LLM step.
    notebooks_dir: str = "notebooks"
    notebook_timeout_minutes: float = Field(default=60, gt=0)  # a notebook that runs longer is stopped and counted as failed
    notebook_concurrency: int = Field(default=1, ge=1)  # how many notebooks run at the same time
    notebook_python: str | None = None  # interpreter for the notebooks, if they need packages this one does not have
    logs_dir: str = "logs"  # everything a notebook prints is kept in <logs_dir>/<run-date>/<notebook>.log

    # Custom standards: the company's own benchmarks (an xlsx file in a Storage bucket) instead of the industry ones. They have their
    # own notebooks folder, their own insights table (written by those notebooks) and their own reports table (sql/llm_reports_custom.sql).
    # Leave CUSTOM_INSIGHTS_TABLE and CUSTOM_REPORTS_TABLE out and `sf-pipeline` simply does not run the custom part.
    custom_standards_bucket: str = "SF_Health_Raw_Data"
    custom_standards_file_path: str = "SF Health Monitoring Custom Standards.xlsx"  # the same variable the custom notebooks read
    custom_insights_table: str | None = None
    custom_reports_table: str | None = None
    custom_notebooks_dir: str = "notebooks_custom"

    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    llm_chain: str = ""

    llm_temperature: float = 0.2
    llm_max_tokens: int = 16384
    # How much the model may "think" before it answers. Thinking tokens are billed (and shown) as OUTPUT tokens, and for this task
    # (a fixed template filled from the input) they add cost, not quality. One of: minimal, low, medium, high, disable. Leave it empty
    # to use the model's own default. A model that has no such setting simply ignores it.
    llm_reasoning_effort: str = "low"
    llm_timeout_seconds: int = 90
    llm_num_retries: int = 2  # retries on the SAME model for timeouts / 5xx / 503 "high demand"
    llm_rate_limit_retries: int = 1  # waits for a 429 (the provider says how long) and retries the same model
    llm_retry_wait_seconds: int = 10  # minimum wait between retries of the same model (max 60)
    llm_allowed_fails: int = 2
    llm_cooldown_seconds: int = 120  # a model that keeps failing is skipped this long, then tried again
    llm_repair_attempts: int = 1
    orchestrator_concurrency: int = 1  # one metric at a time keeps Groq's tokens-per-minute limit in check

    @field_validator("reports_table", "insights_table", "custom_insights_table", "custom_reports_table")
    @classmethod
    def _plain_table_name(cls, v: str | None) -> str | None:
        v = v.strip() if v else v
        if v and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v):
            raise ValueError("must contain only letters, digits and underscores, for example LLM_Reports")
        return v or None

    @field_validator("supabase_service_role_key", "gemini_api_key", "groq_api_key")
    @classmethod
    def _not_too_short(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and len(v.get_secret_value()) < 10:
            raise ValueError("value looks too short to be a real key")
        return v

    @property
    def custom_configured(self) -> bool:
        """True when both tables of the custom standards are named, so that the custom part of the pipeline can run."""
        return bool(self.custom_insights_table and self.custom_reports_table)

    @property
    def chain(self) -> list[str]:
        """Ordered, de-duplicated LiteLLM model strings, e.g. ['gemini/a', 'gemini/b', 'groq/openai/c', 'groq/openai/d']."""
        seen: dict[str, None] = {}
        for part in self.llm_chain.split(","):
            if part.strip():
                seen.setdefault(part.strip(), None)
        return list(seen)

    def secret_values(self) -> list[str]:
        secrets = (self.supabase_service_role_key, self.gemini_api_key, self.groq_api_key)
        return [s.get_secret_value() for s in secrets if s is not None]


def load_settings(
    *, require_llm: bool = True, require_supabase: bool = True, require_tables: bool = True, require_custom: bool = False, **overrides: object
) -> Settings:
    """Validate everything once, up front.
    `require_llm=False` is for --dry-run (no LLM keys needed); `require_supabase=False` is for a pipeline run without the LLM step;
    `require_tables=False` is for the dashboard, which reads only its own tables;
    `require_custom=True` is for a run of the custom standards ONLY, which cannot work without their two tables (and does not use
    INSIGHTS_TABLE and REPORTS_TABLE)."""
    try:
        settings = Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as err:
        # Built from location + message only: pydantic's default text would echo the offending value.
        problems = [f"{'.'.join(str(p) for p in e['loc']).upper()}: {e['msg']}" for e in err.errors()]
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(problems)) from None

    problems: list[str] = []
    if require_supabase and not (settings.supabase_url and settings.supabase_service_role_key):
        problems.append("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    if require_supabase and require_tables and not require_custom and not (settings.insights_table and settings.reports_table):
        problems.append("INSIGHTS_TABLE and REPORTS_TABLE are required (for example ML_Notebook_Insights and LLM_Reports)")
    if bool(settings.custom_insights_table) != bool(settings.custom_reports_table):
        problems.append("CUSTOM_INSIGHTS_TABLE and CUSTOM_REPORTS_TABLE must be set together (one without the other cannot work)")
    if require_custom and not settings.custom_configured:
        problems.append("The custom standards need CUSTOM_INSIGHTS_TABLE (for example ML_Notebook_Custom_Insights) and CUSTOM_REPORTS_TABLE (for example LLM_Reports_Custom)")
    if require_llm and not settings.chain:
        problems.append("LLM_CHAIN is empty. List at least one model, e.g. gemini/<model-id>")
    for entry in settings.chain:
        vendor, _, model = entry.partition("/")
        if "<" in entry or ">" in entry:
            problems.append(f'LLM_CHAIN entry "{entry}" still contains a <placeholder>; put a real model id')
        elif vendor not in VENDOR_KEY_FIELDS or not model:
            problems.append(f'LLM_CHAIN entry "{entry}" must look like gemini/<model-id> or groq/<model-id>')
        elif require_llm and getattr(settings, VENDOR_KEY_FIELDS[vendor]) is None:
            problems.append(f"{VENDOR_KEY_FIELDS[vendor].upper()} is required because LLM_CHAIN uses {vendor}/...")
    if problems:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(problems))
    return settings